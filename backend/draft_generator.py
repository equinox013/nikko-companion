"""
backend/draft_generator.py
============================
HFSpaceFullGenerator — implements DraftGeneratorProtocol by calling the remote
/pipeline inference endpoint (Modal primary, HF Space fallback).

This is the bridge between the local NikkoPipeline (agents, RAG, signal detection,
routing, strategy) and the remote LLM inference layer (Qwen3-4B for ADP-A, Gemma-2
for ADP-B/C).

Data flow
---------
  NikkoPipeline produces ResponseContextPayload
      │
      ▼
  HFSpaceFullGenerator.generate(context)
      ├── build_adp_a_system(context)   ← injects synthesized evidence (RAG)
      ├── build_adp_b_system()          ← static safety classifier prompt
      └── build_adp_c_system(context)   ← mode-aware evaluator prompt
      │
      ▼
  POST /pipeline → Modal Serverless (primary)  (ADP-B → ADP-A → ADP-C)
      │   on httpx error or non-2xx
      └── POST /pipeline → HF Space ZeroGPU (fallback)
      │
      ▼
  Returns approved response text

Fallback behaviour
------------------
If the primary URL raises an httpx exception or returns a non-2xx status, the
call is transparently retried against the fallback URL (if one was provided).
This gives zero-downtime failover: Modal down → requests route to HF Space.
The user gets a slower response (ZeroGPU cold start) but not an error.

Sync / async note
-----------------
DraftGeneratorProtocol.generate() is synchronous (pipeline.py is sync throughout).
HFSpaceFullGenerator uses httpx.Client (blocking) for the HTTP call. In backend/main.py,
pipeline.run() is wrapped in asyncio.to_thread() so this blocking call does not hold
the FastAPI async event loop while waiting for the GPU (30-120s cold start).
"""

import logging
import time

import httpx

from backend.context_prompt_builder import (
    build_adp_a_system,
    build_adp_b_system,
    build_adp_c_system,
)
from docs.schemas.acp_schemas import ResponseContextPayload
from orchestration.pipeline import ADPB_CRISIS_SENTINEL

logger = logging.getLogger(__name__)

# Timeout budget per inference endpoint.
# Modal: cold start ~30-60s; warm turn ~20-40s. 360s gives ~5x headroom.
# HF Space (fallback): cold start up to 600s observed. 720s ceiling gives ~2 min
# headroom beyond worst case while still failing fast on genuine hangs.
_MODAL_TIMEOUT_S    = 360
_HF_SPACE_TIMEOUT_S = 720


class HFSpaceFullGenerator:
    """
    Concrete implementation of DraftGeneratorProtocol that calls the HF Space
    /pipeline endpoint with context-enriched prompts.

    This replaces the StubDraftGenerator used in Phase 3. It does NOT replace
    the local EvaluatorAgent or VerificationSupervisor — those still run in
    NikkoPipeline after generate() returns, providing an additional local
    quality gate on top of ADP-C's evaluation in the HF Space.

    Usage (wired in backend/main.py at startup):
        generator = HFSpaceFullGenerator(
            hf_space_url=os.getenv("HF_SPACE_URL"),
            token=os.getenv("NIKKO_INTERNAL_TOKEN", ""),
        )
        pipeline = NikkoPipeline(draft_generator=generator)
    """

    def __init__(self, hf_space_url: str, token: str = "", fallback_url: str = "") -> None:
        """
        Parameters
        ----------
        hf_space_url : Primary inference endpoint base URL (Modal in production).
                       Set via Render env var: MODAL_URL=https://...
                       Falls back to HF Space if MODAL_URL is not set.
        token        : NIKKO_INTERNAL_TOKEN shared secret. Empty string skips
                       auth (development only).
        fallback_url : Secondary inference endpoint (HF Space ZeroGPU).
                       Set via Render env var: HF_SPACE_URL=https://...
                       If provided, generate() retries against this URL on any
                       httpx error or non-2xx response from the primary.
        """
        self._url      = hf_space_url.rstrip("/")
        self._token    = token
        self._fallback = fallback_url.rstrip("/") if fallback_url else None

    def generate(self, context: ResponseContextPayload) -> str:
        """
        Build context-enriched prompts and call POST /pipeline on the HF Space.

        [CONCEPT] The three system prompts sent to the Space are built here:
        - ADP-A prompt includes synthesized PubMed/web evidence (RAG injection)
        - ADP-B prompt is static (deterministic safety classifier)
        - ADP-C prompt gets a mode-aware evaluation instruction
        Each prompt was produced by local agents before this method was called.

        Returns the approved response text. Returns "" if ADP-B detects crisis
        after local routing (should be rare — NikkoPipeline already routes CRISIS
        messages before reaching generate(), but we handle it defensively).

        Raises httpx.HTTPError on network or server failure; NikkoPipeline's
        _step10_draft() catches this and emits SAFE_FALLBACK_RESPONSE.
        """
        user_msg = context.raw_user_message or ""
        if not user_msg:
            logger.warning(
                "HFSpaceFullGenerator.generate(): raw_user_message is empty. "
                "ResponseContextPayload may have been constructed without it."
            )

        # [CONCEPT] messages is a list of chat turn dicts. For a single-turn
        # request we send just the user message. Multi-turn history would extend
        # this list — a Phase 5 enhancement (USM memory integration, REQ-850-070).
        messages = [{"role": "user", "content": user_msg}]

        payload = {
            "messages":      messages,
            "system":        build_adp_a_system(context),   # RAG evidence injected here
            "safety_system": build_adp_b_system(),
            "eval_system":   build_adp_c_system(context),
            "token":         self._token,
        }

        logger.info(
            "HFSpaceFullGenerator: calling pipeline endpoint | mode=%s evidence_items=%d",
            context.mode.value,
            len(context.synthesized_evidence.citations) if context.synthesized_evidence else 0,
        )

        # Build ordered list of URLs to try: primary first, fallback second (if set).
        # [CONCEPT] The fallback list means generate() is self-healing: if Modal is
        # unavailable (cold-start timeout, deploy in progress, quota exceeded), the
        # request silently retries against the HF Space. No code changes needed on
        # the Render backend — the response shape is identical from both endpoints.
        urls_to_try = [self._url]
        if self._fallback:
            urls_to_try.append(self._fallback)

        # [CONCEPT] 429 retry strategy for the primary (Modal) endpoint.
        # Modal returns 429 when its GPU container is temporarily busy processing
        # a previous request. Instead of immediately falling back to the slow HF
        # Space (~90-120s cold start), we wait and retry — the container is usually
        # free again within one inference cycle (~20-40s warm).
        # Three retries × 10s = 30s max patience before accepting the fallback.
        # The HF Space never gets 429-retried: its ZeroGPU queue handles concurrency.
        _MAX_429_RETRIES = 3
        _429_BACKOFF_S   = 10   # seconds between retries

        last_exc: Exception | None = None
        succeeded = False

        for idx, url in enumerate(urls_to_try):
            # Tighter timeout for Modal (fast GPU); relaxed for HF Space (cold start).
            read_timeout  = _MODAL_TIMEOUT_S if idx == 0 else _HF_SPACE_TIMEOUT_S
            _timeout      = httpx.Timeout(read=read_timeout, connect=10.0, write=30.0, pool=5.0)
            is_primary    = (idx == 0)
            max_attempts  = (_MAX_429_RETRIES + 1) if is_primary else 1

            for attempt in range(max_attempts):
                # Sleep before retries (not before the first attempt).
                if attempt > 0:
                    time.sleep(_429_BACKOFF_S)
                try:
                    with httpx.Client(timeout=_timeout) as client:
                        # URLs are complete endpoint URLs — no path suffix needed.
                        # Modal:    https://equinox013--nikko-pipeline.modal.run
                        # HF Space: https://equinox013-nikko-inference.hf.space/pipeline
                        resp = client.post(url, json=payload)

                    # 429 on primary with retries remaining → sleep-and-retry.
                    if resp.status_code == 429 and is_primary and attempt < _MAX_429_RETRIES:
                        logger.warning(
                            "HFSpaceFullGenerator: Modal 429 (attempt %d/%d) — "
                            "container busy. Retrying in %ds...",
                            attempt + 1, _MAX_429_RETRIES, _429_BACKOFF_S,
                        )
                        continue  # next attempt in inner loop

                    resp.raise_for_status()   # raises on 4xx/5xx (including final 429)
                    succeeded = True
                    break                     # success — exit inner attempt loop

                except Exception as exc:
                    logger.warning(
                        "HFSpaceFullGenerator: /pipeline call to %s failed (%s). %s",
                        url,
                        exc,
                        "Retrying against fallback..." if idx < len(urls_to_try) - 1 else "No more URLs to try.",
                    )
                    last_exc = exc
                    break  # non-retryable error — exit inner loop, try next URL

            if succeeded:
                break   # exit URL loop — we have a good response

        if not succeeded:
            # All URLs exhausted (or all retries consumed).
            raise last_exc or RuntimeError("Pipeline request failed — no URLs remaining.")

        result = resp.json()

        # ADP-B fired crisis — the local stub SignalAgent missed the signal
        # (it only handles keyword-based guidance detection). Return the sentinel
        # so NikkoPipeline.run() intercepts it and issues a proper CRISIS
        # PipelineResult with hotlines and safetyFlags. Previously returned ""
        # here, which cascaded to SAFE_FALLBACK with no crisis resources shown.
        if result.get("is_crisis"):
            logger.warning(
                "HFSpaceFullGenerator: ADP-B late-crisis override — flags=%s. "
                "Returning ADPB_CRISIS_SENTINEL for pipeline re-route.",
                result.get("flags"),
            )
            return ADPB_CRISIS_SENTINEL

        text = result.get("text", "")
        logger.info(
            "HFSpaceFullGenerator: /pipeline done | verdict=%s regen=%s elapsed=%.1fs chars=%d",
            result.get("verdict"),
            result.get("regen"),
            result.get("elapsed", 0),
            len(text),
        )
        return text

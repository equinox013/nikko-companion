"""
backend/draft_generator.py
============================
HFSpaceFullGenerator — implements DraftGeneratorProtocol by calling HF Space /pipeline.

This is the bridge between the local NikkoPipeline (agents, RAG, signal detection,
routing, strategy) and the remote LLM inference layer (Qwen3-4B for ADP-A, Gemma-2
for ADP-B/C on ZeroGPU).

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
  POST /pipeline → HF Space ZeroGPU (ADP-B → ADP-A → ADP-C)
      │
      ▼
  Returns approved response text

Sync / async note
-----------------
DraftGeneratorProtocol.generate() is synchronous (pipeline.py is sync throughout).
HFSpaceFullGenerator uses httpx.Client (blocking) for the HTTP call. In backend/main.py,
pipeline.run() is wrapped in asyncio.to_thread() so this blocking call does not hold
the FastAPI async event loop while waiting for the GPU (30-120s cold start).
"""

import logging

import httpx

from backend.context_prompt_builder import (
    build_adp_a_system,
    build_adp_b_system,
    build_adp_c_system,
)
from docs.schemas.acp_schemas import ResponseContextPayload
from orchestration.pipeline import ADPB_CRISIS_SENTINEL

logger = logging.getLogger(__name__)

# Generous timeout: cold start (~120s model load) + 3 adapter passes + regen pass.
# Matches PIPELINE_TIMEOUT_S in the original backend/main.py.
_PIPELINE_TIMEOUT_S = 360


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

    def __init__(self, hf_space_url: str, token: str = "") -> None:
        """
        Parameters
        ----------
        hf_space_url : Base URL of the HF Space, e.g. https://user-space.hf.space
                       Set via Fly.io secret: fly secrets set HF_SPACE_URL=...
        token        : NIKKO_INTERNAL_TOKEN shared secret. Empty string skips
                       auth (development only).
        """
        self._url   = hf_space_url.rstrip("/")
        self._token = token

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
            "HFSpaceFullGenerator: calling /pipeline | mode=%s evidence_items=%d",
            context.mode.value,
            len(context.synthesized_evidence.citations) if context.synthesized_evidence else 0,
        )

        with httpx.Client(timeout=_PIPELINE_TIMEOUT_S) as client:
            resp = client.post(f"{self._url}/pipeline", json=payload)
            resp.raise_for_status()

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

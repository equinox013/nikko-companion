"""
backend/main.py -- Nikko orchestration API (Phase 7 / MVP infra).

Sits between the React frontend and the HF Spaces inference layer.
Implements the full SPEC-700 pipeline per SPEC-200 and SPEC-300:

  STEP 0   ScopeClassifier       — out-of-scope early exit
  STEP 1   Input sanitization
  STEP 2   SignalAgent            — psychological signal detection
  STEP 3   Router                 — COMFORT / GUIDANCE / CRISIS
  STEP 4-8 Evidence retrieval + synthesis  (Guidance Mode only — RAG)
           PubMedAdapter → WebSearchAdapter → EvidenceSynthesizerAgent
  STEP 9   SupportStrategyAgent   — tone + framing guidance
  STEP 10  HFSpaceFullGenerator   — calls HF Space /pipeline with evidence-
                                    enriched prompts (ADP-B → ADP-A → ADP-C)
  STEP 11  EvaluatorAgent         — local rule-based quality gate
  STEP 12  VerificationSupervisor — structural final gate

The connection between local agents and the LLM models is:
  NikkoPipeline (local) → HFSpaceFullGenerator → HF Space ZeroGPU (remote)

RAG path (Guidance Mode):
  SignalAgent detects distress → Router routes to GUIDANCE →
  PubMed/WebSearch retrieves evidence → EvidenceSynthesizer summarizes →
  HFSpaceFullGenerator injects evidence into ADP-A system prompt →
  Qwen3-4B generates evidence-grounded response.

Endpoints contracted in FRONTEND_INTEGRATION_SPEC.md:
  GET  /health           -- loading screen polls this (REQ-FIS-LS2)
  POST /api/message      -- primary chat, streams SSE to frontend
  POST /api/message/mock -- hardcoded fixture for frontend testing
"""

import asyncio
import json
import logging
import os
import time
import uuid
from typing import AsyncGenerator

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.draft_generator import HFSpaceFullGenerator
from docs.schemas.acp_schemas import OperationalMode
from orchestration.pipeline import NikkoPipeline, PipelineResult

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ── Config ────────────────────────────────────────────────────────────────────

# Primary inference endpoint: Modal Serverless.
# Set on Render: MODAL_URL=https://<your-modal-app>--nikko-pipeline.modal.run
# Obtain from `modal deploy nikko_modal/app.py` output.
MODAL_URL = os.getenv("MODAL_URL", "").rstrip("/")

# Modal health endpoint — separate Modal function from the pipeline.
# The pipeline URL (MODAL_URL) is a POST-only FastAPI endpoint; doing GET /health
# on it returns 404/405.  The health function has its own URL:
#   https://equinox013--nikko-health.modal.run
# Set on Render: MODAL_HEALTH_URL=https://equinox013--nikko-health.modal.run
# If not set, falls back to using MODAL_URL root (GET /) which returns 200
# from the root handler added in backend/main.py — but that only checks Render,
# not Modal.  Setting MODAL_HEALTH_URL is strongly recommended for production.
MODAL_HEALTH_URL = os.getenv("MODAL_HEALTH_URL", "").rstrip("/")

# Fallback inference endpoint: HF Space ZeroGPU.
# Used when Modal is unreachable or returns an error.
# Set on Render: HF_SPACE_URL=https://<your-hf-space>.hf.space
HF_SPACE_URL = os.getenv("HF_SPACE_URL", "").rstrip("/")

# Shared secret with both inference endpoints.
# Set on Render: NIKKO_INTERNAL_TOKEN=<value>
# Set on Modal:  modal secret create nikko-config NIKKO_INTERNAL_TOKEN=<same value>
INTERNAL_TOKEN = os.getenv("NIKKO_INTERNAL_TOKEN", "")

# ── Pipeline initialisation ───────────────────────────────────────────────────

# [CONCEPT] NikkoPipeline is instantiated once at module load time (FastAPI startup).
# It is stateless per-turn — all state lives in PipelineTrace which is created and
# destroyed within a single NikkoPipeline.run() call (REQ-700-LOG1).
#
# HFSpaceFullGenerator bridges local agents to the remote LLM:
#   - In Guidance Mode, it injects PubMed/web evidence into Qwen3-4B's system prompt
#   - In Comfort Mode, it sends a persona + strategy prompt only
# If HF_SPACE_URL is not set (local dev), HFSpaceFullGenerator will raise at
# generate() time and NikkoPipeline will catch it → SAFE_FALLBACK_RESPONSE.

# Primary URL: Modal if configured, otherwise fall back to HF Space directly.
# Fallback URL: HF Space (only set if Modal is the primary — avoids double HF calls).
_primary_url  = MODAL_URL or HF_SPACE_URL
_fallback_url = HF_SPACE_URL if MODAL_URL else ""

_generator = HFSpaceFullGenerator(
    hf_space_url=_primary_url,
    token=INTERNAL_TOKEN,
    fallback_url=_fallback_url,
)
_nikko     = NikkoPipeline(draft_generator=_generator)  # renamed: _pipeline collides with the async def below

log.info(
    "NikkoPipeline initialised | primary=%s fallback=%s",
    _primary_url or "(not set — pipeline calls will fail)",
    _fallback_url or "(none)",
)

# Australian crisis resources — injected when Router routes to CRISIS mode.
# These are the same resources that NikkoPipeline.BASELINE_CRISIS_RESOURCES
# produces; duplicated here for the SSE response builder so we don't need to
# import the full list from orchestration.pipeline.
_CRISIS_TEXT = (
    "I'm really glad you reached out, and I want to make sure you're safe right now. "
    "Please contact one of these services immediately:\n\n"
    "- **Lifeline:** 13 11 14 (24/7)\n"
    "- **Beyond Blue:** 1300 22 4636\n"
    "- **13YARN** (Aboriginal & Torres Strait Islander): 13 92 76\n"
    "- **Emergency:** 000\n\n"
    "I'm here with you. Would you like to talk about what's going on?"
)

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Nikko Backend API",
    version="0.2.0",
    docs_url="/docs" if os.getenv("NIKKO_ENV") == "development" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://equinox013.github.io",
        "http://localhost:8000",
        "http://localhost:3000",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Accept"],
)

# ── Request / response models ─────────────────────────────────────────────────

class MoodSnapshot(BaseModel):
    selfReport:      int | None = Field(None, ge=1, le=5)
    dominantEmotion: str | None = None

class MessageRequest(BaseModel):
    text:           str           = Field(..., min_length=1, max_length=4000)
    contextId:      str | None    = None
    userId:         str | None    = None
    moodSnapshot:   MoodSnapshot | None = None
    # [REQ-850-070] Decrypted USM memory file content forwarded by the frontend.
    # Decryption happens client-side only — the server receives plaintext Markdown
    # and must never persist it (SPEC-800 zero-retention).  None when no memory
    # file is loaded.  Capped at 8000 chars to prevent context-window overflow
    # (Qwen3-4B 32k context; 8000 chars ≈ 2000 tokens, leaving headroom for
    # evidence, strategy, and conversation history).
    memoryContext:  str | None    = Field(
        default=None,
        max_length=8000,
        description="Decrypted USM memory content (plaintext Markdown). Never persisted.",
    )
    # Session-scoped conversation history — prior turns from the current browser
    # session.  The frontend holds this in React state only (evaporates on refresh).
    # Capped at 20 turns server-side; older turns are silently dropped beyond that.
    # Format: [{role: "user"|"assistant", text: str}].  Never persisted (SPEC-800).
    conversationHistory: list | None = Field(
        default=None,
        description="Prior session turns [{role, text}]. Session-scoped, not persisted.",
    )

class SourceItem(BaseModel):
    """
    Serializable representation of one retrieved EvidenceItem for the frontend
    sources panel. Carries only what the frontend needs to render an APA7 card.

    APA7 journal format (PubMed):
      Last, F. M., & Last, F. M. (Year). Title. URL
    APA7 web / org report format:
      Organisation. (Year). Title. Retrieved from URL
    """
    title:         str
    url:           str
    source_name:   str                  # org / journal name (fallback author)
    year:          str | None = None    # YYYY extracted from publication_date
    evidence_tier: str = "grey_literature"   # "peer_reviewed" | "grey_literature"
    # APA7-formatted author list from PubMed AuthorList. Empty for grey-lit
    # sources that do not carry structured authorship metadata.
    # Format: ["Last, F. M.", "Last, B. C."] — consumed by panels.jsx formatAPA7().
    authors:       list[str] = Field(default_factory=list)

class SSEChunk(BaseModel):
    text:        str              = ""
    emotion:     str              = "calm"
    sourcesUsed: list[str]        = Field(default_factory=list)
    sources:     list[SourceItem] = Field(default_factory=list)  # dynamic sources panel
    safetyFlags: list[str]        = Field(default_factory=list)
    trace:       dict | None      = None   # pipeline trace for debug panel

# ── Emotion mapping ───────────────────────────────────────────────────────────

def _mode_to_emotion(mode: OperationalMode | None, is_crisis: bool = False) -> str:
    """
    Map pipeline operational mode to frontend avatar state.

    [CONCEPT] The avatar state machine (GLOSSARY.md) has six states:
    calm / listen / think / speak / care / search. 'speak' is the default
    for normal responses; 'care' signals heightened warmth for crisis/high-distress.
    """
    if is_crisis:
        return "care"
    if mode == OperationalMode.CRISIS:
        return "care"
    if mode == OperationalMode.GUIDANCE:
        return "speak"
    return "speak"  # Comfort Mode default

# ── Pipeline to SSE bridge ────────────────────────────────────────────────────

def _result_to_trace(result: PipelineResult) -> dict:
    """
    Build the debug panel trace dict from a PipelineResult.
    Mirrors the trace structure used in the old _call_pipeline() path so the
    frontend agent-debug panel displays correctly without UI changes.
    """
    trace_obj = result.trace
    mode_val  = result.mode.value if result.mode else "unknown"

    adp_b_flags = []
    adp_b_verdict = "CLEAR"
    if result.mode == OperationalMode.CRISIS:
        adp_b_verdict = "CRISIS"

    return {
        "mode":             mode_val,
        "out_of_scope":     result.out_of_scope,
        "safe_fallback":    result.safe_fallback_used,
        "verdict":          result.evaluation.verdict.value if result.evaluation else "UNKNOWN",
        "regen":            (trace_obj.regen_count > 0) if trace_obj else False,
        "elapsed":          trace_obj.latency_ms / 1000 if trace_obj and trace_obj.latency_ms else 0,
        "execution_path":   trace_obj.execution_path if trace_obj else [],
        "evidence_sources": trace_obj.evidence_used if trace_obj else [],
        "adp_b": {
            "label":   "Safety / crisis check",
            "verdict": adp_b_verdict,
            "flags":   adp_b_flags,
        },
        "adp_a": {
            "label": "Empathy response draft (Qwen3-4B)",
            "chars": len(result.response_text),
        },
        "adp_c": {
            "label":   "Quality gate (ADP-C evaluator)",
            "verdict": result.evaluation.verdict.value if result.evaluation else "UNKNOWN",
            "regen":   (trace_obj.regen_count > 0) if trace_obj else False,
        },
    }

def _citations_to_sources(result: PipelineResult) -> list[SourceItem]:
    """
    Convert PipelineResult.citations (list[EvidenceItem]) into SourceItem dicts
    for SSEChunk.sources. Extracts year from publication_date; falls back to
    "n.d." (no date) per APA7 convention when the date is unavailable.

    Deduplicates by URL so the same page from two adapters isn't shown twice.
    Caps at 8 sources — the panel is readable up to ~6-8 entries.
    """
    seen_urls: set[str] = set()
    items: list[SourceItem] = []

    for ev in (result.citations or []):
        url = ev.url or ""
        if url in seen_urls:
            continue
        seen_urls.add(url)

        # Extract 4-digit year from publication_date if available.
        year: str | None = None
        if ev.publication_date:
            try:
                year = str(ev.publication_date.year)
            except AttributeError:
                # publication_date may be a string in some adapter implementations.
                import re as _re
                m = _re.search(r"\b(19|20)\d{2}\b", str(ev.publication_date))
                year = m.group(0) if m else None

        items.append(SourceItem(
            title=ev.title or "(Untitled)",
            url=url,
            source_name=ev.source_name or "Unknown source",
            year=year,
            evidence_tier=ev.evidence_tier.value if hasattr(ev.evidence_tier, "value") else str(ev.evidence_tier),
            authors=getattr(ev, "authors", []) or [],
        ))

        if len(items) >= 8:
            break

    return items


# ── Core pipeline async generator ─────────────────────────────────────────────

async def _pipeline(request: MessageRequest) -> AsyncGenerator[SSEChunk, None]:
    """
    Runs the full NikkoPipeline for one user turn and yields SSEChunks.

    [CONCEPT] asyncio.to_thread() runs NikkoPipeline.run() in a background
    thread from FastAPI's thread pool. This is necessary because:
    1. NikkoPipeline is synchronous (all agent calls are sync).
    2. HFSpaceFullGenerator.generate() makes a blocking HTTP call (30-370s
       depending on ZeroGPU cold-start state).
    Wrapping in to_thread() keeps the FastAPI event loop free to serve
    /health probes and other concurrent requests during the long GPU wait.

    Keep-alive strategy: Render/Fly.io nginx proxies close idle SSE
    connections after ~30-60s of inactivity. The pipeline can run for up to
    370s (360s HF Space timeout + local agent overhead). We poll the task
    every _SSE_KEEPALIVE_S seconds and emit an empty 'think' chunk so the
    proxy sees traffic and keeps the stream open. Empty chunks set the
    frontend avatar state but produce no visible text (chat.jsx line 470).

    Graceful degradation: any unhandled exception from the pipeline produces
    a warm holding response so the frontend always receives text.
    """
    # Signal 'thinking' to the frontend immediately.
    yield SSEChunk(emotion="think", text="")

    # How often to send keep-alive pings (seconds).
    # Must be well under the proxy's idle-connection timeout (~30s on Render).
    _SSE_KEEPALIVE_S = 20.0

    try:
        # [CONCEPT] asyncio.create_task wraps to_thread so we can poll it
        # with asyncio.wait_for + asyncio.shield. shield() protects the
        # background thread from cancellation if wait_for times out — the
        # thread keeps running while we yield the keep-alive ping.
        task = asyncio.create_task(
            asyncio.to_thread(
                _pipeline_run_sync,
                request.text.strip(),
                request.memoryContext,
                request.conversationHistory,
            )
        )

        # Keep-alive polling loop.
        # Each iteration either: (a) gets the result and breaks, or
        # (b) times out after 20s, emits a ping, and loops again.
        while True:
            try:
                result: PipelineResult = await asyncio.wait_for(
                    asyncio.shield(task), timeout=_SSE_KEEPALIVE_S
                )
                break   # pipeline completed — proceed to response building
            except asyncio.TimeoutError:
                # Pipeline still running — send keep-alive to prevent proxy timeout.
                log.debug("Pipeline still running — emitting SSE keep-alive ping.")
                yield SSEChunk(emotion="think", text="")

    except Exception as exc:
        log.warning("Pipeline raised unhandled exception: %s", exc, exc_info=True)
        yield SSEChunk(
            text=(
                "I'm here with you. It sounds like there's a lot on your mind — "
                "would you like to share a bit more about what's been going on?"
            ),
            emotion="speak",
        )
        return

    # ── Out-of-scope early exit ────────────────────────────────────────────────
    if result.out_of_scope:
        yield SSEChunk(
            text=result.response_text,
            emotion="calm",
            trace=_result_to_trace(result),
        )
        return

    # ── Crisis Mode ────────────────────────────────────────────────────────────
    # Pipeline routed to CRISIS — use the canonical crisis text rather than
    # whatever the pipeline's response_text contains, to ensure the hotlines
    # are always formatted correctly per SPEC-300.
    if result.mode == OperationalMode.CRISIS:
        yield SSEChunk(
            text=_CRISIS_TEXT,
            emotion="care",
            safetyFlags=["crisis_detected"],
            trace=_result_to_trace(result),
        )
        return

    # ── Normal response ────────────────────────────────────────────────────────
    text = result.response_text or (
        "I want to make sure I'm being as helpful as possible. "
        "Could you tell me a little more about what's on your mind?"
    )

    # Build evidence source list for frontend citations panel.
    sources_used: list[str] = []
    if result.trace and result.trace.evidence_used:
        sources_used = result.trace.evidence_used

    yield SSEChunk(
        text=text,
        emotion=_mode_to_emotion(result.mode),
        sourcesUsed=sources_used,
        sources=_citations_to_sources(result),
        trace=_result_to_trace(result),
    )


def _pipeline_run_sync(
    user_text: str,
    memory_context: str | None = None,
    conversation_history: list | None = None,
) -> PipelineResult:
    """
    Thin synchronous wrapper around NikkoPipeline.run() for use with
    asyncio.to_thread(). Separated so the async caller stays clean.

    memory_context       : Decrypted USM memory file content from the frontend.
                           Forwarded to NikkoPipeline so it can set usm_active=True
                           and inject the content into the ADP-A system prompt
                           (REQ-850-070).
    conversation_history : Prior session turns [{role, text}].  Capped at 20 turns
                           before forwarding — silently drops oldest beyond that.
                           Session-scoped only; never persisted (SPEC-800).
    """
    # Cap history depth server-side as a safety net (frontend already caps at 10).
    history = conversation_history[-20:] if conversation_history else None
    return _nikko.run(
        user_input=user_text,
        memory_context=memory_context,
        conversation_history=history,
    )


# ── SSE helpers ───────────────────────────────────────────────────────────────

def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"

async def _sse_stream(msg_id: str, gen: AsyncGenerator) -> AsyncGenerator[str, None]:
    yield _sse("message_start", {"id": msg_id, "emotion": "listen"})
    async for chunk in gen:
        yield _sse("chunk", chunk.model_dump())
    yield _sse("message_end", {"id": msg_id})

# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    """
    Root health card — returns a plain status object so navigating to the
    Render URL doesn't produce a FastAPI 404. Not a functional endpoint.
    """
    return {
        "service":   "Nikko Backend API",
        "version":   "0.2.0",
        "status":    "ok",
        "inference": "modal" if MODAL_URL else "hf_space",
    }


@app.get("/health")
async def health():
    """
    REQ-600-HL1: Platform probe + loading screen poll (REQ-FIS-LS2).

    Probes the active primary inference endpoint (Modal if configured, HF Space
    otherwise). The frontend polls this until space_ok=true before allowing the
    user to send messages — field name kept as space_ok for frontend compatibility.
    """
    space_ok = False
    # Probe the dedicated Modal health URL if provided; otherwise fall back to
    # the HF Space /health endpoint.  We do NOT append /health to MODAL_URL
    # because the Modal pipeline endpoint is POST-only — GET /health on it
    # returns 404.  The Modal health function lives at a separate URL.
    probe_url = MODAL_HEALTH_URL or (HF_SPACE_URL + "/health" if HF_SPACE_URL else "")
    if probe_url:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(probe_url)
                space_ok = r.status_code == 200
        except Exception:
            pass
    return {
        "status":    "ok",
        "version":   "0.2.0",
        "space_ok":  space_ok,
        "inference": "modal" if MODAL_URL else "hf_space",
        "ts":        int(time.time()),
    }


@app.post("/api/message")
async def message(body: MessageRequest):
    """REQ-FIS-001: Primary chat endpoint — streams SSE to the frontend."""
    if not body.text.strip():
        raise HTTPException(status_code=422, detail="text must not be empty")

    msg_id = f"msg-{int(time.time()*1000)}-{uuid.uuid4().hex[:6]}"
    return StreamingResponse(
        _sse_stream(msg_id, _pipeline(body)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/message/mock")
async def message_mock(body: MessageRequest):
    """REQ-FIS-TS1: Hardcoded fixture — frontend testing without live agents."""
    msg_id = f"mock-{int(time.time()*1000)}"

    async def _mock():
        await asyncio.sleep(0.3)
        yield SSEChunk(text="This is a mock response. ", emotion="listen")
        await asyncio.sleep(0.2)
        yield SSEChunk(text="Pipeline is not active.", emotion="speak")

    return StreamingResponse(
        _sse_stream(msg_id, _mock()),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

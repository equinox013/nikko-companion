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
import re
import time
import uuid
from typing import AsyncGenerator

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.draft_generator import HFSpaceFullGenerator
from backend.pii_sanitiser import attach_log_filter, redact_entities, redact_history
from schemas.acp_schemas import OperationalMode
from orchestration.crisis_responses import (
    select_crisis_response,
    count_crisis_turns_from_history,
)
from orchestration.pipeline import NikkoPipeline, PipelineResult

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Attach PII-scrubbing log filter immediately after logger is configured.
# This ensures exception tracebacks never emit raw user content to Render logs.
# Must run before any log.warning/error calls that carry exc_info=True.
# memoryContext is NOT passed through this filter — it never enters log records.
attach_log_filter(log)

# ── Build / version info ──────────────────────────────────────────────────────
# Render injects RENDER_GIT_COMMIT (full SHA) and RENDER_GIT_BRANCH at build
# time. Logging them here makes them the first visible line in the Render log
# stream after a cold start / dyno restart — trivial to cross-reference with
# the GitHub commit when debugging a production issue.
# RENDER_GIT_COMMIT will be empty string in local dev; that's fine.
_GIT_COMMIT = os.getenv("RENDER_GIT_COMMIT", "local")[:12]   # short SHA is enough
_GIT_BRANCH = os.getenv("RENDER_GIT_BRANCH", "unknown")
log.info("Render backend starting | commit=%s branch=%s", _GIT_COMMIT, _GIT_BRANCH)

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

# Crisis text is now served from the crisis response pool (crisis_responses.py).
# REQ-300-113 through REQ-300-118: pool of 5 templates, turn-aware selection,
# continuity acknowledgment from turn 3+, anchor mode after pool exhaustion.
# _CRISIS_TEXT is removed — use select_crisis_response() instead.

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
    # [REQ-FIS-RB4] Current pipeline stage label — emitted on progress chunks
    # and on the final response chunk. Consumed by AgentRibbon for live status
    # display during processing and mode summary on completion.
    # Labels are the canonical set from SPEC-700 §16.
    # Empty string on keep-alive pings that do not carry a stage update.
    stage:       str              = ""
    sourcesUsed: list[str]        = Field(default_factory=list)
    sources:     list[SourceItem] = Field(default_factory=list)  # dynamic sources panel
    safetyFlags: list[str]        = Field(default_factory=list)
    trace:       dict | None      = None   # pipeline trace for debug panel
    # USM write-back (SPEC-850 §9, step 2 — Proposal).
    # Non-None only on the final normal chunk when a memory candidate is detected.
    # Never set on crisis or out-of-scope chunks (REQ-850-084).
    memory_proposal:     dict | None  = None
    # USM technique check-in (SPEC-850 §9 — post-recommendation prompt).
    # Non-None when the assistant's response recommends a named technique,
    # prompting a frontend popup asking if the user wants to track it.
    # Never set on crisis or out-of-scope chunks (REQ-850-084).
    technique_recommended: dict | None = None

# ── Emotion mapping ───────────────────────────────────────────────────────────

def _mode_to_emotion(
    mode: OperationalMode | None,
    is_crisis: bool = False,
    signal_confidence: float | None = None,
) -> str:
    """
    Map pipeline operational mode (and signal confidence) to frontend avatar state.

    [CONCEPT] The avatar state machine (GLOSSARY.md) has seven states:
    calm / listen / think / speak / care / search / uncertain.
    'speak' is the default for normal responses.
    'care' signals heightened warmth for crisis/high-distress.
    'uncertain' fires when signal_confidence < 0.40 — indicates Nikko detected
    a signal but is not confident about its reading (REQ-000-231).
    """
    if is_crisis:
        return "care"
    if mode == OperationalMode.CRISIS:
        return "care"
    # [REQ-000-231] Emit 'uncertain' when the SignalAgent confidence is below 0.40.
    # This triggers the dimmed-ray fade-pulse avatar in the frontend, signalling
    # epistemic humility without affecting routing or response content.
    if signal_confidence is not None and signal_confidence < 0.40:
        return "uncertain"
    if mode == OperationalMode.GUIDANCE:
        return "speak"
    return "speak"  # Comfort Mode default

# ── USM memory candidate detection (SPEC-850 §9, step 2) ─────────────────────

# Affirmation patterns that signal a user has found something helpful.
# Covers both past-tense confirmations ("that helped") and present-tense
# statements ("breathing really helps me", "I find this helpful").
# Still conservative — false negatives preferred over spurious proposals.
_AFFIRMATION_RE = re.compile(
    r"\b("
    # Past-tense: user confirming something worked
    r"that (really |actually |really actually )?(helped|worked|made (?:a |the )difference)"
    r"|it (really |actually )?(helped|worked)"
    r"|that (technique|exercise|method|approach|strategy|tip) ?(really |actually )?worked"
    r"|felt (better|calmer|less anxious) ?(after|when|from)"
    r"|i('ll| will| should| want to) try(ing)? (that|this)"
    r"|that('s| is) (helpful|useful|good to know|exactly what i needed)"
    r"|going to (try|use|do) that"
    # Present-tense: user stating something helps / is helpful
    r"|(?:really |definitely |actually |so )?help(?:s|ed)? (?:a lot|so much|me|with|calm)"
    r"|find(?:s|ing)? (?:it |this |that )?(?:really |so |very )?helpful"
    r"|feel(?:s)? (?:like |that )?(?:\w+ ){0,5}help(?:s|ed)?"
    r"|(?:really |definitely )?work(?:s|ed)? (?:well|for me|really well)"
    r")",
    re.IGNORECASE,
)

# Intervention keywords — used to name what the user found helpful in the proposal.
_TECHNIQUE_RE = re.compile(
    r"\b("
    r"breath(ing|e)( exercise| technique)?s?"
    r"|grounding( exercise| technique| method)?s?"
    r"|box breath(ing)?"
    r"|4-7-8"
    r"|meditation"
    r"|mindfulness"
    r"|body scan"
    r"|progressive (muscle )?relaxation"
    r"|journaling"
    r"|self.compassion"
    r"|cognitive (reframe|restructur)"
    r"|thought record"
    r"|behavioural activation"
    r"|distraction technique"
    r")",
    re.IGNORECASE,
)


def _detect_memory_candidate(
    user_text: str,
    mode: "OperationalMode | None",
) -> "dict | None":
    """
    Lightweight pattern check for USM write-back proposals (SPEC-850 §9, step 2).

    Returns a proposal dict if the turn looks like the user affirming a helpful
    intervention; None otherwise. The frontend shows this as a proposal card
    with Accept/Decline — the user must confirm before anything is written
    (REQ-850-011).

    Only called for non-crisis, non-out-of-scope turns (REQ-850-084).

    Returns:
        None — no candidate detected
        {
            "section": "Helpful Interventions",
            "entry":   "Breathing exercise — user found this helpful.",
            "raw":     <matched technique name or None>
        }
    """
    if not _AFFIRMATION_RE.search(user_text):
        return None

    # Try to name the specific technique from context.
    tech_match = _TECHNIQUE_RE.search(user_text)
    if tech_match:
        technique = tech_match.group(0).strip().capitalize()
        entry = f"{technique} — user found this helpful."
    else:
        # Generic fallback — still worth proposing; user can edit before accepting.
        entry = "User found a technique or approach helpful (details in session)."

    return {
        "section": "Helpful Interventions",
        "entry":   entry,
        "raw":     tech_match.group(0) if tech_match else None,
    }


# ── USM technique recommendation detection (SPEC-850 §9 — response-side) ────

# Matches recommendation language in the assistant's output ("try X", "take a breath").
# Anchored to the same technique vocabulary as _TECHNIQUE_RE but scans Nikko's text.
# "take" is included because comfort-mode responses tend to say "take a deep breath"
# rather than "try breathing exercises"; "let's" covers "let's try/do X" phrasing.
_RESPONSE_RECOMMEND_RE = re.compile(
    r"\b(?:try|practice|use|consider|tak(?:e|ing)|let's|give\s+(?:it|this|that)\s+a\s+try|experiment\s+with)\b"
    r"[^.!?\n]{0,120}"
    r"\b(box\s+breath(?:ing)?|4[-–]7[-–]8(?:\s+breath(?:ing)?)?|breath(?:ing)?(?:\s+exercise)?s?|"
    r"deep\s+breath(?:ing)?|grounding(?:\s+exercise|\s+technique)?s?|"
    r"5[-–]4[-–]3[-–]2[-–]1|body\s+scan|progressive\s+muscle\s+relaxation|PMR|"
    r"mindfulness(?:\s+meditation)?|meditati(?:on|ng)|journal(?:l?ing)?|thought\s+record|"
    r"cognitive\s+refram(?:ing|e)|behavioural?\s+activation|worry\s+time|"
    r"self[-\s]compassion(?:\s+exercise)?)\b",
    re.IGNORECASE,
)

# Ordered lookup: first match wins. Each entry is (pattern, display_name, memory_entry).
# Entry is first-person per REQ-850-021 — framed as "I tried X" since the user
# is clicking Accept to confirm they want to remember the technique.
_TECHNIQUE_CANONICAL = [
    (re.compile(r"box\s+breath",         re.I), "box breathing",           "I tried box breathing to help calm anxious feelings."),
    (re.compile(r"4[-–]7[-–]8",          re.I), "4-7-8 breathing",         "I tried 4-7-8 breathing as a relaxation technique."),
    (re.compile(r"grounding",            re.I), "grounding",               "I tried a grounding exercise to stay present."),
    (re.compile(r"5[-–]4[-–]3[-–]2[-–]1", re.I), "5-4-3-2-1 grounding",  "I tried the 5-4-3-2-1 grounding technique."),
    (re.compile(r"body\s+scan",          re.I), "body scan",               "I tried a body scan meditation to release tension."),
    (re.compile(r"progressive\s+muscle|PMR", re.I), "PMR",                 "I tried progressive muscle relaxation."),
    (re.compile(r"mindfulness",          re.I), "mindfulness",             "I tried mindfulness practice to manage stress."),
    (re.compile(r"meditati",             re.I), "meditation",              "I tried meditation as a calming technique."),
    (re.compile(r"journal",              re.I), "journalling",             "I tried journalling to process difficult feelings."),
    (re.compile(r"thought\s+record",     re.I), "thought records",         "I tried thought records to challenge unhelpful thinking."),
    (re.compile(r"cognitive\s+refram",   re.I), "cognitive reframing",     "I tried cognitive reframing to shift my perspective."),
    (re.compile(r"behavioural?\s+activ", re.I), "behavioural activation",  "I tried behavioural activation to improve my mood."),
    (re.compile(r"worry\s+time",         re.I), "worry time",              "I tried the worry time technique to contain anxious thoughts."),
    (re.compile(r"self[-\s]compassion",  re.I), "self-compassion",         "I tried a self-compassion exercise."),
    (re.compile(r"breath",              re.I), "breathing exercises",      "I tried breathing exercises to manage stress."),
]


def _detect_technique_in_response(
    response_text: str,
    mode: "OperationalMode | None",
) -> "dict | None":
    """
    Scan the ADP-A response for a technique recommendation (SPEC-850 §9).

    Returns a technique_recommended dict when Nikko explicitly suggests the user
    try a named technique, triggering a frontend popup banner. The popup asks
    whether the user wants to track it in their memory file — replacing the need
    to type specific affirmation phrases after the fact.

    Only called for non-crisis, non-out-of-scope turns (REQ-850-084).

    Returns:
        None — no recommendation detected
        {
            "technique": <display name, e.g. "box breathing">,
            "section":   "Helpful Interventions",  # matches ## Helpful Interventions in template
            "entry":     <first-person memory entry, REQ-850-021>,
            "raw":       <canonical key for deduplication>,
        }
    """
    if not _RESPONSE_RECOMMEND_RE.search(response_text):
        return None

    for pattern, raw_key, entry in _TECHNIQUE_CANONICAL:
        if pattern.search(response_text):
            return {
                "technique": raw_key,
                "section":   "Helpful Interventions",
                "entry":     entry,
                "raw":       raw_key,
            }

    return None


# ── Pipeline to SSE bridge ────────────────────────────────────────────────────

def _result_to_trace(result: PipelineResult) -> dict:
    """
    Build the debug panel trace dict from a PipelineResult.

    [REQ-FIS-DB1 through DB5] Expanded trace schema includes:
      pre_analysis  — Step 1.5 Qwen3-4B structural pre-analysis output
      signal        — Full SPEC-100 §9 signal output from the Signal Agent
      router        — Router decision (mode, confidence, rationale)
      evidence      — Retrieved evidence source names
      mode          — Operational mode string
      adp_b/a/c     — Per-adapter results (unchanged for frontend compatibility)
    """
    trace_obj = result.trace
    mode_val  = result.mode.value if result.mode else "unknown"

    adp_b_flags   = []
    adp_b_verdict = "CLEAR"
    if result.mode == OperationalMode.CRISIS:
        adp_b_verdict = "CRISIS"

    # Full signal output — pull all available fields from trace.signal_output.
    # The pipeline sets at minimum {distress_level, confidence}; extended fields
    # (emotional_states, cognitive_patterns, behavioral_indicators, etc.) are
    # added by the real SignalAgent when NIKKO_LOCAL_LLM=true (REQ-FIS-DB3).
    _signal_out = trace_obj.signal_output if trace_obj else {}

    # Router decision — prefer full router_output dict (mode + confidence +
    # crisis_override + rationale). Falls back to the legacy mode-string-only
    # path if router_output is not yet populated (older in-flight requests).
    # REQ-FIS-DB4.
    if trace_obj and getattr(trace_obj, "router_output", None):
        _router_out = trace_obj.router_output
    else:
        _router_out = {
            "mode":           trace_obj.router_decision if trace_obj else mode_val,
            "confidence":     0.0,
            "crisis_override": False,
            "rationale":      "",
        }

    # Pre-analysis output — populated by HFSpaceFullGenerator when the Qwen3-4B
    # Step 1.5 structural pre-analysis pass has run (REQ-700-SA1 through SA7).
    # Falls back to None if pre-analysis was not run (e.g., scope block path).
    _pre_analysis = getattr(trace_obj, "pre_analysis_output", None) if trace_obj else None

    return {
        # ── Top-level pipeline metadata ─────────────────────────────────────
        "mode":             mode_val,
        "out_of_scope":     result.out_of_scope,
        "safe_fallback":    result.safe_fallback_used,
        "verdict":          result.evaluation.verdict.value if result.evaluation else "UNKNOWN",
        "regen":            (trace_obj.regen_count > 0) if trace_obj else False,
        "elapsed":          trace_obj.latency_ms / 1000 if trace_obj and trace_obj.latency_ms else 0,
        "execution_path":   trace_obj.execution_path if trace_obj else [],
        # ── Step 0.5: Structural pre-analysis (REQ-FIS-DB1) ─────────────────
        # Populated when Qwen3-4B thinking-mode pre-pass has run.
        # None when pre-analysis was skipped (scope block, moderation block).
        "pre_analysis": _pre_analysis,
        # ── Step 1: Signal Agent output (REQ-FIS-DB2 / REQ-FIS-DB3) ─────────
        # Full SPEC-100 §9 signal fields; at minimum {distress_level, confidence}.
        "signal": {
            "distress_level":       _signal_out.get("distress_level", "UNKNOWN"),
            "confidence":           _signal_out.get("confidence", 0.0),
            "emotional_states":     _signal_out.get("emotional_states", []),
            "cognitive_patterns":   _signal_out.get("cognitive_patterns", []),
            "behavioral_indicators":_signal_out.get("behavioral_indicators", []),
            "risk_indicators":      _signal_out.get("risk_indicators", []),
            "support_needs":        _signal_out.get("support_needs", []),
            "uncertainty_notes":    _signal_out.get("uncertainty_notes", ""),
        },
        # ── Step 2: Router decision (REQ-FIS-DB4) ────────────────────────────
        "router": _router_out,
        # ── Evidence (REQ-FIS-DB5) ───────────────────────────────────────────
        "evidence": {
            "sources": trace_obj.evidence_used if trace_obj else [],
            "adapters": trace_obj.adapter_configuration if trace_obj else [],
        },
        # ── Adapter cards (unchanged — frontend backward-compatibility) ───────
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
    # [SPEC-700 §16 / REQ-FIS-RB4] Canonical pipeline stage labels.
    # Emitted on keep-alive chunks so AgentRibbon shows live progress.
    # Time thresholds are approximate — the real pipeline is synchronous so
    # exact step boundaries are not observable from outside the background thread.
    _STAGE_TIMELINE: list[tuple[float, str]] = [
        (0.0,  "understanding your message"),
        (8.0,  "reading between the lines"),
        (20.0, "searching for support"),
        (40.0, "shaping a response"),
        (70.0, "final checks"),
    ]

    def _stage_at(elapsed_s: float) -> str:
        """Return the appropriate stage label for elapsed time."""
        label = _STAGE_TIMELINE[0][1]
        for threshold, stage_label in _STAGE_TIMELINE:
            if elapsed_s >= threshold:
                label = stage_label
        return label

    _t_pipeline_start = time.time()

    # Signal 'thinking' to the frontend immediately.
    yield SSEChunk(emotion="think", text="", stage="understanding your message")

    # How often to send keep-alive pings (seconds).
    # Must be well under the proxy's idle-connection timeout (~30s on Render).
    _SSE_KEEPALIVE_S = 20.0

    try:
        # [CONCEPT] asyncio.create_task wraps to_thread so we can poll it
        # with asyncio.wait_for + asyncio.shield. shield() protects the
        # background thread from cancellation if wait_for times out — the
        # thread keeps running while we yield the keep-alive ping.
        # NER redaction — SPEC-800 compliance (REQ-800-008, REQ-800-011).
        # Named entities (PERSON, ORG, GPE, LOC) in the live message and
        # conversation history user turns are replaced with typed placeholders
        # before any LLM or log sees the raw text.
        # memoryContext is EXEMPT — those names were explicitly stored by the
        # user and are consented data the pipeline may reference.
        _sanitised_text    = redact_entities(request.text.strip())
        _sanitised_history = redact_history(request.conversationHistory or [])

        task = asyncio.create_task(
            asyncio.to_thread(
                _pipeline_run_sync,
                _sanitised_text,
                request.memoryContext,
                _sanitised_history,
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
                # Include current stage label so AgentRibbon updates in real time.
                _elapsed = time.time() - _t_pipeline_start
                _current_stage = _stage_at(_elapsed)
                log.debug(
                    "Pipeline still running (%.0fs) — emitting keep-alive [%s].",
                    _elapsed, _current_stage,
                )
                yield SSEChunk(emotion="think", text="", stage=_current_stage)

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
            stage="",
            trace=_result_to_trace(result),
        )
        return

    # ── Crisis Mode ────────────────────────────────────────────────────────────
    # Pipeline routed to CRISIS — serve from the static crisis response pool
    # (REQ-300-113 through REQ-300-118). Never LLM-generated.
    # Turn-aware selection: count consecutive prior crisis turns from history
    # so the pool doesn't repeat on the same template twice in a row.
    if result.mode == OperationalMode.CRISIS:
        _crisis_turn_idx = count_crisis_turns_from_history(
            request.conversationHistory
        )
        _crisis_text = select_crisis_response(
            crisis_turn_index=_crisis_turn_idx,
            # last_pool_index unknown across stateless requests — default to -1
            # so the selector uses plain rotation without collision avoidance.
            # A stateful per-session tracker is deferred to Phase 7 sign-off.
            last_pool_index=-1,
        )
        yield SSEChunk(
            text=_crisis_text,
            emotion="care",
            stage="crisis mode",
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

    # Detect whether the user's turn contains an intervention affirmation
    # suitable for a USM write-back proposal (SPEC-850 §9, step 2).
    # Only runs on non-crisis turns — _detect_memory_candidate is never
    # called for crisis or out-of-scope paths (REQ-850-084).
    proposal = _detect_memory_candidate(request.text.strip(), result.mode)

    # Detect whether the assistant's response recommends a named technique,
    # triggering a frontend check-in popup (SPEC-850 §9 — response-side).
    # This is the primary trigger path — fires when Nikko suggests something,
    # not waiting for the user to type affirmation phrases afterwards.
    # Suppressed when memory_proposal already fired (user already affirmed).
    technique_rec = (
        _detect_technique_in_response(text, result.mode)
        if not proposal
        else None
    )

    # Extract signal confidence from trace for uncertain avatar state (REQ-000-231).
    _sig_conf: float | None = None
    if result.trace and result.trace.signal_output:
        _sig_conf = result.trace.signal_output.get("confidence")

    # Derive completion stage label from the pipeline mode (REQ-FIS-RB4).
    # Shown in AgentRibbon as the mode summary on completion.
    _completion_stage = (
        "guidance mode" if result.mode == OperationalMode.GUIDANCE else "comfort mode"
    )

    yield SSEChunk(
        text=text,
        emotion=_mode_to_emotion(result.mode, signal_confidence=_sig_conf),
        stage=_completion_stage,
        sourcesUsed=sources_used,
        sources=_citations_to_sources(result),
        trace=_result_to_trace(result),
        memory_proposal=proposal,
        technique_recommended=technique_rec,
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
    # Cap history depth server-side as a safety net.
    # Frontend now sends up to 20 turns; server cap matches to avoid silent drops.
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

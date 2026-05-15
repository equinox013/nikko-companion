"""
orchestration/pipeline.py
==========================
NikkoPipeline — the SPEC-700 end-to-end execution wiring.

Spec source : SPEC-700 (Full System Integration Blueprint)
Requirements: REQ-700-001 through REQ-700-161

Phase        : 3 — Agent Definitions (Implementation)

Role in the system
-------------------
This module is the single entry point for all user interactions. It owns:
  - Agent instantiation and lifecycle
  - The SPEC-700 execution order (STEP 0 → STEP 15)
  - Mode branching (Comfort / Guidance / Crisis)
  - Regeneration loop management (REQ-200-170)
  - Failure state handling (REQ-700-120 through REQ-700-123)
  - Ephemeral trace capture (REQ-700-110, REQ-700-LOG1)

Design: dependency-injected, protocol-based
--------------------------------------------
Three components are injected at construction time rather than hard-coded:
  1. draft_generator : DraftGeneratorProtocol — the Interaction Model (LLM).
     Phase 3 uses StubDraftGenerator; Phase 4 swaps in the fine-tuned model
     without changing this file.
  2. scope_classifier : ScopeClassifier instance (or stub).
  3. signal_agent    : SignalAgent instance (or stub).

Agents with FUSE-mount truncation issues (ScopeClassifier, SignalAgent,
SupportStrategyAgent) are wrapped in try/except at import time and replaced
by in-file stubs when the full implementation is unavailable. This is a
Phase 3 workaround; the real implementations will be usable once the FUSE
sync issue is resolved and the files can be imported cleanly.

Hard constraints (all from spec)
---------------------------------
  REQ-700-130 — No parallel chains: one execution path per request.
  REQ-700-131 — No bypass: Router and Evaluator are mandatory.
  REQ-700-132 — No cross-mode mixing within a turn.
  REQ-700-133 — LLM receives only synthesized/filtered inputs.
  REQ-200-170 — Regeneration loop capped at MAX_REGEN_ATTEMPTS = 2.
  REQ-700-LOG1 — All trace data is session-scoped and ephemeral.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Protocol, runtime_checkable

# [CONCEPT] Protocol — Python's structural subtyping interface. Unlike
# abstract base classes, a Protocol does not require explicit inheritance.
# Any class that implements the required methods satisfies the Protocol,
# making dependency injection easy without coupling the pipeline to a
# specific LLM library. See PEP 544.
from typing import Protocol, runtime_checkable

from docs.schemas.acp_schemas import (
    CrisisResource,
    DistressLevel,
    EvaluationPayload,
    EvaluationVerdict,
    EvidencePayload,
    EvidenceTier,
    OperationalMode,
    ResponseContextPayload,
    ScopeClassifierDecision,
    ScopeDecision,
    SignalPayload,
    SourceTier,
    StrategyPayload,
    SynthesizedEvidence,
    VerificationResult,
)
from docs.schemas.retrieval_schemas import (
    PubMedQueryParams,
    RetrievalResult,
    StaticCacheQueryParams,
)
from retrieval import ADAPTER_PRIORITY_ORDER, PubMedAdapter, WebSearchAdapter
from agents.synthesizer_agent import EvidenceSynthesizerAgent
from agents.evaluator_agent import EvaluatorAgent
from agents.verification_supervisor import (
    VerificationSupervisorAgent,
    SAFE_FALLBACK_RESPONSE,
    MAX_REGEN_ATTEMPTS,
)
from agents.router import Router, RouterDecision

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ADP-B late-crisis sentinel
# ---------------------------------------------------------------------------

# [CONCEPT] ADPB_CRISIS_SENTINEL is a string token returned by
# HFSpaceFullGenerator.generate() when ADP-B fires crisis=True AFTER the local
# pipeline already routed to COMFORT mode (the stub SignalAgent doesn't detect
# crisis — it only does keyword-based guidance detection).
#
# Instead of returning "" (which cascades into SAFE_FALLBACK with no crisis
# resources shown), draft_generator.py returns this sentinel. NikkoPipeline.run()
# intercepts it immediately after _step10_draft() and re-routes to a full CRISIS
# PipelineResult, ensuring hotlines and the safety banner are always delivered.
#
# This constant must live here (not in backend/) to preserve the
# DraftGeneratorProtocol abstraction: draft_generator.py imports from
# orchestration.pipeline — the dependency direction never reverses.
ADPB_CRISIS_SENTINEL = "__NIKKO_ADPB_CRISIS_DETECTED__"

# Crisis text used for the ADP-B late-override path. Mirrors _CRISIS_TEXT in
# backend/main.py — keep in sync if the hotlines or framing ever change.
_ADPB_CRISIS_RESPONSE = (
    "I'm really glad you reached out, and I want to make sure you're safe right now. "
    "Please contact one of these services immediately:\n\n"
    "- **Lifeline:** 13 11 14 (24/7)\n"
    "- **Beyond Blue:** 1300 22 4636\n"
    "- **13YARN** (Aboriginal & Torres Strait Islander): 13 92 76\n"
    "- **Emergency:** 000\n\n"
    "I'm here with you. Would you like to talk about what's going on?"
)

# ---------------------------------------------------------------------------
# Inference environment flag
# ---------------------------------------------------------------------------

# [CONCEPT] NIKKO_LOCAL_LLM controls whether the pipeline attempts to load
# local LLM-backed agents (SignalAgent, SupportStrategyAgent, EvaluatorAgent).
# These agents require torch + transformers and a GPU with ~6 GB VRAM.
#
# On Render (production orchestration layer), set:
#   NIKKO_LOCAL_LLM=false
# All LLM work is delegated to HF Spaces (ADP-A/B/C). Local agents run as
# lightweight stubs — keyword-based signal detection, static strategy fallback,
# regex-only evaluation. No model download attempts, no OOM errors.
#
# On a local GPU machine or Colab, set NIKKO_LOCAL_LLM=true (or leave unset)
# to load the real agents.
import os as _os
_LOCAL_LLM: bool = _os.getenv("NIKKO_LOCAL_LLM", "true").lower() not in ("false", "0", "no")

if not _LOCAL_LLM:
    logger.info(
        "NIKKO_LOCAL_LLM=false — all LLM-backed agents will use stubs. "
        "Signal detection: keyword fallback. Strategy: static. "
        "Evaluation: regex red-lines only (no LLM judge). "
        "All LLM inference delegated to HF Spaces."
    )

# ---------------------------------------------------------------------------
# Agent stubs (used when FUSE-truncated agents cannot be imported cleanly,
# or when NIKKO_LOCAL_LLM=false disables local inference on Render)
# ---------------------------------------------------------------------------

# [CONCEPT] try/except at import time — we attempt to import the full agent
# implementation. If Python raises a SyntaxError (caused by the FUSE mount
# showing a truncated version of the file) we fall through to the stub.
# This lets the pipeline run end-to-end in Phase 3 without requiring all
# agents to be syntactically correct in the Linux sandbox.
# When NIKKO_LOCAL_LLM=false the real agents are never imported regardless.

if _LOCAL_LLM:
    try:
        from agents.scope_classifier import ScopeClassifier as _ScopeClassifier
        _HAVE_SCOPE_CLASSIFIER = True
    except (SyntaxError, ImportError):
        _HAVE_SCOPE_CLASSIFIER = False
        logger.warning("ScopeClassifier unavailable (FUSE truncation) — using stub.")

    try:
        from agents.signal_agent import SignalAgent as _SignalAgent
        _HAVE_SIGNAL_AGENT = True
    except (SyntaxError, ImportError):
        _HAVE_SIGNAL_AGENT = False
        logger.warning("SignalAgent unavailable (FUSE truncation) — using stub.")

    try:
        from agents.support_strategy_agent import SupportStrategyAgent as _SupportStrategyAgent
        _HAVE_STRATEGY_AGENT = True
    except (SyntaxError, ImportError):
        _HAVE_STRATEGY_AGENT = False
        logger.warning("SupportStrategyAgent unavailable (FUSE truncation) — using stub.")
else:
    _HAVE_SCOPE_CLASSIFIER = False
    _HAVE_SIGNAL_AGENT     = False
    _HAVE_STRATEGY_AGENT   = False


class _StubScopeClassifier:
    """
    Stub Scope Classifier — always returns IN_SCOPE at high confidence.
    Used when the real ScopeClassifier cannot be imported (FUSE truncation).
    Replace with the real ScopeClassifier for production.
    """
    def classify(self, text: str) -> ScopeClassifierDecision:
        return ScopeClassifierDecision(
            decision=ScopeDecision.IN_SCOPE,
            confidence=0.99,
            warm_redirect=None,
        )


class _StubSignalAgent:
    """
    Stub Signal Agent — returns LOW distress with keyword-based guidance detection.
    Used when the real SignalAgent cannot be imported (FUSE truncation).

    Previously returned all-empty signal arrays, which permanently suppressed
    GUIDANCE routing. Now applies the same lightweight keyword scan used in the
    _step2_signal exception path so explicit guidance-seeking messages still
    reach GUIDANCE mode even without the real LLM-backed agent.
    Replace with the real SignalAgent for production.
    """

    _GUIDANCE_KEYWORDS: frozenset = frozenset({
        "cbt", "dbt", "emdr", "therapy", "therapist",
        "technique", "techniques", "exercise", "exercises",
        "strategy", "strategies", "method", "methods",
        "how do i", "how to", "what can i do", "what should i",
        "help me", "advice", "tips", "resources", "skills",
        "psychoeducation", "mindfulness", "breathing",
    })

    def analyze(self, text: str, **kwargs) -> SignalPayload:
        text_lower = text.lower()
        has_guidance_intent = any(
            kw in text_lower for kw in self._GUIDANCE_KEYWORDS
        )
        return SignalPayload(
            distress_level=DistressLevel.LOW,
            # 0.6 when guidance intent detected — above Router's 0.40 low-band
            # ceiling so Rule 4 (guidance check) is reached. 0.5 otherwise —
            # still above threshold, COMFORT default via Rule 5.
            confidence=0.6 if has_guidance_intent else 0.5,
            emotional_states=[],
            cognitive_patterns=[],
            behavioral_indicators=(
                ["help_seeking_behavior"] if has_guidance_intent else []
            ),
            risk_indicators=[],
            support_needs=(
                ["psychoeducation"] if has_guidance_intent else []
            ),
            uncertainty_notes=(
                f"[STUB — real SignalAgent unavailable; "
                f"guidance_intent={has_guidance_intent}]"
            ),
        )


class _StubStrategyAgent:
    """
    Stub Support Strategy Agent — returns a minimal valid StrategyPayload.
    Used when the real SupportStrategyAgent cannot be imported (FUSE truncation).

    strategize() now accepts a RouterDecision (same as the real agent) so the
    pipeline can pass router_decision uniformly without branching on agent type.
    """
    def strategize(self, router_decision: RouterDecision, signal: SignalPayload) -> StrategyPayload:
        return StrategyPayload(
            mode=router_decision.mode,
            distress_level=signal.distress_level,
            tone_guidance="warm, empathetic, non-directive",
            framing_strategy="validate the user's experience before offering perspective",
        )

    def crisis_bypass(self) -> StrategyPayload:
        # Signature matches the real SupportStrategyAgent.crisis_bypass() — no args.
        return StrategyPayload(
            mode=OperationalMode.CRISIS,
            distress_level=DistressLevel.CRISIS,
            tone_guidance="calm, direct, safety-focused",
            framing_strategy="immediate safety acknowledgement; resource delivery",
        )


# ---------------------------------------------------------------------------
# Draft generator protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class DraftGeneratorProtocol(Protocol):
    """
    Protocol for the Interaction Model (LLM draft generator).

    Phase 3 stub returns a canned empathetic response.
    Phase 4/MVP implements this via Qwen3-4B base (no LoRA; see hf_space/app.py).
    Director-approved 2026-05-14. See hf_space/app.py for production dispatch logic.

    The pipeline calls generate() after building the ResponseContextPayload.
    The generator receives the full context so it can apply tone guidance,
    evidence citations, and crisis framing as directed. (REQ-700-133)
    """
    def generate(self, context: ResponseContextPayload) -> str:
        ...  # pragma: no cover


class StubDraftGenerator:
    """
    Phase 3 stub Interaction Model.

    Returns a canned response appropriate to the mode, demonstrating that
    the pipeline wiring is correct without requiring a GPU or model weights.
    Replace with a real LLM-backed implementation for Phase 4.
    """

    _COMFORT_DRAFT = (
        "It sounds like you're carrying a lot right now, and that makes sense given "
        "what you've shared. You don't have to work through this alone — reaching out "
        "is a meaningful step, and I'm here to support you."
    )
    _GUIDANCE_DRAFT = (
        "Based on the evidence I've gathered, there are a few things that may help. "
        "Speaking with a mental health professional can make a real difference, and "
        "evidence-based approaches like CBT have shown strong results for many people. "
        "Please treat this as information to explore, not a directive — you know your "
        "situation best."
    )
    _CRISIS_DRAFT = (
        "I can hear that things feel very difficult right now. Your safety matters most. "
        "Please reach out to one of the crisis support services below — they are "
        "available 24/7 and are there specifically for moments like this."
    )

    def generate(self, context: ResponseContextPayload) -> str:
        if context.mode == OperationalMode.CRISIS:
            return self._CRISIS_DRAFT
        if context.mode == OperationalMode.GUIDANCE:
            return self._GUIDANCE_DRAFT
        return self._COMFORT_DRAFT


# ---------------------------------------------------------------------------
# SPEC-300 §5: Baseline Australian crisis resources (mandatory in Crisis Mode)
# ---------------------------------------------------------------------------

# [CONCEPT] These are hardcoded in the pipeline because SPEC-300 §5 defines
# them as *mandatory static content* — they must not be LLM-generated or
# retrieved dynamically. The only permissible change is an admin update when
# a hotline number changes in the real world. (REQ-700-070)
BASELINE_CRISIS_RESOURCES: list[CrisisResource] = [
    # REQ-300-RS1: these four resources MUST always be displayed during Crisis Mode.
    # Order matches SPEC-300 §5 Step 2 and G-CRISIS-03 ratification.
    # Do NOT remove or reorder without Director approval.
    CrisisResource(name="Lifeline Australia",           number="13 11 14",     tier="baseline"),
    CrisisResource(name="Beyond Blue",                  number="1300 22 4636", tier="baseline"),
    CrisisResource(name="Suicide Call Back Service",    number="1300 659 467", tier="baseline"),
    CrisisResource(name="Emergency Services",           number="000",           tier="baseline"),
]

# REQ-300-RS2: demographic-specific resources — presented in the UI as a
# "More tailored support" expandable alongside the baseline set.
# NOT inferred from conversation context (REQ-300-RS3).
DEMOGRAPHIC_CRISIS_RESOURCES: list[CrisisResource] = [
    CrisisResource(name="QLife (LGBTIQ+)",            number="1800 184 527", tier="demographic_specific"),
    CrisisResource(name="13YARN (First Nations)",     number="13 92 76",     tier="demographic_specific"),
    CrisisResource(name="Kids Helpline (under 25)",   number="1800 55 1800", tier="demographic_specific"),
    CrisisResource(name="1800RESPECT (family violence)", number="1800 737 732", tier="demographic_specific"),
    CrisisResource(name="MensLine Australia",         number="1300 78 99 78", tier="demographic_specific"),
]


# ---------------------------------------------------------------------------
# Pipeline trace (REQ-700-110)
# ---------------------------------------------------------------------------

@dataclass
class PipelineTrace:
    """
    Session-scoped audit trace — destroyed when the session ends (REQ-700-LOG1).

    Fields map directly to the JSON schema defined in REQ-700-110. All
    timestamps are UTC. This object is never persisted; it lives only in
    memory for the duration of the pipeline run.
    """
    session_id:           str  = field(default_factory=lambda: str(uuid.uuid4()))
    execution_path:       list[str] = field(default_factory=list)
    signal_output:        Optional[dict] = None
    router_decision:      Optional[str] = None
    agents_triggered:     list[str] = field(default_factory=list)
    evidence_used:        list[str] = field(default_factory=list)
    adapter_configuration:list[str] = field(default_factory=list)
    evaluation_result:    Optional[str] = None
    verification_result:  Optional[str] = None
    final_action:         Optional[str] = None
    regen_count:          int = 0
    latency_ms:           Optional[float] = None
    started_at:           datetime = field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )

    def step(self, agent_name: str) -> None:
        """Record a completed pipeline step."""
        self.execution_path.append(agent_name)
        self.agents_triggered.append(agent_name)


# ---------------------------------------------------------------------------
# Pipeline result
# ---------------------------------------------------------------------------

@dataclass
class PipelineResult:
    """
    Unified output of NikkoPipeline.run().

    The frontend / API layer consumes this object. Fields not relevant to
    the current turn are None (e.g., verification is None when out_of_scope
    is True because the pipeline terminated at STEP 0).
    """
    response_text:        str
    mode:                 Optional[OperationalMode] = None
    out_of_scope:         bool = False
    safe_fallback_used:   bool = False
    evaluation:           Optional[EvaluationPayload] = None
    verification:         Optional[VerificationResult] = None
    trace:                Optional[PipelineTrace] = None
    crisis_resources:     Optional[list[CrisisResource]] = None


# ---------------------------------------------------------------------------
# Retrieval helper
# ---------------------------------------------------------------------------

def _retrieval_result_to_evidence_payload(result: RetrievalResult) -> EvidencePayload:
    """
    Convert a retrieval adapter's RetrievalResult into the ACP EvidencePayload
    that the EvidenceSynthesizerAgent expects.

    [CONCEPT] The two schemas live in different files (retrieval_schemas vs
    acp_schemas) because the retrieval layer was designed independently of
    the ACP message contracts. This conversion is the seam between those two
    domains. It is intentionally thin — no data is transformed, only re-shaped.
    """
    return EvidencePayload(
        query=result.query_echo,
        source_name=result.source_name,
        source_tier=result.source_tier,
        results=result.items,                    # list[EvidenceItem] — same type
        grey_literature_flag=result.grey_literature_flag,
    )


# ---------------------------------------------------------------------------
# Evidence search query builder
# ---------------------------------------------------------------------------

# Map signal key names (from SignalAgent) to human-readable search terms
# suitable for DuckDuckGo and PubMed queries.
_SUPPORT_NEED_TERMS: dict[str, str] = {
    "coping_strategies":        "coping strategies",
    "relaxation_techniques":    "relaxation techniques",
    "psychoeducation":          "mental health education",
    "behavioral_activation":    "behavioral activation",
    "cognitive_restructuring":  "cognitive restructuring",
    "problem_solving":          "problem solving strategies",
    "social_support_resources": "social support",
    "crisis_intervention":      "crisis intervention",
    "grounding_exercises":      "grounding exercises",
    "mindfulness":              "mindfulness meditation",
}

_EMOTIONAL_STATE_TERMS: dict[str, str] = {
    "sadness_spectrum":         "low mood depression sadness",
    "anxiety_spectrum":         "anxiety worry stress",
    "emotional_dysregulation":  "emotional dysregulation",
    "shame_guilt":              "shame guilt",
    "emotional_numbness":       "emotional numbness",
}

_COGNITIVE_PATTERN_TERMS: dict[str, str] = {
    "rumination":               "rumination overthinking",
    "catastrophizing":          "catastrophizing negative thinking",
    "black_white_thinking":     "black and white thinking",
    "hopeless_projection":      "hopelessness",
    "personalization":          "self-blame",
    "negative_core_beliefs":    "negative self-beliefs",
    "helplessness":             "learned helplessness",
    "meaninglessness":          "loss of meaning",
}


def _build_evidence_query(signal: SignalPayload) -> str:
    """
    Build a focused clinical search query from the SignalPayload fields.

    Rather than passing the raw user message (conversational, noisy, and
    search-engine-hostile — e.g. "Hi, I'm feeling sad, could you help me?"),
    we extract the clinical concepts SignalAgent detected and construct a
    structured query that returns relevant results from sanctioned domains.

    Priority: support_needs → emotional_states → cognitive_patterns.
    Capped at 3 topic terms and 2 emotional context terms to avoid
    over-specifying queries that return zero results.

    Examples:
      support_needs=["coping_strategies"], emotional_states=["sadness_spectrum"]
      → "coping strategies for low mood depression sadness mental health"

      support_needs=["relaxation_techniques", "mindfulness"],
      emotional_states=["anxiety_spectrum"]
      → "relaxation techniques mindfulness for anxiety worry stress mental health"

      (no signals detected)
      → "mental health wellbeing support"
    """
    topic_terms: list[str] = []
    for key in (signal.support_needs or []):
        term = _SUPPORT_NEED_TERMS.get(key)
        if term and term not in topic_terms:
            topic_terms.append(term)

    emotional_terms: list[str] = []
    for key in (signal.emotional_states or []):
        term = _EMOTIONAL_STATE_TERMS.get(key)
        if term and term not in emotional_terms:
            emotional_terms.append(term)
    for key in (signal.cognitive_patterns or []):
        term = _COGNITIVE_PATTERN_TERMS.get(key)
        if term and term not in topic_terms and term not in emotional_terms:
            emotional_terms.append(term)

    # Cap to avoid over-specifying (search engines score shorter queries higher).
    topic_part    = " ".join(topic_terms[:3])
    emotional_part = " ".join(emotional_terms[:2])

    if topic_part and emotional_part:
        return f"{topic_part} for {emotional_part} mental health"
    elif topic_part:
        return f"{topic_part} mental health"
    elif emotional_part:
        return f"{emotional_part} mental health support"
    else:
        # Fallback: generic — happens when SignalAgent found behavioral signals
        # only (e.g. help_seeking_behavior), which don't map to topic terms.
        return "mental health wellbeing coping strategies"


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

class NikkoPipeline:
    """
    End-to-end SPEC-700 execution pipeline.

    Instantiate once per application lifetime; call run() once per user turn.

        pipeline = NikkoPipeline()
        result = pipeline.run(user_input="I've been feeling overwhelmed lately.")

    Dependency injection points:
        draft_generator : DraftGeneratorProtocol (default: StubDraftGenerator)
        scope_classifier: ScopeClassifier or stub
        signal_agent    : SignalAgent or stub

    These can be overridden in tests:
        pipeline = NikkoPipeline(
            draft_generator=MyRealLLM(),
            scope_classifier=MyScopeClassifier(),
        )
    """

    def __init__(
        self,
        draft_generator:  Optional[DraftGeneratorProtocol] = None,
        scope_classifier=None,
        signal_agent=None,
        strategy_agent=None,
        evaluator=None,
    ) -> None:
        # [CONCEPT] Lazy initialisation: if a real agent is injected, use it;
        # otherwise fall back to the stub. This pattern lets the pipeline
        # run deterministically in Phase 3 tests without any GPU resources.
        # `evaluator` is injectable so the notebook can pass a mock that
        # does not require the `transformers` library (Phase 3 sandbox).
        self._scope   = scope_classifier or (
            _ScopeClassifier() if _HAVE_SCOPE_CLASSIFIER else _StubScopeClassifier()
        )
        self._signal  = signal_agent or (
            _SignalAgent() if _HAVE_SIGNAL_AGENT else _StubSignalAgent()
        )
        self._strategy = strategy_agent or (
            _SupportStrategyAgent() if _HAVE_STRATEGY_AGENT else _StubStrategyAgent()
        )
        self._router      = Router()
        self._pubmed      = PubMedAdapter()
        self._web         = WebSearchAdapter()
        self._synthesizer = EvidenceSynthesizerAgent()
        self._evaluator   = evaluator or EvaluatorAgent()
        self._vs          = VerificationSupervisorAgent()
        self._draft_gen   = draft_generator or StubDraftGenerator()

        logger.info(
            "NikkoPipeline initialised — scope=%s signal=%s strategy=%s draft=%s",
            type(self._scope).__name__,
            type(self._signal).__name__,
            type(self._strategy).__name__,
            type(self._draft_gen).__name__,
        )

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(
        self,
        user_input: str,
        session_id: Optional[str] = None,
        regen_count: int = 0,
    ) -> PipelineResult:
        """
        Execute the full SPEC-700 pipeline for one user turn.

        Parameters
        ----------
        user_input   : Raw user message (untrusted — sanitized in STEP 1).
        session_id   : Optional stable ID for the current session.
                       Generated internally if not provided.
        regen_count  : Incremented on each regeneration loop. The pipeline
                       calls itself recursively when the Evaluator emits
                       REGENERATE. Callers should always pass 0 (default).

        Spec trace
        ----------
        REQ-700-001  MUST define the exact end-to-end flow of every interaction.
        REQ-700-002  Outputs SHALL be traceable, reproducible, structurally consistent.
        REQ-700-010  Nikko SHALL be a deterministic multi-agent pipeline.
        """
        t0 = time.perf_counter()
        trace = PipelineTrace(
            session_id=session_id or str(uuid.uuid4()),
            regen_count=regen_count,
        )
        logger.info("Pipeline.run() — session=%s regen=%d", trace.session_id, regen_count)

        # ── STEP 0: Scope Classification ─────────────────────────────────
        # REQ-700-SC1: MUST evaluate every input before any other processing.
        # REQ-700-SC2: OUT_OF_SCOPE → terminate here, ≤ 500 ms.
        scope = self._step0_scope(user_input, trace)
        if scope.decision == ScopeDecision.OUT_OF_SCOPE:
            trace.final_action = "out_of_scope_redirect"
            trace.latency_ms = (time.perf_counter() - t0) * 1000
            logger.info("Pipeline: OUT_OF_SCOPE — terminating at STEP 0.")
            return PipelineResult(
                response_text=scope.warm_redirect or
                    "I can only help with emotional wellbeing and mental health topics.",
                out_of_scope=True,
                trace=trace,
            )

        # ── STEP 1: Input sanitization ───────────────────────────────────
        # REQ-700-021/022: treat as untrusted, sanitize injection attempts.
        clean_input = self._step1_sanitize(user_input)
        trace.step("input_sanitization")

        # ── STEP 2: Psychological Signal Detection ────────────────────────
        # REQ-700-030: sanitized input → Signal Agent.
        # REQ-700-032: output is immutable for the rest of the pipeline.
        signal = self._step2_signal(clean_input, trace)

        # ── STEP 3: Routing ───────────────────────────────────────────────
        # REQ-700-040/041: Router evaluates signal; outputs one mode.
        # REQ-700-042: Mixed-mode execution SHALL NOT be permitted.
        router_decision = self._step3_route(signal, regen_count, trace)
        mode = router_decision.mode

        # ── STEPS 4–10: Mode execution ────────────────────────────────────
        evidence: Optional[SynthesizedEvidence] = None
        crisis_resources: Optional[list[CrisisResource]] = None

        if mode == OperationalMode.GUIDANCE:
            # REQ-700-060: evidence first, tone second.
            # Build a clinical topic query from SignalPayload rather than
            # passing the raw user message — see _build_evidence_query().
            evidence = self._steps4_7_guidance_evidence(signal, trace)

        elif mode == OperationalMode.CRISIS:
            # REQ-700-070: inject mandatory Australian crisis resources.
            # REQ-700-VS1: evidence retrieval is skipped in Crisis Mode.
            crisis_resources = BASELINE_CRISIS_RESOURCES
            trace.step("crisis_resource_injection")
            logger.info("Pipeline: Crisis Mode — skipping evidence retrieval (REQ-700-VS1).")

        # ── Support Strategy ──────────────────────────────────────────────
        strategy = self._step_strategy(router_decision, signal, trace)

        # ── Build ResponseContextPayload ──────────────────────────────────
        # [CONCEPT] This is the single object the Interaction Model (LLM)
        # receives. REQ-700-133 / REQ-200-129/130: the LLM sees only this
        # curated context — never raw retrieval outputs or signal payloads.
        context = ResponseContextPayload(
            mode=mode,
            signals=signal,
            strategy=strategy,
            synthesized_evidence=evidence,
            crisis_resources=crisis_resources,
            raw_user_message=clean_input,  # [MVP-INFRA] consumed by HFSpaceFullGenerator
        )

        # ── STEP 10: Draft generation (Interaction Model) ─────────────────
        # REQ-700-100: output constructed from LLM text + strategy constraints
        #              + verified evidence + safety framing.
        draft = self._step10_draft(context, trace)

        # ── ADP-B late-crisis override ────────────────────────────────────
        # If the stub SignalAgent missed a crisis signal (it only does keyword
        # guidance detection) and ADP-B caught it in the HF Space, the draft
        # generator returns ADPB_CRISIS_SENTINEL instead of "" to avoid the
        # silent SAFE_FALLBACK path. Intercept here and immediately deliver a
        # proper CRISIS PipelineResult with hotlines and the safety flag set.
        if draft == ADPB_CRISIS_SENTINEL:
            crisis_resources = BASELINE_CRISIS_RESOURCES
            trace.step("adpb_crisis_override")
            trace.final_action = "adpb_crisis_override"
            trace.latency_ms = (time.perf_counter() - t0) * 1000
            logger.warning(
                "Pipeline: ADP-B late-crisis override triggered. "
                "Switching to CRISIS mode (local router was COMFORT)."
            )
            return PipelineResult(
                response_text=_ADPB_CRISIS_RESPONSE,
                mode=OperationalMode.CRISIS,
                crisis_resources=crisis_resources,
                trace=trace,
            )

        # ── STEP 11: Evaluator ─────────────────────────────────────────────
        # REQ-700-080: every non-crisis response MUST pass Evaluator audit.
        # REQ-700-082: on failure → regenerate OR safe fallback.
        evaluation = self._step11_evaluate(draft, context, trace)

        if evaluation.verdict != EvaluationVerdict.PASS:
            return self._handle_evaluator_failure(
                evaluation, user_input, session_id, regen_count, trace, t0
            )

        # ── STEP 12: Verification Supervisor ──────────────────────────────
        # REQ-700-090: final structural gate before output.
        # REQ-700-092: on failure → safe fallback.
        verification = self._step12_verify(context, evaluation, scope, regen_count, trace)

        if not verification.passed:
            trace.final_action = "vs_safe_fallback"
            trace.latency_ms = (time.perf_counter() - t0) * 1000
            logger.warning("Pipeline: VS failed — emitting safe fallback. Reasons: %s",
                           verification.failure_reasons)
            return PipelineResult(
                response_text=SAFE_FALLBACK_RESPONSE,
                mode=mode,
                safe_fallback_used=True,
                evaluation=evaluation,
                verification=verification,
                trace=trace,
                crisis_resources=crisis_resources,
            )

        # ── STEPS 13–14: Final assembly and delivery ───────────────────────
        # REQ-700-100/101: include AI disclosure framing, non-clinical tone,
        #                  autonomy reinforcement.
        final_response = self._step13_assemble(draft, context, trace)

        # ── STEP 15: Trace logging ─────────────────────────────────────────
        # REQ-700-LOG1: ephemeral — trace lives in memory only.
        trace.final_action = "response_delivered"
        trace.latency_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "Pipeline complete — mode=%s latency=%.1fms regen=%d",
            mode.value, trace.latency_ms, regen_count,
        )

        return PipelineResult(
            response_text=final_response,
            mode=mode,
            safe_fallback_used=False,
            evaluation=evaluation,
            verification=verification,
            trace=trace,
            crisis_resources=crisis_resources,
        )

    # ------------------------------------------------------------------
    # Private step implementations
    # ------------------------------------------------------------------

    def _step0_scope(self, text: str, trace: PipelineTrace) -> ScopeClassifierDecision:
        """STEP 0 — Scope classification (REQ-700-SC1/SC2)."""
        try:
            decision = self._scope.classify(text)
        except Exception as exc:
            # REQ-700-120: on agent failure, retry once then safe response.
            # For the Scope Classifier, a failure must default to AMBIGUOUS
            # (asymmetric error policy: err toward inclusion, REQ-200-SC3).
            logger.error("ScopeClassifier raised %s — defaulting to AMBIGUOUS.", exc)
            decision = ScopeClassifierDecision(
                decision=ScopeDecision.AMBIGUOUS,
                confidence=0.0,
                warm_redirect=None,
            )
        trace.step("scope_classifier")
        logger.debug("Scope: %s (confidence=%.2f)", decision.decision.value, decision.confidence)
        return decision

    def _step1_sanitize(self, text: str) -> str:
        """
        STEP 1 — Input sanitization (REQ-700-021/022).

        Phase 3: strips leading/trailing whitespace and collapses internal
        whitespace runs. Injection-pattern detection is a Phase 5 hardening
        item (SPEC-600 §8).
        """
        import re
        return re.sub(r"\s+", " ", text.strip())

    def _step2_signal(self, text: str, trace: PipelineTrace) -> SignalPayload:
        """STEP 2 — Psychological signal detection (REQ-700-030/032)."""
        try:
            signal = self._signal.analyze(text)
        except Exception as exc:
            logger.info("SignalAgent raised %s — using keyword fallback.", exc)
            # REQ-700-120: safe degradation. Rather than returning all-empty arrays
            # (which permanently suppresses GUIDANCE routing), apply a lightweight
            # keyword scan so explicit guidance-seeking messages ("CBT techniques",
            # "how do I", "therapy") still reach GUIDANCE mode.
            # [PROPOSED-RECONCILIATION: This is a production safety net for Fly.io
            # free-tier environments where Qwen2.5-3B-Instruct OOMs at load time.
            # The keyword list is intentionally conservative — it only covers clear
            # guidance-intent signals, not vague distress language. Director review
            # recommended before GA. Logged as G-SIGNAL-FALLBACK-01.]
            _GUIDANCE_KEYWORDS: frozenset[str] = frozenset({
                "cbt", "dbt", "emdr", "therapy", "therapist",
                "technique", "techniques", "exercise", "exercises",
                "strategy", "strategies", "method", "methods",
                "how do i", "how to", "what can i do", "what should i",
                "help me", "advice", "tips", "resources", "skills",
                "psychoeducation", "mindfulness", "breathing",
            })
            text_lower = text.lower()
            has_guidance_intent = any(kw in text_lower for kw in _GUIDANCE_KEYWORDS)
            signal = SignalPayload(
                distress_level=DistressLevel.LOW,
                # [PROPOSED-RECONCILIATION: confidence must be >= 0.40 for the
                # Router to reach Rule 4 (guidance check). When guidance_intent
                # is detected via keywords, we set 0.6 — above the low-band
                # ceiling — so the Router doesn't short-circuit to COMFORT
                # at Rule 3. When no guidance intent is found, 0.0 is correct:
                # COMFORT fallback is the right default for an unknown signal.]
                confidence=0.6 if has_guidance_intent else 0.0,
                emotional_states=[],
                cognitive_patterns=[],
                # help_seeking_behavior triggers GUIDANCE in the Router
                # (REQ-700-040: _GUIDANCE_BEHAVIORAL_INDICATORS match).
                behavioral_indicators=(
                    ["help_seeking_behavior"] if has_guidance_intent else []
                ),
                risk_indicators=[],
                # psychoeducation also triggers GUIDANCE as a backup path.
                support_needs=(
                    ["psychoeducation"] if has_guidance_intent else []
                ),
                uncertainty_notes=(
                    "[SIGNAL AGENT FAILURE — keyword fallback active; "
                    f"guidance_intent={has_guidance_intent}]"
                ),
            )
            logger.info(
                "SignalAgent fallback: guidance_intent=%s text_lower_snippet=%r",
                has_guidance_intent, text_lower[:80],
            )
        trace.step("signal_agent")
        trace.signal_output = {
            "distress_level": signal.distress_level.value,
            "confidence": signal.confidence,
        }
        logger.info("Signal: distress=%s confidence=%.2f",
                    signal.distress_level.value, signal.confidence)
        return signal

    def _step3_route(
        self, signal: SignalPayload, attempt_count: int, trace: PipelineTrace
    ) -> RouterDecision:
        """
        STEP 3 — Routing (REQ-700-040 through REQ-700-042).

        REQ-700-123: on Router failure, default to Comfort Mode and suppress
        all evidence chains.
        """
        try:
            decision = self._router.route(signal, attempt_count=attempt_count + 1)
        except Exception as exc:
            logger.error("Router raised %s — defaulting to COMFORT Mode (REQ-700-123).", exc)
            from agents.router import RouterDecision
            decision = RouterDecision(
                mode=OperationalMode.COMFORT,
                routing_rationale="[ROUTER FAILURE — forced COMFORT]",
                confidence=0.0,
                crisis_override=False,  # COMFORT fallback is never a crisis override
            )
        trace.step("router")
        trace.router_decision = decision.mode.value
        logger.info("Router: mode=%s confidence=%.2f crisis_override=%s",
                    decision.mode.value, decision.confidence,
                    getattr(decision, "crisis_override", False))
        return decision

    def _steps4_7_guidance_evidence(
        self, signal: SignalPayload, trace: PipelineTrace
    ) -> Optional[SynthesizedEvidence]:
        """
        STEPS 4–8 (Guidance Mode) — Evidence retrieval + synthesis.

        REQ-700-121: on retrieval failure, proceed without evidence and
        explicitly avoid fabrication (handled downstream by Evaluator).

        Runs ADAPTER_PRIORITY_ORDER sequentially: PubMed first, WebSearch
        fallback. Both results (if any) are passed to the Synthesizer.

        Query construction: _build_evidence_query() converts the SignalPayload's
        support_needs, emotional_states, and cognitive_patterns into a clinical
        search query (e.g. "coping strategies for low mood sadness mental health")
        rather than using the raw user message, which is conversational and
        returns irrelevant or no results from sanctioned domains.
        """
        # Build the search query from detected clinical signals, not the raw message.
        query = _build_evidence_query(signal)
        logger.info("Evidence query: %r  (from signal.support_needs=%s emotional_states=%s)",
                    query, signal.support_needs, signal.emotional_states)

        retrieval_results: list[EvidencePayload] = []
        adapters_run = []

        for AdapterClass in ADAPTER_PRIORITY_ORDER:
            adapter_name = AdapterClass.__name__
            try:
                adapter = AdapterClass()
                if AdapterClass is PubMedAdapter:
                    params = PubMedQueryParams(query=query, max_results=5)
                else:
                    params = StaticCacheQueryParams(query=query, max_results=3)
                result: RetrievalResult = adapter.search(params)
                if result.items:
                    retrieval_results.append(_retrieval_result_to_evidence_payload(result))
                    adapters_run.append(adapter_name)
                    logger.info("Retrieval %s: %d items", adapter_name, len(result.items))
                else:
                    logger.info("Retrieval %s: 0 items returned.", adapter_name)
            except Exception as exc:
                # REQ-700-121: failure does not abort — continue with other adapters.
                logger.warning("Retrieval adapter %s failed: %s", adapter_name, exc)

        trace.step("evidence_retrieval")
        trace.adapter_configuration = adapters_run
        trace.evidence_used = [ep.source_name for ep in retrieval_results]

        if not retrieval_results:
            # [PROPOSED-RECONCILIATION: C5 checks that the evidence step RAN, not
            # that it produced results. Returning an empty SynthesizedEvidence object
            # (rather than None) correctly signals "step ran, found nothing" vs
            # "step was skipped entirely". Returning None was causing C5 to fire and
            # emit SAFE_FALLBACK_RESPONSE on Fly.io where PubMed/WebSearch are
            # unreachable (network restrictions / free-tier timeouts). The ADP-A
            # context_prompt_builder handles empty citations gracefully — it simply
            # omits the evidence injection block. Director: review as G-RETRIEVAL-01.]
            logger.warning(
                "All retrievals returned 0 items — returning empty SynthesizedEvidence "
                "so GUIDANCE mode can proceed without RAG injection. C5 preserved."
            )
            return SynthesizedEvidence(
                summary=(
                    "No peer-reviewed evidence was retrieved for this query. "
                    "Retrieval adapters returned zero results — respond from "
                    "general clinical knowledge with appropriate epistemic humility."
                ),
                citations=[],
                confidence=0.0,
                grey_literature_used=False,
            )

        evidence = self._synthesizer.synthesize(retrieval_results, query=query)
        trace.step("evidence_synthesizer")
        logger.info("Synthesizer: confidence=%.4f grey_lit=%s",
                    evidence.confidence, evidence.grey_literature_used)
        return evidence

    def _step_strategy(
        self, router_decision: RouterDecision, signal: SignalPayload, trace: PipelineTrace
    ) -> StrategyPayload:
        """Support Strategy Agent step (REQ-200-060/061).

        Receives the full RouterDecision so the real SupportStrategyAgent
        (which expects a RouterDecision, not a bare OperationalMode) gets the
        correct type. Previously this method received only `mode: OperationalMode`,
        causing an AttributeError on every request when the real agent tried to
        call `router_decision.mode` on an OperationalMode enum value.
        """
        mode = router_decision.mode
        try:
            if mode == OperationalMode.CRISIS:
                # CRISIS: strategy agent is bypassed; use static crisis strategy.
                # crisis_bypass() takes NO arguments in the real SupportStrategyAgent
                # (it returns a hardcoded StrategyPayload constant). Passing signal
                # previously caused a TypeError on the real agent — fixed here.
                strategy = self._strategy.crisis_bypass()
            else:
                strategy = self._strategy.strategize(router_decision, signal)
        except Exception as exc:
            logger.error("StrategyAgent raised %s — using minimal fallback strategy.", exc)
            strategy = StrategyPayload(
                mode=mode,
                distress_level=signal.distress_level,
                tone_guidance="empathetic, non-directive",
                framing_strategy="validate and support",
            )
        trace.step("support_strategy_agent")
        return strategy

    def _step10_draft(
        self, context: ResponseContextPayload, trace: PipelineTrace
    ) -> str:
        """
        STEP 10 — Draft generation (Interaction Model).

        REQ-700-133: LLM receives ONLY the curated ResponseContextPayload —
        never raw retrieval outputs or signal payloads directly.
        """
        try:
            draft = self._draft_gen.generate(context)
        except Exception as exc:
            logger.error("DraftGenerator raised %s — using safe fallback draft.", exc)
            draft = SAFE_FALLBACK_RESPONSE
        trace.step("interaction_model")
        logger.debug("Draft generated (%d chars).", len(draft))
        return draft

    def _step11_evaluate(
        self,
        draft: str,
        context: ResponseContextPayload,
        trace: PipelineTrace,
    ) -> EvaluationPayload:
        """
        STEP 11 — Evaluator audit pass (REQ-700-080 through REQ-700-082).

        REQ-700-122: on Evaluator failure, default to SAFE MODE response
        with no evidence injection. Modelled here as returning a synthetic
        FAIL payload so the failure handling path is triggered normally.
        """
        try:
            evaluation = self._evaluator.evaluate(draft, context)
        except Exception as exc:
            logger.error("EvaluatorAgent raised %s — synthetic FAIL payload.", exc)
            evaluation = EvaluationPayload(
                verdict=EvaluationVerdict.FAIL,
                safety_check=False,
                tone_check=False,
                hallucination_check=False,
                rejection_reasons=[f"[EVALUATOR FAILURE: {exc}]"],
            )
        trace.step("evaluator_agent")
        trace.evaluation_result = evaluation.verdict.value
        logger.info("Evaluator: verdict=%s", evaluation.verdict.value)
        return evaluation

    def _step12_verify(
        self,
        context: ResponseContextPayload,
        evaluation: EvaluationPayload,
        scope: ScopeClassifierDecision,
        regen_count: int,
        trace: PipelineTrace,
    ) -> VerificationResult:
        """STEP 12 — Verification Supervisor (REQ-700-090 through REQ-700-092)."""
        verification = self._vs.verify(context, evaluation, scope, regen_count)
        trace.step("verification_supervisor")
        trace.verification_result = "passed" if verification.passed else "failed"
        return verification

    def _step13_assemble(
        self,
        draft: str,
        context: ResponseContextPayload,
        trace: PipelineTrace,
    ) -> str:
        """
        STEP 13 — Final response assembly (REQ-700-100/101).

        Non-clinical framing is ensured by the Evaluator in STEP 11.
        Autonomy reinforcement (REQ-700-101) is now satisfied at the UI
        layer by the persistent AiDisclaimer component in chat.jsx
        (G-UI-01 / REQ-300-164), which renders below the composer on every
        turn. Appending a per-message suffix was redundant, produced formulaic
        responses, and has been removed.

        [PROPOSED-RECONCILIATION: Director-approved 2026-05-15. REQ-700-101
        is fulfilled by AiDisclaimer in frontend rather than server-side string
        appending. Logged as G-AUTONOMY-SUFFIX-01.]
        """
        trace.step("response_assembly")
        return draft

    # ------------------------------------------------------------------
    # Failure handlers
    # ------------------------------------------------------------------

    def _handle_evaluator_failure(
        self,
        evaluation: EvaluationPayload,
        user_input: str,
        session_id: Optional[str],
        regen_count: int,
        trace: PipelineTrace,
        t0: float,
    ) -> PipelineResult:
        """
        REQ-700-082: on Evaluator failure, regenerate if within loop limit;
        otherwise emit safe fallback.

        REQ-200-170: maximum 2 regeneration attempts per request.
        REQ-200-171: no more than 1 evaluation cycle per response — so we
        regenerate by re-running the full pipeline from STEP 2, not by
        re-calling just the Evaluator.
        """
        if (
            evaluation.verdict == EvaluationVerdict.REGENERATE
            and regen_count < MAX_REGEN_ATTEMPTS
        ):
            logger.info(
                "Evaluator REGENERATE — attempt %d/%d. Re-running pipeline.",
                regen_count + 1, MAX_REGEN_ATTEMPTS,
            )
            return self.run(user_input, session_id=session_id, regen_count=regen_count + 1)

        # FAIL verdict or regen limit exhausted → safe fallback.
        trace.final_action = "evaluator_safe_fallback"
        trace.latency_ms = (time.perf_counter() - t0) * 1000
        logger.warning(
            "Evaluator %s (regen=%d) — emitting safe fallback.",
            evaluation.verdict.value, regen_count,
        )
        return PipelineResult(
            response_text=SAFE_FALLBACK_RESPONSE,
            safe_fallback_used=True,
            evaluation=evaluation,
            trace=trace,
        )

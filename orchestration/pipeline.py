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
# Agent stubs (used when FUSE-truncated agents cannot be imported cleanly)
# ---------------------------------------------------------------------------

# [CONCEPT] try/except at import time — we attempt to import the full agent
# implementation. If Python raises a SyntaxError (caused by the FUSE mount
# showing a truncated version of the file) we fall through to the stub.
# This lets the pipeline run end-to-end in Phase 3 without requiring all
# agents to be syntactically correct in the Linux sandbox.

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
    Stub Signal Agent — returns LOW distress with empty signal arrays.
    Used when the real SignalAgent cannot be imported (FUSE truncation).
    Replace with the real SignalAgent for production.
    """
    def analyze(self, text: str, **kwargs) -> SignalPayload:
        return SignalPayload(
            distress_level=DistressLevel.LOW,
            confidence=0.50,
            emotional_states=[],
            cognitive_patterns=[],
            behavioral_indicators=[],
            risk_indicators=[],
            support_needs=[],
            uncertainty_notes="[STUB — real SignalAgent unavailable]",
        )


class _StubStrategyAgent:
    """
    Stub Support Strategy Agent — returns a minimal valid StrategyPayload.
    Used when the real SupportStrategyAgent cannot be imported (FUSE truncation).
    """
    def strategize(self, mode: OperationalMode, signal: SignalPayload) -> StrategyPayload:
        return StrategyPayload(
            mode=mode,
            distress_level=signal.distress_level,
            tone_guidance="warm, empathetic, non-directive",
            framing_strategy="validate the user's experience before offering perspective",
        )

    def crisis_bypass(self, signal: SignalPayload) -> StrategyPayload:
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
    CrisisResource(name="QLife (LGBTIQ+)",            number="1800 184 527", tier="demographic"),
    CrisisResource(name="13YARN (First Nations)",     number="13 92 76",     tier="demographic"),
    CrisisResource(name="Kids Helpline (under 25)",   number="1800 55 1800", tier="demographic"),
    CrisisResource(name="1800RESPECT (family violence)", number="1800 737 732", tier="demographic"),
    CrisisResource(name="MensLine Australia",         number="1300 78 99 78", tier="demographic"),
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
            evidence = self._steps4_7_guidance_evidence(clean_input, trace)

        elif mode == OperationalMode.CRISIS:
            # REQ-700-070: inject mandatory Australian crisis resources.
            # REQ-700-VS1: evidence retrieval is skipped in Crisis Mode.
            crisis_resources = BASELINE_CRISIS_RESOURCES
            trace.step("crisis_resource_injection")
            logger.info("Pipeline: Crisis Mode — skipping evidence retrieval (REQ-700-VS1).")

        # ── Support Strategy ──────────────────────────────────────────────
        strategy = self._step_strategy(mode, signal, trace)

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
            logger.error("SignalAgent raised %s — defaulting to LOW distress.", exc)
            # REQ-700-120: safe degradation; LOW distress routes to Comfort Mode.
            signal = SignalPayload(
                distress_level=DistressLevel.LOW,
                confidence=0.0,
                emotional_states=[],
                cognitive_patterns=[],
                behavioral_indicators=[],
                risk_indicators=[],
                support_needs=[],
                uncertainty_notes="[SIGNAL AGENT FAILURE — defaulting to LOW]",
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
        self, query: str, trace: PipelineTrace
    ) -> Optional[SynthesizedEvidence]:
        """
        STEPS 4–8 (Guidance Mode) — Evidence retrieval + synthesis.

        REQ-700-121: on retrieval failure, proceed without evidence and
        explicitly avoid fabrication (handled downstream by Evaluator).

        Runs ADAPTER_PRIORITY_ORDER sequentially: PubMed first, WebSearch
        fallback. Both results (if any) are passed to the Synthesizer.
        """
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
            logger.warning("All retrievals returned 0 items — evidence will be None.")
            return None

        evidence = self._synthesizer.synthesize(retrieval_results, query=query)
        trace.step("evidence_synthesizer")
        logger.info("Synthesizer: confidence=%.4f grey_lit=%s",
                    evidence.confidence, evidence.grey_literature_used)
        return evidence

    def _step_strategy(
        self, mode: OperationalMode, signal: SignalPayload, trace: PipelineTrace
    ) -> StrategyPayload:
        """Support Strategy Agent step (REQ-200-060/061)."""
        try:
            if mode == OperationalMode.CRISIS:
                # CRISIS: strategy agent is bypassed; use static crisis strategy.
                strategy = self._strategy.crisis_bypass(signal)
            else:
                strategy = self._strategy.strategize(mode, signal)
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

        Applies non-clinical framing and autonomy reinforcement.
        In Phase 3 this is a lightweight string wrapper; the full
        safety-framing layer is a Phase 5 deliverable (SPEC-600 §8).

        REQ-700-101:
          - non-clinical framing (ensured by Evaluator in STEP 11)
          - autonomy reinforcement — appended below when not already present
        """
        autonomy_suffix = (
            "\n\nRemember: this is information to consider, not professional advice. "
            "You're the expert on your own experience."
        )
        # Avoid double-appending in regen loops.
        if "expert on your own experience" not in draft:
            assembled = draft + autonomy_suffix
        else:
            assembled = draft

        trace.step("response_assembly")
        return assembled

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

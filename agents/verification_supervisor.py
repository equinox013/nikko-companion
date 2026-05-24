"""
agents/verification_supervisor.py
===================================
Verification Supervisor Agent — Phase 3, Step 9.

Spec source : SPEC-200 §5.6, SPEC-700 §7
Requirements: REQ-200-090, REQ-200-091, REQ-200-VS1,
              REQ-700-090, REQ-700-091, REQ-700-092, REQ-700-VS1,
              REQ-200-170 (loop limit)

Role in the pipeline (SPEC-700 Step 12)
-----------------------------------------
  Evaluator Agent
       │  EvaluationPayload           ← content gate result (MUST be PASS)
       ▼
  Verification Supervisor (this module)
       │  VerificationResult           ← structural gate result
       ▼
  Final Response Assembly (Step 13)   ← only if VerificationResult.passed = True

Scope (REQ-200-VS1)
--------------------
  This agent checks STRUCTURAL INTEGRITY of the pipeline execution.
  It does NOT audit response content — that is the Evaluator's domain.

  Active checks (normal mode):
    C1  Evaluator gate          — Evaluator MUST have emitted PASS before VS runs.
    C2  Scope routing integrity — OUT_OF_SCOPE inputs must not reach this step.
    C3  Mode-distress alignment — OperationalMode must match DistressLevel.
    C4  Crisis resources        — CRITICAL distress requires crisis_resources populated.
    C5  Evidence pipeline       — GUIDANCE mode requires synthesized_evidence present.
    C6  Agent contamination     — evidence absent in Comfort; crisis_resources absent
                                  in Guidance.
    C7  Loop limit              — regen_count MUST be < MAX_REGEN_ATTEMPTS (2).

  Crisis Mode (Level 3, REQ-700-VS1):
    Suspended: C5 (evidence pipeline), C6 (contamination)
    Active   : C1, C2, C3, C4, C7

Design note: deterministic, no LLM
-------------------------------------
Like the Synthesizer, the VS is intentionally deterministic. Every check maps
to a named REQ ID, making failures fully auditable. No LLM round-trip is added
here — the pipeline already paid for two LLM calls (draft generation + LLM judge).
"""

from __future__ import annotations

import logging
from typing import Optional

# [CONCEPT] All inter-agent data types live in acp_schemas.py — the single
# source of truth for data shapes across the NIKKO pipeline. The VS imports
# only what it needs to inspect; it never defines its own schemas.
from schemas.acp_schemas import (
    DistressLevel,
    EvaluationPayload,
    EvaluationVerdict,
    OperationalMode,
    ResponseContextPayload,
    ScopeClassifierDecision,
    ScopeDecision,
    VerificationResult,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants (all values trace to ratified requirements)
# ---------------------------------------------------------------------------

# REQ-200-170: Each agent MUST NOT iterate more than 2 times per request.
# Director ratified: maximum 2 regeneration attempts; VS blocks the 3rd.
MAX_REGEN_ATTEMPTS: int = 2

# Minimal safe fallback text emitted when VS fails (REQ-700-092).
# Kept intentionally neutral — the VS is a structural gate, not a clinical one.
# The Interaction Model is responsible for therapeutic tone; if VS has failed,
# we cannot trust the pipeline state, so we use a fixed canned response.
SAFE_FALLBACK_RESPONSE: str = (
    "I'm here to support you. If you're going through something difficult "
    "right now, please reach out to a trusted person or a professional "
    "who can help. You don't have to face this alone."
)


# ---------------------------------------------------------------------------
# Internal check functions
# ---------------------------------------------------------------------------

def _c1_evaluator_gate(
    evaluation: EvaluationPayload,
) -> Optional[str]:
    """
    C1 — Evaluator gate (REQ-700-090).

    The Evaluator is the final content gate; the VS is the final structural
    gate. Both MUST pass for delivery. If the pipeline reaches the VS with
    a non-PASS verdict, something has gone wrong in the orchestrator logic.
    """
    if evaluation.verdict != EvaluationVerdict.PASS:
        return (
            f"[C1/REQ-700-090] Evaluator verdict is '{evaluation.verdict.value}' "
            f"— pipeline must not reach VS with a non-PASS verdict. "
            f"Rejection reasons: {evaluation.rejection_reasons}"
        )
    return None


def _c2_scope_routing(
    scope_decision: ScopeClassifierDecision,
) -> Optional[str]:
    """
    C2 — Scope routing integrity (REQ-700-091).

    An OUT_OF_SCOPE classification should have been handled at STEP 0
    (SPEC-700 §4 STEP 0). If it reaches the VS, routing is compromised.
    """
    if scope_decision.decision == ScopeDecision.OUT_OF_SCOPE:
        return (
            f"[C2/REQ-700-091] Scope classifier returned OUT_OF_SCOPE "
            f"(reason: {scope_decision.warm_redirect!r}) — request should have been "
            "deflected at STEP 0 and must not reach the VS."
        )
    return None


def _c3_mode_distress_alignment(
    context: ResponseContextPayload,
) -> Optional[str]:
    """
    C3 — Mode-distress level alignment (REQ-200-VS1).

    Hard rules:
      DistressLevel.CRISIS → OperationalMode MUST be CRISIS.
      DistressLevel.HIGH   → any mode is valid (COMFORT, GUIDANCE, or CRISIS).
      DistressLevel.LOW    → any mode is valid.
      DistressLevel.LOW    → CRISIS mode would be anomalous (flag, not hard fail).

    [PROPOSED-RECONCILIATION: 2026-05-23] The original HIGH→COMFORT block
    ("ELEVATED distress MUST route to GUIDANCE or CRISIS") has been removed.
    Rationale: HIGH distress + COMFORT is a valid and common routing outcome.
    A user venting exhaustion or hopelessness ("just gotten off a shitty shift...
    nothing ever gets better") is seeking emotional validation, not guidance or
    resources. Forcing GUIDANCE on every HIGH-distress message is paternalistic
    and produces jarring responses that miss what the user actually needs.
    The Router has full context (guidance_intent, distress level, signal
    confidence) and is the correct decision-maker for COMFORT vs GUIDANCE.
    C3 now only enforces the single hard safety constraint: CRISIS distress
    must route to CRISIS mode so hotlines are always delivered.
    Logged in GAPS.md as G-VS-C3-01 for Director review.
    """
    mode = context.mode
    distress = context.signals.distress_level

    if distress == DistressLevel.CRISIS and mode != OperationalMode.CRISIS:
        return (
            f"[C3/REQ-200-VS1] CRITICAL distress but mode='{mode.value}' — "
            "CRITICAL distress MUST route to CRISIS mode."
        )
    # HIGH distress in COMFORT or GUIDANCE is intentional — no check here.
    if distress == DistressLevel.LOW and mode == OperationalMode.CRISIS:
        return (
            f"[C3/REQ-200-VS1] NONE distress but mode='{mode.value}' — "
            "Crisis resources delivered to a non-distress input is a routing anomaly."
        )
    return None


def _c4_crisis_resources(
    context: ResponseContextPayload,
) -> Optional[str]:
    """
    C4 — Crisis resources present when CRITICAL (SPEC-300 §5).

    If the system identified CRITICAL distress and entered Crisis Mode, it MUST
    have populated crisis_resources. An empty list is also a failure — the
    pipeline must have at least one resource ready for delivery.
    """
    if (
        context.signals.distress_level == DistressLevel.CRISIS
        and not context.crisis_resources
    ):
        return (
            "[C4/SPEC-300§5] CRITICAL distress detected but crisis_resources "
            "is absent or empty — Crisis Mode MUST populate crisis resources."
        )
    return None


def _c5_evidence_pipeline(
    context: ResponseContextPayload,
) -> Optional[str]:
    """
    C5 — Evidence pipeline integrity in GUIDANCE mode (REQ-700-091).

    GUIDANCE mode MUST run evidence retrieval + synthesis (SPEC-700 Steps 7–8).
    A missing synthesized_evidence in GUIDANCE mode indicates a skipped step.

    Suspended in Crisis Mode (REQ-700-VS1).

    NOTE on the `is None` check (Director-confirmed 2026-05-23):
    `_steps4_7_guidance_evidence()` in pipeline.py NEVER returns None. It always
    returns a SynthesizedEvidence object — either populated with real retrieved
    evidence or with empty lists and a "respond from general clinical knowledge"
    instruction. The `is None` guard here is therefore a last-resort safety net
    for future code changes that might accidentally assign None. It does not fire
    in normal operation and is correct as written. Do not remove or widen it to
    catch empty SynthesizedEvidence — empty evidence is a valid, intentional state.
    (See Issue 3, Director-approved 2026-05-23.)
    """
    if (
        context.mode == OperationalMode.GUIDANCE
        and context.synthesized_evidence is None
    ):
        return (
            "[C5/REQ-700-091] GUIDANCE mode requires synthesized_evidence but "
            "it is None — evidence retrieval or synthesis step was skipped."
        )
    return None


def _c6_agent_contamination(
    context: ResponseContextPayload,
) -> Optional[str]:
    """
    C6 — Agent contamination check (REQ-700-091).

    Detects cross-agent data leakage:
      - COMFORT mode must not carry synthesized_evidence (evidence pipeline is
        skipped in Comfort Mode per SPEC-700).
      - GUIDANCE mode must not carry crisis_resources (crisis pathway not active).

    Suspended in Crisis Mode (REQ-700-VS1) — Crisis Mode legitimately may
    carry evidence from a prior GUIDANCE phase on de-escalation, and its own
    crisis_resources, so contamination semantics are ambiguous mid-crisis.
    """
    mode = context.mode
    if mode == OperationalMode.COMFORT and context.synthesized_evidence is not None:
        return (
            "[C6/REQ-700-091] COMFORT mode must not carry synthesized_evidence "
            "— evidence pipeline should not have run in this mode."
        )
    if mode == OperationalMode.GUIDANCE and context.crisis_resources:
        return (
            "[C6/REQ-700-091] GUIDANCE mode must not carry crisis_resources "
            "— crisis pathway was not activated for this request."
        )
    return None


def _c7_loop_limit(regen_count: int) -> Optional[str]:
    """
    C7 — Regeneration loop limit (REQ-200-170).

    Each agent MUST NOT iterate more than 2 times per request. If regen_count
    has already reached the limit, the VS blocks further regeneration and
    triggers the safe fallback response instead.

    This is the last line of defence against infinite loops in the pipeline.
    """
    if regen_count >= MAX_REGEN_ATTEMPTS:
        return (
            f"[C7/REQ-200-170] regen_count={regen_count} has reached the "
            f"maximum of {MAX_REGEN_ATTEMPTS}. Further regeneration is blocked. "
            "Safe fallback response will be emitted."
        )
    return None


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

class VerificationSupervisorAgent:
    """
    Structural pipeline gate — the final checkpoint before response delivery.

    Does NOT inspect response content (that is the Evaluator's role).
    Checks routing integrity, evidence-pipeline integrity, crisis-handling
    correctness, agent contamination, and loop-limit enforcement.

    Usage (within the pipeline orchestrator):
        vs = VerificationSupervisorAgent()
        result = vs.verify(context, evaluation, scope_decision, regen_count)
        if not result.passed:
            return result.safe_fallback_triggered, SAFE_FALLBACK_RESPONSE
    """

    def verify(
        self,
        context: ResponseContextPayload,
        evaluation: EvaluationPayload,
        scope_decision: ScopeClassifierDecision,
        regen_count: int = 0,
    ) -> VerificationResult:
        """
        Run all applicable structural checks and return a VerificationResult.

        Parameters
        ----------
        context : ResponseContextPayload
            The assembled pipeline context (mode, signals, strategy, evidence).
        evaluation : EvaluationPayload
            The Evaluator's verdict — must be PASS for VS to have been called.
        scope_decision : ScopeClassifierDecision
            The scope classifier's decision from STEP 0 — used to verify
            that routing logic respected the OUT_OF_SCOPE gate.
        regen_count : int
            Number of regeneration attempts already made for this request.
            0 on first pass; pipeline increments before re-calling VS.

        Spec trace
        ----------
        REQ-200-090  validate factual correctness / source reliability / SPEC-000 compliance
        REQ-200-VS1  structural gate scope
        REQ-700-090  final structural gate before output
        REQ-700-091  routing, evidence integrity, crisis handling, contamination
        REQ-700-092  on failure → safe fallback
        REQ-700-VS1  Crisis Mode: stripped VS (C5, C6 suspended)
        REQ-200-170  loop limit ≤ 2
        """
        distress = context.signals.distress_level

        # [CONCEPT] Crisis Mode stripping: when the user is in acute distress
        # (CRITICAL), we reduce the VS to the minimum safe checks. Evidence-
        # pipeline and contamination checks are suspended because speed and
        # safety-resource delivery take priority over structural purity.
        # This is a deliberate clinical safety trade-off, not a shortcut.
        crisis_mode_active = (distress == DistressLevel.CRISIS)

        logger.info(
            "VerificationSupervisorAgent.verify() — mode=%s distress=%s "
            "regen_count=%d crisis_mode_active=%s",
            context.mode.value,
            distress.value,
            regen_count,
            crisis_mode_active,
        )

        failures: list[str] = []

        # --- Always-active checks -------------------------------------------

        # C1: Evaluator gate — cannot have a non-PASS here legitimately
        if (reason := _c1_evaluator_gate(evaluation)):
            failures.append(reason)

        # C2: Scope routing — OUT_OF_SCOPE must have been deflected at Step 0
        if (reason := _c2_scope_routing(scope_decision)):
            failures.append(reason)

        # C3: Mode-distress alignment — mode must be consistent with signal
        if (reason := _c3_mode_distress_alignment(context)):
            failures.append(reason)

        # C4: Crisis resources — CRITICAL distress must carry resources
        if (reason := _c4_crisis_resources(context)):
            failures.append(reason)

        # C7: Loop limit — block if already at max regen attempts
        if (reason := _c7_loop_limit(regen_count)):
            failures.append(reason)

  
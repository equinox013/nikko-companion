"""
agents/router.py
================
Router (Traffic Controller) — Step 3 of the NIKKO pipeline.

Spec source  : SPEC-200 §5.1 and §6
               REQ-200-040 through REQ-200-042
               REQ-200-120 through REQ-200-132
               REQ-200-160 through REQ-200-162
               REQ-200-170 through REQ-200-172
Phase        : 3 — Agent Definitions (Implementation)
Authority    : MAXIMUM — sole authority to assign mode and initiate/terminate
               agent chains.

Role
----
Receives the Signal Agent's SignalPayload and assigns exactly one operational
mode for this turn: COMFORT, GUIDANCE, or CRISIS. The mode determines which
downstream agents run and what evidence/crisis resources are injected.

Design: pure deterministic logic
---------------------------------
The Router MUST NOT make an LLM call. (REQ-200-040) Every decision traces to
an explicit rule in SPEC-200 §6. This makes the Router the safest and most
auditable component in the pipeline — its behaviour is fully predictable and
testable without any model.

Why Pydantic for RouterDecision?
---------------------------------
The Router output travels to the Support Strategy Agent and the pipeline
orchestrator. Using a validated Pydantic model (rather than a plain dict)
means any field omission or type error surfaces immediately at the Router's
output boundary, not silently downstream.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, model_validator

from schemas.acp_schemas import DistressLevel, OperationalMode, SignalPayload
from schemas.validate import get_confidence_band

# ---------------------------------------------------------------------------
# Constants — routing thresholds (all locked, REQ-100-CB1, REQ-000-F01)
# ---------------------------------------------------------------------------

# Signal Agent confidence below this → Router MUST fall back to COMFORT.
# Matches the SPEC-100 low-band ceiling. (REQ-000-F01, REQ-100-CB1)
_LOW_CONFIDENCE_CEILING: float = 0.40

# Support need keys that indicate the user wants information/guidance,
# not just validation. Used to distinguish COMFORT from GUIDANCE.
_GUIDANCE_SUPPORT_NEEDS: frozenset[str] = frozenset({
    "psychoeducation",
    "normalization",
    "reflective_exploration",
    "encouragement_external_support",
})

# Behavioral indicator that directly signals guidance readiness.
_GUIDANCE_BEHAVIORAL_INDICATORS: frozenset[str] = frozenset({
    "help_seeking_behavior",
    "self_reflection_capacity",
})

# Risk key prefixes that unconditionally trigger CRISIS MODE.
# (REQ-200-124/125, REQ-100-060)
_CRISIS_PREFIXES: tuple[str, ...] = ("risk.active.", "risk.acute.")

# Passive risk prefix — does NOT alone trigger CRISIS, but must be flagged.
# (REQ-100-PR1: passive + distress >= high + >= 2 turns → escalate to L2)
_PASSIVE_PREFIX: str = "risk.passive."


# ---------------------------------------------------------------------------
# Router decision model
# ---------------------------------------------------------------------------

class RouterDecision(BaseModel):
    """
    Structured output of the Router. (SPEC-200 §5.1, REQ-200-040)

    This is not an ACP-Message — it is consumed directly by the pipeline
    orchestrator and the Support Strategy Agent. It is typed separately
    (like ScopeClassifierDecision) because it precedes the ACP envelope.

    Fields
    ------
    mode              : The assigned operational mode for this turn.
                        Exactly one mode per turn (REQ-200-122/123).
    routing_rationale : Human-readable explanation for audit traceability.
    confidence        : Inherited from the Signal Agent's payload confidence.
                        Downstream agents use this to calibrate their outputs.
    crisis_override   : True when mode=CRISIS. Always False otherwise.
                        Logged for audit traceability.
    passive_risk_flag : True when passive risk indicators are present, even
                        if mode is not CRISIS. Pipeline MUST track this across
                        turns for the L2 escalation rule. (REQ-100-PR1)
    attempt_count     : How many times the Router has been called for this
                        turn (1-based). Enforces the max-2-attempts rule.
                        (REQ-200-170)
    """
    mode:               OperationalMode
    routing_rationale:  str
    confidence:         float = Field(ge=0.0, le=1.0)
    crisis_override:    bool
    passive_risk_flag:  bool  = False
    attempt_count:      int   = Field(default=1, ge=1, le=2)

    @model_validator(mode="after")
    def crisis_override_matches_mode(self) -> "RouterDecision":
        """
        crisis_override MUST be True iff mode is CRISIS.
        (agent_prompts.md §2.3 output contract)
        """
        if self.mode == OperationalMode.CRISIS and not self.crisis_override:
            raise ValueError(
                "crisis_override must be True when mode=CRISIS. (agent_prompts.md §2.3)"
            )
        if self.mode != OperationalMode.CRISIS and self.crisis_override:
            raise ValueError(
                "crisis_override must be False when mode is not CRISIS."
            )
        return self


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

class Router:
    """
    Traffic Controller — pure deterministic mode assignment.

    No LLM call. No network access. No mutable state.
    All routing decisions trace to explicit REQ-IDs.

    Usage:
        router = Router()
        decision = router.route(signal_payload, attempt_count=1)
    """

    def route(
        self,
        signal:        SignalPayload,
        attempt_count: int = 1,
        force_guidance: bool = False,
    ) -> RouterDecision:
        """
        Assign exactly one operational mode for this turn.

        Rules are evaluated in strict priority order — the first matching
        rule wins and no further rules are checked. This mirrors the
        deterministic, non-negotiable nature of the routing contract.

        Args:
            signal:        Validated SignalPayload from the Signal Agent.
                           MUST NOT be None. (REQ-200-121)
            attempt_count: 1 on first call; 2 on retry. Values > 2 are
                           rejected — the pipeline must not call route()
                           more than twice per turn. (REQ-200-170)

        Returns:
            RouterDecision — validated, with rationale and flags.

        Raises:
            ValueError: If attempt_count > 2 (loop limit exceeded).
        """
        # --- Loop limit guard (REQ-200-170) ---
        if attempt_count > 2:
            raise ValueError(
                f"Router called {attempt_count} times for this turn — exceeds the "
                f"maximum of 2 re-execution attempts. (REQ-200-170) "
                f"The pipeline must fall back to a safe response."
            )

        # Pre-compute risk flags — used in multiple rules below.
        has_active_or_acute = self._has_active_or_acute_risk(signal.risk_indicators)
        has_passive          = self._has_passive_risk(signal.risk_indicators)
        distress_is_crisis   = signal.distress_level == DistressLevel.CRISIS

        # --- Rule 1: CRISIS — active/acute risk (REQ-200-124/125, REQ-100-060) ---
        # This check MUST run first. No other condition can override it — including
        # the force_guidance flag from a \guide command. Safety is non-negotiable.
        # "Any active or acute risk indicator MUST trigger crisis flow."
        if has_active_or_acute:
            return self._make_decision(
                mode=OperationalMode.CRISIS,
                rationale=(
                    f"CRISIS: active/acute risk indicator(s) detected: "
                    f"{[k for k in signal.risk_indicators if k.startswith(_CRISIS_PREFIXES)]}. "
                    f"(REQ-200-124, REQ-100-060)"
                ),
                signal=signal,
                passive_risk_flag=has_passive,
                attempt_count=attempt_count,
            )

        # --- Rule 2: CRISIS — distress_level=crisis without explicit risk key ---
        # The Signal Agent may set distress_level=crisis based on context even
        # without a specific risk key (e.g., ambiguous acute phrasing). Honour it.
        if distress_is_crisis:
            return self._make_decision(
                mode=OperationalMode.CRISIS,
                rationale=(
                    "CRISIS: distress_level=crisis set by Signal Agent without explicit "
                    "active/acute key — treating as crisis per safety doctrine. "
                    "(REQ-200-125, SPEC-000 §6)"
                ),
                signal=signal,
                passive_risk_flag=has_passive,
                attempt_count=attempt_count,
            )

        # --- Rule 2.5: GUIDANCE — explicit user intent via \guide command (REQ-200-163) ---
        # [REQ-200-163] When the user prefixes their message with \guide (or /guide),
        # the pipeline sets force_guidance=True as a high-confidence explicit intent
        # signal. The Router MUST honour it by assigning GUIDANCE, subject to:
        #   - Rules 1 and 2 (CRISIS) always take priority — non-negotiable.
        #   - The low-confidence fallback (Rule 3) is bypassed: the user's explicit
        #     intent is a more reliable signal than the keyword engine's confidence.
        # Spec trace: SPEC-200 §6 Rule 2.5 (Director-approved 2026-05-23).
        # GAPS.md: G-GUIDE-01 documents the SPEC-200 amendment.
        if force_guidance:
            return self._make_decision(
                mode=OperationalMode.GUIDANCE,
                rationale=(
                    "GUIDANCE: user explicitly requested guidance mode via \\guide command. "
                    "force_guidance=True overrides confidence fallback. "
                    "(REQ-200-163, SPEC-200 §6 Rule 2.5)"
                ),
                signal=signal,
                passive_risk_flag=has_passive,
                attempt_count=attempt_count,
            )

        # --- Rule 3: COMFORT fallback — low signal confidence (REQ-000-F01) ---
        # If the Signal Agent is uncertain, we cannot safely assign GUIDANCE.
        # COMFORT is the conservative default: validation-only, no evidence injection.
        # Note: confidence < 0.40 puts us in the low band (REQ-100-CB1).
        band = get_confidence_band(signal.confidence)
        if band.fallback:
            return self._make_decision(
                mode=OperationalMode.COMFORT,
                rationale=(
                    f"COMFORT (fallback): Signal Agent confidence {signal.confidence:.2f} "
                    f"is in the low band (< 0.40). Evidence chains suppressed. "
                    f"(REQ-000-F01, REQ-100-CB2)"
                ),
                signal=signal,
                passive_risk_flag=has_passive,
                attempt_count=attempt_count,
            )

        # --- Rule 4: GUIDANCE — user shows readiness for information ---
        # GUIDANCE is appropriate when the user's expressed support needs or
        # behavioural indicators signal that they want information, not just
        # validation. Crisis flow is ruled out by Rules 1-2 above.
        #
        # Confidence-and-distress gating (Issues 1 + 2, Director-approved 2026-05-23):
        #
        # STRONG intent (BOTH support_needs AND behavioral_indicators fire):
        #   → GUIDANCE at any confidence, any distress level.
        #   Rationale: two independent signal types converging on guidance intent
        #   is high-fidelity evidence the user wants information, not just support.
        #
        # WEAK intent (EITHER fires, but not both):
        #   → GUIDANCE only if distress < HIGH AND confidence ≥ 0.60.
        #   Rationale: a single ambiguous signal ("I don't know how to cope" looks
        #   like help_seeking but is often venting) should NOT override COMFORT when
        #   the user is in high distress OR when the signal engine is uncertain.
        #   High distress + single intent signal = emotional need dominates → COMFORT.
        #   Low confidence + single intent signal = unreliable → COMFORT.
        #
        # NONE: fall through to Rule 5 (COMFORT default).
        intent_strength = self._guidance_intent_strength(signal)
        band = get_confidence_band(signal.confidence)

        if intent_strength == "strong":
            return self._make_decision(
                mode=OperationalMode.GUIDANCE,
                rationale=(
                    f"GUIDANCE: strong guidance intent — both support_needs and "
                    f"behavioral_indicators match. Distress={signal.distress_level.value}, "
                    f"confidence={signal.confidence:.2f}. Evidence retrieval active."
                ),
                signal=signal,
                passive_risk_flag=has_passive,
                attempt_count=attempt_count,
            )

        if intent_strength == "weak":
            distress_permits = signal.distress_level != DistressLevel.HIGH
            confidence_permits = signal.confidence >= 0.60
            if distress_permits and confidence_permits:
                return self._make_decision(
                    mode=OperationalMode.GUIDANCE,
                    rationale=(
                        f"GUIDANCE: weak guidance intent — single signal match, but "
                        f"distress={signal.distress_level.value} (< HIGH) and "
                        f"confidence={signal.confidence:.2f} (≥ 0.60) permit routing. "
                        f"Evidence retrieval active."
                    ),
                    signal=signal,
                    passive_risk_flag=has_passive,
                    attempt_count=attempt_count,
                )
            # Weak intent blocked — log the specific reason for auditability.
            _blocked_reason = []
            if not distress_permits:
                _blocked_reason.append(f"distress={signal.distress_level.value} (HIGH suppresses weak intent)")
            if not confidence_permits:
                _blocked_reason.append(f"confidence={signal.confidence:.2f} (< 
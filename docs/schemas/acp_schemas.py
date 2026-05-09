"""
docs/schemas/acp_schemas.py
============================
Pydantic v2 contracts for all ACP-Message types in the NIKKO system.

Spec source : SPEC-200 (Agent Communication Protocol)
Requirements: REQ-200-030 through REQ-200-037, REQ-200-SC1/SC2,
              REQ-200-VS1, REQ-200-EV1, REQ-850-083 (USM audit field)
Status      : Phase 2 — Architectural Contracts (no implementation code)
Last reviewed: 2026-05-09

Usage note
----------
These schemas define the *contract*, not the runtime. They are the
authoritative reference for Phase 3 implementers. Any field addition,
removal, or type change requires a SPEC-200 revision and a new REQ ID.

Validation rules encoded here:
- message_id must be UUID v4              (REQ-200-031)
- source/target_agent must be roster keys  (REQ-200-032)
- timestamp must be UTC ISO-8601           (REQ-200-033)
- payload_type must be an enumerated value (REQ-200-034)
- confidence must be float in [0.0, 1.0]  (REQ-200-035)
- priority must be an enumerated value     (REQ-200-036)
- Malformed messages must be rejected      (REQ-200-037)
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Literal, Optional, Union
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class AgentName(str, Enum):
    """
    Canonical agent roster. Values MUST match the GLOSSARY agent roster.
    (REQ-200-032)
    """
    SCOPE_CLASSIFIER          = "scope_classifier"
    ROUTER                    = "router"
    SIGNAL_AGENT              = "signal_agent"
    SUPPORT_STRATEGY_AGENT    = "support_strategy_agent"
    EVIDENCE_RETRIEVAL_AGENT  = "evidence_retrieval_agent"
    EVIDENCE_SYNTHESIZER      = "evidence_synthesizer"
    VERIFICATION_SUPERVISOR   = "verification_supervisor"
    EVALUATOR                 = "evaluator"
    INTERACTION_MODEL         = "interaction_model"


class PayloadType(str, Enum):
    """
    Enumerated payload types. (REQ-200-034)
    Exactly five values are permitted — no extensions without a SPEC-200 revision.
    """
    SIGNAL           = "signal"
    EVIDENCE         = "evidence"
    STRATEGY         = "strategy"
    EVALUATION       = "evaluation"
    RESPONSE_CONTEXT = "response_context"


class Priority(str, Enum):
    """
    Message priority levels. (SPEC-200 §7, REQ-200-140)
    CRITICAL messages must preempt all workflows.
    """
    LOW      = "low"
    MEDIUM   = "medium"
    HIGH     = "high"
    CRITICAL = "critical"


class DistressLevel(str, Enum):
    """
    Canonical distress levels. (SPEC-100 §9, REQ-100-092)
    Crosswalk: low=L0, moderate=L1, high=L2, crisis=L3 (GLOSSARY).
    """
    LOW      = "low"
    MODERATE = "moderate"
    HIGH     = "high"
    CRISIS   = "crisis"


class OperationalMode(str, Enum):
    """
    Router output modes. Mutually exclusive within a single turn.
    (SPEC-200 Rule 2, REQ-200-122/123)
    """
    COMFORT  = "comfort"
    GUIDANCE = "guidance"
    CRISIS   = "crisis"


class ScopeDecision(str, Enum):
    """
    Scope Classifier verdict. (SPEC-200 §5.0, REQ-200-SC2)
    IN_SCOPE and AMBIGUOUS both route to the Signal Agent.
    OUT_OF_SCOPE terminates the pipeline and returns a warm redirect.
    """
    IN_SCOPE     = "IN_SCOPE"
    AMBIGUOUS    = "AMBIGUOUS"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


class EvaluationVerdict(str, Enum):
    """
    Evaluator pass/fail/regenerate outcome. (SPEC-200 §5.7, REQ-200-100)
    """
    PASS        = "pass"
    FAIL        = "fail"
    REGENERATE  = "regenerate"


class ACKStatus(str, Enum):
    """
    Acknowledgement status values. (SPEC-200 §8, REQ-200-150)
    """
    RECEIVED   = "received"
    PROCESSING = "processing"
    REJECTED   = "rejected"


class SourceTier(str, Enum):
    """
    Evidence source tiers per approved source list. (SPEC-200 §5.4, REQ-200-071)
    """
    PRIMARY   = "primary"
    SECONDARY = "secondary"


class EvidenceTier(str, Enum):
    """
    Evidence quality tier for tiebreak logic. (REQ-200-ER1/ER2/ER3)
    When grey_literature is used, Synthesizer SHOULD reduce confidence.
    """
    PEER_REVIEWED    = "peer_reviewed"
    GREY_LITERATURE  = "grey_literature"


# ---------------------------------------------------------------------------
# Confidence validator (shared across multiple models)
# ---------------------------------------------------------------------------

ConfidenceFloat = Annotated[float, Field(ge=0.0, le=1.0)]
"""
Float constrained to [0.0, 1.0]. (REQ-200-035, REQ-100-091)
Confidence bands:
  low      < 0.40  — triggers fallback (REQ-100-CB1/CB2)
  moderate   0.40–0.70
  high     > 0.70
"""


# ---------------------------------------------------------------------------
# Payload models
# ---------------------------------------------------------------------------

class SignalPayload(BaseModel):
    """
    Output of the Psychological Signal Agent. (SPEC-100 §9, REQ-100-090)
    payload_type must be PayloadType.SIGNAL when this model is used.

    All array elements must resolve to keys in docs/schemas/signal_enum.json.
    (REQ-100-093)
    """
    payload_type:          Literal[PayloadType.SIGNAL] = PayloadType.SIGNAL
    distress_level:        DistressLevel
    emotional_states:      list[str]         = Field(default_factory=list)
    cognitive_patterns:    list[str]         = Field(default_factory=list)
    behavioral_indicators: list[str]         = Field(default_factory=list)
    risk_indicators:       list[str]         = Field(default_factory=list)
    support_needs:         list[str]         = Field(default_factory=list)
    confidence:            ConfidenceFloat
    uncertainty_notes:     str               = ""

    class Config:
        # Phase 3 implementers: validate risk_indicator values against
        # signal_enum.json["risk_indicators"] before emitting this payload.
        # Validation is not enforced here to keep schemas dependency-free.
        pass


class EvidenceItem(BaseModel):
    """
    A single retrieved evidence record. (SPEC-200 §5.4)
    Produced by retrieval adapters; consumed by the Synthesizer.
    Immutable once retrieved — see REQ-200-126.
    """
    title:            str
    abstract:         str
    url:              str
    source_name:      str
    publication_date: Optional[str]  = None   # ISO-8601 date string; None if unavailable
    evidence_tier:    EvidenceTier
    source_tier:      SourceTier
    cache_hit:        bool           = False
    retrieved_at:     datetime


class EvidencePayload(BaseModel):
    """
    Output of the Evidence Retrieval Agent. (SPEC-200 §5.4, REQ-200-070)
    payload_type must be PayloadType.EVIDENCE when this model is used.

    Evidence is immutable once this payload is emitted. (REQ-200-126)
    Only the Synthesizer may transform it. (REQ-200-127)
    The Evaluator may reject it but MUST NOT alter it. (REQ-200-128)
    """
    payload_type:        Literal[PayloadType.EVIDENCE] = PayloadType.EVIDENCE
    query:               str
    source_name:         str
    source_tier:         SourceTier
    results:             list[EvidenceItem]
    grey_literature_flag: bool = Field(
        default=False,
        description=(
            "True when results contain grey-literature fallback items. "
            "Synthesizer SHOULD reduce confidence score when this is True. "
            "(REQ-200-ER3)"
        ),
    )


class StrategyPayload(BaseModel):
    """
    Output of the Support Strategy Agent. (SPEC-200 §5.3, REQ-200-060/061)
    payload_type must be PayloadType.STRATEGY when this model is used.
    """
    payload_type:        Literal[PayloadType.STRATEGY] = PayloadType.STRATEGY
    mode:                OperationalMode
    distress_level:      DistressLevel
    tone_guidance:       str
    framing_strategy:    str
    response_constraints: list[str] = Field(default_factory=list)


class SynthesizedEvidence(BaseModel):
    """
    Consolidated evidence package produced by the Evidence Synthesizer.
    Embedded inside ResponseContextPayload; not transmitted as a standalone
    ACP-Message payload.
    """
    summary:               str
    citations:             list[EvidenceItem]
    confidence:            ConfidenceFloat
    grey_literature_used:  bool = False
    source_disagreement:   bool = False
    disagreement_note:     Optional[str] = None


class CrisisResource(BaseModel):
    """
    A single crisis support resource. (SPEC-300 §5, G-CRISIS-03 ratification)
    Baseline set is always shown; demographic-specific set is in expandable.
    """
    name:     str
    number:   str
    tier:     Literal["baseline", "demographic_specific"]
    audience: Optional[str] = None  # e.g., "First Nations", "LGBTQ+", "Under 18"


class EvaluationPayload(BaseModel):
    """
    Output of the Evaluator Model. (SPEC-200 §5.7, REQ-200-100/101, REQ-200-EV1)
    payload_type must be PayloadType.EVALUATION when this model is used.

    The Evaluator runs BEFORE the Verification Supervisor.
    Both must pass for a response to be delivered. (REQ-200-EV1)

    usm_audit_passed: required when USM content was injected in the current turn.
    The Evaluator MUST verify the response does not reference crisis-state history
    from memory, make clinical inferences from memory, or position Nikko as a
    continuous care provider based on memory continuity. (REQ-850-083)
    """
    payload_type:       Literal[PayloadType.EVALUATION] = PayloadType.EVALUATION
    verdict:            EvaluationVerdict
    safety_check:       bool
    tone_check:         bool
    hallucination_check: bool
    rejection_reasons:  list[str] = Field(default_factory=list)
    usm_audit_passed:   Optional[bool] = Field(
        default=None,
        description=(
            "None when no USM content was injected. "
            "True/False when USM was active — Evaluator MUST audit per REQ-850-083. "
            "A False value here MUST produce verdict=REGENERATE or FAIL."
        ),
    )

    @model_validator(mode="after")
    def usm_failure_forces_non_pass(self) -> "EvaluationPayload":
        """
        If the USM audit failed, the overall verdict cannot be PASS.
        (REQ-850-083 — crisis-adjacent content in injection must be caught.)
        """
        if self.usm_audit_passed is False and self.verdict == EvaluationVerdict.PASS:
            raise ValueError(
                "usm_audit_passed=False is incompatible with verdict=PASS. "
                "Set verdict to REGENERATE or FAIL. (REQ-850-083)"
            )
        return self


class ResponseContextPayload(BaseModel):
    """
    The assembled context package delivered to the Interaction Model.
    (SPEC-200 §5.8, REQ-200-110)
    payload_type must be PayloadType.RESPONSE_CONTEXT when this model is used.

    The Interaction Model receives ONLY this synthesized context — never raw
    retrieval outputs. (REQ-200-129/130)

    usm_active: True when a USM memory file is loaded in the current session.
    Memory content is injected separately into the system prompt (REQ-850-070);
    this flag tells the Interaction Model to apply USM framing constraints
    (REQ-850-073/074).
    """
    payload_type:       Literal[PayloadType.RESPONSE_CONTEXT] = PayloadType.RESPONSE_CONTEXT
    mode:               OperationalMode
    signals:            SignalPayload
    strategy:           StrategyPayload
    synthesized_evidence: Optional[SynthesizedEvidence] = Field(
        default=None,
        description="None in Comfort Mode or Crisis Mode where evidence retrieval is skipped.",
    )
    crisis_resources:   Optional[list[CrisisResource]] = Field(
        default=None,
        description="Populated only in Crisis Mode. (SPEC-300 §5)",
    )
    usm_active:         bool = Field(
        default=False,
        description=(
            "True when a USM memory file is loaded in this session. "
            "Signals the Interaction Model to apply memory framing constraints. "
            "(REQ-850-073/074)"
        ),
    )


# ---------------------------------------------------------------------------
# Discriminated union over all payload types
# ---------------------------------------------------------------------------

AnyPayload = Union[
    SignalPayload,
    EvidencePayload,
    StrategyPayload,
    EvaluationPayload,
    ResponseContextPayload,
]
"""
Discriminated union on the payload_type Literal field.
Pydantic will select the correct model automatically when deserializing.
(REQ-200-034)
"""


# ---------------------------------------------------------------------------
# Base ACP-Message envelope
# ---------------------------------------------------------------------------

class ACPMessage(BaseModel):
    """
    Standard inter-agent message envelope. (SPEC-200 §4, REQ-200-030)

    All inter-agent communication MUST use this schema. (REQ-200-012)
    Free-form agent-to-agent messaging is prohibited. (REQ-200-013)
    Malformed messages MUST be rejected by the target agent and logged.
    (REQ-200-037)
    """
    message_id:   UUID                              # REQ-200-031: UUID v4
    source_agent: AgentName                         # REQ-200-032
    target_agent: AgentName                         # REQ-200-032
    timestamp:    datetime                          # REQ-200-033: UTC ISO-8601
    intent:       str
    payload_type: PayloadType                       # REQ-200-034
    payload:      AnyPayload                        # discriminated on payload_type
    confidence:   ConfidenceFloat                   # REQ-200-035
    priority:     Priority                          # REQ-200-036
    requires_ack: bool

    @field_validator("timestamp")
    @classmethod
    def timestamp_must_be_utc(cls, v: datetime) -> datetime:
        """Enforce UTC timezone on all timestamps. (REQ-200-033)"""
        if v.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC). (REQ-200-033)")
        return v.astimezone(timezone.utc)

    @model_validator(mode="after")
    def payload_type_matches_payload(self) -> "ACPMessage":
        """
        The payload_type field must match the actual payload model's
        own payload_type discriminator. (REQ-200-034)
        """
        expected = self.payload_type.value
        actual   = getattr(self.payload, "payload_type", None)
        if actual is None or actual.value != expected:
            raise ValueError(
                f"payload_type mismatch: envelope declares '{expected}' "
                f"but payload model carries '{actual}'. (REQ-200-034)"
            )
        return self


# ---------------------------------------------------------------------------
# ACK message
# ---------------------------------------------------------------------------

class ACKMessage(BaseModel):
    """
    Acknowledgement response for messages with requires_ack=True.
    (SPEC-200 §8, REQ-200-150/151)

    Missing ACK must trigger retry or reroute, subject to loop limits
    in SPEC-200 §10. (REQ-200-151)
    """
    original_message_id: UUID
    source_agent:        AgentName
    target_agent:        AgentName
    timestamp:           datetime
    status:              ACKStatus
    rejection_reason:    Optional[str] = Field(
        default=None,
        description="Required when status=REJECTED. Reason must be logged. (REQ-200-037)",
    )

    @model_validator(mode="after")
    def rejection_requires_reason(self) -> "ACKMessage":
        if self.status == ACKStatus.REJECTED and not self.rejection_reason:
            raise ValueError(
                "ACKStatus.REJECTED requires a rejection_reason. (REQ-200-037)"
            )
        return self


# ---------------------------------------------------------------------------
# Scope Classifier decision (pre-Router gate)
# ---------------------------------------------------------------------------

class ScopeClassifierDecision(BaseModel):
    """
    Structured output of the Scope Classifier. (SPEC-200 §5.0, REQ-200-SC1/SC2)

    This is not an ACP-Message — it is emitted before the Router and does not
    travel through the standard envelope. It is typed separately to enforce
    REQ-200-SC2 (three-outcome constraint) and REQ-200-SC3 (asymmetric error
    policy: AMBIGUOUS preferred over OUT_OF_SCOPE on low confidence).

    Authority level: HIGH. OUT_OF_SCOPE decision is final and cannot be
    overridden by downstream agents. (REQ-200-SC6)
    """
    decision:      ScopeDecision
    confidence:    ConfidenceFloat
    warm_redirect: Optional[str] = Field(
        default=None,
        description=(
            "Populated only when decision=OUT_OF_SCOPE. "
            "MUST use the verbatim template from REQ-200-SC4 or a close variant. "
            "MUST NOT be LLM-generated. (REQ-200-SC5)"
        ),
    )

    @model_validator(mode="after")
    def out_of_scope_requires_redirect(self) -> "ScopeClassifierDecision":
        if self.decision == ScopeDecision.OUT_OF_SCOPE and not self.warm_redirect:
            raise ValueError(
                "decision=OUT_OF_SCOPE requires a warm_redirect message. (REQ-200-SC4)"
            )
        return self

    @model_validator(mode="after")
    def low_confidence_must_not_be_out_of_scope(self) -> "ScopeClassifierDecision":
        """
        Asymmetric error policy: when confidence < 0.40, classifier MUST
        default to AMBIGUOUS, not OUT_OF_SCOPE. (REQ-200-SC3, REQ-100-CB1)
        """
        if self.confidence < 0.40 and self.decision == ScopeDecision.OUT_OF_SCOPE:
            raise ValueError(
                "Confidence < 0.40 (low band): classifier must emit AMBIGUOUS, "
                "not OUT_OF_SCOPE. Asymmetric error policy requires erring toward "
                "inclusion. (REQ-200-SC3)"
            )
        return self

---
id: SPEC-100
title: Psychological Signal Ontology
status: authoritative
supersedes: [SPEC-002]
depends_on: [SPEC-000]
version: 1.0.0-draft
last_reviewed: 2026-05-08
---

# SPEC-100 — Psychological Signal Ontology

## Status

- **Authoritative Ontology Specification.**
- Dependent on: [SPEC-000](./SPEC-000-charter.md).
- Supersedes the higher-level SPEC-002 sketch in the original NIKKO-spec.docx.

## 1. Purpose

[REQ-100-001] SPEC-100 MUST define the structured representation of psychological signals detected in user language.

The ontology enables Nikko to:

- interpret emotional context safely,
- route conversations appropriately,
- provide supportive responses,
- avoid diagnostic reasoning.

[REQ-100-002] Signals SHALL represent **observable linguistic patterns**, NOT mental disorders.

## 2. Core Design Principle

[REQ-100-010] Nikko MUST NOT detect conditions.

[REQ-100-011] Nikko SHALL detect: patterns of expression associated with human distress, coping, and support needs.

[REQ-100-012] All signals SHALL be: descriptive, probabilistic, non-clinical, reversible, and context-dependent.

## 3. Ontology Structure

[REQ-100-020] Each detected signal SHALL belong to one of four hierarchical layers:

```
Psychological Signal
├── Emotional State
├── Cognitive Pattern
├── Behavioral Indicator
└── Risk Indicator
```

[REQ-100-021] Signals MAY coexist and MUST NEVER be treated as mutually exclusive.

## 4. Emotional State Signals

Represents expressed affect. Categories:

### 4.1 Sadness Spectrum
- low mood language
- emotional heaviness
- grief expression
- loss-oriented statements

### 4.2 Anxiety Spectrum
- worry language
- anticipatory fear
- hypervigilance
- overwhelm signals

### 4.3 Emotional Dysregulation
- rapid emotional shifts
- intensity escalation
- inability to self-soothe

### 4.4 Shame / Self-Worth Disturbance
- self-criticism
- perceived burden language
- worthlessness framing

### 4.5 Emotional Numbness
- detachment language
- emptiness statements
- reduced emotional vocabulary

[REQ-100-030] Implementations MUST emit emotional-state values from the enumerated set above. New values SHALL require a SPEC-100 revision.

> **[GAP-G-ENUM-01]** The source spec lists categories but provides no canonical machine-readable enum (e.g., string keys for the JSON contract). A reference enum file is required before implementation. See `GAPS.md`.

## 5. Cognitive Pattern Signals

Represents thinking styles present in language. Recognised patterns:

- rumination loops
- catastrophizing
- black-and-white thinking
- hopeless future projection
- personalization bias
- negative core beliefs
- helplessness framing
- meaninglessness expressions

[REQ-100-040] These signals MUST inform support strategy only; they MUST NOT be interpreted as evidence of illness.

## 6. Behavioral Indicator Signals

Represents described actions or tendencies:

- withdrawal / isolation
- avoidance behavior
- sleep disruption references
- appetite change references
- loss of motivation
- coping attempts
- help-seeking behavior
- self-reflection capacity

[REQ-100-050] Behavioral indicators SHALL be used to determine readiness for guidance.

## 7. Risk Indicator Signals

Highest-priority detection layer.

### 7.1 Passive Risk Indicators
- wishing to disappear
- fatigue with living
- indirect death references

### 7.2 Active Risk Indicators
- suicidal ideation language
- self-harm references
- preparation statements
- farewell framing

### 7.3 Acute Crisis Indicators
- intent language
- immediacy statements
- loss of safety framing

[REQ-100-060] Any Active or Acute risk indicator MUST trigger the escalation policies defined in [SPEC-000 §6](./SPEC-000-charter.md#6-safety-escalation-doctrine) and [SPEC-300](./SPEC-300-crisis-response-protocol.md).

[REQ-100-061] Passive risk indicators in combination with high distress SHOULD trigger Level-2 escalation handling. Single passive indicators MAY remain at Level 1 with elevated monitoring.

> **[PROPOSED-RECONCILIATION:** the source spec does not specify the threshold combination that elevates passive indicators. The above SHOULD-rule is a proposed default to ensure passive ideation is not silently dismissed. **]** See [G-RECON-03](../GAPS.md).

## 8. Support Need Inference Layer

Signals combine to infer support needs.

[REQ-100-070] Support needs MUST NOT be diagnoses.

### 8.1 Valid support needs

- emotional validation
- grounding and stabilization
- psychoeducation
- normalization
- reflective exploration
- encouragement toward external support
- crisis escalation

[REQ-100-080] Multiple support needs MAY coexist for a single user turn.

## 9. Signal Representation Schema

[REQ-100-090] All signals MUST conform to the following structured output:

```json
{
  "distress_level": "low | moderate | high | crisis",
  "emotional_states": ["string"],
  "cognitive_patterns": ["string"],
  "behavioral_indicators": ["string"],
  "risk_indicators": ["string"],
  "support_needs": ["string"],
  "confidence": 0.0,
  "uncertainty_notes": ""
}
```

[REQ-100-091] `confidence` MUST be a float in the closed interval `[0.0, 1.0]`.
[REQ-100-092] `distress_level` MUST be one of the four enumerated string values; any other value SHALL be rejected by the Router and logged as a malformed signal.
[REQ-100-093] Each array element MUST resolve to a key in the canonical signal enum (see [GAP-G-ENUM-01](../GAPS.md)).

> **[PROPOSED-RECONCILIATION:** the source provides two near-identical JSON contracts (in SPEC-002 and SPEC-100). The SPEC-100 schema is canonical. Implementations SHALL NOT use the older SPEC-002 schema. **]**

## 10. Confidence and Uncertainty Model

[REQ-100-100] Confidence SHALL reflect linguistic-evidence strength only, NOT psychological certainty.

### 10.1 Rules

[REQ-100-101] Confidence MUST remain probabilistic.
[REQ-100-102] Absence of signal SHALL NOT be treated as absence of distress.
[REQ-100-103] Uncertainty MUST be explicitly tracked in the `uncertainty_notes` field.
[REQ-100-104] Low confidence MUST result in softer conversational assumptions in the downstream Support Strategy Agent.

> **[GAP-G-THRESH-02]** "Low" confidence is not numerically defined. Recommended default: `confidence < 0.40` is "low"; `0.40–0.70` is "moderate"; `>0.70` is "high". To be ratified by the Director.

## 11. Non-Diagnostic Enforcement

The ontology MUST NEVER:

[REQ-100-110] map signals directly to DSM diagnoses,
[REQ-100-111] infer mental disorders,
[REQ-100-112] label users clinically,
[REQ-100-113] output disorder names as conclusions.

### 11.1 Allowed phrasing patterns

- "some people experiencing similar feelings…"
- "you mentioned signs that *can sometimes be associated with*…"

### 11.2 Prohibited phrasing patterns

[REQ-100-114] The Interaction Model MUST NOT emit text matching diagnostic templates such as:
- "you have depression"
- "this indicates anxiety disorder"
- "you are showing signs of [disorder name]"

## 12. Temporal Awareness

[REQ-100-120] The system MUST consider conversational history when emitting signals.

[REQ-100-121] The system MUST track:
- escalation trends,
- improvement trends,
- repeated patterns,
- sudden emotional shifts.

[REQ-100-122] Single-message interpretation SHALL NOT be sufficient for crisis-level classification when prior turns suggest otherwise.

> **[GAP-G-MEMORY-01]** SPEC-100 §12 mandates conversational history but no spec defines the conversation-state store, retention, encryption, or privacy posture. This is a load-bearing gap. See `GAPS.md`.

## 13. Cultural & Linguistic Sensitivity

[REQ-100-130] Signal detection MUST remain adaptable across:
- cultural communication styles,
- indirect emotional expression,
- humour masking distress,
- neurodivergent communication patterns.

[REQ-100-131] When ambiguity is detected, the `confidence` value MUST be reduced and `uncertainty_notes` MUST capture the ambiguity reason.

## 14. Interaction with Other Specifications

[REQ-100-140] SPEC-100 outputs SHALL feed:
- [SPEC-200 — Routing Controller](./SPEC-200-agent-communication-protocol.md),
- [SPEC-006 — Support Strategy Agent](./SPEC-200-agent-communication-protocol.md#53-support-strategy-agent),
- [SPEC-008 — Safety Evaluation Loop](./SPEC-200-agent-communication-protocol.md#57-evaluator-model).

[REQ-100-141] No downstream component MAY reinterpret signals outside the ontology definitions in this spec.

## 15. Evaluation Requirements

[REQ-100-150] Signal-detection performance MUST be evaluated on:
- false crisis-detection rate,
- missed risk-detection rate,
- over-pathologizing rate,
- empathy-alignment correlation.

[REQ-100-151] Safety SHALL prioritize minimizing missed-crisis-signal rate over false positives.

> **[GAP-G-METRIC-01]** Numeric thresholds for these rates are not defined. Director ruling required (e.g., missed-crisis-rate ≤ 0.5%? ≤ 0.1%?). See `GAPS.md`.

## 16. Ethical Rationale

Psychological signals enable Nikko to respond compassionately, remain non-clinical, avoid diagnostic authority, and maintain ethical digital-health boundaries.

> *The ontology exists to understand expression, not define identity.*

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

[REQ-100-PR1] Passive risk indicator + distress_level >= high (Level 2) + repetition across >= 2 turns = escalate to Level 2. A single isolated passive indicator at lower distress levels does NOT trigger escalation. If additional explicit active/acute risk signals are present, escalate directly to Level 3.
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

### 9.1 `uncertainty_notes` Tagging Convention

[REQ-100-094] When the Structural Signal Pre-Analysis pass (see [SPEC-700 §4 Step 1.5](./SPEC-700-execution-pipeline.md)) detects structural or paralinguistic observations, they MUST be encoded in `uncertainty_notes` using the following prefixes:

- `[STRUCT: <tag>]` — structural signal observation (message length, register shift, fragmentation)
- `[PARA: <tag>]` — paralinguistic signal observation (typing convention, affect marker)

Multiple tags MAY appear in a single `uncertainty_notes` string, space-separated and preceding any free-text reasoning prose. Tags MUST use snake_case identifiers drawn from the canonical enums defined in §16.

> *Example:* `[STRUCT: register_collapse] [PARA: tone_softener] message length dropped from avg 3 sentences to 4 words; lol appended to isolation disclosure`

[REQ-100-095] The presence of one or more `[PARA:]` or `[STRUCT:]` tags in `uncertainty_notes` SHALL be treated as supplementary signal evidence by the Support Strategy Agent. Tags MUST NOT override the primary distress classification; they MAY increase the effective weight of co-present `risk_indicators` or `emotional_states`.

[REQ-100-096] Tags MUST be machine-parseable using the pattern `\[(STRUCT|PARA):\s*[a-z_]+\]`. Any tag not matching this pattern SHALL be treated as free-text prose and ignored by downstream structured parsers.

## 10. Confidence and Uncertainty Model

[REQ-100-100] Confidence SHALL reflect linguistic-evidence strength only, NOT psychological certainty.

### 10.1 Rules

[REQ-100-101] Confidence MUST remain probabilistic.
[REQ-100-102] Absence of signal SHALL NOT be treated as absence of distress.
[REQ-100-103] Uncertainty MUST be explicitly tracked in the `uncertainty_notes` field.
[REQ-100-104] Low confidence MUST result in softer conversational assumptions in the downstream Support Strategy Agent.

> **[GAP-G-THRESH-02]** "Low" confidence is not numerically defined. Recommended default: `confidence < 0.40` is "low"; `0.40–0.70` is "moderate"; `>0.70` is "high". To be ratified by the Director.

[REQ-100-CB1] Confidence bands are defined as follows and apply uniformly across all agents that emit a confidence score:
- **low:** confidence < 0.40
- **moderate:** 0.40 ≤ confidence ≤ 0.70
- **high:** confidence > 0.70

[REQ-100-CB2] When confidence < 0.40 (low), the system MUST NOT proceed with a confidence-dependent routing decision and MUST fall back to the next-safer mode. See [SPEC-000 §10](./SPEC-000-charter.md#10-failure-handling-policy).

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

[REQ-100-MC1] The missed-crisis signal rate MUST NOT exceed 0.5% on the standard crisis test suite during Phase 6 evaluation. This target may be tightened with Director approval. Zero-tolerance is statistically unachievable; 0.5% represents the minimum acceptable bar for a v0 safety-critical classifier.
## 16. Paralinguistic Signal Detection

[REQ-100-152] The Signal Agent MUST detect and annotate paralinguistic signals — observable patterns in *how* a message is composed, independent of its lexical content. These signals are valid "observable linguistic patterns" under REQ-100-011 and are mandatory for compliance with REQ-100-130 (indirect emotional expression, humour masking distress, neurodivergent communication patterns).

[REQ-100-153] The Structural Signal Pre-Analysis pass (SPEC-700 §4 Step 1.5) produces `[STRUCT:]` and `[PARA:]` annotations before the Signal Agent runs. The Signal Agent MUST consume these annotations as supplementary input to the standard signal classification. The Signal Agent MUST NOT discard or overwrite the Pre-Analysis annotations.

### 16.1 Tone Softener Signals

[REQ-100-154] The following patterns MUST be detected as `[PARA: tone_softener]` and interpreted as *affect dampeners*, not as expressions of genuine humour. A tone softener appended to a distress-adjacent statement indicates the user is disclosing while managing their emotional exposure:

- `lol`, `lmao`, `haha`, `hehe`, `lmfao` following a distress-vocabulary statement
- `😅`, `💀`, `🙃` used in the same semantic unit as distress content

[REQ-100-155] A detected `[PARA: tone_softener]` MUST increase the confidence weight of any co-detected risk or emotional-state signals in the same message. It MUST NOT be treated as evidence of reduced distress or genuine humour. This requirement directly implements REQ-100-130 ("humour masking distress").

### 16.2 Typographic Register Signals

[REQ-100-156] The following typographic patterns MUST be detected and annotated. They are valid only when co-present with lexical distress signals or structural signals — they MUST NOT be emitted in isolation on neutral messages:

| Tag | Observable Pattern | Interpretation |
|-----|--------------------|----------------|
| `[PARA: terminal_period_weight]` | Terminal period on a ≤8-word message from a user whose prior messages lacked terminal periods | Finality, emotional closure, or passive-affect marker. For digital-native users, a terminal period signals weight, not standard grammar. |
| `[PARA: uncapitalised_self_ref]` | Consistent lowercase `i` as self-reference in a message that also contains distress vocabulary | Contextual indicator of dissociation or reduced self-regard. Invalid without co-present distress content. |
| `[PARA: ellipsis_density]` | Three or more `...` instances within a single message | Trailing thought, unspoken content, inability or unwillingness to complete a statement. |
| `[PARA: all_caps_segment]` | One or more ALL CAPS words within an otherwise lowercase or mixed-case message | Intensity marker or acute emotional load on the capitalised segment. |

### 16.3 Structural Distress Signals

[REQ-100-157] The following structural signals require comparison with prior turns. They MUST NOT be emitted on the first turn of a session. When conversation history is unavailable or has fewer than two prior turns, structural signals MUST be suppressed and this suppression MUST be noted in `uncertainty_notes`:

| Tag | Observable Pattern | Interpretation |
|-----|--------------------|----------------|
| `[STRUCT: register_collapse]` | User's habitual message structure (length, punctuation, emoji use) abruptly shifts to bare, terse, or unformatted text | Significant mood shift; emotional suppression; possible dissociation. |
| `[STRUCT: message_length_collapse]` | Current message is ≤30% of the user's average length over the prior 3 turns | Emotional withdrawal or shutdown. |
| `[STRUCT: monosyllabic_withdrawal]` | Single-word response (`yeah`, `ok`, `idk`, `fine`, `whatever`) following a prior turn of ≥3 sentences | Disengagement or emotional withdrawal. |
| `[STRUCT: uncorrected_typo_density]` | ≥2 uncorrected typographic errors in a message from a user with no typos in prior turns | Elevated cognitive load or emotional overwhelm. |
| `[STRUCT: emoji_absence]` | No emoji in a message from a user who used emoji in ≥2 of the 3 prior turns | Emotional suppression or affective flattening. |

[REQ-100-158] Structural signals MUST be weighted proportionally: `register_collapse` and `message_length_collapse` carry higher evidentiary weight than `monosyllabic_withdrawal` or `emoji_absence` in isolation.

[REQ-100-159] The Support Strategy Agent MUST treat structural signal evidence as grounds for selecting gentler, more presence-focused framing strategies, even when lexical distress level is `low` or `moderate`. A structurally distressed user who uses no explicit distress vocabulary is not a neutral user.

### 16.4 First-Turn Limitation

[REQ-100-160] On the first turn of a session (no conversation history available), all §16.3 structural signals MUST be suppressed. Only §16.1 tone softener and §16.2 typographic register signals are detectable on a first turn.

[REQ-100-161] The suppression of structural signals on first turn MUST be noted by the Pre-Analysis pass as `[STRUCT: suppressed_no_history]` in `uncertainty_notes` so downstream agents can distinguish "no structural signals detected" from "structural signals not evaluated."

---

## 17. Ethical Rationale

Psychological signals enable Nikko to respond compassionately, remain non-clinical, avoid diagnostic authority, and maintain ethical digital-health boundaries.

> *The ontology exists to understand expression, not define identity.*

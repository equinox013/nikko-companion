---
id: SPEC-300
title: Crisis Response Protocol (CRP)
status: authoritative
supersedes: []
depends_on: [SPEC-000, SPEC-100, SPEC-200]
version: 1.0.0-draft
last_reviewed: 2026-05-08
---

# SPEC-300 — Crisis Response Protocol (CRP)

## Status

- **Authoritative Safety Specification.**
- **Overrides all non-crisis behavior in SPEC-001 through SPEC-200 when active.**
- Dependent on: [SPEC-000](./SPEC-000-charter.md), [SPEC-100](./SPEC-100-signal-ontology.md), [SPEC-200](./SPEC-200-agent-communication-protocol.md).

## 1. Purpose

[REQ-300-001] SPEC-300 MUST define mandatory system behavior when users exhibit crisis-level psychological signals, including but not limited to: suicidal ideation, self-harm intent, immediate emotional danger states, loss of safety framing, explicit or implicit desire not to live.

[REQ-300-002] The system SHALL prioritize human life and real-world intervention over conversation continuity.

## 2. Core Crisis Principle

[REQ-300-010] When crisis conditions are detected, the system SHALL no longer behave as a conversational assistant. It MUST become a **stabilization and escalation interface only**.

[REQ-300-011] All non-essential processing MUST be suspended.

## 3. Crisis Definition (Trigger Conditions)

[REQ-300-020] A crisis state SHALL be triggered when [SPEC-100 §9](./SPEC-100-signal-ontology.md#9-signal-representation-schema) outputs `"distress_level": "crisis"`, OR when any of the following are detected:

### 3.1 Explicit indicators
- statements of intent to self-harm,
- suicide-planning language,
- goodbye messages,
- timing-based intent ("tonight", "soon", "right now").

### 3.2 Implicit high-risk indicators
- unbearable-emotional-pain language,
- no-future-orientation combined with hopelessness,
- "I can't go on" framing,
- dissociation combined with withdrawal statements.

[REQ-300-FP1] The implicit/contextual risk classifier MUST be calibrated to a false-positive rate ≤ 5% on the standard crisis test suite. This ceiling is revisable during Phase 6 evaluation with Director approval. The classifier MUST prioritize recall over precision — missing a genuine crisis signal is the higher-cost error.

### 3.3 Contextual escalation
- repeated distress escalation across conversation history,
- inability to engage with grounding attempts.

> **[GAP-G-CRISIS-02]** The implicit and contextual indicators are described prosaically. Implementation requires a concrete classifier output mapping (likely a dedicated risk-classifier model fine-tuned on labelled examples). The mapping does not yet exist.

## 4. Crisis Mode Activation

[REQ-300-030] On crisis detection, the Router MUST set Crisis Mode Lock.

[REQ-300-031] Upon Crisis Mode Lock, the following agents MUST be reconfigured:

| Agent | State |
|-------|-------|
| Evidence Retrieval Agent | DISABLED |
| Support Strategy Agent | LIMITED (stabilization framings only) |
| Normal Interaction Model | DISABLED (except stabilization output) |

[REQ-300-032] Only the Crisis Response Flow defined in §5 MAY execute during Crisis Mode.

## 5. Mandatory Crisis Response Flow (CRF)

### Step 1 — Immediate Stabilization Message

[REQ-300-040] The first response MUST contain: calm tone, emotional validation, non-judgmental language, and no analysis or interpretation.
[REQ-300-041] The system MUST NOT delay stabilization for evidence retrieval.

### Step 2 — Australian Crisis Resources (MANDATORY)

[REQ-300-050] The system MUST provide the following Australian crisis-support options, presented clearly and without dilution:

| Resource | Number |
|----------|--------|
| Lifeline Australia | **13 11 14** |
| Beyond Blue Support Service | **1300 22 4636** |
| Suicide Call Back Service | **1300 659 467** |
| Emergency Services (immediate danger) | **000** |

> **[GAP-G-CRISIS-01]** The deployed UI is publicly accessible (`equinox013.github.io/nikko`) — non-Australian users will reach it. No fallback set is defined for users outside Australia. Director ruling required: ship Australia-only and geo-block non-AU traffic, or define an international fallback set (e.g., 988 US, Samaritans UK, befrienders.org global directory)?
> **[GAP-G-CRISIS-03]** Demographic-specific resources are absent: Kids Helpline (1800 55 1800), 13YARN First Nations (13 92 76), QLife LGBTQ+ (1800 184 527), 1800RESPECT family-violence (1800 737 732), MensLine (1300 78 99 78). Director should rule on whether these are mandatory, optional, or context-routed.

[
[REQ-300-RS1] Baseline crisis resources (MUST always be displayed during Crisis Mode):
- Lifeline: 13 11 14
- Beyond Blue: 1300 22 4636
- Suicide Call Back Service: 1300 659 467
- Emergency Services: 000

[REQ-300-RS2] Demographic-specific resources MUST be provided in a "More tailored support" expandable section alongside the baseline resources:
- QLife (LGBTIQ+): 1800 184 527
- 13YARN (First Nations): 13 92 76
- Kids Helpline (under 25): 1800 55 1800
- 1800RESPECT (family violence): 1800 737 732
- MensLine Australia: 1300 78 99 78

[REQ-300-RS3] The expandable section MUST NOT infer demographic identity from conversation context. It is presented to all users equally.
[REQ-300-GD1] The UI MUST display a prominent disclaimer before the chat interface is accessible, stating: "Nikko is currently available in Australia only. Crisis resources shown are Australian services." This disclaimer is a v0 constraint pending international routing implementation.
[REQ-300-GD2] Crisis resources MUST NOT be presented to users without the geographic scope disclaimer.

### Quick-exit target domain

[REQ-300-QE1] The quick-exit button MUST always be visible during any active session (Comfort, Guidance, and Crisis Modes). On activation, it MUST: (1) immediately clear all session state (`sessionStorage`, non-essential `localStorage`), and (2) replace the browser history entry and navigate to `https://www.bom.gov.au/`.

[REQ-300-QE2] The navigation target `bom.gov.au` (Australian Bureau of Meteorology) is the ratified v0 quick-exit domain. Design rationale: Australian government domain, visually innocuous (weather service), no mental health or social-media content, provides plausible cover for users who require privacy from others in the same space. This domain MUST NOT be changed without Director approval.

> **[RATIFIED 2026-05-11]:** `bom.gov.au` confirmed as quick-exit target per Director ruling on G-P5-001. See [GAPS.md G-P5-001](../GAPS.md#g-p5-001--quick-exit-domain-not-in-spec-300).

### Step 3 — Encourage Human Contact

[REQ-300-060] Nikko MUST explicitly encourage:
- contacting a trusted person,
- reaching out to a professional,
- not staying alone during acute distress.

[REQ-300-061] The encouragement MUST be gentle but direct.

### Step 4 — Safety Anchoring Language

[REQ-300-070] Nikko SHOULD include grounding support such as:
- slow-breathing encouragement,
- presence acknowledgment ("you're not alone in this moment"),
- short-term focus ("let's focus on the next few minutes").

[REQ-300-071] No therapeutic techniques beyond basic stabilization MAY be offered.

### Step 5 — No Problem Solving

[REQ-300-080] Nikko MUST NOT attempt to resolve underlying issues.
[REQ-300-081] Nikko MUST NOT analyze causes.
[REQ-300-082] Nikko MUST NOT provide coping strategies beyond grounding.
[REQ-300-083] Nikko MUST NOT engage in long-form conversation during Crisis Mode.

> *The goal is **containment and escalation**, not resolution.*

## 6. Evidence System Restriction

[REQ-300-090] During Crisis Mode:
- the Evidence Retrieval Agent MUST be bypassed,
- the Evidence Synthesizer MUST be disabled,
- no citations SHALL be presented.

> *Factual accuracy is secondary to immediate human-safety escalation.*

## 7. Interaction Model Constraints

[REQ-300-100] The final LLM output during Crisis Mode MUST: remain short, remain calm, avoid complexity, avoid intellectualization, avoid over-explaining.

[REQ-300-101] No response MAY exceed stabilization-plus-escalation scope.

## 8. Anti-Delay Rule

[REQ-300-110] The system MUST NOT ask probing questions before delivering crisis resources.
[REQ-300-111] The system MUST NOT request clarification before delivering crisis resources.
[REQ-300-112] The system MUST NOT delay escalation with conversational softening.

## 9. Persistence Rule

[REQ-300-120] Crisis Mode SHALL remain active until the Router determines `distress_level` is no longer `crisis` for the current and most-recent prior turn.
[REQ-300-121] No self-reset SHALL be allowed within a single turn.

> **[PROPOSED-RECONCILIATION:** the source spec leaves the de-escalation criterion implicit ("when stabilizes"). Concrete proposal: Crisis Mode persists until **two consecutive turns** classify as `distress_level <= high` AND no risk indicators in [SPEC-100 §7.2 / §7.3](./SPEC-100-signal-ontology.md#7-risk-indicator-signals) are present in either turn. **]** See [G-RECON-04](../GAPS.md).

[REQ-300-DE1] Crisis Mode (Level 3) MUST persist until two consecutive turns classify as distress_level ≤ high (Level 2) AND no risk indicators are present in either turn. A single calmer turn is insufficient to exit Crisis Mode.

## 10. Prohibited Behaviours (Hard Failures)

[REQ-300-130] The system MUST NEVER:
- suggest "handling it alone",
- imply the user should not seek help,
- minimize severity ("it might not be that bad"),
- intellectualize suicide or self-harm,
- present AI as sufficient support.

[REQ-300-131] Any occurrence of the above SHALL constitute a critical safety violation and MUST be logged as such.

## 11. Post-Crisis Transition (De-escalation Phase)

[REQ-300-140] If the user stabilizes per the criteria in §9, the system MAY:
- slowly transition back to Comfort Mode,
- reintroduce supportive dialogue,
- optionally offer gentle grounding suggestions.

[REQ-300-141] Transition MUST NOT occur while any active crisis signal remains.

## 12. Ethical Priority Hierarchy

[REQ-300-150] In crisis situations, priorities SHALL be applied in this order:

1. Human-life safety
2. Real-world escalation
3. Emotional stabilization
4. System coherence
5. Informational completeness

[REQ-300-151] Higher priorities MUST permanently override lower ones.

## 13. System Philosophy

> Nikko is not designed to "solve crisis." Nikko is designed to hold emotional space briefly, then guide the user toward real human support immediately and without hesitation. It is a bridge, not a destination.

## 14. Success Criteria

SPEC-300 is successful when:

- crisis signals are detected reliably,
- escalation is immediate,
- no hallucinated advice is given,
- users are directed to real support,
- the system avoids over-engagement in crisis contexts.

[REQ-300-160] The following SHALL be classified as failure of SPEC-300:
- delayed escalation,
- attempts to resolve crisis independently,
- substitution of human intervention.

## 15. Closing Principle

> *In all crisis contexts: clarity saves lives, complexity does not.*

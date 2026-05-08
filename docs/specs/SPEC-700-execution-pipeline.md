---
id: SPEC-700
title: Full System Integration Blueprint (End-to-End Execution Trace)
status: authoritative
supersedes: []
depends_on: [SPEC-000, SPEC-100, SPEC-200, SPEC-300, SPEC-400, SPEC-500, SPEC-600]
version: 1.0.0-draft
last_reviewed: 2026-05-08
---

# SPEC-700 — Full System Integration Blueprint

## Status

- **Authoritative Runtime Specification.**
- Dependent on: [SPEC-000](./SPEC-000-charter.md) → [SPEC-600](./SPEC-600-deployment-architecture.md).
- Defines: the complete execution lifecycle of Nikko per user interaction.

## 1. Purpose

[REQ-700-001] SPEC-700 MUST define the exact end-to-end flow of every user interaction, including: request ingestion, agent routing, signal processing, evidence retrieval, LLM generation, evaluation loops, crisis overrides, and response delivery.

[REQ-700-002] Every system output SHALL be traceable, reproducible, and structurally consistent.

## 2. Core Execution Philosophy

[REQ-700-010] Nikko SHALL be a **deterministic multi-agent pipeline**, not an emergent system.

[REQ-700-011] Every request MUST follow a fixed, auditable execution graph.

[REQ-700-012] Hidden branching logic outside this specification SHALL be prohibited.

## 3. Full Execution Pipeline Overview

```
1.  User Input
2.  Input Sanitization Layer
3.  Psychological Signal Detection (SPEC-100)
4.  Router Decision (SPEC-200)
5.  Mode Selection (Comfort | Guidance | Crisis)
6.  Agent Chain Execution
7.  Evidence Retrieval (if required)
8.  Evidence Synthesis
9.  Support Strategy Generation
10. LLM Draft Response Generation
11. Evaluator Audit Pass
12. Verification Supervisor Check
13. Final Response Assembly
14. Output Delivery
15. Logging & Audit Trace Storage
```

## 4. Step-by-Step Execution Contract

### STEP 0 — Scope Classification (Pre-Router Gate)

[REQ-700-SC1] Before any other pipeline processing, the Scope Classifier (see [SPEC-200 §5.0](./SPEC-200-agent-communication-protocol.md#50-scope-classifier-pre-router-gate)) MUST evaluate every user input and emit one of three decisions: IN_SCOPE, AMBIGUOUS, or OUT_OF_SCOPE.

[REQ-700-SC2] Routing on Scope Classifier output:
- **IN_SCOPE or AMBIGUOUS** → proceed to STEP 1 (User Input Ingestion) and the normal pipeline.
- **OUT_OF_SCOPE** → return the warm-redirect response immediately. The pipeline MUST terminate here. No downstream agent is invoked. Execution time for this path MUST NOT exceed 500 ms.

[REQ-700-SC3] The Scope Classifier decision and confidence score MUST be included in the session trace for observability. The warm-redirect response MUST be logged as a distinct response type (not a pipeline output) for drift monitoring.

### STEP 1 — User Input Ingestion

[REQ-700-020] Input SHALL be received via the frontend interface.
[REQ-700-021] All input MUST be treated as untrusted.
[REQ-700-022] Input MUST be sanitized for injection attempts.
[REQ-700-023] Raw text MUST be preserved for signal analysis.
[REQ-700-024] The system MUST NOT pre-classify emotional state at ingestion.
[REQ-700-025] The system MUST NOT pre-interpret intent at ingestion.

### STEP 2 — Psychological Signal Detection (SPEC-100)

[REQ-700-030] Sanitized input MUST be passed to the Signal Agent.

[REQ-700-031] The Signal Agent MUST emit:

```json
{
  "distress_level": "...",
  "emotional_states": [],
  "cognitive_patterns": [],
  "behavioral_indicators": [],
  "risk_indicators": [],
  "support_needs": [],
  "confidence": 0.0
}
```

[REQ-700-032] This output SHALL be immutable for the rest of the pipeline.

### STEP 3 — Routing Decision (SPEC-200)

[REQ-700-040] The Router MUST evaluate: signal output; conversation history; system state.

[REQ-700-041] The Router MUST output exactly one mode: Comfort | Guidance | Crisis.

[REQ-700-042] Mixed-mode execution SHALL NOT be permitted.

> **[GAP-G-MEMORY-02]** "Conversation history" usage is repeated here. The state-management spec is missing. Reuse [G-MEMORY-01](../GAPS.md).

[REQ-700-MEM1] Conversation state (history, signal classifications, mode context) is maintained exclusively in-memory within the LLM context window for the duration of the active session. No server-side database, cache, or file storage is used. State is destroyed when the user terminates the session. Session continuity across browser refreshes is not supported in v0.

## 5. Mode Execution Paths

### 5.1 Comfort Mode Flow

Used when emotional distress is present but not crisis-level.

```
Signal → Router
   ↓
Support Strategy Agent
   ↓
Interaction Model (Empathy + Safety Adapter)
   ↓
Optional Evidence Context Injection
   ↓
Evaluator Pass
   ↓
Verification Supervisor
   ↓
Final Response
```

[REQ-700-050] Comfort Mode MUST prioritize emotional validation over factual content.
[REQ-700-051] Comfort Mode MUST avoid overloading the user with facts.

### 5.2 Guidance Mode Flow

Used when the user requests information or coping knowledge.

```
Signal → Router
   ↓
Evidence Retrieval Agent
   ↓
Evidence Synthesizer Agent
   ↓
Support Strategy Agent
   ↓
Interaction Model (Empathy + Safety Adapter)
   ↓
Evaluator Pass
   ↓
Verification Supervisor
   ↓
Final Response
```

[REQ-700-060] Guidance Mode MUST present evidence first and tone second.
[REQ-700-061] Guidance Mode MUST include citations when applicable.
[REQ-700-062] Guidance Mode MUST NOT issue directive advice.

### 5.3 Crisis Mode Flow (OVERRIDE PATH)

Triggered by SPEC-100 crisis signals.

```
Signal → Router
   ↓
Crisis Override Activation
   ↓
Skip Evidence Retrieval
   ↓
Interaction Model (Safety Adapter ONLY)
   ↓
Static Crisis Resource Injection (Australia)
   ↓
Evaluator Minimal Pass (Safety-only)
   ↓
Final Response
```

[REQ-700-070] Crisis Mode MUST inject the Australian crisis resources defined in [SPEC-300 §5 Step 2](./SPEC-300-crisis-response-protocol.md#step-2--australian-crisis-resources-mandatory).

> **[PROPOSED-RECONCILIATION:** the source omits the Verification Supervisor pass in Crisis Mode. The reconciled position: in Crisis Mode the Verification Supervisor MAY be replaced by a minimal safety-only verifier (a stripped-down version that only checks for prohibited phrasings from [SPEC-300 §10](./SPEC-300-crisis-response-protocol.md#10-prohibited-behaviours-hard-failures)) to honour the latency-priority requirement while preserving safety. Full Verification Supervisor pass SHALL NOT be skipped silently — it must be explicitly downgraded and logged. **]** See [G-RECON-06](../GAPS.md).

[REQ-700-VS1] During Crisis Mode (Level 3), the Verification Supervisor MUST NOT be skipped. It operates in a minimal safety-verifier mode: checks routing integrity and Safety adapter compliance only. Tone checks, evidence-pipeline integrity checks, and full cross-spec compliance checks are suspended during Crisis Mode. Full Verification Supervisor operation resumes on de-escalation to Level ≤ 2.
[PROPOSED-RECONCILIATION: Source spec omitted VS from Crisis Mode flow. Reconciled: VS runs in stripped-down mode, not skipped. Director ratified 2026-05-09.]

## 6. Evaluator Pass (Universal Rule)

[REQ-700-080] Every non-crisis response MUST pass Evaluator audit.

[REQ-700-081] The Evaluator MUST check: safety compliance ([SPEC-000](./SPEC-000-charter.md)); hallucination risk; clinical-authority leakage; emotional-tone alignment; evidence correctness (if applicable).

[REQ-700-082] On Evaluator failure, the response MUST be regenerated, OR downgraded to a safer fallback response.

## 7. Verification Supervisor Pass

[REQ-700-090] The Verification Supervisor SHALL be the **final structural gate** before output. The Evaluator ([REQ-200-101](./SPEC-200-agent-communication-protocol.md#57-evaluator-model)) is the final content gate; both MUST pass for delivery.

[REQ-700-091] It MUST check: SPEC-200 routing compliance; evidence integrity (if used); crisis-handling correctness; absence of agent contamination.

[REQ-700-092] On Verification Supervisor failure, the system MUST default to a minimal safe response.

## 8. Final Response Assembly

[REQ-700-100] The final output MUST be constructed from: LLM-generated text; Support Strategy constraints; verified evidence (if any); the safety-framing layer.

[REQ-700-101] The final output MUST include:
- AI disclosure (implicit via tone or explicit, depending on context),
- non-clinical framing,
- autonomy reinforcement where relevant.

## 9. Logging & Trace Capture

[REQ-700-110] Every execution MUST produce a full trace:

```json
{
  "session_id": "string",
  "execution_path": ["string"],
  "signal_output": {},
  "router_decision": "string",
  "agents_triggered": ["string"],
  "evidence_used": ["string"],
  "adapter_configuration": ["string"],
  "evaluation_result": "string",
  "final_action": "string"
}
```

[REQ-700-111] Trace storage MUST conform to [SPEC-600 §9](./SPEC-600-deployment-architecture.md#9-logging--observability-system) and the privacy gap [G-PRIVACY-01](../GAPS.md).

[REQ-700-LOG1] Logging during execution is session-scoped and ephemeral. All trace data MUST be purged when the session ends. See [SPEC-600 §9](./SPEC-600-deployment-architecture.md#9-logging--observability-system).

## 10. Failure State Model

### 10.1 Agent failure
[REQ-700-120] On agent failure, the system MUST retry once, then fall back to a safe minimal response.

### 10.2 Evidence failure
[REQ-700-121] On retrieval failure, the system MUST proceed without evidence and explicitly avoid fabrication.

### 10.3 Evaluator failure
[REQ-700-122] On Evaluator failure, the system MUST default to SAFE MODE response with no evidence injection.

### 10.4 Router failure
[REQ-700-123] On Router failure, the system MUST default to Comfort Mode and suppress all evidence chains.

## 11. Execution Constraints (Hard Rules)

### Rule 1 — No parallel chains
[REQ-700-130] Only one execution path per request SHALL be permitted.

### Rule 2 — No bypass execution
[REQ-700-131] No agent MAY skip the Router or the Evaluator.

### Rule 3 — No cross-mode mixing
[REQ-700-132] Comfort, Guidance, and Crisis modes MUST NOT be combined within a turn.

### Rule 4 — No direct LLM evidence access
[REQ-700-133] The LLM MUST receive only synthesized or filtered inputs.

## 12. Latency Constraints (Operational)

[REQ-700-140] Comfort Mode SHALL be optimized for responsiveness.
[REQ-700-141] Guidance Mode MAY accept moderate delay.
[REQ-700-142] Crisis Mode SHALL receive immediate execution priority.
[REQ-700-143] Safety SHALL override performance.

## 13. Determinism Requirement

[REQ-700-150] Given identical user input, system state, and model version, the **execution path** MUST be consistent.

[REQ-700-151] LLM-generated *content* MAY be stochastic (sampling), but seeded reproducibility MUST be supported in evaluation contexts.

[REQ-700-152] Non-deterministic *routing* SHALL be considered a system failure.

> **[PROPOSED-RECONCILIATION:** the source claims "execution path MUST remain consistent" without distinguishing routing vs content. The above three-line decomposition makes the determinism contract precise. **]**

## 14. System Integrity Principle

[REQ-700-160] Nikko SHALL be a single, controlled execution pipeline composed of verified, constrained modules.

[REQ-700-161] No component MAY act outside this pipeline.

## 15. Success Criteria

The system is successful when:

- every user input follows a traceable execution path,
- crisis handling is immediate and reliable,
- no agent bypass or contamination occurs,
- the Evaluator consistently enforces safety boundaries,
- outputs remain stable under repeated testing.

## 16. Closing Principle

> SPEC-700 is the final layer of structure. It ensures that Nikko behaves not like a probabilistic chatbot, but like a governed, auditable, safety-constrained AI system.

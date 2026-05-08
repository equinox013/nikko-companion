---
id: SPEC-200
title: Agent Communication Protocol (ACP)
status: authoritative
supersedes: [SPEC-003, SPEC-004, SPEC-005, SPEC-006, SPEC-007, SPEC-008]
depends_on: [SPEC-000, SPEC-100]
version: 1.0.0-draft
last_reviewed: 2026-05-08
---

# SPEC-200 — Agent Communication Protocol (ACP)

## Status

- **Authoritative System Specification.**
- Dependent on: [SPEC-000](./SPEC-000-charter.md), [SPEC-100](./SPEC-100-signal-ontology.md).
- Enforces: inter-agent coordination integrity.

## 1. Purpose

[REQ-200-001] SPEC-200 MUST define the communication rules, routing constraints, and message contracts between all agents in the Nikko system.

The objectives are: deterministic agent behavior, controlled information flow, prevention of conflicting outputs, safe escalation handling, and traceable decision-making.

[REQ-200-002] Agents MUST NOT engage in free-form chat. Agents SHALL pass structured state through controlled channels.

## 2. Core Design Principle

[REQ-200-010] Nikko agents SHALL NOT be autonomous conversational entities.

[REQ-200-011] Agents SHALL operate as: stateless processors operating on structured inputs and outputs under a central routing authority.

[REQ-200-012] All inter-agent communication MUST be: structured, typed, validated, auditable.

[REQ-200-013] Free-form agent-to-agent messaging is prohibited.

## 3. System Communication Topology

```
User Input
    ↓
Router (Traffic Controller)
    ↓
Signal Agent → Support Strategy Agent → Evidence Agent → Synthesizer
    ↓
Verification Supervisor
    ↓
Evaluator Model
    ↓
Interaction Model (Final Response)
```

[REQ-200-020] The Router SHALL be the only entity allowed to initiate or terminate agent chains.

> **[PROPOSED-RECONCILIATION:** the source places Verification Supervisor *before* the Evaluator Model in the topology, but later (SPEC-700 §6 then §7) places Evaluator *before* Verification Supervisor in execution order. Reconciled order for downstream specs: **Evaluator pass → Verification Supervisor pass**, on the basis that Evaluator is content-level audit (per-response) and Verification Supervisor is system-level audit (cross-flow). The textual diagram in §3 above is preserved for fidelity to the source; the *operative* execution order for the runtime is the one in [SPEC-700 §3](./SPEC-700-execution-pipeline.md#3-full-execution-pipeline-overview). **]** See [G-RECON-02](../GAPS.md).

## 4. Message Format Standard (ACP-Message)

[REQ-200-030] All inter-agent communication MUST use the ACP schema:

```json
{
  "message_id": "uuid",
  "source_agent": "string",
  "target_agent": "string",
  "timestamp": "iso-8601",
  "intent": "string",
  "payload_type": "signal | evidence | strategy | evaluation | response_context",
  "payload": {},
  "confidence": 0.0,
  "priority": "low | medium | high | critical",
  "requires_ack": true
}
```

[REQ-200-031] `message_id` MUST be a unique UUID (v4 recommended).
[REQ-200-032] `source_agent` and `target_agent` MUST be values from the agent roster in [GLOSSARY](../GLOSSARY.md#agent-roster).
[REQ-200-033] `timestamp` MUST be an ISO-8601 string in UTC.
[REQ-200-034] `payload_type` MUST be one of the five enumerated values.
[REQ-200-035] `confidence` MUST be a float in `[0.0, 1.0]`.
[REQ-200-036] `priority` MUST be one of the four enumerated values.
[REQ-200-037] Messages with malformed schema MUST be rejected by the target agent and logged.

## 5. Agent Roles and Permissions

### 5.1 Router (Traffic Controller)

**Authority Level: MAXIMUM.**

[REQ-200-040] The Router SHALL be responsible for: initiating workflows, selecting agent chains, enforcing SPEC-100 routing decisions, terminating unsafe flows.

[REQ-200-041] The Router MUST NOT generate final user-facing responses.
[REQ-200-042] The Router MUST NOT modify evidence content.

### 5.2 Psychological Signal Agent

**Authority Level: LOW.**

[REQ-200-050] The Signal Agent SHALL interpret user input using the SPEC-100 ontology.
[REQ-200-051] The Signal Agent SHALL emit structured signal objects conforming to [SPEC-100 §9](./SPEC-100-signal-ontology.md#9-signal-representation-schema).
[REQ-200-052] The Signal Agent MAY only send messages to the Router.
[REQ-200-053] The Signal Agent MUST NOT communicate with the Evidence Agent or the Interaction Model directly.

### 5.3 Support Strategy Agent

**Authority Level: MEDIUM.**

[REQ-200-060] The Support Strategy Agent SHALL interpret signals and map them to communication strategies.
[REQ-200-061] Outputs SHALL include: tone guidance, framing strategy, response constraints.
[REQ-200-062] The Support Strategy Agent MUST NOT access raw evidence sources.

### 5.4 Evidence Retrieval Agent

**Authority Level: MEDIUM.**

[REQ-200-070] The Evidence Retrieval Agent SHALL query external knowledge sources and return raw evidence objects.
[REQ-200-071] The Evidence Retrieval Agent MUST query only approved sources, in priority order:
1. PubMed Central Open Access (primary)
2. Healthdirect Australia (primary)
3. Better Health Channel (primary)
4. World Health Organization (primary)
5. NHS (secondary fallback)
6. CDC (secondary fallback)
7. Mayo Clinic (secondary fallback)

[REQ-200-072] Retrieval rules: prefer peer-reviewed evidence; prioritize recency; detect source disagreement; avoid single-source conclusions.
[REQ-200-073] The Evidence Retrieval Agent MUST NOT interpret emotional signals.

> **[GAP-G-EVIDENCE-01]** Source priority is given but no tie-breaking rule is specified when peer-review (highest quality) conflicts with recency (highest currency). Director ruling required.
> **[GAP-G-EVIDENCE-02]** Concrete query interface (REST API endpoints, scraping policy, rate limits) for each source is not defined.

### 5.5 Evidence Synthesizer Agent

**Authority Level: MEDIUM.**

[REQ-200-080] The Evidence Synthesizer Agent SHALL: consolidate retrieved evidence, remove redundancy, normalize citations, compute a confidence score.
[REQ-200-081] The Evidence Synthesizer Agent MUST NOT: interpret user emotion, generate advice, determine response strategy.

### 5.6 Verification Supervisor Agent

**Authority Level: HIGH.**

[REQ-200-090] The Verification Supervisor Agent SHALL: validate factual correctness, detect hallucinations, ensure source reliability, enforce SPEC-000 compliance.
[REQ-200-091] The Verification Supervisor MAY reject any upstream output and trigger regeneration loops, subject to the loop limits in [§10](#10-loop-prevention-rules).

### 5.7 Evaluator Model

**Authority Level: HIGH.**

[REQ-200-100] The Evaluator Model SHALL perform: safety audit, tone-compliance check, epistemic-humility enforcement.
[REQ-200-101] The Evaluator MUST act as the **final content gate** before response generation. Distinct from the Verification Supervisor's **final structural gate** ([REQ-700-090](./SPEC-700-execution-pipeline.md#7-verification-supervisor-pass)).

> **[PROPOSED-RECONCILIATION:** Evaluator and Verification Supervisor have overlapping authority levels (HIGH) but distinct domains. Reconciled scope:
> - **Evaluator** = per-response audit (safety, tone, hallucination heuristics).
> - **Verification Supervisor** = system-level audit (routing integrity, evidence pipeline integrity, cross-spec compliance).
> When both pass, the response is delivered. When either fails, regeneration is triggered. **]** See [G-RECON-02](../GAPS.md).

### 5.8 Interaction Model (Final LLM)

**Authority Level: CONTROLLED OUTPUT ONLY.**

[REQ-200-110] The Interaction Model SHALL: generate the final user-facing response, apply tone guidance, integrate evidence context.
[REQ-200-111] The Interaction Model MUST NOT: modify evidence, override Evaluator decisions, bypass Router decisions.

## 6. Routing Rules (Traffic Logic)

[REQ-200-120] All flows MUST follow deterministic routing rules.

### Rule 1 — Signal First
[REQ-200-121] No agent chain MAY begin without Psychological Signal Agent output (SPEC-100).

### Rule 2 — Mode Separation
[REQ-200-122] The Router MUST classify each turn as exactly one of: Comfort Mode, Guidance Mode, Crisis Mode.
[REQ-200-123] Mixed-mode execution within a single turn is prohibited.

### Rule 3 — Crisis Precedence
[REQ-200-124] If any crisis signal exists, evidence retrieval MUST be deprioritized.
[REQ-200-125] Crisis support flow MUST override all other flows.

### Rule 4 — Evidence Locking
[REQ-200-126] Once evidence is retrieved, it SHALL become immutable.
[REQ-200-127] Only the Evidence Synthesizer MAY transform retrieved evidence.
[REQ-200-128] The Evaluator MAY reject evidence but MUST NOT alter it.

### Rule 5 — No Direct LLM Access to Raw Evidence
[REQ-200-129] The Interaction Model MUST receive synthesized evidence only.
[REQ-200-130] The Interaction Model MUST NOT receive raw retrieval outputs.

### Rule 6 — Single Active Chain Constraint
[REQ-200-131] Only one active agent chain MAY execute per user turn.
[REQ-200-132] Parallel execution within a turn is forbidden.

## 7. Priority System

| Priority | Meaning |
|----------|---------|
| `low` | informational |
| `medium` | standard processing |
| `high` | safety-relevant |
| `critical` | crisis or system failure |

[REQ-200-140] Critical messages MUST preempt all workflows.

## 8. Acknowledgement Protocol

[REQ-200-150] When `requires_ack: true`, the target agent MUST respond with an ACK message.
[REQ-200-151] Missing ACK MUST trigger retry or reroute, subject to the loop limits in §10.

## 9. Failure Handling Rules

If any agent fails:

[REQ-200-160] **Step 1.** The Router MUST attempt re-execution.
[REQ-200-161] **Step 2.** If re-execution fails, the Router MUST fall back to a simpler chain (minimal safe response).
[REQ-200-162] **Step 3.** If unresolved, the Router MUST default to Interaction Model safe response with no evidence injection.

> *Safety > completeness.*

## 10. Loop Prevention Rules

[REQ-200-170] Each agent MUST NOT iterate more than 2 times per request.
[REQ-200-171] No more than 1 evaluation cycle SHALL occur per response.
[REQ-200-172] Circular routing SHALL be forbidden.

## 11. Data Contamination Prevention

[REQ-200-180] Strict layer separation MUST be enforced:

| Layer | Allowed Data |
|-------|--------------|
| Signal Agent | raw user text |
| Evidence Agent | external sources only |
| Synthesizer | structured evidence |
| Interaction Model | curated context only |

[REQ-200-181] Cross-layer leakage SHALL NOT be permitted.

## 12. Observability Requirements

[REQ-200-190] All ACP messages MUST be logged with: agent path trace, decision rationale, confidence propagation, rejection reasons (if any).

[REQ-200-191] Audit logs SHALL be persisted in accordance with [SPEC-600 §9](./SPEC-600-deployment-architecture.md#9-logging--observability-system).

## 13. Ethical Enforcement Integration

[REQ-200-200] SPEC-200 MUST enforce SPEC-000 constraints by:
- blocking clinical-authority propagation,
- preventing unsafe routing,
- enforcing crisis-escalation ordering,
- restricting autonomy of non-Router agents.

## 14. System Philosophy

> Nikko is not a conversational swarm. It is a controlled information-flow system where each agent is a constrained specialist operating under strict routing logic. The Router is not intelligence — it is **traffic-law enforcement for cognition**.

## 15. Success Criteria

SPEC-200 is successful when:

- no agent bypasses routing rules,
- no conflicting outputs reach the Interaction Model,
- crisis flows are always prioritized correctly,
- evidence remains uncorrupted through the pipeline,
- system behaviour is fully traceable.

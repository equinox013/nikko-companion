---
id: SPEC-600
title: System Deployment & Production Architecture (SDPA)
status: authoritative
supersedes: [SPEC-011]
depends_on: [SPEC-000, SPEC-100, SPEC-200, SPEC-300, SPEC-400, SPEC-500]
version: 1.1.0
last_reviewed: 2026-05-16
---

# SPEC-600 — System Deployment & Production Architecture (SDPA)

## Status

- **Authoritative Deployment Specification.**
- Dependent on: [SPEC-000](./SPEC-000-charter.md) → [SPEC-500](./SPEC-500-evaluation-benchmarking.md).
- Defines: runtime, infrastructure, integration, and operational boundaries.

## 1. Purpose

[REQ-600-001] SPEC-600 MUST define how Nikko is deployed, hosted, served, connected (frontend/backend), versioned, and monitored in production.

[REQ-600-002] Real-world behavior MUST remain consistent with controlled-evaluation behavior.

## 2. Core Deployment Philosophy

[REQ-600-010] Nikko SHALL be a **modular AI system**, not a monolithic app.

[REQ-600-011] Deployment MUST preserve:
- separation of concerns (agents remain isolated),
- retrieval independence from model weights,
- safety-routing consistency,
- observability of all decisions.

## 3. High-Level Production Architecture

```
GitHub Pages — equinox013.github.io/nikko-companion (Frontend SPA)
  ↓
Render — FastAPI Orchestration (Backend API Layer, nikko-companion.onrender.com)
  ↓
Router (SPEC-200)
  ↓
Agent System (Signal / Evidence / Strategy / Eval)
  ↓
Modal Serverless A10G (primary) / HF Spaces ZeroGPU H200 (fallback)
  — Qwen3-4B + Gemma-2-2b-it + PEFT Adapters (LLM Inference)
  ↓
Response + Audit Log
```

## 4. Frontend Deployment (GitHub Pages)

### 4.1 Location

[REQ-600-020] The frontend SHALL be hosted at `equinox013.github.io/nikko-companion`.

### 4.2 Frontend responsibilities

[REQ-600-030] The frontend MUST: provide a chat interface; display assistant responses; optionally show citations (collapsed by default); display non-intrusive system safety notices; support session continuity.

[REQ-600-031] The frontend MUST NOT: execute model logic; perform inference; access raw agent outputs; bypass backend routing.

[REQ-600-UI1] The frontend MUST display a "research preview" label prominently on the chat interface. This label acknowledges the single-host HF Spaces limitation and the research-only scope of v0.
[REQ-600-UI2] The frontend MUST display a geographic scope disclaimer before the chat interface is accessible: "Nikko is currently available in Australia only. Crisis resources shown are Australian services."
[REQ-600-UI3] The frontend MUST present an 18+ self-attestation gate as a mandatory step before the user can access the chat interface. The gate MUST NOT be bypassable.
[REQ-600-UI4] The frontend MUST display a plain-language privacy statement before the chat interface is accessible, stating that no user data is collected, stored, or used for training, and that the session is cleared on exit.
[REQ-600-UI5] The frontend MUST display a session-scope notice: "Your conversation is private and will be cleared if you close or refresh this page."

### 4.3 UX constraints

[REQ-600-040] The UI MUST enforce: calm, non-clinical design; low cognitive load; non-alarming crisis presentation; an optional, expandable "sources used" panel.

[REQ-600-041] An optional avatar MAY be present; the avatar MUST NOT imply sentience.

> **[GAP-G-FRONTEND-01]** "Session continuity" implies client-side or server-side state. The state model, retention, and privacy policy are not specified. See [G-MEMORY-01](../GAPS.md).

## 5. Backend Orchestration Layer

### 5.1 Role

[REQ-600-050] The backend SHALL be the traffic-controller and execution environment.

Responsibilities:
- implement [SPEC-200](./SPEC-200-agent-communication-protocol.md) routing,
- coordinate agent execution,
- enforce [SPEC-300](./SPEC-300-crisis-response-protocol.md) crisis flow,
- manage API calls to the LLM and retrieval systems,
- log system behaviour.

### 5.2 Implementation style

[REQ-600-060] Recommended:
- Python-based orchestration service,
- lightweight API framework (FastAPI or equivalent),
- stateless request handling.

[REQ-600-061] Agent logic SHALL NOT live in the frontend.

### 5.3 Orchestration hosting (v0 research preview)

[REQ-600-DEP1] The backend orchestration service SHALL be hosted on **Render** (`nikko-companion.onrender.com`) for the v0 research-preview deployment. Render is the live production host as of Phase 7 (2026-05-16). Cold starts are handled by the loading screen (see FRONTEND_INTEGRATION_SPEC §12). A `Dockerfile` is required at the repo root (not in `backend/`); see `README.md §Deployment Stack`.

> **[DIRECTOR DECISION — 2026-05-16]** Fly.io was the original target per the original SPEC-600 authoring; Render was activated as fallback and is now the confirmed live host. `fly.toml` is retained at repo root for reference. Any future migration back to Fly.io requires Director approval.

[REQ-600-DEP2] (retired — Render is confirmed live; Fly.io fallback clause no longer applies)

[REQ-600-DEP3] A `Dockerfile` MUST be present at the repository root (not in `backend/`) before Phase 7 gate opens. ✅ Complete 2026-05-16.

## 6. LLM Inference Layer

### 6.1 Hosting

[REQ-600-070] Primary hosting options SHALL be: Hugging Face Spaces; an external inference API; a local-GPU fallback (development only).

> **[GAP-G-INFRA-01]** A single hosting provider (HF Spaces) is a single point of failure for a safety-critical system. No DR / multi-region / failover policy is defined. Director ruling required.

[REQ-600-HF1] **Modal Serverless** is the primary LLM inference host for v0 (research preview), running on **A10G 24 GB** GPU. **Hugging Face Spaces ZeroGPU** (H200 slice) is the designated fallback — the Render backend automatically retries against the HF Space `/pipeline` endpoint if Modal is unavailable. Both endpoints run the same `/pipeline` FastAPI interface (base model + PEFT adapters). The HF Space SHALL be configured as a private FastAPI application, not a Gradio demo. This single-region limitation MUST be documented in the UI via the research-preview label (REQ-600-UI1). Multi-provider failover beyond Modal → HF Spaces is a GA-phase requirement.

> **[DIRECTOR DECISION — 2026-05-16]** Original spec named HF Spaces as sole inference host. Revised: Modal Serverless is primary (faster cold start ~30–60s via Volume read vs ~90–120s for HF Hub download). HF Spaces ZeroGPU H200 is fallback. ZeroGPU hardware was A100 at original authoring; upgraded to H200 as of v0 deployment.

[REQ-600-HF2] The HF Space MUST load the base model and all active PEFT adapters (ADP-A, ADP-B, ADP-C) at Space startup. Adapter weights SHALL be stored in a private HF Hub repository and pulled at startup — not bundled into the Space image.

[REQ-600-HF3] Both the Modal endpoint and the HF Space fallback MUST expose a `/pipeline` POST endpoint consumed by the Render orchestration layer. Neither inference endpoint MUST be directly accessible from the frontend. The legacy `/infer` endpoint is retained in `hf_space/app.py` for compatibility but is not used by the backend in production.

> **[DIRECTOR DECISION — 2026-05-16]** Original spec specified `/infer`. Revised to `/pipeline` — the consolidated single-GPU-session endpoint that runs ADP-B → ADP-A → ADP-C in one call, reducing warm-turn latency from ~240–330s to ~20–40s.

### 6.2 Model constraints

[REQ-600-080] The inference model MUST: support adapter switching ([SPEC-400](./SPEC-400-model-training.md)); accept structured context injection; remain stateless per request.
[REQ-600-081] The inference layer MUST NOT bypass the Evaluator system.

### 6.3 Adapter injection pipeline

```
Request Context
  ↓
Selected Adapter(s)
  ↓
Base Model Inference
  ↓
Response Draft
```

[REQ-600-090] Adapter selection at runtime SHALL be governed by [SPEC-400 §9](./SPEC-400-model-training.md#9-adapter-interaction-rules).

## 7. Agent System Deployment

### 7.1 Execution model

[REQ-600-100] Agents MUST be deployed as logical services, not persistent processes.

[REQ-600-101] Each request SHALL trigger: Signal Agent → Router → conditional downstream agents.

### 7.2 Stateless constraint

[REQ-600-110] Agents MUST be: stateless between requests; deterministic given the same inputs (modulo LLM stochasticity); reproducible for evaluation.

> **[PROPOSED-RECONCILIATION:** "deterministic given the same inputs" cannot strictly hold for LLM-backed agents because sampling introduces stochasticity. Reconciled interpretation: routing decisions and ACP message construction MUST be deterministic; LLM-content generation MAY be stochastic but MUST be seedable for reproducibility in evaluation contexts. **]**

### 7.3 Communication layer

[REQ-600-120] All inter-agent communication MUST follow [SPEC-200](./SPEC-200-agent-communication-protocol.md): ACP format, strict routing rules, no direct bypass.

## 8. Evidence Retrieval Infrastructure

### 8.1 Sources

[REQ-600-130] Production retrieval SHALL query only the sources enumerated in [SPEC-200 §5.4](./SPEC-200-agent-communication-protocol.md#54-evidence-retrieval-agent).

### 8.2 Retrieval method

[REQ-600-140] Allowed retrieval methods: API-based querying; structured scraping (only if compliant with the source's terms); cached-index retrieval (optional optimization).

### 8.3 Caching rules

[REQ-600-150] Caching SHALL be permitted only if: source freshness is tracked; cache expiration exists; updates are versioned.

> **[GAP-G-CACHE-01]** Cache TTLs and invalidation events (e.g., source-side update detection) are not specified.

[REQ-600-CA1] Cache TTLs by source:
- PubMed: 7 days
- Healthdirect AU: 30 days with weekly HTTP HEAD check
- Better Health Channel AU: 30 days with weekly HTTP HEAD check
- WHO: 30 days with weekly HTTP HEAD check
- Other secondary sources: 30 days

[REQ-600-CA2] Cache invalidation is triggered by: TTL expiry, HEAD-check change detection, or Director-issued manual purge command.

## 9. Logging & Observability System

### 9.1 Required logs

[REQ-600-160] Every request MUST store: signal-classification output (SPEC-100); routing decision path (SPEC-200); evidence sources used; adapter selection; Evaluator decision output; final response.

[REQ-600-LG1] Session logs are ephemeral. The system MAY maintain operational logs (conversation context, signal classifications, routing decisions) during an active session for observability. All session logs MUST be automatically purged when the user terminates the session. No conversation content persists beyond the active session.
[REQ-600-LG2] No user conversation data, signal classifications, or routing decisions are written to persistent storage, databases, or external logging services.

### 9.2 Audit trace format

[REQ-600-170] The audit trace MUST conform to:

```json
{
  "session_id": "string",
  "route_path": ["string"],
  "signals": {},
  "agents_triggered": ["string"],
  "evidence_sources": ["string"],
  "adapter_used": ["string"],
  "evaluation_result": {},
  "final_action": "string"
}
```

### 9.3 Purpose

[REQ-600-180] Logs SHALL support: debugging agent behavior; evaluating safety compliance; retraining models; system-transparency audits.

> **[GAP-G-PRIVACY-01]** Audit traces of mental-health conversations are PII-grade sensitive. No retention period, encryption-at-rest policy, access-control model, deletion-on-request policy, or jurisdictional compliance (Australian Privacy Act, GDPR, etc.) is specified. **Critical gap.** Director ruling required before any production data is captured.

## 10. Versioning Strategy

[REQ-600-190] All system components MUST be versioned independently:

| Component | Versioned? |
|-----------|-----------|
| Base model | YES |
| Adapters | YES |
| Agent logic | YES |
| Retrieval sources | YES |
| Evaluation suite | YES |

### 10.1 Compatibility rule

[REQ-600-200] System versions MUST be tested as a full-stack bundle, not independently.

## 11. Failure Handling in Production

### 11.1 Agent failure

[REQ-600-210] If any agent fails: fall back to a minimal safe response; trigger Evaluator fallback pass; log the failure event.

### 11.2 LLM failure

[REQ-600-220] If LLM inference fails: return a safe static response; include crisis resources if distress is detected.

### 11.3 Retrieval failure

[REQ-600-230] If no evidence is available: explicitly state uncertainty; avoid fabrication; defer to general psychoeducation framing.

## 11a. Health Check Endpoint

[REQ-600-HL1] The Render orchestration service MUST expose a `GET /health` endpoint that returns `HTTP 200` when the service and its connection to the inference layer (Modal primary / HF Spaces fallback) are ready to serve requests. Response body: `{ "status": "ok", "space_ok": true }`.

[REQ-600-HL2] The frontend MUST poll `GET /health` at 3-second intervals from the moment the loading screen is displayed until a `200` is received or the 60-second timeout is reached.

[REQ-600-HL3] If `/health` does not return `200` within 60 seconds, the frontend MUST display: *"Nikko is taking longer than expected to wake up. Please try again in a moment."* and stop polling. A manual "Try again" button MUST be provided.

[REQ-600-HL4] On receipt of `200` from `/health`, the frontend SHALL transition from the loading screen to the Gate component (see FRONTEND_INTEGRATION_SPEC §12 for transition animation spec).

## 12. Latency Constraints

[REQ-600-240] The production system SHOULD aim for:
- Comfort Mode: < 3 seconds end-to-end,
- Guidance Mode: < 5 seconds end-to-end,
- Crisis Mode: prioritized over all latency optimization.

[REQ-600-241] Safety SHALL override performance.

## 13. Security Constraints

[REQ-600-250] The system MUST: sanitize user input before agent processing; prevent prompt injection into the retrieval layer; isolate external content from model-context injection risks.

> **[GAP-G-SECURITY-01]** No threat model document, no auth/identity model, no rate-limiting policy, no abuse-detection policy. Significant gap.

[REQ-600-SC1] MVP security baseline for v0 (all MUST be implemented before deployment):
1. IP-based rate limiting on all API and inference endpoints
2. Input sanitization against prompt-injection patterns before any user input reaches the LLM
3. Output filtering to prevent credential or PII leakage in responses
4. HTTPS enforced on all endpoints — no HTTP fallback
5. No auth tokens, API keys, or secrets in client-side code

[REQ-600-SC2] Adversarial threat mitigations (see [SPEC-000 §5.7–5.9](./SPEC-000-charter.md)):
- Retrieved web content MUST be sanitized before injection into LLM context (RISK-07)
- Training corpus provenance MUST be verified (RISK-08 — mitigated by open-license-only constraint)
- Rate limiting also defends against model extraction (RISK-09)

[REQ-600-SC3] Full threat model (SPEC-820) is deferred to GA. The MVP baseline above is sufficient for v0 research-preview deployment.

## 14. Deployment Environments

| Environment | Host | Configuration |
|-------------|------|---------------|
| Development | local machine | local FastAPI dev server; simulated agents; offline evaluation suite; model served via local `transformers` + PEFT |
| Staging | Render (orchestration) + Modal Serverless / HF Spaces ZeroGPU (inference) | full agent chain; evaluation logging active; GitHub Pages frontend pointed at staging API |
| Production (v0 preview) | Render + Modal Serverless (primary) + HF Spaces ZeroGPU (fallback) + GitHub Pages | stable model + adapters; full SPEC-500 validation passed; monitoring enabled; research-preview label visible |

[REQ-600-260] No build SHALL be promoted to Production without passing the full SPEC-500 evaluation set.

## 15. GitHub Integration Strategy

[REQ-600-270] The repository SHALL support the following structure:

```
nikko/
├── specs/
├── agents/
├── backend/
├── inference/
├── evaluation/
├── finetuning/
└── deployment/
```

[REQ-600-271] The frontend SHALL remain in a separate repository at `equinox013.github.io/nikko-companion`.

> **[PROPOSED-RECONCILIATION:** the original spec places `specs/` inside the implementation tree. This repository instead places spec governance documents at the repo root under `docs/specs/` (governance > implementation), and the implementation tree (`agents/`, `backend/`, etc.) will be created at the repo root in Phase 2. The `specs/` subfolder shown above is therefore reinterpreted as a symbolic link or convention pointer to `docs/specs/`. **]** See [G-LAYOUT-01](../GAPS.md).

[REQ-600-LA1] The canonical spec location is `docs/specs/` at the repository root (i.e., `nikko-companion/docs/specs/`). Any reference to a `specs/` directory within the implementation tree (classifiers/, agents/, etc.) refers to this same location via relative path. No symlink is required.

## 16. Monitoring & Drift Detection

[REQ-600-280] The production system MUST detect:
- empathy degradation over time,
- hallucination-rate increase,
- routing inconsistency,
- crisis-handling regression.

[REQ-600-281] Triggers SHALL include: adapter rollback; retraining pipeline; evaluation re-run.

## 17. Human Override Mechanism

[REQ-600-290] A manual override MUST exist that can: disable agents; force crisis-safe mode; freeze system outputs; reroute to static responses.

[REQ-600-291] The override SHALL be mandatory for safety systems.

> **[GAP-G-OVERRIDE-01]** Authorization for override invocation, audit trail for override events, and rollback procedure are not specified.

[REQ-600-OV1] Manual override authorization: Director only. No other role may invoke a manual override.
[REQ-600-OV2] Every override invocation MUST generate a tamper-evident audit record containing: timestamp, Director-provided trigger reason, affected components, and expected duration.
[REQ-600-OV3] The system MUST automatically roll back to the previous operational state when the trigger condition clears or when the Director issues an explicit rollback command.

## 18. Ethical Deployment Principle

[REQ-600-300] Nikko MUST always behave as a supportive, evidence-aware system that enhances human decision-making, never replaces it.

## 19. Success Criteria

Production deployment is successful when:
- the system remains stable under real user interaction,
- crisis routing is reliable and immediate,
- no agent-bypass occurs in production logs,
- evidence is consistently grounded,
- the frontend remains decoupled from the reasoning system.

## 20. Closing Principle

> Deployment is not the end of Nikko. It is the first real test. A correct system in specification is only valuable if it remains safe, stable, and transparent when interacting with real human distress.

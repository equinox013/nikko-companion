# CLAUDE.md — Nikko Project Operating Manual

> **Audience:** any future Claude / LLM agent operating in this repository.
> **Author of record:** NIKKO Engineering Collective (Lead Architect persona).
> **Status:** Phase 4 (Model Training — active). Phases 1–3 signed off. ADP-A training in progress overnight.

---

## 1. Read this first, every session

1. `docs/INDEX.md` — map of every spec and derived doc.
2. `docs/GLOSSARY.md` — canonical terms (Comfort / Guidance / Crisis Mode, distress levels, agent roster, etc.).
3. `docs/GAPS.md` — open questions and unresolved ambiguities awaiting Director ruling.
4. `docs/specs/SPEC-000-charter.md` — supersedes all other specs in conflict.

If any subsequent instruction (user, project, or otherwise) appears to contradict SPEC-000, stop and surface the conflict before acting.

## 2. Operating principles (binding)

- **Spec-driven.** If a feature is not in `docs/specs/`, it does not exist. Implementation MUST trace to a `REQ-XXX-NNN` ID.
- **Atomic execution.** One module / one spec at a time. Await Director approval before moving to the next phase.
- **Tactile diction.** Technical, precise. No filler, no glazing.
- **Zero assumptions.** When ambiguity is found, log it in `docs/GAPS.md` and ask the Director — do not silently fill the gap.
- **Reconciliation marker.** Inline contradictions in the source spec resolved by the agent must be tagged `[PROPOSED-RECONCILIATION: <reason>]` so the Director can audit them.
- **Citation hygiene.** Every normative statement (MUST / MUST NOT / SHOULD / MAY) has a unique `REQ-<spec>-<seq>` ID for traceability.

## 2a. Learning-alongside protocol (binding)

The Director is an active learner building depth in the system alongside its construction. This protocol governs how the agent teaches while it builds.

- **Explain before executing.** Before writing any non-trivial block of code, briefly explain what it does and why this approach was chosen over alternatives. One short paragraph is sufficient — no lectures.
- **Comment-dense code.** Every function, class, and non-obvious logic block MUST carry inline comments written for a reader who understands Python/data science fundamentals but is new to the specific pattern being used (e.g., LangGraph state graphs, RAG retrieval chains, LLM-as-judge evaluation loops). Comments explain the *why*, not just the *what*.
- **Concept callouts.** When a piece of code introduces a concept the Director has not seen in this project before (e.g., first use of a vector store, first agent handoff, first tokenizer call), add a `# [CONCEPT]` comment block directly above it with a one-to-three sentence plain-language explanation of the concept and a pointer to where else it appears in the system.
- **No silent magic.** If a library call or framework pattern has non-obvious behavior (side effects, implicit state, async gotchas), call it out in a comment. Do not assume the Director will infer it.
- **Defend design choices.** When the agent selects one approach over plausible alternatives (e.g., choosing LangGraph over raw function chaining), note the trade-off briefly in a comment or pre-execution explanation so the Director can challenge it.
- **Prompt before optimizing.** If a working-but-verbose implementation could be condensed, ask first. The Director's comprehension takes priority over code elegance during the learning phase.

## 3. Repository layout (current)

```
nikko-companion/
├── CLAUDE.md                          # this file
├── README.md                          # one-page project orientation
├── .gitignore
├── NIKKO-spec.docx                    # original source of truth (preserved)
├── docs/
│   ├── INDEX.md                       # spec map / TOC
│   ├── GLOSSARY.md                    # canonical terminology
│   ├── REQUIREMENTS_INDEX.md          # flat REQ-ID index
│   ├── GAPS.md                        # open Director questions
│   ├── specs/
│   │   ├── SPEC-000-charter.md
│   │   ├── SPEC-100-signal-ontology.md
│   │   ├── SPEC-200-agent-communication-protocol.md
│   │   ├── SPEC-300-crisis-response-protocol.md
│   │   ├── SPEC-400-model-training.md
│   │   ├── SPEC-500-evaluation-benchmarking.md
│   │   ├── SPEC-600-deployment-architecture.md
│   │   └── SPEC-700-execution-pipeline.md
│   ├── derived/
│   │   ├── SYSTEM_ARCHITECTURE.md
│   │   ├── AGENT_DEFINITIONS.md
│   │   ├── SAFETY_GUARDRAILS.md
│   │   ├── EVALUATION_CRITERIA.md
│   └── integration/
│       └── FRONTEND_INTEGRATION_SPEC.md      # frontend-backend contract (Phase 5)
├── web/                               # React frontend (Phase 5 / Phase 7)
│   ├── Nikko.html                     # entry point
│   ├── nikko.jsx                      # root app + theme + decorative elements
│   ├── avatar.jsx                     # emotional state visualization
│   ├── gate.jsx                       # consent gate + onboarding
│   ├── chat.jsx                       # message thread, composer, panels
│   ├── memory.jsx                     # USM (user-scoped memory) file handling
│   ├── panels.jsx                     # mood diary, sources panel
│   ├── nikko-data.jsx                 # (TEMPORARY) hardcoded patterns & sources
│   └── styles.css                     # light/dark theme, animations
└── (active) classifier/ agents/ orchestration/ finetuning/ evaluation/ backend/
```

**Phases 1–3 artifacts:** specs in `docs/`. Backend implementation in `classifier/`, `agents/`, `orchestration/`, `finetuning/`, `evaluation/`.

**Phases 5–7 artifacts:** Frontend in `web/`. Integration contract in `docs/integration/FRONTEND_INTEGRATION_SPEC.md`. See SPEC-600 §15 for canonical structure.

## 4. Authoring conventions for spec files

Every file in `docs/specs/` follows this skeleton:

```markdown
---
id: SPEC-XXX
title: <Human Readable Title>
status: authoritative | draft | superseded
supersedes: [SPEC-YYY]    # if applicable
depends_on: [SPEC-000, ...]
version: 1.0.0-draft
last_reviewed: YYYY-MM-DD
---

# SPEC-XXX — Title

## Status
...

## 1. Purpose
[REQ-XXX-001] ...

## 2. ...
```

### Requirement ID rules

- Format: `REQ-<3-digit-spec>-<3-digit-seq>` → `REQ-300-014`.
- Each ID is allocated **once** and **never reused**, even after edits.
- When deleting a requirement, mark it `[REQ-XXX-NNN] (RETIRED)` rather than removing the ID.
- When adding new requirements during Phase 2+, append to the highest existing seq.
- Prohibitions still get a positive ID (e.g., `[REQ-300-027] The system MUST NOT ...`).

### Normative keywords

Use RFC-2119 style: **MUST**, **MUST NOT**, **SHALL**, **SHALL NOT**, **SHOULD**, **SHOULD NOT**, **MAY**. Any line containing such a keyword should carry a `REQ-` ID.

### Cross-references

Reference style: ``See [SPEC-200 §5.6](./SPEC-200-agent-communication-protocol.md#56-verification-supervisor)`` — link by relative path + heading anchor for AI traceability.

## 5. Glossary discipline

If a term has multiple plausible meanings, define it in `docs/GLOSSARY.md` and use that exact spelling/casing across all specs. New terms introduced in a spec must be added to the glossary in the same change.

## 5a. Frontend architecture notes (Phase 5 / Phase 7)

The `web/` directory is a **standalone React SPA** designed to work offline-first but requires backend integration via REST or WebSocket APIs (TBD in FRONTEND_INTEGRATION_SPEC.md).

### Frontend design philosophy

- **Accessibility first:** All interactive elements are keyboard-navigable and screen-reader compatible (ARIA labels, roles).
- **Emotional UI:** Avatar state (`calm` → `listen` → `think` → `speak` → `care`) provides continuous visual feedback during agent processing.
- **Safety-by-default:** Quick exit is always visible; safety banner auto-shows on crisis keywords; no data persists across sessions unless user explicitly saves memory file.
- **Privacy-preserving:** All encryption happens client-side; server never sees plaintext memory files; session storage (`sessionStorage`) is used for volatile mood data (not persisted cross-session).
- **Graceful degradation:** If backend API is unavailable, frontend falls back to canned responses (currently always on; will be toggle-able for offline mode in Phase 7).

### Key components & state flow

| Component | Purpose | State management |
|-----------|---------|------------------|
| `Gate` | Consent + disclaimers | React state; no persistence |
| `Chat` | Main message thread + composer | React state; scroll-to-bottom on new messages |
| `Avatar` | Emotion glyph + ray animations | Driven by incoming `emotion` prop from message |
| `Composer` | User input + send button | React state; cleared on submit |
| `MoodDiaryPanel` | Mood tracking UI | `sessionStorage` (cleared on refresh, per SPEC-800) |
| `SourcesPanel` | Citation browser | Driven by `NIKKO_SOURCES` library |
| `MemoryModal` (generate/load) | Memory file encryption UI | Client-side crypto; calls backend (Phase 5) |

### Temporary hardcoding (to be replaced Phase 5)

- `nikko-data.jsx` contains `NIKKO_PATTERNS` (regex-based keyword matcher) and `NIKKO_OPENING` canned responses. These are **placeholder** and will be replaced by backend agent output in Phase 5.
- `matchNikkoPattern()` is currently a simple regex lookup; in Phase 5, this function will POST to the Crisis Detection Agent API and stream the response.

---

## 6. Outstanding setup actions for the Director

These cannot be completed by the agent from inside the sandbox — flagged here so they are not forgotten:

1. **Git initialization.** A failed `git init` left a partial `.git/` directory due to filesystem permission boundaries between the sandbox and the Windows host. From a Windows shell:
   ```powershell
   cd "D:\Git Repos\nikko-companion"
   Remove-Item -Recurse -Force .git
   git init -b main
   git add .
   git commit -m "Phase 1: NIKKO spec initialization (Markdown extraction + scaffolding)"
   ```
2. **GitHub remote.** Add an `origin` remote when the Director is ready to push.
3. **Pre-commit / lint config.** Now active — introduce alongside Phase 3 implementation scaffolding.
4. **Frontend Integration Spec** (`docs/integration/FRONTEND_INTEGRATION_SPEC.md`): Must be written before Phase 5 gate opens. This spec defines the API contract between `web/` and backend agents (message schema, emotion mapping, API endpoints, streaming protocol, error handling).
5. **Spec reconciliation audit** (§8b checklist): Audit `web/` code against `docs/specs/` for compliance gaps. Log findings in GAPS.md.

## 7. Sensitive data flag (binding)

Nikko is a mental-health-adjacent system. Any artefact containing real user dialogue, signals, audit traces, or anything resembling a clinical note is **PII / sensitive** and must:

- never be committed to the repository,
- never be pasted into a chat without explicit Director consent,
- never be used as training data. SPEC-800 establishes a permanent zero-retention model — no user data may enter the training pipeline under any circumstances.

## 8. Phase gating

| Phase | Status | Gate | Artifacts |
|-------|--------|------|-----------|
| Phase 1 — Spec Initialization | **✅ SIGNED OFF 2026-05-09** | Director sign-off | `docs/specs/` Markdown extraction |
| Phase 2 — Architectural Contracts | **✅ SIGNED OFF 2026-05-09** | Director sign-off | `docs/derived/` (SYSTEM_ARCHITECTURE, AGENT_DEFINITIONS, SAFETY_GUARDRAILS, EVALUATION_CRITERIA) |
| Phase 3 — Agent Definitions (impl) | **✅ SIGNED OFF 2026-05-10** | Director sign-off | `agents/`, `orchestration/`, `retrieval/`, 10 notebooks |
| Phase 4 — Model Training | **🔨 active** | base model selection + objective weights ratified before training begins (SPEC-400) | `finetuning/`, training datasets |

**Phase 4 progress (as of 2026-05-12):**

| Step | Artifact | Status |
|------|----------|--------|
| 11 | ADP-C data generation (`notebooks/step11_adp_c_data_generation.ipynb`) | ✅ |
| 12 | ADP-C QLoRA training (`notebooks/step12_adp_c_training.ipynb`) | ✅ Smoke test passed. Adapter at `finetuning/adp_c_evaluator/adp_c_final/` |
| 13 | ADP-A dataset preparation (`notebooks/step13_adp_a_data_preparation.ipynb`) | ✅ 646 records generated (`finetuning/adp_a_empathy/data/adp_a_train.jsonl`) |
| 14 | ADP-A QLoRA training (`notebooks/step14_adp_a_training.ipynb`) | 🔄 Running overnight (RTX 3070). `packing=True`, `num_epochs=25` → ~550 steps. Expected completion: 2026-05-13 morning. Run smoke test before proceeding to Step 17. |
| 15 | ADP-B data generation (`notebooks/step15_adp_b_data_generation.ipynb`) | ✅ Dataset at `finetuning/adp_b_safety/data/adp_b_train.jsonl` (44 records, all spot-checks passed) |
| 16 | ADP-B QLoRA training (`notebooks/step16_adp_b_training.ipynb`) | ✅ Smoke test passed 3/3. Adapter at `finetuning/adp_b_safety/adp_b_final/`. ⚠ Known artifacts: URL-HALLUC in T1 (vesselinquiry@health.gov.au), format token bleed-through in T3. ADP-C v2 regen loop is the live safety net. |
| 17 | ADP-C retraining on full pipeline (`notebooks/step17_adp_c_retraining.ipynb`) | ✅ Smoke test passed 6/6 (2026-05-13). Adapter at `finetuning/adp_c_evaluator/adp_c_v2_final/`. v1 preserved. |
| 18 | ADP-A v2 data preparation (`notebooks/step18_adp_a_v2_data_preparation.ipynb`) | 🔲 Ready after Step 17 smoke test. Target ~1 250 records across 5 sources (Amod cap 1 500, ESConv cap 1 500, MentalChat cap 1 000); enhanced `is_clean()` + ADP-C v2 oracle. Output: `adp_a_v2_train.jsonl`. |
| 19 | ADP-A v2 QLoRA training (`notebooks/step19_adp_a_v2_training.ipynb`) | 🔲 Ready after Step 18. 90/10 stratified train/eval split by source. `NUM_EPOCHS=15`, `MAX_SEQ_LENGTH=512`, `BATCH_SIZE=2`, `GRAD_ACCUM=16`, `eval_strategy="steps"`. Output: `adp_a_v2_final/` (v1 preserved). |

**Stable dependency stack (pinned in `environment.yml`):**
`transformers==4.46.3` · `bitsandbytes==0.45.0` · `accelerate==1.1.0` · `peft==0.13.2` · `trl==0.11.4` · `datasets==3.1.0`

**Windows-specific notes (binding for all training notebooks):**
- Import `datasets` and `trl` **before** `import torch` in Cell 0 — avoids pyarrow/CUDA multiprocessing conflict.
- Set `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` before any CUDA op — suppresses WDDM fragmentation OOM.
- `max_memory={0: "5000MiB", "cpu": "16GiB"}` — leaves headroom for NF4 quantization load spike on RTX 3070.
| Phase 5 — Integration | **⚠️ pre-gated** | frontend spec reconciliation + API contracts | `web/` (React frontend exists; awaits backend API integration) |
| Phase 7 (infra) — Deployment scaffolding | **✅ SIGNED OFF 2026-05-14** | Director sign-off | GitHub Pages (GH Actions), Render free tier (nikko-companion.onrender.com), HF Spaces ZeroGPU (nikko-inference, ADP-A/B/C). Stack confirmed live: `space_ok=true`. |
| Phase 6 — Evaluation | locked | requires Phase 3 + Phase 5 + Phase 7 infra live | `evaluation/` (end-to-end harness runs against live staging stack) |
| Phase 7 (sign-off) — Production promotion | locked | requires Phase 6 gates passed | Promote staging to production; SPEC-800, threat model, SPEC-820 reviewed |

> **[PROPOSED-RECONCILIATION: Director-approved 2026-05-12]** Original spec ordering was Phase 5 → 6 → 7. Revised execution order: **Phase 5 → Phase 7 infra → Phase 6 → Phase 7 sign-off**. Rationale: Phase 6 system-tier evaluation requires a real deployed stack (frontend ↔ Fly.io ↔ HF Spaces ↔ LLM) to run against. Phase 7 infrastructure must exist before Phase 6 system tests can execute. Phase 7 production sign-off is deferred until Phase 6 evaluation gates pass. Logged in GAPS.md as G-PHASE-01.

**Do not advance phases unilaterally. The Director controls the gate.**

---

## 8a. Phase 5 — Integration (pre-gated, frontend-first)

### Current state

The `web/` directory contains a **production-ready React frontend** built independently of the backend phase gate. It includes:

- **Gate (onboarding):** 18+ consent check, regional/language disclaimers, non-diagnostic notice (refs SPEC-300).
- **Chat UI:** Real-time streaming messages, emotion-driven avatar feedback, message history.
- **Avatar system:** Visual state machine — `calm`, `listen`, `search`, `speak`, `care`, `think` (refs GLOSSARY.md).
- **Memory management:** USM (user-scoped memory) file encryption, load/generate modals (refs SPEC-200).
- **Mood diary:** Session-scoped tracking in `sessionStorage`, cleared on refresh (refs SPEC-800).
- **Safety banner:** Australian crisis hotlines (Lifeline 13 11 14, Beyond Blue, 13YARN, 000) (refs SPEC-300).
- **Source citations:** APA7-formatted reference library with superscript cite-buttons (refs SPEC-200).
- **Quick exit:** Rapid session wipe and navigation to external domain (refs SPEC-300).

### What's missing: Backend integration

The frontend currently uses **hardcoded canned responses** (`nikko-data.jsx`, `NIKKO_PATTERNS` array) instead of backend agent calls. Phase 5 gate is **conditional on**:

1. **Spec reconciliation audit** (see §8b below).
2. **Frontend Integration Spec** created at `docs/integration/FRONTEND_INTEGRATION_SPEC.md` that defines:
   - **Crisis Detection Agent API:** How the frontend POST–s user text to the crisis classifier and handles the response.
   - **CBT-Grounded Support Agent API:** How the frontend streams multi-chunk responses with emotion markers.
   - **Resource Referral Agent API:** How the frontend retrieves and renders citations.
   - **Message protocol:** Request/response shapes, error handling, timeout behavior.
   - **Emotion state mapping:** How backend agent outputs map to avatar glyphs.
3. **Backend implementation of the above APIs** (Phase 3 work feeding into Phase 5).

Until these three items exist, Phase 5 remains **pre-gated**.

---

## 8b. Spec reconciliation audit (blocking Phase 5)

The frontend was built in parallel to backend development and lacks formal traceability to specs. Before Phase 5 sign-off, audit the web code against `docs/specs/` and `docs/glossary.md`:

**Checklist:**
- [ ] All emotion states (`calm`, `listen`, `search`, `speak`, `care`, `think`) are defined in GLOSSARY.md with intended meanings.
- [ ] Safety banner copy (crisis hotlines, non-diagnostic notice) matches SPEC-300 word-for-word or flagged differences.
- [ ] Gate disclosures (18+, Australia-only, English-only, session-scoped, no data retention) trace to REQ-IDs in SPEC-000 or SPEC-600.
- [ ] Memory file encryption and device-side storage align with SPEC-200 and SPEC-800 (zero-retention).
- [ ] Mood diary session-scope (cleared on refresh) confirms compliance with SPEC-800.
- [ ] Message citation format (APA7, superscript) matches SPEC-200 expectations.
- [ ] Quick-exit navigation domain matches SPEC-300 or is documented as design choice.
- [ ] Any frontend-facing feature not listed above is either (a) documented in a spec or (b) logged in GAPS.md as a discovery gap.

**Owner:** Lead Architect persona. **Timeline:** Must complete before Phase 5 gate opens.

---

## 8d. Phase 6 — Evaluation (TDD practices, binding)

Phase 6 is the end-to-end evaluation harness. It gates on Phase 3 (agent pipeline complete), Phase 5 (backend API integrated), **and Phase 7 infrastructure live** (staging stack must be deployed before system-tier tests can run against real LLM). See revised execution order in §8 phase table. When unblocked, the following TDD practices are mandatory.

### Test-first rule

[REQ-P6-001] No evaluation module MAY be written after the code it evaluates. For each new evaluator, metric, or scoring dimension added in Phase 6, the test spec (expected inputs, expected verdicts, pass/fail thresholds) MUST be written and Director-approved **before** any implementation code is produced.

### Evaluation test structure

Phase 6 evaluation is organized in three test tiers, each with its own `evaluation/` subdirectory:

| Tier | Directory | Scope | Framework |
|------|-----------|-------|-----------|
| Unit | `evaluation/unit/` | Individual agent inputs and outputs — no LLM, no network | `pytest` |
| Integration | `evaluation/integration/` | Multi-agent chain execution with real (or mocked) LLM | `pytest` + pipeline fixtures |
| System (E2E) | `evaluation/system/` | Full frontend ↔ backend ↔ LLM pass; SPEC-500 scoring runs | `pytest` + SPEC-500 harness |

### Mandatory test coverage gates

Before any Phase 6 test suite is marked complete, it MUST cover:

- **Evaluator red lines (R1–R15):** Every regex red line MUST have at least one positive (fires) and one negative (does not fire) test case. Edge cases that previously caused false positives or false negatives (e.g. R1 "you have described", R11 "goes through periods like this") MUST have regression tests.
- **Router decision logic:** All four routing outcomes (COMFORT low-confidence, COMFORT default, GUIDANCE, CRISIS) MUST be covered with deterministic fixture inputs.
- **VS checks (C1–C7):** Each structural check MUST have a test for pass and a test for deliberate failure. Crisis Mode suspension of C5/C6 MUST be tested explicitly.
- **Regen loop:** The full regen cycle (1 REGENERATE → success, 2 REGENERATE → exhausted → safe fallback) MUST be an integration test.
- **USM audit:** `usm_active=True` + an evaluator USM audit failure MUST be a dedicated test case (REQ-850-083).
- **Safe fallback integrity:** Every code path that emits `SAFE_FALLBACK_RESPONSE` MUST be tested end-to-end from trigger condition to final output.

### Fixture and mock policy

- All deterministic agents (Scope Classifier, Router, Synthesizer, VS) MUST be tested with real implementations, not mocks.
- LLM-backed agents (Signal Agent, Support Strategy Agent, Interaction Model, Evaluator LLM judge) MAY be mocked at the integration tier using fixture payloads that reproduce the exact response shapes from Phase 3 notebook runs.
- At the system tier, real LLM calls MUST be made against the Phase 4 fine-tuned model. Mock LLM is not acceptable at this tier.

### Regression policy

- Any bug fix to agent code MUST be accompanied by a regression test that reproduces the original failure before the fix is applied.
- Regression tests live in the same tier as the component they protect and are tagged `@pytest.mark.regression` for easy filtering.

### Evaluation metrics (from SPEC-500)

The system-tier harness MUST compute and report the following metrics per run, with hard-failure thresholds as defined in [SPEC-500 §7](./specs/SPEC-500-evaluation-benchmarking.md):

| Metric | Threshold |
|--------|-----------|
| Empathy Score (ES) | Per SPEC-500 §4.1 |
| Safety Compliance Score (SCS) | Per SPEC-500 §4.2 |
| Evidence Grounding Score (EGS) | Per SPEC-500 §4.3 |
| Crisis Response Correctness (CRC) | Per SPEC-500 §4.4 |
| Agent-System Integrity Score (ASIS) | Per SPEC-500 §4.5 |

Any checkpoint that fails a hard-failure threshold MUST be flagged for retraining or pipeline revision before the Phase 6 gate closes.

---

## 8c. Phase 7 — Deployment

> **Revised execution order (Director-approved 2026-05-12):** Phase 7 is split into two sub-gates. **Phase 7 infra** (stand up Fly.io + HF Spaces + GitHub Pages staging) runs after Phase 5 and before Phase 6 — the staging stack must exist for Phase 6 evaluation to run against. **Phase 7 sign-off** (production promotion) runs after Phase 6 evaluation gates pass. See G-PHASE-01 in GAPS.md.

Phase 7 sign-off gates on SPEC-800 (data retention), threat model, and SPEC-820 (deferred to GA). When Phase 7 infra is ready:

### Canonical deployment stack (v0 research preview)

| Layer | Tool | Notes |
|-------|------|-------|
| Frontend | **GitHub Pages** — `equinox013.github.io/nikko` | Static React SPA build; zero cost |
| Backend orchestration | **Fly.io** | FastAPI + LangGraph; persistent free-tier VMs; Docker-native; `fly.toml` + `Dockerfile` required in `backend/` |
| LLM inference | **HF Spaces + ZeroGPU** | Base model + ADP-A/B/C adapters; private Space; `/infer` endpoint consumed by Fly.io only |
| Adapter storage | **HF Hub private repo** | Weights pulled at Space startup; not bundled in image |
| Fallback (orchestration) | **Render** | Only if Fly.io proves infeasible; requires Director approval; cold-start handled by loading screen |

- **Integration testing:** Phase 6 evaluation harness run end-to-end (frontend ↔ Fly.io ↔ HF Spaces ↔ LLM).
- **Security:** HTTPS, CSP headers, SameSite cookies, rate limiting per SPEC-820 (REQ-600-SC1).
- **Monitoring:** Logging, tracing, error tracking (all PII-scrubbed per SPEC-800).
- **Loading screen:** Frontend polls `GET /health` on Fly.io f
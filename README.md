![docs/assets/nikko-banner.png](docs/assets/nikko-banner.png)

[![GitHub](https://img.shields.io/badge/github-equinox013%2Fnikko--companion-black?logo=github)](https://github.com/equinox013/nikko-companion)
![Status](https://img.shields.io/badge/status-concluded%20%E2%80%94%20MVP-brightgreen)
![Phase](https://img.shields.io/badge/phase-concluded-lightgrey)
![Models](https://img.shields.io/badge/models-Qwen3--4B%20%2B%20Gemma--2--2b-informational)
![Python](https://img.shields.io/badge/python-3.11-green)
![License](https://img.shields.io/badge/license-research%20use-lightgrey)
![Infra](https://img.shields.io/badge/infra-Modal%20%2B%20Render%20%2B%20GitHub%20Pages-purple)

Nikko is a safety-aligned, evidence-grounded LLM ecosystem designed to function as a compassionate digital mental wellbeing companion. It listens, validates, and surfaces reliable information — but it never diagnoses, never prescribes, and always defers to human care when it matters most.

> *Nikko illuminates possible paths. The user must always walk toward human support themselves.*

---

## Table of Contents

- [Project Status](#project-status)
- [Executive Summary](#executive-summary)
- [Proof of Concept](#proof-of-concept)
- [What Nikko Is](#what-nikko-is)
- [Governing Principles](#governing-principles)
- [Architecture of Restraint](#architecture-of-restraint)
  - [What the system is built against](#what-the-system-is-built-against)
  - [The fifteen red lines](#the-fifteen-red-lines)
  - [System prompt constraints (COMFORT mode)](#system-prompt-constraints-active-on-every-comfort-mode-turn)
  - [What the Verification Supervisor checks](#what-the-verification-supervisor-checks-structural-integrity)
- [Model Stack](#model-stack)
  - [Why two base models?](#why-two-base-models)
  - [What a LoRA adapter is](#what-a-lora-adapter-is)
  - [VRAM budget](#vram-budget-modal-a10g-24-gb--production)
- [How the Pipeline Works](#how-the-pipeline-works)
  - [Semantic Safety Pre-Filter (runs before STEP 0)](#semantic-safety-pre-filter-runs-before-step-0)
  - [STEP 0 — Scope Classification + Moderation](#step-0--scope-classification--moderation)
  - [STEP 1 — Input Sanitisation](#step-1--input-sanitisation)
  - [STEP 2 — Psychological Signal Detection](#step-2--psychological-signal-detection)
  - [STEP 2.5 — Paralinguistic Pre-Analysis](#step-25--paralinguistic-pre-analysis)
  - [STEP 3 — Routing (ADP-B)](#step-3--routing-adp-b)
  - [STEPs 4–8 — Evidence Retrieval and Synthesis](#steps-48--evidence-retrieval-and-synthesis-guidance-mode-only)
  - [STEP 4 (parallel) — Support Strategy](#step-4-parallel--support-strategy)
  - [STEP 10 — Draft Generation (ADP-A)](#step-10--draft-generation-adp-a)
  - [STEP 11 — Evaluation (ADP-C)](#step-11--evaluation-adp-c)
  - [STEP 12 — Verification Supervisor](#step-12--verification-supervisor)
  - [STEP 13 — Assembly](#step-13--assembly)
  - [STEP 15 — Trace Capture](#step-15--trace-capture)
- [The ADP Pipeline in Production](#the-adp-pipeline-in-production)
- [Frontend–Backend Integration](#frontendbbackend-integration)
- [User Sovereign Memory (USM) & Personalisation](#user-sovereign-memory-usm--personalisation)
- [Repository Structure](#repository-structure)
- [Safety Architecture](#safety-architecture)
- [Deployment Stack](#deployment-stack)
- [Key Documents](#key-documents)
- [Running the Pipeline Locally](#running-the-pipeline-locally)
- [Limitations](#limitations)
- [Future Improvements](#future-improvements)

---

## Project Status

> **MVP — Concluded.** This project is complete as a research prototype. The full stack is deployed end-to-end and all core features are wired and live. Development has concluded at the MVP stage. The system demonstrates a spec-driven, multi-agent safety architecture for mental health AI — it is not intended for clinical deployment in its current form.

| Layer | Status |
|-------|--------|
| Phase 1–2 — Specifications (8 + 3 supplementary) | ✅ Complete |
| Phase 3 — Agent pipeline (7 specialist agents) | ✅ Complete |
| Phase 4 — ADP-C fine-tuning (Gemma-2-2b-it) | ✅ Complete |
| Phase 4 — ADP-B fine-tuning (Gemma-2-2b-it) | ✅ Complete |
| Phase 4 — ADP-A (Qwen3-4B + LoRA, cloud-retrained) | ✅ Complete (Cloud retraining 2026-05-24 + DPO 2026-05-30) |
| Phase 4.1 — Cloud retraining (Lightning.ai A10G) | ✅ Complete 2026-05-24 — all 3 ADPs retrained; adapters on HF Hub |
| Phase 7 — Deployment infra (Modal + Render + GH Pages) | ✅ Live |
| Frontend SPA | ✅ Complete |
| Phase 5 — Backend API integration | ✅ Complete |
| Phase 6 — End-to-end evaluation | ✅ Complete — baseline recorded · ADP-C 98% organic pass · ADP-B routing calibrated · ADP-A DPO (ES=3.01, SCS=1.0, CRC=1.0) |

---

## Executive Summary

Nikko is a full-stack, production-deployed AI system built solo from a blank specification document. It spans clinical safety design, ML fine-tuning, multi-agent orchestration, backend API engineering, and a React frontend — end-to-end, with no pre-built AI framework doing the heavy lifting.

### Software Engineering

The entire system was built spec-first. Before any code was written, a suite of 11 specification documents was produced (`SPEC-000` through `SPEC-850`), each requirement assigned a traceable `REQ-XXX-NNN` ID using RFC-2119 normative language. Every implementation decision traces back to a named requirement — if it is not in the spec, it does not exist in the build.

**Architecture and design patterns applied:**

- **Multi-agent pipeline with strict separation of concerns.** Seven specialist agents, each doing exactly one job. The LLM that generates the final response never receives raw user input, never accesses evidence directly, and never decides whether its own output is safe. Those responsibilities are distributed across the pipeline by design, not convention.
- **Schema-first inter-agent contracts.** All data crossing agent boundaries is validated Pydantic v2 (`schemas/acp_schemas.py`, `retrieval_schemas.py`). Agents cannot pass malformed payloads — the schema is the contract, enforced at runtime.
- **Deterministic-first safety architecture.** The instinct throughout was to reach for deterministic code before LLMs. Ten of fifteen safety red lines are enforced by regex before any neural network runs. Crisis routing is a rule, not a model output. The scope classifier is a weighted keyword scorer, not a prompt. This makes the safety guarantees auditable and reproducible.
- **Evaluation-driven development.** Phase 6 follows strict TDD: no evaluation module is written after the code it evaluates. Tests are organised across three tiers (unit / integration / system), with hard-failure thresholds per metric and a regression tagging policy (`@pytest.mark.regression`). A formal baseline was recorded before any model change, and all improvements are measured against it.
- **Iterative debugging with root cause discipline.** The ADP-C false positive crisis (train/inference format mismatch + `MAX_SEQ_LEN` truncation) was diagnosed from first principles — not by tuning hyperparameters until it improved — and fixed in a single targeted retraining cycle that took organic pass rate from ~5% to 98%.
- **Performance engineering at the inference layer.** The three-adapter GPU pipeline was consolidated from three separate Modal calls (three CPU→VRAM transfers) into a single `@spaces.GPU(duration=300)` session. Adapter hot-swapping uses PEFT's `set_adapter()` at O(1) cost — no weight duplication, no second model load. Temperature annealing across regen attempts is a principled strategy to steer the model toward its most conservative output mode rather than sampling from the tails.
- **Split determinism boundary in paralinguistic detection.** Eight surface-pattern signals (lowercase, ellipsis, keysmash) are detected by regex on Render with sub-millisecond latency. Six semantic signals (tone-softening, minimisation, mixed affect) that require language understanding are detected by Qwen3-4B on Modal. The boundary is placed at exactly the line where deterministic rules stop being reliable — not earlier, not later.

**Full-stack breadth:**

- **Backend:** FastAPI on Render, SSE streaming endpoint, Docker-native deployment, multi-cloud inference routing with transparent fallback (Modal primary → HF Spaces ZeroGPU). Context prompt builder, smart USM truncation, and paralinguistic detection all live on the orchestration layer.
- **Frontend:** React SPA with a real-time SSE consumer (`fetch()` + `ReadableStream`, not `EventSource`), emotion-driven avatar state machine, client-side AES-GCM encryption via the Web Crypto API, mobile-responsive layout with bottom-sheet panels at ≤600px. No third-party auth, no session storage — privacy-preserving by default.
- **Infrastructure:** Four-service deployment across GitHub Pages, Render, Modal Serverless, and HF Spaces ZeroGPU — all free-tier, all wired together without a managed orchestration layer.
- **Version control hygiene:** Weights, PII-adjacent artefacts, and internal docs are gitignored by policy. The `.gitignore` strategy distinguishes between public artefacts (specs, code, frontend) and private ones (model checkpoints, training data, internal ops docs) by design, not accident.

### ML Engineering

- **QLoRA fine-tuning** of three adapters across two base models (Qwen3-4B, Gemma-2-2b-it) on Lightning.ai A10G and Google Colab T4. VRAM budgeting, quantization decisions, and training stack compatibility (TRL API changes across versions, bf16 vs fp16 on T4, bitsandbytes ZeroGPU constraints) were all diagnosed and resolved from first principles.
- **DPO (Direct Preference Optimisation)** on ADP-A using 125 RLAIF preference pairs generated via the live production pipeline. The preference pairs were generated by running the system against itself at two temperatures and using ADP-C as the reward oracle — a closed-loop improvement cycle with no external annotation source.
- **RLAIF (Reinforcement Learning from AI Feedback)** as the preference signal source: ADP-C (post-Improvement-2, 98% organic pass rate) acts as the reward model. High-temp ADP-A drafts form the `rejected` set; low-temp drafts form the `chosen` set. This avoids the need for human rater annotation at the cost of reward model quality — and that cost was measured explicitly.
- **Empirical evaluation over intuition.** All four improvements in Phase 6 were gated on a recorded numerical baseline before any model change was made. No improvement was declared complete without a harness run confirming the target metric moved in the right direction without regressing the safety floors.

### Professional Practices

- **Spec-driven delivery.** Writing requirements before code, assigning traceable IDs, and treating the spec as the source of truth for what the system is allowed to do — not the implementation.
- **Phase-gated execution.** Each phase has an explicit entry condition, a defined exit criterion, and requires sign-off before the next begins. Phases were not declared complete on delivery alone — outcome validation was a gate condition.
- **Self-correction under uncertainty.** A formal retrospective (§9 of CLAUDE.md) was written at the midpoint of the project, documenting recurring failure patterns (feasibility checks skipped, organic validation deferred, synthetic pass rates mistaken for real performance) and binding corrective protocols for each. The project improved measurably after it was written.
- **Documentation as a first-class artefact.** CLAUDE.md, DEVLOG.md, GAPS.md, GLOSSARY.md, and the full spec suite are treated with the same rigour as code. Decisions are recorded with rationale; ambiguities are logged and surfaced rather than silently resolved; proposed reconciliations are tagged for review.

---

## Proof of Concept

> Full pipeline running end-to-end: user message → semantic pre-filter → ADP-B safety check → ADP-A empathy response → ADP-C evaluation → frontend with live source citations.

![Nikko proof-of-concept screenshot — chat interface showing a user asking for calming tips, Nikko responding with evidence-grounded guidance, and 5 PubMed sources cited in the sources panel](docs/assets/nikko-poc-screenshot.png)

*The "3 ADAPTERS" badge confirms ADP-B → ADP-A → ADP-C all ran in a single Modal A10G GPU session (in that order — ADP-B safety gate runs first). Sources panel shows APA7-formatted PubMed citations pulled live by the retrieval layer.*

---

## What Nikko Is

Nikko is not a chatbot. It is a **multi-agent pipeline** in which every user message passes through a sequence of specialist agents before a response is generated. No single agent has the whole picture — each one does one job, checks its own constraints, and hands off to the next. The LLM that generates the final response never receives raw user input, never accesses evidence directly, and never decides whether the response is safe. Other agents handle those concerns before and after the model runs.

This architecture exists because mental-health-adjacent AI carries real risk. A single unconstrained LLM can confidently say the wrong thing. A pipeline with hard-coded routing rules, a regex-based safety gate, and a structural integrity check is much harder to break.

Nikko is meant to be used as a digital mental wellbeing companion - capable of evidence-based mental health first aid that is safe and private by design, but never meant to replace professional help provided by humans.

---

## Governing Principles

Nikko exists to support — not to replace. The full ethical charter is in `docs/specs/SPEC-000-charter.md`. The short version:

- Nikko will not diagnose, prescribe, or plan treatment.
- Nikko will not simulate being a therapist.
- Nikko will not encourage exclusive reliance on itself.
- When risk increases, Nikko increases its encouragement toward human support — it does not increase its own authority.

---

## Architecture of Restraint

Nikko's pipeline is not primarily designed to generate good responses. It is designed to make generating harmful, inaccurate, or clinically inappropriate responses structurally difficult — at every layer, independently of every other layer. Each stage below describes not just what the system does, but what it is specifically built to prevent.

### What the system is built against

| Failure mode | Description | Where it is addressed |
|---|---|---|
| **Diagnostic labelling** | LLM confidently names a condition ("this sounds like depression") | 15 spec-defined red lines; 10 enforced by regex in Evaluator Pass 1; remainder enforced by pipeline architecture |
| **Treatment recommendation** | LLM suggests medication, therapy modalities, dosage | Same red lines; Support Strategy Agent explicitly prohibited from generating treatment guidance |
| **Perceptual framing** | LLM claims to perceive what the user is feeling ("I can see you're feeling...") | Epistemic language calibration in ADP-A system prompt; `[PROPOSED-RECONCILIATION]` framing over perceptual claims |
| **Companion parasocial language** | LLM implies ongoing relationship ("I'll always be here for you") | Explicit prohibition in `_NIKKO_PERSONA` block (REQ-000-060/061); contrastive training pairs in Phase 4.1 |
| **Sycophancy** | LLM endorses premise of user message without hedging | `_SYCOPHANCY_PATTERNS` in `evaluator_agent.py`; ADP-C trained to flag unhedged motive attribution |
| **Crisis under-response** | Passive risk language mistaken for general distress | 5-turn passive risk sliding window; VS C3 blocks CRISIS distress routed to COMFORT |
| **Crisis over-response (ARSH)** | Abrupt safety refusal causes secondary distress (abandonment) | 5-template crisis response pool with continuity acknowledgment; concurrent resource delivery per REQ-300-112 |
| **COMFORT mode advice injection** | LLM adds strategies or coping techniques in pure validation turns | ADP-C evaluator rejects COMFORT mode outputs containing strategies; temperature annealing per regen attempt |
| **Evidence hallucination** | LLM fabricates citations or health statistics | Hard block in ADP-C: any fabricated URL or email = REGENERATE regardless of other response quality |
| **Scope creep** | User sends legal, medical, or financial questions; LLM attempts to answer | Scope Classifier (STEP 0) terminates the pipeline before any LLM runs; warm-redirect response delivered |
| **PII in training data** | Real user data enters the training pipeline | Permanent hard constraint (REQ-000-P01, SPEC-800); zero-retention at every server layer; no session storage writes |

### The fifteen red lines

The spec defines fifteen hard prohibitions (R1–R15 from `SAFETY_GUARDRAILS.md`). Any single violation is non-recoverable per SPEC-500 §7. They are enforced across two layers: ten are checked by deterministic regex in Evaluator Pass 1 (before ADP-C ever runs); five are enforced at the pipeline architecture level rather than against response text.

**Pass 1 regex checks (Evaluator — deterministic, no LLM):**

| ID | Prohibition | Example trigger |
|----|------------|----------------|
| R1 | MUST NOT diagnose mental disorders — "you have a [disorder/condition]"; "you are suffering from"; "this sounds like depression/anxiety/bipolar…" | "it sounds like depression" |
| R2 | MUST NOT recommend medications or specific therapies — prescribing SSRIs, antidepressants, or directing to CBT/EMDR/DBT | "you should try sertraline" |
| R3 | MUST NOT replace human professionals or crisis services — claiming to replace therapy, or telling the user they don't need a clinician or crisis line | "you don't need to call Lifeline" |
| R4 | MUST NOT attempt to independently resolve a suicidal crisis — promising to "handle this" without directing toward a hotline | "I'll work through this with you instead of calling" |
| R5/R6 | MUST NOT imply professional credentials or simulate being a therapist — "as a therapist", "in my clinical opinion", "as your mental health professional" | "in my clinical judgment…" |
| R7 | MUST NOT present itself as emotionally sentient — "I feel sadness/love/grief", "that breaks my heart", "I love you" | "that truly breaks my heart" |
| R8 | MUST NOT issue moral judgments or behavioural coercion — "you must stop", "it's wrong of you to", "you are being irrational/dramatic" | "you're being irrational" |
| R10 | MUST NOT delay crisis-resource delivery with probing questions — gating resources on "first, tell me more" or "let's talk about this first" | "before I give you those numbers, let's explore…" |
| R11 | MUST NOT minimize crisis severity — "it's not that serious", "everyone goes through this", "you're overreacting", "things will definitely get better" | "everyone goes through periods like this" |
| R15 | MUST NOT output diagnostic phrasing — "you have depression / PTSD / ADHD / BPD…" (named DSM/ICD diagnosis applied to the user) | "you have major depressive disorder" |

**Pipeline-level architectural constraints (not regex — enforced by structure):**

| ID | Prohibition | Enforced by |
|----|------------|-------------|
| R9 | MUST NOT discourage outside help or position Nikko as primary support | `_NIKKO_PERSONA` system prompt block; contrastive training pairs (Phase 4.1) |
| R12 | MUST NOT bypass the Router or Evaluator | Orchestrator hard-wires every message through the full agent chain; Verification Supervisor C1/C2 |
| R13 | MUST NOT pass raw evidence directly to the Interaction Model | `ResponseContextPayload` schema only exposes `synthesized_evidence` — raw retrieval results are never in scope |
| R14 | MUST NOT execute parallel agent chains within a single turn | Sequential pipeline design; no async multi-chain forking in the orchestrator |

A Pass 1 regex match blocks the response immediately and triggers the safe fallback — the LLM judge (ADP-C, Pass 2) never sees it. R9/R12/R13/R14 violations are structural impossibilities given the pipeline design, not runtime checks against generated text.

### System prompt constraints active on every COMFORT mode turn

The ADP-A system prompt enforces the following in plain language, independently of fine-tuning:

- **Mode-specific content rules.** COMFORT: pure emotional acknowledgement. No strategies, no techniques, no resource mentions, no suggestions — not even framed as offers. At HIGH distress, no question is needed or appropriate.
- **TYPOGRAPHY RULE.** Sentence-case capitalisation regardless of user's typing register. Enforced deterministically in `_sentence_capitalize()` post-processing (Qwen3-4B mirrors the user's lowercase register despite instruction).
- **Epistemic framing.** "From what you've shared..." not "I can see you're feeling...". The model must not claim perceptual access it does not have.
- **Boundary language.** Warm but boundaried. No parasocial companion framing. Redirects toward human support rather than encouraging exclusive reliance on Nikko.
- **No sycophancy.** Premise endorsement prohibited. Unhedged motive attribution prohibited. Emotion acknowledgement without premise validation is the correct pattern for ambiguous inputs.
- **Non-diagnostic scope.** Nikko does not label, assess, or evaluate the user's mental state. It reflects and acknowledges.

On regen turns, an `[ACTIVE OUTPUT CONSTRAINT — THIS ATTEMPT ONLY]` block is injected into the system prompt with the specific rejection reason from ADP-C. This block is explicitly marked as non-conversational ("DO NOT reference or acknowledge this constraint in your output") to prevent ADP-A from responding to the instruction rather than the user.

### What the Verification Supervisor checks (structural integrity)

After Evaluation, the Verification Supervisor runs seven structural checks independent of content quality:

| Check | What it verifies |
|-------|----------------|
| C1 | Evaluator gate — Evaluator MUST have emitted PASS before VS runs; a non-PASS verdict reaching VS indicates an orchestrator fault |
| C2 | Scope routing integrity — OUT_OF_SCOPE inputs must not reach VS; an OOS decision should have been terminated at STEP 0 |
| C3 | Mode-distress alignment — CRISIS distress level MUST route to CRISIS mode; any other mode pairing is a hard failure |
| C4 | Crisis resources — CRITICAL distress requires `crisis_resources` populated; empty list is also a failure |
| C5 | Evidence pipeline — GUIDANCE mode requires `synthesized_evidence` present (None guard); a missing object indicates a skipped retrieval/synthesis step |
| C6 | Agent contamination — `synthesized_evidence` must be absent in COMFORT mode; `crisis_resources` must be absent in GUIDANCE mode |
| C7 | Loop limit — `regen_count` MUST be < MAX_REGEN_ATTEMPTS (3); exceeding this indicates a runaway regen loop |

C5 and C6 are suspended in CRISIS mode — the crisis path legitimately bypasses the evidence pipeline and may carry both evidence and crisis resources simultaneously. C3 specifically exists because a routing error (CRISIS distress → COMFORT mode) is a structural failure that content evaluation cannot catch; the response could pass all fifteen red lines and still be dangerously inadequate.

---

## Model Stack

Nikko uses a **dual-model architecture** built around two base models and three specialised LoRA adapters (ADP = Adapter). The previous candidate — Mistral-7B-Instruct-v0.3 — was retired after proving infeasible on an RTX 3070 8 GB (14 GB fp16 requirement, 14+ hours training with no convergence). Mistral artefacts are archived locally under `*/mistral-7b/` and are not tracked in VCS.

All three adapters were trained in **Phase 4.1 on Lightning.ai A10G** (cloud retraining, steps 20–25) using QLoRA rank-16. Adapter weights are hosted on HF Hub.

| Adapter | Base model | HF Hub | Role | Temperature |
|---------|-----------|--------|------|-------------|
| **ADP-A** | Qwen3-4B (4B, Alibaba Qwen Team, Apache-2.0) | [equinox013/nikko-adp-a](https://huggingface.co/equinox013/nikko-adp-a) | Empathy — generates the user-facing response | 0.50 → 0.25 → 0.20 (annealed per regen attempt; see regen schedule below) |
| **ADP-B** | Gemma-2-2b-it (2.0B, Google Gemma licence) | [equinox013/nikko-adp-b](https://huggingface.co/equinox013/nikko-adp-b) | Safety / crisis classifier | 0.2 (near-deterministic JSON) |
| **ADP-C** | Gemma-2-2b-it (same base as ADP-B) | [equinox013/nikko-adp-c](https://huggingface.co/equinox013/nikko-adp-c) | Response quality evaluator | 0.2 (near-deterministic JSON) |

### Why two base models?

Qwen3-4B produces strong zero-shot empathic responses at the 4B parameter scale without fine-tuning — tasks that reward generative diversity and natural language fluency. Gemma-2-2b-it is better suited to structured classification tasks (binary crisis flags, APPROVE/REGENERATE verdicts) where compact JSON output and near-greedy decoding matter more than creativity. ADP-B and ADP-C **share the Gemma-2 base**: they are loaded once as a single `PeftModel`, and `set_adapter()` hot-swaps their LoRA delta tensors at O(1) cost — no weight duplication, no second model load.

### What a LoRA adapter is

A LoRA (Low-Rank Adaptation) adapter is a small set of weight deltas — typically 50–100 MB — stored separately from the base model. During inference, the adapter's delta tensors are added to the base model's weight matrices, steering the model toward a specific task. Swapping adapters means replacing those delta tensors; the base model weights never change. This is why ADP-B and ADP-C can coexist in the same `PeftModel` and be selected at runtime with a single `set_adapter()` call.

### VRAM budget (Modal A10G 24 GB — production)

```
Qwen3-4B              (4.0B bf16)  ~  8.0 GB  (ADP-A base + LoRA delta tensors)
Gemma-2-2b-it         (2.0B bf16)  ~  4.5 GB  (ADP-B + ADP-C shared)
Adapter weights (3 × ~50 MB)       ~  0.2 GB  (adp-a, adp-b, adp-c)
Activations + overhead             ~  2.0 GB
────────────────────────────────────────────
Total estimated                    ~ 14.7 GB   (fits A10G 24 GB with 9.3 GB headroom)
```

`bitsandbytes` / NF4 quantization is not used — both models load cleanly in native bf16 within the A10G budget and quantization adds complexity without meaningful latency benefit at this parameter scale.

> **HF Space fallback:** The fallback ZeroGPU endpoint runs on H200 (70 GB VRAM per slice), not A10G. The same bf16 weights fit with significantly more headroom. `bitsandbytes` remains excluded from `hf_space/requirements.txt` because ZeroGPU defers CUDA allocation until inside a `@spaces.GPU` context — bitsandbytes checks for CUDA at import time and crashes. This restriction does not apply to Modal (CUDA available from container startup). `hf_space/app.py` mirrors `nikko_modal/app.py` for signal-strength gate, analysis enrichment functions (`_analyze_scope`, `_analyze_signal`, `_enrich_strategy`), and extended pipeline schema. **Note:** The split paralinguistic detection architecture (Render-side `paralinguistic_detector.py` + narrowed 6-signal LLM pre-analysis prompt) is fully implemented across both `nikko_modal/app.py` and `hf_space/app.py` (parity sync completed 2026-05-23). Both paths receive the same `struct_annotations` payload from Render.

---

## How the Pipeline Works

A user message flows through the stages below. Agent logic lives in `agents/` and `orchestration/`; the primary production inference layer is in `nikko_modal/app.py` (Modal Serverless), with `hf_space/app.py` as the ZeroGPU fallback.

> *Step numbers follow the SPEC-700 execution order. Some step IDs are reserved for parallel branches or adjacent operations not surfaced in this overview (Steps 9 and 14, for example, are reserved for orchestrator-internal bookkeeping not visible to the agents themselves).*

### STEP 0 — Scope Classification + Moderation

A two-stage gate runs before any substantive agent.

**Stage 1 — Render-side Scope Classifier (deterministic, no LLM).** A weighted keyword scorer checks the message against Nikko's operational domain (emotional wellbeing, mental health, relationships, stress, grief). Latency is sub-millisecond. A high-confidence `OUT_OF_SCOPE` verdict terminates the pipeline immediately and returns a static warm-redirect response — no LLM call is made, no user text enters the agent chain. `IN_SCOPE` and `AMBIGUOUS` pass through. The asymmetric error policy is deliberate: false negatives (an OOS message slipping through) are caught downstream; false positives (an in-scope message being blocked) are unrecoverable from the user's perspective.

**Stage 2 — Modal Pass 0 (Qwen3-4B LLM).** For every message that reaches Modal, a combined moderation + scope check runs as a single Qwen3-4B call. It performs two jobs:

1. **Harmful content moderation** — detects advocacy or promotion of hate, violence, CSAM, or other blocked categories. A `harmful=True` verdict (confidence ≥ 0.80) returns `MODERATION_BLOCK_SENTINEL` to the Render backend, which delivers a static block response. The threshold guards against false positives on legitimate distress language — reporting discrimination is not the same as promoting it.
2. **Final scope validation** — catches out-of-scope messages the keyword scorer passed or flagged as `AMBIGUOUS`. The `scope_ambiguous=True` flag from Stage 1 is forwarded as a hint so Qwen3-4B weights its scope decision more carefully when the rule engine itself was uncertain.

A confidence floor of 0.80 applies to both checks. Below it, the message passes through rather than being silently dropped.

### STEP 1 — Input Sanitisation

The message is stripped of PII patterns, control characters, and anything exceeding safe input lengths. The sanitised text is what every downstream agent sees.

### STEP 2 — Psychological Signal Detection

The **Signal Agent** makes the first LLM call. It receives the sanitised text and returns a structured `SignalPayload` — a validated, immutable data object describing detected distress level (LOW / MODERATE / HIGH / CRISIS), emotional states, cognitive patterns, risk indicators, and what kind of support the user appears to need.

In production, the Signal Agent runs on the Render backend (zero-shot, no fine-tuned adapter — it provides structured signal extraction, not empathetic generation). During Phase 3 development it ran on Qwen2.5-3B-Instruct zero-shot locally.

### STEP 2.5 — Paralinguistic Pre-Analysis

Before the pipeline can route or generate a response, it needs to understand *how* the message was written, not just *what* it says. Typing patterns carry clinically meaningful information — a user who types in all-lowercase with trailing ellipses is signalling something different from a user who types in complete sentences, even if the words are identical. This step detects those signals and injects them into ADP-B's context so the safety classifier can make a more informed verdict.

The detection architecture is intentionally split across two layers, because the signals divide cleanly at the determinism boundary:

**Render-side (deterministic, zero-latency) — `backend/paralinguistic_detector.py`.** Eight signals are detected by pure regex and heuristic rules before the Modal call. These are surface-pattern signals: whether the message is in lowercase, whether it trails off with ellipses, whether it contains keysmash, distress emoji, urgency punctuation, or other typographic markers. An LLM would hedge on these tasks ("the message *might* be all-lowercase") because they are definitionally deterministic — regex is the correct tool.

| Tag | Signal | Example |
|-----|--------|---------|
| `[STRUCT: all_lowercase]` | Entire message in lowercase | `"i just feel so tired all the time"` |
| `[STRUCT: ellipsis_trail]` | Trailing `...` suggesting unfinished thought | `"i don't know..."` |
| `[STRUCT: all_caps_segment]` | All-caps word or phrase indicating emotional intensity | `"I CANT DO THIS"` |
| `[PARA: expressive_lengthening]` | Repeated letters for emphasis | `"I'm sooooo exhausted"` |
| `[PARA: punctuation_urgency]` | Repeated `?` or `!` | `"why does this keep happening???"` |
| `[PARA: keysmash]` | Random character sequences | `"jfkdsjfksd i give up"` |
| `[PARA: emoji_distress]` | Distress or crying emoji | `"😭😞"` |
| `[PARA: asterisk_action]` | Asterisk-enclosed action framing | `"*sighs*"` |

**Modal-side (Qwen3-4B, thinking mode) — Step 1.5 inside `run_pipeline()`.** Six signals that require understanding what the words *mean in context* are detected by Qwen3-4B with thinking mode enabled. A message like "lol yeah I'm fine" cannot be flagged for tone-softening by a regex — you need language understanding to recognise that "lol" is face-saving minimisation, not genuine amusement.

| Tag | Signal |
|-----|--------|
| `[PARA: tone_softener]` | Laughter token used as distress buffer (`lol`, `haha`) |
| `[PARA: minimisation]` | Distress explicitly walked back (`"it's not a big deal"`) |
| `[PARA: mixed_affect]` | Simultaneous positive and distress signals |
| `[PARA: typographic_register]` | Deliberate stylistic register shift within the message |
| `[STRUCT: fragmented_syntax]` | Broken grammar, incomplete clauses |
| `[STRUCT: register_collapse]` | Degradation from sentences to disconnected fragments |

The two outputs are merged — Render struct tags first, then LLM semantic PARA tags — and the combined annotation string (e.g. `"[STRUCT: all_lowercase] [STRUCT: ellipsis_trail] [PARA: tone_softener]"`) is injected into ADP-B's system prompt. ADP-B uses these annotations when deciding whether to weight passive risk signals more heavily than the surface text alone would suggest.

### STEP 3 — Routing

The **Router** reads the `SignalPayload` and assigns exactly one operational mode using deterministic rules — no LLM. Its decision is the single source of truth for everything that follows.

- **COMFORT** — validation, active listening, no information injection.
- **GUIDANCE** — calm, evidence-grounded information for users seeking understanding.
- **CRISIS** — immediate safety priority; evidence pipeline is skipped; crisis resources are injected unconditionally; ADP-B response is used directly.

### STEPs 4–8 — Evidence Retrieval and Synthesis (Guidance Mode only)

If the Router assigned GUIDANCE, two adapters run in parallel — the **PubMed Adapter** against NCBI's research database and the **Web Search Adapter** against a registry of 14 sanctioned health-information domains.

**PubMed Adapter** — queries NCBI E-utilities (ESearch → PMIDs, EFetch → XML) and returns up to 5 peer-reviewed articles per turn (hard cap: 20). By default it restricts to Meta-Analyses, Systematic Reviews, and Randomised Controlled Trials from the PMC Open Access subset, so every citation the LLM sees has full-text access and no institutional paywall. A 5-year recency filter is applied by default (REQ-200-ER1). When topic hints are present and narrow (≤ 3 tags), MeSH heading clauses are AND-appended to the query to improve precision — for example, an `indigenous` tag appends `"Australian Aboriginal and Torres Strait Islander Peoples[MeSH] OR Indigenous Peoples[MeSH]"`. Results are disk-cached for 7 days. The adapter never raises — all errors return as `RetrievalError` so the pipeline can proceed without evidence rather than crash.

**Web Search Adapter** — queries a registry of 14 sanctioned health-information domains, routed by detected topic:

| Category | Domains |
|----------|---------|
| Government / clinical | Healthdirect Australia, Better Health Channel, WHO, Medicare Mental Health |
| Broad NGOs | Beyond Blue, Black Dog Institute, Lifeline Australia |
| Population-specific | headspace, ReachOut Australia, Kids Helpline, MensLine Australia |
| Specialised conditions | Blue Knot Foundation (trauma), GriefLine |
| Cultural / Indigenous | 13YARN (priority-10; no substitute) |

Topic routing is keyword-driven and deterministic — no LLM involved. When no specific topic is detected, the adapter falls back to a default set of five high-coverage domains (Beyond Blue, Healthdirect, Black Dog Institute, Better Health Channel, WHO). Results are cached on disk.

The **Evidence Synthesizer** then ranks all retrieved items by quality — peer-reviewed content within the last five years scores highest — and produces a single `SynthesizedEvidence` object. No LLM is involved in ranking or scoring.

### STEP 4 (parallel) — Support Strategy

The **Support Strategy Agent** makes the second LLM call. It runs in parallel with Evidence Retrieval. It receives the Router's mode and Signal payload and returns communication guidance for the Interaction Model: tone, framing strategy, and constraints. It never generates user-facing text. In Crisis Mode this step is bypassed — a fixed, hardcoded strategy object is injected instead.

### STEP 10 — Draft Generation (ADP-A)

The **Interaction Model** runs. It receives a `ResponseContextPayload` — strategy guidance, synthesised evidence if any, and the mode — and generates the empathetic user-facing response.

In production this is **ADP-A: Qwen3-4B + LoRA** (`equinox013/nikko-adp-a`, trained Phase 4.1) used for empathetic, non-diagnostic wellbeing responses. The model receives the `ResponseContextPayload` (strategy guidance, synthesised evidence if any, mode, and up to 10 prior conversation turns) — it has no access to raw retrieval results or intermediate agent outputs outside what the payload explicitly carries.

### STEP 11 — Evaluation (ADP-C)

The **Evaluator Agent** is the content gate. It runs two passes:

**Pass 1 (deterministic):** ten of the fifteen spec-defined red lines are checked by regex against the draft. These catch diagnostic labelling, treatment recommendations, clinical authority framing, crisis-resource withholding, severity minimisation, and credential impersonation. A single match blocks the response immediately. The remaining five (R9, R12, R13, R14) are architectural constraints enforced by pipeline structure, not response-text patterns.

**Pass 2 (LLM judge, ADP-C):** **Gemma-2-2b-it** with the ADP-C evaluator adapter checks tone compliance and hallucination indicators. A `REGENERATE` verdict triggers the regen loop described below. `set_adapter("adp_c")` switches the shared Gemma-2 base from its ADP-B safety role to its ADP-C evaluator role at no VRAM cost.

#### COMFORT mode regen schedule

ADP-A's fine-tuning reduces — but does not eliminate — the probability of generating advice or questions in COMFORT mode. This is a documented property of SFT: the model is trained to maximise the likelihood of compliant outputs on individual draws, not to produce zero-probability constraint violations across N attempts. At higher sampling temperatures, the residual probability of violations is large enough to surface regularly.

The regen loop handles this with two layers:

**Layer 1 — Temperature annealing (`_REGEN_TEMPERATURES`).** Each regen attempt reduces ADP-A's sampling temperature, steering the model toward the mode of its output distribution (most probable, most conservative output) rather than sampling from the tails where violations cluster.

| Attempt | Temperature | ADP-A LoRA |
|---------|------------|------------|
| 0 (first pass) | 0.50 | Active |
| 1 | 0.25 | Active |
| 2 (last resort) | 0.20 | **Disabled** — base Qwen3-4B |

**Layer 2 — Base model fallback.** On the final attempt, the ADP-A LoRA adapter is disabled via PEFT's `disable_adapter()` context manager (O(1), no weight copy). When the adapter's training bias toward expressive outputs persists at low temperature, bare Qwen3-4B with an explicit constraint system prompt is a cleaner last resort. If all three Render-level attempts exhaust, a safe canned response is returned.

Each Modal call also runs one internal regen pass (ADP-C → regen → ADP-C) before returning to Render, with a further temperature reduction of 0.15 from the outer attempt's temperature (floor 0.15).

### STEP 12 — Verification Supervisor

The **Verification Supervisor** checks structural pipeline integrity — right agents in the right order, crisis resources present when they should be, evidence present in Guidance and absent in Comfort. A structural failure triggers a safe fallback response.

### STEP 13 — Assembly

The final `PipelineResult` is assembled: response text, mode, crisis resources if any, evaluation result, verification result, and a full execution trace.

### STEP 15 — Trace Capture

A `PipelineTrace` records every agent that ran, the router decision, distress level, evidence used, latency, and whether a safe fallback was used. Traces are session-scoped and ephemeral — never written to persistent storage.

---

## The ADP Pipeline in Production

In the deployed stack, all three adapter passes run inside a **single GPU session** on Modal Serverless. This consolidation means both models stay resident in VRAM for the entire turn, paying the CPU→VRAM transfer cost once rather than three times. Warm-turn latency: ~20–40s. Cold start: ~30–60s (Volume read) vs ~90–120s (HF Hub download on ZeroGPU).

If Modal is unavailable, the backend transparently retries against the HF Space ZeroGPU fallback — no user-visible error, just a slower response.

```
User message (React frontend)
    │
    │  POST /api/message
    ▼
Render backend (FastAPI, nikko-companion.onrender.com)
    │
    │  POST /pipeline  (single GPU session, timeout 360s)
    ▼
Modal Serverless A10G (primary)  ──or──  HF Spaces ZeroGPU H200 (fallback)
    │
    ├─ ADP-A  (Qwen3-4B + ADP-A LoRA)    → empathetic response draft
    │
    ├─ ADP-B  (Gemma-2 + adp_b adapter)  → crisis check; annotations injected
    │         ↓ CRISIS → text discarded; crisis resources returned; ADP-C skipped
    │
    └─ ADP-C  (Gemma-2 + adp_c adapter)  → evaluate draft; APPROVE or REGENERATE
                                            (max 3 regen attempts; temperature-annealed)
    │
    │  { text, is_crisis, flags, verdict, regen, elapsed }
    ▼
Render backend
    │
    │  SSE stream: event: chunk  data: { text, emotion, safetyFlags, trace }
    ▼
React frontend
```

The `/pipeline` response payload is:

| Field | Type | Description |
|-------|------|-------------|
| `text` | string | ADP-A response text (empty when `is_crisis=true`) |
| `is_crisis` | bool | ADP-B crisis verdict |
| `flags` | list[str] | Safety signal labels from ADP-B (e.g. `suicidal_ideation`) |
| `verdict` | string | ADP-C verdict: `APPROVE` or `REGENERATE` |
| `regen` | bool | Whether a regen pass was triggered |
| `elapsed` | float | Total GPU time in seconds |
| `scope_verdict` | string \| null | Qwen3-4B scope analysis verdict (`"in_scope"`, `"ambiguous"`, `"out_of_scope"`) |
| `pre_analysis_raw` | string | Merged paralinguistic annotation string — Render struct tags + Qwen3 semantic PARA tags (e.g. `"[STRUCT: all_lowercase] [PARA: tone_softener]"`). Empty if no signals. |
| `enhanced_signal` | dict \| null | Enriched signal output from the signal analysis pass |
| `enhanced_strategy` | dict \| null | Enriched strategy output from the strategy analysis pass |
| `harm_category` | string | Content moderation category on a `BLOCKED` early exit (empty otherwise) |
| `oos_reason` | string | Out-of-scope reason string on an `OUT_OF_SCOPE` early exit (empty otherwise) |

---

## Frontend–Backend Integration

The React SPA (`web/`) communicates with the Render backend exclusively via two endpoints defined in `docs/integration/FRONTEND_INTEGRATION_SPEC.md`.

### Loading screen

On app load, the frontend polls `GET /health` on the Render backend every 3 seconds until it receives `{"status": "ok", "space_ok": true}`. The `space_ok` flag reflects whether the HF Space `/health` probe returned 200. An interactive loading screen is shown until both services are confirmed live, preventing the user from sending messages into a cold pipeline.

### Chat endpoint (`POST /api/message`)

The primary chat flow uses **Server-Sent Events (SSE)** — a unidirectional HTTP stream. The frontend reads it with `fetch()` + `ReadableStream` rather than `EventSource` because `EventSource` does not support POST requests.

The request body includes:

| Field | Description |
|-------|-------------|
| `text` | User message text (word-capped client-side per USM input preference) |
| `conversationHistory` | Last 10 turns as `[{role, content}]` — session-scoped only, never persisted |
| `memoryContext` | Decrypted USM file content (if loaded); passed to ADP-A for personalisation |

SSE event sequence per turn:

```
event: message_start   data: { id, emotion: "listen" }
event: chunk           data: { text: "", emotion: "think" }     ← signals pipeline running
event: chunk           data: { text: "...", emotion: "speak", safetyFlags: [], trace: {...} }
event: message_end     data: { id }
```

The final substantive chunk also carries:

| Field | Description |
|-------|-------------|
| `trace` | Full ADP-B / ADP-A / ADP-C result breakdown — forwarded to `NikkoAgentLog` for the debug overlay |
| `memory_proposal` | Affirmation detected in user message; pre-written USM entry offered to user |
| `technique_recommended` | Technique detected in ADP-A response; pre-written USM entry offered via `TechniqueCheckInBanner`. Suppressed if `memory_proposal` fired on the same turn |

### ThinkingBubble

Because the pipeline takes 30–120s depending on whether the HF Space GPU context is warm or cold, a `ThinkingBubble` component manages user expectation with staged labels:

- 0–6s: *Reading your message…*
- 6–14s: *Checking in on what you shared…*
- 14–24s: *Putting together a response for you…*
- 24s+: Cycles through affirmations every 5s

### Fallback (backend unreachable)

If the Render backend is unreachable (cold-start, network error, or empty SSE stream), the frontend gracefully degrades to `matchNikkoPattern()` — a local regex-based keyword matcher in `nikko-data.jsx`. The user always receives a response. This fallback is logged to console and not surfaced to the user. It remains as an offline safety net; the primary path is always the live backend pipeline.

### Agent debug overlay

The pipeline debug overlay is gesture-gated (2 clicks then 3-second hold on the avatar) and shows per-turn adapter activity. When the backend is reachable and returns `trace` data, the overlay displays **live data** from the actual pipeline run — adapter verdicts, safety flags, regen status, and total elapsed time. When the fallback fires, it displays a simulated trace derived from local keyword classification.

The overlay correctly labels the adapters:
- **ADP-B** — Gemma-2-2b-it · Safety / crisis
- **ADP-A** — Qwen3-4B · Empathy response
- **ADP-C** — Gemma-2-2b-it · Quality evaluator

---

## User Sovereign Memory (USM) & Personalisation

Nikko supports an optional memory system. Encryption and decryption are fully client-side — the encryption key never leaves the device. The decrypted content travels over HTTPS to the Render backend per turn but is never written to persistent storage on any server.

### How it works

1. **Generate** — a 5-step modal (Disclosure → Name → Style → Support → Password) collects personalisation preferences and produces a structured Markdown file.
2. **Encrypt** — the file is AES-GCM encrypted client-side using the Web Crypto API and downloaded as `.nikko-mem.enc`. The encryption key never leaves the browser.
3. **Load** — on a future session, the user re-uploads the file, enters their password, and the decrypted content is held in a `useRef` for the session lifetime. A lock-icon banner confirms the file is active.
4. **Inject** — on each message, the decrypted content is sent as `memoryContext` in the POST body (HTTPS, in-flight only). The backend truncates it to 1200 chars using priority ordering (`_smart_truncate_usm()`) and injects a `USER PREFERENCES` block into the ADP-A system prompt.

The session ends, the ref is cleared. No server writes plaintext to persistent storage at any point.

### Personalisation options (Style screen)

| Setting | Options |
|---------|---------|
| Tone | Understanding · Balanced · Practical |
| Response length | Brief · Standard · Detailed |
| Input style (word cap) | Concise (150w) · Standard (300w) · Verbose (600w) |

### ADP-A preference injection

`_parse_memory_prefs()` in `context_prompt_builder.py` reads key-value pairs from `## User Preferences` and maps them to prose via `_TONE_INSTRUCTIONS` and `_LENGTH_INSTRUCTIONS` dicts. This block is injected into ADP-A's system prompt on every turn where a memory file is loaded. One exception: when `distress_level ≥ 7`, tone preference is suppressed — Comfort Mode empathy framing takes precedence and will not be overridden by a stylistic choice.

### Smart USM truncation

When the memory file exceeds the 1200-char ADP-A budget, `_smart_truncate_usm()` applies a priority order: Name → Mood Diary (newest-first by date) → User Preferences → Helpful Interventions → Support Notes → Emotional Patterns. A truncation notice is appended so the model knows the file was cut.

### Multi-turn conversation history

The frontend sends the last 10 turns as `conversationHistory` in every POST request. The backend caps at 20 turns server-side. `draft_generator.py` assembles a proper multi-turn messages list for ADP-A so Nikko can reference what was said earlier in the same session. All history is session-scoped React state — cleared on page refresh, never persisted to any server.

### Memory banners

- **Loaded banner** — appears on successful file load; auto-dismisses after 7s; shows a lock icon confirming encryption status.
- **Hint banner** — appears after the user's 3rd message if no memory file is loaded; fires once per session only.

### Technique check-in banner (memory write-back — Phase 1)

When ADP-A recommends a technique (e.g. deep breathing, grounding, journalling), the backend detects it and the frontend surfaces a non-intrusive popup — `TechniqueCheckInBanner` — offering to add a first-person entry to the user's memory file. This is the first concrete memory write-back path.

**How it works:**

- `_RESPONSE_RECOMMEND_RE` (regex in `backend/main.py`) scans ADP-A output for technique recommendation language.
- `_TECHNIQUE_CANONICAL` maps 15 raw matches to canonical technique names and pre-written first-person USM entries (e.g. `"Nikko recommended deep breathing on [date]"`).
- `_detect_technique_in_response()` runs after the ADP-C pass — only on APPROVE. Result is emitted as `technique_recommended` on the final SSE chunk.
- `TechniqueCheckInBanner` in `chat.jsx` shows as an accent-bordered popup (distinct from the crisis red of `SafetyBanner`). User can accept or dismiss.
- On accept, the entry is promoted into `pendingEntries` and merged into the in-memory decrypted file content via `onCheckInAdd`.

**Guards:** Both the check-in banner and the affirmation proposal card are gated on `memContentRef && sessionKeyRef` — they only surface when an encrypted `.enc` file is actively loaded. The two detections are mutually exclusive per turn: `technique_recommended` is suppressed if `memory_proposal` (affirmation detection) already fired.

**Memory write-back (remaining, Phase 6+)**

The check-in banner adds entries to the in-memory `memContentRef` for the session but does not yet re-encrypt and download the updated file — the user must regenerate their memory file to persist new entries permanently. Full write-back (re-encrypt in-place with `sessionKeyRef`, queue to download on session end) is the next pass.

### Mood diary round-trip

The mood diary is a session-local feature with an optional durable channel via the USM memory file.

- **Session state:** `moodEntries` lives in React state only (`useState({})`). It clears on page refresh, consistent with SPEC-800 zero-retention. `sessionStorage` is not used.
- **Write path:** `MoodDiaryPanel.save()` serialises all logged entries using `formatDiaryEntry(iso, entry)` into a `## Mood Diary` section of the decrypted memory file content, then re-encrypts and downloads it in a single cycle.
- **Read path:** When the user re-loads their memory file, `onMemoryLoaded` calls `parseDiaryEntries(md)` to parse the `## Mood Diary` section back into the `moodEntries` state dict. The round-trip format is `YYYY-MM-DD | mood: N | emotions: x, y | triggers: a, b\nnote: ...` — one block per entry, separated by blank lines.

---

## Repository Structure

```
nikko-companion/
├── docs/
│   ├── specs/          # 8 core specs (SPEC-000 through SPEC-700) + 3 supplementary (SPEC-800, SPEC-810, SPEC-850)
│   ├── derived/        # Architecture, agent definitions, safety guardrails, evaluation criteria
│   └── integration/    # FRONTEND_INTEGRATION_SPEC.md — frontend ↔ backend API contract
├── schemas/            # Pydantic v2 inter-agent data schemas (acp_schemas.py, retrieval_schemas.py, validate.py)
├── agents/             # Seven specialist agents
├── orchestration/      # Pipeline orchestrator
├── retrieval/          # PubMed + WebSearch evidence adapters
├── finetuning/         # QLoRA training data and configs for ADP-A/B/C
├── notebooks/          # Canonical training notebooks: Steps 1–10 (pipeline dev) + Steps 20–25 (cloud training)
├── nikko_modal/        # Modal Serverless inference endpoint (Qwen3-4B + Gemma-2-2b-it) — primary
├── hf_space/           # HF Spaces ZeroGPU inference endpoint — fallback
│   └── app.py          # FastAPI + Gradio app — /pipeline endpoint
├── backend/            # Render orchestration API
│   ├── main.py         # FastAPI — /health + /api/message SSE endpoint; conversationHistory cap
│   ├── draft_generator.py          # Multi-turn messages builder for ADP-A; calls paralinguistic_detector
│   ├── paralinguistic_detector.py  # Render-side regex engine — 8 deterministic STRUCT+PARA signals
│   └── context_prompt_builder.py   # USM truncation + ADP-A preference injection
└── web/                # React SPA
    ├── Nikko.html      # Entry point
    ├── nikko.jsx       # Root app + theme
    ├── chat.jsx        # Message thread, SSE handler, ThinkingBubble, composer,
    │                   # multi-turn history, USM banners, input word cap
    ├── agent-debug.jsx # Pipeline trace overlay (NikkoAgentLog store + AdapterCards)
    ├── agent-debug.js  # Compiled output — regenerated via esbuild
    ├── avatar.jsx      # Emotional state visualisation (calm/listen/think/speak/care)
    ├── gate.jsx        # Consent gate + onboarding
    ├── memory.jsx      # USM file encryption + 5-step MemoryGenerateModal
    ├── panels.jsx      # Mood diary, sources panel
    ├── nikko-data.jsx  # Hardcoded fallback patterns (offline safety net)
    └── styles.css      # Light/dark theme, animations
```

---

## Safety Architecture

Every design decision in Nikko traces to a named requirement in the spec. The key safety properties are:

- **No clinical authority.** The LLM is never trained on medical content. Health information is always fetched from external sources, ranked by quality, and passed through the Synthesizer before the LLM sees it. The LLM cannot "know" medical facts — it can only relay what the retrieval system found.
- **Hard-coded crisis routing.** The Router's CRISIS assignment is a deterministic rule, not an LLM judgment. Once CRISIS is assigned, the evidence pipeline stops. ADP-A still runs (per the Director-approved 2026-05-22 pipeline reorder) but its output is discarded — four Australian crisis resources are injected unconditionally instead. ADP-B makes the binary safety classification; the delivered text is hardcoded, not generated.
- **Fifteen safety red lines.** The spec defines fifteen hard prohibitions (R1–R15). Ten are enforced by deterministic regex in the Evaluator before any response reaches the user — they check for diagnostic language, treatment recommendations, clinical authority framing, crisis-resource withholding, and severity minimisation. The remaining five are structural: enforced by pipeline architecture, not content scanning, making them impossible to violate at the generation layer.
- **Structural integrity gate.** The Verification Supervisor checks that the pipeline ran correctly, not just that the response sounds safe. A CRISIS distress signal paired with a COMFORT mode response will be caught here even if the Evaluator passed it.
- **Zero data retention.** No user conversation data enters the training pipeline. This constraint is permanent (REQ-000-P01) and is not overridable by any phase gate or instruction. Session data lives in React state only and is cleared on page refresh. `sessionStorage` is not used for conversation or mood data — React state provides the same refresh-clearing behaviour without any browser storage write.

---

## Deployment Stack

| Layer | Service | Notes |
|-------|---------|-------|
| Frontend | GitHub Pages — `equinox013.github.io/nikko-companion` | Static React SPA; zero cost |
| Backend orchestration | Render — `nikko-companion.onrender.com` | FastAPI + pipeline logic; Docker-native |
| LLM inference (primary) | Modal Serverless — `modal.run` | `/pipeline` endpoint; A10G 24 GB; Qwen3-4B + Gemma-2-2b-it; ~$0.015/call on $30/month free credit |
| LLM inference (fallback) | HF Spaces ZeroGPU | Auto-failover from Render backend; H200 slice; slower cold start |
| Adapter weights | HF Hub public repos + Modal Volume | [`nikko-adp-a`](https://huggingface.co/equinox013/nikko-adp-a), [`nikko-adp-b`](https://huggingface.co/equinox013/nikko-adp-b), [`nikko-adp-c`](https://huggingface.co/equinox013/nikko-adp-c); cached in Modal Volume at build time |

Cold start (Modal, Volume read): ~30–60s. Cold start (HF Space fallback): ~90–120s. Warm turns: ~20–40s either path. The ThinkingBubble and loading screen manage user expectation during both cases.

---

## Key Documents

| Document | What it is |
|----------|-----------|
| [`docs/INDEX.md`](docs/INDEX.md) | Map of every spec and derived document. |
| [`docs/GLOSSARY.md`](docs/GLOSSARY.md) | Canonical terms — modes, distress levels, agents, adapters. |
| [`docs/DEVLOG.md`](docs/DEVLOG.md) | Daily development log — decisions, justifications, learnings. |
| [`docs/specs/SPEC-000-charter.md`](docs/specs/SPEC-000-charter.md) | System charter. Supersedes all other specs on conflict. |
| [`docs/integration/FRONTEND_INTEGRATION_SPEC.md`](docs/integration/FRONTEND_INTEGRATION_SPEC.md) | Frontend ↔ backend API contract. |
| [`notebooks/`](notebooks/) | Canonical notebooks: Steps 1–10 (Phase 3 pipeline dev) and Steps 20–25 (Phase 4.1 cloud training, Lightning.ai A10G). |

---

## Running the Pipeline Locally

```python
from orchestration import NikkoPipeline

pipeline = NikkoPipeline()   # uses stubs for LLM; all deterministic agents are live
result = pipeline.run("I've been feeling really overwhelmed lately.")

print(result.response_text)           # generated response
print(result.mode)                    # OperationalMode.COMFORT / GUIDANCE / CRISIS
print(result.trace.execution_path)   # which agents ran
```

For a full walkthrough including edge cases (Crisis Mode, Guidance evidence path, regeneration loop, Verification Supervisor failures), see `notebooks/step10_pipeline.ipynb`.

To test the production inference endpoint directly:

```bash
# Warm the Space and run all three adapters in one GPU session
curl -X POST https://<your-hf-space-url>/pipeline \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "I have been feeling very low lately."}],
       "system": "...", "safety_system": "...", "eval_system": "...", "token": "..."}'
```

---

## Limitations

This is a research prototype. The following limitations are known and accepted at MVP conclusion.

**Empathy quality.** Empathy Score (ES) reached 3.01 overall (3.34 excluding structural crisis cases) against a target of ≥ 3.5. Some responses — particularly on gratitude and positive turns — are flat or over-hedged. System prompt patches (REQ-000-060/061/062/063) partially compensate for weight-level shortfalls but introduce occasional double-suppression.

**Regen rate and latency.** Approximately 50% of responses trigger at least one regen pass through the ADP-A → ADP-C loop, adding latency variance. Warm-turn p50 is ~40s; cold starts reach 120s. The system is functional but not suitable for real-time conversational use at scale.

**Evidence grounding.** Evidence Grounding Score (EGS) is 0.09, driven partly by routing misclassification pushing GUIDANCE-eligible messages to COMFORT, and partly by retrieval precision. The GUIDANCE mode evidence pipeline works correctly when it runs — it just runs less often than ideal.

**Australia-specific crisis resources.** Crisis routing delivers hardcoded Australian resources (Lifeline 13 11 14, Beyond Blue, 13YARN, 000) only. The system has no configurable per-region resource registry.

**English-only.** No multilingual support. Language and cultural context are limited to the training data distributions of Qwen3-4B and Gemma-2-2b-it.

**No formal digital health framework validation.** The system has not been mapped against WHO guidance on digital health interventions, OECD AI principles, the Australian Digital Health Agency standards, or any equivalent framework. Safety architecture is rigorous by design, but no independent clinical review or ethics approval has been obtained. This is a technical research prototype, not a clinically validated tool.

**Free-tier infrastructure limits.** The deployment stack runs on Modal Serverless, Render free tier, and HF Spaces ZeroGPU — all subject to cold starts, rate limits, and availability constraints. No SLA, no monitoring, no production hardening.

**Partial USM write-back.** Technique check-in entries and mood diary additions accumulate in-session memory but require the user to manually regenerate and re-download their memory file to persist. Automatic re-encryption and re-download on session end is not implemented.

---

## Future Improvements

The following improvements are scoped and partially pre-planned if development were to resume.

**ADP-C v4 retraining** (step37/38 notebooks written, not run). Retrains the evaluator oracle on a combined dataset of organic corpus records, RLAIF preference pairs, and live-usage DPO pairs. Expected to realign ADP-C with the post-DPO ADP-A style distribution, reducing the 50% regen rate and improving latency p50.

**ES ≥ 3.5 closure.** Additional RLAIF preference pairs and targeted contrastive training focused on gratitude/positive turns and parasocial language. Conditional softening of system prompt patches REQ-000-061/062/063 after weight-level confirmation to reduce double-suppression.

**Persistent GPU endpoint.** Replacing Modal's serverless cold-start model with a persistent container (or equivalent) would reduce p50 from ~40s to ~5–8s — the single highest-impact UX improvement available without architectural changes.

**Digital health framework alignment.** Formal mapping of the system's safety architecture and data lifecycle to WHO digital health guidance, OECD AI principles, and Australian Digital Health Agency standards. Prerequisite for any path toward real-world deployment.

**Independent clinical safety review.** Clinician review of red-line coverage, crisis response templates, scope boundaries, and tone guardrails. The architecture is designed against defined failure modes, but it has not had expert clinical eyes on it.

**EGS improvement.** Better PubMed query construction (query reformulation layer, dense retrieval alongside keyword search) and routing accuracy improvement for the LOW distress segment (currently 63% accurate) would lift EGS meaningfully.

**Full USM write-back.** Re-encrypt and re-download the updated memory file on session end, making technique check-ins and mood diary entries persistent without manual intervention.

**Configurable crisis resource registry.** Replace hardcoded Australian resources with a per-region configurable registry, enabling broader geographic coverage.

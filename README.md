![docs/assets/nikko-banner.png](docs/assets/nikko-banner.png)

[![GitHub](https://img.shields.io/badge/github-equinox013%2Fnikko--companion-black?logo=github)](https://github.com/equinox013/nikko-companion)
![Status](https://img.shields.io/badge/status-MVP-brightgreen)
![Phase](https://img.shields.io/badge/phase-6%20%E2%80%94%20evaluation-blue)
![Models](https://img.shields.io/badge/models-Qwen3--4B%20%2B%20Gemma--2--2b-informational)
![Python](https://img.shields.io/badge/python-3.11-green)
![License](https://img.shields.io/badge/license-research%20use-lightgrey)
![Infra](https://img.shields.io/badge/infra-Modal%20%2B%20Render%20%2B%20GitHub%20Pages-purple)

Nikko is a safety-aligned, evidence-grounded LLM ecosystem designed to function as a compassionate digital mental wellbeing companion. It listens, validates, and surfaces reliable information — but it never diagnoses, never prescribes, and always defers to human care when it matters most.

> *Nikko illuminates possible paths. The user must always walk toward human support themselves.*

---

## Table of Contents

- [Project Status](#project-status)
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
  - [STEP 0 — Scope Classification + Moderation](#step-0--scope-classification--moderation)
  - [STEP 1 — Input Sanitisation](#step-1--input-sanitisation)
  - [STEP 2 — Psychological Signal Detection](#step-2--psychological-signal-detection)
  - [STEP 2.5 — Paralinguistic Pre-Analysis](#step-25--paralinguistic-pre-analysis)
  - [STEP 3 — Routing](#step-3--routing)
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

---

## Project Status

> **MVP.** The full stack is deployed end-to-end. All core features are wired and live. Phase 6 (end-to-end evaluation) is active — running ongoing evaluation, UX refinement, and latency work in parallel with production usage.

| Layer | Status |
|-------|--------|
| Phase 1–2 — Specifications (8 + 3 supplementary) | ✅ Complete |
| Phase 3 — Agent pipeline (7 specialist agents) | ✅ Complete |
| Phase 4 — ADP-C fine-tuning (Gemma-2-2b-it) | ✅ Complete |
| Phase 4 — ADP-B fine-tuning (Gemma-2-2b-it) | ✅ Complete |
| Phase 4 — ADP-A (Qwen3-4B base, no LoRA) | ⛔ Local fine-tuning discontinued (RTX 3070 VRAM limit) |
| Phase 4.1 — Cloud retraining (Lightning.ai A10G) | ✅ Complete 2026-05-24 — all 3 ADPs retrained; adapters on HF Hub |
| Phase 7 — Deployment infra (Modal + Render + GH Pages) | ✅ Live (pulled forward of Phase 6) |
| Frontend SPA | ✅ Complete |
| Phase 5 — Backend API integration | ✅ Complete |
| Phase 6 — End-to-end evaluation | 🔨 Active — running alongside UX + backend speed refinement |

---

## Proof of Concept

> Full pipeline running end-to-end: user message → ADP-A empathy response → ADP-B crisis check → ADP-C evaluation → frontend with live source citations.

![Nikko proof-of-concept screenshot — chat interface showing a user asking for calming tips, Nikko responding with evidence-grounded guidance, and 5 PubMed sources cited in the sources panel](docs/assets/nikko-poc-screenshot.png)

*The "3 ADAPTERS" badge confirms ADP-A → ADP-B → ADP-C all ran in a single Modal A10G GPU session. Sources panel shows APA7-formatted PubMed citations pulled live by the retrieval layer.*

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
| **COMFORT mode advice injection** | LLM adds strategies or coping techniques in pure validation turns | ADP-C evaluator rejects COMFORT mode outputs containing strategies; `_strip_questions()` pre-verifier; temperature annealing per regen attempt |
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

If the Router assigned GUIDANCE, the **PubMed Adapter** queries NCBI's research database and the **Web Search Adapter** searches five sanctioned health-information domains (Healthdirect Australia, Better Health Channel, the World Health Organization, Beyond Blue, and Black Dog Institute). Results are cached on disk.

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

The regen loop handles this with three layers:

**Layer 1 — Pre-verifier question stripping (`_strip_questions()`).** In COMFORT mode, any sentence ending in `?` is removed from the ADP-A draft before ADP-C sees it. ADP-C fine-tuned weights reject question-terminated sentences regardless of instruction-level exceptions — deterministic stripping at the source is more reliable than prompt engineering against trained priors.

**Layer 2 — Temperature annealing (`_REGEN_TEMPERATURES`).** Each regen attempt reduces ADP-A's sampling temperature, steering the model toward the mode of its output distribution (most probable, most conservative output) rather than sampling from the tails where violations cluster.

| Attempt | Temperature | ADP-A LoRA |
|---------|------------|------------|
| 0 (first pass) | 0.50 | Active |
| 1 | 0.25 | Active |
| 2 (last resort) | 0.20 | **Disabled** — base Qwen3-4B |

**Layer 3 — Base model fallback.** On the final attempt, the ADP-A LoRA adapter is disabled via PEFT's `disable_adapter()` context manager (O(1), no weight copy). When the adapter's training bias toward expressive outputs persists at low temperature, bare Qwen3-4B with an explicit constraint system prompt is a cleaner last resort. If all three Render-level attempts exhaust, a safe canned response is returned.

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

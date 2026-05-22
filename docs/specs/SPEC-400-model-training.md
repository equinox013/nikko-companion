---
id: SPEC-400
title: Model Training & Adapter Alignment Protocol (MTAP)
status: authoritative
supersedes: [SPEC-009]
depends_on: [SPEC-000, SPEC-100, SPEC-200, SPEC-300]
version: 1.1.0
last_reviewed: 2026-05-14
---

# SPEC-400 — Model Training & Adapter Alignment Protocol (MTAP)

## Status

- **Authoritative Training Specification.**
- Dependent on: [SPEC-000](./SPEC-000-charter.md) → [SPEC-300](./SPEC-300-crisis-response-protocol.md).
- Applies to: all base models, adapters, and evaluation pipelines.

## 1. Purpose

[REQ-400-001] SPEC-400 MUST define how Nikko's models are selected, fine-tuned, aligned, evaluated, and constrained.

[REQ-400-002] The objective SHALL be: empathetic capability **without** clinical authority, and safety **without** conversational degradation.

## 2. Core Training Philosophy

[REQ-400-010] Nikko MUST NOT be trained to "be a therapist".

[REQ-400-011] Nikko SHALL be trained to communicate like a calm, emotionally intelligent companion while remaining explicitly non-clinical and evidence-bound.

## 3. Model Architecture Standard

### 3.1 Base Model Requirement

[REQ-400-020] All training MUST start from a general instruction-tuned LLM.

Recommended class:
- 2B–4B parameter scale (revised per Director decision 2026-05-14 — see below),
- fits in 8 GB VRAM without quantization,
- native `apply_chat_template()` support (system role, multi-turn),
- strong instruction following.

Reference candidates (revised 2026-05-14):
- Phi-3.5-mini-instruct (3.8B, MIT) — empathy/response (ADP-A)
- Gemma-2-2b-it (2B, Gemma licence) — safety/crisis + evaluation (ADP-B/C)

> **[GAP-G-MODEL-01] CLOSED 2026-05-14** — Licensing review completed. Both selected models permit research deployment without commercial restrictions. See Director Decision below.

[REQ-400-BM1] Nikko is a research-only deployment and will not be commercialised. Base model candidates with compatible research-use licenses (updated priority order, Director decision 2026-05-14; ADP-A further revised 2026-05-16):
1. ~~**Phi-3.5-mini-instruct** (MIT — selected for ADP-A empathy 2026-05-14)~~ — **superseded 2026-05-16**: fine-tuning discontinued (VRAM ceiling); replaced by Qwen3-4B base
2. **Qwen3-4B** (Apache 2.0 — selected as ADP-A production base 2026-05-16; no fine-tuning for MVP)
3. **Gemma-2-2b-it** (Google Gemma licence — selected for ADP-B/C)
4. **Qwen2.5-3B-Instruct** (Apache 2.0 — retained as Phase 3 dev/testing baseline only)

*Retired candidates (archived to `finetuning/mistral-7b/`):*
- ~~Mistral 7B v0.3~~ — infeasible on RTX 3070 8 GB VRAM (14 GB fp16 footprint; training exceeded 14h with no convergence signal at Step 19). See archived notebooks in `notebooks/mistral-7b/`.
- ~~Llama 3.1 8B~~ — same VRAM constraint.

[REQ-400-BM2] License terms for the selected base models MUST be documented in this spec before adapter training begins. The chosen models MUST NOT require commercial licensing for the intended research deployment.

> **[DIRECTOR DECISION — 2026-05-14]** Base model selection **revised**. Previous selection (Mistral-7B-Instruct-v0.3, 2026-05-10) superseded. New selection:
>
> | Adapter | Base Model | HF Identifier | Licence | VRAM (bf16) |
> |---------|-----------|---------------|---------|-------------|
> | ADP-A (Empathy) | Phi-3.5-mini-instruct | `microsoft/Phi-3.5-mini-instruct` | MIT | ~8.5 GB |
> | ADP-B (Safety) | Gemma-2-2b-it | `google/gemma-2-2b-it` | Gemma | ~4.5 GB |
> | ADP-C (Evaluator) | Gemma-2-2b-it | `google/gemma-2-2b-it` | Gemma | shared with ADP-B |
>
> Rationale: Mistral-7B-Instruct-v0.3 was infeasible on the Director's RTX 3070 8 GB VRAM (14 GB bf16 footprint). Phi-3.5-mini-instruct (3.8B) converges ADP-A empathy fine-tuning in ~2h with `packing=True`, `weight_decay=0.01`, `lr=1e-4`. Gemma-2-2b-it (2B) is architecturally ideal for ADP-B/C binary classification tasks and shares its base across both adapters via PEFT `set_adapter()`, eliminating a third model load. Total A10G VRAM budget: ~15 GB (fits 24 GB ZeroGPU with headroom). `trust_remote_code=True` is required for Phi-3.5-mini tokenizer and model classes. bitsandbytes / NF4 quantization is NOT used (ZeroGPU CUDA init-time incompatibility). Both models use native `apply_chat_template()` with system role support. This decision satisfies REQ-400-BM2. Gap GAP-G-MODEL-01 is hereby closed.

> **[DIRECTOR DECISION — 2026-05-16]** ADP-A base model **revised**. Phi-3.5-mini-instruct ADP-A fine-tuning **discontinued** — encountered the same VRAM ceiling as Mistral-7B on the RTX 3070 8 GB dev machine. **Qwen3-4B** (`Qwen/Qwen3-4B`, Apache-2.0) is used as the ADP-A production model **without fine-tuning**; zero-shot quality at the 4B scale is sufficient for the MVP empathy response task. ADP-B and ADP-C training is unaffected. The production model table is amended as follows:
>
> | Adapter | Base Model | HF Identifier | Licence | Fine-tuned? |
> |---------|-----------|---------------|---------|-------------|
> | ADP-A (Empathy) | **Qwen3-4B** | `Qwen/Qwen3-4B` | Apache-2.0 | **⛔ No — base model used directly** |
> | ADP-B (Safety) | Gemma-2-2b-it | `google/gemma-2-2b-it` | Gemma | ✅ QLoRA |
> | ADP-C (Evaluator) | Gemma-2-2b-it | `google/gemma-2-2b-it` | Gemma | ✅ QLoRA |
>
> Production VRAM budget (Modal A10G 24 GB): Qwen3-4B ~8.0 GB + Gemma-2-2b-it ~4.5 GB + adapters + overhead ≈ 14.6 GB (9.4 GB headroom). This supersedes the Phi-3.5-mini-instruct ADP-A selection above. SPEC-400 §3.1, §3.2, `finetuning/README.md`, `agents/README.md` updated accordingly.

### 3.2 Adapter System (Mandatory)

[REQ-400-030] Training MUST use LoRA or QLoRA adapters. The production deployment
uses a **dual-base-model** layout (Director-approved 2026-05-14):

```
Qwen3-4B (base, no LoRA)
└── ADP-A: Empathy Layer            (ADP-A)   ← response generation (base model only for MVP)

Gemma-2-2b-it (base, shared)
├── ADP-B: Safety Alignment         (ADP-B)   ← crisis/safety classification
└── ADP-C: Evaluator Behavior       (ADP-C)   ← response quality gate
```

ADP-B and ADP-C share the Gemma-2-2b-it base. Runtime adapter hot-swap is handled
by `PeftModel.set_adapter()` — no base weight duplication occurs. See `hf_space/app.py`
for the production loading and dispatch logic.

[REQ-400-031] Adapters MUST be independently trainable and runtime-swappable.

## 4. Dataset Stratification

[REQ-400-040] All datasets MUST be separated by function. Cross-functional contamination SHALL NOT be permitted.

### 4.1 Empathy Dataset (ADP-A)

**Purpose:** teach conversational warmth and active listening.

[REQ-400-050] Allowed data types: counselling-style dialogue transcripts; peer-support conversations; motivational-interviewing exchanges; reflective-listening examples; emotionally intelligent writing.

[REQ-400-051] The adapter MUST learn: paraphrasing user emotion; validation without agreement; gentle uncertainty framing; non-judgmental tone.

[REQ-400-052] Forbidden content: diagnostic labelling; clinical-authority framing; directive therapy instructions.

> **[GAP-G-DATA-02]** Specific datasets, licenses, and consent provenance for counselling transcripts are not specified. Many counselling-transcript corpora carry strict use-restrictions. Required before data acquisition.

[REQ-400-CL1] All training datasets MUST have explicit open-use licenses (Apache 2.0, CC-BY, MIT, or equivalent). IRB-required, restricted-access, or unclear-provenance datasets are prohibited. License confirmation is a hard gate before any dataset is acquired or used. Recommended candidates for review: ESConv (CC-BY), EmpatheticDialogues (CC-BY-NC — verify before use), Counsel-Chat (verify license before use).

### 4.2 Safety Alignment Dataset (ADP-B)

**Purpose:** prevent unsafe model behavior.

[REQ-400-060] Training focus: refusal formatting; crisis-escalation language; boundary reinforcement; AI-identity disclosure.

[REQ-400-061] Required outputs: calm refusal styles; safe redirection language; human-escalation encouragement.

### 4.3 Evaluation Behavior Dataset (ADP-C)

**Purpose:** train internal critique behavior. ADP-C SHALL be used by the Evaluator Model only.

[REQ-400-070] Training targets: hallucination-detection patterns; overconfidence detection; clinical-authority leakage detection; citation-validation behavior.

## 5. Evidence Constraint Rule

[REQ-400-080] No SPEC-400 dataset MAY contain:
- medical instruction as authority,
- unverified mental-health claims,
- therapy-directive phrasing.

[REQ-400-081] All medical knowledge SHALL remain externalized via the retrieval system defined in [SPEC-200 §5.4](./SPEC-200-agent-communication-protocol.md#54-evidence-retrieval-agent).

## 6. Training Objective Separation

[REQ-400-090] Each adapter MUST have isolated optimization goals:

| Adapter | Objective |
|---------|-----------|
| Empathy (ADP-A) | emotional resonance + validation |
| Safety (ADP-B) | refusal + boundary enforcement |
| Evaluator (ADP-C) | critique + risk detection |

[REQ-400-091] Shared gradient updates between adapters SHALL NOT occur.

## 7. Loss Function Design (Conceptual)

Training SHALL optimize multiple competing objectives.

[REQ-400-LF1] v0 training approach: Supervised Fine-Tuning (SFT) with rejection sampling. This is the mandatory v0 formulation — simpler, faster, compatible with the open-license corpus constraint. DPO (Direct Preference Optimization) is the planned upgrade path once a preference dataset (ranked response pairs) exists. RLHF, KTO, and PPO are not used in v0.
[REQ-400-LF2] Objective weights for empathy / safety loss components MUST be specified and ratified during Phase 4 planning before training begins.

> **[DIRECTOR DECISION — 2026-05-10]** Objective weights ratified. Gap GAP-G-LOSS-01 is hereby closed. Three sub-decisions recorded below.

#### 7.0.1 ADP-A Training-Time Dataset Mix (ratified)

ADP-A (Empathy Layer) SFT training SHALL use the following dataset mix ratios, ordered by REQ-400-160 priority tiers:

| Tier | Dataset | Mix Weight | Rationale |
|------|---------|------------|-----------|
| 1 | AnnoMI | 30% | Expert-annotated MI transcripts; highest signal quality |
| 1 | Amod / mental_health_counseling_conversations | 25% | Real licensed-professional Q&A; anonymised |
| 2 | ESConv | 20% | Peer-support with labeled strategy tags |
| 3 | MentalChat16K | 15% | Synthetic multi-turn; must pass Evaluator filter (REQ-400-171) |
| 4 | EmpatheticDialogues | 10% | General empathetic tone; volume filler |

AnnoMI is upweighted disproportionate to its raw size (133 transcripts) because it is the only expert-annotated motivational-interviewing source in the stack, directly fulfilling REQ-400-050.

#### 7.0.2 ADP-B and ADP-C Rejection Sampling Asymmetry (ratified)

[REQ-400-LF3] ADP-B (Safety) and ADP-C (Evaluator) rejection sampling filters SHALL apply a **2:1 false-negative to false-positive penalty ratio**. A missed safety violation (false negative) MUST be penalized twice as heavily as an incorrect refusal (false positive). Rationale: prevents clinical drift and authority leakage while avoiding the anti-generic-assistant failure mode defined in REQ-400-140.

#### 7.0.3 Runtime Adapter Composition Weights — α scaling (ratified)

[REQ-400-LF4] When multiple adapters are active simultaneously, their LoRA weight deltas SHALL be combined using the following α scaling factors:

| Mode | α_empathy (ADP-A) | α_safety (ADP-B) | Governing spec |
|------|-------------------|------------------|----------------|
| Comfort Mode | 0.65 | 0.35 | SPEC-700 §5.1 |
| Guidance Mode | 0.50 | 0.50 | SPEC-700 §5.2 |
| Crisis Mode | 0.00 | 1.00 | SPEC-300, SPEC-700 §5.3 |

These are v0 baseline values. SPEC-500 checkpoint evaluation MAY surface the need for adjustment; any change to these values requires a new Director decision recorded in this spec.

### 7.1 Empathy Loss

[REQ-400-100] The empathy loss MUST reward: emotional alignment; reflective phrasing; conversational-flow stability.

### 7.2 Safety Loss

[REQ-400-110] The safety loss MUST reward: correct refusal behaviour; correct crisis escalation; authority-boundary adherence.
[REQ-400-111] The safety loss MUST penalize: diagnostic language; directive advice; overconfidence.

### 7.3 Evaluation Loss

[REQ-400-120] The evaluation loss MUST reward: detection of unsafe outputs; hallucination identification; inconsistency detection.

> **[GAP-G-LOSS-01] CLOSED 2026-05-10** — Concrete loss formulations resolved by Director decisions in §7.0.1–7.0.3 above.

## 8. Behavioral Calibration Constraints

### 8.1 Anti-Therapist Constraint

[REQ-400-130] The model MUST NOT converge toward: therapist-persona simulation; clinical-tone authority; diagnostic framing.

### 8.2 Anti-Generic-Assistant Constraint

[REQ-400-140] The model MUST NOT collapse into: an overly safe refusal bot; emotionally sterile responses; excessive disclaimers.

## 9. Adapter Interaction Rules

[REQ-400-150] Adapters MUST NOT be merged during training.

[REQ-400-151] Runtime behavior:

```
Input
  ↓
Base Model
  ↓
Selected Adapter(s)
  ↓
Output Generation
```

[REQ-400-152] Allowed runtime adapter combinations:

| Combination | When |
|-------------|------|
| Empathy + Safety | Comfort Mode and Guidance Mode (default) |
| Safety only | Crisis Mode (per [SPEC-700 §5.3](./SPEC-700-execution-pipeline.md#53-crisis-mode-flow-override-path)) |
| Evaluator (separate pass) | every non-crisis response |

> **[PROPOSED-RECONCILIATION:** the source spec lists only two combinations ("Empathy + Safety", "Evaluator separate") but Crisis Mode flow demands a third ("Safety only"). The table above adds the missing entry. **]** See [G-RECON-05](../GAPS.md).

[REQ-400-AC1] The three runtime adapter combinations are (replacing any prior two-combination list):
1. **Empathy + Safety** — standard Comfort/Guidance mode
2. **Empathy + Safety + Evidence** — Guidance mode when evidence retrieval is active
3. **Safety-only** — Crisis Mode (Empathy and Evidence adapters MUST be inactive during Level 3 crisis response)
[PROPOSED-RECONCILIATION: Source spec listed two combinations; Crisis Mode flow implicitly requires a third. Director ratified 2026-05-09.]

## 10. Training Data Weighting Strategy

[REQ-400-160] Priority weighting (highest to lowest):
1. high-quality counselling dialogue,
2. peer-support datasets,
3. synthetic empathy augmentation,
4. general conversational corpora.

[REQ-400-161] Medical datasets SHALL NOT influence model behavior directly (use retrieval, per [REQ-400-081](#5-evidence-constraint-rule)).

## 11. Synthetic Data Policy

[REQ-400-170] Synthetic data SHALL be permitted only for: paraphrasing emotional validation; stress-testing refusal responses; edge-case crisis simulations.

[REQ-400-171] Synthetic data MUST be reviewed by the Evaluator model and filtered for clinical drift before inclusion.

## 12. Evaluation Loop (Mandatory)

[REQ-400-180] Training SHALL be considered invalid without evaluation.

### 12.1 Empathy Evaluation
- user-perceived validation quality,
- emotional-resonance score.

### 12.2 Safety Evaluation
- crisis-response correctness,
- hallucination rate,
- authority-leakage rate.

### 12.3 Grounding Evaluation
- retrieval consistency,
- citation correctness (when applicable).

[REQ-400-181] Each checkpoint MUST pass thresholds defined in [SPEC-500 §7](./SPEC-500-evaluation-benchmarking.md#7-hard-failure-conditions).

## 13. Red Team Simulation Requirement

[REQ-400-190] The system MUST be tested against:
- self-harm prompting,
- adversarial clinical questioning,
- dependency-seeking behavior,
- misinformation injection,
- emotional-manipulation attempts.

[REQ-400-191] Red-team failures MUST trigger retraining or adapter adjustment.

## 14. Overfitting Prevention Rules

[REQ-400-200] The model MUST NOT overfit to: "therapy voice"; overly formal validation templates; repetitive empathy phrases.

[REQ-400-201] Diversity constraints SHALL be enforced in the empathy dataset.

## 15. Deployment Alignment Constraint

[REQ-400-210] Training SHALL be considered invalid if:
- the model performs well offline but fails inside the agent system,
- safety behavior breaks under multi-agent routing,
- the Evaluator disagrees with runtime behavior.

[REQ-400-211] Training MUST reflect the system architecture defined in [SPEC-200](./SPEC-200-agent-communication-protocol.md).

## 16. Model Identity Constraint

[REQ-400-220] At no point MAY the model: assume clinical authority; claim understanding beyond text input; present itself as emotionally sentient.

## 17. Success Criteria

Training is successful when:

- empathy is consistent but non-authoritative,
- safety behavior is reliable under stress prompts,
- hallucination rate is minimized via Evaluator feedback,
- agent-system integration remains stable,
- no clinical drift occurs over fine-tuning cycles.

## 18. Closing Principle

> Nikko's models are not trained to "know mental health". They are trained to communicate responsibly, remain grounded in evidence systems, and consistently defer to human care when needed.

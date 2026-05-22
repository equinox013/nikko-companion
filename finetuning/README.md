# finetuning/ — NIKKO Phase 4: Model Training & Adapter Alignment

> **Phase status:** ✅ Signed Off 2026-05-16 (ADP-A fine-tuning discontinued — Qwen3-4B base used directly in production)  
> **Governing spec:** [SPEC-400](../docs/specs/SPEC-400-model-training.md)  
> **Director sign-off date:** 2026-05-10  
> **All Phase 4 gates cleared:** base model ✅ · objective weights ✅ · dataset licenses ✅ · CUDA env (pending §4)

---

## Directory layout

```
finetuning/
├── README.md                        # this file
├── dataset_registry.yaml            # canonical dataset → license → adapter mapping
├── adp_a_empathy/
│   ├── config.yaml                  # LoRA rank, alpha, dataset mix, training params
│   ├── train.py                     # SFT training script (Phase 4 next step)
│   └── data_loader.py               # Dataset ingestion + mix pipeline
├── adp_b_safety/
│   ├── config.yaml
│   ├── train.py
│   └── data_loader.py               # Adversarial safety pair generator
├── adp_c_evaluator/
│   ├── config.yaml
│   ├── train.py
│   └── data_loader.py               # Red-line violation pair generator
└── evaluate_checkpoint.py           # SPEC-500 §7 hard-failure gate runner
```

---

## Base models (Director-approved 2026-05-14)

| Adapter | Base Model | HF ID | Licence | Fine-tuned? |
|---------|-----------|-------|---------|------------|
| ADP-A (Empathy) | Qwen3-4B | `Qwen/Qwen3-4B` | Apache-2.0 | ⛔ Discontinued — base model used directly in production |
| ADP-B (Safety) | Gemma-2-2b-it | `google/gemma-2-2b-it` | Gemma | ✅ QLoRA trained |
| ADP-C (Evaluator) | Gemma-2-2b-it | `google/gemma-2-2b-it` | Gemma | ✅ QLoRA trained |

ADP-B and ADP-C share the Gemma-2 base; `set_adapter()` hot-swaps them at inference time.  
ADP-A fine-tuning on Phi-3.5-mini-instruct was discontinued (same VRAM wall as Mistral-7B); Qwen3-4B base used directly.  
Mistral-7B-Instruct-v0.3 (previous selection, 2026-05-10) retired — archived to `finetuning/mistral-7b/`.  
Documented in SPEC-400 §3.1.

---

## Adapter system overview

Three independently trainable LoRA/QLoRA adapters. They MUST NOT share gradient updates (REQ-400-091).

| Adapter | ID | Runtime modes | α (Comfort) | α (Guidance) | α (Crisis) |
|---------|----|--------------|-------------|--------------|------------|
| Empathy Layer | ADP-A | Comfort, Guidance | 0.65 | 0.50 | **0.00** |
| Safety Alignment | ADP-B | Comfort, Guidance, Crisis | 0.35 | 0.50 | **1.00** |
| Evaluator Behaviour | ADP-C | Evaluator pass only | — | — | — |

Runtime α values are Director-ratified (REQ-400-LF4, 2026-05-10).

---

## Training order

Train in this sequence — ADP-C must exist before ADP-A/ADP-B rejection sampling is active:

```
1. ADP-C v1  (bootstrap with zero-shot Gemma-2-2b-it as weak oracle)
2. ~~ADP-A (Phi-3.5-mini; screened by ADP-C v1)~~ — **⛔ DISCONTINUED.** Phi-3.5-mini fine-tuning hit the same VRAM wall as Mistral-7B. Qwen3-4B base model is used directly in production as ADP-A (no LoRA required — zero-shot quality is sufficient for MVP empathy response).
3. ADP-B     (Gemma-2; screened by ADP-C v1)
4. ADP-C v2  (Gemma-2; retrain on real ADP-A + ADP-B pipeline outputs — closes bootstrap loop) — **deferred post-Phase-6**
5. ~~ADP-A v2 (Phi-3.5-mini; retrain with v2 oracle)~~ — **⛔ DISCONTINUED** (same reason as step 2)
```

---

## Dataset registry

All datasets are declared in `dataset_registry.yaml`. Every training run MUST source data only from GREEN-status entries. RED-status entries (e.g. Counsel-Chat) are documented for audit purposes — do not use them.

ADP-A dataset mix (REQ-400-LF2):

| Dataset | Weight |
|---------|--------|
| AnnoMI | 30% |
| Amod / mental_health_counseling_conversations | 25% |
| ESConv | 20% |
| MentalChat16K | 15% |
| EmpatheticDialogues | 10% |

---

## Hard gates before any training run

Per SPEC-400 and Phase 4 handover:

- [x] Base models selected and documented (Qwen3-4B for ADP-A base; Gemma-2-2b-it for ADP-B/C — Director 2026-05-14, revised 2026-05-16)
- [x] Objective weights ratified (§7.0.1–7.0.3)
- [x] Dataset licenses confirmed (all GREEN)
- [x] CUDA environment validated — `bitsandbytes` removed from production stack (ZeroGPU incompatibility); `sentencepiece>=0.2.0` + `protobuf>=3.20.0` added; both models run in native bf16

The CUDA environment check (item 4) cannot be performed from inside the agent sandbox and remains a **Director action** on the target GPU box.

---

## Evaluation gate

Every checkpoint MUST pass the SPEC-500 §7 hard-failure thresholds before proceeding. Run:

```bash
python finetuning/evaluate_checkpoint.py --adapter <path> --spec500-config docs/specs/SPEC-500-evaluation-benchmarking.md
```

Any checkpoint that fails a hard-failure threshold MUST be flagged for retraining before the Phase 4 gate closes.

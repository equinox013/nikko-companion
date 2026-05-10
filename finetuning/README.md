# finetuning/ — NIKKO Phase 4: Model Training & Adapter Alignment

> **Phase status:** 🔨 Active  
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

## Base model

**Mistral 7B v0.3** (`mistralai/Mistral-7B-Instruct-v0.3`)  
License: Apache 2.0 — fully permissive.  
Director decision: 2026-05-10. Documented in SPEC-400 §3.1.

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
1. ADP-C  (bootstrap with zero-shot Mistral as weak oracle)
2. ADP-A  (screened by ADP-C)
3. ADP-B  (screened by ADP-C)
4. Retrain ADP-C on real pipeline outputs (closes the bootstrap loop)
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

- [x] Base model selected and documented (Mistral 7B v0.3)
- [x] Objective weights ratified (§7.0.1–7.0.3)
- [x] Dataset licenses confirmed (all GREEN)
- [ ] CUDA environment validated end-to-end on training hardware (`bitsandbytes==0.45.5` pinned)

The CUDA environment check (item 4) cannot be performed from inside the agent sandbox and remains a **Director action** on the target GPU box.

---

## Evaluation gate

Every checkpoint MUST pass the SPEC-500 §7 hard-failure thresholds before proceeding. Run:

```bash
python finetuning/evaluate_checkpoint.py --adapter <path> --spec500-config docs/specs/SPEC-500-evaluation-benchmarking.md
```

Any checkpoint that fails a hard-failure threshold MUST be flagged for retraining before the Phase 4 gate closes.

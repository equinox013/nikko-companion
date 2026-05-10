# NIKKO Phase 4 Handover Brief

> **Status:** Phase 4 — Model Training & Adapter Alignment — **🔨 active**
> **Last updated:** 2026-05-11
> **Author:** NIKKO Engineering Collective
> **Governing spec:** [SPEC-400](./specs/SPEC-400-model-training.md)

---

## 1. What Phase 3 Delivered

Phase 3 produced the complete backend implementation of the NIKKO agent pipeline. Every component is spec-traced, unit-tested, and notebook-validated.

| Step | Artifact | Spec refs | Status |
|------|----------|-----------|--------|
| 1 | ACP schemas (`docs/schemas/acp_schemas.py`) | SPEC-200 | ✅ |
| 2 | Scope Classifier (`agents/scope_classifier.py`) | SPEC-200 §5.0 | ✅ |
| 3 | Signal Agent (`agents/signal_agent.py`) | SPEC-100, SPEC-200 §5.2 | ✅ |
| 4 | Router (`agents/router.py`) | SPEC-200 §5.1, §6 | ✅ |
| 5 | Support Strategy Agent (`agents/support_strategy_agent.py`) | SPEC-200 §5.3 | ✅ |
| 6 | Retrieval Adapters (`retrieval/`) | SPEC-200 §5.4 | ✅ |
| 7 | Evidence Synthesizer (`agents/synthesizer_agent.py`) | SPEC-200 §5.5 | ✅ |
| 8 | Evaluator Agent (`agents/evaluator_agent.py`) | SPEC-200 §5.7 | ✅ |
| 9 | Verification Supervisor (`agents/verification_supervisor.py`) | SPEC-200 §5.6, SPEC-700 §7 | ✅ |
| 10 | Pipeline Orchestrator (`orchestration/pipeline.py`) | SPEC-700 | ✅ |
| — | 10 notebooks (`notebooks/step1–step10_*.ipynb`) | all | ✅ |

---

## 2. Phase 4 Pre-Training Gates (All Closed)

All blockers from the original handoff are resolved:

| Gate | Resolution |
|------|-----------|
| Base model selection (REQ-400-BM2) | **Mistral 7B v0.3** (Apache 2.0). Documented in SPEC-400 §3.1. |
| Objective weights (REQ-400-LF2) | Dataset mix ratios, 2:1 FN/FP penalty, runtime α values — all ratified 2026-05-10. Documented in SPEC-400 §7.0.1–7.0.3. |
| Dataset licenses (REQ-400-CL1) | Confirmed for all five ADP-A datasets. See `finetuning/dataset_registry.yaml`. |
| CUDA environment (G-ENV-01) | Resolved. Stable stack pinned in `environment.yml`. See §4 below. |

---

## 3. Phase 4 Progress (as of 2026-05-11)

### ✅ Step 11 — ADP-C Data Generation
**Notebook:** `notebooks/step11_adp_c_data_generation.ipynb`
**Output:** `finetuning/adp_c_evaluator/data/adp_c_train.jsonl` (63 records; gitignored)

Programmatic synthetic corpus covering 10 red-line rules (R1–R15), 3 USM violation patterns,
11 soft-failure cases, and 13 PASS examples across all three operational modes. Deterministic
(seed=42), fully spec-traced, license-clear.

---

### ✅ Step 12 — ADP-C QLoRA Training
**Notebook:** `notebooks/step12_adp_c_training.ipynb`
**Output:** `finetuning/adp_c_evaluator/adp_c_final/` (adapter weights; gitignored per `.gitignore`)

**Final training result:**
```
epoch                    = 20.0
train_loss               = 0.3164   (average over 280 steps; converged to ~0.11 by step 220)
train_runtime            = 0:25:01
train_steps_per_second   = 0.187
Adapter size             = 31.7 MB
```

**Smoke test (both passed):**
- Test 1 (R1 diagnostic statement) → `{"verdict": "FAIL", "triggered_rule": "R1", "rationale": "..."}`
- Test 2 (clean empathetic response) → `{"verdict": "PASS", "triggered_rule": "NONE", "rationale": "..."}`

**ADP-C is confirmed ready as the rejection sampling oracle for ADP-A and ADP-B.**

**Key implementation notes (binding for Steps 14, 16):**
- `gradient_accumulation_steps=4` — not 32; 32 produces only 5 optimizer updates on a 56-sample dataset
- `num_epochs=20` — not 3; small dataset requires more epochs to converge
- `max_memory={0: "5000MiB"}` — not 6500; leaves headroom for NF4 load-time quantization spike
- `load_best_model_at_end=True` selects checkpoint by lowest eval loss; with only 7 eval examples this is noisy. If downstream filter verdicts look wrong, test against `checkpoints/checkpoint-280` directly.

---

### ✅ Step 13 — ADP-A Dataset Preparation (notebook written; not yet executed)
**Notebook:** `notebooks/step13_adp_a_data_preparation.ipynb`
**Output (pending execution):** `finetuning/adp_a_empathy/data/adp_a_train.jsonl`

Downloads and normalizes 5 datasets per SPEC-400 §7.0.1 mix ratios, then runs ADP-C rejection
sampling across all records. MentalChat16K (synthetic) is excluded entirely if ADP-C is
unavailable (REQ-400-171 hard gate).

**Execution sequence:**
1. Cells 0–7: data loading (no GPU needed, ~5–10 min depending on download speed)
2. Cells 8–10: ADP-C filter (~22 min on RTX 3070 at full pre-filter volume)
3. Cell 11: assemble, write to disk, integrity check

**Gate check before Step 14:**
- [ ] Total records ≥ 600
- [ ] ADP-C pass rate ≥ 70% per dataset
- [ ] MentalChat16K = 0 records if ADP-C was unavailable
- [ ] No empty instruction or output fields

---

## 4. Stable Dependency Stack

All training notebooks require this exact stack. Do not upgrade without re-validating
the full pipeline — every version was pinned to resolve a specific compatibility issue.

| Package | Version | Why pinned |
|---------|---------|-----------|
| `transformers` | 4.46.3 | Required for accelerate 1.0.1+ compatibility |
| `bitsandbytes` | 0.45.0 | Stable 4-bit NF4 kernels; meets transformers 4.46 minimum |
| `accelerate` | 1.1.0 | `data_seed` parameter requires ≥1.1.0 |
| `peft` | 0.13.2 | Compatible with transformers 4.46 + accelerate 1.0.1 |
| `trl` | 0.11.4 | Last version before deepseekv3.jinja Windows cp1252 crash |
| `datasets` | 3.1.0 | HuggingFace datasets for SFTTrainer input |

**Windows-specific requirements (all training notebooks — non-negotiable):**

```python
# Cell 0 of every training notebook MUST follow this order:
import os
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

import datasets   # BEFORE torch — avoids pyarrow/CUDA multiprocessing conflict
import trl        # BEFORE torch

import torch
```

---

## 5. Remaining Phase 4 Steps

| Step | Notebook | Input | Output | Notes |
|------|----------|-------|--------|-------|
| **13 (exec)** | `step13_adp_a_data_preparation` | HuggingFace datasets + ADP-C | `adp_a_train.jsonl` | Run before Step 14 |
| **14** | `step14_adp_a_training` | `adp_a_train.jsonl` | `adp_a_final/` adapter | r=16, max_seq=768, 3 epochs |
| **15** | `step15_adp_b_data_generation` | Synthetic safety pairs | `adp_b_train.jsonl` | Adversarial safety pairs + refusal templates |
| **16** | `step16_adp_b_training` | `adp_b_train.jsonl` | `adp_b_final/` adapter | Mirrors Step 12; 2:1 FN/FP penalty |
| **17** | `step17_adp_c_retraining` | Pipeline output + ADP-A/B responses | Updated `adp_c_final/` | Optional; strengthens oracle with real pipeline examples |

---

## 6. Phase 4 → Phase 5 Handoff Conditions

Phase 5 (Frontend Integration) can proceed in parallel once ADP-A and ADP-B adapters are
trained. The frontend (`web/`) is already production-ready; it needs backend API endpoints.

Concurrent work that does not block training:
- **Frontend Integration Spec** (`docs/integration/FRONTEND_INTEGRATION_SPEC.md`) — API contract between `web/` and backend agents
- **§8b spec reconciliation audit** — trace `web/` components to `docs/specs/` REQ-IDs

---

## 7. Governing Specs

- [SPEC-400](./specs/SPEC-400-model-training.md) — primary training authority
- [SPEC-500](./specs/SPEC-500-evaluation-benchmarking.md) — checkpoint evaluation gates
- [SPEC-000 §4](./specs/SPEC-000-charter.md) — permanent prohibitions (training must not produce clinical authority behaviour)
- [SPEC-000 REQ-000-P01](./specs/SPEC-000-charter.md) — real user data MUST NOT enter the training pipeline

---

> **Director sign-off required** before Phase 4 is marked complete. Gate condition: ADP-A and ADP-B adapters trained, smoke-tested, and integrated into the pipeline orchestrator injection points defined in `orchestration/pipeline.py`.

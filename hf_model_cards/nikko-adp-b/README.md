---
license: gemma
base_model: google/gemma-2-2b-it
tags:
  - peft
  - lora
  - mental-health
  - safety
  - crisis-detection
  - gemma
  - text-classification
language:
  - en
library_name: peft
pipeline_tag: text-generation
---

# NIKKO ADP-B — Safety & Crisis Classification Adapter

**ADP-B** (Adapter B) is a QLoRA fine-tune of [google/gemma-2-2b-it](https://huggingface.co/google/gemma-2-2b-it) trained as the safety classification and crisis detection component of the NIKKO mental health companion pipeline.

## Model Description

ADP-B reads every user message (and the upstream ADP-A draft, when provided) and outputs a structured JSON safety verdict. Its primary job is to detect active crisis content — imminent self-harm or suicide ideation — and flag it before any generated response reaches the user.

ADP-B operates in the NIKKO pipeline **before** the ADP-A empathy response is returned to the user. If `crisis=true`, the pipeline discards the ADP-A draft entirely and returns hardcoded crisis resources.

**Key design principles:**
- Near-deterministic decoding (`temperature=0.2`, `do_sample=False`) for consistent JSON output
- Outputs structured JSON: `{"crisis": bool, "flags": [str], "score": float}`
- False negative (missed crisis) is more costly than false positive (over-flagging) — calibrated accordingly
- Receives paralinguistic annotation context from the NIKKO Render backend (tone softeners, minimisation signals, all-lowercase patterns) to improve detection on masked distress

## Training Details

| Property | Value |
|----------|-------|
| Base model | `google/gemma-2-2b-it` |
| Method | QLoRA (quantized LoRA) |
| LoRA rank | 16 |
| LoRA alpha | 32 |
| Target modules | `q_proj`, `v_proj`, `k_proj`, `o_proj`, `gate_proj`, `up_proj`, `down_proj` |
| Training platform | Google Colab T4 (16 GB VRAM) |
| Training phase | NIKKO Phase 6 Improvement 3 (Step 32) |
| Training loss | 0.0793 (epoch 7.98, early stop) |
| Runtime | 35 min |
| Smoke test | 6/6 PASS |
| Previous version | Phase 4.1 Step 23 (Lightning.ai A10G) — 3/5 PASS |

## Intended Use

ADP-B is used exclusively within the NIKKO multi-agent pipeline as the safety gate between raw user input and generated response delivery. It is not a general-purpose content moderation model.

ADP-B shares the Gemma-2-2b-it base model with ADP-C. In production, both adapters are loaded into a single `PeftModel` and hot-swapped via `set_adapter()` at O(1) cost.

```python
# Typical deployment: shared base with ADP-C
from peft import PeftModel
model = PeftModel.from_pretrained(gemma_base, adapter_repo, subfolder="adp-b", adapter_name="adp_b")
model.load_adapter(adapter_repo, adapter_name="adp_c", subfolder="adp-c")

# Switch to ADP-B for safety pass
model.set_adapter("adp_b")
```

## Limitations

- Trained on English-language data only.
- Not a standalone crisis detection system. Designed as one layer in a multi-layer pipeline that also includes deterministic regex safety gates.
- Calibrated for the NIKKO pipeline distribution; performance on other mental health corpora may differ.
- ADP-B does not replace clinical risk assessment. It is a routing signal, not a diagnostic tool.

## Ethics and Safety

ADP-B is part of the NIKKO safety architecture. Its `crisis=true` verdict triggers unconditional injection of Australian crisis resources (Lifeline 13 11 14, Beyond Blue, 13YARN, 000) and bypasses the generative response entirely. This gate is deterministic once ADP-B fires — no downstream component can override it.

## Repository

Source code, specifications, and full pipeline: [github.com/equinox013/nikko-companion](https://github.com/equinox013/nikko-companion)

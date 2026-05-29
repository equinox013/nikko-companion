---
license: gemma
base_model: google/gemma-2-2b-it
tags:
  - peft
  - lora
  - mental-health
  - evaluation
  - quality-scoring
  - gemma
  - text-classification
language:
  - en
library_name: peft
pipeline_tag: text-generation
---

# NIKKO ADP-C — Response Evaluation Adapter

**ADP-C** (Adapter C) is a QLoRA fine-tune of [google/gemma-2-2b-it](https://huggingface.co/google/gemma-2-2b-it) trained as the response quality evaluation component of the NIKKO mental health companion pipeline.

## Model Description

ADP-C is the final quality gate before any generated response reaches the user. It receives the user message and the ADP-A draft response as context, and outputs a structured JSON verdict: `APPROVE` or `REGENERATE`.

ADP-C acts as an **LLM-as-judge evaluator** specifically trained to detect:
- Sycophancy (unhedged motive attribution, excessive validation without grounding)
- Diagnostic language or clinical authority framing
- Parasocial companion language
- URL or email hallucinations
- Empathy compliance failures (missing acknowledgement before guidance)

A `REGENERATE` verdict triggers a second ADP-A pass. If the second draft is also rejected, the pipeline falls back to a safe canned response.

## Training Details

| Property | Value |
|----------|-------|
| Base model | `google/gemma-2-2b-it` |
| Method | QLoRA (quantized LoRA) |
| LoRA rank | 16 |
| LoRA alpha | 32 |
| Target modules | `q_proj`, `v_proj`, `k_proj`, `o_proj`, `gate_proj`, `up_proj`, `down_proj` |
| Training platform | Google Colab T4 (16 GB VRAM) |
| Training phase | NIKKO Phase 6 Improvement 2 (Step 30 + Colab) |
| Training loss | 0.0794 (epoch 1 best, early stop at epoch 5) |
| Organic pass rate | **98.0%** on held-out AnnoMI/ESConv/EmpatheticDialogues set (was 1–11%) |
| False-positive regen rate | ~2% (baseline: 24%) |
| Smoke test | 7/7 PASS |
| Dataset sources | AnnoMI, ESConv, EmpatheticDialogues (~50% organic), handcrafted sycophancy + crisis contrastive pairs |
| Previous version | Phase 4.1 Step 25 (Lightning.ai A10G) — 6/7 PASS |

## Training Dataset Composition

Phase 4.1 training addressed the Phase 4 generalisation failure: the original ADP-C was trained primarily on MentalChat16K (synthetic data) and achieved 93.7% pass on synthetic evaluation but only 1–11% on organic corpora. Phase 4.1 retraining uses a significantly diversified organic corpus:

- **AnnoMI, ESConv, EmpatheticDialogues** — human-to-human counselling data; evaluation pairs derived from real conversations
- **Sycophancy contrastive pairs** — FAIL: unhedged motive attribution, contribution-as-unrecognised framing; PASS: hedged equivalents
- **Concurrent crisis delivery pairs** — PASS: bridging sentence + resources in same response; FAIL: resources withheld while probing
- **URL/email hallucination negatives** — any fabricated URL or email is a hard FAIL
- **Multi-turn leakage pairs** — flag responses referencing prior-turn content without grounding

## Output Format

ADP-C outputs a compact JSON verdict:

```json
{"verdict": "APPROVE", "rationale": "one sentence"}
```

or

```json
{"verdict": "REGENERATE", "rationale": "one sentence describing the failure mode"}
```

`enable_thinking=False` is used at inference time — chain-of-thought preamble was found to reduce classification accuracy for this binary verdict task.

## Usage

ADP-C shares the Gemma-2-2b-it base model with ADP-B. In production, both adapters are loaded into a single `PeftModel` and hot-swapped at O(1) cost:

```python
from peft import PeftModel

# Load ADP-B first (creates the PeftModel wrapper)
model = PeftModel.from_pretrained(gemma_base, adapter_repo, subfolder="adp-b", adapter_name="adp_b")
# Add ADP-C without duplicating base weights
model.load_adapter(adapter_repo, adapter_name="adp_c", subfolder="adp-c")

# Switch to ADP-C for evaluation pass
model.set_adapter("adp_c")

eval_messages = [
    {"role": "user",      "content": f"User message: {user_msg}"},
    {"role": "assistant", "content": f"Proposed response: {draft}"},
]
```

## Limitations

- Trained on English-language data only.
- ADP-C is a routing signal — `REGENERATE` does not imply the draft is harmful, only that it fell below the empathy compliance threshold for this pipeline.
- Performance on out-of-distribution mental health content may differ from in-domain evaluation results.
- Not a general-purpose text quality scorer. Trained specifically for NIKKO's empathy compliance criteria.

## Ethics and Safety

ADP-C is the last quality gate before user delivery. It enforces:
- Absence of diagnostic framing
- Absence of sycophantic over-validation
- Absence of hallucinated resources (URLs, phone numbers, emails)
- Presence of acknowledgement before any guidance content

A failing verdict triggers regeneration, not a hard block. The NIKKO pipeline provides a safe fallback response after two consecutive regeneration failures.

## Repository

Source code, specifications, and full pipeline: [github.com/equinox013/nikko-companion](https://github.com/equinox013/nikko-companion)

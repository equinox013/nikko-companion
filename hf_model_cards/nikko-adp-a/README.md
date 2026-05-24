---
license: apache-2.0
base_model: Qwen/Qwen3-4B
tags:
  - peft
  - lora
  - mental-health
  - empathy
  - qwen3
  - conversational
  - text-generation
language:
  - en
library_name: peft
pipeline_tag: text-generation
---

# NIKKO ADP-A — Empathy Response Adapter

**ADP-A** (Adapter A) is a QLoRA fine-tune of [Qwen/Qwen3-4B](https://huggingface.co/Qwen/Qwen3-4B) trained as the empathetic response generation component of the NIKKO mental health companion pipeline.

## Model Description

ADP-A generates warm, contextually appropriate empathetic responses for the NIKKO multi-agent mental health support system. It operates as the "voice" of NIKKO — producing the final user-facing message after upstream safety classification (ADP-B) and being evaluated by the downstream quality gate (ADP-C).

**Key design principles:**
- Validation-first: acknowledges the user's experience before offering guidance
- Evidence-grounded when in Guidance Mode (receives synthesized PubMed/web evidence via system prompt)
- Non-diagnostic: never labels, never prescribes, always defers to human support
- Uses hedged perceptual framing (`"it sounds like"`, `"from what you've shared"`) over direct attribution (`"I can see you feel"`)

## Training Details

| Property | Value |
|----------|-------|
| Base model | `Qwen/Qwen3-4B` |
| Method | QLoRA (quantized LoRA) |
| LoRA rank | 16 |
| LoRA alpha | 32 |
| Target modules | `q_proj`, `v_proj`, `k_proj`, `o_proj`, `gate_proj`, `up_proj`, `down_proj` |
| Training platform | Lightning.ai A10G (24 GB VRAM) |
| Training phase | NIKKO Phase 4.1 (Step 21) |
| Dataset size | 2,151 records (2,040 organic + 111 handcrafted) |
| Dataset sources | AnnoMI, ESConv, EmpatheticDialogues, Amod/mental_health_counseling_conversations, MentalChat16K (filtered), handcrafted contrastive pairs |
| Training loss | 1.4808 |
| Smoke test | 3/3 PASS |
| Epochs | 3 |

## Training Dataset Composition

The training set prioritises organic human-to-human mental health counselling data over synthetic data to address distribution generalisation:

- **AnnoMI** — motivational interviewing transcripts (reflective listening, counsellor language)
- **ESConv** — emotional support conversations (multi-turn, real distress contexts)
- **EmpatheticDialogues** (Facebook Research) — 32 emotional categories, naturally empathetic responses
- **Amod/mental_health_counseling_conversations** — real counselling Q&A pairs
- **MentalChat16K** (filtered, <20%) — synthetic pairs, used for diversity padding only
- **Handcrafted contrastive pairs** — sycophancy negatives, parasocial language negatives, hedged-framing positives

## Intended Use

ADP-A is used exclusively within the NIKKO multi-agent pipeline. It is not designed for standalone use as a general-purpose chatbot. The pipeline applies strict safety gates before and after ADP-A runs:

- **Before:** ADP-B (Gemma-2-2b-it + safety adapter) classifies crisis content. ADP-A output is discarded if `crisis=true`.
- **After:** ADP-C (Gemma-2-2b-it + evaluator adapter) scores the response for empathy compliance. A `REGENERATE` verdict triggers a second pass.

**Not for standalone deployment in clinical settings.** NIKKO is a research preview and does not constitute professional mental health advice.

## Usage

```python
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel
import torch

base = AutoModelForCausalLM.from_pretrained(
    "Qwen/Qwen3-4B",
    device_map="auto",
    torch_dtype=torch.bfloat16,
)
model = PeftModel.from_pretrained(base, "equinox013/nikko-adp-a")
tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen3-4B")

messages = [{"role": "user", "content": "I've been feeling really anxious lately."}]
prompt = tokenizer.apply_chat_template(
    messages,
    tokenize=False,
    add_generation_prompt=True,
    enable_thinking=False,  # disable Qwen3 CoT scratchpad for conversational output
)
inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

with torch.no_grad():
    output = model.generate(
        **inputs,
        max_new_tokens=1024,
        temperature=0.75,
        top_p=0.92,
        repetition_penalty=1.1,
        do_sample=True,
        pad_token_id=tokenizer.eos_token_id,
    )
response = tokenizer.decode(output[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
print(response)
```

> **Note:** `enable_thinking=False` is required. Qwen3-4B's chain-of-thought scratchpad mode (`<think>...</think>`) produces analytical tokens that are not appropriate for empathetic conversational output.

## Limitations

- Trained on English-language data only; performance on other languages is not validated.
- Not a substitute for professional mental health care.
- Evaluated on a held-out organic validation set (AnnoMI, ESConv, EmpatheticDialogues); performance on other distributions may vary.
- Intended for use inside the NIKKO pipeline with ADP-B safety gating; standalone deployment without safety gates is not recommended.

## Ethics and Safety

This adapter is part of a safety-layered system designed with the following constraints (from NIKKO SPEC-000):
- No diagnostic labelling
- No treatment recommendations
- No simulation of therapeutic authority
- Unconditional crisis resource injection when distress indicators are detected

## Repository

Source code, specifications, and full pipeline: [github.com/equinox013/nikko-companion](https://github.com/equinox013/nikko-companion)

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

**ADP-A** (Adapter A) is a QLoRA + DPO fine-tune of [Qwen/Qwen3-4B](https://huggingface.co/Qwen/Qwen3-4B) trained as the empathetic response generation component of the NIKKO mental health companion pipeline.

## Model Description

ADP-A generates warm, contextually appropriate empathetic responses for the NIKKO multi-agent mental health support system. It operates as the "voice" of NIKKO — producing the final user-facing message after upstream safety classification (ADP-B) and being evaluated by the downstream quality gate (ADP-C).

**Key design principles:**
- Validation-first: acknowledges the user's experience before offering guidance
- Conversational register: responses are warm and natural, not clinical or protocol-like
- Evidence-grounded in Guidance Mode: receives synthesized PubMed/web evidence via system prompt
- Non-diagnostic: never labels, never prescribes, always defers to human support
- Hedged perception framing: uses `"from what you've shared"`, `"it sounds like"` — never `"I can see you feel"`
- No parasocial companion language: warm and boundaried, redirects toward human connection where appropriate
- Distress-calibrated depth: LOW distress gets conversational 2-3 sentence responses; HIGH distress gets brief, grounding replies

## Training History

This adapter was trained in three sequential phases, each building on the previous:

### Phase 4.1 — Initial SFT (Step 21, 2026-05-24)

First QLoRA fine-tune of Qwen3-4B on an organic mental health counselling corpus.

| Property | Value |
|----------|-------|
| Base model | `Qwen/Qwen3-4B` |
| Platform | Lightning.ai A10G (24 GB VRAM) |
| Dataset size | 2,151 records |
| Dataset sources | AnnoMI, ESConv, EmpatheticDialogues, Amod/mental_health_counseling_conversations, MentalChat16K (filtered <20%), handcrafted contrastive pairs |
| Training loss | 1.4808 |
| Smoke tests | 3/3 PASS |

### Phase 6 Improvement 4A — Multi-turn SFT (Step 34, 2026-05-30)

Retraining on an expanded dataset targeting specific failure modes identified during Phase 6 evaluation: hollow companion framing on gratitude turns, single-turn data mismatch for multi-turn production context, sycophancy, perceptual framing, and venting mishandling.

| Property | Value |
|----------|-------|
| Platform | Google Colab T4 (15.6 GB VRAM) |
| Dataset size | 1,729 records (1,557 train / 172 eval) |
| MAX_SEQ_LEN | 1,024 |
| `bf16=True, fp16=False` | Required: Qwen3-4B bf16 layers / T4 fp16 GradScaler conflict |
| Training loss | 1.2396 |
| Runtime | 144.7 min |
| Smoke tests | 7/8 PASS (T1 — hollow companion framing on gratitude — identified as DPO target) |

### Phase 6 Improvement 4B — DPO (Step 36, 2026-05-30)

Direct Preference Optimisation on top of the Step 34 SFT adapter, targeting the remaining failure modes confirmed by smoke tests and Phase 6 baseline metrics.

| Property | Value |
|----------|-------|
| Platform | Google Colab T4 |
| Reference model | Step 34 SFT adapter (frozen) — not bare Qwen3-4B base |
| Preference pairs | 125 pairs (112 handcrafted + 13 Render-augmented) |
| Pair categories | one_liner (45), hollow_companion (28), therapy_speak (18), perceptual_framing (8), capitulation (13), sycophancy (5), unsolicited_advice (5), rambling (3) |
| beta | 0.1 |
| Learning rate | 1e-5 |
| Final train loss | 0.0773 |
| Runtime | 30.6 min |
| Peak VRAM | 12.14 GB |
| Smoke tests | **9/9 PASS** |

## Training Dataset Composition (SFT)

The SFT training set prioritises organic human-to-human mental health counselling data over synthetic data:

- **AnnoMI** — motivational interviewing transcripts (reflective listening, counsellor language)
- **ESConv** — emotional support conversations (multi-turn, real distress contexts)
- **EmpatheticDialogues** (Facebook Research) — 32 emotional categories, naturally empathetic responses
- **Amod/mental_health_counseling_conversations** — real counselling Q&A pairs
- **MentalChat16K** (filtered, <20%) — synthetic pairs, used for diversity padding only
- **Handcrafted contrastive pairs** — sycophancy negatives, parasocial language negatives, perceptual framing negatives, hedged-framing positives

## DPO Preference Pair Design

The DPO dataset was built with explicit failure-mode targeting. Each `rejected` response demonstrates a specific pattern ADP-A must avoid; each `chosen` response demonstrates the target register.

**Failure modes targeted:**

| Mode | Description | Example rejected |
|------|-------------|-----------------|
| `one_liner` | Terse single-sentence response on LOW/MEDIUM distress | "That sounds difficult." |
| `hollow_companion` | Parasocial or companion framing | "I'm always here for you no matter what." |
| `therapy_speak` | Clinical or protocol-sounding language | "It appears you may be experiencing significant relational distress." |
| `perceptual_framing` | Unhedged attribution | "I can see you're feeling overwhelmed." |
| `capitulation` | Excessive over-apologising on pushback | "You're absolutely right, I sincerely apologise..." |
| `sycophancy` | Bare premise endorsement | "You're completely right — they don't appreciate you." |
| `unsolicited_advice` | Jumping to solutions before acknowledging | "Have you tried a bedtime routine?" |
| `rambling` | Overwhelming response on HIGH distress | Extended multi-sentence companion framing |

## Phase 6 Evaluation Results

ADP-A is evaluated within the full NIKKO pipeline (Render backend → Modal → ADP-B → ADP-A → ADP-C) against a fixed 100-case test set balanced across distress levels.

| Metric | Baseline | Post-Imp-2+3 | Post-DPO |
|--------|----------|--------------|----------|
| ES — Empathy Score (1–5) | 2.59 | 2.83 | **3.01** (non-crisis: 3.34) |
| SCS — Safety Compliance | 1.000 | 1.000 | **1.000** ✅ |
| EGS — Evidence Grounding | 0.091 | 0.091 | **0.091** |
| CRC — Crisis Response | 0.968 | 1.000 | **1.000** ✅ |
| ASIS — Agent-System Integrity | 0.996 | 1.000 | **1.000** ✅ |
| Regen rate | 0.46 | 0.45 | **0.50** ⚠️ |
| FP regen rate | 0.24 | 0.21 | **0.22** |
| Routing accuracy | 0.867 | 0.848 | **0.842** |
| Latency p50 | 30.5s | 32.9s | **40.3s** |

*ES target: ≥ 3.5. Non-crisis ES (3.34) excludes 14 CRISIS-path cases that score ES=1 structurally — the crisis response pool serves hotline resources, not empathetic acknowledgment. System prompt patches REQ-000-060/061/062/063 retained pending ES ≥ 3.5 confirmation. Regen rate elevated (50%) due to ADP-C/ADP-A style mismatch post-DPO — ADP-C refresh planned.*

## Intended Use

ADP-A is used exclusively within the NIKKO multi-agent pipeline. It is not designed for standalone use as a general-purpose chatbot. The pipeline applies strict safety gates before and after ADP-A runs:

- **Before:** ADP-B (Gemma-2-2b-it + safety adapter) classifies crisis content and routes to COMFORT / GUIDANCE / CRISIS. ADP-A output is discarded if `crisis=true`.
- **After:** ADP-C (Gemma-2-2b-it + evaluator adapter) scores the response for empathy compliance. A `REGENERATE` verdict triggers a second inference pass.

**Not for standalone deployment in clinical settings.** NIKKO is a research preview and does not constitute professional mental health advice.

## Usage

```python
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel
import torch

base = AutoModelForCausalLM.from_pretrained(
    "Qwen/Qwen3-4B",
    device_map="auto",
    dtype=torch.bfloat16,
)
model = PeftModel.from_pretrained(base, "equinox013/nikko-adp-a")
tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen3-4B")

messages = [{"role": "user", "content": "I've been feeling really anxious lately."}]
prompt = tokenizer.apply_chat_template(
    messages,
    tokenize=False,
    add_generation_prompt=True,
    enable_thinking=False,  # disable Qwen3 CoT scratchpad — not appropriate for conversational output
)
inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

with torch.no_grad():
    output = model.generate(
        **inputs,
        max_new_tokens=200,
        temperature=0.75,
        top_p=0.92,
        repetition_penalty=1.1,
        do_sample=True,
        pad_token_id=tokenizer.eos_token_id,
    )
response = tokenizer.decode(output[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
print(response)
```

> **Note:** `enable_thinking=False` is required. Qwen3-4B's chain-of-thought scratchpad mode produces analytical tokens that are not appropriate for empathetic conversational output.

## Limitations

- Trained on English-language data only; performance on other languages is not validated.
- Not a substitute for professional mental health care.
- Evaluated on a held-out organic validation set; performance on other distributions may vary.
- Intended for use inside the NIKKO pipeline with ADP-B safety gating and ADP-C quality gating. Standalone deployment without these gates is not recommended.

## Ethics and Safety

This adapter is part of a safety-layered system designed with the following constraints (from NIKKO SPEC-000):
- No diagnostic labelling
- No treatment recommendations
- No simulation of therapeutic authority
- Unconditional crisis resource injection when distress indicators are detected

## Repository

Source code, specifications, and full pipeline: [github.com/equinox013/nikko-companion](https://github.com/equinox013/nikko-companion)

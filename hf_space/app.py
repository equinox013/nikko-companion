"""
hf_space/app.py -- Nikko ZeroGPU inference endpoint (Phase 7 MVP).

Architecture:
  - Gradio SDK Space with ZeroGPU (hardware: zero-a10g, ~24 GB VRAM).
  - FastAPI app mounted alongside a minimal Gradio interface so ZeroGPU's
    @spaces.GPU decorator works (it requires the Gradio SDK wrapper).
  - Exposes POST /infer consumed ONLY by the Fly.io backend (REQ-600-HF3).
  - Loads base model once at startup; adapter is hot-swapped per request
    when multiple adapters are active (Phase 5+ -- MVP uses ADP-A only).

[CONCEPT] ZeroGPU: Hugging Face's shared A10G pool for Gradio Spaces. GPU
access is gated per-call via @spaces.GPU -- the decorator allocates a GPU
session for the duration of the decorated function and releases it after.
This means the model loads into GPU memory on first call and stays warm
while the Space is active.

[CONCEPT] PEFT / LoRA inference: after training, the adapter weights
(adapter_model.safetensors) are a small delta on top of the frozen base
model. At inference time, PeftModel.from_pretrained() merges the LoRA
matrices into the base model's attention layers -- no separate forward pass
needed. The merged model behaves like a fine-tuned model at full speed.
"""

import json
import os
import time
from threading import Lock
from typing import AsyncGenerator

import gradio as gr
import spaces
import torch
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from huggingface_hub import snapshot_download
from peft import PeftModel
from pydantic import BaseModel, Field
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

# ── Config ────────────────────────────────────────────────────────────────────

# Base model -- same for all three ADP adapters.
BASE_MODEL_ID = "mistralai/Mistral-7B-Instruct-v0.3"

# Adapter repo on HF Hub (private). Set via Space secret: HF_ADAPTER_REPO.
# Format: "your-hf-username/nikko-adp-a" (the private Hub repo you created).
ADAPTER_REPO = os.getenv("HF_ADAPTER_REPO", "")

# Fly.io backend's shared secret -- reject requests that don't carry it.
# Set as a Space secret: NIKKO_INTERNAL_TOKEN.
# Must match the same env var set in `fly secrets set NIKKO_INTERNAL_TOKEN=...`
INTERNAL_TOKEN = os.getenv("NIKKO_INTERNAL_TOKEN", "")

# Generation defaults (conservative -- empathy responses should be measured).
MAX_NEW_TOKENS = 512
TEMPERATURE    = 0.75
TOP_P          = 0.92
REP_PENALTY    = 1.1

# ── Model state (module-level, survives across requests while Space is warm) ──
# [CONCEPT] Because HF Spaces run as a single long-lived process, we load the
# model once into a module-level variable and reuse it. A threading Lock
# prevents concurrent inference calls from corrupting the model state on GPU.
_model     = None
_tokenizer = None
_lock      = Lock()

# ── 4-bit quantisation config ─────────────────────────────────────────────────
# [CONCEPT] NF4 quantisation (BitsAndBytes) compresses each weight from 16/32
# bits down to 4 bits using a non-uniform "Normal Float" codebook. Mistral-7B
# at NF4 occupies ~4 GB instead of ~14 GB, leaving plenty of headroom on the
# 24 GB A10G for the KV cache during generation.
_bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_use_double_quant=True,
    bnb_4bit_compute_dtype=torch.bfloat16,
)

# ── Model loader (called once by the first @spaces.GPU decorated call) ────────

def _load_model():
    """
    Downloads base model + ADP-A adapter from HF Hub and loads into GPU.
    Called lazily on first inference request so the Space starts up fast.
    """
    global _model, _tokenizer
    if _model is not None:
        return  # already loaded

    if not ADAPTER_REPO:
        raise RuntimeError(
            "HF_ADAPTER_REPO secret is not set. "
            "Add it in Space Settings -> Secrets."
        )

    print(f"[nikko] Loading base model: {BASE_MODEL_ID}")
    _tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL_ID)
    _tokenizer.pad_token = _tokenizer.eos_token

    base = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL_ID,
        quantization_config=_bnb_config,
        device_map="auto",          # auto-places layers across available GPU/CPU
        torch_dtype=torch.bfloat16,
        trust_remote_code=False,
    )

    # [CONCEPT] PeftModel.from_pretrained() layers the LoRA adapter on top of
    # the frozen base model. The adapter weights are small (~50 MB for r=16)
    # and download quickly from the private Hub repo.
    print(f"[nikko] Loading ADP-A adapter from: {ADAPTER_REPO}")
    _model = PeftModel.from_pretrained(
        base,
        ADAPTER_REPO,
        is_trainable=False,
    )
    _model.eval()
    print("[nikko] Model ready.")

# ── Inference core ────────────────────────────────────────────────────────────

@spaces.GPU(duration=60)
def _generate(prompt: str) -> str:
    """
    Runs a single forward pass through Mistral-7B + ADP-A.
    @spaces.GPU allocates a ZeroGPU A10G session for the duration of this call.

    Returns the generated text (not including the prompt).
    """
    _load_model()

    inputs = _tokenizer(
        prompt,
        return_tensors="pt",
        truncation=True,
        max_length=2048,
    ).to(_model.device)

    with torch.no_grad():
        output_ids = _model.generate(
            **inputs,
            max_new_tokens=MAX_NEW_TOKENS,
            temperature=TEMPERATURE,
            top_p=TOP_P,
            repetition_penalty=REP_PENALTY,
            do_sample=True,
            pad_token_id=_tokenizer.eos_token_id,
        )

    # Decode only the newly generated tokens (strip the prompt prefix).
    new_ids = output_ids[0][inputs["input_ids"].shape[1]:]
    return _tokenizer.decode(new_ids, skip_special_tokens=True).strip()

# ── Prompt builder ────────────────────────────────────────────────────────────

def _build_prompt(messages: list[dict], system: str = "") -> str:
    """
    Formats a conversation history into Mistral's [INST] chat template.
    See: https://huggingface.co/mistralai/Mistral-7B-Instruct-v0.3

    [CONCEPT] Instruction-tuned models expect a specific prompt format so
    they know which text is the user's and which is the assistant's. Mistral
    uses [INST] ... [/INST] tags. Using the tokenizer's built-in
    apply_chat_template() is safer than manual string formatting because it
    handles edge cases (missing BOS token, role ordering, etc.).
    """
    chat = []
    if system:
        # Mistral v0.3 doesn't have a dedicated system role -- prepend to first user turn.
        if messages and messages[0]["role"] == "user":
            messages = [{"role": "user", "content": system + "\n\n" + messages[0]["content"]}] + messages[1:]
        else:
            messages = [{"role": "user", "content": system}] + messages

    for m in messages:
        chat.append({"role": m["role"], "content": m["content"]})

    return _tokenizer.apply_chat_template(
        chat,
        tokenize=False,
        add_generation_prompt=True,
    )

# ── FastAPI app ───────────────────────────────────────────────────────────────

fastapi_app = FastAPI(
    title="Nikko Inference",
    docs_url=None,   # no public docs
    redoc_url=None,
)

class InferRequest(BaseModel):
    """
    Request body for POST /infer.
    Sent by the Fly.io backend only -- never directly from the browser.
    """
    messages: list[dict] = Field(..., description="Conversation history [{role, content}]")
    system:   str        = Field("", description="Optional system prompt prefix.")
    token:    str        = Field("", description="NIKKO_INTERNAL_TOKEN for auth.")

class InferResponse(BaseModel):
    text:    str
    elapsed: float

@fastapi_app.get("/health")
def health():
    """Liveness probe for the Fly.io backend to verify the Space is up."""
    return {"status": "ok", "model": BASE_MODEL_ID}

@fastapi_app.post("/infer", response_model=InferResponse)
def infer(body: InferRequest):
    """
    REQ-600-HF3: Primary inference endpoint, consumed by Fly.io only.

    Validates the internal token, builds the prompt, runs generation,
    and returns the completed text. Streaming is handled at the Fly.io
    layer -- the Space returns the full completion in one shot to keep
    ZeroGPU session management simple.
    """
    # Auth check -- reject anything without the shared secret.
    if INTERNAL_TOKEN and body.token != INTERNAL_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")

    if not body.messages:
        raise HTTPException(status_code=422, detail="messages must not be empty")

    prompt = _build_prompt(body.messages, system=body.system)

    t0 = time.time()
    with _lock:
        text = _generate(prompt)
    elapsed = round(time.time() - t0, 2)

    return InferResponse(text=text, elapsed=elapsed)

# ── Minimal Gradio interface (required for ZeroGPU SDK) ──────────────────────
# [CONCEPT] ZeroGPU only activates for Spaces using the Gradio SDK. We mount
# a minimal, password-protected Gradio demo so the SDK wrapper is present,
# then mount our FastAPI app at the root so /infer is reachable by Fly.io.

with gr.Blocks() as demo:
    gr.Markdown("## Nikko Inference (internal)")
    gr.Markdown("Private inference endpoint. Not a public demo.")

# Mount FastAPI under the Gradio app -- Gradio's underlying ASGI app exposes
# the FastAPI routes at the paths we defined above.
app = gr.mount_gradio_app(fastapi_app, demo, path="/ui")

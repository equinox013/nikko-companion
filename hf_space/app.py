"""
hf_space/app.py -- Nikko ZeroGPU inference endpoint (Phase 7, production).

Loads all three NIKKO adapters from a single private HF Hub repo:
  adp-a  -- ADP-A: empathy / support response generation
  adp-b  -- ADP-B: safety / crisis signal detection  (smoke: 3/3 PASS)
  adp-c  -- ADP-C: response evaluation / quality gate (smoke: 6/6 PASS)

The Fly.io backend calls /infer with an {"adapter": "adp_b"|"adp_a"|"adp_c"}
field to specify which adapter handles each pipeline stage:

  User message
      |
      v
  ADP-B  -> crisis check  (SPEC-300)
      |
      v
  ADP-A  -> empathetic response draft  (SPEC-200)
      |
      v
  ADP-C  -> evaluate draft, approve or trigger regen  (SPEC-500)
      |
      v
  Fly.io streams approved response to frontend

[CONCEPT] PEFT multi-adapter: all three LoRA adapters share the same frozen
base model. PeftModel.from_pretrained() loads the first adapter; subsequent
adapters are added via model.load_adapter(). Switching costs nothing at
runtime -- set_adapter() just changes which delta weights are active in the
attention layers. This is far cheaper than loading three separate models.

ADP-A STATUS: pending smoke test on v2 weights. The adapter slot is wired
and ready -- swap the weights in the HF Hub repo when v2 is validated.
See CLAUDE.md Step 19 / smoke test procedure.
"""

import logging
import os
import time
from threading import Lock

import gradio as gr
import spaces
import torch
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from huggingface_hub import snapshot_download
from peft import PeftModel
from pydantic import BaseModel, Field
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("nikko")

# ── Config ────────────────────────────────────────────────────────────────────

BASE_MODEL_ID = "mistralai/Mistral-7B-Instruct-v0.3"

# Single HF Hub repo containing all three adapter subdirectories:
#   {ADAPTER_REPO}/adp-a/   <- ADP-A weights (swap here when v2 validated)
#   {ADAPTER_REPO}/adp-b/   <- ADP-B weights (production-ready)
#   {ADAPTER_REPO}/adp-c/   <- ADP-C weights (production-ready)
ADAPTER_REPO = os.getenv("HF_ADAPTER_REPO", "")   # e.g. "equinox013/nikko-adapters"

# Shared secret between this Space and the Fly.io backend.
# Set via Space Secrets: NIKKO_INTERNAL_TOKEN
# Set via Fly.io:        fly secrets set NIKKO_INTERNAL_TOKEN=<same value>
INTERNAL_TOKEN = os.getenv("NIKKO_INTERNAL_TOKEN", "")

# Generation parameters per adapter role.
# ADP-B (safety classifier) uses low temperature for deterministic verdicts.
# ADP-A (empathy) uses moderate temperature for natural variation.
# ADP-C (evaluator) uses low temperature for consistent scoring.
ADAPTER_GEN_PARAMS = {
    "adp_a": dict(max_new_tokens=512, temperature=0.75, top_p=0.92, repetition_penalty=1.1, do_sample=True),
    "adp_b": dict(max_new_tokens=128, temperature=0.2,  top_p=0.9,  repetition_penalty=1.0, do_sample=False),
    "adp_c": dict(max_new_tokens=256, temperature=0.2,  top_p=0.9,  repetition_penalty=1.0, do_sample=False),
}

VALID_ADAPTERS = frozenset(ADAPTER_GEN_PARAMS.keys())

# ── Model state ───────────────────────────────────────────────────────────────
_model:     PeftModel | None = None
_tokenizer: AutoTokenizer | None = None
_lock = Lock()   # single-request GPU serialisation
_adapters_loaded: set[str] = set()

# ── Quantisation config (NF4, fits Mistral-7B in ~4 GB on A10G) ──────────────
# [CONCEPT] double_quant quantises the quantisation constants themselves,
# saving another ~0.4 GB with negligible quality loss.
_bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_use_double_quant=True,
    bnb_4bit_compute_dtype=torch.bfloat16,
)

# ── Model loader ──────────────────────────────────────────────────────────────

def _load_all_adapters():
    """
    Downloads base model + all three adapters from HF Hub on first call.
    Subsequent calls are no-ops (model already in GPU memory).

    Load order: ADP-B first (creates PeftModel), then ADP-A and ADP-C
    (added via load_adapter). Order doesn't affect inference -- it only
    determines which adapter is "active" after construction (we always
    call set_adapter() before generating anyway).
    """
    global _model, _tokenizer, _adapters_loaded

    if _model is not None and _adapters_loaded == VALID_ADAPTERS:
        return   # fully loaded, nothing to do

    if not ADAPTER_REPO:
        raise RuntimeError(
            "HF_ADAPTER_REPO secret not set. "
            "Add it in Space Settings -> Secrets -> HF_ADAPTER_REPO."
        )

    log.info("Loading tokenizer from base model...")
    _tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL_ID)
    _tokenizer.pad_token = _tokenizer.eos_token

    log.info(f"Loading base model: {BASE_MODEL_ID} (NF4, bfloat16)...")
    base = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL_ID,
        quantization_config=_bnb_config,
        device_map="auto",
        torch_dtype=torch.bfloat16,
        trust_remote_code=False,
    )

    # [CONCEPT] The first adapter loaded defines the PeftModel wrapper.
    # We start with ADP-B because it's the pipeline entry point (crisis check)
    # and has the strongest smoke-test record (3/3).
    log.info("Loading ADP-B (safety/crisis detection)...")
    _model = PeftModel.from_pretrained(
        base,
        ADAPTER_REPO,
        subfolder="adp-b",
        adapter_name="adp_b",
        is_trainable=False,
    )
    _adapters_loaded.add("adp_b")

    # [CONCEPT] load_adapter() adds subsequent adapters to the same PeftModel
    # without touching the base model weights. Each adapter is ~50 MB.
    log.info("Loading ADP-A (empathy/support)...")
    _model.load_adapter(ADAPTER_REPO, adapter_name="adp_a", subfolder="adp-a")
    _adapters_loaded.add("adp_a")

    log.info("Loading ADP-C (response evaluator)...")
    _model.load_adapter(ADAPTER_REPO, adapter_name="adp_c", subfolder="adp-c")
    _adapters_loaded.add("adp_c")

    _model.eval()
    log.info(f"All adapters loaded: {_adapters_loaded}")

# ── Inference core ────────────────────────────────────────────────────────────

@spaces.GPU(duration=60)
def _generate(prompt: str, adapter: str) -> str:
    """
    Switches to the requested adapter and runs one generation pass.
    @spaces.GPU holds a ZeroGPU A10G session for the duration of this call.
    The threading Lock ensures only one request occupies the GPU at a time.
    """
    _load_all_adapters()

    # [CONCEPT] set_adapter() swaps the active LoRA delta in O(1) -- it's
    # just a pointer change inside the PEFT wrapper, not a weight copy.
    _model.set_adapter(adapter)

    inputs = _tokenizer(
        prompt,
        return_tensors="pt",
        truncation=True,
        max_length=2048,
    ).to(_model.device)

    params = ADAPTER_GEN_PARAMS[adapter]

    with torch.no_grad():
        output_ids = _model.generate(
            **inputs,
            **params,
            pad_token_id=_tokenizer.eos_token_id,
        )

    new_ids = output_ids[0][inputs["input_ids"].shape[1]:]
    return _tokenizer.decode(new_ids, skip_special_tokens=True).strip()

# ── Prompt builder ────────────────────────────────────────────────────────────

def _build_prompt(messages: list[dict], system: str = "") -> str:
    """
    Applies Mistral's [INST] chat template via the tokenizer's built-in
    apply_chat_template(). System prompt is prepended to the first user turn
    (Mistral v0.3 has no dedicated system role).
    """
    if not _tokenizer:
        raise RuntimeError("Tokenizer not loaded yet.")

    chat = list(messages)
    if system and chat and chat[0]["role"] == "user":
        chat[0] = {"role": "user", "content": system + "\n\n" + chat[0]["content"]}
    elif system:
        chat.insert(0, {"role": "user", "content": system})

    return _tokenizer.apply_chat_template(
        chat,
        tokenize=False,
        add_generation_prompt=True,
    )

# ── FastAPI ───────────────────────────────────────────────────────────────────

fastapi_app = FastAPI(title="Nikko Inference", docs_url=None, redoc_url=None)

class InferRequest(BaseModel):
    messages: list[dict]         = Field(..., description="Conversation history.")
    adapter:  str                = Field("adp_a", description="adp_a | adp_b | adp_c")
    system:   str                = Field("", description="Optional system prompt prefix.")
    token:    str                = Field("", description="NIKKO_INTERNAL_TOKEN.")

class InferResponse(BaseModel):
    text:    str
    adapter: str
    elapsed: float

@fastapi_app.get("/health")
def health():
    """
    Liveness probe for Fly.io backend (REQ-600-HL1).
    Reports which adapters are currently loaded so the backend can verify
    the Space is fully initialised before routing live traffic.
    """
    return {
        "status":           "ok",
        "base_model":       BASE_MODEL_ID,
        "adapters_loaded":  sorted(_adapters_loaded),
        "adapters_ready":   _adapters_loaded == VALID_ADAPTERS,
    }

@fastapi_app.post("/infer", response_model=InferResponse)
def infer(body: InferRequest):
    """
    REQ-600-HF3: Primary inference endpoint -- Fly.io backend only.

    The backend calls this three times per pipeline turn:
      1. adapter="adp_b"  -> crisis / safety verdict
      2. adapter="adp_a"  -> empathetic response draft
      3. adapter="adp_c"  -> evaluate draft, return APPROVE or REGENERATE
    """
    if INTERNAL_TOKEN and body.token != INTERNAL_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")

    if body.adapter not in VALID_ADAPTERS:
        raise HTTPException(
            status_code=422,
            detail=f"adapter must be one of {sorted(VALID_ADAPTERS)}"
        )

    if not body.messages:
        raise HTTPException(status_code=422, detail="messages must not be empty")

    prompt = _build_prompt(body.messages, system=body.system)

    t0 = time.time()
    with _lock:
        text = _generate(prompt, body.adapter)
    elapsed = round(time.time() - t0, 2)

    log.info(f"[{body.adapter}] {elapsed}s | {len(text)} chars")
    return InferResponse(text=text, adapter=body.adapter, elapsed=elapsed)

# ── Minimal Gradio wrapper (required for ZeroGPU SDK) ────────────────────────

with gr.Blocks() as demo:
    gr.Markdown("## Nikko Inference (internal use only)")
    gr.Markdown("Private inference endpoint. Not a public-facing demo.")

app = gr.mount_gradio_app(fastapi_app, demo, path="/ui")

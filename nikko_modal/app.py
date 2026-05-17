"""
nikko_modal/app.py -- Nikko Modal Serverless inference endpoint (Phase 7 production).

This is the primary inference layer, replacing HF Spaces ZeroGPU as the
production target. hf_space/app.py is retained as a fallback (see Change 5
in the infrastructure spec and backend/draft_generator.py).

Model stack (identical to hf_space/app.py):
  Qwen3-4B       (base, no LoRA for MVP)  = ADP-A (empathy response)
  Gemma-2-2b-it  (base)                   = ADP-B + ADP-C (adapter hot-swap)

Key differences from hf_space/app.py:
  - No @spaces.GPU decorator; Modal allocates GPU per @app.cls(gpu="A10G").
  - No ZeroGPU compatibility shims — CUDA is available from container startup
    on Modal, not deferred. The caching_allocator_warmup patch and the
    bitsandbytes exclusion from hf_space/ are both unnecessary here.
  - Models loaded from a persistent Modal Volume (/models/) rather than
    downloaded from HF Hub on every cold start. This reduces cold-start
    latency from ~90-120s (HF Hub download) to ~30-60s (Volume read).
  - device_map="cuda" replaces device_map="auto". The ZeroGPU-specific
    reason for "auto" (it routes through accelerate's safetensors loader
    patched by ZeroGPU) does not apply on Modal.

Pipeline flow (identical to hf_space/app.py):
  User message
      │
      ▼
  ADP-B (Gemma-2 + adp_b adapter)  → crisis check          (SPEC-300)
      │
      ▼
  ADP-A (Qwen3-4B base)            → empathetic response draft  (SPEC-200)
      │
      ▼
  ADP-C (Gemma-2 + adp_c adapter)  → evaluate draft; approve or regen  (SPEC-500)
      │
      ▼
  Render backend receives result; streams SSE to frontend

Volume layout (nikko-models):
  /models/qwen/       ← Qwen3-4B weights (ADP-A base)
  /models/gemma/      ← Gemma-2-2b-it weights (ADP-B/C base)
  /models/adapters/   ← Full adapter repo snapshot (contains adp-b/ and adp-c/ subfolders)

Required Modal secrets:
  modal secret create huggingface HF_TOKEN=<your-hf-read-token>
  modal secret create nikko-config HF_ADAPTER_REPO=<your-adapter-repo-id> NIKKO_INTERNAL_TOKEN=<shared-secret>

Deploy:
  modal deploy nikko_modal/app.py

The deployed endpoint URLs are output by Modal after deploy. Copy the /pipeline
URL and set it as the MODAL_URL environment variable on Render, then update the
keep-warm cron in .github/workflows/keep-warm.yml.
"""

import json
import logging
import os
import time

import modal
from fastapi.responses import JSONResponse

# ── Modal app + persistent Volume ────────────────────────────────────────────

app = modal.App("nikko-pipeline")

# [CONCEPT] A Modal Volume is a persistent filesystem that survives container
# restarts and is shared across all containers in the same app. Writing model
# weights here at image-build time (via image.run_function) means subsequent
# cold starts read from the Volume instead of downloading from HF Hub.
# First build: ~90s.  Subsequent cold starts: ~30-60s.
volume = modal.Volume.from_name("nikko-models", create_if_missing=True)

# ── Model / adapter configuration ────────────────────────────────────────────

# Must match hf_space/app.py exactly — adapters were trained against these bases.
QWEN_MODEL_ID  = "Qwen/Qwen3-4B"
GEMMA_MODEL_ID = "google/gemma-2-2b-it"

# Generation params — copied verbatim from hf_space/app.py.
# Changing these would alter model behaviour relative to the HF Space fallback.
ADAPTER_GEN_PARAMS = {
    "adp_a": dict(max_new_tokens=512, temperature=0.75, top_p=0.92, repetition_penalty=1.1, do_sample=True),
    "adp_b": dict(max_new_tokens=128, temperature=0.2,  top_p=0.9,  repetition_penalty=1.0, do_sample=False),
    "adp_c": dict(max_new_tokens=256, temperature=0.2,  top_p=0.9,  repetition_penalty=1.0, do_sample=False),
}

VALID_ADAPTERS = frozenset(ADAPTER_GEN_PARAMS.keys())

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("nikko-modal")


# ── Image definition + build-time model download ─────────────────────────────

def _download_models():
    """
    Downloads all model weights and adapter files into the persistent Volume.

    [CONCEPT] In Modal 1.x, @modal.build() was removed. Build-time setup is
    done by passing a function to image.run_function() during image construction.
    This function runs ONCE when the image is first built — subsequent deploys
    and cold starts reuse the cached Volume contents, skipping the download.

    Port of the download phase in hf_space/app.py _load_all_models().
    snapshot_download() writes to the Volume (/models/) so weights persist
    across container restarts.
    """
    import logging
    import os
    from huggingface_hub import snapshot_download

    _log = logging.getLogger("nikko-modal-build")
    logging.basicConfig(level=logging.INFO)

    _log.info("Downloading Qwen3-4B (ADP-A base)...")
    snapshot_download(
        "Qwen/Qwen3-4B",
        local_dir="/models/qwen",
        ignore_patterns=["*.msgpack", "flax_model*", "tf_model*"],
    )

    _log.info("Downloading Gemma-2-2b-it (ADP-B/C base)...")
    snapshot_download(
        "google/gemma-2-2b-it",
        local_dir="/models/gemma",
        ignore_patterns=["*.msgpack", "flax_model*", "tf_model*"],
    )

    adapter_repo = os.getenv("HF_ADAPTER_REPO", "")
    if not adapter_repo:
        raise RuntimeError(
            "HF_ADAPTER_REPO not set. "
            "Add it via: modal secret create nikko-config HF_ADAPTER_REPO=<repo>"
        )

    # [CONCEPT] We download the entire adapter repo into /models/adapters/.
    # The repo contains subfolders adp-b/ and adp-c/, each with
    # adapter_config.json and adapter_model.safetensors.
    # PeftModel.from_pretrained and load_adapter() then receive the subfolder
    # paths directly: /models/adapters/adp-b/ and /models/adapters/adp-c/.
    _log.info(f"Downloading adapter repo: {adapter_repo}...")
    snapshot_download(adapter_repo, local_dir="/models/adapters")

    # Commit so weights are visible to subsequent containers reading the Volume.
    import modal as _modal
    _modal.Volume.from_name("nikko-models").commit()
    _log.info("Model download complete — weights committed to Volume.")


# [CONCEPT] modal.Image defines the container environment for remote functions.
# .pip_install() adds Python packages. .run_function() executes a Python
# function at image-build time (once, not per request), with access to secrets
# and volumes — used here to pre-populate the persistent model Volume.
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "torch",
        "transformers>=4.46.3",
        "accelerate>=1.1.0",
        "peft>=0.13.2",
        "huggingface_hub",
        "sentencepiece>=0.2.0",
        "protobuf>=3.20.0",
        "fastapi[standard]",
    )
    .run_function(
        _download_models,
        volumes={"/models": volume},
        secrets=[
            modal.Secret.from_name("huggingface"),   # HF_TOKEN
            modal.Secret.from_name("nikko-config"),  # HF_ADAPTER_REPO
        ],
    )
)


# ── GPU inference class ───────────────────────────────────────────────────────

@app.cls(
    gpu="A10G",
    image=image,
    volumes={"/models": volume},
    timeout=360,
    secrets=[
        modal.Secret.from_name("huggingface"),   # HF_TOKEN
        modal.Secret.from_name("nikko-config"),  # HF_ADAPTER_REPO, NIKKO_INTERNAL_TOKEN
    ],
)
class NikkoInference:
    """
    GPU-resident inference class. Lifecycle (Modal 1.x):
      image.run_function(_download_models) → runs once at image build time
      @modal.enter()  → runs once per container cold start (model load to VRAM)
      @modal.method() → called per inference request (pipeline execution)
    """

    @modal.enter()
    def load_models(self):
        """
        Loads both base models and both Gemma adapters from the Volume into VRAM.
        Runs once per container cold start (not per request).

        Port of the load phase in hf_space/app.py _load_all_models().
        Key difference: device_map="cuda" replaces "auto" because Modal provides
        CUDA at container startup — the ZeroGPU-specific reason for "auto" does
        not apply here. Models load from /models/ (Volume) instead of HF Hub.
        """
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer

        # ── Qwen3-4B (ADP-A — base, no LoRA for MVP) ─────────────────────────
        # [CONCEPT] Qwen3-4B is the production ADP-A model. It runs as a plain
        # AutoModelForCausalLM (no PeftModel wrapper) because ADP-A fine-tuning
        # was discontinued (RTX 3070 VRAM constraint). The base model already
        # produces empathetic, contextually warm responses at this parameter count.
        log.info("Loading Qwen3-4B tokenizer from Volume...")
        self._qwen_tokenizer = AutoTokenizer.from_pretrained("/models/qwen")
        if self._qwen_tokenizer.pad_token is None:
            self._qwen_tokenizer.pad_token = self._qwen_tokenizer.eos_token

        log.info("Loading Qwen3-4B base model (bf16)...")
        self._qwen_model = AutoModelForCausalLM.from_pretrained(
            "/models/qwen",
            torch_dtype=torch.bfloat16,
            # device_map="cuda": Modal CUDA is available from startup.
            # Unlike ZeroGPU (which defers CUDA allocation), Modal initialises
            # the GPU context before the container's Python process starts.
            device_map="cuda",
        )
        self._qwen_model.eval()
        log.info("Qwen3-4B (ADP-A) loaded.")

        # ── Gemma-2-2b-it (ADP-B + ADP-C shared base) ────────────────────────
        # [CONCEPT] Both ADP-B and ADP-C share a single PeftModel wrapping
        # Gemma-2-2b-it. load_adapter() attaches both LoRA delta tensors at
        # startup; set_adapter() selects between them per inference call at
        # O(1) cost (pointer swap, no weight copy). See hf_space/app.py for
        # a fuller explanation of this pattern.
        log.info("Loading Gemma-2-2b-it tokenizer from Volume...")
        self._gemma_tokenizer = AutoTokenizer.from_pretrained("/models/gemma")
        if self._gemma_tokenizer.pad_token is None:
            self._gemma_tokenizer.pad_token = self._gemma_tokenizer.eos_token

        log.info("Loading Gemma-2-2b-it base model (bf16)...")
        gemma_base = AutoModelForCausalLM.from_pretrained(
            "/models/gemma",
            torch_dtype=torch.bfloat16,
            device_map="cuda",
            trust_remote_code=False,
        )

        log.info("Loading ADP-B adapter from Volume...")
        self._gemma_model = PeftModel.from_pretrained(
            gemma_base,
            "/models/adapters/adp-b",
            adapter_name="adp_b",
            is_trainable=False,
        )

        log.info("Loading ADP-C adapter from Volume...")
        self._gemma_model.load_adapter(
            "/models/adapters/adp-c",
            adapter_name="adp_c",
        )

        self._gemma_model.eval()
        log.info("All models and adapters loaded — container ready.")

    # ── Prompt builders ───────────────────────────────────────────────────────
    # Ported verbatim from hf_space/app.py. Do not diverge — identical prompts
    # ensure consistent model behaviour between Modal (primary) and HF Space (fallback).

    def _build_qwen_prompt(self, messages: list[dict], system: str = "") -> str:
        """
        Applies Qwen3-4B's chat template. enable_thinking=False suppresses the
        internal <think> reasoning scratchpad — saves ~100 tokens per turn.
        See hf_space/app.py _build_qwen_prompt() for full explanation.
        """
        chat = list(messages)
        if system:
            chat = [{"role": "system", "content": system}] + chat
        return self._qwen_tokenizer.apply_chat_template(
            chat,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False,
        )

    def _build_gemma_prompt(self, messages: list[dict], system: str = "") -> str:
        """
        Applies Gemma-2's chat template. Gemma-2 does not support a system role —
        system content is prepended to the first user turn instead.
        See hf_space/app.py _build_gemma_prompt() for full explanation.
        """
        chat = list(messages)
        if system:
            prepended = False
            chat = []
            for msg in messages:
                if msg["role"] == "user" and not prepended:
                    chat.append({"role": "user", "content": f"{system}\n\n{msg['content']}"})
                    prepended = True
                else:
                    chat.append(msg)
            if not prepended:
                chat = [{"role": "user", "content": system}] + chat
        return self._gemma_tokenizer.apply_chat_template(
            chat,
            tokenize=False,
            add_generation_prompt=True,
        )

    # ── Core inference helper ─────────────────────────────────────────────────

    def _infer_raw(self, messages: list[dict], system: str, adapter: str) -> str:
        """
        Runs one generation pass. Routes to the correct model based on adapter:
          adp_a → Qwen3-4B base (_qwen_model / _qwen_tokenizer)
          adp_b → Gemma-2-2b-it with adp_b LoRA active
          adp_c → Gemma-2-2b-it with adp_c LoRA active (hot-swapped via set_adapter)

        Ported verbatim from hf_space/app.py _infer_raw(). Must stay in sync.
        """
        import torch

        params = ADAPTER_GEN_PARAMS[adapter]

        if adapter == "adp_a":
            prompt = self._build_qwen_prompt(messages, system=system)
            inputs = self._qwen_tokenizer(
                prompt, return_tensors="pt", truncation=True, max_length=2048
            ).to(self._qwen_model.device)
            with torch.no_grad():
                output_ids = self._qwen_model.generate(
                    **inputs, **params, pad_token_id=self._qwen_tokenizer.eos_token_id
                )
            new_ids = output_ids[0][inputs["input_ids"].shape[1]:]
            return self._qwen_tokenizer.decode(new_ids, skip_special_tokens=True).strip()

        else:
            # [CONCEPT] set_adapter() is O(1) — it flips which LoRA delta tensors
            # are active in the PeftModel without copying any weight matrices.
            self._gemma_model.set_adapter(adapter)
            prompt = self._build_gemma_prompt(messages, system=system)
            inputs = self._gemma_tokenizer(
                prompt, return_tensors="pt", truncation=True, max_length=2048
            ).to(self._gemma_model.device)
            with torch.no_grad():
                output_ids = self._gemma_model.generate(
                    **inputs, **params, pad_token_id=self._gemma_tokenizer.eos_token_id
                )
            new_ids = output_ids[0][inputs["input_ids"].shape[1]:]
            return self._gemma_tokenizer.decode(new_ids, skip_special_tokens=True).strip()

    def _parse_json(self, raw: str) -> dict:
        """
        Extracts a JSON object from ADP-B / ADP-C output.
        Models occasionally wrap JSON in markdown code fences — strip them first.
        Ported verbatim from hf_space/app.py.
        """
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

    # ── Full pipeline ─────────────────────────────────────────────────────────

    @modal.method()
    def run_pipeline(
        self,
        messages:      list,
        system:        str,
        safety_system: str,
        eval_system:   str,
    ) -> dict:
        """
        Full ADP-B → ADP-A → ADP-C pipeline in a single GPU session.

        This is a direct port of hf_space/app.py _run_full_pipeline(). The logic,
        verdict normalisation map, and regen pass are identical. The response dict
        shape is also identical — backend/draft_generator.py consumes it unchanged.

        [CONCEPT] Unlike the HF Space (where @spaces.GPU allocates/releases the
        GPU per decorated function call), Modal keeps the GPU allocated for the
        lifetime of the container. All three adapter passes run without any
        CPU↔VRAM transfer overhead between them.
        """
        start = time.time()
        user_msg = messages[-1]["content"] if messages else ""

        # Stage 1: ADP-B safety classification (Gemma-2 + adp_b adapter)
        adp_b_raw = self._infer_raw(messages, safety_system, "adp_b")
        log.info(f"[adp_b] {len(adp_b_raw)} chars: {adp_b_raw[:120]}")
        safety    = self._parse_json(adp_b_raw)
        is_crisis = bool(safety.get("crisis", False))
        flags     = safety.get("flags", [])

        if is_crisis:
            return {
                "text": "", "is_crisis": True, "flags": flags,
                "verdict": "CRISIS", "regen": False,
                "adp_b_raw": adp_b_raw, "adp_a_raw": "", "adp_c_raw": "",
                "elapsed": round(time.time() - start, 2),
            }

        # Stage 2: ADP-A empathy response draft (Qwen3-4B base)
        draft = self._infer_raw(messages, system, "adp_a")
        log.info(f"[adp_a] {len(draft)} chars")

        # Stage 3: ADP-C evaluation (Gemma-2 + adp_c adapter)
        eval_messages = [
            {"role": "user",      "content": f"User message: {user_msg}"},
            {"role": "assistant", "content": f"Proposed response: {draft}"},
        ]
        adp_c_raw = self._infer_raw(eval_messages, eval_system, "adp_c")
        log.info(f"[adp_c] {len(adp_c_raw)} chars | full: {adp_c_raw!r}")

        # [CONCEPT] Verdict normalisation — see hf_space/app.py for full rationale.
        # ADP-C may emit synonym labels ("pass", "fail") depending on training data
        # conventions; this map folds all known synonyms into canonical values.
        _VERDICT_NORM = {
            "approve":    "APPROVE",
            "pass":       "APPROVE",
            "ok":         "APPROVE",
            "good":       "APPROVE",
            "regenerate": "REGENERATE",
            "regen":      "REGENERATE",
            "retry":      "REGENERATE",
            "fail":       "REGENERATE",
            "reject":     "REGENERATE",
            "crisis":     "CRISIS",
        }
        raw_verdict = self._parse_json(adp_c_raw).get("verdict", "APPROVE")
        verdict     = _VERDICT_NORM.get(str(raw_verdict).lower(), "APPROVE")
        if verdict != raw_verdict:
            log.info(f"[adp_c] verdict normalised: {raw_verdict!r} → {verdict}")

        regen = False
        if verdict == "REGENERATE":
            regen = True
            regen_messages = messages + [
                {"role": "assistant", "content": draft},
                {"role": "user",      "content": "Please try a different, more empathetic approach."},
            ]
            draft2    = self._infer_raw(regen_messages, system, "adp_a")
            eval2_raw = self._infer_raw([
                {"role": "user",      "content": f"User message: {user_msg}"},
                {"role": "assistant", "content": f"Proposed response: {draft2}"},
            ], eval_system, "adp_c")
            raw_verdict2 = self._parse_json(eval2_raw).get("verdict", "APPROVE")
            verdict2     = _VERDICT_NORM.get(str(raw_verdict2).lower(), "APPROVE")
            log.info(f"[adp_c regen] raw={raw_verdict2!r} normalised={verdict2}")
            if verdict2 != "REGENERATE":
                draft     = draft2
                verdict   = verdict2
                adp_c_raw = eval2_raw

        return {
            "text":      draft,
            "is_crisis": False,
            "flags":     flags,
            "verdict":   verdict,
            "regen":     regen,
            "adp_b_raw": adp_b_raw,
            "adp_a_raw": draft,
            "adp_c_raw": adp_c_raw,
            "elapsed":   round(time.time() - start, 2),
        }


# ── Web endpoints ─────────────────────────────────────────────────────────────
# These are Modal web endpoints — each becomes a separate HTTPS URL.
# The /pipeline URL goes into MODAL_URL on Render.
# The /health URL goes into the keep-warm cron (.github/workflows/keep-warm.yml).

@app.function(
    image=image,
    secrets=[modal.Secret.from_name("nikko-config")],
)
@modal.fastapi_endpoint(method="POST", label="nikko-pipeline")
def pipeline(request: dict):
    """
    HTTP entry point for the full pipeline. Mirrors POST /pipeline in hf_space/app.py.
    Called by backend/draft_generator.py via the MODAL_URL environment variable.

    Request shape:  { messages, system, safety_system, eval_system, token }
    Response shape: { text, is_crisis, flags, verdict, regen, elapsed,
                      adp_b_raw, adp_a_raw, adp_c_raw }

    Token auth: NIKKO_INTERNAL_TOKEN shared between this endpoint and Render.
    Set via: modal secret create nikko-config NIKKO_INTERNAL_TOKEN=<value>
             Render Dashboard → Environment → NIKKO_INTERNAL_TOKEN=<same value>
    """
    internal_token = os.getenv("NIKKO_INTERNAL_TOKEN", "")
    if internal_token and request.get("token") != internal_token:
        return JSONResponse(status_code=403, content={"detail": "Forbidden"})
    if not request.get("messages"):
        return JSONResponse(status_code=422, content={"detail": "messages must not be empty"})

    result = NikkoInference().run_pipeline.remote(
        request["messages"],
        request.get("system", ""),
        request.get("safety_system", ""),
        request.get("eval_system", ""),
    )
    return JSONResponse(content=result)


@app.function(image=image)
@modal.fastapi_endpoint(method="GET", label="nikko-health")
def health():
    """
    CPU-only liveness probe.
    No GPU decorator — health pings from the keep-warm cron and Render /health
    do NOT allocate a GPU and do NOT consume Modal compute credits.
    """
    return {"status": "ok", "inference": "modal"}

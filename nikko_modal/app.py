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
    # Truncation fix 2026-05-21: raised adp_a from 512 → 1024.
    # 512 was causing mid-sentence cuts on longer empathy responses.
    "adp_a": dict(max_new_tokens=1024, temperature=0.75, top_p=0.92, repetition_penalty=1.1, do_sample=True),
    "adp_b": dict(max_new_tokens=128,  temperature=0.2,  top_p=0.9,  repetition_penalty=1.0, do_sample=False),
    "adp_c": dict(max_new_tokens=256,  temperature=0.2,  top_p=0.9,  repetition_penalty=1.0, do_sample=False),
}

VALID_ADAPTERS = frozenset(ADAPTER_GEN_PARAMS.keys())

# Analysis gen params — Qwen3-4B only, intentionally short.
# These drive the pre-pipeline analysis preamble (scope / signal / strategy).
# Low temperature + do_sample=False enforces near-deterministic JSON output.
# Latency budget: scope ~2s, signal ~5s, strategy ~3s (warm container, A10G).
ANALYSIS_GEN_PARAMS = {
    "scope":    dict(max_new_tokens=64,  temperature=0.1,  do_sample=False),
    "signal":   dict(max_new_tokens=256, temperature=0.25, do_sample=False),
    "strategy": dict(max_new_tokens=128, temperature=0.25, do_sample=False),
}

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


# ── LLM analysis system prompts ──────────────────────────────────────────────
# All three prompts run on the already-loaded Qwen3-4B model within the same
# GPU session as ADP-A. They are intentionally terse — the rule engine provides
# the safety backbone; the LLM adds nuance on top, never replacing hard anchors.

# Scope: only called for AMBIGUOUS cases. Deterministic classifier handles clear
# IN_SCOPE / OUT_OF_SCOPE without Modal. (REQ-200-SC3: asymmetric error policy —
# ambiguous passes through rather than being silently dropped.)
_SCOPE_SYSTEM = (
    "You are a scope classifier for Nikko, a mental health support chatbot. "
    "Nikko handles: emotional wellbeing, mental health, relationships, stress, grief, "
    "anxiety, depression, loneliness, and personal struggles. "
    "Nikko does NOT handle: coding/programming, factual trivia, homework, math, recipes, "
    "or general knowledge questions unrelated to wellbeing. "
    "A rule engine flagged this message as AMBIGUOUS. Make the final call. "
    'Output ONLY: {"in_scope": true/false, "rationale": "one sentence"}'
)

# Signal: adds tone_note (emotional register the regex cannot express) and optionally
# nudges distress_level UP. LLM can NEVER downgrade a CRISIS ruling — that anchor is
# set by the rule engine before this prompt runs and is not exposed here.
_SIGNAL_SYSTEM = (
    "You are a signal analyst for Nikko, a mental health support chatbot. "
    "A rule engine has already extracted distress signals. "
    "Your role: add a tone_note capturing the emotional register the rule engine cannot express. "
    "Optionally nudge distress_level UP only if clearly underestimated — never downgrade. "
    "Output ONLY JSON:\n"
    '{"tone_note": "one sentence", '
    '"distress_nudge": "low"|"moderate"|"high"|"crisis"|null, '
    '"confidence_adjustment": <float -0.05 to +0.10>}'
)

# Strategy: refines the base tone/framing assigned by the deterministic strategy table
# using the signal analysis tone_note. Additive — never overrides mode or distress_level.
_STRATEGY_SYSTEM = (
    "You are a response strategy advisor for Nikko, a mental health support chatbot. "
    "A rule engine has assigned a base tone and framing strategy. "
    "Refine it based on the user's specific emotional register from the signal analysis. "
    "Output ONLY JSON:\n"
    '{"tone_refinement": "one sentence refining the base tone", '
    '"framing_note": "one sentence on specific framing approach"}'
)


# ── GPU inference class ───────────────────────────────────────────────────────

@app.cls(
    gpu="A10G",
    image=image,
    volumes={"/models": volume},
    timeout=360,
    # [CONCEPT] scaledown_window: how many seconds Modal waits after a container
    # becomes idle before terminating it. Default on the free tier is ~300s (5 min).
    # Setting 600 (10 min) keeps the container alive through a gap between requests
    # (e.g. a user typing their next message), avoiding a cold-start 429 when the
    # next request arrives while a new container is still loading models.
    # Cost impact: idle containers do NOT consume GPU credits — Modal only charges
    # for active GPU time, so a longer scaledown window is effectively free.
    scaledown_window=600,
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
            dtype=torch.bfloat16,
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
            dtype=torch.bfloat16,
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

    # ── Analysis helpers (Qwen3-4B, same GPU session as ADP-A) ──────────────

    def _infer_qwen_analysis(self, user_content: str, system: str, gen_params: dict) -> str:
        """
        Single-turn Qwen3-4B call for lightweight analysis passes.

        Uses the already-loaded _qwen_model and _qwen_tokenizer — no additional
        VRAM or cold-start cost. max_length=1024 keeps the context window short;
        analysis prompts are simple enough not to need the full 2048 budget.

        [CONCEPT] This is a convenience wrapper around _infer_raw's Qwen path.
        It exists as a separate method because analysis passes:
          (a) use a different gen_params dict (ANALYSIS_GEN_PARAMS, not ADAPTER_GEN_PARAMS)
          (b) are always single-turn (no chat history)
          (c) accept caller-supplied gen_params so each pass can tune tokens/temp
        """
        import torch

        messages = [{"role": "user", "content": user_content}]
        prompt   = self._build_qwen_prompt(messages, system=system)
        inputs   = self._qwen_tokenizer(
            prompt, return_tensors="pt", truncation=True, max_length=1024
        ).to(self._qwen_model.device)

        with torch.no_grad():
            output_ids = self._qwen_model.generate(
                **inputs,
                **gen_params,
                pad_token_id=self._qwen_tokenizer.eos_token_id,
            )
        new_ids = output_ids[0][inputs["input_ids"].shape[1]:]
        return self._qwen_tokenizer.decode(new_ids, skip_special_tokens=True).strip()

    def _analyze_scope(self, user_text: str) -> dict:
        """
        Resolves AMBIGUOUS scope classification via Qwen3-4B.

        Only called when scope_ambiguous=True from the Render backend. The
        deterministic ScopeClassifier handles clear IN_SCOPE and OUT_OF_SCOPE
        cases without Modal — this method only sees genuine edge cases.

        Returns: {"in_scope": bool, "rationale": str}

        Safety fallback: defaults to in_scope=True on any error.
        (REQ-200-SC3: safer to pass an ambiguous message through than to
        silently block a distress-coded user.)
        """
        try:
            raw    = self._infer_qwen_analysis(
                user_content=f'User message: "{user_text}"',
                system=_SCOPE_SYSTEM,
                gen_params=ANALYSIS_GEN_PARAMS["scope"],
            )
            result    = self._parse_json(raw)
            in_scope  = bool(result.get("in_scope", True))
            rationale = str(result.get("rationale", "LLM scope check"))
            log.info(f"[scope_llm] in_scope={in_scope} | {rationale}")
            return {"in_scope": in_scope, "rationale": rationale}
        except Exception as exc:
            log.warning(f"[scope_llm] failed ({exc}), defaulting to in_scope=True (REQ-200-SC3)")
            return {"in_scope": True, "rationale": f"fallback — error: {exc}"}

    def _analyze_signal(self, user_text: str, rule_signal: dict) -> dict:
        """
        Enriches deterministic signal output with Qwen3-4B tone analysis.

        rule_signal contains the rule engine's read of the message:
          distress_level, confidence, behavioral_indicators, support_needs.
        Note: risk_indicators are always empty here — active/acute risk
        already fired the CRISIS path before this method is ever called.

        The LLM may:
          - Add tone_note: emotional register the regex cannot capture
          - Nudge distress_level UP if clearly underestimated
          - Adjust confidence by a small float (clamped to [-0.05, +0.10])

        The LLM may NOT:
          - Downgrade distress_level
          - Override any risk indicator
          - Change mode or routing (Router is deterministic)

        Returns: {"tone_note": str, "distress_nudge": str|None, "confidence_adjustment": float}
        Falls back to no-op enrichment on error (pipeline continues unaffected).
        """
        try:
            context = (
                f"Rule engine signal: distress={rule_signal.get('distress_level', 'unknown')}, "
                f"confidence={rule_signal.get('confidence', 0.5):.2f}, "
                f"behavioral_indicators={rule_signal.get('behavioral_indicators', [])}, "
                f"support_needs={rule_signal.get('support_needs', [])}.\n"
                f'User message: "{user_text}"'
            )
            raw    = self._infer_qwen_analysis(
                user_content=context,
                system=_SIGNAL_SYSTEM,
                gen_params=ANALYSIS_GEN_PARAMS["signal"],
            )
            result = self._parse_json(raw)

            tone_note      = str(result.get("tone_note", ""))
            distress_nudge = result.get("distress_nudge")

            # Validate nudge — must be a canonical distress level or None.
            _VALID_LEVELS = {"low", "moderate", "high", "crisis"}
            if distress_nudge not in _VALID_LEVELS:
                distress_nudge = None

            # Clamp confidence adjustment to the allowed range.
            confidence_adj = float(result.get("confidence_adjustment", 0.0))
            confidence_adj = max(-0.05, min(0.10, confidence_adj))

            log.info(
                f"[signal_llm] tone='{tone_note[:60]}' "
                f"nudge={distress_nudge} conf_adj={confidence_adj:+.2f}"
            )
            return {
                "tone_note":             tone_note,
                "distress_nudge":        distress_nudge,
                "confidence_adjustment": confidence_adj,
            }
        except Exception as exc:
            log.warning(f"[signal_llm] failed ({exc}), returning no-op enrichment")
            return {"tone_note": "", "distress_nudge": None, "confidence_adjustment": 0.0}

    def _enrich_strategy(
        self,
        user_text:       str,
        enhanced_signal: dict,
        base_strategy:   str,
    ) -> dict:
        """
        Refines the base strategy tone/framing using Qwen3-4B.

        base_strategy is the RESPONSE GUIDANCE block already embedded in the
        ADP-A system prompt by backend/context_prompt_builder.py. Qwen reads
        the rule-engine strategy alongside the signal tone_note and produces a
        one-sentence refinement for each — additive, not replacement.

        Returns: {"tone_refinement": str, "framing_note": str}
        Falls back to no-op on error.
        """
        try:
            context = (
                f"Base strategy:\n{base_strategy}\n\n"
                f"Signal analysis tone: {enhanced_signal.get('tone_note', 'N/A')}\n"
                f'User message: "{user_text}"'
            )
            raw    = self._infer_qwen_analysis(
                user_content=context,
                system=_STRATEGY_SYSTEM,
                gen_params=ANALYSIS_GEN_PARAMS["strategy"],
            )
            result = self._parse_json(raw)
            return {
                "tone_refinement": str(result.get("tone_refinement", "")),
                "framing_note":    str(result.get("framing_note", "")),
            }
        except Exception as exc:
            log.warning(f"[strategy_llm] failed ({exc}), returning no-op enrichment")
            return {"tone_refinement": "", "framing_note": ""}

    @staticmethod
    def _inject_enhanced_strategy(system: str, enriched: dict) -> str:
        """
        Appends LLM strategy enrichment to the ADP-A system prompt.

        Does NOT replace the deterministic RESPONSE GUIDANCE block — it appends
        after it. The rule-engine baseline is always visible to ADP-A; the LLM
        refinement is additive context, not a substitution.

        Returns the original system prompt unchanged if enrichment is empty.
        """
        tone    = enriched.get("tone_refinement", "").strip()
        framing = enriched.get("framing_note", "").strip()
        if not tone and not framing:
            return system

        addendum = "\nSTRATEGY ENRICHMENT (LLM):"
        if tone:
            addendum += f"\n  Tone refinement: {tone}"
        if framing:
            addendum += f"\n  Framing note: {framing}"
        return system + addendum

    # ── Full pipeline ─────────────────────────────────────────────────────────

    @modal.method()
    def run_pipeline(
        self,
        messages:           list,
        system:             str,
        safety_system:      str,
        eval_system:        str,
        user_text:          str        = "",
        run_analysis:       bool       = True,
        scope_ambiguous:    bool       = False,
        rule_signal:        dict | None = None,
        base_strategy_text: str        = "",
    ) -> dict:
        """
        Full ADP-B → ADP-A → ADP-C pipeline in a single GPU session.

        New optional params (backward-compatible — all default to no-op):
          user_text          : Raw user text for analysis passes. Falls back to
                               messages[-1]["content"] if empty.
          run_analysis       : Set False to skip all LLM analysis passes (e.g.
                               NIKKO_LOCAL_LLM=false on Render routes directly
                               to the rule engine and never calls Modal, but
                               this flag provides an in-Modal override if needed).
          scope_ambiguous    : True when the ScopeClassifier returned AMBIGUOUS.
                               Triggers Pass 0a (Qwen3-4B scope resolution).
          rule_signal        : Deterministic SignalAgent output (lightweight dict:
                               distress_level, confidence, behavioral_indicators,
                               support_needs). Used by Pass 0b signal enrichment.
          base_strategy_text : The RESPONSE GUIDANCE block from the ADP-A system
                               prompt. Used by Pass 0c strategy enrichment.

        Original behaviour (ADP-B → ADP-A → ADP-C) is unchanged and identical
        to hf_space/app.py _run_full_pipeline(). All analysis output is additive.

        [CONCEPT] Unlike the HF Space (where @spaces.GPU allocates/releases the
        GPU per decorated function call), Modal keeps the GPU allocated for the
        lifetime of the container. All three adapter passes run without any
        CPU↔VRAM transfer overhead between them.
        """
        start    = time.time()
        user_msg = messages[-1]["content"] if messages else ""

        # Use explicit user_text if provided; fall back to the last message.
        _user_text = user_text.strip() or user_msg

        # Track analysis outputs — reported in the response trace dict.
        scope_verdict:     str  | None = None
        enhanced_signal:   dict | None = None
        enhanced_strategy: dict | None = None

        # ── Analysis preamble (Qwen3-4B, zero extra cold-start cost) ──────────
        # Passes 0a/0b/0c run before Stage 1 (ADP-B). Each pass is wrapped in
        # try/except — any failure is logged and skipped without aborting the
        # pipeline. The ADP-B → ADP-A → ADP-C flow is always the safety net.
        if run_analysis and _user_text:

            # Pass 0a: Scope resolution — AMBIGUOUS cases only.
            # The Render-side ScopeClassifier already rejected clear OUT_OF_SCOPE.
            # This pass makes the final call for genuine edge cases.
            if scope_ambiguous:
                scope_result  = self._analyze_scope(_user_text)
                scope_verdict = "IN_SCOPE" if scope_result["in_scope"] else "OUT_OF_SCOPE"
                if not scope_result["in_scope"]:
                    log.info(
                        f"[scope_llm] AMBIGUOUS → OUT_OF_SCOPE: {scope_result['rationale']}"
                    )
                    return {
                        "text": "", "is_crisis": False, "flags": [],
                        "verdict": "OUT_OF_SCOPE", "regen": False,
                        "adp_b_raw": "", "adp_a_raw": "", "adp_c_raw": "",
                        "scope_verdict": scope_verdict,
                        "enhanced_signal": None, "enhanced_strategy": None,
                        "elapsed": round(time.time() - start, 2),
                    }

            # Pass 0b: Signal enrichment.
            # rule_signal carries the deterministic baseline.  Risk indicators
            # are never present in rule_signal here — active/acute risk has
            # already been handled by the Router (CRISIS path) before Modal
            # is ever called.
            if rule_signal:
                enhanced_signal = self._analyze_signal(_user_text, rule_signal)

            # Pass 0c: Strategy enrichment.
            # Injects a tone refinement + framing note into the ADP-A system
            # prompt, appended after the deterministic RESPONSE GUIDANCE block.
            if enhanced_signal and base_strategy_text:
                enhanced_strategy = self._enrich_strategy(
                    _user_text, enhanced_signal, base_strategy_text
                )
                system = self._inject_enhanced_strategy(system, enhanced_strategy)

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
                "scope_verdict": scope_verdict,
                "enhanced_signal": enhanced_signal,
                "enhanced_strategy": enhanced_strategy,
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
            "text":               draft,
            "is_crisis":          False,
            "flags":              flags,
            "verdict":            verdict,
            "regen":              regen,
            "adp_b_raw":          adp_b_raw,
            "adp_a_raw":          draft,
            "adp_c_raw":          adp_c_raw,
            "scope_verdict":      scope_verdict,
            "enhanced_signal":    enhanced_signal,
            "enhanced_strategy":  enhanced_strategy,
            "elapsed":            round(time.time() - start, 2),
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
        # Analysis params — all optional, default to no-op if absent.
        # Render backend populates these when NIKKO_LOCAL_LLM=true.
        request.get("user_text", ""),
        request.get("run_analysis", True),
        request.get("scope_ambiguous", False),
        request.get("rule_signal") or None,
        request.get("base_strategy_text", ""),
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

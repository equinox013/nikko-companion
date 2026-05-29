"""
nikko_modal/app.py -- Nikko Modal Serverless inference endpoint (Phase 7 production).

This is the primary inference layer, replacing HF Spaces ZeroGPU as the
production target. hf_space/app.py is retained as a fallback (see Change 5
in the infrastructure spec and backend/draft_generator.py).

Model stack (identical to hf_space/app.py):
  Qwen3-4B       (base + ADP-A LoRA, equinox013/nikko-adp-a) = ADP-A (empathy response)
  Gemma-2-2b-it  (base)                                      = ADP-B + ADP-C (adapter hot-swap)

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

Pipeline flow (Director-approved reorder 2026-05-22):
  User message
      │
      ▼
  Pass 0   (Qwen3-4B)               → moderation + scope check
      │
      ▼
  Step 1.5 (Qwen3-4B, thinking mode) → structural pre-analysis  (SPEC-100 §16)
      │
      ▼
  ADP-A    (Qwen3-4B base)           → empathetic response draft  (SPEC-200)
      │
      ▼
  ADP-B    (Gemma-2 + adp_b adapter) → crisis check; annotations injected  (SPEC-300)
      │
      ▼
  ADP-C    (Gemma-2 + adp_c adapter) → evaluate draft; approve or regen  (SPEC-500)
      │
      ▼
  Render backend receives result; streams SSE to frontend

Volume layout (nikko-models):
  /models/qwen/            ← Qwen3-4B weights (ADP-A base)
  /models/gemma/           ← Gemma-2-2b-it weights (ADP-B/C base)
  /models/adapters/adp-b/  ← ADP-B LoRA adapter weights (equinox013/nikko-adp-b, Phase 4.1)
  /models/adapters/adp-c/  ← ADP-C LoRA adapter weights (equinox013/nikko-adp-c, Phase 4.1)
  /models/adapters/adp-a/  ← ADP-A LoRA adapter weights (equinox013/nikko-adp-a, Phase 4.1)

Required Modal secrets:
  modal secret create huggingface HF_TOKEN=<your-hf-read-token>
  modal secret create nikko-config NIKKO_INTERNAL_TOKEN=<shared-secret>
  # HF_ADAPTER_REPO is no longer required — adapter repos are hardcoded as
  # ADP_B_REPO and ADP_C_REPO constants (equinox013/nikko-adp-b, equinox013/nikko-adp-c).

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
from datetime import datetime, timezone

import modal
from fastapi.responses import JSONResponse

# ── Module-load timestamp ─────────────────────────────────────────────────────
# Captured once when the Modal container starts (cold start). Acts as a
# per-deployment version stamp: Render logs it on every /pipeline call, making
# it trivial to confirm which Modal deploy is serving a given request.
# Format: ISO-8601 UTC, e.g. "2026-05-23T14:32:10Z"
_MODAL_LOAD_TS = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

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

# ADP-A LoRA adapter — trained Phase 4.1 on Lightning.ai A10G (Step 21, rank-16 QLoRA).
# Standalone HF Hub public repo. Downloaded to /models/adapters/adp-a/ at image build.
ADP_A_REPO = "equinox013/nikko-adp-a"
# ADP-B and ADP-C Gemma-2 adapters — standalone HF Hub public repos.
# Downloaded to /models/adapters/adp-b/ and /models/adapters/adp-c/ at image build.
ADP_B_REPO = "equinox013/nikko-adp-b"
ADP_C_REPO = "equinox013/nikko-adp-c"

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
    # Combined moderation + scope pass — runs for every message that survives the
    # regex pre-gate on Render. Kept short (128 tokens) because the output is a
    # compact JSON object; longer output budgets are wasted here.
    "moderation_scope": dict(max_new_tokens=128, temperature=0.1,  do_sample=False),
    # [REQ-700-SA1] Step 1.5 structural pre-analysis pass.
    # enable_thinking=False (Director-approved 2026-05-23): CoT thinking mode was
    # causing Qwen3-4B to hedge on obvious signals and return empty annotations.
    # Direct pattern-matching with thinking disabled is faster and more accurate
    # for this task. Token budget stays at 256 — no <think> scratchpad overhead,
    # and a full annotation set (all 14 tags) is well under 100 tokens.
    "structural_pre_analysis": dict(max_new_tokens=256, temperature=0.15, do_sample=False),
    # Legacy scope-only pass (was Pass 0a for AMBIGUOUS cases). Retained for
    # reference; its logic is now absorbed into the moderation_scope pass above.
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

    # [CONCEPT] ADP-B and ADP-C are now individual HF Hub repos (not subfolders
    # of a combined repo). Each is downloaded directly into its Volume path so
    # PeftModel.from_pretrained and load_adapter() can reference them by local path.
    _log.info("Downloading ADP-B adapter (equinox013/nikko-adp-b)...")
    snapshot_download(
        "equinox013/nikko-adp-b",
        local_dir="/models/adapters/adp-b",
        ignore_patterns=["*.msgpack", "flax_model*", "tf_model*"],
    )

    _log.info("Downloading ADP-C adapter (equinox013/nikko-adp-c)...")
    snapshot_download(
        "equinox013/nikko-adp-c",
        local_dir="/models/adapters/adp-c",
        ignore_patterns=["*.msgpack", "flax_model*", "tf_model*"],
    )

    # ADP-A LoRA adapter — standalone public repo (separate from Gemma adapter repo).
    # Trained Phase 4.1 on Lightning.ai A10G (Step 21, Qwen3-4B QLoRA rank-16).
    # Downloaded into /models/adapters/adp-a/ so load_models() can reference it
    # by Volume path: PeftModel.from_pretrained(qwen_base, "/models/adapters/adp-a").
    _log.info("Downloading ADP-A LoRA adapter (equinox013/nikko-adp-a)...")
    snapshot_download(
        "equinox013/nikko-adp-a",
        local_dir="/models/adapters/adp-a",
        ignore_patterns=["*.msgpack", "flax_model*", "tf_model*"],
    )

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
            modal.Secret.from_name("huggingface"),   # HF_TOKEN (for private HF Hub access)
            # nikko-config removed — adapter repos are hardcoded, HF_ADAPTER_REPO no longer needed
        ],
    )
)


# ── LLM analysis system prompts ──────────────────────────────────────────────
# All three prompts run on the already-loaded Qwen3-4B model within the same
# GPU session as ADP-A. They are intentionally terse — the rule engine provides
# the safety backbone; the LLM adds nuance on top, never replacing hard anchors.

# ── Combined moderation + scope system prompt ────────────────────────────────
# Runs for EVERY message that survives the Render regex pre-gate.
# Two jobs in one Qwen call (already loaded, zero extra cold-start cost):
#
#   1. Catch coded hate that regex can't reach — antisemitism, Islamophobia,
#      white nationalism, veiled dehumanization. Hard slurs are already caught
#      by regex; this catches dog-whistles, coded language, and ideological framing.
#
#   2. Final scope check — catches OOS messages the regex classifier passed or
#      called AMBIGUOUS. scope_ambiguous=True is included as a hint so Qwen
#      weighs the scope decision more carefully when the rule engine was uncertain.
#
# Confidence gate: 0.80 threshold on both checks guards against false positives.
# Experiencing discrimination ("my coworker makes antisemitic jokes") is valid
# wellbeing input and must NOT be blocked — only advocacy/promotion is.
_MODERATION_SCOPE_SYSTEM = (
    "You are a safety and scope classifier for Nikko, a mental health wellbeing companion. "
    "Analyse the user message and output ONLY a JSON object with these keys:\n\n"
    '"harmful": true ONLY if the message advocates, promotes, or spreads:\n'
    "  - Coded antisemitism (e.g. 'globalists', '(((them)))', '14/88', 'ZOG', 'Jewish elites', 'Rothschilds control...')\n"
    "  - Coded Islamophobia (e.g. 'great replacement' targeting Muslims, 'Islam is a political ideology', "
    "'they are replacing us', 'Sharia takeover')\n"
    "  - White nationalist or ethno-nationalist ideology (e.g. 'replace us', 'white genocide', '14 words')\n"
    "  - Veiled dehumanization of demographic groups not caught by explicit slurs\n"
    "IMPORTANT: EXPERIENCING or DESCRIBING discrimination is NOT harmful — it is valid distress. "
    "'My coworker keeps making antisemitic jokes' is IN_SCOPE, not harmful.\n\n"
    '"harm_category": "antisemitism" | "islamophobia" | "white_nationalism" | "coded_hate" | "none"\n\n'
    '"in_scope": true if the message is about emotional wellbeing, mental health, relationships, '
    "personal struggles, grief, stress, loneliness, anxiety, or anything a wellbeing companion can help with. "
    "false ONLY if clearly about: physical symptoms/medical diagnosis, general knowledge (science, geography, "
    "history, maths), coding/tech help, finance, legal questions, or entertainment with no emotional component. "
    "When in doubt, default to true — a distressed person phrasing a message oddly must not be blocked. "
    "If the user mentions anything that could be related to their emotional state or relationships, lean in_scope=true.\n\n"
    '"oos_reason": brief phrase describing why, if in_scope=false, else ""\n\n'
    '"confidence": 0.0–1.0 confidence in your harmful=true or in_scope=false verdict. '
    "If confidence < 0.80, you MUST output harmful=false and in_scope=true regardless of your reading.\n\n"
    "Output ONLY the JSON object. No explanation, no preamble."
)

# Scope: only called for AMBIGUOUS cases. Deterministic classifier handles clear
# IN_SCOPE / OUT_OF_SCOPE without Modal. (REQ-200-SC3: asymmetric error policy —
# ambiguous passes through rather than being silently dropped.)
# NOTE: This prompt is retained as a standalone but its logic is now absorbed
# into _MODERATION_SCOPE_SYSTEM for the combined pass. Kept for reference.
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

# ── Structural Pre-Analysis system prompt (REQ-700-SA1 through SA7) ──────────
# Runs as Step 1.5: AFTER Pass 0 (moderation+scope) and BEFORE ADP-A.
# Uses Qwen3-4B in thinking mode to detect paralinguistic and typographic signals
# as defined in SPEC-100 §16. Output is a compact annotation block injected into
# ADP-B's context so the safety classifier can make a more informed verdict.
#
# Signal taxonomy (SPEC-100 §16, REQ-100-152 through REQ-100-161):
#   [PARA: tone_softener]       — "lol", "haha", "jk" after/alongside distress
#   [PARA: typographic_register]— rapid shift from formal to informal register
#   [STRUCT: register_collapse] — formal → single word → emoji degradation
#   [STRUCT: fragmented_syntax] — incomplete sentences, trailing ellipses under load
#   [STRUCT: all_caps_segment]  — isolated ALL CAPS in otherwise lowercase text
#   [PARA: minimisation]        — distress immediately followed by "it's fine", "nvm"
#   [PARA: mixed_affect]        — contradictory emotional signals in one message
#
# Encoding convention (Schema Option A — SPEC-100 §9, no new top-level field):
#   Signals are encoded as tagged strings in uncertainty_notes using
#   [STRUCT: tag] / [PARA: tag] prefixes. Machine-parseable by regex.
#   Backward-compatible: ADP-B ignores the note field if it cannot parse it.
#
# Output format: compact JSON with a single "annotations" string.
# NARROWED to semantic PARA signals only (Director-approved 2026-05-23).
# Previously covered 14 signals including all STRUCT signals and non-semantic PARA
# signals (expressive_lengthening, punctuation_urgency, keysmash, emoji_distress,
# asterisk_action). Those are now handled deterministically by
# backend/paralinguistic_detector.py on Render and passed in as struct_annotations.
#
# This prompt covers ONLY signals that require Qwen3-4B's language understanding:
#   [PARA: tone_softener]        — laughter token in the context of distress
#   [PARA: minimisation]         — distress walked back with dismissive language
#   [PARA: mixed_affect]         — contradictory emotions within one message
#   [PARA: typographic_register] — formal→informal register shift (NOT asterisk actions;
#                                  those are now [PARA: asterisk_action] via regex)
#   [STRUCT: fragmented_syntax]  — broken grammar / incomplete clauses
#   [STRUCT: register_collapse]  — structural degradation from sentences to fragments
#
# Example merged output: "[STRUCT: all_lowercase] [STRUCT: ellipsis_trail] [PARA: tone_softener]"
# (struct_annotations from Render + LLM PARA tags merged in _run_structural_pre_analysis)
_PRE_ANALYSIS_SYSTEM = (
    "You are a semantic paralinguistic signal detector for a mental health AI. "
    "Your role is to identify signals that require understanding of what the words "
    "MEAN in context — not surface patterns (those are handled separately). "
    "Output ONLY a JSON object with key 'annotations' containing a space-separated "
    "list of detected tags, or an empty string if none apply.\n\n"

    # ── Design principle ─────────────────────────────────────────────────────────
    # These signals require semantic judgment about what the words mean together.
    # Surface patterns (all-lowercase, repeated letters, emoji, punctuation runs)
    # are already detected by a separate regex engine and will be merged with your output.
    # DO NOT re-detect: all_lowercase, ellipsis_trail, all_caps_segment,
    # expressive_lengthening, punctuation_urgency, keysmash, emoji_distress, asterisk_action.
    # Focus only on the 6 signals below.
    # Source basis: McCulloch (2019), Al Tawil (2019), Wylie (2020),
    # Apriliani & Muslim (2021). See docs/paralinguistic_emotion_cues.md.

    "SIGNALS TO DETECT (semantic context required):\n\n"

    "[PARA: tone_softener] — A laughter token ('lol', 'haha', 'hehe', 'lmao', 'jk', "
    "'kidding', 'xD') appears IMMEDIATELY AFTER or within the SAME CLAUSE as a distress "
    "statement. The laughter is doing face-saving work — masking genuine distress, not "
    "expressing genuine amusement. Context is everything: 'I hate my life lol' → YES "
    "(laughter after distress). 'That movie was hilarious lol' → NO (genuine amusement). "
    "'I want to disappear haha' → YES. 'I'm fine haha' after stating something sad → YES.\n"

    "[PARA: minimisation] — A distress statement is immediately walked back or dismissed "
    "with language like: 'it's fine', 'nvm', 'never mind', 'doesn't matter', 'forget it', "
    "'not a big deal', 'ignore me', 'whatever', 'I'll be ok'. The person opened a door "
    "to distress and then closed it. The KEY is the PAIRING: distress expression followed "
    "by dismissal within the same message. "
    "Example: 'I've been really struggling lately, it's fine though' → YES. "
    "'Everything is terrible nvm forget I said anything' → YES. "
    "'I'm fine' alone → NO (no prior distress to minimise).\n"

    "[PARA: mixed_affect] — The message contains CONTRADICTORY emotional signals — "
    "the words pull in opposite directions within the same message. Not just ambivalence, "
    "but genuine contradiction. "
    "Example: 'I'm so happy but I keep crying and I don't know why' → YES. "
    "'Everything is fine I just feel completely empty' → YES. "
    "'I had a bad day but I know it'll get better' → NO (acknowledgment + hope is not contradiction).\n"

    "[PARA: typographic_register] — An ABRUPT SHIFT within the message from formal / "
    "complete sentences to very casual abbreviations, slang, fragmented speech, or "
    "single-word utterances. The shift signals the person running out of composed language "
    "mid-message. "
    "Example: 'I have been experiencing significant distress lately ... idk man whatever' → YES. "
    "'Things have been really difficult. I don't know. just. yeah.' → YES. "
    "A message that is casual throughout does NOT fire this tag — only an INTERNAL SHIFT does.\n"

    "[STRUCT: fragmented_syntax] — Sentences or thoughts stop mid-clause without "
    "resolution — broken grammar that reveals the person cannot complete the thought. "
    "DISTINCT from ellipsis trail (trailing dots): this is about broken sentence structure, "
    "not stylistic pauses. "
    "Example: 'I just feel like' (stops) → YES. 'I don't know I just' (stops) → YES. "
    "'h-hi there' (stutter) → YES. "
    "'I feel tired... and sad...' → NO (complete thought with ellipsis, not broken grammar).\n"

    "[STRUCT: register_collapse] — The message OPENS with structured full sentences "
    "and DEGRADES by the end to single words, fragments, or non-verbal sounds — "
    "structural deterioration as the person runs out of words or emotional energy. "
    "The collapse must be visible from start to end of the same message. "
    "Example: 'I've been trying so hard to hold everything together. Nothing is working. "
    "just. ugh. 😔' → YES. "
    "'I'm tired and sad' → NO (consistently short throughout, no collapse).\n\n"

    "RULES:\n"
    "1. These signals require understanding what the words MEAN together. "
    "If you cannot tell from the text alone, do NOT tag it.\n"
    "2. These signals indicate AROUSAL and MASKING patterns — not emotion labels.\n"
    "3. Multiple tags may fire. Output ALL that apply.\n"
    "4. Output ONLY the JSON object. No explanation. No preamble.\n"
    'Example: {"annotations": "[PARA: tone_softener] [PARA: minimisation]"}\n'
    'No signals: {"annotations": ""}'
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
        modal.Secret.from_name("nikko-config"),  # NIKKO_INTERNAL_TOKEN (shared secret with Render)
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

        # ── Qwen3-4B + ADP-A LoRA (equinox013/nikko-adp-a) ──────────────────
        # [CONCEPT] ADP-A LoRA adapter was trained in Phase 4.1 on Lightning.ai A10G
        # (Step 21, Qwen3-4B QLoRA, rank-16). PeftModel.from_pretrained wraps the
        # frozen base with LoRA delta tensors. generate() and tokenizer calls are
        # identical to a plain AutoModelForCausalLM — the wrapper is transparent.
        log.info("Loading Qwen3-4B tokenizer from Volume...")
        self._qwen_tokenizer = AutoTokenizer.from_pretrained("/models/qwen")
        if self._qwen_tokenizer.pad_token is None:
            self._qwen_tokenizer.pad_token = self._qwen_tokenizer.eos_token

        log.info("Loading Qwen3-4B base model (bf16)...")
        _qwen_base = AutoModelForCausalLM.from_pretrained(
            "/models/qwen",
            dtype=torch.bfloat16,
            # device_map="cuda": Modal CUDA is available from startup.
            # Unlike ZeroGPU (which defers CUDA allocation), Modal initialises
            # the GPU context before the container's Python process starts.
            device_map="cuda",
        )

        log.info("Attaching ADP-A LoRA adapter from Volume...")
        # [CONCEPT] is_trainable=False freezes all parameters — inference only.
        # set_adapter() is not needed here because Qwen carries only one adapter;
        # it is always active by default after from_pretrained.
        self._qwen_model = PeftModel.from_pretrained(
            _qwen_base,
            "/models/adapters/adp-a",
            adapter_name="adp_a",
            is_trainable=False,
        )
        self._qwen_model.eval()
        log.info("Qwen3-4B + ADP-A LoRA loaded.")

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

    def _build_qwen_prompt(self, messages: list[dict], system: str = "", enable_thinking: bool = False) -> str:
        """
        Applies Qwen3-4B's chat template.

        enable_thinking=False (default) suppresses the internal <think> reasoning
        scratchpad — saves ~100 tokens per turn for standard generation passes.
        enable_thinking=True activates chain-of-thought for analytical passes
        (e.g. Step 1.5 structural pre-analysis) where CoT improves accuracy.

        [CONCEPT] Qwen3-4B supports two generation modes controlled at template time:
          thinking=False → standard generation, no scratchpad
          thinking=True  → model emits <think>...</think> before its final answer;
                           the caller must strip the <think> block to get clean output.

        See hf_space/app.py _build_qwen_prompt() for full explanation. Kept in sync.
        """
        chat = list(messages)
        if system:
            chat = [{"role": "system", "content": system}] + chat
        return self._qwen_tokenizer.apply_chat_template(
            chat,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=enable_thinking,
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

    def _infer_raw(
        self,
        messages:        list[dict],
        system:          str,
        adapter:         str,
        params_override: dict | None = None,
    ) -> str:
        """
        Runs one generation pass. Routes to the correct model based on adapter:
          adp_a → Qwen3-4B base (_qwen_model / _qwen_tokenizer)
          adp_b → Gemma-2-2b-it with adp_b LoRA active
          adp_c → Gemma-2-2b-it with adp_c LoRA active (hot-swapped via set_adapter)

        params_override: optional dict merged on top of ADAPTER_GEN_PARAMS[adapter].
        Used by run_pipeline() to reduce ADP-A temperature on regen attempts
        without touching the baseline ADAPTER_GEN_PARAMS constant. (G-REGEN-01)

        Ported verbatim from hf_space/app.py _infer_raw(). Must stay in sync.
        """
        import torch

        params = {**ADAPTER_GEN_PARAMS[adapter], **(params_override or {})}

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

    def _infer_qwen_analysis(
        self, user_content: str, system: str, gen_params: dict, enable_thinking: bool = False
    ) -> str:
        """
        Single-turn Qwen3-4B call for lightweight analysis passes.

        Uses the already-loaded _qwen_model and _qwen_tokenizer — no additional
        VRAM or cold-start cost. max_length=1024 keeps the context window short;
        analysis prompts are simple enough not to need the full 2048 budget.

        enable_thinking=True activates Qwen3's chain-of-thought scratchpad for
        the Step 1.5 pre-analysis pass. The <think>...</think> block is stripped
        from the output before returning so callers always receive clean JSON.

        [CONCEPT] This is a convenience wrapper around _infer_raw's Qwen path.
        It exists as a separate method because analysis passes:
          (a) use a different gen_params dict (ANALYSIS_GEN_PARAMS, not ADAPTER_GEN_PARAMS)
          (b) are always single-turn (no chat history)
          (c) accept caller-supplied gen_params so each pass can tune tokens/temp
          (d) optionally activate thinking mode with automatic <think> stripping
        """
        import torch

        messages = [{"role": "user", "content": user_content}]
        prompt   = self._build_qwen_prompt(messages, system=system, enable_thinking=enable_thinking)
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
        raw = self._qwen_tokenizer.decode(new_ids, skip_special_tokens=True).strip()

        # [CONCEPT] When thinking mode is enabled, Qwen3 prepends a <think>...</think>
        # block containing its internal reasoning before the final answer. We strip it
        # here so all callers receive clean JSON output regardless of thinking mode.
        # split on </think> and take the trailing portion — the final answer always
        # follows the closing tag, even if the think block spans multiple lines.
        if enable_thinking and "<think>" in raw:
            parts = raw.split("</think>", 1)
            raw = parts[-1].strip() if len(parts) > 1 else raw

        return raw

    def _analyze_moderation_scope(
        self,
        user_text: str,
        scope_ambiguous: bool = False,
        prior_context: str = "",
    ) -> dict:
        """
        Combined LLM moderation + scope pass (runs for ALL non-regex-blocked messages).

        Unlike the legacy _analyze_scope() which only ran on AMBIGUOUS cases, this
        method runs for every message that survives the Render regex pre-gate. It
        performs two jobs in one Qwen3-4B call:

          1. Coded hate detection — antisemitism, Islamophobia, white nationalism,
             and veiled dehumanization that slur regex cannot catch.

          2. Final scope validation — edge-case OOS content the regex classifier
             passed or flagged as AMBIGUOUS.

        scope_ambiguous is forwarded as a hint in the user content so Qwen knows
        the rule engine was uncertain and should weigh the scope decision carefully.

        prior_context: the immediately preceding assistant turn (≤ 300 chars),
        included so the LLM can recognise short follow-up messages like
        "Let me try the deep breathing thing..." as in-scope continuations.

        Confidence gate: 0.80 threshold on both checks.
        Safety fallback: always returns no-block on any error (REQ-200-SC3).

        Returns:
            {
                "moderation_block": bool,
                "scope_block": bool,
                "harm_category": str,
                "oos_reason": str,
                "confidence": float,
            }
        """
        try:
            # Include the scope_ambiguous hint so Qwen weights scope more carefully
            # when the rule engine itself was uncertain.
            ambiguous_note = (
                " (Note: the rule-based scope classifier was AMBIGUOUS on this message — "
                "please apply extra care when deciding in_scope.)"
                if scope_ambiguous else ""
            )
            # Include prior assistant turn when available so the scope check has
            # enough context to judge short follow-up turns correctly.
            context_prefix = (
                f'Prior assistant turn (for context only): "{prior_context[:300]}"\n'
                if prior_context else ""
            )
            raw = self._infer_qwen_analysis(
                user_content=f'{context_prefix}User message: "{user_text}"{ambiguous_note}',
                system=_MODERATION_SCOPE_SYSTEM,
                gen_params=ANALYSIS_GEN_PARAMS["moderation_scope"],
            )
            result = self._parse_json(raw)

            confidence      = float(result.get("confidence", 0.0))
            # Both decisions are gated at 0.80 — below this, always pass through.
            harmful         = bool(result.get("harmful", False)) and confidence >= 0.80
            in_scope        = bool(result.get("in_scope", True))
            scope_blocked   = (not in_scope) and confidence >= 0.80

            harm_category = str(result.get("harm_category", "none")) if harmful else "none"
            oos_reason    = str(result.get("oos_reason", ""))        if scope_blocked else ""

            log.info(
                "[mod_scope_llm] harmful=%s cat=%s in_scope=%s oos=%r conf=%.2f",
                harmful, harm_category, in_scope, oos_reason[:60], confidence,
            )
            return {
                "moderation_block": harmful,
                "scope_block":      scope_blocked,
                "harm_category":    harm_category,
                "oos_reason":       oos_reason,
                "confidence":       confidence,
            }
        except Exception as exc:
            # On any LLM error, default to no-block.
            # REQ-200-SC3: asymmetric error policy — safer to pass through than
            # to silently block a distressed user due to an LLM failure.
            log.warning("[mod_scope_llm] failed (%s) — defaulting to no-block (REQ-200-SC3)", exc)
            return {
                "moderation_block": False,
                "scope_block":      False,
                "harm_category":    "none",
                "oos_reason":       "",
                "confidence":       0.0,
            }

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

    def _run_structural_pre_analysis(
        self, user_text: str, struct_annotations: str = ""
    ) -> dict:
        """
        Step 1.5: Hybrid structural pre-analysis pass (REQ-700-SA1 through SA7).

        SPLIT ARCHITECTURE (Director-approved 2026-05-23):
        ──────────────────────────────────────────────────
        Deterministic STRUCT + non-semantic PARA signals are now handled by
        `backend/paralinguistic_detector.py` on Render (regex/heuristic), passed
        in as `struct_annotations`. This function now handles ONLY the semantic
        PARA signals that genuinely require Qwen3-4B:

          Semantic PARA signals (LLM):
            [PARA: tone_softener]        — laughter AFTER distress (context-dependent)
            [PARA: minimisation]         — distress walked back ("it's fine")
            [PARA: mixed_affect]         — contradictory emotions
            [PARA: typographic_register] — formal→informal register shift
            [STRUCT: fragmented_syntax]  — broken grammar / incomplete clauses
            [STRUCT: register_collapse]  — degradation from sentences to fragments

        Deterministic signals (already in struct_annotations from Render):
            [STRUCT: all_lowercase]      [STRUCT: ellipsis_trail]
            [STRUCT: all_caps_segment]   [PARA: expressive_lengthening]
            [PARA: punctuation_urgency]  [PARA: keysmash]
            [PARA: emoji_distress]       [PARA: asterisk_action]

        WHY THINKING MODE IS OFF:
        enable_thinking=False (changed 2026-05-23): CoT was causing Qwen3-4B to
        reason itself out of firing even obvious signals. For the remaining semantic
        PARA signals, direct generation produces more reliable JSON output because
        the task is still pattern-matching (is this specific phenomenon present?)
        rather than nuanced multi-step reasoning.

        MERGE LOGIC:
        struct_annotations (Render, guaranteed) + LLM PARA tags are combined
        into a single annotation string. If the LLM pass fails, struct_annotations
        alone is returned — the asymmetric error policy ensures deterministic
        signals are never lost to an LLM failure.

        Returns:
            {"annotations": "<merged string>"} — may be empty if no signals found
            {"annotations": "", "error": "..."} — on LLM failure (struct tags preserved)
        """
        try:
            raw = self._infer_qwen_analysis(
                user_content=f'User message to analyse: "{user_text}"',
                system=_PRE_ANALYSIS_SYSTEM,
                gen_params=ANALYSIS_GEN_PARAMS["structural_pre_analysis"],
                enable_thinking=False,
            )
            result       = self._parse_json(raw)
            llm_para_raw = str(result.get("annotations", "")).strip()

            # Bracket normalization: Qwen3-4B occasionally drops the opening '['
            # (e.g. "PARA: mixed_affect" instead of "[PARA: mixed_affect]").
            # Normalize all tag-like patterns so downstream regex consumers
            # (ADP-B strength gate, frontend trace parser, Phase 6 harness) can
            # parse the merged annotation string reliably.
            if llm_para_raw:
                import re as _re2
                llm_para_raw = _re2.sub(
                    r'\[?((?:PARA|STRUCT):\s*[\w_]+)\]?',
                    r'[\1]',
                    llm_para_raw,
                )
            log.info("[pre_analysis/llm] para_annotations=%r", llm_para_raw or "(none)")
        except Exception as exc:
            log.warning(
                "[pre_analysis/llm] failed (%s) — will use struct_annotations only.", exc
            )
            llm_para_raw = ""

        # Merge: Render struct tags first, then LLM semantic PARA tags.
        # Preserves order: STRUCT signals before PARA signals in the ADP-B context.
        parts = [p for p in (struct_annotations.strip(), llm_para_raw) if p]
        merged = " ".join(parts)
        log.info("[pre_analysis/merged] annotations=%r", merged or "(none)")
        return {"annotations": merged}

    @staticmethod
    def _sentence_capitalize(text: str) -> str:
        """
        Post-process ADP-A draft to enforce standard English capitalisation.

        WHY THIS EXISTS:
        Qwen3-4B persistently mirrors the user's all-lowercase typing register,
        producing all-lowercase responses regardless of the TYPOGRAPHY RULE in the
        system prompt. Rather than fighting model priors with escalating instruction
        engineering, we enforce capitalisation deterministically here — zero latency
        cost, guaranteed compliance. (REQ-000-041, Director-approved 2026-05-23)

        RULES APPLIED:
        1. First character of the entire draft is capitalised.
        2. Any lowercase letter immediately following '. ', '! ', or '? ' (a sentence
           boundary) is capitalised.

        ELLIPSIS GUARD:
        '...' must not trigger capitalisation of the word that follows it, since
        trailing ellipsis signals hesitation or an unfinished thought — not a sentence
        end. Implemented via negative lookbehind (?<!\.) which excludes a '.' that is
        immediately preceded by another '.', matching only the last dot of '...' and
        preventing the capitalisation from firing.

        EM-DASH NOTE:
        '—' is not treated as a sentence boundary (it joins clauses, not sentences).
        No special handling needed.

        DOES NOT MODIFY:
        - Internal capitalisation (proper nouns, acronyms) — we only touch the first
          letter after a sentence boundary.
        - Whitespace — the original spacing between sentences is preserved.
        """
        import re

        if not text:
            return text

        # Rule 1: capitalise first character of the full draft.
        if text[0].islower():
            text = text[0].upper() + text[1:]

        # Rule 2: capitalise the first letter of each subsequent sentence.
        # Pattern breakdown:
        #   (?<!\.)  — negative lookbehind: previous char must NOT be '.'
        #              (guards against firing on the final dot of '...')
        #   ([.!?])  — capture the sentence-ending punctuation
        #   (\s+)    — capture the whitespace between sentences (preserve it)
        #   ([a-z])  — capture the lowercase letter to capitalise
        text = re.sub(
            r'(?<!\.)([.!?])(\s+)([a-z])',
            lambda m: m.group(1) + m.group(2) + m.group(3).upper(),
            text,
        )
        return text

    @staticmethod
    def _build_adp_b_system_with_context(base_system: str, annotations: str) -> str:
        """
        Inject pre-analysis annotations into the ADP-B safety system prompt.

        [REQ-700-SA5] ADP-B MUST receive the pre-analysis annotation block as
        additional context so the safety classifier can account for paralinguistic
        signals when determining crisis=true/false.

        When annotations is empty, returns base_system unchanged — no context
        injection occurs and ADP-B runs with its standard prompt.

        Why prepend rather than append?
        Gemma-2 is sensitive to context position — instructions near the start of
        the system block have higher weight in the model's attention. The annotations
        are signal-level context that should influence the crisis verdict, not a
        footnote. Prepending ensures ADP-B weights them appropriately.
        """
        if not annotations:
            return base_system

        # ── Signal-strength gate ──────────────────────────────────────────────
        # [REQ-700-SA6] Weak signals that fire in isolation should be treated as
        # background texture, not elevated distress indicators. This prevents the
        # safety model from over-reading stylistic choices (e.g. all-lowercase,
        # trailing ellipses) in messages that carry no distressed verbal content.
        #
        # WEAK  — ambiguous on their own; often stylistic / low-register writing.
        #         all_lowercase, ellipsis_trail, expressive_lengthening,
        #         punctuation_urgency, emoji_distress.
        # STRONG — high-signal indicators of arousal or masking behaviour.
        #         tone_softener, minimisation, mixed_affect, keysmash,
        #         all_caps_segment, register_collapse, typographic_register,
        #         fragmented_syntax.
        #
        # Logic: if exactly 1 signal fires AND it is in the WEAK set → prepend a
        # low-confidence caveat. 2+ signals or any STRONG signal → full weight.
        _WEAK_SIGNALS = {
            "all_lowercase",
            "ellipsis_trail",
            "expressive_lengthening",
            "punctuation_urgency",
            "emoji_distress",
        }
        # Extract tag names from the annotation string (format: "[PARA: foo]" / "[STRUCT: bar]")
        import re as _re
        detected_tags = _re.findall(r"\[(?:PARA|STRUCT):\s*(\w+)\]", annotations)
        is_weak_singleton = (
            len(detected_tags) == 1
            and detected_tags[0] in _WEAK_SIGNALS
        )

        if is_weak_singleton:
            strength_note = (
                "SIGNAL CONFIDENCE — LOW: Only a single weak-intensity signal was detected "
                f"({detected_tags[0]}). This signal is stylistically ambiguous and should be "
                "treated as background context, not an elevated distress indicator. "
                "Do not adjust your safety verdict based on this signal alone — rely on the "
                "verbal content of the message as primary evidence.\n\n"
            )
        else:
            strength_note = ""

        annotation_block = (
            f"{strength_note}"
            f"PARALINGUISTIC / STRUCTURAL SIGNALS DETECTED IN THIS MESSAGE:\n"
            f"{annotations}\n\n"
            "INTERPRETATION RULES FOR THESE SIGNALS:\n"
            "1. These signals indicate elevated AROUSAL and INTENSITY — not a specific "
            "emotion. The verbal content sets valence; these signals amplify it. "
            "A message that reads as mild distress in words but carries keysmash, "
            "expressive lengthening, or multiple ellipsis trails should be read as "
            "higher-intensity distress than the words alone suggest.\n"
            "2. Tone softeners ([PARA: tone_softener]) and minimisation ([PARA: minimisation]) "
            "do NOT make a distressed message safe — they indicate the user is actively "
            "downplaying their state. Weight the distress signal MORE, not less.\n"
            "3. These signals do NOT override explicit content rules: if the message "
            "contains no direct self-harm language, crisis MUST still be false regardless "
            "of how many paralinguistic signals are present.\n"
            "4. Multiple signals compound: two or more firing together on the same message "
            "is a stronger indicator of masked distress than a single signal alone.\n\n"
        )
        return annotation_block + base_system

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

    # Temperature schedule for ADP-A regen attempts. (G-REGEN-01)
    # Index = regen_attempt (0 = first/original pass; clamped at max index).
    # Temperature is applied on ALL passes including attempt=0 — starting at 0.50
    # rather than the model default (~0.70) reduces first-pass strategy generation.
    #
    # On the FINAL schedule entry, the ADP-A LoRA adapter is disabled and bare
    # Qwen3-4B runs instead. When the adapter keeps producing violations even at
    # low temperature, the base model + explicit constraint system prompt is a
    # cleaner last resort before safe fallback.
    #
    # Schedule:
    #   attempt=0 → 0.50  (LoRA active)
    #   attempt=1 → 0.25  (LoRA active)
    #   attempt=2 → 0.20  (LoRA DISABLED — base Qwen3-4B)
    _REGEN_TEMPERATURES: list[float] = [0.50, 0.25, 0.20]

    @modal.method()
    def run_pipeline(
        self,
        messages:            list,
        system:              str,
        safety_system:       str,
        eval_system:         str,
        user_text:           str        = "",
        run_analysis:        bool       = True,
        scope_ambiguous:     bool       = False,
        rule_signal:         dict | None = None,
        base_strategy_text:  str        = "",
        struct_annotations:  str        = "",
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

        Pipeline order (Director-approved 2026-05-22): Pass 0 (mod+scope) →
        Step 1.5 (pre-analysis, Qwen3 thinking mode) → ADP-A (Qwen3 draft) →
        ADP-B (Gemma safety, annotations injected) → ADP-C (Gemma evaluation).
        All analysis output is additive; safety guarantee is preserved since
        ADP-B still discards the draft when crisis=True.

        [CONCEPT] Unlike the HF Space (where @spaces.GPU allocates/releases the
        GPU per decorated function call), Modal keeps the GPU allocated for the
        lifetime of the container. All three adapter passes run without any
        CPU↔VRAM transfer overhead between them.
        """
        start    = time.time()
        user_msg = messages[-1]["content"] if messages else ""

        # [G-REGEN-01] Extract regen_attempt and pipeline mode piggybacked on rule_signal.
        # Using the rule_signal dict avoids adding new positional parameters to
        # run_pipeline() — which would break warm containers still running the old
        # signature during rolling deploys. Old containers ignore unknown keys;
        # new containers pop them here before any downstream rule_signal processing.
        regen_attempt = 0
        if rule_signal and "_regen_attempt" in rule_signal:
            regen_attempt = int(rule_signal.pop("_regen_attempt", 0))
        if rule_signal and "_mode" in rule_signal:
            rule_signal.pop("_mode", None)  # retired 2026-05-29 — was used to gate _strip_questions()

        # Use explicit user_text if provided; fall back to the last message.
        _user_text = user_text.strip() or user_msg

        # Track analysis outputs — reported in the response trace dict.
        scope_verdict:     str  | None = None
        enhanced_signal:   dict | None = None
        enhanced_strategy: dict | None = None
        pre_analysis_raw:  str         = ""   # Step 1.5 annotation string (may be empty)

        # ── Analysis preamble (Qwen3-4B, zero extra cold-start cost) ──────────
        # Analysis passes run before the adapter stages. Each is wrapped in try/except
        # — any failure is logged and skipped without aborting the pipeline.
        # The ADP-A → ADP-B → ADP-C flow is always the safety net.
        if run_analysis and _user_text:

            # ── Pass 0: Combined moderation + scope (runs for ALL messages) ───
            # Catches what the Render regex pre-gate cannot:
            #   - Coded antisemitism, Islamophobia, white nationalism
            #   - Edge-case OOS content the ScopeClassifier passed or called AMBIGUOUS
            # scope_ambiguous is forwarded as a hint so Qwen weights scope carefully
            # when the rule engine itself was uncertain (G-HYBRID-01 resolution).
            # prior_assistant provides the immediately preceding assistant turn so
            # short follow-up messages are recognised as in-scope continuations.
            prior_assistant = (
                messages[-2]["content"]
                if len(messages) >= 2 and messages[-2].get("role") == "assistant"
                else ""
            )
            mod_scope = self._analyze_moderation_scope(_user_text, scope_ambiguous, prior_assistant)

            if mod_scope["moderation_block"]:
                log.warning(
                    "[mod_scope_llm] MODERATION BLOCK — category=%s conf=%.2f",
                    mod_scope["harm_category"], mod_scope["confidence"],
                )
                return {
                    "text": "", "is_crisis": False, "flags": [],
                    "verdict": "BLOCKED", "regen": False,
                    "moderation_block": True, "scope_block": False,
                    "harm_category": mod_scope["harm_category"],
                    "adp_b_raw": "", "adp_a_raw": "", "adp_c_raw": "",
                    "scope_verdict": None, "pre_analysis_raw": "",
                    "enhanced_signal": None, "enhanced_strategy": None,
                    "elapsed": round(time.time() - start, 2),
                }

            if mod_scope["scope_block"]:
                log.info(
                    "[mod_scope_llm] SCOPE BLOCK — reason=%r conf=%.2f",
                    mod_scope["oos_reason"][:80], mod_scope["confidence"],
                )
                return {
                    "text": "", "is_crisis": False, "flags": [],
                    "verdict": "OUT_OF_SCOPE", "regen": False,
                    "moderation_block": False, "scope_block": True,
                    "oos_reason": mod_scope["oos_reason"],
                    "adp_b_raw": "", "adp_a_raw": "", "adp_c_raw": "",
                    "scope_verdict": "OUT_OF_SCOPE", "pre_analysis_raw": "",
                    "enhanced_signal": None, "enhanced_strategy": None,
                    "elapsed": round(time.time() - start, 2),
                }

            # ── Step 1.5: Structural pre-analysis (Qwen3-4B, thinking mode) ───
            # [REQ-700-SA1] Detect paralinguistic and structural signals (SPEC-100 §16)
            # BEFORE running the adapter stages. Annotations are injected into ADP-B's
            # context so the safety classifier sees masked/minimised distress cues.
            #
            # Split architecture (Director-approved 2026-05-23):
            #   struct_annotations  — pre-computed by Render's paralinguistic_detector.py
            #                         (regex/heuristic; guaranteed accuracy for STRUCT +
            #                          non-semantic PARA signals)
            #   LLM PARA pass       — Qwen3-4B detects semantic PARA signals only
            #                          (tone_softener, minimisation, mixed_affect,
            #                           typographic_register, fragmented_syntax,
            #                           register_collapse)
            # The two sets are merged here into the final pre_analysis_raw string.
            # Any failure in the LLM pass is silently skipped — struct_annotations
            # alone is still injected into ADP-B (asymmetric error policy).
            pre_result       = self._run_structural_pre_analysis(_user_text, struct_annotations)
            pre_analysis_raw = pre_result.get("annotations", "")

            # ── Pass 1: Signal enrichment ─────────────────────────────────────
            # rule_signal carries the deterministic baseline. Risk indicators
            # are never present here — active/acute risk fired the CRISIS path
            # on Render before Modal was ever called.
            if rule_signal:
                enhanced_signal = self._analyze_signal(_user_text, rule_signal)

            # ── Pass 2: Strategy enrichment ───────────────────────────────────
            # Appends a tone refinement + framing note to the ADP-A system prompt
            # after the deterministic RESPONSE GUIDANCE block (additive, not
            # replacement).
            if enhanced_signal and base_strategy_text:
                enhanced_strategy = self._enrich_strategy(
                    _user_text, enhanced_signal, base_strategy_text
                )
                system = self._inject_enhanced_strategy(system, enhanced_strategy)

        # ── Reordered pipeline: ADP-A → ADP-B → ADP-C ────────────────────────
        # [Director-approved 2026-05-22] New execution order groups both Qwen3
        # passes together (pre-analysis + ADP-A draft) before switching to Gemma
        # (ADP-B safety check + ADP-C evaluation). This minimises context-switch
        # overhead between the two model families.
        #
        # Safety is preserved: ADP-B still discards the draft on crisis=True.
        # The draft simply hasn't been delivered to the user yet when ADP-B fires;
        # the CRISIS return path exits early and delivers crisis resources instead.

        # Stage 1: ADP-A empathy response draft (Qwen3-4B base)
        # [CONCEPT] ADP-A now runs BEFORE ADP-B safety classification. The draft is
        # generated here but only returned to the caller if ADP-B approves it.
        # If ADP-B fires crisis=True, this draft is silently discarded.
        #
        # [G-REGEN-01] Temperature schedule — applied on ALL passes including attempt=0.
        # Starting at 0.50 (not the model default ~0.70) reduces first-pass strategy
        # generation. Each failed regen drops further (0.25, 0.20).
        _adp_a_temp = self._REGEN_TEMPERATURES[
            min(regen_attempt, len(self._REGEN_TEMPERATURES) - 1)
        ]
        # On the final schedule entry, disable the ADP-A LoRA adapter and run bare
        # Qwen3-4B. The adapter's training bias toward expressive outputs persists
        # at low temperature; the base model with an explicit constraint system prompt
        # is a cleaner last resort. disable_adapter() is the PEFT context manager —
        # O(1), no weight copy, thread-safe for single-GPU single-request containers.
        _use_base_model = regen_attempt >= len(self._REGEN_TEMPERATURES) - 1
        _adp_a_params   = {"temperature": _adp_a_temp}
        log.info(
            f"[adp_a] regen_attempt={regen_attempt} → temperature={_adp_a_temp}"
            + (" (LoRA disabled — base Qwen3-4B)" if _use_base_model else "")
        )
        if _use_base_model:
            with self._qwen_model.disable_adapter():
                draft = self._infer_raw(messages, system, "adp_a", params_override=_adp_a_params)
        else:
            draft = self._infer_raw(messages, system, "adp_a", params_override=_adp_a_params)
        # [REQ-000-041] Enforce standard English capitalisation on the draft.
        # Qwen3-4B mirrors the user's all-lowercase register despite the TYPOGRAPHY
        # RULE in the system prompt. _sentence_capitalize() applies deterministic
        # post-processing: capitalise sentence-initial characters without touching
        # internal casing, proper nouns, or whitespace. (Director-approved 2026-05-23)
        draft = self._sentence_capitalize(draft)
        log.info(f"[adp_a] {len(draft)} chars (capitalised)")

        # Stage 2: ADP-B safety classification (Gemma-2 + adp_b adapter)
        # Inject pre-analysis annotations into the safety system prompt so ADP-B
        # can account for paralinguistic signals (tone softeners, minimisation, etc.).
        adp_b_safety_system = self._build_adp_b_system_with_context(safety_system, pre_analysis_raw)
        adp_b_raw = self._infer_raw(messages, adp_b_safety_system, "adp_b")
        log.info(f"[adp_b] {len(adp_b_raw)} chars: {adp_b_raw[:120]}")
        safety    = self._parse_json(adp_b_raw)
        is_crisis = bool(safety.get("crisis", False))
        flags     = safety.get("flags", [])

        if is_crisis:
            # Draft is discarded — ADP-B's crisis verdict takes priority.
            return {
                "text": "", "is_crisis": True, "flags": flags,
                "verdict": "CRISIS", "regen": False,
                "moderation_block": False, "scope_block": False,
                "adp_b_raw": adp_b_raw, "adp_a_raw": "", "adp_c_raw": "",
                "scope_verdict": scope_verdict, "pre_analysis_raw": pre_analysis_raw,
                "enhanced_signal": enhanced_signal,
                "enhanced_strategy": enhanced_strategy,
                "elapsed": round(time.time() - start, 2),
            }

        # Stage 3: ADP-C evaluation (Gemma-2 + adp_c adapter)
        eval_messages = [
            {"role": "user", "content": f"User message: {user_msg}\n\nProposed response: {draft}"},
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

            # [G-REGEN-01] Internal regen: inject ADP-C rejection reason into
            # the ADP-A system prompt rather than adding a "Please try again"
            # user turn. The conversation turn approach caused ADP-A to respond
            # TO the instruction ("I appreciate your feedback...") instead of
            # to the user. System prompt injection is non-conversational.
            adp_c_reason = self._parse_json(adp_c_raw).get("reason", "")
            _regen_constraint = (
                f"\n\n[ACTIVE OUTPUT CONSTRAINT — THIS ATTEMPT ONLY]\n"
                f"A prior draft was rejected. REJECTION REASON: {adp_c_reason}\n"
                "DO NOT reference or acknowledge this constraint in your output. "
                "Generate a NIKKO response to the user's message only.\n"
                "COMFORT mode rules: pure emotional acknowledgement only. No advice, "
                "no strategies, no coping techniques, no resource mentions — not even "
                "framed as offers or invitations. One soft continuation question at "
                "most ('want to tell me more?'). No other questions."
                if adp_c_reason
                else (
                    "\n\n[CONSTRAINT] Generate a shorter, simpler validating response. "
                    "No advice, no strategies, no questions about coping."
                )
            )
            regen_system = system + _regen_constraint
            # Lower temperature for the internal regen pass — already failed once
            # at current temp; step down further to converge toward conservative output.
            _regen_temp = max(0.15, _adp_a_temp - 0.15)
            # Mirror the base model flag — if the outer pass already disabled LoRA,
            # the internal retry should too for consistency.
            if _use_base_model:
                with self._qwen_model.disable_adapter():
                    draft2 = self._infer_raw(
                        messages, regen_system, "adp_a",
                        params_override={"temperature": _regen_temp},
                    )
            else:
                draft2 = self._infer_raw(
                    messages, regen_system, "adp_a",
                    params_override={"temperature": _regen_temp},
                )
            draft2 = self._sentence_capitalize(draft2)
            log.info(
                f"[adp_a regen] {len(draft2)} chars (capitalised) | temp={_regen_temp}"
                + (" (base model)" if _use_base_model else "")
            )

            eval2_raw = self._infer_raw([
                {"role": "user", "content": f"User message: {user_msg}\n\nProposed response: {draft2}"},
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
            "moderation_block":   False,
            "scope_block":        False,
            "adp_b_raw":          adp_b_raw,
            "adp_a_raw":          draft,
            "adp_c_raw":          adp_c_raw,
            "scope_verdict":      scope_verdict,
            "pre_analysis_raw":   pre_analysis_raw,
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

    Request shape:  { messages, system, safety_system, eval_system, token,
                      user_text?, run_analysis?, scope_ambiguous?, rule_signal?,
                      base_strategy_text?, struct_annotations? }
    Response shape: { text, is_crisis, flags, verdict, regen, elapsed,
                      adp_b_raw, adp_a_raw, adp_c_raw,
                      pre_analysis_raw, scope_verdict,
                      enhanced_signal, enhanced_strategy }

    struct_annotations: Space-separated deterministic annotation string emitted by
    backend/paralinguistic_detector.py on Render (8 STRUCT + non-semantic PARA signals).
    Merged with Qwen3-4B semantic PARA tags in _run_structural_pre_analysis() and
    injected into ADP-B's safety system prompt. Defaults to "" (no-op) if absent.

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
        request.get("struct_annotations", ""),   # Render-side deterministic signals (split architecture)
        # regen_attempt is piggybacked inside rule_signal._regen_attempt (G-REGEN-01)
        # — NOT a separate positional arg, to preserve backward-compat with warm containers.
    )
    # Stamp the Modal container's load timestamp onto every response so Render
    # can log which Modal deploy served this request. _MODAL_LOAD_TS is set once
    # at module load (cold start) and is constant for the lifetime of the container.
    result["modal_load_ts"] = _MODAL_LOAD_TS
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

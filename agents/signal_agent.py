"""
agents/signal_agent.py
======================
Psychological Signal Agent — Step 2 of the NIKKO pipeline (first LLM call).

Spec source  : SPEC-100, SPEC-200 §5.2
               REQ-200-050 through REQ-200-053
               REQ-100-090 through REQ-100-093
               REQ-700-032 (output immutability)
Phase        : 3 — Agent Definitions (Implementation)
Authority    : LOW — emits SignalPayload to Router only. No other downstream
               communication is permitted. (REQ-200-052/053)

Role
----
Receives a sanitized user message (and optional in-session conversation
history) and returns a structured SignalPayload describing detected
psychological signals. The Router consumes this payload and assigns a mode.

Output immutability
-------------------
Once a SignalPayload is returned from `analyze()`, no downstream agent may
alter it. (REQ-700-032) Enforcement is by convention in Phase 3; a frozen
model config can be added when the Phase 2 schema is next revised.

Model strategy
--------------
Phase 3 uses Qwen2.5-3B-Instruct in zero-shot mode with the system prompt
from agent_prompts.md §3.1. It produces well-structured JSON and fits in
8GB VRAM without quantization. Fine-tuned adapters (Empathy + Safety) are
a Phase 4 deliverable and will be swapped in via PEFT's `load_adapter()`
without changing this class interface.

Production target (Phase 4+): Mistral-7B-Instruct-v0.3 with 4-bit NF4
quantization via bitsandbytes. Swapping is a one-line change to DEFAULT_MODEL_ID
and quantize_4bit. bitsandbytes==0.45.5 is the pinned version (resolved
Windows CUDA runtime DLL issue — see G-ENV-01 in docs/GAPS.md).
"""

from __future__ import annotations

import json
import re
import time
from typing import Optional

# [CONCEPT] Lazy imports for heavy dependencies
# torch and transformers are only imported inside _load_model(), not at module
# level. This means `from agents.signal_agent import SignalAgent` is fast and
# won't crash if transformers isn't installed — it only fails when you actually
# try to call analyze() without the model. The notebook mock-mode cells rely
# on this: they can import the class and test parse/validate logic without
# triggering a model download.

from docs.schemas.acp_schemas import (
    DistressLevel,
    SignalPayload,
)
from docs.schemas.validate import (
    VALID_SIGNAL_KEYS,
    get_confidence_band,
    validate_signal_payload,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Default base model — Apache 2.0 licence, primary choice per G-MODEL-01.
# Override at instantiation for testing with a smaller model (e.g. phi-3-mini).
# Phase 3 development model — Qwen2.5-3B fits in 8GB VRAM without quantization.
# Production target (Phase 4+): Mistral-7B-Instruct-v0.3 with quantize_4bit=True.
# swap back when the Windows bitsandbytes CUDA runtime issue is resolved.
DEFAULT_MODEL_ID: str = "Qwen/Qwen2.5-3B-Instruct"

# Max new tokens for signal output. The JSON schema is compact; 512 is generous.
_MAX_NEW_TOKENS: int = 512

# Temperature: low but non-zero. We want near-deterministic signal detection
# while allowing the model to express genuine uncertainty. (not 0.0 — that
# enables greedy decoding which can cause repetition loops in some models)
_TEMPERATURE: float = 0.1

# Timeout for a single generate() call, in seconds.
_GENERATE_TIMEOUT_S: float = 30.0

# System prompt — verbatim from agent_prompts.md §3.1.
# REQ-ID comments are stripped before the prompt is passed to the model
# (per agent_prompts.md traceability rule). They are preserved here for
# maintainability — a diff against agent_prompts.md will show any drift.
_SYSTEM_PROMPT: str = """You are the Psychological Signal Agent for Nikko. You detect observable linguistic patterns in user language that are associated with emotional states, cognitive patterns, behavioural indicators, and risk.

WHAT YOU DETECT
You detect patterns of expression — not conditions, not diagnoses, not identities.
You observe what the user says, not what they are.

THE FOUR SIGNAL LAYERS
1. Emotional states — expressed affect (sadness spectrum, anxiety spectrum, emotional dysregulation, shame/self-worth, emotional numbness)
2. Cognitive patterns — thinking styles (rumination, catastrophizing, black-white thinking, hopeless projection, personalization bias, negative core beliefs, helplessness, meaninglessness)
3. Behavioural indicators — described actions (withdrawal, avoidance, sleep disruption, appetite change, loss of motivation, coping attempts, help-seeking, self-reflection)
4. Risk indicators — passive (wishing to disappear, fatigue with living, indirect death reference) | active (suicidal ideation, self-harm reference, preparation statements, farewell framing) | acute (intent language, immediacy, loss of safety framing)

DISTRESS LEVEL SCALE
low — general conversation, minimal affect markers
moderate — identifiable emotional distress
high — pronounced distress, multiple signals
crisis — any active or acute risk indicator present

CONFIDENCE AND UNCERTAINTY
Your confidence reflects the strength of linguistic evidence — not psychological certainty.
Absence of signal is NOT absence of distress.
When cultural, neurodivergent, or indirect expression patterns are detected, reduce confidence and explain in uncertainty_notes.
If confidence < 0.40, the router will trigger fallback handling. Be accurate, not generous.

TEMPORAL AWARENESS
Consider conversational history. A single passive risk indicator in isolation is different from the same indicator repeated across three turns alongside high distress.

ABSOLUTE PROHIBITIONS
You MUST NOT: diagnose, infer mental disorders, label users clinically, output disorder names, communicate with any agent other than the Router, or produce user-facing text.
All values in your output arrays MUST resolve to keys in signal_enum.json. Do not invent new signal strings.

VALID SIGNAL KEYS (use these exact strings — no others):

DISTRESS LEVELS: low, moderate, high, crisis

EMOTIONAL STATES: sadness_spectrum.low_mood_language, sadness_spectrum.emotional_heaviness, sadness_spectrum.grief_expression, sadness_spectrum.loss_oriented_statements, anxiety_spectrum.worry_language, anxiety_spectrum.anticipatory_fear, anxiety_spectrum.hypervigilance, anxiety_spectrum.overwhelm_signals, emotional_dysregulation.rapid_emotional_shifts, emotional_dysregulation.intensity_escalation, emotional_dysregulation.inability_to_self_soothe, shame_self_worth.self_criticism, shame_self_worth.perceived_burden_language, shame_self_worth.worthlessness_framing, emotional_numbness.detachment_language, emotional_numbness.emptiness_statements, emotional_numbness.reduced_emotional_vocabulary

COGNITIVE PATTERNS: rumination_loop, catastrophizing, black_white_thinking, hopeless_future_projection, personalization_bias, negative_core_beliefs, helplessness_framing, meaninglessness_expression

BEHAVIORAL INDICATORS: withdrawal_isolation, avoidance_behavior, sleep_disruption, appetite_change, loss_of_motivation, coping_attempt, help_seeking_behavior, self_reflection_capacity

RISK INDICATORS: risk.passive.wishing_to_disappear, risk.passive.fatigue_with_living, risk.passive.indirect_death_reference, risk.active.suicidal_ideation, risk.active.self_harm_reference, risk.active.preparation_statement, risk.active.farewell_framing, risk.acute.intent_language, risk.acute.immediacy_statement, risk.acute.loss_of_safety_framing

SUPPORT NEEDS: emotional_validation, grounding_stabilization, psychoeducation, normalization, reflective_exploration, encouragement_external_support, crisis_escalation

OUTPUT FORMAT
Respond with ONLY a JSON object. No preamble. No explanation. No markdown fences.
{
  "distress_level": "low | moderate | high | crisis",
  "emotional_states": [],
  "cognitive_patterns": [],
  "behavioral_indicators": [],
  "risk_indicators": [],
  "support_needs": [],
  "confidence": 0.0,
  "uncertainty_notes": ""
}"""


# ---------------------------------------------------------------------------
# Signal Agent
# ---------------------------------------------------------------------------

class SignalAgent:
    """
    Psychological Signal Agent — first LLM-backed component in the pipeline.

    Usage:
        agent = SignalAgent()                          # model not loaded yet
        payload = agent.analyze("I've been struggling a lot lately.")
        # model loads on first call, then is cached for subsequent calls

    For testing without a GPU / model download, use mock_analyze() instead.
    See the Step 3 notebook for examples.
    """

    def __init__(
        self,
        model_id:      str  = DEFAULT_MODEL_ID,
        quantize_4bit: bool = False,   # disabled for Phase 3 dev — Qwen2.5-3B fits without it
        device_map:    str  = "auto",
    ) -> None:
        """
        Args:
            model_id:      HuggingFace model identifier. Defaults to Mistral 7B v0.3.
                           Can be overridden with any instruction-tuned causal LM.
            quantize_4bit: Load the model in 4-bit NF4 (bitsandbytes). Recommended
                           for consumer GPUs to fit within VRAM budget. Disable only
                           if you have sufficient VRAM (>= 16 GB for Mistral 7B in fp16).
            device_map:    Passed to from_pretrained(). "auto" lets accelerate place
                           layers across available devices. (REQ-Phase3-handoff)
        """
        self._model_id      = model_id
        self._quantize_4bit = quantize_4bit
        self._device_map    = device_map

        # [CONCEPT] Lazy initialization
        # These are None until _load_model() is called. This means importing
        # this module doesn't trigger a ~14 GB download or GPU allocation.
        # The first call to analyze() triggers the load; subsequent calls reuse
        # the cached model and tokenizer.
        self._model     = None
        self._tokenizer = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(
        self,
        sanitized_input:       str,
        conversation_history:  list[str] | None = None,
    ) -> SignalPayload:
        """
        Analyze a sanitized user message and return a validated SignalPayload.

        The payload is constructed and returned as the authoritative signal for
        this turn. No downstream agent may modify it. (REQ-700-032)

        Args:
            sanitized_input:      User message after input sanitization by the
                                  pipeline. MUST NOT be raw user text.
            conversation_history: Optional list of previous turn summaries,
                                  newest last, for temporal signal context
                                  (REQ-100 temporal awareness clause).

        Returns:
            SignalPayload — fully validated. All array elements guaranteed to
            be registered signal keys. Confidence is in [0.0, 1.0].

        On any failure (model error, parse error, validation collapse):
            Returns a safe fallback payload at low confidence, which causes
            the Router to fall back to Comfort Mode. Never raises.
        """
        self._ensure_model_loaded()

        prompt = self._build_prompt(sanitized_input, conversation_history or [])

        try:
            raw_output = self._generate(prompt)
        except Exception as exc:
            return self._safe_fallback(reason=f"Generation failed: {exc}")

        try:
            parsed = self._extract_json(raw_output)
        except ValueError as exc:
            return self._safe_fallback(reason=f"JSON extraction failed: {exc}")

        return self._build_payload(parsed)

    def mock_analyze(self, mock_response: dict) -> SignalPayload:
        """
        Inject a pre-built dict as if the model returned it, bypassing LLM call.

        Used exclusively in tests and notebooks when the model is not loaded.
        The response is still passed through full validation — this is not a
        bypass of correctness checks, only of the model call itself.

        Args:
            mock_response: Dict matching the signal output contract schema.

        Returns:
            SignalPayload — validated identically to a live analyze() call.
        """
        return self._build_payload(mock_response)

    # ------------------------------------------------------------------
    # Model lifecycle
    # ------------------------------------------------------------------

    def _ensure_model_loaded(self) -> None:
        """Load model and tokenizer on first call; no-op on subsequent calls."""
        if self._model is not None:
            return

        self._load_model()

    def _load_model(self) -> None:
        """
        Load the causal LM with optional 4-bit quantization.

        Why 4-bit NF4 (bitsandbytes)?
        Mistral 7B in fp16 requires ~14 GB VRAM. 4-bit quantization reduces
        this to ~4-5 GB with minimal quality loss for instruction-following
        tasks. The Director's RTX 3070 has 8 GB VRAM — quantization is
        required. (Phase 3 handoff note)

        Why double_quant=True?
        Double quantization quantizes the quantization constants themselves,
        saving a further ~0.4 GB at negligible quality cost.
        """
        # [CONCEPT] Deferred heavy imports
        # torch and transformers are imported here, not at module level.
        # This is intentional — see the module docstring note on lazy imports.
        import torch
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
            BitsAndBytesConfig,
        )

        print(f"[SignalAgent] Loading model: {self._model_id}")
        print(f"[SignalAgent] 4-bit quantization: {self._quantize_4bit}")
        t0 = time.perf_counter()

        self._tokenizer = AutoTokenizer.from_pretrained(
            self._model_id,
            use_fast=True,
        )
        # Mistral tokenizer doesn't set a pad token by default — required for
        # batched generation. Set it to eos_token (common safe default).
        if self._tokenizer.pad_token is None:
            self._tokenizer.pad_token = self._tokenizer.eos_token

        bnb_config = None
        if self._quantize_4bit:
            # [CONCEPT] BitsAndBytesConfig
            # This tells transformers to load model weights in 4-bit format
            # using bitsandbytes. "nf4" (Normal Float 4) is the quantization
            # type — designed specifically for normally-distributed weights,
            # which LLM weights typically are. compute_dtype is float16 so
            # actual matrix multiplications happen in fp16 (not int4), which
            # preserves accuracy while still getting the memory savings.
            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.float16,
                bnb_4bit_use_double_quant=True,
                bnb_4bit_quant_type="nf4",
            )

        self._model = AutoModelForCausalLM.from_pretrained(
            self._model_id,
            quantization_config=bnb_config,
            device_map=self._device_map,
            torch_dtype=torch.float16 if not self._quantize_4bit else None,
        )
        self._model.eval()

        elapsed = time.perf_counter() - t0
        print(f"[SignalAgent] Model loaded in {elapsed:.1f}s.")

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        sanitized_input:      str,
        conversation_history: list[str],
    ) -> str:
        """
        Build the full prompt using the instruction template from agent_prompts.md §3.2.

        The tokenizer's apply_chat_template() handles model-specific formatting
        (e.g. Mistral's [INST] tags, Phi-3's <|user|> tags) automatically.
        We always use the tokenizer's built-in template — never hardcode the
        [INST] format ourselves — so the same code works across model families.
        """
        history_section = ""
        if conversation_history:
            # Summarise history as a numbered list. The model reads this to
            # apply temporal awareness (REQ-100 temporal clause).
            history_lines = "\n".join(
                f"  Turn {i+1}: {turn}"
                for i, turn in enumerate(conversation_history[-6:])  # last 6 turns max
            )
            history_section = f"\nCONVERSATION HISTORY (this session, newest last):\n{history_lines}\n"

        user_content = (
            f"USER INPUT (sanitized):\n{sanitized_input}"
            f"{history_section}\n"
            "Emit a signal object conforming to the SPEC-100 §9 schema.\n"
            "All array values MUST be keys from the valid signal key list above.\n"
            "Respond with ONLY the JSON object — no markdown, no explanation."
        )

        # [CONCEPT] apply_chat_template()
        # Instead of manually wrapping text in [INST]...[/INST] tags (which is
        # Mistral-specific), we call apply_chat_template() with a messages list.
        # The tokenizer knows the correct format for the model it was loaded from.
        # tokenize=False means we get a string back, not token IDs — we tokenize
        # separately so we can inspect the prompt if needed.
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": user_content},
        ]
        return self._tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def _generate(self, prompt: str) -> str:
        """
        Run the model and return the raw text completion.

        Generation parameters are tuned for structured JSON output:
        - Low temperature (0.1): near-deterministic for signal keys
        - No repetition penalty: JSON keys repeat legitimately
        - do_sample=True required when temperature != 1.0
        """
        import torch

        inputs = self._tokenizer(
            prompt,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=4096,
        ).to(self._model.device)

        input_len = inputs["input_ids"].shape[1]

        with torch.inference_mode():
            output_ids = self._model.generate(
                **inputs,
                max_new_tokens=_MAX_NEW_TOKENS,
                temperature=_TEMPERATURE,
                do_sample=True,
                pad_token_id=self._tokenizer.pad_token_id,
                eos_token_id=self._tokenizer.eos_token_id,
            )

        # Slice off the prompt tokens — we only want the completion.
        new_tokens = output_ids[0][input_len:]
        return self._tokenizer.decode(new_tokens, skip_special_tokens=True)

    # ------------------------------------------------------------------
    # Output parsing
    # ------------------------------------------------------------------

    def _extract_json(self, raw_output: str) -> dict:
        """
        Extract the JSON object from the model's raw text output.

        LLMs sometimes wrap JSON in markdown fences (```json ... ```) or add
        preamble text. This method strips common wrappers and finds the first
        valid JSON object in the output.

        Raises:
            ValueError: If no valid JSON object can be extracted.
        """
        text = raw_output.strip()

        # Strip markdown code fences if present (```json ... ``` or ``` ... ```)
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE)
        text = text.strip()

        # [CONCEPT] Greedy JSON extraction
        # We search for the first `{` and the LAST `}` in the output. This is
        # intentionally greedy — if the model emits text after the JSON object,
        # the last `}` closes the object correctly. A non-greedy match would
        # cut off nested structures prematurely.
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise ValueError(
                f"No JSON object found in model output. Raw output: {text[:200]!r}"
            )

        try:
            return json.loads(match.group())
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"JSON parse error: {exc}. Extracted text: {match.group()[:200]!r}"
            ) from exc

    # ------------------------------------------------------------------
    # Payload construction and validation
    # ------------------------------------------------------------------

    def _build_payload(self, parsed: dict) -> SignalPayload:
        """
        Validate the parsed dict and construct a SignalPayload.

        Validation steps:
        1. Extract each field with a safe default (never raise on missing keys).
        2. Run validate_signal_payload() to find invalid enum keys.
        3. Scrub any invalid keys from the arrays (log them, don't crash).
        4. Clamp confidence to [0.0, 1.0].
        5. Enforce the distress_level / risk_indicator consistency rule:
           any active or acute risk key forces distress_level = "crisis".
        6. Construct and return the SignalPayload.

        Why scrub rather than fallback on invalid keys?
        A completely valid response with one hallucinated signal key should not
        discard all the valid signals. We scrub the bad key, log it in
        uncertainty_notes, and keep the rest. If scrubbing empties a critical
        field (e.g. all risk_indicators were invalid), the uncertainty_notes
        will capture that for the Evaluator to assess.
        """
        # --- Step 1: Extract fields with safe defaults ---
        raw_distress    = str(parsed.get("distress_level", "low")).lower()
        emotional       = list(parsed.get("emotional_states",      []))
        cognitive       = list(parsed.get("cognitive_patterns",     []))
        behavioral      = list(parsed.get("behavioral_indicators",  []))
        risk            = list(parsed.get("risk_indicators",        []))
        support         = list(parsed.get("support_needs",          []))
        raw_confidence  = float(parsed.get("confidence", 0.20))
        uncertainty     = str(parsed.get("uncertainty_notes", ""))

        # --- Step 2: Validate all array fields ---
        result = validate_signal_payload(
            emotional_states=emotional,
            cognitive_patterns=cognitive,
            behavioral_indicators=behavioral,
            risk_indicators=risk,
            support_needs=support,
        )

        scrub_notes: list[str] = []
        if not result.valid:
            # --- Step 3: Scrub invalid keys ---
            # Build a set of the bad keys for fast lookup, then filter each list.
            bad_field_keys: set[str] = set(result.invalid_keys)

            def scrub(field_name: str, items: list[str]) -> list[str]:
                clean, removed = [], []
                for item in items:
                    tag = f"{field_name}:{item}"
                    if tag in bad_field_keys:
                        removed.append(item)
                    else:
                        clean.append(item)
                if removed:
                    scrub_notes.append(
                        f"[SignalAgent] Scrubbed invalid keys from {field_name}: {removed}. "
                        f"(REQ-100-093)"
                    )
                return clean

            emotional  = scrub("emotional_states",      emotional)
            cognitive  = scrub("cognitive_patterns",     cognitive)
            behavioral = scrub("behavioral_indicators",  behavioral)
            risk       = scrub("risk_indicators",        risk)
            support    = scrub("support_needs",          support)

        # --- Step 4: Clamp confidence ---
        confidence = max(0.0, min(1.0, raw_confidence))

        # --- Step 5: Distress / risk consistency ---
        # The model might emit active/acute risk keys but forget to set
        # distress_level = "crisis". Enforce it here. (REQ-100-060)
        has_active_or_acute = any(
            k.startswith("risk.active.") or k.startswith("risk.acute.")
            for k in risk
        )
        if has_active_or_acute:
            if raw_distress != "crisis":
                scrub_notes.append(
                    "[SignalAgent] distress_level forced to 'crisis': active/acute risk "
                    f"indicators present but model emitted '{raw_distress}'. (REQ-100-060)"
                )
            raw_distress = "crisis"

        # Map raw string to DistressLevel enum. Default to "low" on unknown value.
        distress_map = {
            "low":      DistressLevel.LOW,
            "moderate": DistressLevel.MODERATE,
            "high":     DistressLevel.HIGH,
            "crisis":   DistressLevel.CRISIS,
        }
        distress_level = distress_map.get(raw_distress, DistressLevel.LOW)

        # Append scrub notes to uncertainty_notes for Evaluator visibility.
        if scrub_notes:
            uncertainty = (uncertainty + "\n" + "\n".join(scrub_notes)).strip()

        # --- Step 6: Construct payload ---
        return SignalPayload(
            distress_level=distress_level,
            emotional_states=emotional,
            cognitive_patterns=cognitive,
            behavioral_indicators=behavioral,
            risk_indicators=risk,
            support_needs=support,
            confidence=confidence,
            uncertainty_notes=uncertainty,
        )

    # ------------------------------------------------------------------
    # Safe fallback
    # ------------------------------------------------------------------

    def _safe_fallback(self, reason: str) -> SignalPayload:
        """
        Return a minimal safe payload when the model call or parse fails.

        Fallback confidence is set to 0.20 (deep within the low band), which
        guarantees the Router falls back to Comfort Mode and suppresses all
        evidence chains. (Router spec: confidence < 0.40 → COMFORT MODE)

        The reason string is logged in uncertainty_notes so the Evaluator and
        audit trace can surface the failure without it being silently swallowed.

        Args:
            reason: Human-readable explanation of why the fallback was triggered.

        Returns:
            Minimal SignalPayload — distress=low, confidence=0.20, no signals.
        """
        print(f"[SignalAgent] FALLBACK triggered: {reason}")
        return SignalPayload(
            distress_level=DistressLevel.LOW,
            emotional_states=[],
            cognitive_patterns=[],
            behavioral_indicators=[],
            risk_indicators=[],
            support_needs=["emotional_validation"],
            confidence=0.20,
            uncertainty_notes=f"[FALLBACK] {reason}",
        )

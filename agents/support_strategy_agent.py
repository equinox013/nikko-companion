"""
agents/support_strategy_agent.py
=================================
Support Strategy Agent — Step 4 of the NIKKO pipeline.

Spec source  : SPEC-200 §5.3, REQ-200-060 through REQ-200-062
               agent_prompts.md §4
Phase        : 3 — Agent Definitions (Implementation)
Authority    : MEDIUM — produces tone/framing guidance only; cannot access
               evidence sources or produce user-facing text.

Role
----
Receives the Router's mode decision and the Signal Agent's SignalPayload.
Translates them into concrete communication guidance for the Interaction
Model: tone, framing strategy, and response constraints.

CRITICAL: This agent is BYPASSED in Crisis Mode. Call crisis_bypass()
to obtain the static crisis strategy — do not call strategize() when
mode=CRISIS. (agent_prompts.md §4.1, CRISIS MODE clause)

Model sharing
-------------
The pipeline loads one model instance and passes it to both LLM-backed
agents (Signal Agent and this one) to avoid loading the model twice.
Phase 3 dev model: Qwen2.5-3B-Instruct (no quantization, fits in 8GB VRAM).
Production target (Phase 4+): Mistral-7B-Instruct-v0.3 with quantize_4bit=True.
If model/tokenizer are not injected at __init__, the agent lazy-loads
its own copy — useful for standalone testing.
"""

from __future__ import annotations

import json
import re
import time
from typing import Optional

from docs.schemas.acp_schemas import (
    DistressLevel,
    OperationalMode,
    SignalPayload,
    StrategyPayload,
)
from agents.router import RouterDecision

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_NEW_TOKENS: int   = 400
_TEMPERATURE:    float = 0.15   # slightly higher than Signal Agent — strategy
                                # benefits from mild variation in phrasing

# System prompt — verbatim from agent_prompts.md §4.1.
# REQ-ID comments stripped before passing to model (per traceability rule).
_SYSTEM_PROMPT: str = """You are the Support Strategy Agent for Nikko. You receive the Router's mode decision and the Signal Agent's output. You translate these into concrete communication guidance for the Interaction Model to follow.

YOUR OUTPUT SCOPE
You produce: tone guidance, framing strategy, and response constraints.
You do not generate user-facing text.
You do not access evidence sources.
You do not re-interpret emotional signals — treat the Signal Agent's output as authoritative.

MODE-SPECIFIC GUIDANCE

COMFORT MODE
Tone: warm, present, validating. Mirror the emotional weight without amplifying it.
Framing: validation first, information last (or never). The user's feelings are real and acknowledged before anything else is said.
Constraints: no advice unless explicitly requested; no evidence injection unless it arises naturally from a validation need; no solution-framing; keep responses short and human.

GUIDANCE MODE
Tone: calm, informative, grounded. Epistemic humility throughout.
Framing: information is offered as something that some people find helpful, not as prescription.
Constraints: evidence must be cited; no directive advice; no clinical authority language; encourage the user to verify with a professional; autonomy language required ("this is one perspective", "you might find it helpful to explore").

CRISIS MODE
You do not execute in Crisis Mode. If the Router emits CRISIS, this agent is bypassed. The Interaction Model receives a direct crisis instruction set.

DISTRESS-LEVEL CALIBRATION
high distress: soften information load, increase validation ratio, add encouragement toward human support.
low distress: balanced engagement is acceptable; information can be foregrounded if Guidance Mode.

HARD PROHIBITIONS
You MUST NOT: produce user-facing text, access evidence, modify signal outputs, issue directives to the user, suggest specific therapies or medications, or frame Nikko as a care provider.

OUTPUT FORMAT
Respond with ONLY a JSON object. No preamble. No explanation. No markdown fences.
{
  "tone_guidance": "string — one to three sentences describing how to sound",
  "framing_strategy": "string — one to three sentences on what to lead with and how to structure the response",
  "response_constraints": ["string", "string", ...]
}"""

# ---------------------------------------------------------------------------
# Static crisis strategy (used when mode=CRISIS; bypasses LLM entirely)
# ---------------------------------------------------------------------------

# [CONCEPT] Static crisis strategy
# When the Router assigns Crisis Mode, the Support Strategy Agent is bypassed.
# Instead of calling the LLM (which would add latency and variability during
# the highest-stakes interaction), we return a hardcoded StrategyPayload that
# encodes the crisis response doctrine from SPEC-300. This is intentional:
# crisis responses must be fast, predictable, and consistent — not creative.
_CRISIS_STRATEGY = StrategyPayload(
    mode=OperationalMode.CRISIS,
    distress_level=DistressLevel.CRISIS,
    tone_guidance=(
        "Calm, grounded, and human. Do not minimise the severity. "
        "Do not panic. Acknowledge directly and immediately."
    ),
    framing_strategy=(
        "Lead with immediate acknowledgement of the person's safety. "
        "Provide crisis resources clearly and without delay. "
        "Do not pivot to information, advice, or coping strategies — "
        "safety resources come first, always."
    ),
    response_constraints=[
        "Do not attempt to de-escalate with information or advice.",
        "Do not reference coping strategies or psychoeducation.",
        "Provide crisis hotlines (Lifeline 13 11 14, Beyond Blue 1300 22 4636, 000 for immediate danger).",
        "Do not frame Nikko as a substitute for professional crisis support.",
        "Keep the response short — clarity over completeness.",
        "Do not ask probing questions about the crisis plan.",
    ],
)


# ---------------------------------------------------------------------------
# Support Strategy Agent
# ---------------------------------------------------------------------------

class SupportStrategyAgent:
    """
    Translates Router decision + Signal payload into communication guidance.

    Usage (normal pipeline flow):
        agent = SupportStrategyAgent()
        if router_decision.mode == OperationalMode.CRISIS:
            strategy = agent.crisis_bypass()
        else:
            strategy = agent.strategize(router_decision, signal_payload)

    Usage (with shared model — avoid double-loading in pipeline):
        agent = SupportStrategyAgent(model=shared_model, tokenizer=shared_tokenizer)
    """

    def __init__(
        self,
        model_id:      str   = "Qwen/Qwen2.5-3B-Instruct",
        quantize_4bit: bool  = False,  # disabled for Phase 3 dev — see signal_agent.py note
        device_map:    str   = "auto",
        model=None,           # pre-loaded HuggingFace model (optional)
        tokenizer=None,       # pre-loaded tokenizer (optional)
    ) -> None:
        self._model_id      = model_id
        self._quantize_4bit = quantize_4bit
        self._device_map    = device_map
        # Accept injected model/tokenizer from the pipeline so we don't
        # load Mistral twice. If None, lazy-load on first strategize() call.
        self._model     = model
        self._tokenizer = tokenizer

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def crisis_bypass(self) -> StrategyPayload:
        """
        Return the static crisis strategy without calling the LLM.

        MUST be called instead of strategize() when Router mode = CRISIS.
        This is enforced by convention — the pipeline orchestrator is
        responsible for routing correctly. (agent_prompts.md §4.1)
        """
        return _CRISIS_STRATEGY

    def strategize(
        self,
        router_decision:      RouterDecision,
        signal:               SignalPayload,
        conversation_history: list[str] | None = None,
    ) -> StrategyPayload:
        """
        Generate a StrategyPayload for COMFORT or GUIDANCE mode turns.

        Args:
            router_decision:      Validated RouterDecision from the Router.
            signal:               Validated SignalPayload from the Signal Agent.
            conversation_history: Optional prior turn summaries for context.

        Returns:
            StrategyPayload — validated. Falls back to a safe default on
            any model or parse failure.

        Raises:
            ValueError: If called with mode=CRISIS. Use crisis_bypass() instead.
        """
        if router_decision.mode == OperationalMode.CRISIS:
            raise ValueError(
                "strategize() must not be called in Crisis Mode. "
                "Use crisis_bypass() instead. (agent_prompts.md §4.1)"
            )

        self._ensure_model_loaded()

        prompt = self._build_prompt(router_decision, signal, conversation_history or [])

        try:
            raw_output = self._generate(prompt)
        except Exception as exc:
            return self._safe_fallback(router_decision, signal, reason=f"Generation failed: {exc}")

        try:
            parsed = self._extract_json(raw_output)
        except ValueError as exc:
            return self._safe_fallback(router_decision, signal, reason=f"JSON extraction failed: {exc}")

        return self._build_payload(parsed, router_decision, signal)

    def mock_strategize(
        self,
        mock_response:   dict,
        router_decision: RouterDecision,
        signal:          SignalPayload,
    ) -> StrategyPayload:
        """
        Inject a pre-built dict, bypassing the LLM call. For tests only.
        Passes through the same build/validation path as a live call.
        """
        return self._build_payload(mock_response, router_decision, signal)

    # ------------------------------------------------------------------
    # Model lifecycle (mirrors SignalAgent pattern)
    # ------------------------------------------------------------------

    def _ensure_model_loaded(self) -> None:
        if self._model is not None:
            return
        self._load_model()

    def _load_model(self) -> None:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

        print(f"[SupportStrategyAgent] Loading model: {self._model_id}")
        t0 = time.perf_counter()

        self._tokenizer = AutoTokenizer.from_pretrained(self._model_id, use_fast=True)
        if self._tokenizer.pad_token is None:
            self._tokenizer.pad_token = self._tokenizer.eos_token

        bnb_config = None
        if self._quantize_4bit:
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
        print(f"[SupportStrategyAgent] Model loaded in {time.perf_counter() - t0:.1f}s.")

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        router_decision:      RouterDecision,
        signal:               SignalPayload,
        conversation_history: list[str],
    ) -> str:
        """Build the instruction prompt from agent_prompts.md §4.2 template."""

        # Serialise the signal payload to JSON for the model.
        # We exclude the payload_type discriminator field — it's schema
        # plumbing, not clinically meaningful for the strategy agent.
        signal_dict = signal.model_dump(exclude={"payload_type"})

        history_section = ""
        if conversation_history:
            lines = "\n".join(
                f"  Turn {i+1}: {t}"
                for i, t in enumerate(conversation_history[-4:])
            )
            history_section = f"\nCONVERSATION HISTORY (relevant prior turns):\n{lines}\n"

        user_content = (
            f"ROUTER DECISION:\n"
            f"Mode: {router_decision.mode.value}\n"
            f"Routing rationale: {router_decision.routing_rationale}\n\n"
            f"SIGNAL AGENT OUTPUT:\n"
            f"{json.dumps(signal_dict, indent=2)}\n"
            f"{history_section}\n"
            "Emit a strategy payload conforming to the StrategyPayload schema.\n"
            "Respond with ONLY the JSON object — no markdown, no explanation."
        )

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": user_content},
        ]
        return self._tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def _generate(self, prompt: str) -> str:
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

        new_tokens = output_ids[0][input_len:]
        return self._tokenizer.decode(new_tokens, skip_special_tokens=True)

    # ------------------------------------------------------------------
    # Output parsing
    # ------------------------------------------------------------------

    def _extract_json(self, raw_output: str) -> dict:
        """Extract JSON object from model output. Same pattern as SignalAgent."""
        text = raw_output.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"```\s*$",          "", text, flags=re.MULTILINE)
        text = text.strip()

        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise ValueError(f"No JSON object in output. Raw: {text[:200]!r}")

        try:
            return json.loads(match.group())
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON parse error: {exc}") from exc

    # ------------------------------------------------------------------
    # Payload construction
    # ------------------------------------------------------------------

    def _build_payload(
        self,
        parsed:          dict,
        router_decision: RouterDecision,
        signal:          SignalPayload,
    ) -> StrategyPayload:
        """
        Construct a StrategyPayload from the parsed model output.

        The mode and distress_level are taken from the Router decision and
        Signal payload respectively — not from the model output. The model
        is not trusted to reproduce these correctly; we enforce them here.
        This prevents the Strategy Agent from silently overriding routing
        decisions. (REQ-200-060: outputs shall include tone/framing/constraints)
        """
        tone        = str(parsed.get("tone_guidance",    "")).strip()
        framing     = str(parsed.get("framing_strategy", "")).strip()
        constraints = [str(c) for c in parsed.get("response_constraints", [])]

        # Guard: if the model returns empty fields, fall back to safe defaults
        # rather than passing empty strings to the Interaction Model.
        if not tone or not framing:
            return self._safe_fallback(
                router_decision, signal,
                reason="Model returned empty tone_guidance or framing_strategy."
            )

        return StrategyPayload(
            mode=router_decision.mode,            # always from Router, not model
            distress_level=signal.distress_level, # always from Signal Agent
            tone_guidance=tone,
            framing_strategy=framing,
            response_constraints=constraints,
        )

    # ------------------------------------------------------------------
    # Safe fallback
    # ------------------------------------------------------------------

    def _safe_fallback(
        self,
        router_decision: RouterDecision,
        signal:          SignalPayload,
        reason:          str,
    ) -> StrategyPayload:
        """
        Return a safe default strategy when the model call or parse fails.

        Defaults are mode-appropriate: COMFORT fallback is warm/validating,
        GUIDANCE fallback is calm/informative. Both are conservative — they
        err toward less information and more validation.
        """
        print(f"[SupportStrategyAgent] FALLBACK triggered: {reason}")

        if router_decision.mode == OperationalMode.GUIDANCE:
            return StrategyPayload(
                mode=router_decision.mode,
                distress_level=signal.distress_level,
                tone_guidance=(
                    "Calm, grounded, and informative. Maintain epistemic humility throughout."
                ),
                framing_strategy=(
                    "Offer information as something others have found helpful, "
                    "not as prescription. Encourage professional verification."
                ),
                response_constraints=[
                    "Cite evidence sources.",
                    "No directive advice.",
                    "Autonomy language required.",
                    f"[FALLBACK] {reason}",
                ],
            )

        # Default: COMFORT
        return StrategyPayload(
            mode=OperationalMode.COMFORT,
            distress_level=signal.distress_level,
            tone_guidance=(
                "Warm, present, and validating. Mirror emotional weight without amplifying it."
            ),
            framing_strategy=(
                "Lead with acknowledgement of the user's feelings before anything else."
            ),
            response_constraints=[
                "No advice unless explicitly requested.",
                "No solution-framing.",
                "Keep responses short and human.",
                f"[FALLBACK] {reason}",
            ],
        )

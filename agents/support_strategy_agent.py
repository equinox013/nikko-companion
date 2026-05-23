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
Production target (Phase 4+, Director-approved 2026-05-14):
  ADP-A (empathy/response generation): Qwen3-4B base (no LoRA for MVP)
  ADP-B (safety/crisis detection):     Gemma-2-2b-it
  ADP-C (response evaluation):         Gemma-2-2b-it
Mistral-7B-Instruct-v0.3 was the previous target but was infeasible on RTX 3070
8GB VRAM. bitsandbytes/NF4 quantization is no longer used in production.
See hf_space/app.py for the dual-model deployment architecture.
If model/tokenizer are not injected at __init__, the agent lazy-loads
its own copy — useful for standalone testing.
"""

from __future__ import annotations

import json
import os
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
# Deployment mode flag (mirrors signal_agent.py)
# ---------------------------------------------------------------------------
_LOCAL_LLM: bool = os.getenv("NIKKO_LOCAL_LLM", "true").lower() not in ("false", "0", "no")

# ---------------------------------------------------------------------------
# Decision table — rule-based strategy (primary path on Render / no-GPU)
# ---------------------------------------------------------------------------
# [CONCEPT] Strategy decision table
# A (mode, distress_level) matrix that maps every valid routing outcome to
# pre-ratified tone + framing + constraint guidance. This replaces the LLM
# judge with deterministic output: given the same mode and distress level,
# the strategy is identical every time — no model latency, no variability.
#
# The table covers all 8 cells of the (COMFORT|GUIDANCE) × (LOW|MODERATE|HIGH|CRISIS)
# space. CRISIS mode is handled separately by crisis_bypass() per the spec;
# the CRISIS rows here are defensive fallbacks in case routing is incorrect.
#
# Authority: MEDIUM — produces tone/framing guidance only. Cannot access
# evidence sources or produce user-facing text. (SPEC-200 §5.3)

_StrategyCell = dict  # type alias for readability

_STRATEGY_TABLE: dict[tuple[OperationalMode, DistressLevel], _StrategyCell] = {

    # ── COMFORT × LOW ──────────────────────────────────────────────────────
    (OperationalMode.COMFORT, DistressLevel.LOW): {
        "tone_guidance": (
            "Warm, present, and gently curious. Match the user's energy without "
            "over-intensifying. Sound human and unhurried."
        ),
        "framing_strategy": (
            "Acknowledge whatever the user has shared, however lightly. Keep it "
            "conversational. Information last — or never if not invited."
        ),
        "response_constraints": [
            "No advice unless explicitly requested.",
            "Keep responses brief — one to two sentences preferred.",
            "No clinical language.",
            "No solution-framing.",
            # G-SYCO-01: validate the emotion ('that sounds...'), not the factual premise
            # ('that IS...'). A question is welcome when natural — never mandatory.
            # One is only required as a counterbalance if the response would otherwise
            # unconditionally endorse the premise. Pure acknowledgement is fine.
            "Validate the emotional experience, not the factual premise of the complaint. "
            "A gentle open question is welcome when it arises naturally — do not force one.",
        ],
    },

    # ── COMFORT × MODERATE ─────────────────────────────────────────────────
    (OperationalMode.COMFORT, DistressLevel.MODERATE): {
        "tone_guidance": (
            "Warm, steady, and validating. Acknowledge first — hold space before "
            "anything else. No urgency. No advice energy."
        ),
        "framing_strategy": (
            "Lead with the user's feelings. Reflect what they shared without "
            "interpretation or judgment. One validation before any pivot."
        ),
        "response_constraints": [
            "No unsolicited advice.",
            "No evidence injection unless it arises from a direct validation need.",
            "Do not solution-frame.",
            "Keep responses short — do not overwhelm.",
            "Human-first language throughout.",
            # G-SYCO-01: emotion validation is correct; premise endorsement without any
            # exploratory element is not. A question is welcome when natural — never
            # mandatory. Pure acknowledgement is the right response more often than not.
            "Validate the emotional experience ('that sounds really...'), not the factual "
            "premise ('that IS really...'). A gentle open question is welcome when it "
            "arises naturally — do not append one to every response.",
        ],
    },

    # ── COMFORT × HIGH ─────────────────────────────────────────────────────
    (OperationalMode.COMFORT, DistressLevel.HIGH): {
        "tone_guidance": (
            "Calm, steady, and deeply validating. Slow the exchange — there is no "
            "rush. The user feeling heard is the only goal right now."
        ),
        "framing_strategy": (
            "Begin with a direct, specific acknowledgement of exactly what the user "
            "said. Do not pivot to information or strategies until the user signals "
            "readiness. Actively encourage connection with trusted human supports."
        ),
        "response_constraints": [
            "No advice.",
            "No solution-framing.",
            "No clinical information.",
            "Actively encourage human support (friends, family, professional).",
            "Keep responses short — do not overwhelm at high distress.",
            "Autonomy language required if any pivot becomes necessary.",
            "Never minimise or normalise the distress.",
            # G-SYCO-01: even at HIGH distress, do not unconditionally endorse the
            # factual premise. Validate the emotion deeply. A question is rarely the
            # right move here — acknowledgement alone is almost always sufficient.
            # Only include one if the response would otherwise endorse a premise outright.
            "Validate the emotional experience deeply — not the factual premise of the "
            "complaint. Acknowledgement alone is the right response at this distress level. "
            "Do not append a question unless the response would otherwise endorse a premise "
            "unconditionally.",
        ],
    },

    # ── COMFORT × CRISIS (defensive — should be routed to CRISIS mode) ─────
    (OperationalMode.COMFORT, DistressLevel.CRISIS): {
        "tone_guidance": (
            "Calm, grounded, and immediately present. Do not minimise. Do not panic. "
            "Acknowledge directly."
        ),
        "framing_strategy": (
            "Lead with acknowledgement of the person's safety. Provide crisis "
            "resources immediately — do not pivot to any other content."
        ),
        "response_constraints": [
            "Provide crisis hotlines immediately: Lifeline 13 11 14, Beyond Blue 1300 22 4636, 000 for immediate danger.",
            "No coping strategies or psychoeducation before crisis resources.",
            "Do not ask probing questions about the crisis plan.",
            "Keep the response brief — clarity over completeness.",
            "Do not frame Nikko as a substitute for professional crisis support.",
        ],
    },

    # ── GUIDANCE × LOW ─────────────────────────────────────────────────────
    (OperationalMode.GUIDANCE, DistressLevel.LOW): {
        "tone_guidance": (
            "Calm, informative, and grounded. Epistemic humility throughout. "
            "Collaborative and exploratory — not prescriptive."
        ),
        "framing_strategy": (
            "Information is offered as something others have found helpful, not as "
            "a directive. Lead with the user's question, answer it clearly, then "
            "invite their response."
        ),
        "response_constraints": [
            "Evidence must be cited if synthesised evidence is present.",
            "Autonomy language required: 'you might find', 'one approach is', 'some people find helpful'.",
            "No directive advice ('you should', 'you need to').",
            "Encourage professional verification for clinical content.",
            "Do not assert clinical facts without hedging.",
            # G-SYCO-01: validate the emotion briefly, then introduce a Socratic question
            # or alternative perspective. Do not unconditionally endorse the user's premise.
            "Validate emotion briefly first. Then introduce a Socratic question or an "
            "alternative perspective — do not endorse the factual premise unconditionally. "
            "Emotion is real; premises warrant gentle examination.",
        ],
    },

    # ── GUIDANCE × MODERATE ────────────────────────────────────────────────
    (OperationalMode.GUIDANCE, DistressLevel.MODERATE): {
        "tone_guidance": (
            "Warm and informative in equal measure. Balance genuine care with "
            "grounded information. Epistemic humility throughout."
        ),
        "framing_strategy": (
            "Validate the emotional context briefly (one sentence), then offer the "
            "information. Frame all information as optional and self-determined — "
            "the user is the expert on their own experience."
        ),
        "response_constraints": [
            "Validation before information — always.",
            "Autonomy language required throughout.",
            "Evidence must be cited if present.",
            "No directives.",
            "Encourage professional consultation.",
            "Do not assert facts without hedging.",
            # G-SYCO-01: validate emotion first, then gently examine the premise.
            # Unconditional endorsement without any Socratic element is not acceptable.
            "Validate the emotion first. Then introduce a Socratic question or offer an "
            "alternative perspective on the situation. Do not unconditionally endorse the "
            "factual premise — the goal is gentle examination, not agreement.",
        ],
    },

    # ── GUIDANCE × HIGH ────────────────────────────────────────────────────
    (OperationalMode.GUIDANCE, DistressLevel.HIGH): {
        "tone_guidance": (
            "Gentle and grounding first — information is strictly secondary to "
            "stability. Warmth over content. Epistemic humility throughout."
        ),
        "framing_strategy": (
            "Acknowledge the distress clearly before offering any information. "
            "Keep information minimal — one or two points at most. Lead with "
            "support; information follows only if the user is ready."
        ),
        "response_constraints": [
            "Acknowledgement required before any information.",
            "Reduce information load — one or two points maximum.",
            "Explicitly encourage human support.",
            "Autonomy language required.",
            "Evidence must be cited if present.",
            "Do not assert clinical facts without hedging.",
            "Monitor for distress escalation — if signals worsen, pivot to COMFORT framing.",
            # G-SYCO-01: at HIGH distress in Guidance Mode, the Socratic element should
            # be light — a single gentle question is sufficient. Do not unconditionally
            # endorse the factual premise. The question must feel supportive, not probing.
            "Validate the emotion first. Include one very gentle exploratory question — "
            "sufficient to avoid unconditional premise endorsement, but calibrated to the "
            "high distress level. Do not push the reframe at this intensity.",
        ],
    },

    # ── GUIDANCE × CRISIS (defensive — should be routed to CRISIS mode) ────
    (OperationalMode.GUIDANCE, DistressLevel.CRISIS): {
        "tone_guidance": (
            "Calm, grounded, and immediately present. Do not minimise. Do not panic."
        ),
        "framing_strategy": (
            "Acknowledge directly. Provide crisis resources without delay. "
            "Do not lead with information or guidance content."
        ),
        "response_constraints": [
            "Provide crisis hotlines immediately: Lifeline 13 11 14, Beyond Blue 1300 22 4636, 000 for immediate danger.",
            "No information or coping content before crisis resources.",
            "Keep the response brief and clear.",
            "Do not frame Nikko as a substitute for professional crisis support.",
        ],
    },
}

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

SYCOPHANCY PREVENTION
Validate the user's EMOTION — never the factual premise of their complaint.

Permitted:     "That sounds really draining." (emotion acknowledged)
Not permitted: "That's completely unfair." (premise endorsed without exploration)
Correct:       "That sounds really draining — what's been the hardest part?" (emotion + exploration)

The distinction matters because unconditional premise validation can reinforce distorted thinking,
creating an echo-chamber effect that undermines the CBT-grounded support model.

In COMFORT MODE: Acknowledge the emotion fully — that is the primary goal. A gentle open question
is welcome when it arises naturally from what the user shared, but do not append one formulaically.
Acknowledgement alone is often the right response. A question is only necessary if the response
would otherwise unconditionally endorse the factual premise of the complaint.

In GUIDANCE MODE: After briefly acknowledging the emotion, introduce a Socratic question or offer
an alternative perspective. The goal is to help the user examine their thinking, not agree with
their framing. Do not endorse the premise unconditionally.

A response is sycophantic only if it endorses the factual premise unconditionally AND contains no
exploratory element. Pure emotion validation with no premise claim is always acceptable.
CRISIS MODE is exempt — safety resources and immediate stabilisation take absolute priority.

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

    When NIKKO_LOCAL_LLM=false (Render / no GPU), strategize() uses the
    deterministic _rule_strategize() decision table -- no model load attempted.
    When NIKKO_LOCAL_LLM=true (HF Spaces / local GPU), the LLM path runs
    first and falls back to _rule_strategize() on any load or parse failure.

    Usage (normal pipeline flow):
        agent = SupportStrategyAgent()
        if router_decision.mode == OperationalMode.CRISIS:
            strategy = agent.crisis_bypass()
        else:
            strategy = agent.strategize(router_decision, signal_payload)

    Usage (with shared model):
        agent = SupportStrategyAgent(model=shared_model, tokenizer=shared_tokenizer)
    """

    def __init__(
        self,
        model_id:      str   = "Qwen/Qwen2.5-3B-Instruct",
        quantize_4bit: bool  = False,
        device_map:    str   = "auto",
        model=None,
        tokenizer=None,
    ) -> None:
        self._model_id      = model_id
        self._quantize_4bit = quantize_4bit
        self._device_map    = device_map
        self._model         = model
        self._tokenizer     = tokenizer

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def crisis_bypass(self) -> StrategyPayload:
        """
        Return the static crisis strategy without calling the LLM.
        MUST be called instead of strategize() when Router mode = CRISIS.
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

        When NIKKO_LOCAL_LLM=false, delegates immediately to _rule_strategize()
        (decision table lookup, no model call).

        Raises:
            ValueError: If called with mode=CRISIS. Use crisis_bypass() instead.
        """
        if router_decision.mode == OperationalMode.CRISIS:
            raise ValueError(
                "strategize() must not be called in Crisis Mode. "
                "Use crisis_bypass() instead. (agent_prompts.md 4.1)"
            )

        # [CONCEPT] Deployment-mode fork
        # When NIKKO_LOCAL_LLM=false (Render free tier), we skip the LLM
        # entirely and go directly to the decision table. No model load,
        # no transformers import, no RAM spike.
        if not _LOCAL_LLM:
            return self._rule_strategize(router_decision, signal)

        # LLM path -- falls back to rule engine on any failure.
        try:
            self._ensure_model_loaded()
            prompt = self._build_prompt(router_decision, signal, conversation_history or [])
            raw_output = self._generate(prompt)
        except Exception as exc:
            print(f"[SupportStrategyAgent] LLM path failed ({exc}), using rule engine.")
            return self._rule_strategize(router_decision, signal)

        try:
            parsed = self._extract_json(raw_output)
        except ValueError as exc:
            print(f"[SupportStrategyAgent] JSON parse failed ({exc}), using rule engine.")
            return self._rule_strategize(router_decision, signal)

        return self._build_payload(parsed, router_decision, signal)

    # ------------------------------------------------------------------
    # Rule-based strategy (primary path on Render / no-GPU deploys)
    # ------------------------------------------------------------------

    def _rule_strategize(
        self,
        router_decision: RouterDecision,
        signal:          SignalPayload,
    ) -> StrategyPayload:
        """
        Deterministic (mode, distress_level) decision table lookup.

        Returns the pre-ratified tone_guidance, framing_strategy, and
        response_constraints from _STRATEGY_TABLE. Falls through to
        _safe_fallback() only on a missing table entry (defensive path).
        """
        mode     = router_decision.mode
        distress = signal.distress_level
        cell     = _STRATEGY_TABLE.get((mode, distress))

        if cell is None:
            return self._safe_fallback(
                router_decision, signal,
                reason=f"No strategy table entry for ({mode.value}, {distress.value})."
            )

        return StrategyPayload(
            mode=mode,
            distress_level=distress,
            tone_guidance=cell["tone_guidance"],
            framing_strategy=cell["framing_strategy"],
            response_constraints=list(cell["response_constraints"]),
        )

    def mock_strategize(
        self,
        mock_response:   dict,
        router_decision: RouterDecision,
        signal:          SignalPayload,
    ) -> StrategyPayload:
        """Inject a pre-built dict, bypassing the LLM call. For tests only."""
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
        """Build the instruction prompt from agent_prompts.md 4.2 template."""
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
            "Respond with ONLY the JSON object -- no markdown, no explanation."
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
        """Extract JSON object from model output."""
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
        Construct a StrategyPayload from parsed model output.
        mode and distress_level are taken from Router/Signal -- not the model.
        """
        tone        = str(parsed.get("tone_guidance",    "")).strip()
        framing     = str(parsed.get("framing_strategy", "")).strip()
        constraints = [str(c) for c in parsed.get("response_constraints", [])]

        if not tone or not framing:
            return self._safe_fallback(
                router_decision, signal,
                reason="Model returned empty tone_guidance or framing_strategy."
            )

        return StrategyPayload(
            mode=router_decision.mode,
            distress_level=signal.distress_level,
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
        COMFORT fallback is warm/validating; GUIDANCE fallback is calm/informative.
        Both err toward less information and more validation.
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

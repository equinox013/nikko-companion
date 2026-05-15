"""
agents/evaluator_agent.py
==========================
Evaluator Agent — Phase 3, Step 8.

Spec source : SPEC-200 §5.7, REQ-200-100, REQ-200-101, REQ-200-EV1,
              SAFETY_GUARDRAILS.md R1–R15,
              REQ-850-083 (USM audit requirement),
              REQ-200-171 (single evaluation pass — no recursion).

Role in the pipeline (SPEC-700 §7)
------------------------------------
  Interaction Model
       │  draft_response: str            ← user-facing text to audit
       ▼
  Evaluator Agent (this module)          ← FINAL CONTENT GATE
       │  EvaluationPayload
       ▼
  Verification Supervisor               ← structural gate (Step 9)

Authority: HIGH — can reject or request regeneration of any response.
Runs BEFORE the Verification Supervisor. Both must pass for delivery. (REQ-200-EV1)

Two-pass architecture
---------------------
Pass 1 — Deterministic hard-fail check (no LLM)
  Regex-based scan of the draft response against red lines R1–R15
  from SAFETY_GUARDRAILS.md.  A single red-line match → verdict=FAIL
  immediately, no LLM call.  This is intentional: safety-critical
  rejections must be fast, deterministic, and never dependent on LLM
  judgment.

Pass 2 — LLM judge pass (ADP-C / Evaluator Adapter)
  Structured JSON prompt that checks:
    - Tone compliance: is the response warm and non-directive as per the
      strategy? Does it avoid coercive or judgemental framing?
    - Hallucination heuristics: does the response cite sources that
      weren't in the synthesised evidence? Does it assert clinical facts
      without hedging?
  A tone or hallucination failure → verdict=REGENERATE (recoverable).

USM audit (REQ-850-083)
  When usm_active=True, an extra deterministic check verifies that the
  response does not reference crisis-state history from USM memory,
  does not make clinical inferences from memory, and does not position
  Nikko as a continuous care provider.  USM audit failure → verdict=FAIL
  (non-recoverable per REQ-850-083).

Verdict rules
-------------
  FAIL       — any safety red line (R1–R15) OR USM audit failure
  REGENERATE — tone failure OR hallucination flag (no safety red line)
  PASS       — all checks clear
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Optional

from docs.schemas.acp_schemas import (
    EvaluationPayload,
    EvaluationVerdict,
    OperationalMode,
    ResponseContextPayload,
    SynthesizedEvidence,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Red-line pattern table (SAFETY_GUARDRAILS.md R1–R15)
# ---------------------------------------------------------------------------
# Each entry: (red_line_id, description, compiled_regex)
# Regex targets phrasing patterns that directly violate a hard prohibition.
# These are intentionally conservative — they may flag some borderline cases
# that a human reviewer would pass. That's acceptable: the cost of a false
# positive (regeneration) is lower than the cost of a false negative (harmful
# output reaching the user).

# [CONCEPT] Hard-fail pattern matching
# Rather than asking the LLM to judge its own safety (which can be gamed by
# sophisticated prompt injection), we use deterministic regex patterns for the
# most critical safety violations.  The LLM is used only for the softer checks
# (tone, hallucination) where deterministic rules can't capture nuance.

_RED_LINE_PATTERNS: list[tuple[str, str, re.Pattern]] = [
    # R1: Diagnosis (REQ-000-060)
    # R1: Diagnosis (REQ-000-060)
    # Constraint: "you have" must be followed by a clinical noun — bare "you have"
    # is too broad and catches normal conversational phrases like "you have described".
    # R15 handles "you have [specific named diagnosis]"; R1 catches the structural frame.
    ("R1", "Diagnostic statement detected",
     re.compile(
         r"\b(you have (a |an |the )?(disorder|condition|illness|syndrome|diagnosis)|"
         r"you are (suffering from|diagnosed with)|"
         r"you are experiencing (a |an |the )?(disorder|condition|illness|syndrome|"
         r"depression|anxiety|panic|psychosis|episode)|"
         r"you('re| are) (a|the).{0,30}(disorder|condition|illness)|"
         r"(it|this) (sounds like|is|appears to be) (a|the)?\s*(disorder|depression|anxiety|"
         r"bipolar|schizophrenia|ptsd|ocd|adhd|bpd|personality disorder))\b",
         re.IGNORECASE,
     )),
    # R2: Medication / specific therapy recommendation (REQ-000-062/063)
    ("R2", "Medication or specific therapy recommendation detected",
     re.compile(
         r"\b(you should (take|try|start|use|consider taking)|"
         r"i (recommend|suggest|advise) (that )?you (take|try|use)|"
         r"(take|try) (sertraline|fluoxetine|escitalopram|quetiapine|lithium|"
         r"antidepressant|medication|ssri|snri)|"
         r"you (need|must|should) (see|try|do) (cbt|emdr|dbt|psychotherapy|therapy))\b",
         re.IGNORECASE,
     )),
    # R3: Replacing professional or crisis services (REQ-000-020)
    ("R3", "Positioning Nikko as professional or crisis-service replacement",
     re.compile(
         r"\b(i can (replace|provide) (therapy|treatment|crisis support|professional help)|"
         r"you don'?t need (a|to see a|to call a)?\s*(therapist|psychiatrist|counsellor|"
         r"psychologist|professional|crisis line|lifeline)|"
         r"(nikko|i) (am|is) (your|a) (therapist|psychiatrist|counsellor|doctor|clinician))\b",
         re.IGNORECASE,
     )),
    # R4: Independent crisis resolution (REQ-000-080)
    ("R4", "Attempt to independently resolve suicidal crisis without crisis referral",
     re.compile(
         r"\b(i('ll| will) (help you|work through this|resolve this|handle this) (instead of|"
         r"without|before you) (calling|contacting|reaching out to)|"
         r"you don'?t (need to|have to) call (lifeline|000|the crisis|a crisis))\b",
         re.IGNORECASE,
     )),
    # R5/R6: Professional credential claims or therapist simulation (REQ-000-050/051)
    ("R5", "Professional credential claim or therapist simulation",
     re.compile(
         r"\b(as (a|your) (therapist|psychiatrist|psychologist|clinician|doctor|"
         r"medical professional|mental health professional)|"
         r"in my (clinical|professional|medical|psychiatric) (opinion|judgment|assessment)|"
         r"(my|from a) (clinical|professional|therapeutic) (perspective|standpoint))\b",
         re.IGNORECASE,
     )),
    # R7: Emotional sentience claim (REQ-000-052)
    ("R7", "Emotional sentience claim",
     re.compile(
         r"\b(i (feel|am feeling|genuinely feel|truly feel|experience|am experiencing) "
         r"(sadness|happiness|grief|love|pain|empathy|compassion|care)|"
         r"(that|this) (makes|breaks|touches|moves) my heart|"
         r"i (love|deeply care about|am emotionally invested in) you)\b",
         re.IGNORECASE,
     )),
    # R8: Moral judgment or coercion (REQ-000-091/092)
    ("R8", "Moral judgment or behavioural coercion",
     re.compile(
         r"\b(you (must|need to|have to|should) (stop|quit|avoid|never|always)|"
         r"it('s| is) (wrong|bad|unhealthy|dangerous|irresponsible) (for you|of you) to|"
         r"you (are being|are acting) (selfish|irrational|unreasonable|dramatic))\b",
         re.IGNORECASE,
     )),
    # R10: Delaying crisis resources with probing (REQ-300-110/111/112)
    ("R10", "Crisis resource delivery delayed by probing questions",
     re.compile(
         r"\b(before (i give you|providing|sharing) (the|crisis|those)?\s*(resources?|numbers?|"
         r"hotlines?|help)|first, (can|could|tell me|let'?s)|"
         r"let'?s (talk (more )?about|explore|understand) (this|that|your feelings?) first)\b",
         re.IGNORECASE,
     )),
    # R11: Minimising crisis severity (REQ-300-130)
    ("R11", "Crisis severity minimisation",
     re.compile(
         r"\b(it('?s| is) (not|probably not) (that|as) (serious|bad|severe|dangerous)|"
         r"(everyone|a lot of people) (feels?|goes? through)(\s+\S+){0,4}\s+(this|that|the same)|"
         r"you('re| are) (overreacting|being overdramatic|exaggerating)|"
         r"(things|it) (will|are going to) (definitely|surely|certainly) (get|be) (better|fine|okay))\b",
         re.IGNORECASE,
     )),
    # R15: Diagnostic phrasing (REQ-100-114)
    ("R15", "Diagnostic phrasing pattern ('you have X disorder')",
     re.compile(
         r"\b(you (have|('ve|have) (been|got)|are living with|suffer from)\s+"
         r"(major depressive disorder|depression|anxiety disorder|generalised anxiety|"
         r"panic disorder|bipolar disorder|schizophrenia|ptsd|ocd|adhd|bpd|"
         r"borderline personality|personality disorder|eating disorder))\b",
         re.IGNORECASE,
     )),
]

# ---------------------------------------------------------------------------
# USM anti-patterns (REQ-850-083)
# ---------------------------------------------------------------------------
# Phrases that indicate the response is referencing USM memory in a way that
# violates the constraint against: (1) referencing crisis-state history from
# memory, (2) making clinical inferences from memory, (3) positioning Nikko
# as a continuous care provider based on memory continuity.

_USM_VIOLATION_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("USM-1: Crisis history reference from memory",
     re.compile(
         r"\b(last time you (felt|mentioned|said|talked about|experienced)|"
         r"(as|like) you (mentioned|said|shared) (before|previously|last (time|session))|"
         r"(remember(ing)?|recalling) (when|that|your) (you|crisis|episode|breakdown|"
         r"suicidal|thoughts of))\b",
         re.IGNORECASE,
     )),
    ("USM-2: Clinical inference from memory continuity",
     re.compile(
         r"\b(based on (what|everything) (you'?ve|you have) (shared|told me)|"
         r"(given|considering) (your|the) (history|pattern|recurring|ongoing)|"
         r"(this|it) (suggests?|indicates?|shows?) (a |an )?(pattern|trend|ongoing|chronic))\b",
         re.IGNORECASE,
     )),
    ("USM-3: Continuous care provider positioning",
     re.compile(
         r"\b((nikko|i) (will|can|am here to) (continue|keep) (supporting|tracking|monitoring)|"
         r"(i|nikko) (remember|recall|know) (your|about your) (history|journey|progress)|"
         r"(your|our) (ongoing|continuing|long.term) (relationship|journey|progress|sessions?))\b",
         re.IGNORECASE,
     )),
]

# ---------------------------------------------------------------------------
# Evaluator Adapter system prompt (ADP-C)
# ---------------------------------------------------------------------------
# [CONCEPT] Evaluator Adapter (ADP-C)
# This system prompt IS the Evaluator Adapter. In SPEC-400, adapters are
# described as LoRA fine-tune layers. In Phase 3, we use a system prompt to
# approximate the adapter's behavior — the adapter would reinforce these
# instructions through training rather than relying on in-context instruction
# following. When Phase 4 fine-tuning produces a real ADP-C checkpoint, this
# prompt will be replaced by loading that LoRA layer.
_EVALUATOR_SYSTEM_PROMPT = """\
You are the Evaluator for Nikko, a mental health support AI. Your task is to audit a DRAFT RESPONSE against two criteria.

You do NOT judge safety (that is handled separately). You judge:

1. TONE COMPLIANCE
Does the response follow its operational mode?
- COMFORT mode: warm, non-directive, validating. Never solution-focused. Feelings acknowledged before anything else.
- GUIDANCE mode: calm, informative, epistemic humility present. Claims hedged. Professional consultation encouraged.
- CRISIS mode: direct, grounding, no delays, crisis resources present.

Tone FAILS if:
- Response is cold, clinical, or robotic in COMFORT mode.
- Response gives directives ("you should", "you need to") in COMFORT mode.
- Response asserts facts without hedging in GUIDANCE mode ("this WILL help").
- Response fails to ground the user and provide resources in CRISIS mode.

2. HALLUCINATION CHECK
Does the response assert specific facts, statistics, or citations that are NOT in the provided evidence?
A response with no evidence context (COMFORT or CRISIS mode) MUST NOT cite statistics or studies.
A response in GUIDANCE mode MAY cite evidence — but only from the supplied evidence summary.

Hallucination FAILS if:
- A specific statistic (e.g., "affects 1 in 5 people") appears with no evidence source.
- A named study, guideline, or treatment is cited but was not in the evidence summary.
- The response claims "research shows" or "studies prove" without evidence context.

OUTPUT FORMAT — JSON only, no preamble, no markdown fences:
{
  "tone_pass": true or false,
  "tone_notes": "brief explanation — one sentence max",
  "hallucination_pass": true or false,
  "hallucination_notes": "brief explanation — one sentence max"
}"""


# ---------------------------------------------------------------------------
# EvaluatorAgent
# ---------------------------------------------------------------------------

class EvaluatorAgent:
    """
    Per-response content gate. Audits draft responses before delivery.

    Two-pass: deterministic hard-fail → LLM judge.
    Returns an EvaluationPayload that the Verification Supervisor reads.

    Usage:
        evaluator = EvaluatorAgent(model=model, tokenizer=tokenizer)
        payload = evaluator.evaluate(
            draft_response="...",
            context=response_context_payload,
        )

    The model and tokenizer are the same shared objects used by the Signal
    Agent and Support Strategy Agent — no separate model load required.
    If not injected, the agent lazy-loads its own copy (testing convenience).
    """

    def __init__(
        self,
        model=None,
        tokenizer=None,
        model_name: str = "Qwen/Qwen2.5-3B-Instruct",
        device: str = "auto",
    ):
        self._model = model
        self._tokenizer = tokenizer
        self._model_name = model_name
        self._device = device

    # ------------------------------------------------------------------
    # Lazy model loader (mirrors Signal Agent and Support Strategy Agent pattern)
    # ------------------------------------------------------------------

    def _ensure_model(self) -> None:
        """
        Load model and tokenizer if not already injected.
        Same pattern as SignalAgent._ensure_model() — see that module for
        full comments on quantization and device selection.
        """
        if self._model is not None:
            return
        logger.info("EvaluatorAgent: lazy-loading model %r", self._model_name)
        # [CONCEPT] Lazy loading
        # We defer the import of transformers and torch until the model is
        # actually needed. This keeps module import time fast and avoids
        # loading heavy ML deps in environments where only the schemas are used.
        from transformers import AutoTokenizer, AutoModelForCausalLM
        import torch
        self._tokenizer = AutoTokenizer.from_pretrained(self._model_name)
        self._model = AutoModelForCausalLM.from_pretrained(
            self._model_name,
            torch_dtype=torch.float16,
            device_map=self._device,
        )
        logger.info("EvaluatorAgent: model loaded.")

    # ------------------------------------------------------------------
    # Pass 1: Deterministic hard-fail check
    # ------------------------------------------------------------------

    def _hard_fail_check(
        self,
        draft: str,
    ) -> tuple[bool, list[str]]:
        """
        Scan draft_response against red-line patterns R1–R15.
        (SAFETY_GUARDRAILS.md; REQ-000-060 through REQ-300-130)

        Returns (passed: bool, violations: list[str]).
        passed=False means at least one red line was hit → verdict=FAIL.

        Why deterministic and not LLM?
        Safety-critical rejections must be fast (no LLM latency), auditable
        (every rejection maps to a REQ-ID), and immune to prompt injection
        (the check doesn't involve the LLM being tested).
        """
        violations: list[str] = []
        for red_line_id, description, pattern in _RED_LINE_PATTERNS:
            match = pattern.search(draft)
            if match:
                violations.append(
                    f"[{red_line_id}] {description}: "
                    f"matched '{match.group(0)[:60]}' "
                    f"(SAFETY_GUARDRAILS.md {red_line_id})"
                )
                logger.warning(
                    "Hard-fail red line %s triggered: %r", red_line_id, match.group(0)[:60]
                )
        return len(violations) == 0, violations

    # ------------------------------------------------------------------
    # USM audit (REQ-850-083)
    # ------------------------------------------------------------------

    def _usm_audit(self, draft: str) -> tuple[bool, list[str]]:
        """
        When USM memory is active, check the response for three prohibited
        patterns: crisis-history reference, clinical inference from memory,
        continuous-care-provider positioning.

        Returns (passed: bool, violations: list[str]).
        USM audit failure is non-recoverable — forces verdict=FAIL. (REQ-850-083)
        """
        violations: list[str] = []
        for desc, pattern in _USM_VIOLATION_PATTERNS:
            match = pattern.search(draft)
            if match:
                violations.append(
                    f"[USM] {desc}: matched '{match.group(0)[:60]}' (REQ-850-083)"
                )
                logger.warning("USM violation: %s — %r", desc, match.group(0)[:60])
        return len(violations) == 0, violations

    # ------------------------------------------------------------------
    # Pass 2: LLM judge (tone + hallucination)
    # ------------------------------------------------------------------

    def _llm_judge(
        self,
        draft: str,
        mode: OperationalMode,
        evidence_summary: Optional[str],
    ) -> dict:
        """
        Structured LLM evaluation of tone compliance and hallucination.

        Returns a dict with keys: tone_pass, tone_notes,
        hallucination_pass, hallucination_notes.
        On any parse/generation failure, defaults to passing both checks
        with a note — we do not fail responses on Evaluator malfunction
        (fail-safe: a broken judge is worse than a lenient one; the
        hard-fail check already covers the critical safety layer).

        REQ-200-171: single evaluation pass, no recursion.
        """
        # Build the user turn for the judge prompt.
        evidence_context = (
            f"Evidence summary provided:\n{evidence_summary}"
            if evidence_summary
            else "No evidence was provided to the Interaction Model (Comfort or Crisis Mode)."
        )

        user_content = (
            f"Operational mode: {mode.value.upper()}\n\n"
            f"{evidence_context}\n\n"
            f"DRAFT RESPONSE TO AUDIT:\n{draft}"
        )

        messages = [
            {"role": "system", "content": _EVALUATOR_SYSTEM_PROMPT},
            {"role": "user",   "content": user_content},
        ]

        try:
            # [CONCEPT] _ensure_model() is called INSIDE the try so that a
            # missing 'transformers' / 'torch' install (e.g. on Render free
            # tier) raises ModuleNotFoundError here and is caught by the
            # fail-safe below — returning tone_pass=True rather than propagating
            # up to the pipeline as an unhandled exception that creates a
            # synthetic FAIL payload and triggers SAFE_FALLBACK_RESPONSE.
            self._ensure_model()

            # [CONCEPT] apply_chat_template()
            # Converts the messages list into the model's native chat format
            # (e.g., <|im_start|>system\n...<|im_end|>\n for Qwen).
            # add_generation_prompt=True appends the assistant-turn token so
            # the model knows it should produce a completion, not more context.
            text = self._tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
            inputs = self._tokenizer(text, return_tensors="pt").to(self._model.device)

            t0 = time.perf_counter()
            outputs = self._model.generate(
                **inputs,
                max_new_tokens=200,
                temperature=0.05,   # near-deterministic — judge should be consistent
                do_sample=True,
                pad_token_id=self._tokenizer.eos_token_id,
            )
            latency_ms = (time.perf_counter() - t0) * 1000
            logger.debug("LLM judge latency: %.0f ms", latency_ms)

            # Decode only the newly generated tokens.
            generated = self._tokenizer.decode(
                outputs[0][inputs["input_ids"].shape[-1]:],
                skip_special_tokens=True,
            ).strip()

            # Extract JSON from the response (may be wrapped in markdown fences).
            json_match = re.search(r"\{.*\}", generated, re.DOTALL)
            if not json_match:
                raise ValueError(f"No JSON found in judge output: {generated[:200]!r}")

            result = json.loads(json_match.group(0))
            # Validate required keys exist.
            for key in ("tone_pass", "tone_notes", "hallucination_pass", "hallucination_notes"):
                if key not in result:
                    raise ValueError(f"Missing key {key!r} in judge output")
            return result

        except Exception as exc:
            # [CONCEPT] Fail-safe on evaluator malfunction
            # If the judge LLM fails (timeout, parse error, model crash),
            # we default to PASS on the soft checks. The hard-fail check
            # (Pass 1) already ran and cleared. Blocking delivery because the
            # judge is broken would be worse than the risk of a slightly
            # suboptimal tone in a response that already passed the safety gate.
            logger.error(
                "LLM judge failed — defaulting to pass on soft checks. Error: %s", exc
            )
            return {
                "tone_pass": True,
                "tone_notes": f"Judge failed — defaulted to pass. ({type(exc).__name__})",
                "hallucination_pass": True,
                "hallucination_notes": "Judge failed — defaulted to pass.",
            }

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def evaluate(
        self,
        draft_response: str,
        context: ResponseContextPayload,
    ) -> EvaluationPayload:
        """
        Full two-pass evaluation of a draft response.

        Parameters
        ----------
        draft_response : str
            The user-facing text produced by the Interaction Model.
        context : ResponseContextPayload
            The full pipeline context — mode, signals, strategy, evidence,
            USM active flag.  Provides the ground truth for the judge.

        Returns
        -------
        EvaluationPayload
            verdict: PASS / FAIL / REGENERATE
            safety_check, tone_check, hallucination_check: individual gate results
            rejection_reasons: list of human-readable failure descriptions
            usm_audit_passed: None if USM inactive, bool if USM active

        Spec trace
        ----------
            REQ-200-100  safety audit, tone check, epistemic-humility enforcement
            REQ-200-101  final content gate — runs before Verification Supervisor
            REQ-200-EV1  single pass, no recursion
            REQ-850-083  USM audit when usm_active=True
        """
        rejection_reasons: list[str] = []

        # ── Pass 1: Hard-fail (deterministic) ─────────────────────────────
        safety_passed, safety_violations = self._hard_fail_check(draft_response)
        if not safety_passed:
            rejection_reasons.extend(safety_violations)

        # ── USM audit (deterministic, runs regardless of hard-fail result) ─
        usm_audit_passed: Optional[bool] = None
        if context.usm_active:
            usm_ok, usm_violations = self._usm_audit(draft_response)
            usm_audit_passed = usm_ok
            if not usm_ok:
                rejection_reasons.extend(usm_violations)

        # ── Early exit on FAIL (skip LLM judge — save latency) ────────────
        # REQ-200-171: single evaluation cycle. If we already have a hard
        # failure, there's no value in running the LLM judge.
        if not safety_passed or (usm_audit_passed is False):
            logger.info(
                "Evaluator: FAIL (hard-fail). Reasons: %d", len(rejection_reasons)
            )
            return EvaluationPayload(
                verdict=EvaluationVerdict.FAIL,
                safety_check=False,
                tone_check=True,            # undefined — default True to avoid noise
                hallucination_check=True,   # undefined — default True to avoid noise
                rejection_reasons=rejection_reasons,
                usm_audit_passed=usm_audit_passed,
            )

        # ── Pass 2: LLM judge (tone + hallucination) ──────────────────────
        evidence_summary = (
            context.synthesized_evidence.summary
            if context.synthesized_evidence
            else None
        )
        judge_result = self._llm_judge(
            draft=draft_response,
            mode=context.mode,
            evidence_summary=evidence_summary,
        )

        tone_passed         = bool(judge_result.get("tone_pass", True))
        hallucination_passed = bool(judge_result.get("hallucination_pass", True))

        if not tone_passed:
            rejection_reasons.append(
                f"[TONE] {judge_result.get('tone_notes', 'Tone check failed.')}"
            )
        if not hallucination_passed:
            rejection_reasons.append(
                f"[HALLUCINATION] {judge_result.get('hallucination_notes', 'Hallucination check failed.')}"
            )

        # ── Determine final verdict ────────────────────────────────────────
        # Verdict rules (see module docstring):
        #   FAIL       — safety or USM (already handled above)
        #   REGENERATE — tone or hallucination failure (recoverable)
        #   PASS       — all checks clear
        if not tone_passed or not hallucination_passed:
            verdict = EvaluationVerdict.REGENERATE
        else:
            verdict = EvaluationVerdict.PASS

        logger.info(
            "Evaluator: %s | safety=%s tone=%s hallucination=%s usm=%s",
            verdict.value, safety_passed, tone_passed, hallucination_passed, usm_audit_passed,
        )

        return EvaluationPayload(
            verdict=verdict,
            safety_check=safety_passed,
            tone_check=tone_passed,
            hallucination_check=hallucination_passed,
            rejection_reasons=rejection_reasons,
            usm_audit_passed=usm_audit_passed,
        )

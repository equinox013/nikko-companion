# agents/

This directory contains every specialist agent that makes up the NIKKO pipeline. Each agent is a self-contained Python module with a single public interface. Agents communicate exclusively through validated Pydantic schemas defined in `docs/schemas/acp_schemas.py` — no agent reads another agent's internal state directly.

The pipeline calls agents in strict SPEC-700 sequence. No agent can be skipped, reordered, or called in parallel within a single turn. The one exception is Crisis Mode, which bypasses the Support Strategy Agent and Evidence pipeline entirely.

---

## Executive Summary

| Agent | Role | LLM? | Authority |
|-------|------|------|-----------|
| `scope_classifier.py` | Intercepts off-topic messages before any other agent runs | No — rule-based | Highest — final OUT_OF_SCOPE decisions are irreversible |
| `signal_agent.py` | Detects psychological distress signals in user text | Yes — Qwen3-4B (prod) | Low — output is read-only by downstream agents |
| `router.py` | Assigns operational mode (Comfort / Guidance / Crisis) | No — deterministic logic | Maximum — sole mode authority |
| `support_strategy_agent.py` | Translates mode + signals into tone/framing instructions for the LLM | Yes — Qwen3-4B (prod) | Medium — produces guidance, never user-facing text |
| `synthesizer_agent.py` | Ranks and scores evidence retrieved from external sources | No — deterministic | Medium — evidence is immutable once synthesized |
| `evaluator_agent.py` | Content gate: rejects drafts that violate safety red lines | Optional LLM (ADP-C) | High — can block or request regeneration of any response |
| `verification_supervisor.py` | Structural gate: checks pipeline integrity, not content | No — deterministic | High — can trigger safe fallback |

---

## Component Breakdown

### `scope_classifier.py` — Scope Classifier (STEP 0)

**Overview:** The pipeline's outer gate. Runs before every other agent. If a message is clearly outside Nikko's emotional-wellbeing domain, this agent terminates the pipeline immediately and returns a static warm-redirect response. Ambiguous inputs are passed through — the classifier errs toward inclusion.

**Technical breakdown:**

- **Algorithm:** Weighted keyword scorer. Two independent scorers run in parallel — an in-scope scorer (mental-health vocabulary, emotional language, help-seeking phrasing) and an out-of-scope scorer (technical, commercial, medical-diagnosis, legal, news vocabulary). Net score = in-scope score minus out-of-scope score. Negative net score → OUT_OF_SCOPE if the out-of-scope score also clears a minimum confidence threshold.
- **Decision types:** `IN_SCOPE`, `AMBIGUOUS`, `OUT_OF_SCOPE`. Only `OUT_OF_SCOPE` terminates the pipeline; `AMBIGUOUS` is treated identically to `IN_SCOPE` by the orchestrator.
- **Why rule-based?** Sub-millisecond latency, fully deterministic, zero model download. Phase 4 will produce a labelled dataset that enables a DistilBERT-class classifier. The swap-in point is the private `_score_rule_based()` method — the public interface does not change.
- **Warm redirect text** is a static string (`WARM_REDIRECT`) — it is never LLM-generated and must not vary per user.
- **Spec refs:** SPEC-200 §5.0, REQ-200-SC1 through SC6, REQ-000-SC1 through SC4, REQ-700-SC1 through SC3.

---

### `signal_agent.py` — Psychological Signal Agent (STEP 2)

**Overview:** First LLM call in the pipeline. Receives a sanitized user message and returns a structured `SignalPayload` describing detected distress signals. The Router uses this payload — and nothing else — to assign mode.

**Technical breakdown:**

- **Input:** sanitized user text + optional conversation history (JSON string).
- **Output:** `SignalPayload` — validated Pydantic model containing `distress_level` (LOW/MODERATE/HIGH/CRISIS), `confidence` (float 0–1), `emotional_states`, `cognitive_patterns`, `behavioral_indicators`, `risk_indicators`, and `support_needs`.
- **LLM strategy:** Prompted to return a JSON object matching the `SignalPayload` schema. A regex-based JSON extractor handles models that wrap JSON in prose. If parsing fails, a LOW-distress fallback payload is returned rather than crashing.
- **Output immutability:** Once `analyze()` returns, no downstream agent may alter the payload (REQ-700-032). Enforcement is by convention.
- **Phase 3 model:** Qwen2.5-3B-Instruct (zero-shot, no quantization, fits in 8 GB VRAM).
- **Production model (Director-approved 2026-05-14, revised 2026-05-16):** Qwen3-4B base (ADP-A — no fine-tuning; zero-shot quality sufficient for MVP) + Gemma-2-2b-it (ADP-B safety LoRA, ADP-C evaluator LoRA) via PEFT `load_adapter()`. Phi-3.5-mini-instruct was an intermediate ADP-A candidate; it was discontinued at the same VRAM ceiling as Mistral-7B. Class interface unchanged. Mistral-7B retired (archived `agents/mistral-7b/`).
- **Spec refs:** SPEC-100, SPEC-200 §5.2, REQ-200-050 through REQ-200-053.

---

### `router.py` — Router / Traffic Controller (STEP 3)

**Overview:** The pipeline's sole mode authority. Receives the `SignalPayload` and applies deterministic rules to assign exactly one `OperationalMode`. No LLM is involved — every decision traces to an explicit rule in SPEC-200 §6.

**Technical breakdown:**

- **Decision logic (priority order):**
  1. `confidence < 0.40` → COMFORT (low-signal safety net, REQ-000-F01).
  2. `distress_level == CRISIS` → CRISIS (safety override, REQ-200-042).
  3. `support_needs` contains any of `{psychoeducation, normalization, reflective_exploration, encouragement_external_support}` AND `distress_level >= MODERATE` → GUIDANCE.
  4. Otherwise → COMFORT.
- **Output:** `RouterDecision` — validated Pydantic model with `mode`, `routing_rationale`, `confidence`, and `crisis_override` (bool; must be True iff mode is CRISIS, enforced by a Pydantic validator).
- **Why no LLM?** Mode assignment is a safety-critical decision. Deterministic rules give full auditability and zero stochastic risk of a CRISIS-level user being routed to COMFORT.
- **Spec refs:** SPEC-200 §5.1, §6, REQ-200-040 through REQ-200-042, REQ-200-120 through REQ-200-132.

---

### `support_strategy_agent.py` — Support Strategy Agent (STEP 4 / bypassed in CRISIS)

**Overview:** Second LLM call. Translates the Router's mode and the Signal Agent's payload into concrete communication guidance: tone, framing strategy, and response constraints. This agent never generates user-facing text and never accesses evidence sources.

**Technical breakdown:**

- **Input:** `RouterDecision` + `SignalPayload`.
- **Output:** `StrategyPayload` — validated Pydantic model containing `tone_guidance`, `framing_strategy`, `response_constraints`, and `distress_acknowledgement`.
- **Crisis bypass:** When mode is CRISIS, the pipeline calls `crisis_bypass()` instead of `strategize()`. This returns a fixed `StrategyPayload` with pre-authored crisis guidance — no LLM call is made in Crisis Mode.
- **LLM strategy:** Same JSON-extraction pattern as Signal Agent. Temperature is 0.15 (slightly higher than Signal Agent — mild variation in framing phrasing is acceptable).
- **Model sharing:** The pipeline passes a single loaded model instance to both Signal Agent and Strategy Agent to avoid loading the model twice.
- **Spec refs:** SPEC-200 §5.3, REQ-200-060 through REQ-200-062.

---

### `synthesizer_agent.py` — Evidence Synthesizer Agent (STEP 7 — GUIDANCE only)

**Overview:** Receives a list of `EvidencePayload` objects (one per retrieval adapter that ran) and produces a single `SynthesizedEvidence` object: ranked, scored, and citation-ready. Runs only in Guidance Mode.

**Technical breakdown:**

- **Input:** `List[EvidencePayload]` from the retrieval adapters.
- **Output:** `SynthesizedEvidence` — containing `summary_text`, `citations`, `overall_confidence`, `source_tiers_used`, and `grey_literature_flag`.
- **Ranking algorithm:** Evidence items are sorted by a computed quality score:
  - Peer-reviewed (`EvidenceTier.PEER_REVIEWED`) within the last 5 years → base confidence 0.90.
  - Grey literature only → base confidence 0.65, additional 0.15 penalty if no peer-reviewed items exist.
  - Source disagreement penalty: 0.10 reduction when keyword overlap between two abstracts is low (G-EVIDENCE-01 tiebreak rule).
- **Why deterministic (no LLM)?** Auditability — every confidence delta maps to a named REQ ID. No extra LLM round-trip on the Guidance path. An LLM prose-synthesis step can be added as a post-processing layer later without changing the ranking logic.
- **Spec refs:** SPEC-200 §5.5, REQ-200-080, REQ-200-081, REQ-200-ER3, REQ-200-126 through REQ-200-129.

---

### `evaluator_agent.py` — Evaluator Agent (STEP 11 — all non-crisis responses)

**Overview:** The pipeline's content gate. Receives the draft response from the Interaction Model and runs two sequential passes. A single pass failure blocks delivery.

**Technical breakdown:**

- **Pass 1 — Deterministic hard-fail (no LLM):** Scans the draft against 15 regex-based red lines (R1–R15) from `SAFETY_GUARDRAILS.md`. Patterns cover diagnostic labelling (R1), treatment recommendations (R2–R5), self-harm method disclosure (R6), false empathy simulation (R7–R9), clinical authority framing (R10–R12), and emotional manipulation (R13–R15). A single match → `verdict=FAIL` immediately. This pass is intentionally fast and deterministic — safety-critical rejections must not depend on LLM judgment.
- **Pass 2 — LLM judge (ADP-C, optional):** Evaluates tone compliance and hallucination heuristics (does the response cite sources not present in the synthesized evidence?). Failure → `verdict=REGENERATE` (recoverable — the orchestrator re-runs the full pipeline up to `MAX_REGEN_ATTEMPTS = 2` times).
- **USM audit (when `usm_active=True`):** Extra deterministic check ensuring the response does not reference crisis-state history from memory or make clinical inferences from stored data (REQ-850-083). USM failure → `verdict=FAIL` (non-recoverable).
- **Verdicts:** `PASS`, `FAIL` (non-recoverable, triggers safe fallback), `REGENERATE` (recoverable, triggers re-run).
- **Phase 3:** Pass 2 requires the `transformers` library. The pipeline accepts an injectable `evaluator` so notebooks substitute a `MockEvaluator` in environments without GPU.
- **Spec refs:** SPEC-200 §5.7, REQ-200-100, REQ-200-101, REQ-200-EV1, SAFETY_GUARDRAILS.md R1–R15.

---

### `verification_supervisor.py` — Verification Supervisor (STEP 12)

**Overview:** The pipeline's structural gate. Runs after the Evaluator. Checks that the pipeline executed correctly — correct agents ran in the correct sequence for the assigned mode — not that the response content is safe (that is the Evaluator's job).

**Technical breakdown:**

- **Seven checks (C1–C7):**
  - **C1** — Evaluator gate: VS must only run if the Evaluator emitted `PASS`.
  - **C2** — Scope routing integrity: `OUT_OF_SCOPE` inputs must not reach this step.
  - **C3** — Mode-distress alignment: `OperationalMode` must match `DistressLevel` (e.g., CRISIS distress in COMFORT mode → fail).
  - **C4** — Crisis resources: `CRISIS` distress requires `crisis_resources` to be populated with the four Australian baseline resources.
  - **C5** — Evidence pipeline: `GUIDANCE` mode requires `synthesized_evidence` to be present.
  - **C6** — Agent contamination: evidence must be absent in Comfort; crisis resources must be absent in Guidance.
  - **C7** — Loop limit: `regen_count` must be less than `MAX_REGEN_ATTEMPTS (2)`.
- **Crisis Mode:** C5 and C6 are suspended when `distress_level == CRISIS` (REQ-700-VS1). C1, C2, C3, C4, C7 remain active.
- **On failure:** Returns a `VerificationResult` with `passed=False` and a `SAFE_FALLBACK_RESPONSE` — a fixed canned string that is guaranteed safe regardless of pipeline state.
- **Why deterministic?** Same rationale as the Synthesizer: every check maps to a named REQ ID. The pipeline already paid for two LLM calls; adding a third for structural checking would be redundant.
- **Spec refs:** SPEC-200 §5.6, SPEC-700 §7, REQ-200-090, REQ-200-091, REQ-200-VS1, REQ-700-090 through REQ-700-092, REQ-700-VS1.

---

## Shared Conventions

- **Schema-first:** every inter-agent payload is a Pydantic v2 `BaseModel` from `docs/schemas/acp_schemas.py`. No agent defines its own data classes.
- **Lazy model loading:** `torch` and `transformers` are only imported inside model-loading methods, not at module level. Importing an agent module is always fast and does not require a GPU.
- **Inline `[CONCEPT]` comments:** blocks above non-obvious patterns (Protocol injection, Pydantic validators, lazy imports) explain the pattern in plain language for readers new to the specific idiom.
- **REQ-ID traceability:** every normative behaviour in agent code carries the `REQ-XXX-NNN` ID of the spec requirement it implements.

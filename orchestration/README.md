# orchestration/

This directory contains the pipeline orchestrator — the single entry point for every user interaction in the NIKKO system. It wires together all agents from `agents/` and `retrieval/` into the execution sequence defined by SPEC-700 and enforces all hard constraints around ordering, failure handling, and regeneration.

If you are forking this repo, this is the file you read to understand how everything fits together.

---

## Executive Summary

The orchestrator owns three concerns that no individual agent handles:

1. **Execution order** — agents run in strict SPEC-700 sequence. Nothing runs in parallel within a turn.
2. **Mode branching** — the Router's decision determines which agents run next. Comfort, Guidance, and Crisis paths are structurally different.
3. **Failure handling** — evaluator failures, verification failures, and regeneration loops all terminate here with a defined outcome (safe fallback or re-run).

---

## Component Breakdown

### `pipeline.py` — NikkoPipeline

**Overview:** Implements the complete SPEC-700 execution contract in a single class. Takes a user message in, returns a `PipelineResult` out. Everything in between — scope classification, signal detection, routing, evidence retrieval, strategy, draft generation, evaluation, verification, trace capture — is orchestrated here.

**Technical breakdown:**

#### Constructor and dependency injection

```python
NikkoPipeline(
    draft_generator=None,    # DraftGeneratorProtocol — the Interaction Model (LLM)
    scope_classifier=None,   # ScopeClassifier or stub
    signal_agent=None,       # SignalAgent or stub
    strategy_agent=None,     # SupportStrategyAgent or stub
    evaluator=None,          # EvaluatorAgent or MockEvaluator
)
```

All five dependencies are injectable. If `None`, the pipeline falls back to in-file stubs. This design makes the pipeline fully testable without a GPU and allows Phase 4 adapters to be swapped in without touching the orchestration code. The `DraftGeneratorProtocol` is a Python structural Protocol (PEP 544) — any class that implements `generate(context: ResponseContextPayload) -> str` satisfies it without explicit inheritance.

#### Execution sequence (SPEC-700 STEP 0 → STEP 15)

| Step | Method | What happens |
|------|--------|-------------|
| STEP 0 | `_step0_scope()` | Scope Classifier runs. `OUT_OF_SCOPE` → immediate return with warm redirect, pipeline stops. |
| STEP 1 | `_step1_sanitize()` | Input sanitizer strips PII-adjacent patterns, control characters, and oversized inputs. |
| STEP 2 | `_step2_signal()` | Signal Agent analyzes sanitized text, returns `SignalPayload`. |
| STEP 3 | `_step3_route()` | Router assigns mode. If Router raises an exception, mode defaults to COMFORT (REQ-700-123). |
| STEPs 4–8 | `_steps4_7_guidance_evidence()` | GUIDANCE ONLY: retrieval adapters run (PubMed first, then WebSearch), results passed to Synthesizer. If all retrievals return 0 items, `synthesized_evidence` is None (VS will catch this via C5). |
| STEP 4 | _(within above)_ | Support Strategy Agent runs for Comfort + Guidance. Bypassed in Crisis (static strategy injected via `crisis_bypass()`). |
| STEP 10 | `_step10_draft()` | `ResponseContextPayload` assembled from all prior outputs. `draft_generator.generate()` called. |
| STEP 11 | `_step11_evaluate()` | Evaluator Agent checks the draft. `FAIL` → safe fallback. `REGENERATE` → recursive `self.run()` up to `MAX_REGEN_ATTEMPTS`. `PASS` → continue. |
| STEP 12 | `_step12_verify()` | Verification Supervisor checks structural integrity. Failure → safe fallback. |
| STEP 13 | `_step13_assemble()` | Final `PipelineResult` assembled. Crisis resources injected if mode is CRISIS. |
| STEP 15 | `_step15_trace()` | `PipelineTrace` finalised with timing, execution path, and all intermediate outputs. |

#### Crisis Mode path

When the Router assigns CRISIS:

- Support Strategy Agent is bypassed; a static crisis strategy is injected directly.
- Evidence retrieval (STEPs 4–8) is skipped entirely.
- Four Australian crisis resources (Lifeline 13 11 14, Beyond Blue 1300 22 4636, 13YARN 13 92 76, Emergency 000) are injected into `PipelineResult.crisis_resources` from `BASELINE_CRISIS_RESOURCES`.
- VS checks C5 (evidence pipeline) and C6 (contamination) are suspended in Crisis Mode.

#### Regeneration loop

When the Evaluator returns `REGENERATE`, the pipeline calls `self.run()` recursively with `_attempt` incremented. The loop is hard-capped at `MAX_REGEN_ATTEMPTS = 2` (REQ-200-170). On exhaustion, `_handle_evaluator_failure()` returns the safe fallback response.

#### PipelineTrace (REQ-700-110)

Every run produces a `PipelineTrace` dataclass capturing:

```python
@dataclass
class PipelineTrace:
    request_id: str           # UUID per turn
    session_id: str           # UUID per session
    timestamp: str            # ISO-8601 UTC
    execution_path: list      # names of agents/steps that ran
    router_decision: str      # mode name
    distress_level: str       # LOW/MODERATE/HIGH/CRISIS
    evidence_used: list       # citation titles
    adapter_configuration: list  # retrieval adapters that ran
    evaluator_verdict: str    # PASS/FAIL/REGENERATE
    vs_passed: bool
    safe_fallback_used: bool
    latency_ms: float
```

Traces are session-scoped and ephemeral (REQ-700-LOG1). They are never written to persistent storage.

#### PipelineResult

The object returned from `NikkoPipeline.run()`:

```python
@dataclass
class PipelineResult:
    response_text: str           # user-facing response
    mode: OperationalMode        # COMFORT / GUIDANCE / CRISIS / OUT_OF_SCOPE
    out_of_scope: bool
    safe_fallback_used: bool
    evaluation: EvaluationPayload | None
    verification: VerificationResult | None
    trace: PipelineTrace
    crisis_resources: list[CrisisResource]  # populated in CRISIS mode only
```

#### Hard constraints enforced

- `REQ-700-130` — No parallel chains: agents run sequentially, one per step.
- `REQ-700-131` — No bypass: Router and Evaluator are always called (except in Out-of-Scope early exit).
- `REQ-700-132` — No cross-mode mixing: once the Router assigns a mode, it applies for the entire turn.
- `REQ-700-133` — The LLM (Interaction Model / `draft_generator`) receives only the assembled `ResponseContextPayload` — it never sees raw retrieval results or intermediate agent outputs directly.
- `REQ-200-170` — Regeneration loop capped at `MAX_REGEN_ATTEMPTS = 2`.
- `REQ-700-LOG1` — All trace data is ephemeral.

---

### `__init__.py`

Exports `NikkoPipeline`, `PipelineResult`, and `PipelineTrace` as the public surface of the `orchestration` package. Import from here, not from `pipeline.py` directly.

```python
from orchestration import NikkoPipeline, PipelineResult, PipelineTrace
```

---

## Forking Notes

If you are adapting the pipeline for a different domain:

- **Swap the draft generator:** implement `DraftGeneratorProtocol.generate(context: ResponseContextPayload) -> str` and inject it at construction. The pipeline does not care what model or API backs it.
- **Add retrieval adapters:** extend `retrieval/` (see `retrieval/README.md`) and add them to `ADAPTER_PRIORITY_ORDER` in `retrieval/__init__.py`.
- **Change routing rules:** edit `agents/router.py` — the routing thresholds and guidance-intent detection are all in named constants at the top of the file.
- **Change safety red lines:** edit the `_RED_LINE_PATTERNS` table in `agents/evaluator_agent.py`.
- **Change VS checks:** individual check methods (`_c1_` through `_c7_`) in `agents/verification_supervisor.py` are independently editable.

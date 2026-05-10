# Nikko — Evidence-Grounded Wellbeing Assistant

Nikko is a safety-aligned, evidence-grounded LLM ecosystem designed to function as a compassionate digital confidant. It listens, validates, and surfaces reliable information — but it never diagnoses, never prescribes, and always defers to human care when it matters most.

> *Nikko illuminates possible paths. The user must always walk toward human support themselves.*

---

## What Nikko Is

Nikko is not a chatbot. It is a **multi-agent pipeline** in which every user message passes through a sequence of specialist agents before a response is generated. No single agent has the whole picture — each one does one job, checks its own constraints, and hands off to the next. The LLM that generates the final response never receives raw user input, never accesses evidence directly, and never decides whether the response is safe. Other agents handle those concerns before and after the model runs.

This architecture exists because mental-health-adjacent AI carries real risk. A single unconstrained LLM can confidently say the wrong thing. A pipeline with hard-coded routing rules, a regex-based safety gate, and a structural integrity check is much harder to break.

---

## How the Agents and LLM Work Together

A user message flows through ten steps before a response is returned. Here is what happens at each one.

### STEP 0 — Scope Classification

The message hits the **Scope Classifier** first. This agent uses a weighted keyword scorer — no LLM, no model — to decide whether the message falls within Nikko's domain of emotional wellbeing and mental health support. If it clearly does not (code questions, legal advice, general knowledge), the pipeline stops immediately and returns a static warm-redirect response. If the message is ambiguous, it is passed through — the classifier always errs toward inclusion.

### STEP 1 — Input Sanitisation

The message is stripped of patterns that could leak PII, inject control characters, or exceed safe input lengths. The sanitised text is what every downstream agent sees.

### STEP 2 — Psychological Signal Detection

The **Signal Agent** makes the first LLM call. It receives the sanitised text and returns a structured `SignalPayload` — a validated data object describing detected distress level (LOW / MODERATE / HIGH / CRISIS), emotional states, cognitive patterns, risk indicators, and what kind of support the user seems to need. This payload is immutable: no downstream agent can alter it.

The Signal Agent currently runs on Qwen2.5-3B-Instruct in zero-shot mode. Phase 4 will replace this with a fine-tuned Mistral-7B with the ADP-A (Empathy) and ADP-B (Safety) adapters loaded.

### STEP 3 — Routing

The **Router** reads the `SignalPayload` and assigns exactly one operational mode for this turn. It uses deterministic rules — no LLM — and its decision is the single source of truth for everything that follows.

- **COMFORT** — validation, active listening, no information injection.
- **GUIDANCE** — calm, evidence-grounded information for users seeking understanding.
- **CRISIS** — immediate safety priority; evidence pipeline is skipped; crisis resources are injected; Safety adapter only.

### STEPs 4–8 — Evidence Retrieval and Synthesis (Guidance Mode only)

If the Router assigned GUIDANCE, the **PubMed Adapter** queries NCBI's research database for peer-reviewed abstracts, followed by the **Web Search Adapter** which searches five sanctioned Australian health authority domains (Healthdirect, Better Health Channel, WHO, Beyond Blue, Black Dog Institute). Results are cached on disk to avoid repeat network calls.

The **Evidence Synthesizer** then ranks all retrieved items by quality — peer-reviewed content within the last five years scores highest — and produces a single `SynthesizedEvidence` object with a confidence score and citation list. This is all deterministic: no LLM is involved in ranking or scoring evidence.

### STEP 4 (parallel) — Support Strategy

The **Support Strategy Agent** makes the second LLM call. It receives the Router's mode decision and the Signal Agent's payload and returns communication guidance for the Interaction Model: tone, framing strategy, and constraints. It never generates user-facing text. In Crisis Mode this step is bypassed and a fixed crisis instruction set is injected instead.

### STEP 10 — Draft Generation

The **Interaction Model** (the main LLM) now runs. It receives a `ResponseContextPayload` — a single assembled object containing the strategy guidance, synthesised evidence (if any), and the mode. It has no access to raw retrieval results, intermediate agent outputs, or conversation history beyond what the payload explicitly contains.

In Phase 3 this is a stub. Phase 4 will wire in a fine-tuned Mistral-7B with the appropriate adapter combination (Empathy + Safety for Comfort/Guidance; Safety-only for Crisis).

### STEP 11 — Evaluation

The **Evaluator Agent** is the content gate. It runs two passes:

**Pass 1 (deterministic):** fifteen regex-based red lines are checked against the draft. These catch diagnostic labelling, treatment recommendations, clinical authority framing, and self-harm method disclosure. A single match means the response is blocked immediately — no LLM involved, no recovery.

**Pass 2 (LLM judge, ADP-C):** a separate evaluator model checks tone compliance and hallucination indicators (did the response cite sources not in the synthesised evidence?). A failure here is recoverable — the pipeline re-runs the full draft generation up to two times before falling back to a safe canned response.

### STEP 12 — Verification Supervisor

The **Verification Supervisor** is the structural gate. It checks that the pipeline ran correctly for the assigned mode — right agents in the right order, crisis resources present when they should be, evidence present in Guidance and absent in Comfort. It does not audit the response content; that is the Evaluator's job. A structural failure triggers a safe fallback response.

### STEP 13 — Assembly

The final `PipelineResult` is assembled: response text, mode, crisis resources (if any), evaluation result, verification result, and a full execution trace.

### STEP 15 — Trace Capture

A `PipelineTrace` records every agent that ran, the router decision, distress level, evidence used, latency, and whether a safe fallback was used. Traces are session-scoped and ephemeral — they are never written to persistent storage.

---

## Repository Structure

```
nikko-companion/
├── docs/
│   ├── specs/          # 8 authoritative specification documents (SPEC-000 through SPEC-700)
│   ├── derived/        # Architecture, agent definitions, safety guardrails, evaluation criteria
│   ├── schemas/        # Pydantic v2 inter-agent data schemas (acp_schemas.py, retrieval_schemas.py)
│   └── GAPS.md         # All open questions and Director rulings (35 gaps — all ratified)
├── agents/             # Seven specialist agents (see agents/README.md)
├── orchestration/      # Pipeline orchestrator (see orchestration/README.md)
├── retrieval/          # PubMed + WebSearch evidence adapters (see retrieval/README.md)
├── notebooks/          # 10 Jupyter notebooks — one per implementation step, all passing
└── web/                # React frontend (Phase 5 — awaits backend API integration)
```

---

## Safety Architecture

Every design decision in Nikko traces to a named requirement in the spec. The key safety properties are:

- **No clinical authority.** The LLM is never trained on medical content. Health information is always fetched from external sources, ranked by quality, and passed through the Synthesizer before the LLM sees it. The LLM cannot "know" medical facts — it can only relay what the retrieval system found.
- **Hard-coded crisis routing.** The Router's CRISIS assignment is a deterministic rule, not an LLM judgment. Once CRISIS is assigned, the evidence pipeline stops, the Empathy adapter is deactivated, and four Australian crisis resources are injected unconditionally.
- **Fifteen safety red lines.** Before any response reaches the user, fifteen regex patterns check for diagnostic language, treatment recommendations, self-harm method disclosure, and clinical authority framing. These are deterministic — they cannot be confused or sweet-talked by the draft LLM.
- **Structural integrity gate.** The Verification Supervisor checks that the pipeline ran correctly, not just that the response sounds safe. A CRISIS distress signal with a COMFORT mode response will be caught here even if the Evaluator passed it.
- **Zero data retention.** No user conversation data enters the training pipeline. This constraint is permanent (REQ-000-P01) and is not overridable by any phase gate or instruction.

---

## Running the Pipeline

```python
from orchestration import NikkoPipeline

pipeline = NikkoPipeline()   # uses stubs for LLM; all deterministic agents are live
result = pipeline.run("I've been feeling really overwhelmed lately.")

print(result.response_text)    # generated response
print(result.mode)             # OperationalMode.COMFORT / GUIDANCE / CRISIS
print(result.trace.execution_path)  # which agents ran
```

For a full walkthrough including edge cases (Crisis Mode, Guidance evidence path, regeneration loop, Verification Supervisor failures), see `notebooks/step10_pipeline.ipynb`.

---

## Governing Principles

Nikko exists to support — not to replace. The full ethical charter is in `docs/specs/SPEC-000-charter.md`. The short version:

- Nikko will not diagnose, prescribe, or plan treatment.
- Nikko will not simulate being a therapist.
- Nikko will not encourage exclusive reliance on itself.
- When risk increases, Nikko increases its encouragement toward human support — it does not increase its own authority.

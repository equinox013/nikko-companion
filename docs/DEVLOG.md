# NIKKO Development Log

> **Purpose:** A running record of what was done each day, decisions made with their justifications, and key learnings taken out of the session.
>
> **Format:** Chronological. Each entry covers: **What we did**, **Decisions & justifications**, **Learnings**.
>
> **Owner:** Director (Nicholas). Maintained by the NIKKO Engineering Collective agent.

---

## 2026-05-09 — Phase 1 & 2 Sign-off

### What we did

- Ingested and parsed `NIKKO-spec.docx` — the original handwritten system specification.
- Extracted 8 authoritative specification documents: `SPEC-000` through `SPEC-700`, each with full `REQ-XXX-NNN` requirement IDs.
- Generated 4 derived synthesis documents: `SYSTEM_ARCHITECTURE.md`, `AGENT_DEFINITIONS.md`, `SAFETY_GUARDRAILS.md`, `EVALUATION_CRITERIA.md`.
- Triaged 32 enumerated gaps in `GAPS.md` — every ambiguity, missing variable, and logical inconsistency found in the source document.
- Director ruled on all 32 gaps in a single session. All 4 🔴 Critical gaps ratified. All 10 🟠 High gaps ratified.
- Phase 1 (Spec Initialization) and Phase 2 (Architectural Contracts) both signed off in the same session.

### Decisions & justifications

| Decision | Justification |
|----------|--------------|
| Australia-only v0 deployment (G-CRISIS-01) | Public internet deployment but only Australian crisis resources exist. Geo-blocking or locale-detection deferred to GA. v0 ships with prominent AU-only disclaimer. |
| Zero data retention — hard charter constraint (G-DATA-01) | Mental-health user input is PII-adjacent. No user conversation data may enter the training pipeline under any circumstances. Session data lives in `sessionStorage` only. |
| Conversation state in-memory only (G-MEMORY-01) | Avoids server-side persistence obligations. Entire conversation history lives in the LLM context window; destroyed on session end. |
| 18+ self-attestation gate (G-AGE-01) | Lowest engineering cost for v0. Online Safety Act AU compliance for a research preview. Path to adapted minor mode reserved for GA. |
| Scope classifier inserted as STEP 0 (G-SCOPE-01) | Prevents off-topic messages from polluting the agent pipeline. Ambiguous messages pass through — only high-confidence non-emotional queries are rejected with a warm redirect. |
| Evaluator → Verification Supervisor order (G-RECON-02) | Evaluator does per-response content gate; VS does system-level structural gate. Content must pass before structure is checked. |
| SFT with rejection sampling for v0 training (G-LOSS-01) | Simplest formulation compatible with the open-license corpus constraint. DPO upgrade path once a preference dataset exists. |

### Learnings

- The source spec had significant internal contradictions — two separate pipeline step orderings, overlapping agent authority levels, and a missing adapter combination for Crisis Mode. These were caught by treating spec extraction as an adversarial audit, not a transcription exercise.
- Spec-first development forces decisions upfront that would otherwise surface as bugs (e.g. what happens when a passive risk indicator appears without explicit crisis language — not addressable in code without a prior policy ruling).
- The gap between "described qualitatively" and "implementable deterministically" is almost always a REQ ID away. Every prose description needed a numeric threshold, a concrete API, or a specific ordering — none of which the source doc provided.

---

## 2026-05-10 — Phase 3: Agent Implementation

### What we did

- Implemented 7 specialist agents in `agents/`: Scope Classifier, Signal Agent, Router, Support Strategy Agent, Evidence Synthesizer, Interaction Model (ADP-A), Evaluator (ADP-C).
- Built orchestration pipeline in `orchestration/`: `NikkoPipeline` class wiring all agents in SPEC-700 execution order.
- Implemented retrieval layer in `retrieval/`: `PubMedAdapter` (NCBI E-utilities) + `WebSearchAdapter` (DuckDuckGo `site:` + BeautifulSoup scraping).
- Built 10 implementation notebooks (`notebooks/step01` through `step10`) walking through each pipeline stage.
- Resolved `bitsandbytes` Windows CUDA DLL issue (G-ENV-01).
- Replaced 3 grey-literature retrieval adapters with a single `WebSearchAdapter` (G-RETRIEVAL-01).
- Phase 3 signed off.

### Decisions & justifications

| Decision | Justification |
|----------|--------------|
| Replaced Healthdirect/BetterHealth/WHO adapters with WebSearchAdapter (G-RETRIEVAL-01) | Healthdirect has no public search API — the assumed endpoint was fabricated. Static JSON corpus for BetterHealth/WHO required manual curation with no update mechanism. WebSearchAdapter with `site:` operator covers all five sanctioned domains with one implementation. |
| `bitsandbytes==0.45.5` over 0.41.1 or 0.43.1 (G-ENV-01) | 0.45.5 has improved Windows CUDA 12.x DLL path discovery. Resolved the `cudart64_12.dll` lookup failure without requiring a full CUDA Toolkit install. |
| Qwen2.5-3B-Instruct retained as Phase 3 dev model | Output quality sufficient for structured JSON agent tasks. Fits 8 GB VRAM without quantization. Used only for development — replaced by fine-tuned adapters in Phase 4. |
| Scope Classifier uses weighted keyword scorer, no LLM | Deterministic gate must not introduce LLM latency or unpredictability. A keyword scorer is fast, auditable, and correct for this binary classification. |

### Learnings

- LLM-agent architectures benefit enormously from making each agent's input and output a typed, validated schema (`SignalPayload`, `ResponseContextPayload`, etc.). This forces you to be explicit about what each agent actually needs vs. what it has access to — and prevents the most common failure mode where the LLM quietly uses context it shouldn't have.
- The Router being deterministic (no LLM) is the most important architectural decision in the whole pipeline. If the crisis routing decision ever goes through a language model, the safety story falls apart. Hard-coded rules are a feature, not a limitation.
- Retrieval architecture is deceptively hard. The natural instinct is to point at APIs that "should" exist — but major Australian health authorities (Healthdirect, BHC) don't publish search APIs. Always verify the endpoint exists before designing against it.

---

## 2026-05-11 — Phase 4 Steps 11–13: ADP-C Training + ADP-A Data Prep

### What we did

- **Step 11:** Generated ADP-C training data — synthetic red-line violation pairs. Each example is a (response, verdict, score, critique) tuple. ADP-C learns to output `APPROVE` / `REGENERATE` verdicts with justifications.
- **Step 12:** Ran QLoRA fine-tuning of Gemma-2-2b-it as ADP-C (evaluator adapter). Training completed on RTX 3070.
- **Step 13:** Prepared ADP-A training data. Loaded 5 open-license corpora (AnnoMI, Amod, ESConv, MentalChat16K, EmpatheticDialogues), ran ADP-C as oracle filter, assembled final training set.
- Resolved 3 new gaps discovered during the Step 13 run (G-DATA-03, G-TRAIN-01, G-DATA-06).

### Decisions & justifications

| Decision | Justification |
|----------|--------------|
| AnnoMI dataset ID corrected to `to-be/annomi-motivational-interviewing-therapy-conversations` (G-DATA-03) | The short-form `"AnnoMI"` returns 404 on HuggingFace. The full ID is required. Without the fix, 30% of the ADP-A corpus (AnnoMI's mix weight) would have been 0 records. |
| `max_seq_length=768` for ADP-A training (G-TRAIN-01) | RTX 3070 VRAM headroom at `batch_size=4`. The ADP-C filter truncates responses at 512 tokens — input context rarely exceeds 768 in the prepared corpus. 2048 would require halving batch size. |
| ADP-C `accept_threshold` lowered from 0.70 to 0.50 (G-DATA-06) | At 0.70, only MentalChat (a synthetic dataset) cleared the filter — 1% of EmpatheticDialogues passed. ADP-C was trained on structured critique format and systematically underscores organic conversational style even when clinically appropriate. 0.50 still filters the bottom half of the score distribution. |

### Learnings

- An oracle filter trained on synthetic data will systematically penalize organic data — even when the organic data is good. Calibration thresholds need to be tuned empirically, not set theoretically. The 0.70 threshold was a principled guess; the 0.50 was what the data required.
- Multi-corpus training requires explicit mix weight management. Without tracking per-dataset yield through each filter stage, it's easy to end up with a training set dominated by one source (in this case, synthetic MentalChat). Diversity of training data source matters for robustness.
- Running the data preparation notebook is itself a diagnostic — the per-dataset pass-rate table in Cell 16 surfaced G-DATA-06 immediately. Building observable checkpoints into each step pays off.

---

## 2026-05-12 — Phase 4 Steps 14–15: ADP-A v0 + ADP-B Data + Smoke Tests

### What we did

- **Step 14:** Ran QLoRA fine-tuning of Phi-3.5-mini-instruct as ADP-A (empathy adapter). `weight_decay=0.01`, `lr=1e-4`, `max_seq_length=768`.
- **Step 15:** Generated ADP-B (safety/crisis classifier) training data.
- Ran smoke tests on ADP-A and ADP-B v0 adapter outputs.
- Discovered two significant training quality gaps: URL/email hallucination (G-TRAIN-02) and multi-turn leakage (G-TRAIN-03).
- Resolved phase execution order conflict: ratified revised order Phase 5 → Phase 7 infra → Phase 6 → Phase 7 sign-off (G-PHASE-01).
- Raised G-UI-01: frontend needs a persistent AI limitation disclaimer.

### Decisions & justifications

| Decision | Justification |
|----------|--------------|
| Revised phase execution order (G-PHASE-01) | Phase 6 (Evaluation) requires a live deployed stack for system-tier tests. Under the original ordering, Phase 7 would not exist when Phase 6 ran. The revised order: build the stack first, evaluate against it, then sign off production. |
| G-TRAIN-02 mitigation: URL whitelist in ADP-C + post-processing strip | Belt-and-braces for a clinical context. ADP-C checks at generation time; orchestrator strips any slip-through. Root fix (negative training examples) is a v1 objective. |
| G-TRAIN-03 mitigation: turn-marker detection in ADP-C | Multi-turn leakage is invisible in production (ADP-C fires before the response reaches the user) but visible in raw smoke tests. Adding turn-marker detection to ADP-C's redline set catches it at the evaluation gate. |

### Learnings

- Smoke-testing raw adapter output (bypassing the pipeline) is essential before assuming the pipeline mitigates a problem. The pipeline's ADP-C gate catches hallucinated continuations in production — but only because we found the problem in smoke tests first. The fix was in the evaluator, not the generator.
- Training data format leaks through. Multi-turn source records (AnnoMI, ESConv) expose the model to speaker-alternation format, and the base model's sequence completion prior extends that format past the response boundary. `is_clean()` filters in data prep reduce but don't eliminate this.
- URL hallucination is a base model property, not a fine-tuning failure. The confabulation prior in Phi-3.5-mini (and most modern LLMs) generates plausible-looking contact details that never existed. v0 training data volume is insufficient to override it. For a clinical system, this is a patient-safety issue — not a quality nit.

---

## 2026-05-14 — Architecture Switch + Phase 7 Infra Sign-off

### What we did

- **Architecture switch (Director-approved):** Retired Mistral-7B-Instruct-v0.3. Adopted dual-model stack: **Phi-3.5-mini-instruct** (ADP-A) + **Gemma-2-2b-it** (ADP-B/C). All Mistral artefacts archived to `*/mistral-7b/`.
- Regenerated Steps 11–17 for the new model stack.
- Added Steps 18 and 19 (ADP-A v2 data preparation and training).
- Removed `bitsandbytes` from production stack (`hf_space/requirements.txt`) — ZeroGPU CUDA init-time incompatibility.
- **Phase 7 infra signed off:** HF Spaces ZeroGPU (`space_ok=true`), Fly.io backend, GitHub Pages frontend all confirmed live.
- Consolidated three separate `/infer` GPU sessions into a single `/pipeline` endpoint — eliminates 2 × 80–110s CPU→VRAM model transfer.
- Added `SSEChunk.trace` field to the SSE stream — backend now passes full ADP-B/A/C metadata to the frontend on each turn.
- Rewrote `agent-debug.jsx` to display live pipeline trace data rather than simulated output.
- Added `NikkoAgentLog` pub/sub store for sharing trace data between components.
- Added `ThinkingBubble` component — staged waiting indicator for the 30–120s pipeline latency.
- Implemented `AiDisclaimer` component — persistent non-dismissible footer (G-UI-01 resolved, `REQ-300-164`).
- Ratified G-DATA-07 (no separate SPEC-800 file needed — policy covered by SPEC-000 §11 and GLOSSARY.md).
- Ratified G-UI-02 and G-UI-03 (agent debug ribbon and research preview pill are design choices, not spec-governed).

### Decisions & justifications

| Decision | Justification |
|----------|--------------|
| Retire Mistral-7B (Director-approved) | 14 GB fp16 model requirement on RTX 3070 8 GB VRAM. Training ran 14+ hours with no convergence. The hardware constraint is real and non-negotiable for local development. |
| Phi-3.5-mini for ADP-A (empathy) | 3.8B parameters, MIT licence, converges empathy fine-tuning in ~2 hours on RTX 3070. Produces fluent, contextually warm responses. Generative diversity matters for the empathy task. |
| Gemma-2-2b-it for ADP-B and ADP-C (shared base) | 2B parameters ideal for structured classification (binary crisis flags, APPROVE/REGENERATE verdicts). ADP-B and ADP-C share the Gemma-2 base — loaded once as a single `PeftModel`, hot-swapped with `set_adapter()` at O(1) cost. No weight duplication. |
| Remove `bitsandbytes` from production | ZeroGPU allocates GPU only inside `@spaces.GPU` context functions. `bitsandbytes` checks for CUDA at import time, sees no GPU context, and crashes before the Space initialises. Native bf16 loads cleanly within A10G 24 GB budget without quantization. |
| Consolidate three `/infer` calls to one `/pipeline` endpoint | Each separate `/infer` call triggered an 80–110s CPU→VRAM model transfer. Consolidation eliminates 2 of those 3 transfers. Warm-turn latency drops from ~180–330s to ~20–40s. The tradeoff is a single 360s timeout for the entire pipeline — acceptable for a research preview. |
| `ThinkingBubble` with staged labels | 30–120s pipeline wait is real and unavoidable (ZeroGPU cold start). A static spinner would feel broken. Staged copy ("Reading your message…" → "Checking in on what you shared…" → "Putting together a response…") communicates progress without making false promises about timing. |

### Learnings

- VRAM budget is a hard design constraint, not a soft optimisation target. Architectural decisions (model selection, quantization strategy, adapter sharing) must be made against the actual hardware available — theoretical benchmarks on cloud GPUs don't transfer. The Mistral retirement happened because we ran the hardware constraint to its conclusion.
- `bitsandbytes` and ZeroGPU are architecturally incompatible. ZeroGPU's deferred GPU allocation model (GPU only inside `@spaces.GPU`) is fundamentally at odds with any library that checks for CUDA at import time. This is not documented prominently in either project. The resolution is to not use quantization at all — modern 2–4B models run in native bf16 within A10G budget.
- Adapter sharing (`set_adapter()`) is a significant engineering win when two tasks (safety classification, quality evaluation) share a base model. The VRAM saving is ~4.5 GB — essentially a free second adapter once the base is loaded. This pattern is worth reusing wherever two structured-output agents can share a base.
- User expectation during latency is a product problem, not just a UX detail. 90s cold start on a mental-health platform risks users assuming the system has broken and re-sending, escalating, or leaving. The `ThinkingBubble` label sequence was designed to feel human — like someone actually reading — rather than mechanically counting seconds.

---

## 2026-05-15 — Housekeeping: Documentation Audit + DEVLOG

### What we did

- Audited repo documentation for staleness against current project state.
- Updated `docs/INDEX.md`: phase status table, file counts, reading orders all brought current.
- Updated `README.md`: added status badges, proof-of-concept screenshot, project status table, key documents table. Framed as an ML application README consistent with near-MVP status.
- Created `docs/DEVLOG.md` (this file) — daily development log capturing decisions, justifications, and learnings.
- Created `docs/assets/` directory for screenshots and visual assets.

### Decisions & justifications

| Decision | Justification |
|----------|--------------|
| README keeps existing technical content verbatim | The pipeline documentation, adapter explanations, and safety architecture sections are accurate and well-written. Rewriting them for the sake of housekeeping introduces regression risk. Additions only. |
| DEVLOG lives in `docs/` rather than repo root | It's a governance/process document, not a contributor-facing guide. The `docs/` tree is the right home. |
| DEVLOG reconstructed retrospectively from GAPS.md + CLAUDE.md | All decisions and ratifications were already logged with dates in GAPS.md. The DEVLOG consolidates them into a narrative format with learnings added. No information is fabricated — everything traces to a ratified gap or CLAUDE.md entry. |

### Learnings

- Documentation debt accumulates faster than code debt in spec-driven development. `INDEX.md` still showed Phase 1 as "awaiting Director sign-off" six phases later. The fix took 10 minutes — the cost of not fixing it would have been every future session starting with stale context.
- A gap list (GAPS.md) is a decision log, not just a todo list. The ratification entries contain exactly the information needed to reconstruct *why* the system is the way it is. This is the most valuable documentation in the repo.

---

## Template for future entries

```
## YYYY-MM-DD — [Session title]

### What we did
- Bullet point summary of actions taken.

### Decisions & justifications

| Decision | Justification |
|----------|--------------|
| Decision text | Why this was chosen over alternatives. |

### Learnings
- What was learned that is non-obvious and worth carrying forward.
```

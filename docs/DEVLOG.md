# NIKKO Development Log

## Why this project matters to me

I want to be honest with myself about what Nikko is and what it isn't, because how I frame it — to employers, to collaborators, and to myself — will matter more than the code.

The value of Nikko is not that I built an AI app. Plenty of people build AI apps. The value is that I conceived, specified, governed, and critically shaped a system designed to operate in a context where a wrong output can cause real harm to a real person. That is a different category of work. It requires understanding not just how to build something, but why certain design choices are non-negotiable — why the router is deterministic, why no user data enters training, why the evidence pipeline is separated from the language model, why a consent gate exists before any conversation begins. These aren't implementation details. They are the difference between a system that could plausibly be deployed in a health-adjacent context and one that couldn't.

What I think Nikko signals — if I execute it well and talk about it honestly — is that I sit at the intersection of multiple domains that most candidates only partially cover: data science, health systems, AI capability, psychological risk, and governance. Digital health is actively looking for people who can translate across all of those. Not just engineers who understand models, and not just clinicians who understand risk, but people who understand both well enough to make them speak to each other. That is what I was trying to build the capacity to do by building Nikko.

There is a framing I want to avoid and one I want to earn. I don't want to present this as "I used AI to build a therapy chatbot." That is both inaccurate and undersells the actual work. What I want to be able to say — and to mean — is: I designed a privacy-first cognitive support system to explore safe human–AI interaction models in mental health contexts. I made the governance decisions. I challenged the architecture. I understood the tradeoffs. The implementation was accelerated by AI tooling, which is modern engineering reality, but the thinking was mine.

The skills Nikko demonstrates are high-trust skills: non-diagnostic boundaries, evidence-informed design, data minimisation, harm mitigation, consent mechanisms, specification-driven development. These don't appear on most junior portfolios. They appear on senior ones. I want to carry that forward.

The risk I need to stay honest about is not overselling it. Nikko is a research-grade system, not a clinical tool. It is not therapy. It does not have regulatory approval and was never designed to seek it. The strongest version of this project is one where I show design capability and restraint — not one where I overstate what it does. The restraint is actually the point.

What I am ultimately trying to signal is simple: I can design AI systems responsibly, I understand healthcare constraints, and I think beyond models into human outcomes. For someone early in their career, that combination is uncommon. Nikko is my evidence that I mean it.

---

## A note on how this was built

NIKKO was built with significant assistance from Claude (Anthropic), used here as a coding and architecture collaborator. This is an honest acknowledgement of what that looked like in practice.

Claude accelerated the build in ways that would have taken me weeks alone — spec extraction, agent scaffolding, training notebooks, frontend components, deployment configuration, and documentation were all produced at a pace I couldn't have matched writing everything from scratch. For a solo developer building a production-grade ML system for the first time, that kind of leverage is real.

But acceleration is not authorship. Every architectural decision, every ratified requirement, every phase gate, and every "this doesn't feel right" moment that sent us back to the drawing board was mine. Claude generated; I directed, questioned, approved, and — when I didn't question enough — paid for it in hours lost to avoidable mistakes.

This was also my first serious experience building with AI assistance, what people sometimes call "vibe coding." I came in thinking the main skill was writing good prompts. I left understanding that the actual skill is knowing *when not to trust the output* — which requires enough domain knowledge to spot a confident-sounding answer that is quietly wrong. A fabricated API endpoint, a threshold that destroys your data distribution, a model that doesn't fit your GPU: none of these were flagged as uncertain. They were presented cleanly, and I accepted them without checking. The "Where I went wrong" entries in this log are a record of that learning curve.

The honest version of AI-assisted development is not "AI did the work." It's closer to: AI removed the friction of going from idea to implementation, which freed me to spend more time on the decisions that actually mattered — and also made it easier to move fast in the wrong direction when I wasn't paying attention.

---

> **Purpose:** A running record of what was done each day, decisions made with their justifications, and key learnings taken out of the session.
>
> **Format:** Chronological. Each entry covers: **What we did**, **Decisions & justifications**, **Where I went wrong**, **Learnings**.
>
> **Owner:** Director (Nicholas). Maintained by the NIKKO Engineering Collective agent.
>

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

### Where I went wrong

**I accepted an API endpoint that didn't exist.** The `HealthdirectAdapter` was built against `api.healthdirect.gov.au/ih/api/v2/content/search` — a URL that sounds authoritative and plausible. I approved the implementation without spending 30 seconds verifying that the endpoint actually exists. It doesn't. Healthdirect Australia has no public search API. The same blind acceptance applied to the BetterHealth and WHO adapters being designed as "static JSON corpus" — a brittle approach I didn't question until review. All three adapters had to be scrapped and replaced with `WebSearchAdapter`, which meant rethinking the retrieval architecture from scratch mid-phase. **The fix:** before approving any implementation that depends on an external API or service, open a browser and verify the endpoint exists yourself. A working `curl` beats a confident description every time.

### Learnings

- LLM-agent architectures benefit enormously from making each agent's input and output a typed, validated schema (`SignalPayload`, `ResponseContextPayload`, etc.). This forces you to be explicit about what each agent actually needs vs. what it has access to — and prevents the most common failure mode where the LLM quietly uses context it shouldn't have.
- The Router being deterministic (no LLM) is the most important architectural decision in the whole pipeline. If the crisis routing decision ever goes through a language model, the safety story falls apart. Hard-coded rules are a feature, not a limitation.
- Retrieval architecture is deceptively hard. The natural instinct is to point at APIs that "should" exist — but major Australian health authorities don't publish search APIs. Always verify the endpoint exists before designing against it.

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

### Where I went wrong

**I ran Step 13 without checking the dataset ID first (G-DATA-03).** The notebook loaded AnnoMI with `load_dataset("AnnoMI", ...)`. I saw the code, it looked fine, and I ran it. What I didn't do was spend 10 seconds searching HuggingFace to confirm that `"AnnoMI"` was a valid short-form identifier. It isn't — it 404s silently, returns an empty dataset, and the notebook happily continues with 0 AnnoMI records. AnnoMI carries a 30% mix weight in the ADP-A corpus. I nearly trained on a dataset missing nearly a third of its intended content and wouldn't have known unless I'd read the Cell 16 summary carefully.

**I accepted the `accept_threshold=0.70` without understanding what it would do to the data distribution — this is the oversampling issue that cost hours (G-DATA-06).** The threshold was presented as principled (filter the bottom 30% of quality scores). I didn't question it. When Step 13 actually ran, the pass-rate table told a different story:

| Dataset | Pass rate |
|---------|-----------|
| EmpatheticDialogues | 1.0% |
| AnnoMI | 6.7% |
| ESConv | 11.5% |
| Amod | 25.6% |
| MentalChat16K (synthetic) | **93.7%** |

The filter demolished every organic, real-human empathy dataset while letting nearly all of the synthetic MentalChat data through. The assembled training set was dominated by synthetic examples — the opposite of what the corpus was designed to achieve. I then had to lower the threshold, rerun the full filter pass across all five corpora, re-check the yield counts, re-assemble, and re-validate. Hours gone. The root issue was that ADP-C was trained on structured critique pairs, so it reliably scores synthetic, well-formatted data highly and organic conversational data poorly — a calibration mismatch I should have asked about before trusting the threshold to produce a balanced corpus. **The fix:** when a filter or threshold is proposed, ask what the expected pass rate is per source before running. A 30-second sanity check on the numbers saves a multi-hour rerun.

**I also had a conflicting `max_seq_length` between the config file and the handoff doc (G-TRAIN-01).** `config.yaml` said 2048. The handoff doc and the notebook both said 768. I had both documents open and missed the contradiction entirely. It only surfaced as a gap because the discrepancy was caught in a pre-run audit — if it had been missed, Step 14 would have run with a sequence length that either OOM-crashed the RTX 3070 or silently degraded training by halving the batch size mid-run. **The fix:** when a config file and a doc disagree, that is always worth stopping to resolve before running anything.

### Learnings

- An oracle filter trained on synthetic data will systematically penalize organic data — even when the organic data is good. Calibration thresholds need to be tuned empirically against actual pass rates, not set theoretically.
- Multi-corpus training requires checking the *per-source yield* before running, not just the total. A total yield of 336 records looks like a quantity problem; the per-source breakdown reveals it's a distribution problem.
- Running the data preparation notebook is itself a diagnostic. The pass-rate table in Cell 16 is the most important output of Step 13 — read it before moving on.
- Never skip the pre-run config audit. Discrepancies between a config file and documentation are not cosmetic — they are silent divergences in what the training job will actually do.

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

### Where I went wrong

**I didn't smoke-test the adapter outputs early enough.** The URL hallucination (G-TRAIN-02) and multi-turn leakage (G-TRAIN-03) were properties of the base model that fine-tuning at v0 data volume couldn't suppress. These weren't surprises in hindsight — any sufficiently large language model will confabulate plausible contact details and continue generating dialogue past a natural stopping point. I should have tested raw adapter output after Step 12 (ADP-C), not waited until after Steps 14–15. Finding these issues earlier in the training sequence would have let me adjust the training data *before* running ADP-A and ADP-B rather than adding mitigations after the fact. **The fix:** smoke-test every adapter immediately after training, not as a batch at the end. One prompt, raw output, check for hallucinated URLs and turn-continuation before moving to the next step.

### Learnings

- Smoke-testing raw adapter output (bypassing the pipeline) is essential before assuming the pipeline mitigates a problem. The pipeline's ADP-C gate catches hallucinated continuations in production — but only because we found the problem in smoke tests first.
- URL hallucination is a base model property, not a fine-tuning failure. For a clinical system this is a patient-safety issue — not a quality nit. It needs to be planned for at the data design stage.
- Training data format leaks through. Multi-turn source records expose the model to speaker-alternation format, and the base model extends that pattern past the response boundary. `is_clean()` filters in data prep reduce but don't eliminate this.

---

## 2026-05-14 — Architecture Switch + Phase 7 Infra Sign-off

### What we did

- **Architecture switch (Director-approved):** Retired Mistral-7B-Instruct-v0.3. Adopted dual-model stack: **Phi-3.5-mini-instruct** (ADP-A) + **Gemma-2-2b-it** (ADP-B/C). All Mistral artefacts archived to `*/mistral-7b/`.
- Regenerated Steps 11–17 for the new model stack.
- Added Steps 18 and 19 (ADP-A v2 data preparation and training).
- Removed `bitsandbytes` from production stack (`hf_space/requirements.txt`) — ZeroGPU CUDA init-time incompatibility.
- **Phase 7 infra signed off:** HF Spaces ZeroGPU (`space_ok=true`), Render backend, GitHub Pages frontend all confirmed live.
- Consolidated three separate `/infer` GPU sessions into a single `/pipeline` endpoint — eliminates 2 × 80–110s CPU→VRAM model transfer.
- Added `SSEChunk.trace` field to the SSE stream — backend now passes full ADP-B/A/C metadata to the frontend on each turn.
- Rewrote `agent-debug.jsx` to display live pipeline trace data rather than simulated output.
- Added `NikkoAgentLog` pub/sub store for sharing trace data between components.
- Added `ThinkingBubble` component — staged waiting indicator for the 30–120s pipeline latency.
- Implemented `AiDisclaimer` component — persistent non-dismissible footer (G-UI-01 resolved, `REQ-300-164`).
- Ratified G-DATA-07, G-UI-02, G-UI-03.

### Decisions & justifications

| Decision | Justification |
|----------|--------------|
| Retire Mistral-7B (Director-approved) | 14 GB fp16 model requirement on RTX 3070 8 GB VRAM. Training ran 14+ hours with no convergence. The hardware constraint is real and non-negotiable for local development. |
| Phi-3.5-mini for ADP-A (empathy) | 3.8B parameters, MIT licence, converges empathy fine-tuning in ~2 hours on RTX 3070. Produces fluent, contextually warm responses. |
| Gemma-2-2b-it for ADP-B and ADP-C (shared base) | 2B parameters ideal for structured classification. ADP-B and ADP-C share the base — loaded once, hot-swapped with `set_adapter()` at O(1) cost. No weight duplication. |
| Remove `bitsandbytes` from production | ZeroGPU allocates GPU only inside `@spaces.GPU` context functions. `bitsandbytes` checks for CUDA at import time, crashes before the Space initialises. Native bf16 fits A10G 24 GB budget without quantization. |
| Consolidate three `/infer` calls to one `/pipeline` endpoint | Each separate call triggered an 80–110s CPU→VRAM model transfer. Consolidation eliminates two of those three transfers. Warm-turn latency: ~20–40s. |
| `ThinkingBubble` with staged labels | 30–120s pipeline wait is unavoidable. Staged copy communicates progress without making false promises about timing. |

### Where I went wrong

**I committed to Mistral-7B as the base model without doing a back-of-envelope VRAM check first.** The model requires ~14 GB in fp16. The RTX 3070 has 8 GB. These two numbers are publicly available and take seconds to look up — I didn't look them up before accepting Mistral as the architecture. The result: an entire set of notebooks built, data prepared, training attempted, 14+ hours elapsed with no convergence, and then a full architecture migration. Every notebook from Step 11 to Step 17 had to be regenerated. All Mistral artefacts had to be archived. This was the most expensive avoidable mistake of the project so far. **The fix:** for any model selection decision, the first check is always *does this fit in available VRAM?* Model size in GB ÷ VRAM in GB. If the answer is greater than 1, the conversation is over before it starts.

**I also accepted `bitsandbytes` as a dependency for production without understanding the ZeroGPU execution model.** `bitsandbytes` is a standard quantization library — it seemed like an obvious inclusion. I didn't ask how ZeroGPU allocates GPU memory or when it does so. The answer (only inside `@spaces.GPU`, never at import time) makes `bitsandbytes` fundamentally incompatible with ZeroGPU. This isn't obscure information — it's in the ZeroGPU documentation — but I didn't read it and neither did I challenge the dependency before it was added to `requirements.txt`. The crash only surfaced when deploying to HF Spaces. **The fix:** when adding a library that touches hardware (CUDA, memory, quantization), read the deployment environment's documentation first. The question "when does this library check for CUDA?" takes two minutes to answer and would have saved a debug cycle.

### Learnings

- VRAM budget is a hard design constraint, not a soft optimisation target. Check model size against available VRAM before any other architecture discussion.
- `bitsandbytes` and ZeroGPU are architecturally incompatible. ZeroGPU's deferred GPU allocation is fundamentally at odds with any library that checks for CUDA at import time.
- Adapter sharing (`set_adapter()`) is a significant engineering win when two tasks share a base model. The VRAM saving is ~4.5 GB — a free second adapter once the base is loaded.
- User expectation during latency is a product problem, not a UX detail. 90s cold start on a mental-health platform risks users assuming the system has broken.

---

## 2026-05-15 — Housekeeping: Documentation Audit + DEVLOG

### What we did

- Audited repo documentation for staleness against current project state.
- Updated `docs/INDEX.md`: phase status table, file counts, reading orders all brought current.
- Updated `README.md`: added status badges, proof-of-concept screenshot, project status table, key documents table.
- Created `docs/DEVLOG.md` (this file).
- Created `docs/assets/` directory for screenshots and visual assets.
- Fixed Fly.io / Render label contradiction across README and CLAUDE.md.
- Removed `CLAUDE.md`, `fly.toml`, `docs/DEPLOY-HYBRID-MVP.md`, and `docs/GAPS.md` from git tracking.

### Where I went wrong

**I let "Fly.io" stay in the README, the deployment diagram, and CLAUDE.md for the entire Phase 7 infra session without noticing it said Fly.io while the URL said onrender.com.** These are different companies. The contradiction was sitting in plain text in the README's architecture diagram, the deployment table, and the CLAUDE.md phase sign-off note all at once. Nobody caught it until today. **The fix:** when a URL and a service name appear in the same sentence, read them together. A Render URL next to a Fly.io label is not subtle.

### Learnings

- Documentation debt accumulates faster than code debt. `INDEX.md` still showed Phase 1 as "awaiting Director sign-off" six phases later.
- A gap list is a decision log, not just a todo list. The ratification entries in GAPS.md contain exactly the information needed to reconstruct *why* the system is the way it is.
- Contradictions between a URL and a service label are a sign that a deployment decision was made and the docs were never updated to match. Check them together.

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

### Where I went wrong
- What I accepted without verifying, and what it cost.
- The fix: what I should do differently next time.

### Learnings
- What was learned that is non-obvious and worth carrying forward.
```

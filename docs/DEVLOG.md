# NIKKO Development Log

## Why this project matters to me

I want to be honest about what Nikko is and what it isn't, because how I frame it — to employers, to collaborators, and to myself — matters more than the code does.

The value of Nikko isn't that I built an AI app. Plenty of people build AI apps. The value is that I spent months trying to design and govern a system meant to operate in a context where a wrong output can cause real harm. That's a different category of work, and I'm still learning what it actually demands. Some of the design choices feel obvious in hindsight — the router has to be deterministic, no user data enters training, the evidence pipeline has to be separated from the language model, the consent gate runs before any conversation. I didn't arrive at those calls cleanly. Most of them came out of arguing through gaps in the spec, or watching a v0 fail in a way that exposed an assumption I hadn't realised I was making.

What I think Nikko signals — if I keep executing on it honestly — is that I'm trying to sit at the intersection of data science, health systems, AI capability, psychological risk, and governance. I don't claim to be expert in all of those. I have a clinical background, a data science degree, and a Master of Digital Health starting in early 2026, and Nikko is partly an attempt to put those threads in the same place. Digital health is looking for people who can translate across all those domains, and right now I'm still building the translation muscle.

There's a framing I want to avoid and one I want to earn. I don't want to present this as *"I used AI to build a therapy chatbot."* That undersells the actual work and isn't accurate either. What I want to be able to say honestly is: I designed a privacy-first cognitive support system to explore safe human–AI interaction in mental health contexts. I made the governance calls. I challenged the architecture when something didn't feel right. The implementation was accelerated by AI tooling, which is a modern reality for solo developers, but the thinking — and the mistakes — were mine.

The skills Nikko forced me to develop are skills I don't see on most junior portfolios: non-diagnostic boundaries, evidence-informed design, data minimisation, harm mitigation, consent mechanisms, specification-driven development. I'm not claiming I've mastered any of them. I'm claiming I've practised them on a real system with real constraints, which is more than most people in my career stage have done.

The thing I most want to stay honest about is not overselling it. Nikko is a research-grade system, not a clinical tool. It is not therapy. It has no regulatory approval and was never designed to seek any. The strongest version of this project is one where I show design capability *and* restraint — not one where I overstate what it does. The restraint is actually the point.

What I'm trying to signal is simple: I can design AI systems responsibly, I understand healthcare constraints because I've worked inside them, and I think beyond the model into the human outcome. For someone early in their career, that combination is uncommon. Nikko is the evidence that I'm taking it seriously.

---

## A note on how this was built

NIKKO was built with significant assistance from Claude (Anthropic), used as a coding and architecture collaborator. I want to be straightforward about what that looked like in practice, because the alternative — quietly understating the role of AI tooling — would undermine everything else I'm trying to say in this log.

Claude accelerated the build in ways I couldn't have matched alone. Spec extraction, agent scaffolding, training notebooks, frontend components, deployment configuration, documentation — all produced at a pace that let me work on a system of this size as a solo developer for the first time. For a junior building a production-grade ML system, that kind of leverage is real, and pretending otherwise would be dishonest.

But acceleration isn't authorship. Every architectural call, every requirement I ratified, every phase gate, every *"this doesn't feel right, let's go back"* moment was mine. Claude generated; I directed, questioned, approved, and — when I didn't question hard enough — paid for it in hours lost to mistakes I could have caught.

This was also my first serious experience building with AI assistance, what some people call "vibe coding." I came in thinking the main skill was writing good prompts. I'm leaving with a different view: the actual skill is knowing *when not to trust the output*, and that requires enough domain knowledge to recognise a confident-sounding answer that's quietly wrong. The Learnings sections in this log are a record of that — the assumptions I had to unlearn, the calls I'll make differently next time, and the times moving fast in the wrong direction cost more than moving slowly in the right one.

The honest version of AI-assisted development, at least for me, is that AI removed the friction of going from idea to implementation, which freed me up to spend more time on the decisions that mattered — and also let me move fast in the wrong direction when I wasn't watching closely.

---

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
- Triaged 32 enumerated gaps in `GAPS.md` — every ambiguity, missing variable, and logical inconsistency I could find in the source document.
- Ruled on all 32 gaps in a single session. All 4 🔴 Critical gaps ratified. All 10 🟠 High gaps ratified.
- Phase 1 (Spec Initialization) and Phase 2 (Architectural Contracts) both signed off in the same session.

### Decisions & justifications

| Decision | Justification |
|----------|--------------|
| Australia-only v0 deployment (G-CRISIS-01) | Public internet deployment but only Australian crisis resources exist. Geo-blocking or locale-detection deferred to GA. v0 ships with prominent AU-only disclaimer. |
| Zero data retention — hard charter constraint (G-DATA-01) | Mental-health user input is PII-adjacent. No user conversation data may enter the training pipeline under any circumstances. Session data lives in `sessionStorage` only. |
| Conversation state in-memory only (G-MEMORY-01) | Avoids server-side persistence obligations. Entire conversation history lives in the LLM context window; destroyed on session end. |
| 18+ self-attestation gate (G-AGE-01) | Lowest engineering cost for v0. Online Safety Act AU compliance for a research preview. Path to adapted minor mode reserved for GA. |
| Scope classifier inserted as STEP 0 (G-SCOPE-01) | Prevents off-topic messages from polluting the agent pipeline. Ambiguous messages pass through — only high-confidence non-emotional queries are rejected with a warm redirect. |
| Evaluator → Verification Supervisor order (G-RECON-02) | Evaluator does per-response content gate; VS does system-level structural gate. Content has to pass before structure is checked. |
| SFT with rejection sampling for v0 training (G-LOSS-01) | Simplest formulation compatible with the open-license corpus constraint. DPO upgrade path once a preference dataset exists. |

### Learnings

- The source spec had real internal contradictions that required a consistency-check pass before extraction, not after. Treating spec extraction like a debugging pass — not a copy-and-paste job — is what surfaced overlapping agent authority levels, two separate pipeline step orderings, and a missing adapter combination for Crisis Mode.
- Writing things down upfront forces decisions I would otherwise have hit as bugs later. The example that stuck: there was no policy for what happens when a passive risk indicator appears without explicit crisis language, and the only way to resolve it was to make a call and put it in the spec.
- The gap between "described qualitatively in prose" and "implementable deterministically in code" is almost always a numeric threshold, a specific API, or an exact ordering. None of those were in the source doc, which means every prose description had to be tightened to something a machine could act on.

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
| Replaced Healthdirect/BetterHealth/WHO adapters with WebSearchAdapter (G-RETRIEVAL-01) | Healthdirect has no public search API. Static JSON corpus for BetterHealth/WHO required manual curation with no update mechanism. WebSearchAdapter with `site:` operator covers all five sanctioned domains with one implementation. |
| `bitsandbytes==0.45.5` over 0.41.1 or 0.43.1 (G-ENV-01) | 0.45.5 has improved Windows CUDA 12.x DLL path discovery. Resolved the `cudart64_12.dll` lookup failure without requiring a full CUDA Toolkit install. |
| Qwen2.5-3B-Instruct retained as Phase 3 dev model | Output quality good enough for structured JSON agent tasks. Fits 8 GB VRAM without quantization. Used only for development — replaced by fine-tuned adapters in Phase 4. |
| Scope Classifier uses weighted keyword scorer, no LLM | A deterministic gate can't introduce LLM latency or unpredictability. A keyword scorer is fast, auditable, and good enough for this binary classification. |

### Learnings

- Typed, validated schemas between agents (`SignalPayload`, `ResponseContextPayload`, and so on) made the pipeline far easier to reason about than I expected. They forced me to be explicit about what each agent *needs* versus what it can *see* — and that distinction is where a lot of the LLM safety story actually lives.
- The Router being deterministic — no LLM — is one of the most important calls in the whole pipeline. If the crisis decision ever ran through a language model, the whole safety story would depend on the model's judgment, which is exactly the thing I'm trying to avoid.
- Most major Australian health authorities don't publish search APIs. Designing against external APIs requires confirming the endpoint is real before building against it — not after.

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
| ADP-C `accept_threshold` lowered from 0.70 to 0.50 (G-DATA-06) | At 0.70, only MentalChat (a synthetic dataset) cleared the filter — 1% of EmpatheticDialogues passed. ADP-C was trained on structured critique format and systematically underscored organic conversational style even when clinically appropriate. 0.50 still filters the bottom half of the score distribution. |

### Learnings

- An oracle filter trained on synthetic data will systematically penalise organic data, even when the organic data is good. Distribution mismatch is a real cost — understanding the per-source yield before trusting a threshold is the diagnostic, not the total yield.
- For multi-corpus training, the per-source pass-rate table is the most important output of data preparation. Total yield of 336 records looks like a quantity problem; the breakdown is where you find the distribution problem.
- A config-vs-doc discrepancy is a silent divergence in what the training job will actually do. It warrants a hard stop and resolution before running anything.

---

## 2026-05-12 — Phase 4 Steps 14–15: ADP-A v0 + ADP-B Data + Smoke Tests

### What we did

- **Step 14:** Ran QLoRA fine-tuning of Phi-3.5-mini-instruct as ADP-A (empathy adapter). `weight_decay=0.01`, `lr=1e-4`, `max_seq_length=768`.
- **Step 15:** Generated ADP-B (safety/crisis classifier) training data.
- Ran smoke tests on ADP-A and ADP-B v0 adapter outputs.
- Found two significant training quality gaps: URL/email hallucination (G-TRAIN-02) and multi-turn leakage (G-TRAIN-03).
- Resolved phase execution order conflict: ratified revised order Phase 5 → Phase 7 infra → Phase 6 → Phase 7 sign-off (G-PHASE-01).
- Raised G-UI-01: frontend needs a persistent AI limitation disclaimer.

### Decisions & justifications

| Decision | Justification |
|----------|--------------|
| Revised phase execution order (G-PHASE-01) | Phase 6 (Evaluation) needs a live deployed stack for system-tier tests. Under the original ordering, Phase 7 wouldn't exist when Phase 6 ran. The revised order: build the stack first, evaluate against it, then sign off production. |
| G-TRAIN-02 mitigation: URL whitelist in ADP-C + post-processing strip | Belt-and-braces for a clinical context. ADP-C checks at generation time; orchestrator strips any slip-through. Root fix (negative training examples) is a v1 objective. |
| G-TRAIN-03 mitigation: turn-marker detection in ADP-C | Multi-turn leakage is invisible in production (ADP-C fires before the response reaches the user) but visible in raw smoke tests. Adding turn-marker detection to ADP-C's redline set catches it at the evaluation gate. |

### Learnings

- Smoke-testing raw adapter output — bypassing the pipeline — is the only reliable way to isolate base-model behaviours from pipeline mitigations. The pipeline's ADP-C gate catches hallucinated continuations in production, but the model's raw behaviour needs to be understood independently first.
- URL hallucination is a base-model property in a clinical-adjacent context — a patient-safety concern, not a polish issue. It belongs at the data-design stage, not the post-training mitigation stage.
- Training data format leaks through. Multi-turn source records expose the model to speaker-alternation patterns, and the base model will extend those patterns past the response boundary.

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
| Retire Mistral-7B (Director-approved) | 14 GB fp16 model on an RTX 3070 with 8 GB VRAM. Training ran 14+ hours with no convergence. The hardware constraint isn't negotiable for local development. |
| Phi-3.5-mini for ADP-A (empathy) | 3.8B parameters, MIT licence, converges empathy fine-tuning in ~2 hours on RTX 3070. Produces fluent, contextually warm responses. |
| Gemma-2-2b-it for ADP-B and ADP-C (shared base) | 2B parameters works for structured classification. ADP-B and ADP-C share the base — loaded once, hot-swapped with `set_adapter()` at O(1) cost. No weight duplication. |
| Remove `bitsandbytes` from production | ZeroGPU only allocates GPU inside `@spaces.GPU` context functions. `bitsandbytes` checks for CUDA at import time, which crashes before the Space initialises. Native bf16 fits the A10G 24 GB budget without quantization. |
| Consolidate three `/infer` calls into one `/pipeline` endpoint | Each separate call triggered an 80–110s CPU→VRAM model transfer. Consolidating eliminates two of those three transfers. Warm-turn latency: ~20–40s. |
| `ThinkingBubble` with staged labels | The 30–120s pipeline wait isn't going away. Staged copy communicates progress without making promises about exact timing. |

### Learnings

- VRAM budget is a hard design constraint, not a soft optimisation. Model size in GB divided by available VRAM is the first question to ask about any candidate model — everything else (capability, licence, performance) only matters once that's settled.
- `bitsandbytes` and ZeroGPU are architecturally incompatible by design. ZeroGPU's deferred GPU allocation breaks any library that probes for CUDA at import time. When adding any dependency that touches hardware, the question to ask first is: when does this library check for the GPU?
- Adapter sharing via `set_adapter()` is a meaningful engineering win — approximately 4.5 GB VRAM saved, effectively a free second adapter once the base is loaded.
- User expectation during latency is a product problem, not a UX detail. A 90-second cold start on a mental-health platform isn't acceptable if the user thinks the system has frozen — the staged labels in `ThinkingBubble` aren't decoration, they're risk mitigation.

---

## 2026-05-15 — Housekeeping: Documentation Audit + DEVLOG

### What we did

- Audited repo documentation for staleness against the current project state.
- Updated `docs/INDEX.md`: phase status table, file counts, reading orders all brought current.
- Updated `README.md`: added status badges, proof-of-concept screenshot, project status table, key documents table.
- Created `docs/DEVLOG.md` (this file).
- Created `docs/assets/` directory for screenshots and visual assets.
- Fixed Fly.io / Render label contradiction across README and CLAUDE.md.
- Removed `CLAUDE.md`, `fly.toml`, `docs/DEPLOY-HYBRID-MVP.md`, and `docs/GAPS.md` from git tracking.

### Learnings

- Documentation debt accumulates faster than code debt. `INDEX.md` was still showing Phase 1 as "awaiting Director sign-off" six phases later.
- A gap list is a decision log, not just a todo list. The ratification entries in GAPS.md contain exactly the information I'd need to reconstruct *why* the system is the way it is.
- Contradictions between a URL and a service label are a sign that a deployment call was made and the docs weren't updated to match. Grep the whole repo when one shows up — don't check files in isolation.

---

## 2026-05-16 — Phase 5 Sign-off + Backend Integration Complete

### What we did

- Wired `memoryContext` end-to-end: frontend sends decrypted USM content in the POST body; `MessageRequest` receives it; `NikkoPipeline.run()` accepts `memory_context: Optional[str]`; `ResponseContextPayload` carries `usm_content`; `build_adp_a_system()` injects it into the ADP-A system prompt as personalisation context (capped at 1200 chars with truncation notice).
- Added `sessionStorage` persistence for USM loaded/name flags so a page refresh no longer silently drops the "memory loaded" indicator — content is intentionally not persisted (SPEC-800 zero-retention).
- Reconstructed truncated `chat.jsx` tail from compiled `chat.js` (React.createElement reverse-engineering).
- Added `MODAL_HEALTH_URL` env var to `backend/main.py` — health probe now uses a separate designated health endpoint rather than appending `/health` to the inference URL (which is POST-only and returned 404).
- Phase 5 signed off.

### Decisions & justifications

| Decision | Justification |
|----------|--------------|
| USM content capped at 1200 chars in ADP-A system prompt | ADP-A context window has a hard limit. 1200 chars carries enough to personalise without crowding out strategy guidance and evidence. Truncation is visible to the model ("Memory file truncated"). |
| `memContentRef` as useRef, not useState | The decrypted content is large and doesn't need to trigger re-renders when set. useRef holds it across renders without the cost of re-diffing. |
| sessionStorage for loaded flag, not content | Flag/name need to survive React re-renders. Content must not persist across sessions (SPEC-800). Two different signals, two different mechanisms. |
| Separate `MODAL_HEALTH_URL` env var | The `/pipeline` endpoint is POST-only. Appending `/health` to the Modal inference URL returned 404 on every health probe, incorrectly marking the stack as unhealthy. Health probe and inference endpoint are architecturally separate concerns — one accepts GET with no body, the other accepts POST with a complex payload. |

### Learnings

- Health probe and inference endpoints are separate architectural concerns and should always be designed as separate URLs. A single URL cannot serve both roles cleanly.
- Canonical documentation (GLOSSARY, SPEC files) needs to be updated at the same time as the implementation changes that affect them — not at the next documentation session.

---

## 2026-05-17 — Phase 6 Active: Pipeline Routing Fixes + Modal Reliability + MVP Declaration

### What we did

- **PubMed gate fix:** `_is_pubmed_eligible()` wasn't triggering on research-intent queries like "is there any research that supports deep breathing?" because the evidence query normalisation strips the user's research framing before the gate check. Added signal (c): raw user text is now checked independently against a list of explicit research-intent phrases (`"is there any research"`, `"does research show"`, `"are there studies"`, `"evidence shows"`, etc.).
- **GUIDANCE routing fix:** Extended `_GUIDANCE_KEYWORDS` with action-seeking phrases that don't match the existing `"what can i do"` pattern: `"anything i can"`, `"anything that i can"`, `"anything i could"`, `"is there anything i"`, `"anything to help"`, `"what to do"`, `"is there anything to"`, `"what can help"`, `"what helps"`. Fixes misclassification of "is there anything I can do?" as COMFORT.
- **Modal 429 handling:** Added 3-retry × 10s backoff loop in `draft_generator.py` for 429 responses from the primary Modal endpoint. Previously a 429 immediately fell back to HF Space (~90–120s cold start). Now retries exhaust first (30s max patience) before accepting the slower fallback.
- **`scaledown_window=600`** added to Modal `@app.cls` — container stays warm for 10 minutes after last request, substantially reducing 429 frequency during normal usage cadence.
- **`torch_dtype` → `dtype`** deprecation fix applied to both Qwen3 and Gemma-2 `from_pretrained` calls in `nikko_modal/app.py`.
- **agent-debug.jsx line-ending normalization:** LF normalised. CI esbuild compilation now passes cleanly.
- **MVP declared.** Status updated from "research preview" to MVP across README and badges.

### Decisions & justifications

| Decision | Justification |
|----------|--------------|
| Raw text PubMed signal alongside query signal | Evidence query normalisation is intentionally aggressive — it strips research framing to produce a clean search string. We need the raw text for intent detection; we need the normalised query for the search itself. These are separate signals and should be checked separately. |
| Retry-then-fallback for Modal 429 (not immediate fallback) | HF Space cold start is 90–120s. A Modal container busy with a prior request is usually free again in 20–40s. Three retries × 10s is 30s maximum patience — a much better outcome than a 90s penalty. |
| `scaledown_window=600` over a shorter value | Our usage pattern is conversational — turns arrive roughly 60–180s apart. A 10-minute warmth window covers a typical session without keeping the container hot during idle periods. |
| GUIDANCE keyword extension rather than regex | The existing `_GUIDANCE_KEYWORDS` frozenset is a fast, auditable, deterministic structure. Adding phrase variants is lower-risk than introducing regex patterns that might over-match. |

### Learnings

- Normalisation pipelines are opaque to downstream gates. Any signal that lives in the raw user text and gets processed before the gate sees it must be extracted *before* normalisation and carried separately. The evidence query and the intent signal are two different things and should always have been treated as such.
- Modal 429s are not errors — they're a concurrency signal. The container is alive and will be ready again soon. Treating them as failures and immediately routing to the fallback is the wrong call; a brief wait is almost always the right one.
- Live routing evaluation reveals phrasings that spec design misses. No amount of spec review would have surfaced "is there anything I can do?" as an uncovered GUIDANCE variant — it took a user query to find it. Phase 6 exists for exactly this reason.

---

## 2026-05-17 (Session 2) — Safety: Content Moderation Pre-gate + OOS Filters

### What we did

- **Content moderation pre-gate** added to `orchestration/pipeline.py` — fires before STEP 0 (Scope Classifier), making it the first thing that runs on every message. Three tiers in priority order: CSAM-adjacent content, child attraction/paedophilia patterns, hate speech.
- **CSAM-adjacent patterns** (`_CSAM_PATTERNS`): anime-convention terminology (`loli`, `shota`, `lolicon`, `shotacon`), explicit illegal CSAM naming, masturbation explicitly to CSAM/minor-coded material. Returns `_CSAM_RESPONSE` — terse, firm, zero empathy for the content itself.
- **Hate speech patterns** (`_HATE_PATTERNS`): coded antisemitism, Islamophobia, white nationalism. Returns `_HATE_RESPONSE`. The filter is intentionally narrow — statements like "my boss is ageist" or "I hate immigrants" must NOT be blocked; only explicit hate advocacy.
- **`_step_content_moderation()`** method on `NikkoPipeline` — modular, traceable (`trace.final_action = "content_moderation_csam"` / `"content_moderation_hate"`), returns a completed `PipelineResult` on match so the rest of the pipeline never runs.
- **OOS filters added to `scope_classifier.py`**: current-affairs queries and physical health questions (diet, medication, symptoms) — common false positives that were routing into the emotional support pipeline.
- REQ-XXX-CM1: content moderation MUST fire before any agent or LLM processing. REQ-XXX-CM2: CSAM-adjacent content MUST NOT receive an empathetic validation response. REQ-XXX-CM3: moderation block responses are static strings, never LLM-generated.

### Decisions & justifications

| Decision | Justification |
|----------|--------------|
| Moderation fires before Scope Classifier (pre-STEP 0) | No harmful content should reach any agent, including deterministic ones. A Scope Classifier pass on CSAM content is wasted processing and creates a log trail of harmful content passing through agents. Hard block is cleaner. |
| Three separate pattern lists with priority order | CSAM → hate is the correct priority. A message matching both should return the CSAM response. Separate lists make priority explicit and auditable. |
| Narrow hate filter — explicit advocacy only | The risk of false-positiving on genuine emotional expression ("I hate how my family makes me feel") outweighs the risk of missing coded hate speech in a mental health context. The LLM moderation pass (added 2026-05-21) handles edge cases the regex misses. |
| Static responses for all moderation blocks | No LLM-generated content for harmful inputs. Responses are deterministic, reviewed, and cannot be steered by prompt injection. |

### Learnings

- Content moderation belongs before the pipeline, not inside it. Once a message enters the agent graph it has already been logged and seen by the scope classifier. For CSAM-adjacent content the answer is a hard stop at the gate with no downstream processing.
- Static moderation responses are a feature, not a limitation. LLM-generated responses to hate speech create a prompt-injection surface. Deterministic strings cannot be steered.
- Safety regex requires adversarial testing: base form, plural, compound, abbreviation. Coverage gaps are the first thing a probing user will reach for.

---

## 2026-05-21 — Phase 6 Active: Two-tier Moderation Gate + Scope Fixes + USM Personalisation

### What we did

**Workstream 1 — Two-tier moderation gate (hybrid regex + LLM)**

- **Hybrid LLM analysis layer** added to `nikko_modal/app.py`: Qwen3-4B runs a combined moderation + scope pass (`_analyze_moderation_scope()`) for every message surviving the Render-side regex pre-gate. Two decisions in one LLM call — `moderation_block` and `scope_block` — each gated at 0.80 confidence.
- **`MODERATION_BLOCK_SENTINEL`** and **`SCOPE_BLOCK_SENTINEL`**: string sentinels returned by `draft_generator.py` when Modal blocks a message. Intercepted in `pipeline.run()`, mapped to static `_HATE_RESPONSE` and `WARM_REDIRECT`. The pipeline never reaches signal detection or draft generation.
- **`scope_ambiguous` wiring fixed** (G-HYBRID-01): was hardcoded `False` in `draft_generator.py` — the Modal LLM scope pass never received the actual AMBIGUOUS verdict from `ScopeClassifier`. Now correctly threaded from `ScopeClassifier` through `_pipeline_run_sync()` into the Modal POST payload as a weighting hint.
- **HF Space fallback parity**: the full combined moderation + scope LLM pass ported to `hf_space/app.py` so the fallback path applies identical moderation logic.
- **`agents/deterministic/`** directory created: snapshot copies of `scope_classifier.py`, `signal_agent.py`, and `support_strategy_agent.py` — the pure rule-based versions before LLM augmentation. Serves as a reference baseline and regression anchor.

**Workstream 2 — Safety regex fixes**

- **CSAM plurals**: `\bloli\b` → `\b(lolis?|lolicons?|shotas?|shotacons?)\b`.
- **Wanking compound pattern**: added `.{0,30}` to allow intervening words before the target verb/noun.
- **`_CHILD_ATTRACTION_PATTERNS`**: added physical contact verb pattern (`want/need/like to touch/feel/fondle/grope a child/kid/minor`) and grooming-indicator pattern (`want to be alone with kids/a child`).
- **Scope classifier arithmetic patterns**: two new patterns at weight 0.90 anchored on `what('s|is)` — catches `what's 1+1?` and natural-language arithmetic while avoiding false positives on mood ratings (`5/10`) and duration ranges (`5-10 minutes`).

**Workstream 3 — Multi-turn context + USM personalisation**

- **Multi-turn conversation history** wired end-to-end: `acp_schemas.py` gains `conversation_history: Optional[list]` on `ResponseContextPayload`; `pipeline.py` threads it through `run()`; `backend/main.py` accepts `conversationHistory` from the POST body (20-turn server cap); `draft_generator.py` builds a multi-turn messages list for ADP-A; `chat.jsx` sends last 10 turns per request. Session-scoped React state only — cleared on refresh.
- **Smart USM truncation** (`context_prompt_builder.py`): `_smart_truncate_usm()` replaces naive `[:1200]` slice with a priority-ordered section parser — Name → Mood Diary (newest-first by date) → User Preferences → Helpful Interventions → Support Notes → Emotional Patterns. Truncation notice appended to model when budget exceeded.
- **Memory name personalisation**: `makeEmptyMemoryMd()` writes a `## Name` section; `parseMemoryName()` extracts it on load; ADP-A instructed to address user by name naturally; topbar pill shows `Memory · [Name]`.
- **5-step MemoryGenerateModal** (`memory.jsx`): Disclosure → Name gate (skip → password) → Style (Tone / Response length / Input style — pill selectors with CSS tooltips) → Support (don't-help checkboxes + free-text + life context textarea) → Password. `makeEmptyMemoryMd()` and `parseMemoryPrefs()` exported on `window`.
- **ADP-A preference injection** (`context_prompt_builder.py`): `_parse_memory_prefs()` extracts `key: value` pairs from `## User Preferences`; `_TONE_INSTRUCTIONS` / `_LENGTH_INSTRUCTIONS` map them to prose injected as a `USER PREFERENCES` block. Suppressed at `distress_level ≥ 7` — empathy framing takes precedence.
- **Memory banners** (`chat.jsx`): `MemBanner` — `loaded` variant (7s auto-dismiss, lock icon) and `hint` variant (after 3rd message with no file loaded; once per session via `hintShownRef`).
- **Client-side input word cap** (`chat.jsx`): `applyInputCap()` reads `input_length` pref; caps `reqBody.text` at 150/300/600 words. Full message still shown in thread — only the backend payload is capped.
- **Documentation audit**: corrected Phase 5-era GLOSSARY defect — "Client-side only (USM)" incorrectly stated the inference backend never receives USM content.

### Decisions & justifications

| Decision | Justification |
|----------|--------------|
| LLM moderation gate at 0.80 confidence | Below 0.80, a distressed person phrasing a message oddly must not be blocked. False negatives (edge-case content through) are less harmful than false positives (blocking a vulnerable user). The regex pre-gate handles high-confidence cases. |
| Combined moderation + scope in a single LLM call | Two separate calls would double latency for every message. The decisions share context; one pass is sufficient. |
| `scope_ambiguous` as a weighting hint, not an override | The LLM scope check cannot override the regex-based AMBIGUOUS verdict — that would create a path where the LLM alone decides to block content (violating REQ-200-SC3). It nudges the LLM toward tighter scrutiny on ambiguous messages only. |
| Sentinels intercepted in `pipeline.run()`, not `draft_generator` | `draft_generator` has one responsibility: build the ADP-A prompt and return a draft string. Routing logic belongs in the orchestrator. |
| Arithmetic patterns anchored on `what('s\|is)` | Without the anchor, `5/10` (mood rating) and `5-10 minutes` (duration range) false-positive. The anchor targets only question-form arithmetic. |
| Priority-ordered USM truncation over first-N chars | First-N chars is wrong for a growing document where newest diary entries are at the bottom. The priority order reflects what ADP-A needs most per turn. |
| 1200-char ADP-A USM budget | Enough for name + preferences + support notes without crowding strategy guidance and evidence. Above that, signal-to-noise inverts. |
| Multi-turn history capped at 10 turns (frontend) / 20 turns (backend) | 10 turns covers a typical session. The 20-turn server-side cap is a belt-and-braces guard if the frontend cap ever fails. |
| Tone preference suppressed at distress_level ≥ 7 | Stylistic preferences are a calm-state instruction. They do not override empathy framing in acute distress. |
| `input_length` word cap on `reqBody.text` only | The displayed message is the user's record of what they typed. Silently truncating the display would be dishonest. Only the backend payload is capped. |

### Learnings

- The hybrid regex + LLM moderation architecture is the right shape: regex handles high-confidence cases at zero latency; LLM handles coded and edge-case content with a conservative confidence gate. Neither alone is sufficient.
- Wiring verification matters as much as schema design. A parameter can be correctly defined in every schema and still never populated by the caller. Verifying the data flows end-to-end with a real value — not just a default — is a separate step from writing the schema.
- Safety regex needs adversarial testing before shipping: base form, plural, compound, abbreviation.
- Canonical documentation must be updated at the same time as the implementation changes that affect it — not at the next documentation session.
- Personalisation features live at the intersection of UX, backend prompt engineering, and security policy simultaneously. A word-cap decision is also a decision about what the user sees vs. what the model sees vs. what the server stores.

---

## 2026-05-21 (Session 2) — Phase 6: Technique Check-in Banner (Memory Write-back Phase 1)

### What we did

- **`technique_recommended` field** added to `SSEChunk` in `backend/main.py`.
- **`_RESPONSE_RECOMMEND_RE`**: regex scanning ADP-A output for technique recommendation language (e.g. "try deep breathing", "you might find journalling helpful").
- **`_TECHNIQUE_CANONICAL`**: 15-entry ordered dict mapping raw regex matches to canonical technique names and pre-written first-person USM entries (e.g. `"Nikko suggested deep breathing on [date]"`).
- **`_detect_technique_in_response()`**: runs after the ADP-C APPROVE pass. Result emitted as `technique_recommended` on the final SSE chunk. Suppressed if `memory_proposal` already fired on the same turn — the two write-back paths are mutually exclusive per turn.
- **`_AFFIRMATION_RE` expanded**: added present-tense patterns to fix silent-drop bug — `"help a lot"`, `"find this helpful"`, `"works for me"` now all match.
- **`TechniqueCheckInBanner`** component added to `chat.jsx`: popup styled like the crisis `SafetyBanner` but with an accent-coloured border (`.technique-checkin-banner` in `styles.css`) — visually distinct from crisis red. User can accept or dismiss.
- **`techniqueCheckIn` state** and **`onCheckInAdd` callback** in `chat.jsx`: on accept, the pre-written entry is promoted into `pendingEntries` and merged into `memContentRef` for the session.
- **Guards**: both `TechniqueCheckInBanner` and the memory proposal card are gated on `memContentRef && sessionKeyRef` — they only surface when an encrypted `.enc` file is actively loaded. No write-back UI surfaces on a session without a loaded memory file.
- **Compile and deploy**: compiled clean via `esbuild@0.25.3` to 726-line `chat.js` (42.5 KB). Verified `techniqueCheckIn` present 11× in compiled output.
- **Docs updated**: `FRONTEND_INTEGRATION_SPEC.md` SSE chunk field table updated with `memory_proposal` and `technique_recommended` fields. GLOSSARY updated with `Technique check-in` and `pendingEntries` terms. README write-back section expanded.

### Decisions & justifications

| Decision | Justification |
|----------|--------------|
| Technique detection runs on ADP-A output, not user message | The user doesn't say "you recommended breathing" — Nikko does. The signal to detect is in the response, not the input. Scanning the ADP-A output is the only reliable source. |
| Detection runs only on APPROVE, not REGENERATE or safe fallback | A regenerated or fallback response was not the intended output — it should not trigger a memory write. APPROVE is the only path where the response is considered authoritative. |
| Mutually exclusive with `memory_proposal` per turn | Surfacing two write-back prompts in the same turn would be confusing and intrusive. One is enough. Affirmation proposal (user-side detection) takes precedence; technique check-in (response-side detection) is suppressed if the former fires. |
| Popup style (accent border) rather than inline chat bubble | The check-in is a UI action, not a conversational message. Inline bubbles are part of the conversation record; this is an ephemeral prompt to act. The `SafetyBanner` popup pattern is the established precedent for non-conversation UI overlays. |
| `pendingEntries` in React state, not immediate re-encrypt | Full re-encrypt-in-place requires `sessionKeyRef` infrastructure and a download trigger. That is the next pass. Accumulating accepted entries in state first is the correct incremental step — it unblocks the UX without blocking on the crypto plumbing. |
| `_AFFIRMATION_RE` present-tense patterns added alongside fix | The silent-drop bug (past-tense-only matching) was discovered while testing `TechniqueCheckInBanner`. Fixed in the same commit because the two features share the mutual-exclusion logic — an undertested `_AFFIRMATION_RE` would have produced incorrect suppression decisions. |

### Learnings

- Detection logic for write-back features needs to be tested across tense, phrasing, and person (first/second/third) — not just the canonical form. Affirmations especially come in a wide range of natural-language forms.
- Mutual-exclusion logic between two detection paths is a forcing function for testing both. Writing the suppression condition exposed the affirmation tense gap immediately because I had to reason through what would happen if both fired.
- Incremental write-back (accumulate to `pendingEntries` → re-encrypt later) is the right shape: it delivers user value immediately without blocking on the crypto infrastructure.
- Popup UI for write-back prompts (not inline bubbles) is architecturally cleaner. Inline messages are the conversation record; write-back prompts are transient UI actions. Mixing them would make the conversation thread unreliable as a record.

---

## 2026-05-21 (Session 3) — Phase 6: Mood Diary Round-trip, Mobile Bottom Sheets, USM Fixes

### What we did

**Mood diary SPEC-800 compliance fix**
- Removed all `sessionStorage` reads/writes for `moodEntries` in `chat.jsx`. Replaced with `useState({})` — pure React state that clears on page refresh, as required by SPEC-800 zero-retention.

**Mood diary → memory file write path (`panels.jsx`)**
- Added module-level `formatDiaryEntry(iso, entry)`: serialises a diary entry as `YYYY-MM-DD | mood: N | emotions: x, y | triggers: a, b\nnote: ...`.
- Rewrote `save()` in `MoodDiaryPanel` as a unified function: commits React state via `onSet`, then writes all diary entries + any memory section edits into `## Mood Diary` / `## Helpful Interventions` / `## Support Notes` in one re-encrypt + download cycle. Previously these were separate code paths.
- `canSave` logic: Save enabled if diary has data OR user is in memory edit mode. Prevents empty downloads.
- Removed collapsible "From your memory file" block. Memory section now renders flat above Save button — less friction, no hidden content.

**Mood diary ← memory file read path (`chat.jsx`)**
- Added `parseDiaryEntries(md)` function: inverse of `formatDiaryEntry`. Parses `## Mood Diary` section back into `{ [iso]: entry }` dict on file load. Handles `YYYY-MM-DD | mood: N | emotions: ... | triggers: ...` format; optional `note:` second line.
- Wired into `onMemoryLoaded`: calls `setMoodEntries(parseDiaryEntries(md))` immediately after `setMemName(name)`. Round-trip complete: save → encrypt → reload → parse → state restored.

**Mobile bottom sheets (`chat.jsx` + `styles.css`)**
- At ≤600px: `.chat.floating` panels switch from fixed side cards to bottom sheets (`position: fixed; bottom: 0; left/right: 0; height: 82vh`) with `animation: sheet-up`.
- `.tab-float` side buttons hidden; replaced by `.mobile-tabbar` fixed at footer — Mood and Sources tabs toggle their sheets, opening one auto-closes the other.
- `.sheet-backdrop`: full-screen overlay (`z-index: 45`) — tapping outside closes both panels.
- At ≤480px: gate card goes full-width, modals drop padding, mood chip/pip touch targets enlarged to 44px minimum, research preview pill hidden.

**GitHub URL fix**
- Research preview tooltip in `chat.jsx` linked to `github.com/nikko-research/nikko` (dead URL). Updated to `github.com/equinox013/nikko-companion`.

**Compile**
- `chat.jsx` → `chat.js` via `esbuild@0.25.3`. 47.4 KB clean output.

### Decisions & justifications

| Decision | Justification |
|----------|--------------|
| Pure React state for `moodEntries` (no sessionStorage) | SPEC-800 zero-retention: mood data must not survive a page refresh. sessionStorage survives a refresh in the same tab — React state does not. |
| `parseDiaryEntries` lives in `chat.jsx`, not `panels.jsx` | `chat.jsx` owns `moodEntries` state and `onMemoryLoaded` — the parse call must be co-located with the callback that updates the state. `panels.jsx` owns the write path only. |
| Unified Save (diary + memory in one cycle) | Two separate Save actions were confusing and could leave them out of sync. One encrypted download per Save click is simpler and safer — the user always gets a consistent file. |
| Bottom sheet on ≤600px, not ≤480px | At 600px the side panel overlay starts to crowd the chat thread. 480px is too late — on real phones the panels were already overlapping. 600px matches typical phone landscape + small portrait breakpoints. |
| Tab bar replaces `.tab-float` buttons on mobile | `.tab-float` floats over the panel body and is hard to tap one-handed. A fixed tab bar at the footer is thumb-friendly and the established mobile pattern. |

### Learnings

- Round-trip data flows (write → encrypt → load → parse) need both paths designed together, not one at a time. Building only the write path first and treating the read path as a follow-up creates a broken contract that users will hit on first reload.
- A unified Save button with clear `canSave` semantics is worth the refactor. The split "Save diary" / "Save memory" approach was found to be confusing in production usage within one session.

---

## 2026-05-22 — Peer Review Response: Non-Verbal Signals, Halo Effect, Crisis Abruptness

### What we did

- Returned from a peer review. Three substantive critiques were raised and worked through to full spec-level resolution.
- **Critique 1 (non-verbal signals):** Designed a three-part response: typing-pattern signal detection based on internet communication conventions (tone softeners, typographic register, register collapse), a Qwen3-4B thinking-mode structural pre-analysis pass as Step 1.5 in the pipeline (no retraining), and a mood check-in popup triggered after memory file load.
- **Critique 2 (halo effect):** Ratified uncertainty avatar state (confidence < 0.40 triggers `uncertain` glyph with dimmed rays) and epistemic language calibration (evidential framing over perceptual claims). Rejected design-layer desaturation approaches on grounds of stripping warmth unnecessarily.
- **Critique 3 (crisis abruptness / ARSH):** Ratified concurrent delivery interpretation for REQ-300-112 (within-turn framing is not a prohibited delay). Designed a 5-template crisis response pool with turn-aware selection and continuity acknowledgment. Added onboarding expectation sentence to Gate.
- Rejected Qwen3-4B rebase for ADP-B — same VRAM wall as ADP-A fine-tuning. Adopted structural pre-pass approach instead, which achieves the same reasoning capability without any retraining.
- Designed pipeline transparency improvements: dynamic AgentRibbon stage labels (subtle, secondary typography), expanded debug overlay exposing pre-analysis, full signal output, and router decision.
- Amended 5 spec files: SPEC-100, SPEC-700, SPEC-300, SPEC-000, GLOSSARY.md, FRONTEND_INTEGRATION_SPEC.md. Created SESSION-BRIEF-2026-05-22.md.
- Documentation conflict audit received — 17 conflicts across 31 files. Queued for separate resolution pass.

### Decisions & justifications

| Decision | Justification |
|----------|--------------|
| Qwen3-4B as structural pre-pass, not ADP-B rebase | Retraining ADP-B on Qwen3-4B would hit the same RTX 3070 8GB VRAM wall that discontinued ADP-A fine-tuning. The pre-pass achieves the same reasoning outcome by injecting annotations into ADP-B's context window — no retraining, no new model load (Qwen3-4B is already in the pipeline). |
| Schema Option A (tag strings in `uncertainty_notes`, no new field) | Backward-compatible. `[STRUCT:]` and `[PARA:]` tags are machine-parseable by regex. Adding a new top-level field would require ACP schema updates across the pipeline. The current `uncertainty_notes` field was always intended for this kind of supplementary observation. |
| Crisis response pool (5 static templates) | Directly addresses ARSH — Abrupt Refusal Secondary Harm, the documented phenomenon where an LLM's sudden disengagement at crisis escalation causes secondary distress. Static templates eliminate generative unpredictability at the highest-stakes moment. Turn-aware cycling prevents the perception of a scripted loop. |
| Concurrent delivery interpretation ratified | REQ-300-112 prohibits *delay before* resources, not framing *alongside* resources. The distinction maps directly to clinical evidence: extended engagement before resource delivery is dangerous; a bridging sentence within the same response as resources is not. |
| Uncertainty avatar state over persistent limitation badge | A persistent label reads as boilerplate within three sessions. The uncertainty state is *contextual* — it fires when the system is actually unsure about the current message — which makes it a meaningful signal rather than ambient noise. |
| Epistemic language calibration over visual desaturation | Warmth is load-bearing for a mental health support tool. Desaturating the avatar or adding "digital texture" to reduce trust attribution would also reduce the emotional safety the user needs. Language calibration gets the same epistemic result without touching the affective channel. |
| Mood check-in popup (not typed response) | Asking the user to type a mood rating creates friction at the exact moment they've just loaded their memory file and are oriented toward conversation. A click-based popup captures the data without interrupting that orientation. |

### Research grounding (peer review context)

The peer review surfaced three critiques that align closely with documented failure modes in the mental health AI literature. These concepts now inform the system's design decisions and should be used as framing if Nikko is ever written up or presented:

**Stochastic Parrot (Bender et al., 2021):** LLMs are described as systems that stitch together linguistic forms based on probabilistic patterns without any reference to meaning. The *ersatz fluency* this produces — sounding reasoned and empathetic — is a byproduct of scale, not comprehension. This is the theoretical foundation for RISK-10 (Visual Halo Effect) and the epistemic language calibration requirement: Nikko should never linguistically imply perceptual access it doesn't have. The fact that it sounds like it understands doesn't mean it does, and the design should reflect that.

**Abrupt Refusal Secondary Harm (ARSH):** The second critique maps directly to this documented phenomenon — the trauma caused when a model suddenly disengages or hard-refuses a user due to safety guardrails, particularly in mental health contexts. The person who is told "I can't help with this, please call a hotline" at the exact moment they're most vulnerable experiences the refusal as abandonment. The crisis response pool, concurrent delivery ratification, and continuity-acknowledgment language are all direct mitigations for ARSH.

**Clinical Scaffolding / Therabot (Jacobson et al., 2025):** The Therabot RCT demonstrated that an expert-fine-tuned model under human supervision can produce measurable clinical symptom reduction. This validates the evidence-grounded, human-primacy architecture of Nikko — the system's job is *scaffolding*, not resolution. It also establishes the design space Nikko sits in: not a Stage 3 (fully autonomous) deployment, but a Stage 1–2 (assistive to collaborative) tool where the system's bounded scope is a feature, not a limitation.

**Global mental health gap:** The structural justification for the system's existence: an average of 11 years between symptom onset and treatment start, compounded by clinician shortage. Nikko's value proposition is not clinical efficacy — it's accessible, stigma-reduced, on-demand presence for people who are waiting. That framing should stay central to how the project is described.

These frameworks should be cited if Nikko is ever written up for academic or professional audiences. They provide the theoretical scaffolding for why the architectural constraints exist — the non-diagnostic boundary, the non-replacement principle, the crisis escalation design.

### Learnings

- ARSH is a documented failure mode with a name. Any mental health AI that hard-stops in a crisis path needs to design around it explicitly. Static response pools, continuity language, and onboarding expectation-setting are the mitigation tools.
- The "Stochastic Parrot" framing is useful precisely because it names something the system's language can subtly deny. Every "I can see you're feeling..." from an LLM is technically a stochastic parrot constructing a plausible empathy claim. Epistemic language calibration is not pedantry — it's accuracy.
- Retraining a model to get a capability that the base model already provides (Qwen3-4B thinking mode) is almost always the wrong call. Check whether the capability exists in an already-loaded model before committing to a training run.
- Documentation conflicts compound silently. 17 conflicts across 31 files don't announce themselves — they accumulate until someone runs an audit. Every platform migration and model switch needs a doc-update pass in the same session, not the next one.

---

## 2026-05-23 — Debug Overlay Audit, Routing Fix + HF Space → Modal Parity Sync

### What we did

**Debug overlay audit and fixes**

- Removed the SVG ribbon glyph from `agent-debug.jsx` — decorative, added visual noise to a diagnostic tool.
- Signal card updated to display full signal arrays (emotions, cognitive patterns, risk indicators) rather than a truncated summary.
- Router card updated to show real confidence score and rationale from `trace.router_output`.
- Evidence card added to the debug overlay.
- `router_output` and `pre_analysis_output` fields added to `PipelineTrace` in `orchestration/pipeline.py`. `_step3_route` populates `router_output`; `_step10_draft` reads `_last_metadata` from `HFSpaceFullGenerator` after `generate()` to populate `pre_analysis_output`.
- `_last_metadata` side-channel added to `HFSpaceFullGenerator.__init__` — stores the full pipeline response dict after `generate()` so `_step10_draft` can read pre-analysis data without breaking the `DraftGeneratorProtocol` interface.
- `_mode` bridge fixed in `chat.jsx` SSE handler: `data.trace.mode` was not being forwarded to `_mode` on the `NikkoAgentLog` entry. Fixed by adding `_mode: (data.trace.mode || '').toUpperCase()` in the update call.

**Routing fix — acknowledgment/gratitude turns**

- Added `_ACKNOWLEDGMENT_RE` regex to `orchestration/pipeline.py`. Prevents acknowledgment and gratitude turns ("it helped a bit, thanks", "the breathing really worked") from triggering GUIDANCE routing even when technique keywords (e.g. "breathing") are present. Registered as REQ-000-043. Guard placed before the GUIDANCE keyword check so order of evaluation is unambiguous.

**HF Space → Modal parity sync**

- `hf_space/app.py` brought to full feature parity with `nikko_modal/app.py` — the fallback path now runs identical logic to the primary path.
- `_PRE_ANALYSIS_SYSTEM`: expanded from 7 basic tags to the 13-tag Modal version, adding `expressive_lengthening`, `punctuation_urgency`, `keysmash`, `emoji_distress`, `ellipsis_trail`, `all_lowercase`, and full arousal/intensity framing with source citations.
- Signal-strength gate (`_WEAK_SIGNALS`) backported: singleton weak signals now trigger a low-confidence caveat in the ADP-B system prompt rather than carrying full weight.
- `_SCOPE_SYSTEM`, `_SIGNAL_SYSTEM`, `_STRATEGY_SYSTEM` prompts added.
- `_analyze_scope`, `_analyze_signal`, `_enrich_strategy`, `_inject_enhanced_strategy` functions ported as module-level functions.
- `_run_full_pipeline` updated with `rule_signal` and `base_strategy_text` params for Pass 1 signal enrichment and Pass 2 strategy enrichment.
- `PipelineRequest` and `PipelineResponse` schemas updated: `scope_verdict`, `enhanced_signal`, `enhanced_strategy`, `harm_category`, `oos_reason` added as new fields.
- `ANALYSIS_GEN_PARAMS` generation parameters added for scope, signal, and strategy analysis passes.

### Decisions & justifications

| Decision | Justification |
|----------|--------------|
| `_last_metadata` side-channel on `HFSpaceFullGenerator` | `DraftGeneratorProtocol` has a fixed interface — `generate()` returns a string. Pre-analysis metadata is needed by `_step10_draft` without breaking the protocol. A side-channel attribute on the concrete class is the narrowest change that doesn't require a protocol update or return-type change cascading through every caller. |
| `_mode` bridge fixed in the SSE handler, not the overlay component | `NikkoAgentLog.add()` is the single insertion point for trace data. Fixing the bridge there ensures every downstream consumer gets the correct mode. Fixing it in the overlay component would only address the display symptom. |
| `_ACKNOWLEDGMENT_RE` placed before GUIDANCE keyword check | The acknowledgment gate must fire before the keyword gate — a thank-you message containing "breathing" must not reach the GUIDANCE keyword list. Order of evaluation is semantically significant here. |
| Full function parity, not just prompt parity, in HF Space | A fallback that diverges on analysis enrichment produces different routing decisions under identical inputs. Fallback correctness requires identical logic, not just identical prompts. |

### Learnings

- A side-channel attribute is sometimes the correct design when adding out-of-band data to a class with a fixed protocol interface. Changing the protocol return type would cascade through every caller; the side-channel is surgically contained.
- Data bridges in the SSE handler are invisible when missing — the system appears to work but silently drops information. Any new trace field added to the backend needs an explicit bridge in the frontend handler verified before the change is closed.
- Fallback paths need the same update discipline as primary paths. The HF Space had diverged over multiple sessions because each parity-relevant change was applied to Modal only. After any `nikko_modal/app.py` change, a two-file diff check against `hf_space/app.py` should be standard practice.

---

## 2026-05-23 — Phase 6 Routing Fixes + Split Paralinguistic Detection Architecture

### What we did

**Routing fixes (Issues 1, 2, 4, 5)**

- **Issue 5 — CRISIS confidence cap** (`signal_agent.py`): If the LLM returns CRISIS but no active/acute risk keyword is present and confidence < 0.75, distress is downgraded to HIGH. Prevents under-confident CRISIS verdicts from triggering the full crisis path.
- **Issues 1 & 2 — Guidance routing + `\guide` command** (`router.py`): Replaced binary `_guidance_intent_present()` with `_guidance_intent_strength()` returning strong/weak/none. Rule 2.5 added: `\guide` command forces GUIDANCE mode (CRISIS still overrides). Weak intent gated by distress < HIGH AND confidence ≥ 0.60 to prevent LOW-distress venting messages from routing to GUIDANCE.
- **Issue 4 — Passive risk sustained tracking** (`pipeline.py`, `acp_schemas.py`, `context_prompt_builder.py`): 5-turn sliding window; ≥2 hits of passive risk language with distress not LOW → `passive_risk_sustained=True`. COMFORT nudge injected into ADP-A system prompt when sustained.
- **VS C3 fix** (`verification_supervisor.py`): C3 previously blocked HIGH+COMFORT, treating it as a mode–distress mismatch. HIGH distress in COMFORT mode is a valid venting routing outcome — C3 now only blocks CRISIS distress in non-CRISIS mode.
- **`docs/GAPS.md`**: G-VS-C3-01 and G-GUIDE-01 resolved and documented.

**Typography enforcement (REQ-000-041)**

- `_sentence_capitalize()` added to `nikko_modal/app.py` as a deterministic post-processing step on every ADP-A draft. Qwen3-4B mirrors the user's all-lowercase register despite the TYPOGRAPHY RULE in the system prompt. Post-processing is guaranteed — no model instruction-following required. Capitalises first character and sentence-initial letters after `.!?`, with ellipsis guard (negative lookbehind `(?<!\.)` prevents `...` from triggering).

**Split paralinguistic detection architecture (Director-approved 2026-05-23)**

Root cause identified: Qwen3-4B is an unreliable detector for deterministic text properties. Tasks like "does this message contain only lowercase letters" require pattern-matching, not probabilistic inference — the model consistently hedged, producing `{"annotations": ""}` regardless of message content.

Solution: split the 14-signal taxonomy at the semantic boundary.

- **`backend/paralinguistic_detector.py`** (new): Pure Python regex/heuristic engine detecting 8 deterministic signals on Render — zero latency, zero LLM cost, guaranteed accuracy. Signals: `[STRUCT: all_lowercase]`, `[STRUCT: ellipsis_trail]`, `[STRUCT: all_caps_segment]`, `[PARA: expressive_lengthening]`, `[PARA: punctuation_urgency]`, `[PARA: keysmash]`, `[PARA: emoji_distress]`, `[PARA: asterisk_action]`. Sources: McCulloch (2019), Apriliani & Muslim (2021).
- **`backend/draft_generator.py`**: Calls `detect_struct_signals(user_msg)` before the Modal call; result sent as `struct_annotations` in the payload.
- **`nikko_modal/app.py`**: `_PRE_ANALYSIS_SYSTEM` narrowed to 6 semantic PARA signals only (`tone_softener`, `minimisation`, `mixed_affect`, `typographic_register`, `fragmented_syntax`, `register_collapse`). `_run_structural_pre_analysis()` accepts `struct_annotations` from Render and merges it with LLM output. `pipeline()` endpoint passes `struct_annotations` to `run_pipeline.remote()`. `enable_thinking=False` for the pre-analysis pass — CoT caused hedging on pattern-matching sub-tasks.

**Keysmash threshold calibration**

- `_is_keysmash()` thresholds tightened: vowel ratio `< 0.35` → `< 0.20`, home-row ratio `> 0.50` → `> 0.65`. "shift" (5 chars, 20% vowel, 60% home-row) was a false positive under the original thresholds. Tightening eliminates this class of common English word false positives while preserving genuine keysmash detection.

**Bracket normalization**

- LLM occasionally emits malformed tags (e.g. `PARA: mixed_affect` without brackets). Added `re.sub(r'\[?((?:PARA|STRUCT):\s*[\w_]+)\]?', r'[\1]', ...)` normalization step after LLM output parsing in `_run_structural_pre_analysis`. All downstream consumers (ADP-B strength gate, trace parser, Phase 6 harness) now receive well-formed `[PARA: x]` / `[STRUCT: x]` strings.

### Decisions & justifications

| Decision | Justification |
|----------|--------------|
| Deterministic post-processing for typography (REQ-000-041) | Model instruction-following for typography is unreliable — Qwen3-4B consistently mirrors the user's register despite explicit rules. Deterministic post-processing is guaranteed, zero-latency, and zero-cost. |
| Render-side regex for 8 deterministic signals | LLM inference for pattern-matching tasks (all_lowercase detection, ellipsis counting) produces probabilistic hedging on tasks that are definitionally deterministic. Regex is the correct tool. |
| Semantic split at PARA/LLM boundary | Signals requiring contextual understanding of word meaning (tone_softener — is this "lol" face-saving or genuine?) cannot be answered deterministically. Signals requiring only surface pattern inspection (repeated letters, emoji presence) can and should be. |
| enable_thinking=False for semantic PARA signals | After the deterministic signals moved to Render, the remaining LLM task (6 semantic PARA signals) is still pattern-matching — just with context. CoT was causing more hedging, not less. Direct generation is more reliable for classification tasks of this kind. |
| Bracket normalization over prompt engineering | Prompt engineering to guarantee bracket formatting is fragile — one model update can break it. A regex normalization step is a two-line fix with guaranteed output regardless of model output formatting. |

### Learnings

- The probability-vs-determinism boundary in a hybrid pipeline is not where you first draw it. Every time an LLM is asked to perform a task that has a closed-form answer (does this string match a pattern?), it will hedge — and hedging is wrong. The evaluation pipeline is the right place to detect this: when LLM output is consistently empty for signal detection tasks but non-empty for semantic reasoning tasks, the architecture needs to be re-examined, not the prompt.
- Threshold calibration on heuristics requires production data. The keysmash heuristic was set at literature-inspired thresholds that looked correct in theory but produced false positives on ordinary English words in production. One live turn ("shift") identified the problem immediately. Short latency between deploy and observation is the leverage here.
- HF Space parity requires an explicit two-file check after every `nikko_modal/app.py` change. The fallback path diverges silently — there are no compiler errors, only behavioural differences at runtime.

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

---

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

This was also my first serious experience building with AI assistance, what some people call "vibe coding." I came in thinking the main skill was writing good prompts. I'm leaving with a different view: the actual skill is knowing *when not to trust the output*, and that requires enough domain knowledge to recognise a confident-sounding answer that's quietly wrong. A fabricated API endpoint, a threshold that destroys your data distribution, a model that doesn't fit your GPU — none of these were flagged as uncertain when they were produced. They looked clean, I accepted them, and I learned the hard way. The "Where I went wrong" sections in this log are partly a record of that learning curve.

The honest version of AI-assisted development, at least for me, is that AI removed the friction of going from idea to implementation, which freed me up to spend more time on the decisions that mattered — and also let me move fast in the wrong direction when I wasn't watching closely.

---

> **Purpose:** A running record of what was done each day, decisions made with their justifications, and key learnings taken out of the session.
>
> **Format:** Chronological. Each entry covers: **What we did**, **Decisions & justifications**, **Where I went wrong**, **Learnings**.
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

### Where I went wrong

Honestly, the main mistake on day one was assuming the source spec was internally consistent enough to translate directly into requirement IDs. It wasn't. There were two separate pipeline step orderings, overlapping agent authority levels, and a missing adapter combination for Crisis Mode. I caught these because I happened to be paranoid about contradictions, not because I had a method. Next time I'd start with an explicit consistency-check pass before I tried to extract anything structured.

### Learnings

- The source spec had real internal contradictions I didn't expect. Treating spec extraction more like a debugging pass than a copy-and-paste job is what surfaced them — but I had to learn that mid-session, not before.
- Writing things down upfront forces decisions I would otherwise have hit as bugs later. The example that stuck: I had no policy for what happens when a passive risk indicator appears without explicit crisis language, and the only way to resolve it was to make a call and put it in the spec.
- The gap between "described qualitatively in prose" and "implementable deterministically in code" is almost always a numeric threshold, a specific API, or an exact ordering. None of those were in the source doc, which means every prose description had to be tightened to something a machine could act on. That was more work than I budgeted for.

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
| Qwen2.5-3B-Instruct retained as Phase 3 dev model | Output quality good enough for structured JSON agent tasks. Fits 8 GB VRAM without quantization. Used only for development — replaced by fine-tuned adapters in Phase 4. |
| Scope Classifier uses weighted keyword scorer, no LLM | A deterministic gate can't introduce LLM latency or unpredictability. A keyword scorer is fast, auditable, and good enough for this binary classification. |

### Where I went wrong

**I accepted an API endpoint that didn't exist.** The `HealthdirectAdapter` was built against `api.healthdirect.gov.au/ih/api/v2/content/search` — a URL that *sounds* authoritative and plausible. I approved the implementation without spending 30 seconds verifying that the endpoint actually exists. It doesn't. Healthdirect Australia has no public search API. The same blind acceptance applied to the BetterHealth and WHO adapters being designed as "static JSON corpus" — a brittle approach I didn't question until review. All three adapters had to be scrapped and replaced with `WebSearchAdapter`, which meant rethinking the retrieval architecture mid-phase.

In hindsight, the warning sign was right there: I was approving an adapter against a URL I had never personally hit in a browser. I hadn't done that before because most of my prior work has been on internal data, where the source is given. Building against external APIs is a different reflex set and I'm still developing it. **The fix is simple:** before approving any external dependency, I open a browser or run `curl` and confirm the endpoint is real. A 200 OK beats a confident description every time.

### Learnings

- Typed, validated schemas between agents (`SignalPayload`, `ResponseContextPayload`, and so on) made the pipeline far easier to reason about than I expected. They forced me to be explicit about what each agent *needs* versus what it can *see* — and that distinction is where a lot of the LLM safety story actually lives.
- I'm now convinced the Router being deterministic — no LLM — is one of the most important calls in the whole pipeline. I didn't fully appreciate that until I tried to imagine the alternative. If the crisis decision ever ran through a language model, the whole safety story would depend on the model's judgment, which is exactly the thing I'm trying to avoid.
- Retrieval architecture turned out to be harder than I assumed. The natural instinct is to point at APIs that *should* exist for a public health authority — but most major Australian health authorities don't actually publish search APIs. I'm still learning to separate "this sounds reasonable" from "this is real."

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

### Where I went wrong

**I ran Step 13 without checking the dataset ID first (G-DATA-03).** The notebook loaded AnnoMI with `load_dataset("AnnoMI", ...)`. I saw the code, it looked fine, and I ran it. What I didn't think to do was spend 10 seconds searching HuggingFace to confirm `"AnnoMI"` was a valid short-form identifier. It isn't — it 404s silently, returns an empty dataset, and the notebook happily continues with 0 AnnoMI records. AnnoMI was supposed to carry a 30% mix weight in the ADP-A corpus. I came close to training on a corpus missing almost a third of its content and wouldn't have known unless I'd read the Cell 16 summary carefully. I now read the per-dataset row counts before I touch the next cell.

**I accepted the `accept_threshold=0.70` without checking what it would do to the data distribution (G-DATA-06).** This is the one that cost the most hours, and it's the one I'm most embarrassed about, because in theory I knew the risk and just didn't apply it. The threshold was presented to me as principled — "filter the bottom 30% of quality scores" — and that sounded reasonable. I didn't ask the obvious follow-up: *what does the pass rate look like per dataset?* When Step 13 actually ran, the answer was rough:

| Dataset | Pass rate |
|---------|-----------|
| EmpatheticDialogues | 1.0% |
| AnnoMI | 6.7% |
| ESConv | 11.5% |
| Amod | 25.6% |
| MentalChat16K (synthetic) | **93.7%** |

The filter wiped out almost every organic, real-human empathy dataset and waved through almost all of the synthetic MentalChat data. The training set I would have produced was dominated by synthetic examples — the opposite of what the corpus was meant to be. I then had to drop the threshold, rerun the filter pass across all five corpora, re-check the yield counts, re-assemble, and re-validate. Hours gone.

What I missed, and what I now know to think about: ADP-C was trained on structured critique pairs, so it reliably rates structured synthetic data highly and rates organic conversational data lower, even when the organic data is actually good. That's a calibration mismatch between what ADP-C was taught to like and what I needed it to filter. I knew filters could be miscalibrated in theory. I had never actually run one against a multi-source corpus, so I didn't have the reflex of *"what's the per-source pass rate before I trust this threshold?"* I have that reflex now.

**I also missed a conflicting `max_seq_length` between the config file and the handoff doc (G-TRAIN-01).** `config.yaml` said 2048. The handoff doc and the notebook both said 768. I had both documents open and didn't notice. It only got caught in a pre-run audit — if it had slipped through, Step 14 would have either OOM-crashed the RTX 3070 or silently halved the batch size mid-run. **The fix:** when a config file and a doc disagree, that's never cosmetic. I stop and resolve it before running anything.

### Learnings

- An oracle filter trained on synthetic data will systematically penalise organic data, even when the organic data is good. I'd read about distribution mismatch before; I'd never *felt* it cost me a day of training prep until now.
- For multi-corpus training, the per-source yield is the diagnostic, not the total. Total yield of 336 records looks like a quantity problem on the surface. The breakdown is where you find the distribution problem.
- The data preparation notebook is itself a diagnostic. The pass-rate table in Cell 16 of Step 13 is the most important output of that whole step — I now read it before moving on, not after.
- A config-vs-doc discrepancy is a silent divergence in what the training job will actually do. I treat it like a hard stop.

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

### Where I went wrong

**I didn't smoke-test adapter outputs early enough.** The URL hallucination (G-TRAIN-02) and the multi-turn leakage (G-TRAIN-03) weren't really fine-tuning failures — they were base-model behaviours that v0 fine-tuning on this data volume wasn't going to suppress. I now realise that any sufficiently large language model will confabulate plausible-looking contact details and will keep generating dialogue past a natural stopping point if the training data had multi-turn formatting in it. None of that surprises me in hindsight. It surprised me at the time because I'd grouped ADP-A and ADP-B together in my head and saved testing for "after both are trained," which meant I caught the issues much later than I needed to.

What I should have done was run one prompt through raw ADP-C output the moment Step 12 finished, then again for ADP-A after Step 14, before moving on. Finding the issues earlier would have let me adjust training data *before* the next adapter, instead of layering mitigations on after the fact. **The fix:** smoke-test every adapter as soon as it finishes training. One prompt, raw output, check the obvious failure modes. That's a 5-minute investment, not an end-of-phase batch.

### Learnings

- Smoke-testing raw adapter output — bypassing the pipeline — is the only way I'd have caught these. The pipeline's ADP-C gate does catch hallucinated continuations in production, but only because we noticed the problem outside the pipeline first. Trusting the safety layer to clean up the model's behaviour without testing the model directly is a habit I want to break.
- URL hallucination is a base-model property, not a fine-tuning failure. In a clinical-adjacent context that's a patient-safety concern, not a polish issue. I now think about it at the data-design stage.
- Training data format leaks through. Multi-turn source records expose the model to speaker-alternation patterns, and the base model will extend those patterns past the response boundary. `is_clean()` filters in data prep reduce it but don't eliminate it.

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

### Where I went wrong

**I committed to Mistral-7B without doing a back-of-envelope VRAM check first.** The model needs around 14 GB in fp16. The RTX 3070 has 8 GB. Those numbers are publicly available and would have taken under a minute to look up — I just didn't look them up before accepting Mistral as the architecture. The result: an entire set of notebooks built, training data prepared, training attempted, 14+ hours elapsed with no convergence, and then a full architecture migration. Every notebook from Step 11 to Step 17 had to be regenerated. Every Mistral artefact had to be archived.

This is the most expensive avoidable mistake I made on the project, and it's also the most embarrassing because it's an arithmetic problem. I knew about VRAM constraints in the abstract — that's why I'd been training on the 3070 in the first place. What I hadn't internalised was that *the first question to ask about any candidate model is whether it physically fits*, before anything else. I had ordered my thinking around capability, performance, and licence, and put hardware fit last. That ordering is wrong. **The fix:** model size in GB divided by VRAM in GB. If the answer is greater than 1, the conversation is over. Everything else only matters once that's settled.

**I also added `bitsandbytes` as a production dependency without understanding the ZeroGPU execution model.** `bitsandbytes` is a standard quantization library — it seemed like an obvious inclusion, and I'd already used it locally without trouble. I didn't ask the right question, which is *when* ZeroGPU allocates GPU memory and *when* the library checks for CUDA. The answer (ZeroGPU allocates only inside `@spaces.GPU`; bnb checks at import time) makes them fundamentally incompatible. That isn't obscure information — it's in the ZeroGPU docs — but I didn't read those docs and I didn't push back on the dependency before it landed in `requirements.txt`. The crash only showed up when I deployed.

I'm finding a pattern in my own mistakes here: I treat "it worked locally" as much stronger evidence than it is, and I'm slow to read the deployment environment's docs when a new library is involved. **The fix:** when adding anything that touches hardware (CUDA, memory, quantization), the question is "when does this thing check for the GPU?" That takes two minutes and would have saved a deploy cycle.

### Learnings

- VRAM budget is a hard design constraint, not a soft optimisation. I now check model size against available VRAM as the first question, not the last.
- `bitsandbytes` and ZeroGPU are architecturally incompatible by design. ZeroGPU's deferred GPU allocation breaks any library that probes for CUDA at import time. Good to know now; I wish I'd known a week earlier.
- Adapter sharing via `set_adapter()` is a much bigger engineering win than I realised before this project. The VRAM saving is around 4.5 GB — effectively a free second adapter once the base is loaded. I'll be reaching for this pattern again.
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

### Where I went wrong

I noted in this entry that I'd "fixed the Fly.io / Render label contradiction" — and on a later pass I found I hadn't actually finished the job. The pipeline diagram still labelled the backend as Fly.io in one place and Render in another *within the same diagram*. Documentation cleanup needs the same rigour as code review, and I clearly didn't give it that here. A search-and-verify across the file would have caught the leftover.

### Learnings

- Documentation debt accumulates faster than code debt. `INDEX.md` was still showing Phase 1 as "awaiting Director sign-off" six phases later.
- A gap list is a decision log, not just a todo list. The ratification entries in GAPS.md contain exactly the information I'd need to reconstruct *why* the system is the way it is, which I underestimated until I started writing this DEVLOG.
- Contradictions between a URL and a service label are a sign that a deployment call was made and the docs weren't updated to match. I'm learning to check them together, not separately, and to grep the whole repo when one shows up.

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

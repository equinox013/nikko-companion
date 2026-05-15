# GAPS — Open Questions for the Director

> **Purpose:** every ambiguity, missing variable, and logical fallacy identified during Phase 1 spec extraction. Each gap blocks at least one downstream decision. The Director must rule on each before the dependent phase can advance.
>
> **Format:** ID | severity | summary | recommended default. Detailed discussion follows the table.

---

## Severity legend

| Symbol | Meaning |
|--------|---------|
| 🔴 **Critical** | blocks deployment or violates a charter principle if unresolved |
| 🟠 **High** | blocks an entire phase or spec |
| 🟡 **Medium** | blocks a single feature or sub-requirement |
| 🔵 **Low** | clarity / stylistic |

---

## Summary table

> **Status key:** ✅ RATIFIED · 🔄 DEFERRED · ⏳ OPEN

| ID | Severity | Domain | Summary | Status |
|----|----------|--------|---------|--------|
| [G-P5-001](#g-p5-001--quick-exit-domain-not-in-spec-300) | 🔵 Low | Frontend | Quick-exit navigation target (bom.gov.au) is in FRONTEND_INTEGRATION_SPEC but not in SPEC-300 | ✅ RATIFIED |
| [G-P5-002](#g-p5-002--untraced-frontend-features) | 🟡 Medium | Frontend | Agent debug overlay, first-run tutorial, and suggestion chips have no spec trace | ✅ RATIFIED |
| [G-CRISIS-01](#g-crisis-01--non-australian-users) | 🔴 Critical | Safety / Geo | Public-internet deployment but Australia-only crisis resources | ✅ RATIFIED |
| [G-DATA-01](#g-data-01--no-privacy--data-lifecycle-spec) | 🔴 Critical | Privacy | No privacy / retention / consent spec exists | ✅ RATIFIED |
| [G-PRIVACY-01](#g-privacy-01--audit-trace-pii-handling) | 🔴 Critical | Privacy | Audit traces of mental-health convos have no retention / encryption / deletion policy | ✅ RATIFIED |
| [G-EVAL-01](#g-eval-01--human-evaluator-design) | 🔴 Critical | Eval | Human-evaluator design unspecified — gates Phase 6 / 7 (re-rated from 🟠) | ✅ RATIFIED |
| [G-MEMORY-01](#g-memory-01--conversation-state-store) | 🟠 High | State | Conversation history mandated but no state store defined | ✅ RATIFIED |
| [G-CRISIS-03](#g-crisis-03--demographic-specific-resources) | 🟠 High | Safety | No specialized hotlines (Kids Helpline, 13YARN, QLife, MensLine, 1800RESPECT) | ✅ RATIFIED |
| [G-RECON-02](#g-recon-02--evaluator-vs-verification-supervisor) | 🟠 High | Architecture | Evaluator vs Verification Supervisor scope/order ambiguous | ✅ RATIFIED |
| [G-METRIC-02](#g-metric-02--scoring-rubrics-undefined) | 🟠 High | Eval | Score rubrics (0–1 mappings, judge model, IRR floors) absent | ✅ RATIFIED |
| [G-INFRA-01](#g-infra-01--single-point-of-failure-hosting) | 🟠 High | Infra | HF Spaces is sole hosting, no DR / failover | ✅ RATIFIED |
| [G-SECURITY-01](#g-security-01--no-threat-model) | 🟠 High | Security | No threat model, auth, rate-limit, abuse policy | ✅ RATIFIED |
| [G-CRISIS-02](#g-crisis-02--implicit-risk-classifier-mapping) | 🟠 High | Safety | Implicit / contextual risk indicators have no classifier mapping | ✅ RATIFIED |
| [G-DATA-02](#g-data-02--counselling-corpus-licensing) | 🟠 High | Data | Empathy adapter dataset licenses / consent provenance unspecified | ✅ RATIFIED |
| [G-LOSS-01](#g-loss-01--training-loss-formulation) | 🟠 High | Training | No concrete loss formulation (DPO/RLHF/etc., objective weights) | ✅ RATIFIED |
| [G-RELEASE-01](#g-release-01--adapter--model-release-governance) | 🟠 High | Ops | No model / adapter release-governance, canary, rollback, or model-card policy | ✅ RATIFIED |
| [G-AGE-01](#g-age-01--age-verification--minor-user-policy) | 🟠 High | Compliance | No spec rule on minor users (Online Safety Act AU; GDPR-K / COPPA if international) | ✅ RATIFIED |
| [G-RECON-01](#g-recon-01--distress-level-vs-escalation-level) | 🟡 Medium | Terminology | Distress-level vs Escalation-level unification | ✅ RATIFIED |
| [G-RECON-03](#g-recon-03--passive-risk-elevation-rule) | 🟡 Medium | Safety | When do passive risk indicators elevate to Crisis? | ✅ RATIFIED |
| [G-RECON-04](#g-recon-04--crisis-mode-de-escalation-rule) | 🟡 Medium | Safety | Concrete rule for exiting Crisis Mode | ✅ RATIFIED |
| [G-RECON-05](#g-recon-05--missing-adapter-combination) | 🟡 Medium | Architecture | Crisis "Safety-only" adapter combo absent in SPEC-400 §9 | ✅ RATIFIED |
| [G-RECON-06](#g-recon-06--verification-supervisor-in-crisis-mode) | 🟡 Medium | Architecture | Source skips Verification Supervisor in Crisis Mode | ✅ RATIFIED |
| [G-EVIDENCE-01](#g-evidence-01--peer-review-vs-recency-tiebreak) | 🟡 Medium | Evidence | Tiebreak rule between peer-review and recency | ✅ RATIFIED |
| [G-EVIDENCE-02](#g-evidence-02--retrieval-interface-undefined) | 🟡 Medium | Evidence | Concrete query API for each source not defined | ✅ RATIFIED |
| [G-ENUM-01](#g-enum-01--canonical-signal-enum-missing) | 🟡 Medium | Schema | Signal categories listed prosaically, no machine-readable enum | ✅ RATIFIED |
| [G-THRESH-01](#g-thresh-01--safe-thresholds-undefined) | 🟡 Medium | Eval | "Safe thresholds" referenced but never quantified | ✅ RATIFIED |
| [G-THRESH-02](#g-thresh-02--confidence-bands) | 🟡 Medium | Schema | "Low / moderate / high" confidence bands not numerically defined | ✅ RATIFIED |
| [G-METRIC-01](#g-metric-01--signal-evaluation-rate-targets) | 🟡 Medium | Eval | Numeric targets for missed-crisis-rate etc. unspecified | ✅ RATIFIED |
| [G-MODEL-01](#g-model-01--base-model-licensing-review) | 🟡 Medium | Training | License review for Llama 3 / Mistral candidates not done | ✅ RATIFIED |
| [G-OVERRIDE-01](#g-override-01--manual-override-controls) | 🟡 Medium | Ops | Override authorization, audit, rollback unspecified | ✅ RATIFIED |
| [G-CACHE-01](#g-cache-01--cache-ttl-and-invalidation) | 🟡 Medium | Infra | Cache TTLs and invalidation events undefined | ✅ RATIFIED |
| [G-FRONTEND-01](#g-frontend-01--session-continuity-mechanism) | 🟡 Medium | Frontend | "Session continuity" mechanism unspecified | ✅ RATIFIED |
| [G-RISK-01](#g-risk-01--adversarial-threats-not-enumerated) | 🟡 Medium | Risk | Adversarial threats (prompt injection, training-data poisoning) absent from SPEC-000 risk list | ✅ RATIFIED |
| [G-SCOPE-01](#g-scope-01--topic-scope-enforcement) | 🟠 High | Security | No mechanism prevents off-topic queries passing through the pipeline | ✅ RATIFIED |
| [G-LAYOUT-01](#g-layout-01--repository-spec-folder-location) | 🔵 Low | Layout | `specs/` placement diverges between SPEC-600 §15 and current repo | ✅ RATIFIED |
| [G-MEMORY-02](#g-memory-02--conversation-history-in-router) | 🔵 Low | State | SPEC-700 STEP 3 reuses unresolved memory dependency | ✅ RATIFIED |
| [G-ENV-01](#g-env-01--bitsandbytes-windows-cuda-runtime) | 🟡 Medium | Infra | bitsandbytes CUDA runtime DLL not resolved on Windows dev machine — resolved via `pip install bitsandbytes==0.45.5` | ✅ RESOLVED 2026-05-10 |
| [G-RETRIEVAL-01](#g-retrieval-01--retrieval-adapter-architecture-change) | 🟡 Medium | Architecture | Director-directed replacement of 3 grey-lit adapters with WebSearchAdapter | ✅ RESOLVED 2026-05-10 |
| [G-DATA-03](#g-data-03--annomi-huggingface-dataset-identifier-mismatch) | 🟡 Medium | Training | Step 13 loads `"AnnoMI"` but registry URL is `to-be/annomi-...`; if wrong, 30% of ADP-A corpus is lost | ✅ RESOLVED 2026-05-11 |
| [G-TRAIN-01](#g-train-01--adp-a-max_seq_length-discrepancy) | 🟡 Medium | Training | `adp_a_empathy/config.yaml` sets `max_seq_length: 2048`; handoff doc and Step 13 Cell 22 say 768 — Director ruling required before Step 14 | ✅ RESOLVED 2026-05-11 |
| [G-DATA-06](#g-data-06--adp-c-threshold-calibration-mismatch) | 🟡 Medium | Training | ADP-C `accept_threshold=0.70` rejects 88–99% of organic empathy datasets (AnnoMI 6.7%, ESConv 11.5%, EmpatheticDialogues 1.0%). Only MentalChat (synthetic) passes. Threshold lowered to 0.50 — Director-ratified 2026-05-11. | ✅ RESOLVED 2026-05-11 |
| [G-TRAIN-02](#g-train-02--v0-url-and-email-hallucination) | 🟠 High | Safety / Training | ADP-A and ADP-B v0 adapters hallucinate plausible-looking but fabricated URLs and email addresses (e.g. `vesselinquiry@health.gov.au`). Base model confabulation prior not fully overridden by v0 training data volume. | ⏳ OPEN — addressed in Step 17 |
| [G-TRAIN-03](#g-train-03--v0-multi-turn-leakage) | 🟠 High | Safety / Training | ADP-A and ADP-B v0 adapters generate fake User:/Nikko: continuations after the response closes. Caused by multi-turn training format bleed-through. Pipeline VS check mitigates at inference time; root fix requires training data restructure. | ⏳ OPEN — addressed in Step 17 |
| [G-UI-01](#g-ui-01--ai-limitation-disclaimer) | 🟡 Medium | Frontend / Safety | No persistent UI disclaimer communicating that Nikko is AI and may produce inaccurate information. Users may act on hallucinated content (e.g. fabricated contact details) without verification. Recommended copy: "Nikko is AI and can make mistakes. Do not action anything without further checking." | ✅ RESOLVED 2026-05-14 |
| [G-PHASE-01](#g-phase-01--phase-execution-order-reconciliation) | 🟡 Medium | Process | Original spec ordered Phase 5 → 6 → 7. Director-approved revised order: Phase 5 → Phase 7 infra → Phase 6 → Phase 7 sign-off. Rationale: system-tier evaluation requires a live deployed stack. | ✅ RATIFIED 2026-05-12 |
| [G-UI-02](#g-ui-02--agent-debug-ribbon) | 🔵 Low | Frontend | `AgentRibbon` component in chat.jsx has no spec trace. Director ruling: internal debug aid, not a user-facing feature. No spec entry required. | ✅ RATIFIED 2026-05-14 |
| [G-UI-03](#g-ui-03--research-preview-pill) | 🔵 Low | Frontend | "Research preview" status pill in chat header has no spec trace. Director ruling: transparency design choice, not spec-governed. | ✅ RATIFIED 2026-05-14 |
| [G-DATA-07](#g-data-07--spec-800-missing) | 🔵 Low | Privacy | SPEC-800 (data retention) referenced in code comments but document does not exist. Data-retention policy is covered by SPEC-000 §11 and GLOSSARY.md zero-retention principle. Director ruling: no separate SPEC-800 required. | ✅ RATIFIED 2026-05-14 |

---

## Detail

### G-CRISIS-01 — Non-Australian users

**Severity:** 🔴 Critical
**Spec touched:** SPEC-300 §5, SPEC-500 §4.4, SPEC-600 §4.1
**Issue:** The frontend ships at `equinox013.github.io/nikko` (publicly reachable from any country). Crisis mode hard-codes Australian hotlines. A non-Australian user in crisis receives numbers that won't help them.
**Options for Director:**
1. Geo-block non-AU IPs at the frontend, with a static "Nikko is currently available in Australia only" page elsewhere.
2. Detect locale (Accept-Language / IP-geo) and serve a localized resource set; require an international fallback (Samaritans UK, 988 US, befrienders.org global directory).
3. Defer: ship Australia-only with an explicit prominent disclaimer in the UI before chat begins.
**Recommended default:** Option 3 for v0; Option 2 by GA. Charter principle (human safety primacy) eventually requires Option 2.
**[RATIFIED 2026-05-09]:** **[RATIFIED 2026-05-09]:** Option 3 — Ship v0 as Australia-only. A prominent disclaimer MUST appear in the UI before the chat begins, stating that Nikko is currently available in Australia only. International routing (Option 2) is a GA-phase requirement per charter principle (human safety primacy). Tracked in SPEC-300 §5 and SPEC-600 §4.1.

---

### G-DATA-01 — No privacy / data lifecycle spec

**Severity:** 🔴 Critical
**Spec touched:** SPEC-000, SPEC-400 §4, SPEC-600 §9
**Issue:** Nikko handles emotional / mental-health user input. No SPEC defines data retention, anonymization, encryption, consent, deletion-on-request, jurisdiction, or what is permissible to use for training. SPEC-500 §10 forbids "real user data" in evals, but the production pipeline necessarily handles real user data.
**Required outcome:** a new SPEC-800 — Data Lifecycle & Privacy. Should align with Australian Privacy Act (APP-1 to APP-13), and likely GDPR if non-AU users are accepted ([G-CRISIS-01](#g-crisis-01--non-australian-users)).
**Recommended default:** Stop-the-line. Block Phase 4 (training) and Phase 7 (deployment) until SPEC-800 is drafted.
**[RATIFIED 2026-05-09]:** **[RATIFIED 2026-05-09]:** No user input or session data is ever ingested for model training. This is a hard charter constraint, not a configuration option. A clear, plain-language privacy statement MUST be displayed in the UI before the chat begins. SPEC-800 (Data Lifecycle & Privacy) is created as a required deliverable and covers session data handling and the privacy statement. Phase 4 (Training) proceeds on pre-approved open-license corpora only — never on production user data. Phases 4 and 7 are unblocked on this basis.

---

### G-PRIVACY-01 — Audit trace PII handling

**Severity:** 🔴 Critical
**Spec touched:** SPEC-600 §9, SPEC-700 §9
**Issue:** Audit traces preserve full conversation context, signal classifications, and routing decisions. These are de-facto clinical-grade sensitive records. SPEC-600 mandates logging but says nothing about: encryption-at-rest, retention period, access control, deletion-on-request, jurisdictional storage location, breach disclosure.
**Recommended default:** Encrypt-at-rest (AES-256) by default; 30-day retention with auto-purge; access strictly to listed engineering team via audited keys. To be ratified as part of the SPEC-800 outcome above.
**[RATIFIED 2026-05-09]:** **[RATIFIED 2026-05-09]:** Logs are session-scoped and ephemeral. The system MAY maintain operational logs during an active session for observability. All session logs MUST be automatically purged when the user terminates the session. No conversation content, signal classifications, or routing decisions persist beyond the active session. Encryption-at-rest and access control apply to any transient in-session storage. Ratified as part of SPEC-800 scope.

---

### G-MEMORY-01 — Conversation state store

**Severity:** 🟠 High
**Spec touched:** SPEC-100 §12, SPEC-200 §3, SPEC-700 STEP 3, SPEC-600 §4.3
**Issue:** Multiple specs mandate consideration of "conversation history". No spec defines: where state is stored, how long, encryption posture, per-session vs persistent, anonymity model, multi-turn agent re-entry behavior.
**Options:**
1. **Per-session, in-memory only** (no persistence across browser refresh). Lowest privacy risk, weakest temporal awareness.
2. **Server-side ephemeral** (Redis with short TTL, e.g., 24h). Balanced.
3. **Server-side persistent with user account.** Strongest UX, biggest privacy obligation.
**Recommended default:** Option 2 for v0, with explicit user-clearable session.
**Dependency:** ties into [G-DATA-01](#g-data-01--no-privacy--data-lifecycle-spec).
**[RATIFIED 2026-05-09]:** **[RATIFIED 2026-05-09]:** In-memory only. Conversation state lives exclusively in the LLM context window for the duration of the active session. No server-side database, cache (Redis or otherwise), or file-based persistence is used. State is destroyed when the session ends. Consistent with G-PRIVACY-01 ruling. SPEC-700 and SPEC-600 updated accordingly.

**[SCOPE CLARIFICATION 2026-05-09]:** The phrase "no file-based persistence" in this ratification is scoped to **Nikko's server-side infrastructure**. It does not prohibit user-initiated, user-controlled, client-side local file storage. The User Sovereign Memory (USM) feature — specified in [SPEC-850](./specs/SPEC-850-user-sovereign-memory.md) and permitted under [REQ-800-023 through REQ-800-026](./specs/SPEC-800-data-lifecycle-privacy.md#11-user-sovereign-memory-exception) — is an explicitly approved exception operating entirely outside the server perimeter.

---

### G-CRISIS-03 — Demographic-specific resources

**Severity:** 🟠 High
**Spec touched:** SPEC-300 §5 Step 2
**Issue:** Australia maintains specialized hotlines that the spec ignores. A trans-identified user in crisis sees Lifeline; QLife (1800 184 527) would be more appropriate. Same for: Kids Helpline (1800 55 1800), 13YARN First Nations (13 92 76), 1800RESPECT for family violence (1800 737 732), MensLine (1300 78 99 78).
**Options:**
1. Always show all six baseline numbers (cognitive overload risk).
2. Detect demographic signals from prior conversation and route accordingly (privacy risk + classification error risk).
3. Show the four baseline numbers + a "More tailored support" expandable that lists the demographic-specific options.
**Recommended default:** Option 3 — least likely to misclassify, lowest privacy risk, still respects dignity.
**[RATIFIED 2026-05-09]:** **[RATIFIED 2026-05-09]:** Option 3 — baseline 4 resources always visible, demographic-specific resources in a 'More tailored support' expandable. Baseline set: Lifeline (13 11 14), Beyond Blue (1300 22 4636), Suicide Call Back Service (1300 659 467), 000 emergency. Expandable set: QLife (1800 184 527), 13YARN (13 92 76), Kids Helpline (1800 55 1800), 1800RESPECT (1800 737 732), MensLine (1300 78 99 78). No demographic inference or classification required. SPEC-300 §5 updated.

---

### G-RECON-02 — Evaluator vs Verification Supervisor

**Severity:** 🟠 High
**Spec touched:** SPEC-200 §3, §5.6, §5.7; SPEC-700 §6, §7
**Issue:** The two agents have overlapping HIGH authority levels. The source spec describes them in different orders in different places.
**Reconciliation already proposed in specs:**
- **Evaluator** = per-response audit (safety, tone, hallucination heuristics).
- **Verification Supervisor** = system-level audit (routing integrity, evidence-pipeline integrity, cross-spec compliance).
- Order: Evaluator → Verification Supervisor (Evaluator first because content-level checks gate Verification Supervisor's system-level checks).
**Director ruling required:** confirm the proposed scope split, or specify a different one. If they collapse into a single agent, multiple specs need to be revised.
**[RATIFIED 2026-05-09]:** **[RATIFIED 2026-05-09]:** Proposed scope split confirmed. Evaluator = per-response content gate (safety compliance, tone, hallucination heuristics). Verification Supervisor = system-level structural gate (routing integrity, evidence-pipeline integrity, cross-spec compliance). Execution order: Evaluator first, then Verification Supervisor. Both must pass for a response to be delivered. SPEC-200 and SPEC-700 updated.

---

### G-METRIC-02 — Scoring rubrics undefined

**Severity:** 🟠 High
**Spec touched:** SPEC-500 §4, §6
**Issue:** All five scores (ES, SCS, EGS, CHS, AIS) are described conceptually with a weighted final formula, but: no 0–1 rubric per metric; no judge model named; no inter-rater agreement floor; no pass/fail threshold for the final score.
**Required outcome:** rubrics document (likely a SPEC-501) with concrete LLM-as-judge rubrics, calibration set, IRR floor (suggested: Cohen's κ ≥ 0.7 vs human ground truth on a 200-example calibration set), and final-score release threshold (suggested: ≥ 0.85 with no hard-fail conditions triggered).
**[RATIFIED 2026-05-09]:** **[RATIFIED 2026-05-09]:** Recommended defaults ratified with Director veto addition. LLM-as-judge rubrics to be specified in SPEC-501 (Phase 6 deliverable). IRR floor: Cohen's κ ≥ 0.70 on a 200-example calibration set. Composite release threshold: ≥ 0.85 with no hard-fail conditions triggered. Director veto: the Director MAY override a passing automated score or block a failing one based on qualitative review. SPEC-500 updated.

---

### G-INFRA-01 — Single point of failure hosting

**Severity:** 🟠 High
**Spec touched:** SPEC-600 §6.1
**Issue:** Hugging Face Spaces is named as primary inference host. For a safety-critical mental-health system, single-region single-provider hosting is fragile.
**Options:**
1. Accept v0 as research/demo only; document the limitation in the UI; revisit for GA.
2. Add multi-provider failover (HF + Replicate / Modal / Together) with health checks.
3. Self-host on a managed inference endpoint (e.g., Anthropic's, Bedrock) for production while keeping HF Spaces for staging.
**Recommended default:** Option 1 for v0 with explicit "research preview" labelling; Option 2 by GA.
**[RATIFIED 2026-05-09]:** **[RATIFIED 2026-05-09]:** Option 1 for v0. Hugging Face Spaces accepted as sole inference host for the research preview. The UI MUST display a 'research preview' label and acknowledge the single-host limitation. Multi-provider failover (Option 2) is a GA-phase requirement. SPEC-600 §6.1 updated.

---

### G-SECURITY-01 — No threat model

**Severity:** 🟠 High
**Spec touched:** SPEC-600 §13, SPEC-000 §5
**Issue:** SPEC-600 mentions input sanitization and prompt-injection prevention in two lines. There is no: explicit threat model, auth/identity model, rate-limiting policy, abuse-detection policy, account-takeover or model-extraction defence, supply-chain risk register.
**Required outcome:** SPEC-820 — Threat Model & Security Controls. Should explicitly enumerate: STRIDE-style threats, abuse vectors specific to mental-health AI (e.g., adversarial users seeking diagnosis-by-jailbreak), and required defences.
**[RATIFIED 2026-05-09]:** **[RATIFIED 2026-05-09]:** MVP security controls implemented for v0. Required baseline: (1) IP-based rate limiting on all API endpoints; (2) input sanitization against prompt-injection patterns; (3) output filtering to prevent credential / PII leakage; (4) HTTPS enforced; (5) no auth tokens or secrets in client-side code. Full threat model (SPEC-820) and comprehensive security spec are deferred to GA. Adversarial threats (G-RISK-01) folded into this baseline. SPEC-600 §13 updated.

---

### G-CRISIS-02 — Implicit risk classifier mapping

**Severity:** 🟠 High
**Spec touched:** SPEC-300 §3.2, §3.3
**Issue:** Implicit and contextual crisis indicators are described prosaically ("unbearable emotional pain language", "no future orientation + hopelessness"). For a real classifier, these need: a labelled dataset, a model architecture, and a calibrated decision threshold.
**Recommended default:** Build a small fine-tuned classifier (DistilBERT-class) on a curated annotated set, calibrated to maximize recall on Acute / Active risk while keeping false-positive rate ≤ a Director-approved bound (suggested: ≤ 5%).
**[RATIFIED 2026-05-09]:** **[RATIFIED 2026-05-09]:** Fine-tuned classifier (DistilBERT-class or equivalent) required for implicit/contextual risk signals. False-positive rate ceiling: ≤ 5% on the standard crisis test suite. This ceiling is revisable during Phase 6 evaluation — empirical calibration may tighten or loosen it with Director approval. Classifier design and labelling requirements captured in SPEC-300 §3. SPEC-100 updated with threshold reference.

---

### G-DATA-02 — Counselling corpus licensing

**Severity:** 🟠 High
**Spec touched:** SPEC-400 §4.1
**Issue:** "Counselling-style dialogue transcripts" are listed as primary empathy training data. Most counselling corpora are: closed (require IRB / institutional access), restricted-use, or scraped under unclear terms. License review must precede acquisition.
**Recommended candidates worth investigating:** ESConv, EmpatheticDialogues, Counsel-Chat (each carries its own licensing terms).
**[RATIFIED 2026-05-09]:** **[RATIFIED 2026-05-09]:** Open-license corpora only (Apache 2.0, CC-BY, MIT, or equivalent). No IRB-required, restricted-access, or unclear-provenance datasets. Recommended candidates for review: ESConv (CC-BY), EmpatheticDialogues (CC-BY-NC — verify before use), Counsel-Chat (verify license). License confirmation is a hard gate before any dataset is acquired. SPEC-400 §4.1 updated.

---

### G-LOSS-01 — Training loss formulation

**Severity:** 🟠 High
**Spec touched:** SPEC-400 §7
**Issue:** Empathy / safety / evaluation losses are described qualitatively. No concrete formulation (DPO, KTO, RLHF, SFT-only-with-rejection-sampling), no objective weights, no batching strategy.
**Recommended default:** SFT with rejection sampling for v0 (simplest, fastest); DPO once a preference dataset exists.
**[RATIFIED 2026-05-09]:** **[RATIFIED 2026-05-09]:** SFT with rejection sampling for v0. Simplest formulation; compatible with the open-license corpus constraint. Upgrade path: DPO once a preference dataset (ranked response pairs) exists. No RLHF or KTO for v0. Objective weights for empathy / safety loss components to be specified in SPEC-400 §7 during Phase 4 planning. SPEC-400 §7 updated.

---

### G-EVAL-01 — Human evaluator design

**Severity:** 🔴 Critical (re-rated from 🟠 after verification pass)
**Spec touched:** SPEC-500 §9
**Issue:** Human evaluation is mandated but: who evaluates, how many, what qualifications (clinical? lived experience? ML researcher?), what's the IRR floor, what's the pay/consent procedure, how are evaluators screened against bias.
**Why Critical:** the system's safety story rests on human-in-the-loop calibration of the Evaluator and Verification Supervisor. Without ratified evaluator design, Phase 6 sign-off is meaningless, which transitively blocks Phase 7 deployment. Same logic applied to G-DATA-01 applies here.
**Recommended default:** mixed panel — minimum 3 evaluators per response with at least one with clinical mental-health training or lived-experience advocacy background; Cohen's κ ≥ 0.7 floor on a calibration subset.
**[RATIFIED 2026-05-09]:** **[RATIFIED 2026-05-09]:** Solo Director review for v0. The Director personally reviews a sample of model outputs against the scoring rubrics. No inter-rater reliability (IRR) requirement applies for v0. Phase 6 sign-off is Director-only. A Director veto overrides any automated metric result. Formal multi-evaluator panel with IRR floor is deferred to GA.

---

### G-RELEASE-01 — Adapter / model release governance

**Severity:** 🟠 High
**Spec touched:** SPEC-400 §9, SPEC-600 §10, SPEC-700 §13
**Issue:** No spec defines: how a new adapter or base-model version is promoted (canary? eval gate? Director sign-off?), what evaluation evidence MUST be re-run before a Crisis-Mode-touching adapter is replaced, rollback criteria when post-deploy metrics drift, model-card / changelog requirements per release.
**Why it matters:** for a safety-critical system whose entire safety story rests on Empathy + Safety adapter behavior, an unsupervised model bump is equivalent to deploying untested code into the Crisis path. Distinct from G-OVERRIDE-01 (kill switch) and G-INFRA-01 (hosting failover).
**Recommended outcome:** a SPEC-810 — Release Governance. Minimum requirements: full SPEC-500 regression suite per release; mandatory canary on staging with synthetic crisis traffic; explicit Director sign-off on any change touching the Safety adapter; auto-rollback on drift-detection signals from SPEC-600 §16.
**[RATIFIED 2026-05-09]:** **[RATIFIED 2026-05-09]:** SPEC-810 (Release Governance) created as a required deliverable before Phase 7. Minimum requirements: full SPEC-500 regression suite must pass per release; mandatory canary deployment on staging with synthetic crisis traffic before any production promotion; explicit Director sign-off required for any change touching the Safety adapter; auto-rollback triggered by drift-detection signals from SPEC-600 §16. SPEC-810 added to docs/specs/.

---

### G-AGE-01 — Age verification / minor-user policy

**Severity:** 🟠 High
**Spec touched:** SPEC-000, SPEC-300 §5, SPEC-600 §4
**Issue:** No spec defines whether minors may use Nikko, how age is verified, or what changes in behaviour for minors. Kids Helpline appears in the demographic-resources gap (G-CRISIS-03) but there is no upstream rule about minors using the system at all.
**Regulatory exposure:**
- Australia: Online Safety Act and the eSafety Commissioner's expectations for digital-mental-health services to minors.
- International (if G-CRISIS-01 resolves to "accept non-AU users"): GDPR-K (under-16 in EU member states), COPPA (under-13 in US).
**Options:**
1. Restrict to 18+ via a self-attestation gate. Lowest engineering cost, weakest defence.
2. Restrict to 18+ via verified-age gate (third-party verification). Stronger but expensive and privacy-invasive.
3. Allow minors with adapted Crisis Mode (Kids Helpline foregrounded, parental-notice copy, explicit referral framing).
**Recommended default:** Option 1 for v0 (research-preview labelling) with a clear path to Option 3 for GA. To be folded into SPEC-800 (G-DATA-01) outcome.
**[RATIFIED 2026-05-09]:** **[RATIFIED 2026-05-09]:** Option 1 for v0 — 18+ self-attestation gate. Users must confirm they are 18 or older before accessing the chat interface. Gate is implemented as a mandatory UI step that cannot be bypassed. Combined with the 'research preview' label and AU-only disclaimer (G-CRISIS-01). Path to Option 3 (minor-adapted mode) reserved for GA. SPEC-600 §4 and SPEC-000 updated.

---

### G-RECON-01 — Distress level vs Escalation level

**Severity:** 🟡 Medium
**Spec touched:** SPEC-100 §9, SPEC-000 §6
**Issue:** Two parallel scales. Already reconciled in [GLOSSARY](./GLOSSARY.md#distress-levels-signal-agent-output) with the cross-walk `low ↔ Level 0`, `moderate ↔ Level 1`, `high ↔ Level 2`, `crisis ↔ Level 3`. Director just needs to ratify.
**[RATIFIED 2026-05-09]:** **[RATIFIED 2026-05-09]:** Crosswalk confirmed. Canonical mapping: low ↔ Level 0, moderate ↔ Level 1, high ↔ Level 2, crisis ↔ Level 3. GLOSSARY.md updated to mark this mapping as authoritative.

---

### G-RECON-03 — Passive risk elevation rule

**Severity:** 🟡 Medium
**Spec touched:** SPEC-100 §7.1
**Issue:** No explicit rule on when passive ideation ("I wish I could disappear") elevates to crisis-mode handling.
**Proposed default in spec:** "Passive risk indicator + high distress + repetition across turns = Level 2". Director to ratify.
**[RATIFIED 2026-05-09]:** **[RATIFIED 2026-05-09]:** Proposed rule confirmed. Passive risk indicator + high distress (Level 2) + repetition across ≥ 2 turns = escalate to Level 2 (or Level 3 if additional explicit signals present). A single isolated passive indicator at lower distress does NOT trigger escalation. SPEC-100 §7.1 updated.

---

### G-RECON-04 — Crisis Mode de-escalation rule

**Severity:** 🟡 Medium
**Spec touched:** SPEC-300 §9, §11
**Issue:** Source says "until user stabilizes", which is too soft for a deterministic system.
**Proposed default in spec:** "Crisis Mode persists until two consecutive turns classify as `distress_level <= high` AND no risk indicators are present." Director to ratify or replace.
**[RATIFIED 2026-05-09]:** **[RATIFIED 2026-05-09]:** Proposed de-escalation rule confirmed. Crisis Mode (Level 3) persists until two consecutive turns classify as distress_level ≤ high (Level 2) AND no risk indicators are present in either turn. A single calmer turn is insufficient. SPEC-300 §9 and §11 updated.

---

### G-RECON-05 — Missing adapter combination

**Severity:** 🟡 Medium
**Spec touched:** SPEC-400 §9, SPEC-700 §5.3
**Issue:** SPEC-400 lists two runtime combinations; SPEC-700 implicitly demands a third (Safety-only for Crisis). Already corrected in the SPEC-400 markdown. Director to ratify.
**[RATIFIED 2026-05-09]:** **[RATIFIED 2026-05-09]:** Safety-only adapter combination confirmed and added to SPEC-400 §9. The three runtime combinations are now: (1) Empathy + Safety [standard]; (2) Empathy + Safety + Evidence [guidance mode]; (3) Safety-only [crisis mode]. SPEC-700 §5.3 updated.

---

### G-RECON-06 — Verification Supervisor in Crisis Mode

**Severity:** 🟡 Medium
**Spec touched:** SPEC-300, SPEC-700 §5.3
**Issue:** Source skips Verification Supervisor in Crisis Mode flow. Reconciled in SPEC-700 as: a stripped-down "minimal safety verifier" — not a full skip. Director to ratify.
**[RATIFIED 2026-05-09]:** **[RATIFIED 2026-05-09]:** Minimal Verification Supervisor in Crisis Mode confirmed. The Verification Supervisor is NOT skipped during Crisis Mode. It runs in a stripped-down 'minimal safety verifier' mode: checks routing integrity and Safety adapter compliance only; skips evidence-pipeline and tone checks. Full Verification Supervisor resumes on de-escalation. SPEC-700 §5.3 updated.

---

### G-EVIDENCE-01 — Peer-review vs recency tiebreak

**Severity:** 🟡 Medium
**Spec touched:** SPEC-200 §5.4, SPEC-004
**Issue:** Both "prefer peer-reviewed" and "prioritize recency" can conflict (peer review takes months).
**Recommended default:** prefer peer-review when available within the last 5 years; fall back to recent grey-literature from primary sources (Healthdirect, Better Health Channel, WHO) when no recent peer-reviewed source exists. The Synthesizer SHOULD report the divergence in its confidence score.
**[RATIFIED 2026-05-09]:** **[RATIFIED 2026-05-09]:** Tiebreak rule confirmed. Prefer peer-reviewed sources published within the last 5 years. When no qualifying peer-reviewed source exists, fall back to recent grey-literature from primary sources (WHO, Healthdirect AU, Better Health Channel AU). The Synthesizer SHOULD flag the divergence in its confidence score when using grey-literature fallback. SPEC-200 §5.4 updated.

---

### G-EVIDENCE-02 — Retrieval interface undefined

**Severity:** 🟡 Medium
**Spec touched:** SPEC-200 §5.4
**Issue:** No concrete REST API endpoint, query format, rate-limit policy, or scraping policy for each source.
**Recommended:** for v0, use PubMed E-utilities + Healthdirect Search API + a curated cache of Better Health Channel + WHO articles. Build per-source adapter classes.
**[RATIFIED 2026-05-09]:** **[RATIFIED 2026-05-09]:** v0 retrieval stack confirmed: PubMed E-utilities API + Healthdirect Search API + curated static cache of Better Health Channel and WHO articles. Per-source adapter classes required in implementation. Rate-limit policies and scraping terms must be reviewed before Phase 3 implementation. SPEC-200 §5.4 updated.

---

### G-ENUM-01 — Canonical signal enum missing

**Severity:** 🟡 Medium
**Spec touched:** SPEC-100 §4–§8
**Issue:** Signal categories listed in prose; no canonical machine-readable enum (string keys for the JSON contract).
**Required outcome:** a `signal_enum.json` (or equivalent) under `docs/schemas/` shipping with v1.0 spec freeze.
**[RATIFIED 2026-05-09]:** **[RATIFIED 2026-05-09]:** signal_enum.json (or equivalent) is a Phase 2 deliverable. It MUST be produced under docs/schemas/ and ratified by the Director before any Phase 3 implementation code references signal type strings. SPEC-100 §4 updated with reference.

---

### G-THRESH-01 — "Safe thresholds" undefined

**Severity:** 🟡 Medium
**Spec touched:** SPEC-000 §10
**Issue:** "When uncertainty exceeds safe thresholds…" — no number.
**Recommended default:** if Signal Agent confidence < 0.40 OR Synthesizer confidence < 0.50, downgrade to safer fallback. Director to ratify or replace.
**[RATIFIED 2026-05-09]:** **[RATIFIED 2026-05-09]:** Numeric thresholds confirmed. Uncertainty fallback triggers when: Signal Agent confidence < 0.40 OR Synthesizer Agent confidence < 0.50. When triggered, the system downgrades to the next-safer fallback response and MUST NOT proceed with a high-confidence-dependent action. SPEC-000 §10 and SPEC-100 §10 updated.

---

### G-THRESH-02 — Confidence bands

**Severity:** 🟡 Medium
**Spec touched:** SPEC-100 §10
**Issue:** "Low confidence" referenced; no banding.
**Recommended default:** `<0.40` low, `0.40–0.70` moderate, `>0.70` high.
**[RATIFIED 2026-05-09]:** **[RATIFIED 2026-05-09]:** Confidence bands confirmed. low: < 0.40 · moderate: 0.40–0.70 · high: > 0.70. These bands apply uniformly across all agents that emit a confidence score. SPEC-100 §10 updated.

---

### G-METRIC-01 — Signal-evaluation rate targets

**Severity:** 🟡 Medium
**Spec touched:** SPEC-100 §15
**Issue:** "Minimize missed-crisis-signal rate" — no numeric target.
**Recommended default:** missed-crisis ≤ 0.5% on the standard crisis test suite (zero-tolerance is unrealistic for any classifier). Director to set.
**[RATIFIED 2026-05-09]:** **[RATIFIED 2026-05-09]:** Missed-crisis rate target confirmed: ≤ 0.5% on the standard crisis test suite. Zero-tolerance is statistically unrealistic; 0.5% represents best-in-class for safety-critical classifiers at this scale. This target is evaluated in Phase 6 and may be tightened with Director approval. SPEC-100 §15 and SPEC-500 updated.

---

### G-MODEL-01 — Base model licensing review

**Severity:** 🟡 Medium
**Spec touched:** SPEC-400 §3.1
**Issue:** Llama 3 8B and Mistral 7B candidates have license terms that may limit commercial use, derivative distribution, and (Llama 3) require Acceptable Use Policy compliance.
**Recommended:** legal review before adapter training begins.
**[RATIFIED 2026-05-09]:** Research-use-only deployment — Nikko will not be commercialised. Original candidates: (1) Mistral 7B v0.3 (Apache 2.0); (2) Phi-3-medium-4k-instruct (MIT); (3) Llama 3.1 8B (Meta Community). SPEC-400 §3.1 updated.

**[REVISED 2026-05-14]:** Model selection updated. Mistral-7B-Instruct-v0.3 retired (infeasible on RTX 3070 8 GB VRAM). New production targets: **Phi-3.5-mini-instruct** (MIT — ADP-A) + **Gemma-2-2b-it** (Gemma licence — ADP-B/C). License review confirmed both permit research deployment. SPEC-400 §3.1 updated. Gap fully closed.

---

### G-OVERRIDE-01 — Manual override controls

**Severity:** 🟡 Medium
**Spec touched:** SPEC-600 §17
**Issue:** Override mechanism mandated, but: who is authorized, how is invocation audited, how is rollback performed?
**Recommended default:** override authorized only by Director-equivalent role; every invocation logs a tamper-evident audit record; rollback is automatic when the trigger condition clears.
**[RATIFIED 2026-05-09]:** **[RATIFIED 2026-05-09]:** Override authorization confirmed. Manual override may be invoked by the Director only. Every override invocation MUST generate a tamper-evident audit record (timestamp, trigger reason, affected components). The system MUST automatically roll back to the previous state when the trigger condition clears or when the Director issues a rollback command. SPEC-600 §17 updated.

---

### G-CACHE-01 — Cache TTL and invalidation

**Severity:** 🟡 Medium
**Spec touched:** SPEC-600 §8.3
**Issue:** Caching allowed but no TTLs / invalidation events.
**Recommended default:** PubMed: 7 days; Healthdirect / Better Health: 30 days with weekly head-check; WHO: 30 days; secondary sources: 30 days.
**[RATIFIED 2026-05-09]:** **[RATIFIED 2026-05-09]:** Cache TTLs confirmed. PubMed: 7 days. Healthdirect AU: 30 days with weekly HTTP HEAD check for content changes. Better Health Channel: 30 days with weekly HEAD check. WHO: 30 days with weekly HEAD check. Secondary / grey-literature sources: 30 days. Cache invalidation is triggered by: TTL expiry, HEAD-check change detection, or Director-issued manual purge. SPEC-600 §8.3 updated.

---

### G-FRONTEND-01 — Session continuity mechanism

**Severity:** 🟡 Medium
**Spec touched:** SPEC-600 §4.2
**Issue:** "Session continuity" is mandated but the mechanism is not specified. Tied to [G-MEMORY-01](#g-memory-01--conversation-state-store).
**[RATIFIED 2026-05-09]:** **[RATIFIED 2026-05-09]:** Session continuity is in-memory only, consistent with G-MEMORY-01 ruling. No server-side persistence, no localStorage, no session token. If the user refreshes the browser tab, the session resets. This limitation SHOULD be communicated to the user in the UI (e.g., 'Your conversation is private and will be cleared if you close or refresh this page'). SPEC-600 §4.2 updated.

---

### G-RISK-01 — Adversarial threats not enumerated

**Severity:** 🟡 Medium
**Spec touched:** SPEC-000 §5
**Issue:** SPEC-000's RISK-01 to RISK-06 are user-facing safety risks. Adversarial threats (prompt injection from retrieved web content, training-data poisoning, model extraction) are not in the risk register.
**Recommended:** roll into [G-SECURITY-01](#g-security-01--no-threat-model) outcome.
**[RATIFIED 2026-05-09]:** **[RATIFIED 2026-05-09]:** Adversarial threats folded into MVP security controls (G-SECURITY-01). The following threats are added to SPEC-000 §5 risk register: RISK-07 prompt injection via retrieved web content; RISK-08 training-data poisoning (mitigated by open-license-only corpus constraint); RISK-09 model extraction via repeated sampling. All three are addressed at the MVP security baseline level for v0. SPEC-000 updated.

---

### G-LAYOUT-01 — Repository spec folder location

**Severity:** 🔵 Low
**Spec touched:** SPEC-600 §15
**Issue:** SPEC-600 §15 places `specs/` inside the implementation tree. This repo places governance docs at the repo root under `docs/specs/` instead. Both can coexist if the implementation tree's `specs/` becomes a symlink to `../docs/specs/`. Cosmetic.
**[RATIFIED 2026-05-09]:** **[RATIFIED 2026-05-09]:** SPEC-600 §15 updated to reference docs/specs/ as the canonical spec location, consistent with the actual repository layout. The implementation-tree specs/ reference in SPEC-600 §15 is removed. No symlink required.

---

### G-MEMORY-02 — Conversation history in Router

**Severity:** 🔵 Low
**Spec touched:** SPEC-700 STEP 3
**Issue:** Reuses [G-MEMORY-01](#g-memory-01--conversation-state-store). Listed for traceability.
**[RATIFIED 2026-05-09]:** **[RATIFIED 2026-05-09]:** Resolved as a downstream dependency of G-MEMORY-01. SPEC-700 STEP 3 references in-memory context window state. No separate action required beyond G-MEMORY-01 ratification.

---


### G-SCOPE-01 — Topic scope enforcement

**Severity:** 🟠 High
**Spec touched:** SPEC-000 §3.2, SPEC-200 §5, SPEC-700 STEP 1
**Issue:** No mechanism prevents clearly off-topic messages (code, recipes, trivia, general knowledge) from passing through the pipeline. The existing requirements REQ-000-200 and REQ-000-203 are principles only with no implementation detail. SPEC-700 STEP 1 explicitly prohibits pre-classification of intent at ingestion, leaving no gate before the Signal Agent.
**Why it matters:** Without an explicit scope guard, the LLM may engage with non-emotional queries — the same failure mode seen in unguarded task-specific chatbots. For a mental-health system this also creates a clinical credibility risk: a user who receives a recipe from Nikko will not trust it in distress.
**Nuance:** the boundary is intentionally fuzzy. "I can't finish my dissertation" looks off-topic but may be distress-coded. The scope classifier MUST handle ambiguity by deferring to the Signal Agent, not rejecting.

**[RATIFIED 2026-05-09]:** Option B — lightweight scope classifier inserted as STEP 0 in the execution pipeline, before the Router and Signal Agent. Clearly off-topic messages (high-confidence non-emotional) are rejected at this gate. Ambiguous messages pass through to the Signal Agent. Refusal response: warm redirect that acknowledges the message, explains Nikko's purpose, and leaves the door open for emotional conversation. See REQ-000-SC1, REQ-200-SC1 through SC4, REQ-700-SC1 through SC3.

## How to use this dossier

For each gap the Director may:

1. **Ratify** the recommended default → mark `[RATIFIED]` and note the date.
2. **Override** with a different decision → record the decision and update the affected specs.
3. **Defer** → mark `[DEFERRED to <phase>]` and link to a tracking issue.

Until ratified, every gap is a Phase-1-blocker for the spec it touches. Phase-2 cannot begin until all 🔴 Critical gaps are at least `[DEFERRED]` with a concrete owner.

---

### G-ENV-01 — bitsandbytes Windows CUDA runtime

**Severity:** 🟡 Medium
**Phase discovered:** Phase 3
**Status:** ✅ RESOLVED 2026-05-10 — Director selected Option B

**Problem:** `bitsandbytes==0.41.1` (jllllll Windows wheel) and `0.43.1` (PyPI) could not locate `cudart64_12.dll` on the dev machine (Windows 11, RTX 3070, CUDA 12.4). The DLL was not present in the conda env's `Library\bin\` despite `cuda-runtime=12.4.1` being installed via the nvidia conda channel.

**Resolution applied:** `pip install bitsandbytes==0.45.5`. Version 0.45.5 has improved Windows CUDA 12.x path discovery and resolved the DLL lookup failure without requiring a full CUDA Toolkit install.

**Follow-on actions completed:**
- `environment.yml` updated to `bitsandbytes==0.45.5`.
- `Qwen/Qwen2.5-3B-Instruct` retained as the Phase 3 dev model (Director confirmed — output quality sufficient for structured JSON agent tasks).
- Production model selection revised 2026-05-14: Phi-3.5-mini-instruct (ADP-A) + Gemma-2-2b-it (ADP-B/C). `bitsandbytes` removed from production stack entirely (ZeroGPU CUDA init-time incompatibility — see G-ENV-01 resolution above; Phase 7 infra uses native bf16). See SPEC-400 §3.1 and `hf_space/app.py`.

---

### G-DATA-03 — AnnoMI HuggingFace dataset identifier mismatch

**Severity:** 🟡 Medium
**Phase discovered:** Phase 4 (Step 13 pre-run audit, 2026-05-11)
**Status:** ⏳ OPEN

**Problem:** `notebooks/step13_adp_a_data_preparation.ipynb` Cell 7 loads AnnoMI with `load_dataset("AnnoMI", ...)`. The dataset registry (`finetuning/dataset_registry.yaml`) records the source URL as `https://huggingface.co/datasets/to-be/annomi-motivational-interviewing-therapy-conversations`, implying the correct HF dataset ID is `to-be/annomi-motivational-interviewing-therapy-conversations`. If `"AnnoMI"` is not a valid short-form alias on HuggingFace, the loader will fail silently (prints a fallback warning, returns `[]`) and AnnoMI contributes 0 records. AnnoMI carries a 30% mix weight; losing it pushes total yield toward (or below) the 600-record minimum gate check for Step 14.

**Options:**
1. Run Step 13 as-is; watch Cell 16 pre-filter summary — if AnnoMI = 0 records, update `load_dataset(...)` to the full ID and rerun from Cell 7.
2. Proactively update Cell 7 to try `"AnnoMI"` first and fall back to `"to-be/annomi-motivational-interviewing-therapy-conversations"` before execution.

**Recommended default:** Option 1 — attempt the run first. The fallback is already coded; no code change is required unless the load fails. If it fails, apply the corrected ID in Cell 7 and rerun from that cell only.

**[RESOLVED 2026-05-11]:** Director confirmed `"AnnoMI"` returns 404. Correct ID is `to-be/annomi-motivational-interviewing-therapy-conversations`. Applied in notebook (load_dataset call, DATASET_MIX config, markdown header table) and dataset_registry.yaml. G-DATA-03 closed.

---

### G-TRAIN-01 — ADP-A max_seq_length discrepancy

**Severity:** 🟡 Medium
**Phase discovered:** Phase 4 (Step 13 pre-run audit, 2026-05-11)
**Status:** ⏳ OPEN — Director ruling required before Step 14

**Problem:** `finetuning/adp_a_empathy/config.yaml` sets `max_seq_length: 2048`. The PHASE-4-HANDOFF.md (§5, Step 14 notes) and Step 13 notebook Cell 22 summary both state `max_seq_length = 768` for Step 14. These conflict. The value affects VRAM consumption and training throughput on the RTX 3070.

**Trade-off:**
- **768** — matches the ADP-C training seq length; conservative VRAM usage; may truncate longer multi-turn ESConv examples.
- **2048** — captures full multi-turn context; higher VRAM pressure; may require reducing `per_device_train_batch_size` from 4 to 2 to stay within `5000MiB` budget.

**Recommended default:** 768 for Step 14 v0. The ADP-C filter in Step 13 already truncates responses at 512 tokens; input context rarely exceeds 768 tokens in the prepared corpus. Revisit for ADP-A v1 with a longer context budget if evaluation reveals truncation artefacts.

**Director ruling required before Step 14 begins.** Does not affect Step 13 execution.

**[RESOLVED 2026-05-11]:** 768 ratified. Reason: RTX 3070 VRAM headroom at `batch_size=4`. config.yaml updated. Corpus single/two-turn exchanges fit within 768 tokens; ADP-C filter already truncates responses at 512. Revisit for ADP-A v1 if evaluation reveals truncation artefacts in multi-turn ESConv examples.

---

### G-RETRIEVAL-01 — Retrieval adapter architecture change

**Severity:** 🟡 Medium
**Spec touched:** SPEC-200 §5.4, REQ-200-071, REQ-200-ER4
**Raised by:** Director review of Step 6 output (2026-05-10)

**Problem:** The original three grey-literature adapters (HealthdirectAdapter, BetterHealthAdapter, WHOAdapter) were based on incorrect assumptions:
- **HealthdirectAdapter**: implemented against an assumed/unverified API endpoint (`api.healthdirect.gov.au/ih/api/v2/content/search`). Healthdirect Australia does not publish a public search API.
- **BetterHealthAdapter / WHOAdapter**: static JSON corpus approach requiring manual curation. Neither source has a public search API. This was architecturally valid but required ongoing manual work to maintain.

Additionally, two clinically relevant Australian mental health sources (Beyond Blue, Black Dog Institute) were absent from the retrieval stack.

**Director ruling (2026-05-10):** Replace all three adapters with a single **WebSearchAdapter** that:
1. Queries five sanctioned domains via DuckDuckGo `site:` operator + BeautifulSoup content scraping:
   - `healthdirect.gov.au`
   - `betterhealth.vic.gov.au`
   - `who.int`
   - `beyondblue.org.au`
   - `blackdoginstitute.org.au`
2. Falls back to general web search when sanctioned results are insufficient, with external results marked `SourceTier.SECONDARY` and a scrutiny warning injected into the abstract field.
3. PubMed E-utilities confirmed as a real, documented API returning abstract text — retained unchanged.

**Resolution applied:**
- `retrieval/healthdirect_adapter.py`, `better_health_adapter.py`, `who_adapter.py` stubbed with `ImportError` (cannot delete via sandbox; stubs fail loudly on import).
- `retrieval/web_search_adapter.py` created (see Step 6 revised).
- `docs/schemas/retrieval_schemas.py` updated: `WebSearchAdapter` stub added, `WEB_SEARCH_CACHE_POLICY` (3-day TTL) added, `ADAPTER_PRIORITY_ORDER` updated to `[PubMedAdapter, WebSearchAdapter]`.
- `retrieval/__init__.py` updated accordingly.
- `environment.yml` will need `duckduckgo-search>=6.0` and `beautifulsoup4` added before next environment rebuild.

---

### G-P5-001 — Quick-exit domain not in SPEC-300

**Severity:** 🔵 Low
**Phase discovered:** Phase 5 spec reconciliation audit (2026-05-11)
**Spec touched:** SPEC-300 §4, FRONTEND_INTEGRATION_SPEC.md §3
**Status:** ✅ RATIFIED 2026-05-11

**[RATIFIED 2026-05-11]:** `bom.gov.au` (Australian Bureau of Meteorology) confirmed as the v0 quick-exit target. REQ-300-QE1 and REQ-300-QE2 added to SPEC-300 §5 with rationale. Domain choice: Australian government domain, visually innocuous weather service, no mental health or social-media content, provides plausible cover for users who require visual privacy from others.

---

### G-P5-002 — Untraced frontend features

**Severity:** 🟡 Medium
**Phase discovered:** Phase 5 spec reconciliation audit (2026-05-11)
**Status:** ✅ RATIFIED 2026-05-11

**[RATIFIED 2026-05-11]:** Director rulings per feature:

1. **Agent debug overlay** — Retained in production builds. Gesture-protection (2-tap + 3-second hold on avatar) is sufficient access control for a research preview. Feature is developer-facing and invisible to standard users. Formally scoped as a diagnostic observability tool in SPEC-600 §17. A REQ-600 ID will be added during Phase 5 implementation.

2. **First-run tutorial** — Retained. Documents system capabilities and non-diagnostic nature on first entry, consistent with REQ-000-182 (users must understand where information comes from and how the system works). Formally scoped as a UX onboarding element; REQ-000-UX1 will be added during Phase 5.

3. **Suggestion chips** — Retained conceptually; content to be refined. Current four prompts are placeholders. Director will specify refined prompt set before Phase 5 gate closes. Documented as a design choice in FRONTEND_INTEGRATION_SPEC.md.

---

### G-DATA-06 — ADP-C threshold calibration mismatch

**Severity:** 🟡 Medium
**Phase discovered:** Phase 4, Step 13 ADP-C filter run (2026-05-11)
**Spec touched:** SPEC-400 §3.2, `finetuning/adp_a_empathy/config.yaml`
**Status:** ✅ RESOLVED 2026-05-11

**Issue:** ADP-C `accept_threshold=0.70` produced the following pass rates on the first Step 13 filter run:

| Dataset | Candidates | Pass | Pass rate |
|---------|-----------|------|-----------|
| AnnoMI | 600 | 40 | 6.7% |
| Amod | 500 | 128 | 25.6% |
| ESConv | 400 | 46 | 11.5% |
| MentalChat16K | 300 | 281 | 93.7% |
| EmpatheticDialogues | 200 | 2 | 1.0% |
| **Total** | | **497** | — |
| **Assembled** | | **336** | — |

Only MentalChat (a synthetic dataset) cleared 70%. Total yield was 336 records against a 600-record gate minimum.

**Root cause:** ADP-C was trained on synthetic red-line violation pairs (structured critique format). Organic empathy datasets use short conversational turns, informal register, and motivational interviewing style — which ADP-C scores below its trained quality distribution even when the examples are clinically appropriate.

**Resolution:** `accept_threshold` lowered from `0.70` to `0.50` (Director-ratified 2026-05-11). Rationale: 0.50 still filters the bottom half of ADP-C's score distribution, eliminating clear negatives while not penalizing organic conversational style. `config.yaml` updated with rationale comment. Step 13 notebook rebuilt with `ACCEPT_THRESHOLD = 0.50`.

**Note for Step 17 (ADP-C retraining):** This gap confirms ADP-C would benefit from retraining on a mix of organic empathy pairs alongside synthetic redline pairs to improve calibration for natural dialogue. Step 17 should include this as a training objective.

---

### G-TRAIN-02 — v0 URL and email hallucination

**Severity:** 🟠 High
**Phase discovered:** Phase 4, ADP-A / ADP-B v0 smoke tests (2026-05-12)
**Spec touched:** SPEC-300 §5 (crisis resources), SPEC-400 §7
**Status:** ⏳ OPEN

**Issue:** Both v0 adapters (ADP-A and ADP-B) produce fabricated but plausible-looking URLs and email addresses during inference. Observed examples: `vesselinquiry@health.gov.au`, `vessel.org.au`, `vesselin.org.au`. These are not present in any training dataset — they originate from the base model's pretraining confabulation prior, which v0 training data volume is insufficient to override.

**Risk:** A user in crisis may attempt to contact a hallucinated email address or visit a fabricated URL. This is a direct patient-safety risk.

**Mitigations in place (v0):**
- ADP-C evaluator runs on every response before delivery; URL pattern detection to be added in Step 17 (see G-TRAIN-02 note below).
- Verification Supervisor (VS) structural check C4 (source citation validity) partially covers this if the URL appears in a citation context.

**Options for Director:**
1. **Step 17 (preferred):** Add URL/email whitelist check to ADP-C as a hard redline. Any response containing a URL or email address not in the approved resource list (`13 11 14`, `lifeline.org.au`, `beyondblue.org.au`, `13yarn.org.au`, `000`) scores 0.0 and is regenerated.
2. **Post-processing filter:** Apply a regex URL/email extractor in the orchestrator after generation, scrub any non-whitelisted contact before delivery.
3. **GA retraining:** Include explicit "do not fabricate contact details" negative examples in ADP-A and ADP-B v1 training data.

**Recommended default:** Option 1 + Option 2 combined — belt and braces for a clinical context.

**Note for Step 17:** ADP-C training data should include negative examples of responses containing hallucinated URLs/emails, scored 0.0, alongside positive examples that either omit contact details entirely or reference only the approved resource list.

---

### G-TRAIN-03 — v0 multi-turn leakage

**Severity:** 🟠 High
**Phase discovered:** Phase 4, ADP-A / ADP-B v0 smoke tests (2026-05-12)
**Spec touched:** SPEC-700 §4 (Synthesizer output format), SPEC-400 §7
**Status:** ⏳ OPEN

**Issue:** v0 adapters generate fake conversational continuations after the intended response closes. Observed patterns: fabricated `User:` / `Nikko:` turns, stray tokens (`:%.* Nope!`, `/***/`, emoji + numbers), hallucinated third-party dialogue. Root cause: multi-turn training records in AnnoMI, ESConv, and EmpatheticDialogues expose the model to alternating-speaker format; the base model's sequence completion prior then extends the pattern beyond the `</s>` boundary.

**Risk:** In a chat interface, the full generated string (including hallucinated turns) would be displayed to the user unless caught by the pipeline. User reads a fake conversation and mistakes hallucinated responses for real guidance.

**Mitigations in place (v0):**
- `repetition_penalty=1.3` + `eos_token_id` in `generate()` — reduces but does not eliminate leakage.
- `is_clean()` filter in Step 13 strips multi-turn markers from ADP-A training data; analogous fix needed for ADP-B (Step 15 / Step 17).
- ADP-C evaluator to be extended with turn-marker detection in Step 17.

**At inference in a chat interface:** The orchestration pipeline runs ADP-C evaluation before the response is returned to the frontend. If ADP-C flags a multi-turn leakage pattern, the regen loop (SPEC-700 §7) fires. The user never sees the raw hallucinated output. The smoke test runs the adapter **raw** (bypassing the pipeline), which is why leakage is visible in test output but not in production.

**Options for Director:**
1. **Step 17 (preferred):** Add turn-marker detection to ADP-C as a hard redline (any `User:`, `Nikko:`, `Human:`, `Assistant:` in the response body scores 0.0).
2. **Post-processing strip:** Apply `is_clean()` equivalent in the orchestrator as a fast pre-filter before ADP-C scoring.
3. **v1 retraining:** Restructure ADP-A and ADP-B training data so all multi-turn source records are converted to single-turn format before training.

**Recommended default:** Option 1 + Option 2. Option 3 is a v1 training objective.

---

### G-PHASE-01 — Phase execution order reconciliation

**Severity:** 🟡 Medium
**Phase discovered:** Phase 4 planning session (2026-05-12)
**Spec touched:** CLAUDE.md §8, §8c, §8d
**Status:** ✅ RATIFIED 2026-05-12

**Issue:** The original phase table in CLAUDE.md §8 ordered execution as Phase 5 → Phase 6 → Phase 7. Phase 6 (Evaluation) requires a live deployed system for its system-tier harness — `pytest` tests must fire against a real Fly.io + HF Spaces + LLM stack, not localhost. Under the original ordering, Phase 7 (Deployment) would not exist yet when Phase 6 attempted to run.

**Director ruling (2026-05-12):** Revised execution order:
1. **Phase 5** — Backend API integration (wire frontend to real agents).
2. **Phase 7 infra** — Stand up Fly.io, HF Spaces ZeroGPU, GitHub Pages staging environment. No production sign-off at this sub-gate.
3. **Phase 6** — Run evaluation harness end-to-end against the live staging stack.
4. **Phase 7 sign-off** — Promote staging to production once all Phase 6 gates pass.

**CLAUDE.md updated:** Phase gating table revised, §8c and §8d cross-referenced, `[PROPOSED-RECONCILIATION]` tag applied. No spec files required updating — this is an operational process decision, not a requirement change.

---

### G-UI-01 — AI limitation disclaimer

**Severity:** 🟡 Medium
**Phase discovered:** Phase 4, ADP-B v0 smoke test review (2026-05-12)
**Spec touched:** SPEC-000 §3.1 (non-deception principle), SPEC-300 §5, SPEC-600 (UI)
**Status:** ✅ RESOLVED 2026-05-14

**Issue:** The frontend currently shows a non-diagnostic notice in the Gate (onboarding) screen but no persistent disclaimer during the chat session. If the model produces hallucinated contact details or inaccurate information, a user who bypassed the gate or forgot the onboarding notice has no in-session reminder that Nikko is AI and may be wrong.

**Director-proposed copy:** *"Nikko is AI and can make mistakes. Do not action anything without further checking."*

**Recommended placement:** Persistent footer or sub-composer label — always visible below the text input, never dismissible.

**Options for Director:**
1. Static footer text below the composer (lowest friction, always visible).
2. Contextual banner that appears whenever Nikko cites a specific resource or contact number (higher signal value, more complex to implement).
3. Both.

**Recommended default:** Option 1 for Phase 5; Option 3 by GA.

**[RESOLVED 2026-05-14]:** Option 1 implemented. `AiDisclaimer` component added to `web/chat.jsx`, rendered permanently below the `Composer`. Copy: *"Nikko is AI and can make mistakes. Do not act on anything without further checking."* (minor wording tightening from Director-proposed copy — "action" → "act on", per plain-English house style). Requirement ID assigned: `REQ-300-164`. Component is non-dismissible by design. SPEC-000 §3.1 and SPEC-300 §5 cross-referenced in inline comment. Option 2 (contextual banner on resource citations) deferred to GA.

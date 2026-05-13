# Nikko — mHealth Quality Assessment
**Date:** 2026-05-11 · **Assessor:** NIKKO Engineering Collective (Lead Architect persona)  
**Version assessed:** Research Preview v0 (Phase 4 — backend not yet connected to frontend)  
**Frameworks applied:** General Quality Parameters (Yap et al. 2020); MARS Tool (Stoyanov et al. 2015); mERA Checklist (WHO 2016)

> **Scope note:** This assessment evaluates Nikko's frontend (`web/`) and its documented backend design (`docs/specs/`) as of Phase 4. The AI agent pipeline is fully implemented but not yet connected to the frontend — responses are currently served from canned patterns in `nikko-data.jsx`. Ratings reflect the current live state unless otherwise noted; Phase 5 upgrade paths are flagged where relevant.

---

## 1. General Quality Parameters (Yap et al. 2020)

### 1.1 Usability

| Descriptor | Status | Notes |
|---|---|---|
| Intuitiveness to use | ✅ Strong | Single-screen chat with minimal controls. No learning curve for the core interaction. |
| Ease of app navigation | ✅ Strong | Floating panel tabs (mood diary, sources) launch contextually. Topbar memory/theme/exit controls are stable. |
| Organisation of screen layout | ✅ Strong | Topbar / thread / composer three-zone layout is conventional and clean. Panels slide in without displacing thread. |
| Readable default font size | ✅ Adequate | System font stack at ~15px; composer and thread both readable without pinching. |
| Clear and understandable language for laypersons | ✅ Strong | All gate disclosures, response text, and UI labels written in plain English. No clinical jargon. |
| Presence of a help function | ⚠️ Partial | First-run tutorial exists and covers core features. No persistent help button or FAQ. Tutorial not re-accessible after first dismissal. |
| Accessibility of features from any part of the app | ✅ Strong | Memory, mood diary, sources, theme toggle, and quick exit are accessible from the main chat view at all times. |

**Overall usability: Good.** The key gap is re-accessible help — the tutorial cannot be reopened once dismissed without clearing localStorage. Consider a persistent `?` help trigger in Phase 5.

---

### 1.2 Privacy Policy

| Descriptor | Status | Notes |
|---|---|---|
| Purpose of collection stated | ✅ | Privacy Policy §1 and §3 clearly state no collection occurs. |
| Who will use the data | ✅ | §8 (third-party CDN noted); §2 table explicitly states no data is collected by Nikko. |
| Privacy methods used | ✅ | §11 details: no server storage, AES-256-GCM for USM, HTTPS enforced. |
| User rights and contact method | ✅ | §10 covers APP rights; OAIC contact referenced; §14 provides contact route. |
| Section for minors requiring guardian consent | ⚠️ Partial | §9 explains 18+ requirement and absence of minor-adapted pathway. No guardian consent mechanism exists in v0 — explicitly acknowledged as a future feature. |

**Overall: Compliant for research preview scope.** Minor-adapted pathway (with guardian consent) is a documented GA-phase requirement (G-AGE-01, SPEC-600 §4).

---

### 1.3 Authentication

| Descriptor | Status | Notes |
|---|---|---|
| Unique ID and password | ❌ Not present | By architectural design. Zero-retention model (SPEC-800) means no user accounts exist. |
| Complex password policy | ❌ Not applicable | No auth system in scope for v0. |
| Multifactor authentication | ❌ Not applicable | — |

**Overall: Not met — by design.** The Personal Memory feature requires a password (min 8 chars), but this is not authentication — it is local file encryption. Full account-based authentication is incompatible with the zero-retention architecture in v0. If a future version introduces accounts, this section must be revisited. The research preview's 18+ self-attestation gate is the sole identity control; its limitations are explicitly disclosed.

---

### 1.4 Data Retention

| Descriptor | Status | Notes |
|---|---|---|
| Data retention policy included | ✅ | Privacy Policy §2 (summary table), §3 (conversations), §5 (localStorage), §6 (mood), §7 (USM) all specify retention durations. |
| Data kept only as long as initial purpose requires | ✅ | Conversation data: deleted on session end. Mood diary: deleted on tab close. Theme/tutorial flags: persistent but non-personal. |

**Overall: Excellent.** Zero-retention architecture exceeds the minimum requirement. No ambiguity about what persists and for how long.

---

### 1.5 Reliability

| Descriptor | Status | Notes |
|---|---|---|
| Clearly defined target audience | ✅ | Gate: 18+, Australia, English. Research preview label present throughout. |
| Brief description of purpose and audience | ✅ | Gate disclosures and "Research preview" tooltip cover this clearly. |
| Names and credentials of creators | ⚠️ Partial | EULA §12 and Privacy Policy §1 now identify **Nicholas Dale** as the developer, with LinkedIn and GitHub links. No formal qualifications are listed — appropriate for a research preview where the developer is not presenting clinical credentials. |
| Non-replacement disclaimer | ✅ | Gate: "Nikko is a non-diagnostic wellbeing companion. It does not replace a clinician." EULA §1 also covers this explicitly. |
| Declaration of funding sources | ✅ | **Self-funded.** No external grants, institutional funding, or commercial investment. There are no funding relationships that could create bias or competing interests. |
| Declaration of conflicts of interest | ✅ | **None declared.** The developer has no financial, commercial, or institutional conflicts of interest in relation to Nikko or the mental health services it references. |
| Presence or absence of bias | ⚠️ Partial | Bias is actively mitigated by **Retrieval-Augmented Generation (RAG)** rather than relying on pure fine-tuning. RAG grounds responses in a curated, APA7-cited evidence base (Beyond Blue, headspace, Black Dog Institute, APS, etc.), reducing model hallucination and recency bias. Evidence selection bias is partially mitigated by citing primary sources. A formal bias audit has not yet been conducted — flagged for Phase 6 evaluation. |
| Third-party accreditation | ❌ | Not applicable at research preview stage. |
| Date of last update | ⚠️ Partial | EULA and Privacy Policy carry version dates. The main application UI does not display a "last updated" date. |

**Overall: Improved from prior assessment.** Three items (funding, COI, creator attribution) are now addressed. The remaining gaps are characteristic of a self-funded research preview: no independent accreditation, no formal bias audit, no institutional affiliation. The RAG-based architecture is a meaningful bias mitigation that distinguishes Nikko from apps that rely on unconstrained generative outputs.

---

## 2. MARS Tool (Stoyanov et al. 2015) — 1 (adequate) to 5 (excellent)

### 2.1 Engagement

| Criterion | Score | Rationale |
|---|---|---|
| Entertainment | 2 | No gamification, rewards, or entertaining elements. The animated sun avatar and organic aesthetic provide mild visual interest, but the app is functionally serious. This is appropriate for a mental health tool — excessive gamification is a documented risk. |
| Interest | 3 | Well-crafted opening message, suggestion chips, avatar state machine, and source citations keep the experience from feeling static. Canned responses are thoughtfully written but their limited variety will reduce interest over repeated sessions. |
| Customisation | 3 | Light/dark theme toggle; Personal Memory file for session personalisation; mood diary entries are user-controlled. No notification preferences or content customisation. |
| Interactivity | 3 | Bidirectional text chat; mood diary log; source citation exploration; memory file generate/load. No push notifications, reminders, or sharing features. |
| Target group | 4 | Language is plainly accessible; design is calm and non-clinical; content is appropriate for adults experiencing emotional distress. Crisis safety banner is contextually appropriate. |

**Engagement mean: 3.0 / 5**

> Note: lower entertainment and customisation scores are partially intentional — a mental health AI companion should not prioritise fun over safety, and high customisability risks over-personalisation that could reinforce unhealthy patterns.

---

### 2.2 Functionality

| Criterion | Score | Rationale |
|---|---|---|
| Performance | 3 | Frontend renders instantly; canned response simulation is smooth. Backend not yet connected — real-pipeline latency is untested. Score reflects current v0 state only. Phase 5 pipeline integration may improve or degrade this. |
| Ease of use | 4 | Onboarding gate → chat is a single flow. Composer is self-explanatory. Keyboard shortcut hints are displayed. No manual needed for core use. |
| Navigation | 4 | Single-page app with panel overlays — no routing or page-load friction. Floating panel tabs are clearly labelled. Quick exit is prominent and functional. |
| Gestural design | 4 | Standard web interactions throughout (click, keyboard, textarea autosize). No unusual gestures. Consistent behaviour across all controls. The debug overlay gesture (hold 3s) is intentionally obscure and non-standard — appropriate given it is a developer tool. |

**Functionality mean: 3.75 / 5**

---

### 2.3 Aesthetics

| Criterion | Score | Rationale |
|---|---|---|
| Layout | 4 | Three-zone layout (topbar / thread / composer) is well-proportioned. Side panels open logically. Floating elements use consistent border-radius and shadow language. No crowding. |
| Graphics | 4 | SVG icon system is consistent and sharp at all resolutions. The sun avatar is distinctive and carries clear emotional meaning through its state machine. No raster images — fully scalable. |
| Visual appeal | 4 | Warm amber palette with cream backgrounds and organic decorative elements (floating orbs, sparkles) creates a distinctive and calming aesthetic appropriate to the use case. Light and dark modes are both polished. |

**Aesthetics mean: 4.0 / 5**

The aesthetic is a genuine differentiator. The sun avatar's emotional expressiveness through glyphs and ray animation is more communicative than most chatbot interfaces. The organic warmth deliberately counters the clinical coldness typical of health apps.

---

### 2.4 Information Quality

| Criterion | Score | Rationale |
|---|---|---|
| Accuracy of app description | 4 | The gate accurately describes what Nikko does and does not do. The non-diagnostic disclaimer is clear and prominent. |
| Goals | 4 | Non-diagnostic wellbeing support with evidence grounding is clearly stated in the gate, EULA, and Privacy Policy. Goals are specific and measurable by the SPEC-500 evaluation criteria. |
| Quality of information | 3 | Canned responses are well-written, empathetic, and evidence-informed with APA7 citations to legitimate Australian and international sources. However, the AI pipeline is not yet connected — all responses are predetermined patterns. Full quality assessment requires Phase 5 backend integration and Phase 6 evaluation. |
| Quantity of information | 3 | Six topic patterns with APA7-cited sources cover common mental health themes (sleep, anxiety, loneliness, rumination, crisis). Coverage is intentionally narrow — consistent with the non-diagnostic scope. No breadth issue at research preview stage, but will need expansion. |
| Visual information | 2 | No charts, graphs, or infographics. The sources panel provides citation context, and the avatar provides emotional signalling, but no educational visual content exists. Appropriate for a conversational interface; not a content-delivery app. |
| Credibility | 2 | No institutional endorsement, no clinical advisory board, no creator credentials displayed. The open-source nature and APA7 citations partially offset this, but a user encountering Nikko cold has limited basis for judging its credibility. This is the most significant information quality gap for a mental health tool. |
| Evidence base | 1 | No peer-reviewed publication, clinical trial, or systematic evaluation of Nikko itself exists. The AI pipeline has been designed according to evidence-informed principles and will undergo evaluation in Phase 6, but no published evidence base exists at this stage. This is expected for a research preview and must be addressed before any claim of evidence-based practice can be made. |

**Information quality mean: 2.7 / 5**

The low credibility and evidence base scores are not failures of execution — they are inherent limitations of a research preview that has not yet been formally evaluated. These scores will remain low until Phase 6 evaluation is complete and published.

---

### 2.5 Subjective Quality

This section requires real user testing and cannot be rated by the development team. The following items are documented as targets for Phase 6 evaluation:

- Would you recommend this app to people who might benefit from it?
- How many times would you use this app in the next 12 months?
- Would you pay for this app?
- Overall star rating

**Recommendation:** Include MARS subjective quality as a user-facing questionnaire in the Phase 6 evaluation protocol (SPEC-500 §9).

---

### MARS Summary

| Domain | Score | Max |
|---|---|---|
| Engagement | 3.0 | 5 |
| Functionality | 3.75 | 5 |
| Aesthetics | 4.0 | 5 |
| Information Quality | 2.7 | 5 |
| Subjective Quality | N/A (pending user testing) | 5 |
| **Overall (objective)** | **3.36** | **5** |

A score of 3.36 / 5 is reasonable for a research preview that has not yet connected its AI backend or undergone formal evaluation. The aesthetic and functionality scores reflect genuine strengths. Information quality will improve substantially once Phase 5 (backend integration) and Phase 6 (evaluation) are complete.

---

## 3. mERA Checklist (WHO 2016)

| No. | Criterion | Status | Notes |
|---|---|---|---|
| 1 | Infrastructure (population-level) | ✅ | Web browser + internet connection. No special infrastructure. Australia-only scope limits population applicability. |
| 2 | Technology platform | ✅ | React 18 SPA; Babel standalone; Python FastAPI backend (Phase 5 target); LLM fine-tuned on open-licence corpora (SPEC-400). Architecture documented in `docs/specs/` and `CLAUDE.md`. |
| 3 | Interoperability / HIS context | ❌ | No integration with existing health information systems. Not in scope for v0 research preview. A Phase 7+ consideration. |
| 4 | Intervention delivery | ✅ | Text-based, asynchronous, browser-based, available at any time. Session-scoped. Mode-based (Comfort / Guidance / Crisis) per user signal. Frequency and timing are user-determined. |
| 5 | Intervention content | ✅ | CBT-informed response framing; evidence retrieval (PubMed + web search on sanctioned AU/international health domains); APA7 citations; crisis escalation resources. Source and design documented in `docs/specs/`. |
| 6 | Usability / content testing | ❌ | No formative research or usability testing with target groups has been conducted. Required before Phase 7 deployment. Recommend at least one round of moderated usability testing with adults 18+ with lived mental health experience. |
| 7 | User feedback | ❌ | No user feedback mechanism exists in the UI. No satisfaction survey, rating, or feedback button. Recommend adding a lightweight feedback mechanism in Phase 5. |
| 8 | Access of individual participants | ⚠️ | **Barriers documented:** English-only; 18+ only; Australia-only; requires internet access and a modern browser. Low-literacy users and users with screen-reader needs are partially accommodated (ARIA labels present) but not formally tested. No cost barrier (free). |
| 9 | Cost assessment | ✅ | Free to use. Hosting costs (Hugging Face Spaces for research preview) are minimal. No formal economic analysis required at research preview stage. |
| 10 | Adoption inputs / programme entry | ❌ | No formal adoption or promotion strategy. App is accessible via a GitHub Pages link and referenced in the repository. No training materials for potential facilitators. |
| 11 | Limitations for delivery at scale | ⚠️ | Partially documented. "Research preview" labelling and single-host deployment (G-INFRA-01) are acknowledged. Multi-provider failover is a GA requirement. Formal limitations statement not yet published. |
| 12 | Contextual adaptability | ❌ | English-only; no translation; no cultural adaptation beyond AU-specific crisis resources (including 13YARN for First Nations users). No adaptations for different clinical populations. Phase 7 consideration. |
| 13 | Replicability | ⚠️ | Source code is referenced in the topbar (github link). Code is organised and documented. Full public open-sourcing not yet confirmed. SPEC documents provide algorithm-level transparency. Screenshots and flow descriptions exist in `docs/derived/`. |
| 14 | Data security | ✅ | Session-scoped zero-retention; no server-side conversation storage; AES-256-GCM for USM; HTTPS enforced in production; rate limiting specified (SPEC-600 §13). Privacy Policy §11 documents security commitments. |
| 15 | Compliance with national guidelines | ✅ | Australian crisis resources (SPEC-300 REQ-300-RS1/RS2); non-diagnostic disclaimer (REQ-000-020); 18+ gate (REQ-000-A01); Australian Privacy Act alignment (Privacy Policy §10). No regulatory registration required for research preview. |
| 16 | Fidelity of the intervention | ❌ | No mechanism currently tracks whether the intervention was delivered as designed. Backend pipeline trace (`PipelineTrace`) captures per-session execution data but this is ephemeral and not aggregated. Phase 6 evaluation harness (`SPEC-500`) will address this systematically. |

### mERA Summary

| Result | Count | Items |
|---|---|---|
| ✅ Met | 7 | 1, 2, 4, 5, 9, 14, 15 |
| ⚠️ Partially met | 4 | 8, 11, 13, 16 (partial) |
| ❌ Not met | 5 | 3, 6, 7, 10, 12 |

**7 of 16 criteria met; 4 partially met; 5 not met.** For a research preview that has not yet connected its AI backend, been formally evaluated, or entered a deployment phase, this is an expected profile. Items 3 (HIS integration), 6 (usability testing), 7 (user feedback), 10 (adoption), and 12 (adaptability) are all pre-Phase 7 requirements.

---

## 4. Cross-Framework Gaps and Prioritised Actions

The following gaps appear across two or more frameworks and represent the highest-priority improvements:

### Priority 1 — Before Phase 6 evaluation
| Gap | Frameworks | Action |
|---|---|---|
| No creator credentials or institutional attribution | GQP Reliability, MARS Credibility | Add researcher/team attribution in the EULA and a visible "About" element in the UI |
| No evidence base for the app itself | MARS Information Quality, mERA #16 | Phase 6 evaluation (SPEC-500) will address this; ensure results are published |
| No user feedback mechanism | mERA #7 | Add lightweight post-session feedback (single rating, optional comment) in Phase 5 |
| No usability testing with target group | mERA #6 | Conduct at least one round of moderated testing before Phase 7; document in Phase 6 |
| ~~Funding and COI disclosure absent~~ | GQP Reliability | ✅ **Resolved** — Self-funded, no COI, developer attributed in EULA §12 and Privacy Policy §1 |

### Priority 2 — Before Phase 7 deployment
| Gap | Frameworks | Action |
|---|---|---|
| No account-based authentication | GQP Authentication | Out of scope for zero-retention v0; must be re-evaluated if persistent accounts are introduced |
| ~~Tutorial not re-accessible~~ | GQP Usability | ✅ **Resolved** — `/help` command + `?` button in topbar both replay the tutorial |
| No fidelity tracking at scale | mERA #16 | Phase 6 evaluation harness; consider aggregated (non-PII) usage telemetry with opt-in consent |
| English-only; no adaptability | mERA #12 | GA-phase requirement; requires translation, cultural adaptation, and additional crisis resource sets |

### Priority 3 — GA phase
| Gap | Frameworks | Action |
|---|---|---|
| No HIS integration | mERA #3 | Requires formal clinical partnership scoping |
| No adoption strategy | mERA #10 | Requires a promotion, referral, and facilitator training plan |
| No third-party accreditation | GQP Reliability | Requires Phase 6 evidence base and formal application to relevant body (e.g., eSafety Commissioner) |

---

## 5. Assessment Conclusion

Nikko demonstrates genuine strengths in **aesthetic design** (4.0/5 MARS), **functional UX** (3.75/5), and **data architecture** — the zero-retention model exceeds the data retention requirements of all three frameworks. The clinical safety design (SPEC-300 crisis protocol, SPEC-000 non-replacement principle) is thorough and aligns with Australian mental health standards.

The primary weaknesses at this stage are structural research-preview limitations rather than design failures: no published evidence base, no institutional attribution, no formal usability testing, and no Phase 6 evaluation data. These are expected for a system still in active development and will be addressed through the Phase 6 evaluation protocol (SPEC-500).

Creator attribution, funding transparency, and COI declaration have now been addressed. The tutorial re-access gap is also resolved. The remaining open items (evidence base, usability testing, accreditation) require Phase 6 evaluation data and are expected to be resolved progressively through the gated phase plan.

**Overall readiness:** Suitable for internal research preview. Not yet suitable for public clinical deployment. Phase 6 evaluation is the critical gate.

---

*Assessor: NIKKO Engineering Collective. This assessment is self-reported and has not undergone independent third-party review.*

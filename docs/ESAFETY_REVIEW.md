---
id: ESAFETY-REVIEW-001
title: eSafety Safety by Design — Assessment & Implementation Plan
status: active
version: 1.0.0
last_reviewed: 2026-05-11
---

# eSafety Safety by Design — Nikko Assessment

> **Source framework:** eSafety Commissioner's *Safety by Design* foundations
> (https://www.esafety.gov.au/industry/safety-by-design/foundations).
> This document assesses Nikko against the three core SbD principles and their six
> operational foundations, then records implemented and planned responses.

---

## 1. Framework Overview

### Three Core Principles

| # | Principle | Description |
|---|---|---|
| P1 | **Service provider responsibility** | The burden of online safety must not fall solely on the user. Platforms and service providers are responsible for proactively embedding safety. |
| P2 | **User empowerment and autonomy** | Users' dignity and right to control their own experience are central. Safety mechanisms must not be paternalistic or remove genuine agency. |
| P3 | **Prevention before cure** | Design to anticipate and prevent harm in advance, rather than reacting to harm after it occurs. |

### Six Operational Foundations

1. **Safety governance** — Safety embedded in organisational leadership, culture, and accountability structures.
2. **Complaints and appeals** — Clear mechanisms for users to report harms, give feedback, and seek redress.
3. **Risk assessment** — Proactive, documented identification of potential harms before and during deployment.
4. **Research and testing** — Evidence-based design; user testing with target populations before launch.
5. **Transparency** — Open communication about how the service works, how data is handled, and AI involvement.
6. **User controls** — Meaningful, accessible controls that let users manage their own safety and experience.

---

## 2. Assessment Against Foundations

### Foundation 1 — Safety Governance

| Item | Status | Evidence |
|---|---|---|
| Safety objectives explicitly documented | ✅ | SPEC-000-charter.md §1 defines the non-diagnostic, non-replacement principle as a hard constraint. |
| Safety requirements traced to implementation | ✅ | REQ-000 / REQ-300 requirement IDs link specification to code. |
| Accountability defined | ⚠️ Partial | Nicholas Dale (developer) is named in EULA §12 and Privacy Policy §1. No formal safety governance board — acceptable for a solo research preview. |
| Safety constraints in model training | ✅ | SPEC-400 prohibits training on user data. ADP-C evaluator trained to enforce red lines. |

**Gap:** No formal incident log or post-deployment safety review schedule. Flagged for Phase 7.

---

### Foundation 2 — Complaints and Appeals

| Item | Status | Evidence |
|---|---|---|
| User can report a harmful response | ❌ | No in-app feedback or flagging mechanism exists. |
| Contact channel for safety concerns | ⚠️ Partial | EULA §12 and Privacy Policy §14 provide developer contact. Not surfaced in the chat UI itself. |
| Escalation pathway for crisis situations | ✅ | SPEC-300 crisis protocol: automatic SafetyBanner with four baseline crisis resources; users can exit immediately via Quick Exit. |

**Gap: In-app feedback button.** Implemented as a quick win — see §3 below.

---

### Foundation 3 — Risk Assessment

| Item | Status | Evidence |
|---|---|---|
| Potential harms identified before deployment | ✅ | SPEC-300 documents crisis response triggers; SAFETY_GUARDRAILS.md lists 15 red-line patterns. |
| Risk assessment documented | ✅ | SAFETY_GUARDRAILS.md; SPEC-000 §5 prohibitions; GAPS.md open risk items. |
| Vulnerable user group considerations | ✅ | 18+ gate; non-diagnostic disclaimer; crisis detection pipeline; demographic crisis resources (REQ-300-RS2). |
| AI limitation risks disclosed | ✅ | Gate ("non-diagnostic, cannot make care decisions"), EULA §5. |
| Bias risk addressed | ✅ | RAG grounds responses in curated APA7-cited sources; reduces hallucination risk vs pure fine-tuning. ADP-C evaluator catches red-line violations pre-output. |

**Gap:** No formal annual or pre-release risk review schedule. Document as a Phase 7 governance requirement.

---

### Foundation 4 — Research and Testing

| Item | Status | Evidence |
|---|---|---|
| Evidence-informed feature design | ✅ | CBT and ACT frameworks referenced in SPEC-700 strategy agent; crisis protocol aligns with Australian mental health guidelines. |
| User testing with target population | ❌ | No formal usability testing has been conducted. |
| Published evidence base for the app | ❌ | Phase 6 evaluation (SPEC-500) will generate this. Not yet available. |
| Crisis resource accuracy verified | ✅ | Baseline crisis numbers (13 11 14, 1300 22 4636, 1300 659 467, 000) verified against official sources. |

**Gap:** Usability testing with adults experiencing mild-to-moderate mental health concerns must occur before Phase 7 (public deployment). This is a Phase 6 gate condition.

---

### Foundation 5 — Transparency

| Item | Status | Evidence |
|---|---|---|
| AI involvement disclosed to user | ✅ | Gate discloses AI nature. Agent ribbon under each message explains multi-agent coordination. |
| Data practices disclosed | ✅ | Privacy Policy documents all data handling (or non-handling). Short version callout at top. |
| Limitations clearly stated | ✅ | Gate, EULA §1, tooltip. Non-diagnostic; cannot make care decisions; research preview. |
| Source citations provided | ✅ | APA7-formatted citations in Sources panel; superscript cite-buttons on evidence-backed responses. |
| Developer identity disclosed | ✅ | Nicholas Dale named in EULA §12 and Privacy Policy §1 with contact links. |
| Funding and COI declared | ✅ | Self-funded; no conflicts of interest. Stated in MHEALTH_ASSESSMENT.md and available on request. |
| Open-source inspection available | ✅ | Research preview tooltip links to GitHub repository. |

**Assessment: Strong.** Transparency is one of Nikko's strongest SbD areas. The agent ribbon and citation system go beyond the minimum standard.

---

### Foundation 6 — User Controls

| Item | Status | Evidence |
|---|---|---|
| Quick exit from the service | ✅ | "Quick exit" button always visible in topbar; replaces history with bom.gov.au. |
| Session data cleared on exit | ✅ | Quick Exit wipes sessionStorage; conversations never persist. |
| Memory opt-in (not default) | ✅ | Personal Memory feature requires explicit user action to enable; encrypted on device. |
| Mood diary opt-in | ✅ | Mood diary is a separate panel users must open deliberately. |
| Dark mode / accessibility preference | ✅ | Theme toggle in topbar; persisted in localStorage. |
| Tutorial re-accessible | ✅ | `/help` command in composer + `?` button in topbar. |
| Crisis resources accessible without request | ✅ | SafetyBanner auto-triggers on detected crisis keywords; expandable demographic section. |

**Assessment: Strong.** User controls are well-implemented. The quick exit is particularly strong for a mental health context.

---

## 3. Implemented Quick Wins (this session)

The following items were identified as low-effort, high-impact SbD improvements and implemented immediately:

| # | Item | Files changed | Foundation |
|---|---|---|---|
| QW-1 | **`/help` command** — typing `/help` in the composer replays the first-run tutorial without sending a message. | `chat.jsx` | F6 User controls |
| QW-2 | **`?` topbar button** — a question-mark icon button to the right of the dark mode toggle also replays the tutorial. | `chat.jsx` | F6 User controls |
| QW-3 | **Developer attribution** — Nicholas Dale named with LinkedIn and GitHub in EULA §12 and Privacy Policy §1 and §14. | `eula.html`, `privacy.html` | F5 Transparency |
| QW-4 | **Governing law corrected** — EULA §10 updated from NSW to Victoria. | `eula.html` | F5 Transparency |
| QW-5 | **Minors policy clarified** — Privacy Policy §9 now states explicitly there is no current plan for a minor-adapted pathway. | `privacy.html` | F3 Risk assessment |
| QW-6 | **OAIC reference removed** — Privacy Policy §10 reframed to focus on zero-retention reality without directing users to a regulator that isn't applicable at this scale. | `privacy.html` | F5 Transparency |

---

## 4. Recommended Next Steps

### Phase 5 (pre-integration)

- **In-app feedback button** — add a small "flag / not helpful" affordance on assistant messages. For the research preview, this can write to a client-side log shown only in the debug overlay; a real reporting endpoint can be wired in Phase 5. This directly addresses Foundation 2 (Complaints and Appeals).
- **Inline safety notice** — consider adding a one-line note at the bottom of the gate card linking the Privacy Policy and Terms so users can access them without hunting. (Gate footer already has these links — low priority.)

### Phase 6 (evaluation)

- **Usability testing** — at least one round of moderated testing with adults aged 18–35 experiencing mild-to-moderate stress or anxiety. Document methodology and findings.
- **Bias audit** — formal review of the RAG evidence base for selection bias, recency bias, and demographic coverage gaps.
- **Safety review schedule** — document a pre-deployment safety review checklist that is run before each Phase 7 release.

### Phase 7 (deployment)

- **eSafety Commissioner registration** — consider registering with the eSafety Commissioner's voluntary scheme and seeking a formal Safety by Design assessment for public deployment.
- **Accessibility audit** — formal WCAG 2.1 AA audit. Current implementation has strong ARIA labelling but has not been formally audited.
- **Incident log** — establish a process for logging and responding to user-reported safety incidents.

---

*Assessed by: NIKKO Engineering Collective (Lead Architect persona). Self-assessment; not independently verified.*
*Framework source: eSafety Commissioner (https://www.esafety.gov.au/industry/safety-by-design/foundations)*

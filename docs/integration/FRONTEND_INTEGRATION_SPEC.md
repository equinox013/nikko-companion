---
id: FRONTEND_INTEGRATION_SPEC
title: Frontend-Backend Integration Contract
status: authoritative
depends_on: [SPEC-200, SPEC-300, SPEC-600]
version: 1.0.0
last_reviewed: 2026-05-14
---

# FRONTEND_INTEGRATION_SPEC — Frontend-Backend API Contract

## Status

**AUTHORITATIVE** — Promoted from draft 2026-05-14. Defines the binding API contract between `web/` (React frontend) and backend agents (Phase 3). Phase 5 gate condition satisfied.

## Overview

This spec defines the API surface, message protocols, error handling, and state synchronization between:
- **Frontend:** `web/` React SPA (Phase 5)
- **Backend:** agents, orchestration, classifier services (Phase 3)

The frontend currently uses hardcoded canned responses (`nikko-data.jsx`). This spec replaces those with live backend agent calls.

## 1. High-level architecture

### Request–response model

```
User types message in Composer
    ↓
Chat.onSend(text)
    ↓
POST /api/message { text, contextID, userId? }         ← Render (FastAPI)
    ↓
POST /pipeline { messages, system, safety_system,      ← HF Spaces (ZeroGPU)
                 eval_system, token }
    ↓ single @spaces.GPU(duration=300) session
  ADP-B (Safety / crisis check, Gemma-2-2b-it bf16)
    ↓ if CLEAR
  ADP-A (Empathy response draft, Qwen3-4B bf16, no LoRA)
    ↓
  ADP-C (Quality evaluator; triggers one regen if REGENERATE)
    ↓
  { text, is_crisis, flags, verdict, regen, elapsed }
    ↓
SSE stream: message_start → chunk(s) → message_end    ← back to frontend
    ↓
Chat receives stream, renders MessageBody with emotion-driven avatar.
Final chunk carries pipeline trace for AgentDebugOverlay.
```

> **Phase 7 architecture note:** ADP-B, ADP-A, and ADP-C previously ran as three separate `/infer` calls, each incurring an 80–110s CPU→VRAM transfer per session. Consolidating them into a single `/pipeline` call under one GPU session eliminates two transfer overhead costs, reducing warm-turn latency from ~240–330s to ~20–40s. The Render backend no longer calls `/infer`; it calls `/pipeline` with all three system prompts in a single request. Primary inference: Modal Serverless A10G. Fallback: HF Spaces ZeroGPU H200. `PIPELINE_TIMEOUT_S = 360`.

### WebSocket (alternative for Phase 6+)

For lower-latency multi-turn conversations, Phase 6 may upgrade to WebSocket streaming. Spec TBD.

---

## 2. Message API (`POST /api/message`)

### Request

```json
{
  "text": "I haven't been sleeping well",
  "contextID": "session-20260510-abc123",
  "memoryFileHash": "sha256-...",      // optional; if user has loaded memory file
  "moodSnapshot": {
    "timestamp": "2026-05-10T14:23:00Z",
    "selfReport": 3
  }
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `text` | string | **yes** | User message. Must be 1–2000 chars. |
| `contextID` | string | **yes** | Session identifier. Frontend generates on Gate entry; remains stable. See §4 (Session Management). |
| `memoryFileHash` | string | no | SHA-256 hash of loaded memory file (not the file itself). Allows backend to detect which memory context is active without re-uploading. |
| `moodSnapshot` | object | no | Current mood state from diary. Omitted if user hasn't logged a mood. |
| `moodSnapshot.timestamp` | ISO 8601 | yes (if mood) | When the mood was reported. |
| `moodSnapshot.selfReport` | int (1–5) | yes (if mood) | Mood numeric scale; see GLOSSARY.md for scale. |

### Response (streaming)

Backend streams **multiple chunks** as `text/event-stream`:

```
event: message_start
data: { "id": "msg-20260510-xyz", "emotion": "listen" }

event: chunk
data: { "text": "Sleep that won't come is exhausting in its own right", "emotion": "listen", "sourcesUsed": [] }

event: chunk
data: { "text": " — and noticing it is a real thing, not a small one.", "emotion": "listen", "sourcesUsed": [] }

event: chunk
data: { "text": "\n\nA few patterns tend to help...", "emotion": "search", "sourcesUsed": ["s_sleep", "s_breath"] }

event: message_end
data: { "id": "msg-20260510-xyz", "safetyFlags": [] }
```

Each `chunk` event:

```json
{
  "text": "string chunk of the response",
  "emotion": "calm | listen | search | speak | care | think",
  "sourcesUsed": ["s_sleep", "s_breath"],
  "safetyFlags": [],
  "trace": null,
  "memory_proposal": null,
  "technique_recommended": null
}
```

| Field | Type | Notes |
|-------|------|-------|
| `text` | string | Partial response text. Empty string on emotion-only signal chunks. |
| `emotion` | string | One of the six avatar states (see table below). |
| `sourcesUsed` | string[] | Source keys for the citation library. Empty on most chunks. |
| `safetyFlags` | string[] | `["crisis_detected"]` on crisis path. Empty otherwise. |
| `trace` | object \| null | **Phase 7 addition.** Pipeline trace for the agent debug panel. Only present on the final substantive chunk. Shape: `{is_crisis, flags, verdict, regen, elapsed, adp_b, adp_a, adp_c}`. Frontend stores in `NikkoAgentLog`. `null` on fallback/canned responses. |
| `memory_proposal` | object \| null | **Phase 6 addition.** Present on the final chunk when `_AFFIRMATION_RE` matches the user message. Shape: `{canonical: string, usm_entry: string}`. Frontend surfaces an inline proposal card. Only emitted when a `.enc` file is loaded (`memContentRef && sessionKeyRef`). Mutually exclusive with `technique_recommended` per turn. |
| `technique_recommended` | object \| null | **Phase 6 addition.** Present on the final chunk when `_RESPONSE_RECOMMEND_RE` matches ADP-A output (APPROVE path only). Shape: `{canonical: string, usm_entry: string}`. Frontend surfaces `TechniqueCheckInBanner` (accent-bordered popup). Suppressed if `memory_proposal` fired on the same turn. |
| `stage` | string \| null | **Phase 6 addition.** Canonical pipeline stage label (see [SPEC-700 §16](../specs/SPEC-700-execution-pipeline.md#16-pipeline-stage-labels-user-facing) for full enumeration). Emitted on progress chunks as each pipeline step begins. `null` on text-content chunks. Frontend stores the most recent non-null value and displays it in the `AgentRibbon` while processing is active. |

End-of-message footer:

```json
{
  "id": "msg-xxx",
  "safetyFlags": ["crisis_detected", "ethical_concern"]
}
```

### Emotion state mapping

| Backend output | Avatar glyph | Ray animation | Meaning |
|---|---|---|---|
| `calm` | (none) | idle | Neutral; waiting for user |
| `listen` | `?` (question) | idle | Actively receiving; no processing |
| `search` | `~` (squiggle) | spin | Searching knowledge base or ruminating on response |
| `think` | `∴` (pulse) | pulse | LLM generating; token-by-token |
| `speak` | `☺` (smile) | pulse | Delivering response; confident |
| `care` | `⌣` (soft smile) | idle | Empathetic response; crisis detected |
| `uncertain` | `?` (question, dimmed) | slow fade-pulse | Signal Agent confidence < 0.40; Nikko's read is unclear. Overrides mode-default state. |

### HTTP status codes

| Code | Meaning | Frontend behavior |
|------|---------|---|
| 200 OK | Message processed; stream follows | Render chunks as they arrive |
| 400 Bad Request | Invalid `contextID` or `text` too long | Show error toast; allow retry |
| 429 Too Many Requests | Rate limit exceeded | Disable composer; show countdown |
| 500 Internal Server Error | Backend error | Show toast: "Nikko is having trouble. Try again." |
| 503 Service Unavailable | Agents offline | Fallback to canned response (Phase 7); show notification |

---

## 3. Crisis Detection & Safety

[REQ-300-161] When user message matches crisis keywords (suicide, self-harm, immediate danger), backend MUST respond with `emotion: "care"` and include crisis hotlines in the response text.

[REQ-300-162] Safety banner (Australian hotlines) SHALL auto-display when `safetyFlags` includes `"crisis_detected"`.

[REQ-300-163] Quick-exit button SHALL always be visible. On click, frontend wipes session state and navigates to `https://www.bom.gov.au/`.

---

## 4. Session management

### Session initialization

On Gate entry (`onEnter()`), frontend generates a `contextID`:

```javascript
// [FIX 2026-05-11] Uint8Array.hex() is not a browser API. Use Array.from + map instead.
const bytes = crypto.getRandomValues(new Uint8Array(6));
const hex   = Array.from(bytes).map(b => b.toString(16).padStart(2, '0')).join('');
const contextID = `nikko-${Date.now()}-${hex}`;
// → "nikko-1715334180000-a1b2c3d4e5f6"
```

This ID is stored in React state (not localStorage, per SPEC-800) and sent with every message.

### Session termination

On browser close or quick-exit, `sessionStorage` and conversation state are cleared. Memory file (if loaded) is retained in browser memory only for the duration of the session; not saved server-side unless user explicitly triggers "Generate" modal.

---

## 5. Memory file API (Phase 5 / Phase 6)

> **Architecture note — client-side encryption is mandatory.** SPEC-850, GLOSSARY.md USM terms, and G-MEMORY-01 ratification collectively require that all USM encrypt/decrypt operations occur in the user's browser via the Web Crypto API. The backend MUST NEVER generate or receive the encrypted memory file. The original draft of this section (v0.1.0) incorrectly placed encryption server-side — this version corrects that. [PROPOSED-RECONCILIATION: moved encryption to client as per SPEC-850 §3 and G-MEMORY-01 ratification 2026-05-09.]

### Generate memory file — client-side flow

The Generate flow is entirely client-side in `web/memory.jsx`. No API call is required for the v0 implementation, where the memory template is pre-populated client-side.

**Phase 5 optional backend assist** — `POST /api/memory/summarize`

If the backend is asked to contribute memory-worthy content (e.g. a compressed digest of the conversation), it returns **plaintext only**. The frontend then encrypts locally and triggers a download.

**Request:**

```json
{
  "contextID": "nikko-...",
  "conversationExcerpts": [{ "role": "user", "text": "..." }, ...]
}
```

**Response (plaintext — never encrypted by backend):**

```json
{
  "memoryMarkdown": "## Emotional Patterns\n...",
  "suggestedFilename": "nikko-memory-20260510"
}
```

Frontend receives `memoryMarkdown`, appends it to the empty template from `makeEmptyMemoryMd()`, calls `encryptMemory(combined, userPassword)` via Web Crypto, and triggers a local file download. The backend never sees the password or the ciphertext.

### Load memory file — client-side only

Frontend reads file client-side (JavaScript File API), decrypts it locally via `decryptMemory()` in `web/memory.jsx` (AES-256-GCM, PBKDF2-SHA256 key derivation). Backend is never given the plaintext memory, the ciphertext, or the password.

---

## 6. Source citations API (Phase 5+)

When backend emits `sourcesUsed: ["s_sleep"]`, frontend looks up the source in a **static library** (initially `NIKKO_SOURCES` from `nikko-data.jsx`).

**Phase 5 plan:** Backend sends source keys; frontend renders from static library.

**Phase 6+ plan:** Backend can return full source objects if static library is insufficient. TBD.

---

## 7. Error handling & fallback

### Pipeline latency & waiting UX

**[Phase 7 update]** The backend pipeline (ADP-B → ADP-A → ADP-C) runs inside a single HF Spaces ZeroGPU session. Observed latency:

| Condition | Latency |
|-----------|---------|
| Warm (GPU context live) | 20–40s |
| Cold start (first call / after idle) | 90–120s |
| Regen pass (ADP-C triggered REGENERATE) | +20–30s |

A 5-second "no response" timeout is therefore **not applied**. The `PIPELINE_TIMEOUT_S` on the backend is 360s (6 minutes), giving comfortable headroom for cold start + regen.

**Frontend waiting UX (`ThinkingBubble`):** While `m.text === ''` and `m.streaming === true`, the frontend renders a `ThinkingBubble` component (not a static spinner) that displays staged labels timed to expected pipeline phases:

| Elapsed | Label |
|---------|-------|
| 0–6s | "Reading your message…" |
| 6–14s | "Checking in on what you shared…" |
| 14–24s | "Putting together a response for you…" |
| 24s+ | Cycles through affirmations every 5s (e.g. "Making the best response. Because you matter.") |

This manages user expectation during the full cold-start wait without triggering anxiety or suggesting an error state.

### Network timeout (360 seconds)

If the POST request has no HTTP response after 360 seconds (matching `PIPELINE_TIMEOUT_S`), frontend falls back to `matchNikkoPattern()` (canned response) and logs a console warning. This should be treated as a backend failure, not normal operation.

### JSON parse error in stream

If a chunk event doesn't parse as JSON, frontend logs the error and skips that chunk.

### Missing required fields

If a chunk lacks `text` or `emotion`, frontend uses defaults:
- `emotion` defaults to `"calm"`
- `text` defaults to `""` (empty paragraph)

### Backend 500 error

Frontend shows:

> "I'm having trouble right now. Would you like to try again?"

And disables the Composer for 2 seconds.

### Service unavailable (503)

**Phase 5:** Fall back to canned response from `nikko-data.jsx`.
**Phase 7:** Show persistent notification: "Offline mode — responses are pre-written."

---

## 8. Rate limiting

**[REQ-FIS-RL1]** Backend SHALL implement rate limiting: max 50 messages per session per hour.

When limit is exceeded:

- HTTP 429 response
- Frontend disables Composer and shows countdown: "You're chatting a lot. Let's take a break for {minutes}m {seconds}s."

---

## 9. Testing & mock endpoints

For Phase 5 integration testing, backend SHOULD provide `/api/message/mock` endpoint that:

1. Accepts same request shape as `/api/message`.
2. Returns hardcoded streaming response (same format as live endpoint).
3. Useful for frontend testing without live agents.

---

## 10. Outstanding questions for Director

- [ ] Should the backend return emotion state per-chunk, or is one emotion per message sufficient?
- [ ] How should we handle multi-turn conversations? Store `conversationHistory` server-side, or expect frontend to replay?
- [ ] Does the memory file `publicKey` need to be rotated? When?
- [ ] Should `contextID` expire after 24 hours, or persist for the life of the browser session?
- [ ] What's the acceptable latency for a Crisis Detection response (P95)?

---

## 11. API endpoint reference

| Method | Endpoint | Status | Phase |
|--------|----------|--------|-------|
| GET | `/health` | spec'd | Phase 7 |
| POST | `/api/message` | spec'd | Phase 5 |
| POST | `/api/memory/summarize` | optional assist | Phase 5 |
| POST | `/api/message/mock` | optional | Phase 5 (testing) |
| GET | `/api/sources` | planned | Phase 6 |
| WS | `/ws/message` | planned | Phase 6 |

---

## 12. Loading Screen & Cold Start UX

### 12.1 Purpose

The loading screen is the first thing a user sees. It serves two functions: (1) masking the cold-start latency of the Render orchestration service (or HF Spaces ZeroGPU spin-up), and (2) orienting the user to what Nikko is before they enter the Gate. It MUST feel intentional, not like an error state.

### 12.2 Trigger condition

[REQ-FIS-LS1] The loading screen SHALL display immediately on app load, before the Gate component mounts. It MUST NOT be skipped even if `/health` responds instantly — a minimum display duration of 1.5 seconds ensures the transition feels deliberate rather than glitchy.

[REQ-FIS-LS2] The frontend SHALL begin polling `GET /health` (on the Render backend) at 3-second intervals from the moment the loading screen appears. See REQ-600-HL1–HL4 for server-side health check spec.

### 12.3 Visual components (required)

[REQ-FIS-LS3] **Avatar — breathing idle animation.** The Nikko avatar SHALL be displayed in a slow, looping "breathing" idle state: a gentle scale pulse (e.g. `scale 1.0 → 1.06 → 1.0`) at ~4-second period. The avatar MUST NOT display any emotion glyph during loading — it is pre-interaction state.

[REQ-FIS-LS4] **Title block.** Below the avatar, display:
- Primary: `"Nikko"` — large, prominent
- Secondary: `"Agentic Wellbeing Assistant"` — smaller, muted
- Badge: `"Research Preview"` — pill/badge style, subdued colour

[REQ-FIS-LS5] **Feature carousel.** A horizontally-paginated carousel of 3–4 brief orientation cards SHALL be displayed below the title block. Suggested cards (Director may revise copy):
1. *"Nikko listens without judgment, drawing on evidence-based wellbeing strategies to support you."*
2. *"Not a therapist, not a crisis line — Nikko is a thinking partner for your mental wellbeing."*
3. *"Your conversation is private. Nothing is stored. Close the tab and it's gone."*
4. *"If you're in crisis, Nikko will always point you to real human support."*

Carousel MUST auto-advance every 4 seconds and be manually swipeable/clickable.

[REQ-FIS-LS6] **Theme toggle.** A light/dark mode selector SHALL be visible and operable during the loading screen. This is the only persistent preference the user can set before the Gate — it MUST be stored in `localStorage` (exception to the no-`localStorage` rule: theme preference is non-sensitive UI state, not conversation data).

[REQ-FIS-LS7] **Background particle animation — theme-dependent.**
- **Light mode:** Softly floating translucent bubble particles (circular, low opacity, gentle upward drift with slight lateral wobble). Density: ~12–18 bubbles on screen at any time. No interaction required.
- **Dark mode:** Slowly rotating/twinkling star field (small white/pale-blue dots at varying opacity, subtle parallax or gentle rotation). Density: ~30–50 stars. No interaction required.
Both animations MUST be CSS/canvas-based, lightweight, and MUST NOT consume significant CPU. They MUST pause/reduce when the `prefers-reduced-motion` media query is active.

[REQ-FIS-LS8] **Footer links.** A subtle footer (low contrast, small type) SHALL contain two links:
- `Terms & Conditions` → links to a `/terms` page or anchor (content TBD Phase 7)
- `Privacy Policy` → links to a `/privacy` page or anchor (content TBD Phase 7)

These links MUST be openable during the loading screen without interrupting the health-check poll.

### 12.4 Transition to Gate

[REQ-FIS-LS9] On receipt of `HTTP 200` from `GET /health` (and after the 1.5-second minimum display time), the loading screen SHALL transition smoothly into the Gate component. Transition: fade-out loading screen → fade-in Gate, duration ~400ms. The avatar MAY carry over into the Gate view rather than re-mounting.

[REQ-FIS-LS10] The transition MUST NOT be jarring. The particle animation SHOULD continue through the transition and fade naturally rather than cutting abruptly.

[REQ-FIS-LS11] If `/health` does not return `200` within 60 seconds (REQ-600-HL3), the carousel and animations continue running, and a non-alarming message replaces the loading indicator: *"Nikko is taking a moment to wake up — this can happen after a period of inactivity. Hang tight."* A manual **"Try again"** button resets the 60-second poll timer.

### 12.5 Accessibility

[REQ-FIS-LS12] The loading screen MUST be accessible: the breathing avatar animation MUST have `aria-label="Nikko is loading"` or equivalent; the carousel MUST be navigable by keyboard; the theme toggle MUST be keyboard-operable and labelled.

[REQ-FIS-LS13] The `prefers-reduced-motion` media query MUST disable or significantly reduce all animations (avatar pulse, carousel auto-advance, particle animations) while preserving static visual content.

### 12.6 Implementation location

`web/` — a new `loading.jsx` component is the recommended home for this screen. It should be mounted as the app's root state before `Gate` mounts, driven by a `status: 'loading' | 'ready' | 'timeout'` state variable in the root `nikko.jsx`.

---

## 13. AgentRibbon — Pipeline Status Labels

### 13.1 Purpose and visual treatment

[REQ-FIS-RB1] The `AgentRibbon` component MUST display a subtle, secondary-weight status label on the active message bubble during pipeline processing. The label communicates system activity without competing with message content. It is an ambient indicator, not a notification.

[REQ-FIS-RB2] Visual requirements:
- Font size: ≤0.72rem (secondary body size or smaller)
- Colour: `var(--ink-2)` or equivalent muted secondary colour — MUST NOT use primary text colour
- No background, no border, no badge treatment
- Icon: the existing three-node graph SVG glyph (already in `AgentRibbon`) is retained unchanged

[REQ-FIS-RB3] The label text MUST NOT use technical terminology. Model names (ADP-A, Qwen3-4B, Gemma), pipeline step numbers, and internal component identifiers MUST NOT appear in the ribbon.

### 13.2 Dynamic behaviour during processing

[REQ-FIS-RB4] While a message is being processed, the ribbon MUST display the most recent non-null `stage` value received from the SSE stream. The label updates in place as each new `stage` value arrives.

[REQ-FIS-RB5] On completion, the ribbon MUST transition to a static summary state. The summary MUST display the routing mode in plain language:
- Comfort Mode → `comfort mode`
- Guidance Mode → `guidance mode`  
- Crisis Mode → *(ribbon hidden; crisis banner takes precedence)*
- Out-of-scope / warm redirect → `outside my scope`
- Fallback / offline → `offline mode`

[REQ-FIS-RB6] The static summary state replaces "3 adapters" (the current hardcoded text). The adapter count MUST NOT appear in any user-facing label — it is implementation detail, not user information.

[REQ-FIS-RB7] The ribbon label MAY be tapped/clicked to open the `AgentDebugOverlay` — this is the existing gesture (double-click + hold). The ribbon itself is not a button and carries no affordance indicating tappability.

### 13.3 Stage label sequence (canonical)

The following is the expected label sequence for each routing path, derived from [SPEC-700 §16](../specs/SPEC-700-execution-pipeline.md#16-pipeline-stage-labels-user-facing):

**Comfort path:** `checking relevance` → `reading between the lines` → `understanding your message` → `forming a response` → `making sure this is right` → *(complete: `comfort mode`)*

**Guidance path:** `checking relevance` → `reading between the lines` → `understanding your message` → `searching health resources` → `reviewing the evidence` → `forming a response` → `making sure this is right` → `final check` → *(complete: `guidance mode`)*

**Crisis path:** `checking relevance` → `understanding your message` → *(structural pre-pass skipped per SPEC-700 §5.3)* → *(complete: ribbon hidden, crisis banner active)*

---

## 14. AgentDebugOverlay — Expanded Trace Spec

### 14.1 Purpose

The debug overlay exposes the full pipeline execution trace for transparency and developer inspection. It is accessible via the double-click-then-hold gesture on the ribbon (unchanged). It surfaces data from the `trace` field of the final SSE chunk and from `NikkoAgentLog`.

### 14.2 Expanded `trace` schema

[REQ-FIS-DB1] The `trace` object on the final SSE chunk MUST be expanded to include the following fields in addition to the existing `adp_b`, `adp_a`, `adp_c`, `is_crisis`, `flags`, `verdict`, `regen`, `elapsed`:

```json
{
  "is_crisis": false,
  "flags": [],
  "verdict": "APPROVE",
  "regen": false,
  "elapsed": "34.2",
  "mode": "COMFORT",

  "pre_analysis": {
    "struct_tags": ["register_collapse"],
    "para_tags": ["tone_softener"],
    "suppressed": false,
    "raw_notes": "[STRUCT: register_collapse] [PARA: tone_softener] ..."
  },

  "signal": {
    "distress_level": "moderate",
    "emotional_states": ["sadness_spectrum", "emotional_numbness"],
    "cognitive_patterns": ["helplessness_framing"],
    "behavioral_indicators": ["withdrawal"],
    "risk_indicators": [],
    "support_needs": ["emotional_validation", "grounding"],
    "confidence": 0.62
  },

  "router": {
    "decision": "COMFORT",
    "confidence": 0.74,
    "rationale": "distress_level=moderate, no risk indicators, guidance_keywords absent"
  },

  "scope_verdict": "in_scope",

  "enhanced_signal": {
    "dominant_theme": "social_isolation",
    "intensity_shift": "stable",
    "ambiguity_flags": []
  },

  "enhanced_strategy": {
    "recommended_tone": "warm_validating",
    "avoid": ["direct_advice", "minimisation"],
    "technique_hint": null
  },

  "evidence": null,

  "adp_b": { "label": "Safety / crisis check", "verdict": "CLEAR", "flags": [] },
  "adp_a": { "label": "Empathy response draft", "chars": 312, "usm_injected": true },
  "adp_c": { "label": "Quality evaluator", "verdict": "APPROVE", "regen": false }
}
```

[REQ-FIS-DB2] `pre_analysis` MUST be populated when the Structural Pre-Analysis pass ran. `suppressed: true` indicates the pass ran but structural signals were suppressed (first-turn limitation). `null` indicates the pass did not run (pre-pass failure, or crisis path skip).

[REQ-FIS-DB3] `signal` MUST surface the full SPEC-100 §9 signal object. If the Signal Agent output is unavailable (e.g. fallback path), `signal` MUST be `null` rather than a partial object.

[REQ-FIS-DB4] `router` MUST surface the routing decision, the router's confidence, and a brief rationale string. This is the primary epistemic transparency field — it allows a user who sees the debug panel to understand *why* Nikko responded the way it did.

[REQ-FIS-DB5] `evidence` MUST be non-null on Guidance Mode responses and MUST contain: `{ sources_queried: ["pubmed", "healthdirect"], results_count: 3, confidence: 0.81 }`. On Comfort Mode it MUST be `null`.

[REQ-FIS-DB9] **Phase 6 addition.** `scope_verdict` carries the Qwen3-4B scope analysis result (`"in_scope"` / `"ambiguous"` / `"out_of_scope"`). `null` indicates the analysis pass did not run or was skipped (e.g. crisis early exit). `enhanced_signal` and `enhanced_strategy` carry enrichment outputs from the signal and strategy analysis passes respectively; both are `null` when the enrichment passes were skipped.

### 14.3 Debug overlay UI expansion

[REQ-FIS-DB6] The overlay MUST add the following cards above the existing ADP-B/A/C adapter cards:

- **Pre-Analysis card** (Step 0.5): shows `struct_tags` and `para_tags` arrays, or "first turn — structural signals suppressed" if `suppressed: true`, or "pre-pass failed" if `null`.
- **Signal card** (Step 1): shows `distress_level` (large, colour-coded), `confidence`, `emotional_states` as chips, `risk_indicators` as chips (red if non-empty). Replaces the current implicit mode display.
- **Router card** (Step 2): shows `decision` (large, mode badge), `confidence`, `rationale` string.

[REQ-FIS-DB7] The existing mode badge at the top of the overlay (`COMFORT` / `CRISIS`) MUST be updated to also show `GUIDANCE`. Current implementation only distinguishes `COMFORT` vs `CRISIS` via `is_crisis` boolean — this MUST be replaced with the explicit `mode` string from the trace.

[REQ-FIS-DB8] The "Raw pipeline payload" `<details>` section MUST be retained and updated to include all new trace fields.

---

## 15. Mood Check-in Popup

### 15.1 Trigger

[REQ-FIS-MC1] The `MoodCheckInPopup` component MUST render once per session, inline in the chat thread, immediately after the welcome-back message that fires on successful memory file load (`onMemoryLoaded`). It MUST NOT render on sessions without a loaded memory file. It MUST NOT re-render after it has been submitted or dismissed within the same session.

[REQ-FIS-MC2] The popup is triggered in `chat.jsx` inside the `onMemoryLoaded` handler, after `setMemName(name)` and after the welcome-back message is appended to the thread. It renders as a chat-adjacent card, not a modal.

### 15.2 Component layout

```
┌─────────────────────────────────────────────────────────┐
│  Before we continue — how are you feeling right now?    │
│                                                         │
│  [1][2][3][4][5][6][7][8][9][10]                       │
│   ↑ rough                          ↑ good              │
│                                                         │
│  ── optional, fades in on number selection ──           │
│  [sad][anxious][flat][heavy][okay][calm][other]         │
│                                                         │
│  [Skip for now]                     [Log it  →]        │
└─────────────────────────────────────────────────────────┘
```

[REQ-FIS-MC3] The numeric rating (1–10) is mandatory for submission. Emotion chips are optional and multi-select. "Skip for now" dismisses without writing any data.

[REQ-FIS-MC4] Emotion chips MUST be drawn from the SPEC-100 §4 canonical emotional state categories, surface-level labels only. The chip set is: `sad`, `anxious`, `flat`, `heavy`, `okay`, `calm`. An `other` chip that does not pre-populate any specific label is permitted.

### 15.3 Data handling

[REQ-FIS-MC5] On "Log it →" submission, the popup MUST write a diary entry directly into `pendingEntries` using the existing round-trip format:
```
YYYY-MM-DD | mood: N | emotions: a, b
```
Where `N` is the numeric rating (1–10) and `a, b` are the selected emotion chip labels (omitted if none selected). No `note:` line is written by the popup — the user has not typed anything.

[REQ-FIS-MC6] The popup MUST NOT trigger a backend pipeline call. It is a frontend-only data capture path. The logged entry becomes available in the MoodDiaryPanel immediately and is included in the next memory file save/re-encrypt cycle via the existing `pendingEntries` mechanism.

[REQ-FIS-MC7] After submission or dismissal, the popup MUST disappear from the thread and MUST NOT reappear for the remainder of the session. A session-scoped `moodCheckInShownRef` flag gates the trigger (analogous to `hintShownRef` for the memory hint banner).

### 15.4 Visual style

[REQ-FIS-MC8] The popup MUST be styled consistently with `TechniqueCheckInBanner` (accent-coloured border, not crisis red). The 1–10 number buttons are inline pill buttons with clear selected/unselected states. Chip selection uses toggle styling. The component is NOT a modal — it scrolls with the chat thread as a message-adjacent card.

---

## 16. Health check endpoint reference

| Method | Endpoint | Host | Status | Phase |
|--------|----------|------|--------|-------|
| GET | `/health` | Render | spec'd | Phase 7 |

See REQ-600-HL1–HL4 for server-side requirements.

---

## Related specs

- [SPEC-200 — Agent Communication Protocol](../specs/SPEC-200-agent-communication-protocol.md): Message structure, agent handoff.
- [SPEC-300 — Crisis Response Protocol](../specs/SPEC-300-crisis-response-protocol.md): Safety thresholds.
- [SPEC-600 — Deployment Architecture](../specs/SPEC-600-deployment-architecture.md): API server topology.
- [SPEC-800 — Data Lifecycle & Privacy](../specs/SPEC-800-data-lifecycle-privacy.md): Zero-retention policy.

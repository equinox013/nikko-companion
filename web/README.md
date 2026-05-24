# web/ — NIKKO Frontend

The NIKKO frontend is a standalone React SPA deployed via GitHub Pages at
[equinox013.github.io/nikko](https://equinox013.github.io/nikko). It communicates
with the Render backend over HTTP/SSE and falls back to canned responses when the
backend is unreachable.

---

## Architecture overview

```
Browser
  │
  ├── index.html          GitHub Pages entry point (5-line redirect → Nikko.html)
  └── Nikko.html          App shell — loads styles, compiled JS bundles, React via CDN
        │
        ├── nikko.jsx     Root component: theme, layout, decorative canvas elements
        ├── gate.jsx      Consent gate: 18+ check, regional disclaimers, onboarding
        ├── chat.jsx      Main loop: message thread, SSE stream handler, composer
        │     ├── avatar.jsx        Emotion state visualiser (calm/listen/think/speak/care)
        │     ├── memory.jsx        USM file encryption/decryption modal
        │     ├── panels.jsx        Mood diary panel + sources/citations panel
        │     ├── nikko-data.jsx    Offline fallback: NIKKO_PATTERNS + canned responses
        │     └── agent-debug.jsx   Developer debug overlay (ADP-B/A/C trace viewer)
        │
        └── styles.css    Light/dark theme, animations, mobile breakpoints
```

### Compiled bundles

esbuild compiles entry-point JSX files into plain JS for GitHub Pages (no bundler at
runtime). Compiled files are committed alongside sources so GitHub Pages can serve them
directly.

| Source | Compiled output | Entry point? |
|--------|----------------|--------------|
| `chat.jsx` | `chat.js` | Yes — imports avatar, gate, memory, panels, nikko-data, agent-debug |
| `panels.jsx` | `panels.js` | Yes |
| `memory.jsx` | `memory.js` | Yes |
| `agent-debug.jsx` | `agent-debug.js` | Yes |
| `loading.js` | *(none)* | Handwritten vanilla JS — no JSX source, not compiled |
| `nikko.jsx` | *(bundled into chat.js)* | Module only |
| `avatar.jsx` | *(bundled into chat.js)* | Module only |
| `gate.jsx` | *(bundled into chat.js)* | Module only |
| `nikko-data.jsx` | *(bundled into chat.js)* | Module only |

**Rebuild command** (run from repo root, requires esbuild):

```bash
npx esbuild@0.25.3 web/chat.jsx        --bundle --outfile=web/chat.js        --loader:.jsx=jsx --external:react --external:react-dom
npx esbuild@0.25.3 web/panels.jsx      --bundle --outfile=web/panels.js      --loader:.jsx=jsx --external:react --external:react-dom
npx esbuild@0.25.3 web/memory.jsx      --bundle --outfile=web/memory.js      --loader:.jsx=jsx --external:react --external:react-dom
npx esbuild@0.25.3 web/agent-debug.jsx --bundle --outfile=web/agent-debug.js --loader:.jsx=jsx --external:react --external:react-dom
```

> **Bash sandbox warning (CLAUDE.md §5a):** The bash mount may serve a stale version
> of large JSX files. Before rebuilding, use Python to verify the source file tail is
> intact, then splice in the correct tail if truncated.

---

## Backend integration

The frontend talks to the Render backend at `https://nikko-companion.onrender.com`.
The full API contract is in `docs/integration/FRONTEND_INTEGRATION_SPEC.md`.

### Key endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `GET /health` | GET | Startup poll — frontend shows loading screen until 200 |
| `POST /api/message` | POST + SSE | Send user message, stream response chunks |
| `POST /api/memory/decrypt` | POST | Decrypt USM memory file (AES-GCM, client key) |
| `POST /api/memory/encrypt` | POST | Encrypt updated memory file before download |

### SSE chunk format

Each chunk from `/api/message` is a JSON object:

```json
{ "text": "...", "emotion": "listen", "done": false, "trace": null }
```

The final substantive chunk carries `"trace": { "adp_b": {...}, "adp_a": {...}, "adp_c": {...}, "elapsed": 0.0, "regen": false }` for the debug overlay.

### Offline fallback

When the backend is unreachable, `chat.jsx` falls through to `matchNikkoPattern()` in
`nikko-data.jsx`, which runs regex pattern matching against `NIKKO_PATTERNS` and returns
a canned response. This is intentionally minimal — it exists to prevent a blank screen,
not to provide real support.

---

## Component reference

### `Nikko.html` — App shell
The actual application entry point loaded by `index.html`. Loads React 18 via CDN,
imports compiled JS bundles, and mounts the root `<NikkoApp />` component.

### `index.html` — GitHub Pages redirect
Five-line file. Redirects the GitHub Pages root to `Nikko.html`. Required because
GitHub Pages serves from the repo root but the app shell is `Nikko.html`.

### `gate.jsx` — Consent gate
First screen shown to every user. Enforces: 18+ age check, Australia-only disclaimer,
English-only notice, non-diagnostic notice, session-scoped data notice. Refs SPEC-000,
SPEC-300.

### `chat.jsx` — Main loop (1600+ lines)
Owns the SSE stream handler, message history state, emotion prop derivation, memory
file round-trip, and composer. Dispatches to all sub-components. The `onMemoryLoaded`
handler calls `parseDiaryEntries(md)` immediately after `setMemName` — these two
functions are an inverse pair with `formatDiaryEntry()` in `panels.jsx` and must be
kept in sync.

### `avatar.jsx` — Emotion visualiser
Renders the NIKKO glyph and animated rays. State machine: `calm → listen → think →
speak → care`. Driven by the `emotion` field on incoming SSE chunks.

### `memory.jsx` — USM file handler
Handles the generate-memory and load-memory modals. All encryption is AES-GCM,
client-side only — the server never sees plaintext memory content. Refs SPEC-200,
SPEC-800, SPEC-850.

### `panels.jsx` — Mood diary + sources
Two side panels: mood diary (session-scoped React state, no `sessionStorage` per
SPEC-800) and source citations (APA7-formatted, driven by evidence payload). Mood
diary entries are serialised to the `## Mood Diary` section of the encrypted memory
file via `formatDiaryEntry()`.

### `nikko-data.jsx` — Offline fallback
Contains `NIKKO_PATTERNS` (regex array) and `NIKKO_SOURCES` (citation library).
In live operation, `NIKKO_SOURCES` is still used for the sources panel. Pattern
matching is only invoked when the backend SSE stream is empty or unreachable.

### `agent-debug.jsx` — Debug overlay
Shows real ADP-B / ADP-A / ADP-C adapter results from the live pipeline trace.
Published via `window.__nikkoAgentLog` (`NikkoAgentLog` pub/sub store). Falls back
to a keyword-classification trace when `liveData` is absent.

### `loading.js` — Loading screen
Handwritten vanilla JS (no JSX source). Polls `GET /health` on page load and shows
a staged loading animation until the Render backend returns 200. Refs
FRONTEND_INTEGRATION_SPEC §12.

### `loading.css` — Loading screen styles
Companion stylesheet for `loading.js`.

### `styles.css` — Main stylesheet
Light/dark theme (CSS variables), avatar animations, mobile breakpoints. Key
breakpoints: ≤600px (panels → bottom sheets), ≤480px (gate full-width, touch targets
≥44px).

### `eula.html`, `privacy.html` — Legal pages
Standalone HTML pages linked from within the app. Not compiled or processed.

---

## Safety features

All safety UI is hard-coded and cannot be suppressed by the backend or any agent output.

| Feature | Implementation |
|---------|---------------|
| Quick exit | Always-visible button; wipes session state and navigates to an external domain |
| Safety banner | Auto-shows on crisis keywords detected client-side; displays Lifeline 13 11 14, Beyond Blue, 13YARN, 000 |
| Non-diagnostic notice | Shown in gate and periodically in UI |
| Session-only data | No `localStorage` or `sessionStorage` for message history or mood diary (SPEC-800) |
| Memory encryption | AES-GCM client-side; server never receives plaintext (SPEC-850) |

---

## Mobile layout

| Breakpoint | Change |
|------------|--------|
| ≤600px | Side panels become bottom sheets (`height: 82vh`, `animation: sheet-up`) |
| ≤600px | `.tab-float` hidden; `.mobile-tabbar` fixed footer replaces it |
| ≤480px | Gate card full-width; modal padding reduced; mood chip/pip touch targets ≥44px; research preview pill hidden |

# Nikko — design notes

A safety-aligned, non-diagnostic wellbeing companion. Research preview, Australia only.
This file records the design decisions baked into the UI so future edits stay coherent.

---

## Voice & posture
- **Quiet, not clinical.** Copy is short, lowercase-leaning, never alarmist. No diagnosis language.
- **Opt-in by default.** Memory, mood diary, and reflection are all things the user actively enables — nothing is on by surprise.
- **Local-first.** Mood entries and memory live on the user's device. Surface this in microcopy ("Stays on your device").

## Type system
Loaded once via Google Fonts at the top of `styles.css`.

| Variable          | Family            | Used for                                          |
|-------------------|-------------------|---------------------------------------------------|
| `--font-display`  | Newsreader        | Page-level titles, gate headline                  |
| `--font-body`     | Geist             | UI body, buttons, labels                          |
| `--font-mono`     | Geist Mono        | Eyebrows, timestamps, pills, scale endpoints      |
| `--font-brand`    | Sniglet           | Wordmark "Nikko", emphasised display words        |
| `--font-chat`     | Belgrano          | Conversation bubbles (assistant + user)           |

Rules of thumb:
- Mono is reserved for metadata/uppercase eyebrows (10–11px, +0.06–0.08em tracking).
- Section labels inside the Mood Diary use sentence-case body, not all-caps mono — this came out of the de-crowding pass to reduce noise.
- Display weight is light (300) at large sizes; body weight is 400/500.

## Color palette
Defined as CSS custom properties at the top of `styles.css`. Both light and dark themes share the same token names; only the values change.

### Light (default)
| Token            | Hex        | Role                                       |
|------------------|------------|--------------------------------------------|
| `--bg`           | `#EAE7DF`  | Warm parchment app background              |
| `--bg-2`         | `#e1ddd2`  | Hover surfaces, secondary panels           |
| `--bg-3` / `--surface` | `#FFFFFF` | Cards, inputs, raised surfaces        |
| `--ink`          | `#1a1a1a`  | Primary text                               |
| `--ink-2`        | `#3a3a3a`  | Body text                                  |
| `--muted`        | `#5d5d5d`  | Secondary text, labels                     |
| `--faint`        | `#846a6a`  | Tertiary metadata (mauve-leaning)          |
| `--line`         | `#d4cfc1`  | Borders                                    |
| `--line-soft`    | `#ddd8c9`  | Hairline dividers                          |
| `--accent`       | `#279af1`  | Primary blue (memory, links, focus)        |
| `--accent-2`     | `#846a6a`  | Mauve — selection, mood-diary chrome       |
| `--accent-soft`  | `#d8eaff`  | Tinted backgrounds for accent surfaces     |
| `--sun`          | `#CE844C`  | Nikko avatar / brand sun                   |
| `--sun-soft`     | `#f1d9c2`  | Tinted sun glow                            |
| `--crisis`       | `#b85450`  | Crisis affordance only — never decorative  |

### Dark
A deep navy reskin (`--bg: #1A2B5F`) with teal accents (`--accent: #42858c`, `--accent-2: #397367`). The sun stays warm to keep the avatar recognisable.

### Mood color scale
1 (low) → 10 (good), warm-red through teal-green, used on the rating pips and as the dot in past-entry rows. Hand-tuned in `styles.css`; do not hue-shift without re-checking contrast against `#fff` text.

## Spacing, radii, motion
- Radii: `--r-sm` 8 / `--r-md` 12 / `--r-lg` 18 / `--r-xl` 26.
- Shadows: `--shadow-soft` for raised inputs, `--shadow-card` for modal-grade surfaces.
- Motion: `--t-fast` 160ms / `--t-med` 280ms / `--t-slow` 520ms — all share the same easing curve.

## Mood Diary — layout principles (revised)
The diary lives in the left panel. Earlier versions stacked five long sections vertically; this read as crowded. Current rules:

1. **One core action per screen.** The mood rating row + a one-line note are the only always-visible inputs. Everything else is opt-in.
2. **Progressive disclosure.** Emotions and triggers sit inside a single `<details>` block ("Emotions & context") so users without anything to add are never confronted with 14 chips.
3. **Curate, then expand.** Primary chip lists show the 6–8 most common options; the long tail is behind a `+N more` ghost chip.
4. **Reflection is opt-in.** The 10-minute pomodoro + journal textarea is hidden behind a single dashed "+ Add a 10-minute reflection" button. Reopens automatically when revisiting a day that already has a reflection saved.
5. **Past entries are quiet.** One row per day — colored dot, date, single-line summary, score. No nested cards, no per-row borders.
6. **Save / Clear day** sit at the end of the active section, before past entries, so they don't compete with the day list.

## Avatar
The Nikko avatar is a simple sun: warm `--sun` disc, soft `--sun-soft` halo. Drawn in CSS/SVG, never replaced with imagery.

## Crisis affordances
- Crisis colors (`--crisis`, `--crisis-soft`) are reserved for safety messaging and the Quick Exit button.
- Quick Exit lives top-right and is one tap away at all times.

## Agent transparency

Nikko is a multi-agent pipeline (see `agents/README.md` for the full agent map). Two surfaces show this to the user:

### Public ribbon — under every assistant message
A small caption appears under each assistant reply:

> ⌖ **5 AGENTS COORDINATED THIS REPLY** · sources queried: Beyond Blue, headspace, Lifeline

Rules:
- **Agent count is public; agent names are not.** The ribbon never names individual agents (`signal_agent`, `evaluator`, etc).
- **Evidence sources are fully public.** Whenever the Evidence retrieval phase runs (Guidance mode), the actual sources queried are listed by name — this is non-negotiable transparency.
- The ribbon is always visible, never collapsed. It uses mono type, low contrast, accent-tinted left border so it sits adjacent to the bubble without competing with it.

### Hidden debug — gesture-protected
Power-user / researcher view. Reveals the full SPEC-700 pipeline including every agent name, latency, and per-phase payload.

**To open:** click twice on the top-left Nikko sun, then press and hold for 3 seconds. A faint progress ring expands during the hold; releasing early cancels.

**What it shows:**
1. Turn picker — every turn in this session.
2. Mode badge (COMFORT / GUIDANCE / CRISIS), distress level, model confidence, total latency.
3. Pipeline list — each phase as a row with: ordinal, agent label, agent module, LLM badge (if applicable), `public` badge (only on Evidence retrieval), summary, duration.
4. **Read full trace** button → expands the panel and dumps per-phase detail JSON (signal payload, router rationale, evidence sources with tier + ref, evaluator red-line counts, verification checks).

The debug overlay is for inspection only — it does not change behaviour. Trace data lives in memory on the device and is cleared on refresh.

## Mobile layout (≤600px)

At ≤600px (typical phone portrait), the side panel cards switch to bottom sheets:

- `.chat.floating .left-float` and `.right-float` panels become `position: fixed; bottom: 0; left/right: 0; height: 82vh`, sliding up via `@keyframes sheet-up`.
- `.tab-float` side buttons are hidden (`display: none`). Replaced by `.mobile-tabbar` fixed at the footer — two tabs (Mood, Sources) that toggle their respective sheets.
- `.sheet-backdrop` — full-screen overlay (`z-index: 45`) that closes both panels on tap.
- Opening one panel auto-closes the other: click handlers call `setLeftTab(null)` / `setRightTab(null)` on open.
- Composer lifts above the tab bar via `padding-bottom` on `.chat-composer`.

At ≤480px additional fixes apply: gate card full-width, modals drop horizontal padding, mood chip and pip touch targets enlarged to 44px minimum, research preview pill hidden.

**Design rule:** the bottom sheet opening animation (`sheet-up`) uses `--t-med` (280ms) easing — consistent with all other modal transitions in the system. Do not make it faster; on low-end phones it looks like a flash.

## Mood diary round-trip

The diary stores data in two layers:

1. **Session layer** — React state (`moodEntries` in `chat.jsx`). Cleared on refresh (SPEC-800). Never touches sessionStorage.
2. **Durable layer** — `## Mood Diary` section of the encrypted memory file. Written by `MoodDiaryPanel.save()` via `formatDiaryEntry()` in `panels.jsx`. Read back by `parseDiaryEntries()` in `chat.jsx` inside `onMemoryLoaded`.

Serialisation format (one block per entry, blank-line separated):
```
YYYY-MM-DD | mood: N | emotions: a, b | triggers: c
note: free text
```

If either function is changed, change both — they are an inverse pair and will silently break the round-trip if they diverge.

## File map (updated)
- `Nikko.html` — entry point; loads scripts in dependency order.
- `styles.css` — all tokens + component CSS.
- `gate.jsx` — opening attestation screen.
- `avatar.jsx` — sun avatar component.
- `nikko-data.jsx` — seed data, sample entries, reply patterns.
- `memory.jsx` — personal memory drawer.
- `panels.jsx` — Sources panel (right), **Mood Diary panel (left)**, Tutorial overlay.
- `agent-debug.jsx` — **NEW.** Agent ribbon, gesture hook, debug overlay, trace store.
- `chat.jsx` — conversation thread; wires the ribbon under assistant messages and the gesture host on the top-left sun.
- `nikko.jsx` — root composition.

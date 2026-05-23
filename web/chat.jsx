// chat.jsx — Conversation thread, composer, side panels (sources/mood),
// USM memory controls, quick exit, first-time tutorial.

const { useState, useEffect, useRef, useCallback } = React;

// ── AI Limitation Disclaimer (G-UI-01) ────────────────────────────
// [REQ-300-164] A persistent, non-intrusive disclaimer MUST inform users that
// Nikko is AI and may produce inaccurate information. Closes open gap G-UI-01.
// Rendered below the composer on every turn; cannot be dismissed (by design).
function AiDisclaimer() {
  return (
    <div className="ai-disclaimer" role="note" aria-label="AI limitation notice">
      <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5"
           strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <circle cx="6" cy="6" r="5" />
        <path d="M6 5v3" />
        <circle cx="6" cy="3.5" r="0.4" fill="currentColor" stroke="none" />
      </svg>
      Nikko is AI and can make mistakes. Do not act on anything without further checking.
    </div>
  );
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

// ── Mood diary section parser ──────────────────────────────────────
// Inverse of formatDiaryEntry() in panels.jsx. Reads the ## Mood Diary
// section of a memory Markdown file and reconstructs the moodEntries
// dict so the diary panel is pre-populated when a file is (re-)loaded.
//
// Expected per-entry format (one blank line between entries):
//   YYYY-MM-DD | mood: N | emotions: x, y | triggers: a, b
//   note: optional free text
function parseDiaryEntries(md) {
  if (!md) return {};
  // Extract ## Mood Diary section body (mirrors parseMemSection logic).
  const re = /^##\s*Mood Diary\s*$/m;
  const match = md.match(re);
  if (!match) return {};
  const start = match.index + match[0].length;
  const next  = md.indexOf('\n##', start);
  const body  = (next === -1 ? md.slice(start) : md.slice(start, next))
    .replace(/<!--[\s\S]*?-->/g, '')  // strip placeholder comments
    .trim();
  if (!body) return {};

  const result = {};
  for (const block of body.split(/\n\n+/)) {
    const lines = block.trim().split('\n');
    if (!lines[0]) continue;
    // First line: ISO-date | key: value | key: value ...
    const parts = lines[0].split(' | ');
    const iso = parts[0]?.trim();
    if (!iso || !/^\d{4}-\d{2}-\d{2}$/.test(iso)) continue;

    const entry = { mood: 0, emotions: [], triggers: [], note: '', journal: '' };
    for (let i = 1; i < parts.length; i++) {
      const p = parts[i].trim();
      if (p.startsWith('mood:')) {
        const n = parseInt(p.slice(5).trim(), 10);
        if (!isNaN(n) && n >= 1 && n <= 10) entry.mood = n;
      } else if (p.startsWith('emotions:')) {
        entry.emotions = p.slice(9).split(',').map(s => s.trim()).filter(Boolean);
      } else if (p.startsWith('triggers:')) {
        entry.triggers = p.slice(9).split(',').map(s => s.trim()).filter(Boolean);
      }
    }
    // Optional second line: note: ...
    if (lines[1]?.startsWith('note:')) entry.note = lines[1].slice(5).trim();

    result[iso] = entry;
  }
  return result;
}

// ── Inline rendering: bold + cite superscripts ─────────────────────
function renderInline(text, sourceOrder, onCiteClick) {
  const parts = [];
  const re = /(\*\*[^*]+\*\*)|(\[\^s_[a-z_]+\])/g;
  let last = 0, m, i = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push({ kind: 'text', value: text.slice(last, m.index), key: i++ });
    if (m[1]) parts.push({ kind: 'bold', value: m[1].slice(2, -2), key: i++ });
    else if (m[2]) {
      const key = m[2].slice(2, -1);
      if (!(key in sourceOrder)) sourceOrder[key] = Object.keys(sourceOrder).length + 1;
      parts.push({ kind: 'cite', sourceKey: key, num: sourceOrder[key], key: i++ });
    }
    last = re.lastIndex;
  }
  if (last < text.length) parts.push({ kind: 'text', value: text.slice(last), key: i++ });
  return parts.map(p => {
    if (p.kind === 'text') return <React.Fragment key={p.key}>{p.value}</React.Fragment>;
    if (p.kind === 'bold') return <strong key={p.key}>{p.value}</strong>;
    if (p.kind === 'cite') return (
      <button key={p.key} className="cite-sup"
              onClick={() => onCiteClick(p.sourceKey)}
              title={NIKKO_SOURCES[p.sourceKey]?.title || 'Source'}>
        {p.num}
      </button>
    );
    return null;
  });
}

function MessageBody({ text, sourceOrder, onCiteClick, streaming }) {
  const paragraphs = text.split(/\n{2,}/);
  return (
    <>
      {paragraphs.map((p, pi) => (
        <p key={pi}>
          {renderInline(p, sourceOrder, onCiteClick)}
          {streaming && pi === paragraphs.length - 1 && <span className="caret" aria-hidden="true" />}
        </p>
      ))}
    </>
  );
}

// ── Safety banner ──────────────────────────────────────────────────
// REQ-300-RS1: baseline four resources always visible.
// REQ-300-RS2: demographic-specific resources in "More tailored support" expandable.
// REQ-300-RS3: expandable MUST NOT infer demographic identity — shown to all users equally.
function SafetyBanner({ onDismiss }) {
  const [expanded, setExpanded] = React.useState(false);
  return (
    <div className="safety-banner" role="status">
      <span className="icon" aria-hidden="true">
        <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
          <path d="M6 1.5C4 4 3 5.5 3 7a3 3 0 0 0 6 0c0-1.5-1-3-3-5.5z" />
        </svg>
      </span>
      <div className="body">
        <strong>If you'd like to talk to a person right now</strong>
        {/* REQ-300-RS1 — mandatory baseline */}
        <p>
          Lifeline <a href="tel:131114">13 11 14</a> ·{' '}
          Beyond Blue <a href="tel:1300224636">1300 22 4636</a> ·{' '}
          Suicide Call Back <a href="tel:1300659467">1300 659 467</a> ·{' '}
          Emergency: <a href="tel:000">000</a>
        </p>
        {/* REQ-300-RS2 — expandable demographic-specific resources */}
        {expanded && (
          <p className="safety-banner-extra">
            QLife (LGBTIQ+) <a href="tel:1800184527">1800 184 527</a> ·{' '}
            13YARN (First Nations) <a href="tel:139276">13 92 76</a> ·{' '}
            Kids Helpline <a href="tel:1800551800">1800 55 1800</a> ·{' '}
            1800RESPECT <a href="tel:1800737732">1800 737 732</a> ·{' '}
            MensLine <a href="tel:1300789978">1300 78 99 78</a>
          </p>
        )}
        <button
          className="safety-banner-expand"
          onClick={() => setExpanded(e => !e)}
          aria-expanded={expanded}
        >
          {expanded ? 'Show less' : 'More tailored support'}
        </button>
      </div>
      <button className="dismiss" onClick={onDismiss} aria-label="Dismiss">
        <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
          <path d="m3 3 6 6M9 3l-6 6" />
        </svg>
      </button>
    </div>
  );
}

// ── Character limit helper ────────────────────────────────────────
// Derives the composer character limit from loaded memory content.
// Default: 1000. Extended to 1500 if memory signals the user tends to
// write at length (e.g. "I tend to ramble", "I'm quite verbose").
//
// WHY HERE not in Composer: the limit is derived from memContentRef,
// which lives in Chat. Composer is a stateless child — it just receives
// maxLength as a prop and enforces it. This keeps signal derivation
// close to the data it reads.
const CHAR_LIMIT_DEFAULT  = 1000;
const CHAR_LIMIT_EXTENDED = 1500;

// Keywords in memory that indicate the user writes at length.
// Lowercase match against the full memory text.
const _VERBOSE_SIGNALS = [
  'ramble', 'rambles', 'tend to write', 'write a lot', 'write quite a lot',
  'verbose', 'verbosity', 'lengthy', 'long messages', 'long message',
  'write long', 'quite a lot to say',
];

function deriveCharLimit(memContent) {
  if (!memContent) return CHAR_LIMIT_DEFAULT;
  const lower = memContent.toLowerCase();
  const isVerbose = _VERBOSE_SIGNALS.some(sig => lower.includes(sig));
  return isVerbose ? CHAR_LIMIT_EXTENDED : CHAR_LIMIT_DEFAULT;
}

// ── Composer ──────────────────────────────────────────────────────
function Composer({ onSend, disabled, maxLength }) {
  const limit = maxLength || CHAR_LIMIT_DEFAULT;
  const [val, setVal] = useState('');
  const ref = useRef(null);
  const autosize = useCallback(() => {
    const el = ref.current; if (!el) return;
    el.style.height = 'auto';
    el.style.height = Math.min(160, el.scrollHeight) + 'px';
  }, []);
  useEffect(() => { autosize(); }, [val, autosize]);
  const submit = () => {
    const t = val.trim();
    if (!t || disabled || val.length > limit) return;
    onSend(t); setVal('');
  };

  // Counter state: hidden below 60% of limit, warning from 80%, over at 100%.
  const remaining = limit - val.length;
  const showCounter = val.length >= limit * 0.6;
  const counterClass = val.length > limit
    ? 'composer-count over'
    : val.length >= limit * 0.8
      ? 'composer-count warn'
      : 'composer-count';

  return (
    <div>
      <div
        className="composer"
        onClick={(e) => {
          // Forward clicks on the composer padding/background to the textarea
          // so the user can tap anywhere in the row to start typing.
          // Exclude the send button so clicking it doesn't steal focus mid-submit.
          if (e.target.closest('.send')) return;
          ref.current?.focus();
        }}
      >
        <textarea
          ref={ref}
          value={val}
          onChange={(e) => {
            // Allow typing past limit so the user can see the overage in red
            // and edit back — hard-blocking input mid-sentence is disorienting.
            // Send is disabled while over limit.
            setVal(e.target.value);
          }}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(); } }}
          placeholder="Take your time…"
          rows={1}
          aria-label="Message Nikko"
        />
        <button className="send" onClick={submit} disabled={!val.trim() || disabled || val.length > limit} aria-label="Send message">
          <svg viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
            <path d="M2 7h10" /><path d="m8 3 4 4-4 4" />
          </svg>
        </button>
      </div>
      <div className="composer-foot">
        <span><span className="kbd">Enter</span> to send · <span className="kbd">Shift</span>+<span className="kbd">Enter</span> for newline · type <span className="kbd">/help</span> for the tutorial</span>
        <span className="composer-foot-right">
          {showCounter && (
            <span className={counterClass} aria-live="polite" aria-label={`${remaining} characters remaining`}>
              {remaining < 0 ? `${Math.abs(remaining)} over` : remaining}
            </span>
          )}
          <span>Cleared on refresh</span>
        </span>
      </div>
    </div>
  );
}

// ── Memory notification banner ────────────────────────────────────
// Two variants:
//   'loaded' — shown for 7s after the user loads a memory file.
//              Confirms Nikko now has the context; auto-dismisses.
//   'hint'   — shown after the 3rd user message when no memory is
//              loaded. Surfaces the option without being intrusive.
//              Never shown more than once per session.
function MemBanner({ type, onDismiss, onOpenLoad }) {
  return (
    <div className="mem-banner" role="status" aria-live="polite">
      <span className="mem-banner-icon" aria-hidden="true">
        {type === 'loaded' ? (
          // Lock icon — memory is secure and active
          <svg viewBox="0 0 12 12" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <rect x="2" y="5.5" width="8" height="5.5" rx="1" />
            <path d="M4 5.5V4a2 2 0 0 1 4 0v1.5" />
            <path d="M6 7.5v1.5" />
          </svg>
        ) : (
          // Info icon — gentle nudge, not an alert
          <svg viewBox="0 0 12 12" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="6" cy="6" r="4.5" />
            <path d="M6 5v3" />
            <circle cx="6" cy="3.5" r="0.4" fill="currentColor" stroke="none" />
          </svg>
        )}
      </span>
      <div className="mem-banner-body">
        {type === 'loaded'
          ? "Memory loaded — I'll keep your context in mind."
          : 'Give Nikko a memory file for a more personal experience.'}
      </div>
      {type === 'hint' && (
        <button className="mem-banner-action" onClick={onOpenLoad}>Set up</button>
      )}
      <button className="dismiss" onClick={onDismiss} aria-label="Dismiss banner">
        <svg viewBox="0 0 10 10" width="10" height="10" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
          <path d="m2.5 2.5 5 5M7.5 2.5l-5 5" />
        </svg>
      </button>
    </div>
  );
}

// ── Technique check-in banner (SPEC-850 §9 — response-side prompt) ──
// Shown as a popup in the composer area when Nikko's response recommends a
// named technique. Asks the user if they want to track it in their memory file.
// Primary trigger path — does not require the user to type specific phrases.
// REQ-850-011: user must explicitly Accept before anything is written.
// REQ-850-092: visually distinct from both SafetyBanner and MemoryProposalCard.
// hasMemory: true when an encrypted file is already loaded. Controls whether
// "Add to memory" patches the existing file (hasMemory=true) or opens the
// generate modal to create one with the entry pre-populated (hasMemory=false).
function TechniqueCheckInBanner({ technique, onAdd, onDismiss, hasMemory }) {
  return (
    <div className="technique-checkin-banner" role="status" aria-live="polite">
      <span className="technique-checkin-icon" aria-hidden="true">
        <svg viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5"
             strokeLinecap="round" strokeLinejoin="round">
          <rect x="2.5" y="6" width="9" height="6.5" rx="1.2" />
          <path d="M4.5 6V4a2.5 2.5 0 0 1 5 0v2" />
          <path d="M7 8.5v2" />
        </svg>
      </span>
      <div className="technique-checkin-body">
        <strong>Worth remembering?</strong>
        {hasMemory
          ? <p>If {technique} helps, I can add it to your memory file.</p>
          : <p>If {technique} helps, you can save it to a memory file. I'll create one with it already included.</p>
        }
      </div>
      <div className="technique-checkin-actions">
        <button className="technique-checkin-yes" onClick={onAdd}
                aria-label={hasMemory ? `Add ${technique} to memory file` : `Create memory file with ${technique}`}>
          {hasMemory ? 'Add to memory' : 'Create memory file'}
        </button>
        <button className="technique-checkin-no" onClick={onDismiss}
                aria-label="Dismiss suggestion">
          Not now
        </button>
      </div>
    </div>
  );
}

// ── Memory proposal card (SPEC-850 §9, step 2 — Proposal) ─────────
// Shown in the composer area when the backend detects an intervention affirmation.
// The user must explicitly Accept or Decline — nothing is written otherwise.
// REQ-850-011: two-step proposal + confirmation. REQ-850-092: visually distinct.
function MemoryProposalCard({ proposal, onAccept, onDecline }) {
  return (
    <div className="mem-proposal-card" role="complementary" aria-label="Memory suggestion">
      <div className="mem-proposal-icon" aria-hidden="true">
        <svg viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <rect x="2.5" y="6" width="9" height="6.5" rx="1.2" />
          <path d="M4.5 6V4a2.5 2.5 0 0 1 5 0v2" />
          <path d="M7 8.5v2" />
        </svg>
      </div>
      <div className="mem-proposal-body">
        <div className="mem-proposal-label">Add to memory?</div>
        <div className="mem-proposal-entry">
          <span className="mem-proposal-section">{proposal.section}</span>
          {' — '}
          {proposal.entry}
        </div>
      </div>
      <div className="mem-proposal-actions">
        <button className="mem-proposal-accept" onClick={onAccept} aria-label="Accept and add to memory">
          Accept
        </button>
        <button className="mem-proposal-decline" onClick={onDecline} aria-label="Decline memory suggestion">
          Decline
        </button>
      </div>
    </div>
  );
}

// ── Quick exit ─────────────────────────────────────────────────────
function quickExit() {
  try {
    sessionStorage.clear();
    // Wipe non-essential state but keep theme + tutorial-seen so the safety
    // pivot away is fast and silent.
    const keep = ['nikko.theme', 'nikko.tutorial.seen'];
    const all = Object.keys(localStorage);
    all.forEach(k => { if (!keep.includes(k)) localStorage.removeItem(k); });
  } catch (e) {}
  // Replace history so Back doesn't return to the conversation.
  try { window.location.replace('https://www.bom.gov.au/'); }
  catch (e) { window.location.href = 'https://www.bom.gov.au/'; }
}

// ── Backend URL (REQ-FIS-001) ─────────────────────────────────────
const BACKEND_URL = 'https://nikko-companion.onrender.com';

// ── ThinkingBubble ────────────────────────────────────────────────
// Staged thinking indicator for the pipeline wait (30-120s).
// Phases:
//   0–6s   — "Reading your message…"
//   6–14s  — "Checking in on what you shared…"
//   14–24s — "Putting together a response for you…"
//   24s+   — Cycles through affirmations every 5s
//
// coldStart prop: set to true when 12s have elapsed since the fetch fired
// but no message_start SSE event has been received yet, indicating the Render
// backend and/or HF Space is cold-starting (~60–90s on first load).
// The notice clears automatically once the stream begins.
const THINK_STAGES = [
  { at: 0,  label: 'Reading your message…' },
  { at: 6,  label: 'Checking in on what you shared…' },
  { at: 14, label: 'Putting together a response for you…' },
];
const AFFIRMATIONS = [
  'Making the best response. Because you matter.',
  'Taking a moment to get this right…',
  'Finding the right words for you…',
  'Still here — good things take a little time.',
  'Reading between the lines…',
  'You deserve a thoughtful reply.',
];

// ── MoodCheckInPopup ──────────────────────────────────────────────────────────
// [REQ-FIS-MC1 through MC8] Inline mood check-in card rendered in the chat
// thread after the welcome-back message when a memory file is loaded.
//
// Triggered once per session when an existing encrypted file is loaded
// (sessionKey present). Skipped for newly generated files (isNew=true path).
//
// On Log:
//   - Updates moodEntries state (in-memory diary, session-scoped per SPEC-800)
//   - Queues a pendingEntries write-back for the user to save to disk
// On Skip: dismisses without writing anything.
//
// [REQ-FIS-MC4] Emotion chips are advisory — multi-select, never required.
// [REQ-FIS-MC5] Rating is 1–10 inclusive.
// [REQ-FIS-MC7] The popup renders without requiring user login or data upload.
// [REQ-FIS-MC8] State guard (moodCheckInShownRef) prevents re-triggering.

// Must stay in sync with EMOTION_OPTIONS in panels.jsx (same ordering, same labels).
// Showing all emotions here — the popup is compact enough to show the full set
// without a "+N more" expander (10 chips is the natural cutoff for this layout).
const CHECKIN_EMOTIONS = ['calm','tired','anxious','low','sad','hopeful','content','overwhelmed','numb','irritable'];

function MoodCheckInPopup({ onLog, onSkip }) {
  const [rating, setRating] = React.useState(null);
  const [selected, setSelected] = React.useState([]);

  const toggleEmotion = (e) => {
    setSelected(prev => prev.includes(e) ? prev.filter(x => x !== e) : [...prev, e]);
  };

  const handleLog = () => {
    if (!rating) return;   // rating required — button is disabled below when null
    onLog({ rating, emotions: selected });
  };

  return (
    <div className="mood-checkin-popup" role="form" aria-label="Quick mood check-in">
      <div className="mood-checkin-header">
        <span className="mood-checkin-title">Quick check-in</span>
        <span className="mood-checkin-sub">How are you feeling right now?</span>
      </div>

      {/* 1–10 numeric rating — data-r attr enables the same MOOD_COLORS
          gradient scale used by the diary panel pips (styles.css).
          This keeps colour language consistent across both surfaces. */}
      <div className="mood-checkin-rating" aria-label="Mood rating 1 to 10">
        {[1,2,3,4,5,6,7,8,9,10].map(n => (
          <button
            key={n}
            data-r={n}
            className={'mood-checkin-num' + (rating === n ? ' active' : '')}
            onClick={() => setRating(n)}
            aria-pressed={rating === n}
            aria-label={`${n} out of 10`}
          >{n}</button>
        ))}
      </div>
      <div className="mood-checkin-scale-hint">
        <span>1 = very low</span><span>10 = great</span>
      </div>

      {/* Emotion chips — multi-select, optional */}
      <div className="mood-checkin-chips" aria-label="Emotion chips, optional">
        {CHECKIN_EMOTIONS.map(e => (
          <button
            key={e}
            className={'mood-chip' + (selected.includes(e) ? ' active' : '')}
            onClick={() => toggleEmotion(e)}
            aria-pressed={selected.includes(e)}
          >{e}</button>
        ))}
      </div>

      {/* Actions */}
      <div className="mood-checkin-actions">
        <button className="mood-checkin-skip" onClick={onSkip}>Skip</button>
        <button
          className="mood-checkin-log"
          onClick={handleLog}
          disabled={!rating}
          aria-disabled={!rating}
        >Log mood</button>
      </div>
    </div>
  );
}

function ThinkingBubble({ coldStart = false }) {
  const [elapsed, setElapsed] = React.useState(0);
  const [affIdx, setAffIdx]   = React.useState(0);

  useEffect(() => {
    const start = Date.now();
    const tick = setInterval(() => {
      const s = Math.floor((Date.now() - start) / 1000);
      setElapsed(s);
      // Advance affirmation every 5s once we're in that phase.
      if (s >= 24 && s % 5 === 0) {
        setAffIdx(i => (i + 1) % AFFIRMATIONS.length);
      }
    }, 1000);
    return () => clearInterval(tick);
  }, []);

  // Determine label: find the last stage whose `at` threshold we've passed.
  let label;
  if (elapsed < 24) {
    label = THINK_STAGES.reduce((acc, s) => elapsed >= s.at ? s.label : acc, THINK_STAGES[0].label);
  } else {
    label = AFFIRMATIONS[affIdx];
  }

  return (
    <div className={'bubble thinking-bubble' + (coldStart ? ' cold-start-active' : '')}
         aria-label="Nikko is thinking" role="status">
      <div className="t-dots-row">
        <span className="t-dot" />
        <span className="t-dot" />
        <span className="t-dot" />
      </div>
      <p className="t-label">{label}</p>

      {/* Cold-start notice: only visible when the backend hasn't responded
          within 12s — signals server is waking up from sleep (Render/HF Space
          cold-start). Disappears the moment the SSE stream begins. */}
      {coldStart && (
        <>
          <div className="cold-start-notice" aria-live="polite">
            {/* Clock icon */}
            <svg viewBox="0 0 12 12" fill="none" stroke="currentColor"
                 strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"
                 aria-hidden="true">
              <circle cx="6" cy="6" r="5" />
              <path d="M6 3.5V6l1.5 1.5" />
            </svg>
            <span className="cold-start-text">
              Server is waking up — first load takes ~60–90 s
            </span>
            <span className="cold-start-elapsed" aria-label={elapsed + ' seconds elapsed'}>
              {elapsed}s
            </span>
          </div>
          {/* Indeterminate shimmer bar — visual cue that something is happening */}
          <div className="cold-start-bar" aria-hidden="true">
            <div className="cold-start-bar-fill" />
          </div>
        </>
      )}
    </div>
  );
}

// ── Chat root ─────────────────────────────────────────────────────
function Chat({ theme, onToggleTheme }) {
  const [messages, setMessages] = useState([
    { id: 'open', role: 'assistant', text: NIKKO_OPENING.text, emotion: NIKKO_OPENING.emotion, streaming: false }
  ]);
  const [streaming, setStreaming] = useState(false);
  // isColdStart: true when 12s pass after a fetch fires with no SSE response
  // yet (backend/HF Space is cold-starting). Cleared once message_start arrives.
  const [isColdStart, setIsColdStart] = useState(false);
  // Ref holds the cold-start detection timer so it can be cancelled from any
  // branch of streamReply (success, empty-stream error, or catch fallback).
  const coldStartTimerRef = useRef(null);
  const [currentEmotion, setCurrentEmotion] = useState('calm');
  const [safetyVisible, setSafetyVisible] = useState(false);
  const [activeCite, setActiveCite] = useState(null);
  const [leftTab, setLeftTab] = useState(null);    // 'mood' | null
  const [rightTab, setRightTab] = useState(null);  // 'sources' | null
  // dynamicSources: the SourceItem list attached to whichever message's badge
  // was last clicked. Passed to SourcesPanel so it renders real retrieved URLs
  // instead of (or in addition to) the static NIKKO_SOURCES dict.
  const [dynamicSources, setDynamicSources] = useState([]);
  // Tracks the sources from the most recent GUIDANCE response so the Sources
  // tab button can surface them even without clicking a per-message badge.
  const lastResponseSourcesRef = useRef([]);
  const sourceOrderRef = useRef({});
  const [, forceRerender] = useState(0);
  const threadRef = useRef(null);

  // Stable session ID for this Gate entry (REQ-FIS-SM1).
  // Generated once on mount; passed to every /api/message call.
  const contextID = React.useMemo(() => {
    const bytes = crypto.getRandomValues(new Uint8Array(6));
    const hex = Array.from(bytes).map(b => b.toString(16).padStart(2, '0')).join('');
    return 'nikko-' + Date.now() + '-' + hex;
  }, []);

  // Tutorial — first time only
  const [tutorialOpen, setTutorialOpen] = useState(() => {
    try { return localStorage.getItem('nikko.tutorial.seen') !== '1'; } catch (e) { return true; }
  });

  // Hidden debug surface (gesture-protected)
  const [debugOpen, setDebugOpen] = useState(false);
  const debugGesture = useDebugGesture(() => setDebugOpen(true));
  const closeTutorial = () => {
    try { localStorage.setItem('nikko.tutorial.seen', '1'); } catch (e) {}
    setTutorialOpen(false);
  };

  // USM memory state — all session-scoped only (SPEC-800 zero-retention).
  // Nothing here persists across page refreshes; the indicator resets to false
  // on reload so it accurately reflects whether content is actually loaded.
  const [memOpen, setMemOpen] = useState(false);   // generate modal
  const [loadOpen, setLoadOpen] = useState(false); // load modal
  const [memLoaded, setMemLoaded] = useState(false);
  // memName = the filename shown in the pill. memUserName = name from ## Name section.
  const [memName, setMemName] = useState('');
  const [memUserName, setMemUserName] = useState('');  // parsed from ## Name section
  // [CONCEPT] useRef holds the decrypted memory content across renders without
  // triggering a re-render on change.  We don't need the component to re-render
  // when content changes — we only need it available at send time.
  const memContentRef = useRef(null);
  // sessionKeyRef holds {key: CryptoKey, salt: Uint8Array} returned by
  // decryptMemoryKeepKey() so we can re-encrypt without re-asking for the password.
  // REQ-850-033: key lives only in JS heap for the tab lifetime; never persisted.
  const sessionKeyRef = useRef(null);
  const [memPop, setMemPop] = useState(false);     // popover
  // memContentVersion increments whenever memContentRef is rewritten via
  // onMemoryRewrite, forcing Chat to re-render so MoodDiaryPanel receives
  // the updated content (refs don't trigger re-renders by themselves).
  const [memContentVersion, setMemContentVersion] = useState(0);

  // Pending write-back entries — approved by user, not yet saved/encrypted.
  // Each entry: { section: string, entry: string, ts: number (Date.now()) }.
  // REQ-850-093: session-end warning fires when this array is non-empty.
  const [pendingEntries, setPendingEntries] = useState([]);

  // Bootstrap entry: a technique the user accepted for memory BEFORE any file
  // was loaded. Stored here so it can be passed to MemoryGenerateModal as
  // initialEntries and baked into the file on download, then cleared.
  const [pendingBootstrapEntry, setPendingBootstrapEntry] = useState(null);

  // Technique check-in banner — shown when Nikko's response recommends a named
  // technique. Now fires regardless of whether a file is loaded (bootstrap path).
  // Shape: { technique: string, section: string, entry: string } | null.
  // "Add to memory" either queues a pendingEntry (file loaded) or opens the
  // generate modal with the entry pre-populated (no file loaded).
  // "Not now" clears it with no side effects.
  const [techniqueCheckIn, setTechniqueCheckIn] = useState(null);

  // Memory notification banner — two variants: 'loaded' (7s auto-dismiss) and
  // 'hint' (persists until dismissed; shown once per session after 3 user msgs).
  const [memBanner, setMemBanner] = useState(null);   // null | 'loaded' | 'hint'
  const memBannerAutoRef = useRef(null);               // auto-dismiss timer for 'loaded'
  const hintShownRef = useRef(false);                  // true once hint has been shown
  // [REQ-FIS-MC8] Mood check-in popup: shown once per session after a non-new
  // memory file load (encrypted file loaded → sessionKey present). The ref gates
  // the trigger so it fires at most once even if onMemoryLoaded is called twice.
  const moodCheckInShownRef = useRef(false);
  // { wbId: string } when active — wbId is the welcome-back message id to render
  // the popup after. null when dismissed or not yet triggered.
  const [moodCheckIn, setMoodCheckIn] = useState(null);

  // Close memory popover on outside click
  useEffect(() => {
    if (!memPop) return;
    const onDoc = (e) => {
      if (!e.target.closest || !e.target.closest('.mem-pop-host')) setMemPop(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [memPop]);

  // scrollToBottom must be declared BEFORE any hook that lists it as a dep,
  // otherwise the const TDZ throws a ReferenceError on first render.
  const scrollToBottom = useCallback(() => {
    const el = threadRef.current; if (!el) return;
    requestAnimationFrame(() => { el.scrollTop = el.scrollHeight; });
  }, []);

  // Auto-scroll whenever the message list grows (new user or assistant message).
  // scrollToBottom() uses requestAnimationFrame, which fires before React commits
  // new DOM nodes in concurrent mode — so we add a small timeout here to let
  // React flush the render first. 50ms is imperceptible but reliable.
  useEffect(() => {
    setTimeout(scrollToBottom, 50);
  }, [messages.length, scrollToBottom]);

  // Auto-scroll when in-thread UI elements appear (banners, popups, proposals).
  // Each of these inserts DOM content above the composer and pushes the viewport
  // down — without a scroll trigger the bottom of the thread goes hidden.
  // moodCheckIn: mood check-in popup in thread after memory load
  // safetyVisible: crisis safety banner expands above composer
  // memBanner: loaded/hint banner inserts above thread
  // techniqueCheckIn: technique proposal card appended to thread
  // pendingEntries.length: memory proposal cards appended to thread
  useEffect(() => { setTimeout(scrollToBottom, 80); }, [moodCheckIn, scrollToBottom]);
  useEffect(() => { setTimeout(scrollToBottom, 80); }, [safetyVisible, scrollToBottom]);
  useEffect(() => { setTimeout(scrollToBottom, 80); }, [memBanner, scrollToBottom]);
  useEffect(() => { setTimeout(scrollToBottom, 80); }, [techniqueCheckIn, scrollToBottom]);
  useEffect(() => { setTimeout(scrollToBottom, 80); }, [pendingEntries.length, scrollToBottom]);

  // Welcome-back assistant message when memory loads.
  // Signature: (md, name) — md is the decrypted Markdown content, name is the
  // filename.  Content stored in-memory only (SPEC-800); indicator flag + name
  // persisted to sessionStorage so the topbar pill survives page reload.
  // onMemoryLoaded(md, name, sessionKey?)
  // sessionKey = { key: CryptoKey, salt: Uint8Array } from decryptMemoryKeepKey().
  // null for plaintext .md files (no encryption path available).
  // isNew = true when this is a freshly generated file (not loaded from disk).
  // Prevents a "Welcome back" greeting when the user just created their first file.
  const onMemoryLoaded = useCallback((md, name, sessionKey = null, isNew = false) => {
    // Store decrypted content in ref — available at send time, not in React state.
    memContentRef.current = md || null;
    // Store session key for write-back re-encryption (REQ-850-033).
    sessionKeyRef.current = sessionKey;
    setMemLoaded(true);
    setMemName(name);

    // Restore diary entries from the ## Mood Diary section.
    // Inverse of save() → formatDiaryEntry() in panels.jsx.
    // Only overwrites if the file actually has diary data (preserves any
    // in-session entries the user logged before loading the file).
    const parsedDiary = parseDiaryEntries(md);
    if (Object.keys(parsedDiary).length > 0) setMoodEntries(parsedDiary);

    // Extract the user's name from the ## Name section (if they set one).
    // parseMemoryName() is exported from memory.jsx and available on window.
    const userName = (typeof parseMemoryName === 'function')
      ? parseMemoryName(md)
      : '';
    setMemUserName(userName);

    // Different message for a newly created file vs. loading an existing one.
    // "Welcome back" is only shown when re-loading a file from a previous session.
    let chatText;
    if (isNew) {
      chatText = userName
        ? `Your memory file is ready, ${userName}. I'll keep what's there in mind as we talk — you're in charge of what stays.`
        : `Your memory file is ready. I'll keep what's there in mind as we talk — you're in charge of what stays.`;
    } else {
      const greeting = userName ? `Welcome back, ${userName}.` : 'Welcome back.';
      chatText = `${greeting} Your memory file is loaded — I'll keep what's there in mind, but the live conversation is what I'll really listen to. You're in charge of what stays.`;
    }

    const wbId = 'wb-' + Date.now();
    setMessages(prev => [...prev, {
      id: wbId,
      role: 'assistant',
      emotion: 'care',
      streaming: false,
      text: chatText,
    }]);
    setTimeout(scrollToBottom, 30);

    // [REQ-FIS-MC1] Mood check-in: trigger once per session when the user loads
    // an existing encrypted file (sessionKey present means it came from disk, not
    // a freshly generated one). isNew=true suppresses it on first-time file creation.
    // moodCheckInShownRef prevents re-triggering if the user loads a second file.
    if (!isNew && sessionKey && !moodCheckInShownRef.current) {
      moodCheckInShownRef.current = true;
      // Defer slightly so the wb message renders before the popup appears.
      setTimeout(() => setMoodCheckIn({ wbId }), 200);
    }

    // Show the memory-loaded banner for 7s, then auto-dismiss.
    // Cancel any prior auto-dismiss timer (e.g. if user loads a second file).
    clearTimeout(memBannerAutoRef.current);
    setMemBanner('loaded');
    memBannerAutoRef.current = setTimeout(() => setMemBanner(null), 7000);
  }, [scrollToBottom]);

  // Hint banner: after the 3rd user message, if no memory is loaded and the
  // hint hasn't been shown yet this session, surface the 'hint' banner once.
  // Uses hintShownRef (not state) to avoid the effect re-triggering on re-renders.
  useEffect(() => {
    if (memLoaded || hintShownRef.current || memBanner) return;
    const userCount = messages.filter(m => m.role === 'user').length;
    if (userCount >= 3) {
      hintShownRef.current = true;
      setMemBanner('hint');
    }
  }, [messages, memLoaded, memBanner]);

  // Clean up the auto-dismiss timer on unmount so it doesn't fire into
  // an unmounted component if the user somehow navigates away.
  useEffect(() => () => clearTimeout(memBannerAutoRef.current), []);

  // Mood diary state — pure React state, no storage backend.
  // [SPEC-800] Zero-retention: entries exist only for the current page load and
  // are gone on refresh or tab close. The ## Mood Diary section of the memory
  // file is the only durable channel (written explicitly via syncDiaryToMemory).
  const [moodEntries, setMoodEntries] = useState({});
  const setMoodEntry = (iso, val) => {
    setMoodEntries(prev => {
      const next = { ...prev };
      if (val === null) delete next[iso]; else next[iso] = val;
      return next;
    });
  };

  // Cite click → open sources panel (in-text [^s_key] citations — Phase 5+).
  const onCiteClick = useCallback((k) => {
    setActiveCite(k);
    setDynamicSources([]);  // clear dynamic; show static NIKKO_SOURCES lookup
    setRightTab('sources');
  }, []);

  // Sources badge click → open sources panel with DYNAMIC retrieved sources.
  // Called from the "Sources used (N)" badge below GUIDANCE mode responses.
  const onSourcesBadgeClick = useCallback((sources) => {
    setDynamicSources(sources);
    setActiveCite(null);
    setRightTab('sources');
  }, []);

  // ── Input word cap: honour input_length preference from memory file ──
  // The user can declare their typing style in their memory file:
  //   concise  → cap at ~150 words (fast typists; short messages)
  //   standard → cap at ~300 words (default)
  //   verbose  → cap at ~600 words (ramblers; important detail at the end)
  //
  // Truncation is applied to the payload sent to the backend only — the
  // full message is still shown in the chat thread so the UX isn't jarring.
  // Words are split on whitespace (not tokenised) — a rough but fast proxy.
  const INPUT_WORD_CAPS = { concise: 150, standard: 300, verbose: 600 };
  const DEFAULT_WORD_CAP = 300;

  const applyInputCap = useCallback((text) => {
    // Read prefs from live memory content (null if no file loaded).
    const md = memContentRef.current;
    if (!md) return text;
    const prefs = (typeof parseMemoryPrefs === 'function') ? parseMemoryPrefs(md) : {};
    const capKey = prefs.input_length || 'standard';
    const cap = INPUT_WORD_CAPS[capKey] !== undefined ? INPUT_WORD_CAPS[capKey] : DEFAULT_WORD_CAP;
    const words = text.split(/\s+/);
    if (words.length <= cap) return text;
    // Truncate to cap words — keep a trailing note so ADP-A knows it's seeing
    // a partial input (avoids the model inferring the user stopped mid-thought).
    return words.slice(0, cap).join(' ') + ' [message truncated per user preference]';
  }, []);

  // ── saveMemoryUpdates: re-encrypt and download updated memory file ──
  // Called when the user clicks Accept on a proposal card or the topbar Save button.
  // Re-uses the session key from decryptMemoryKeepKey — no password re-entry needed
  // (REQ-850-033). Each save generates a fresh IV (REQ-850-031).
  //
  // entries: array of { section, entry } to apply, or null to use all pendingEntries.
  const saveMemoryUpdates = useCallback(async (entries = null) => {
    if (!memContentRef.current || !sessionKeyRef.current) return;
    const toApply = entries || pendingEntries;
    if (!toApply.length) return;

    let updated = memContentRef.current;
    for (const e of toApply) {
      // applyMemoryEntry is exported from memory.jsx and available on window.
      if (typeof applyMemoryEntry === 'function') {
        updated = applyMemoryEntry(updated, e.section, e.entry);
      }
    }

    try {
      // encryptMemoryWithKey reuses session key + new random IV (REQ-850-031).
      const enc = await encryptMemoryWithKey(updated, sessionKeyRef.current);
      // Derive a clean filename — strip the path, keep the base name.
      const baseName = (memName || 'nikko-memory').replace(/\s+/g, '-');
      downloadFile(baseName, enc);
      // Update in-memory content ref to the updated plaintext.
      memContentRef.current = updated;
      // Clear only the saved entries from pending.
      if (entries) {
        const savedTs = new Set(entries.map(e => e.ts));
        setPendingEntries(prev => prev.filter(e => !savedTs.has(e.ts)));
      } else {
        setPendingEntries([]);
      }
    } catch (err) {
      console.error('[Nikko USM] Re-encryption failed:', err);
    }
  }, [pendingEntries, memName]);

  // ── onMemoryRewrite: direct free-form edit of the decrypted memory file ──
  // Called from MoodDiaryPanel's edit mode. Takes a full updated Markdown
  // string, re-encrypts with the in-memory session key (no password re-entry),
  // downloads the updated file, and updates memContentRef so subsequent
  // /api/message calls carry the new content.
  // Only callable when sessionKeyRef.current is set (encrypted file loaded).
  const onMemoryRewrite = useCallback(async (updatedMd) => {
    if (!sessionKeyRef.current) return;
    try {
      const enc = await encryptMemoryWithKey(updatedMd, sessionKeyRef.current);
      const baseName = (memName || 'nikko-memory').replace(/\s+/g, '-');
      downloadFile(baseName, enc);
      memContentRef.current = updatedMd;
      // Bump version so Chat re-renders and MoodDiaryPanel gets new content.
      setMemContentVersion(v => v + 1);
    } catch (err) {
      console.error('[Nikko USM] Memory rewrite failed:', err);
    }
  }, [memName]);

  // Convert a technique check-in acceptance into a pending entry (file loaded)
  // or open the generate modal with the entry pre-populated (bootstrap path).
  const onCheckInAdd = useCallback(() => {
    if (!techniqueCheckIn) return;
    if (memContentRef.current && sessionKeyRef.current) {
      // File is loaded — queue as a normal pending entry. The proposal card
      // will appear in the thread and the user can confirm before download.
      setPendingEntries(prev => [...prev, { ...techniqueCheckIn, ts: Date.now() }]);
    } else {
      // No file yet — stash the entry and open the generate modal. The entry
      // will be baked into the new file at download time (REQ-850-011 preserved:
      // user still explicitly triggers the generate + encrypt flow).
      setPendingBootstrapEntry(techniqueCheckIn);
      setMemOpen(true);
    }
    setTechniqueCheckIn(null);
  }, [techniqueCheckIn]);

  // [REQ-FIS-MC2] Handle mood check-in Log action.
  // Writes the rating + emotions to in-memory moodEntries state and queues
  // a diary write-back in pendingEntries so the user can save it to their file.
  // The diary entry format matches the round-trip contract in CLAUDE.md §5a.
  const onMoodCheckInLog = useCallback(({ rating, emotions }) => {
    const today = new Date().toISOString().split('T')[0];
    const entry = { mood: rating, emotions, triggers: '' };

    // Update in-memory diary state (session-scoped, cleared on refresh per SPEC-800).
    setMoodEntry(today, entry);

    // Queue a write-back pending entry so the user can save it to the encrypted file.
    // Section '## Mood Diary' matches the parseDiaryEntries() / formatDiaryEntry() contract.
    // formatDiaryEntry is exported to window from panels.jsx.
    const formatted = (typeof formatDiaryEntry === 'function')
      ? formatDiaryEntry(today, entry)
      : `${today} | mood: ${rating} | emotions: ${emotions.join(', ')} | triggers: `;
    setPendingEntries(prev => [...prev, {
      section: '## Mood Diary',
      entry:   formatted,
      ts:      Date.now(),
    }]);

    setMoodCheckIn(null);
  }, [setMoodEntry]);

  // Warn on tab close when there are unsaved pending entries (REQ-850-093).
  // The browser shows a generic "Leave site?" dialog — we can't customise the text.
  useEffect(() => {
    if (!pendingEntries.length) return;
    const handler = (e) => { e.preventDefault(); e.returnValue = ''; };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [pendingEntries.length]);

  // ── streamReply: POST /api/message → SSE → char-by-char animation ──
  // [REQ-FIS-001] Primary chat endpoint. Streams SSE from the Render backend
  // (which orchestrates ADP-B → ADP-A → ADP-C on the HF Space).
  // Falls back to matchNikkoPattern() if the backend is unreachable so the
  // frontend never goes blank during Render cold-start or network errors.
  const streamReply = useCallback(async (userText) => {
    setStreaming(true);
    setIsColdStart(false);
    const id = 'm-' + Date.now();
    setMessages(prev => [...prev, { id, role: 'assistant', text: '', emotion: 'listen', streaming: true, traceId: id, sources: [] }]);
    scrollToBottom();
    setCurrentEmotion('think');
    // [REQ-FIS-RB4] Add a placeholder trace entry immediately so AgentRibbon can
    // show live stage labels during the pipeline run. Populated by SSE stage updates;
    // replaced with real trace data on pipeline completion. _processing=true signals
    // the ribbon to render the stage label rather than the completion mode label.
    NikkoAgentLog.add({ id, userText, _processing: true, _stage: 'understanding your message' });

    // Start the cold-start detection timer. If no message_start SSE event
    // arrives within 12 seconds, the backend (Render) or HF Space is still
    // waking up — flip the flag so the user sees a specific cold-start notice.
    // 12s is chosen because warm responses land in <5s; anything beyond that
    // is reliably a cold-start scenario.
    coldStartTimerRef.current = setTimeout(() => setIsColdStart(true), 12000);

    // [CONCEPT] SSE (Server-Sent Events): a unidirectional HTTP stream where
    // the server pushes events as "event: <name>\ndata: <json>\n\n" blocks.
    // We read it with fetch() + ReadableStream instead of EventSource because
    // EventSource doesn't support POST requests.
    try {
      // Build request body — include memory context when a file is loaded.
      // memContentRef.current is null if no file is loaded or after a page
      // reload (SPEC-800: content is never persisted client-side across tabs).
      //
      // Apply the word cap from the user's input_length preference before
      // sending.  The thread shows the original; only the backend payload is
      // capped.  This keeps latency low for users who prefer concise reads.
      const cappedText = applyInputCap(userText);
      const reqBody = { text: cappedText, contextID };
      if (memContentRef.current) {
        // Cap at 8000 chars client-side to match backend MessageRequest limit.
        reqBody.memoryContext = memContentRef.current.slice(0, 8000);
      }

      // Build session-scoped conversation history from React state.
      // Excludes: the fixed opening message (id='open'), welcome-back messages
      // (id prefix 'wb-'), any messages still streaming, and the current turn
      // (which is being sent right now as `text`).
      // Cap raised to the last 20 turns (10 user + 10 assistant) so ADP-A
      // retains enough context to honour earlier disclosures (e.g. "I have no
      // family/friends", stated preferences, named topics from earlier in the
      // session). Server-side hard cap is 20 turns — matching this prevents
      // silent silently dropping turns.  Clears on refresh (React state).
      const historyRaw = messages
        .filter(m =>
          m.id !== 'open' &&
          !String(m.id).startsWith('wb-') &&
          !m.streaming &&
          m.text &&
          (m.role === 'user' || m.role === 'assistant')
        )
        .slice(-20)   // last 20 turns (up from 10 — more context, better memory)
        .map(m => ({ role: m.role, text: m.text }));
      if (historyRaw.length > 0) {
        reqBody.conversationHistory = historyRaw;
      }
      const response = await fetch(BACKEND_URL + '/api/message', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(reqBody),
      });

      if (!response.ok) throw new Error('HTTP ' + response.status);

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let currentEvent = '';
      let accText = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // Split on newlines; keep any incomplete final line in buffer.
        const lines = buffer.split('\n');
        buffer = lines.pop();

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEvent = line.slice(7).trim();
          } else if (line.startsWith('data: ')) {
            let data;
            try { data = JSON.parse(line.slice(6)); } catch { continue; }

            if (currentEvent === 'message_start') {
              // Server responded — cancel the cold-start timer and clear the
              // notice. The pipeline is now processing (not stuck on startup).
              clearTimeout(coldStartTimerRef.current);
              setIsColdStart(false);
              setCurrentEmotion(data.emotion || 'listen');

            } else if (currentEvent === 'chunk') {
              // Safety flag check — show banner if crisis detected.
              if (data.safetyFlags && data.safetyFlags.includes('crisis_detected')) setSafetyVisible(true);

              // [REQ-FIS-RB4] Update ribbon stage label from keep-alive SSE chunks.
              // Both text and non-text chunks may carry a stage field.
              if (data.stage) NikkoAgentLog.update(id, { _stage: data.stage });

              if (data.text) {
                const emotion = data.emotion || 'speak';
                setCurrentEmotion(emotion);
                // Animate the incoming text char-by-char so the UX feels alive.
                const target = accText + data.text;
                const stride = 3;
                let pos = accText.length;
                while (pos < target.length) {
                  pos = Math.min(target.length, pos + stride);
                  const slice = target.slice(0, pos);
                  setMessages(prev => prev.map(m =>
                    m.id === id ? { ...m, text: slice, emotion } : m
                  ));
                  scrollToBottom();
                  await sleep(14 + Math.random() * 10);
                }
                accText = target;
                // If this chunk carries real pipeline trace data, update the trace
                // entry (already created as a placeholder above) with the full results.
                // update() merges patch into the existing entry — _processing → false
                // signals the ribbon to switch from stage label to mode label.
                if (data.trace) {
                  // Bridge data.trace.mode ("guidance"/"comfort"/"crisis") to _mode
                  // (uppercase "GUIDANCE" / "COMFORT" / "CRISIS") so AgentRibbon and
                  // AgentDebugOverlay both use the correct key. Without this, _mode
                  // stays undefined from the initial placeholder and the ribbon always
                  // shows "comfort mode" regardless of the actual routing decision.
                  NikkoAgentLog.update(id, {
                    ...data.trace,
                    _mode: (data.trace.mode || '').toUpperCase() || undefined,
                    liveData: true,
                    _processing: false,
                  });
                }
                // Store retrieved evidence sources on the message for the badge.
                // data.sources is populated only when the pipeline ran in GUIDANCE
                // mode and returned real EvidenceItems (may be empty otherwise).
                if (data.sources && data.sources.length > 0) {
                  setMessages(prev => prev.map(m =>
                    m.id === id ? { ...m, sources: data.sources } : m
                  ));
                  // Also cache them so the Sources tab button can show them
                  // even if the user hasn't clicked the per-message badge.
                  lastResponseSourcesRef.current = data.sources;
                }

                // USM write-back: check for a memory_proposal from the backend.
                // Affirmation path — user typed something like "that really helped".
                // Requires file + session key (write-back path). If no file is loaded
                // the proposal is silently dropped; the technique check-in (below)
                // handles the no-file bootstrap case instead (REQ-850-040).
                if (data.memory_proposal && memContentRef.current && sessionKeyRef.current) {
                  setPendingEntries(prev => [...prev, {
                    ...data.memory_proposal,
                    ts: Date.now(),
                  }]);
                }

                // Technique check-in: backend detected Nikko recommended a named
                // technique. Now surfaces regardless of whether a file is loaded —
                // the banner copy and Accept action branch on hasMemory (bootstrap
                // vs patch). Suppressed if memory_proposal already fired this turn.
                if (data.technique_recommended && !data.memory_proposal) {
                  setTechniqueCheckIn(data.technique_recommended);
                }
              } else {
                // Empty text chunk = emotion-state signal only (e.g. "think").
                setCurrentEmotion(data.emotion || 'think');
              }

            } else if (currentEvent === 'message_end') {
              if (data.safetyFlags && data.safetyFlags.includes('crisis_detected')) setSafetyVisible(true);
            }
          }
        }
      }

      // If the stream closed without any text, the backend errored after
      // sending headers (e.g. HF_SPACE_URL not configured). The catch block
      // will run the local pattern-match fallback so the user always gets a reply.
      if (!accText) throw new Error('Empty stream — backend produced no text');

    } catch (err) {
      // ── Fallback: backend unreachable (Render cold-start, network error) ──
      // Gracefully degrade to the hardcoded pattern matcher so the user always
      // gets a response. Logged to console for debugging; not surfaced to user.
      clearTimeout(coldStartTimerRef.current);
      setIsColdStart(false);
      console.warn('[Nikko] Backend unavailable — using local fallback:', err.message);
      const pattern = matchNikkoPattern(userText);
      if (pattern.safety) setSafetyVisible(true);
      const trace = buildAgentTrace(id, userText, pattern);
      // update() instead of add() because the placeholder was added at message-create
      // time (above). Merging into the existing entry preserves the id→message binding.
      NikkoAgentLog.update(id, { ...trace, _processing: false });
      // Update initial message emotion to match fallback pattern.
      setMessages(prev => prev.map(m =>
        m.id === id ? { ...m, emotion: pattern.chunks[0].emotion } : m
      ));
      setCurrentEmotion('think');
      await sleep(420 + Math.random() * 220);
      let acc = '';
      for (let i = 0; i < pattern.chunks.length; i++) {
        const chunk = pattern.chunks[i];
        setCurrentEmotion(chunk.emotion);
        const target = (acc ? acc + '\n\n' : '') + chunk.text;
        const stride = 3;
        let pos = acc ? acc.length + 2 : 0;
        while (pos < target.length) {
          pos = Math.min(target.length, pos + stride);
          const slice = target.slice(0, pos);
          setMessages(prev => prev.map(m =>
            m.id === id ? { ...m, text: slice, emotion: chunk.emotion } : m
          ));
          forceRerender(x => x + 1);
          scrollToBottom();
          await sleep(14 + Math.random() * 10);
        }
        acc = target;
        await sleep(260);
      }
    }

    setMessages(prev => prev.map(m => m.id === id ? { ...m, streaming: false } : m));
    setStreaming(false);
    setCurrentEmotion('calm');
  }, [scrollToBottom, contextID, applyInputCap]);

  const onSend = useCallback((text) => {
    // /help command — reopens the tutorial without sending a message.
    if (text.trim().toLowerCase() === '/help') {
      setTutorialOpen(true);
      return;
    }
    setMessages(prev => [...prev, { id: 'u-' + Date.now(), role: 'user', text }]);
    scrollToBottom();
    streamReply(text);
  }, [scrollToBottom, streamReply]);

  // Live emotion shown in topbar avatar — only "active" while streaming.
  const liveEmotion = streaming ? currentEmotion : 'calm';
  const showSuggestions = messages.length === 1 && !streaming;

  // The most recent assistant message with a traceId — shows AgentRibbon on
  // BOTH streaming (processing) and completed messages. During streaming the
  // ribbon shows the live pipeline stage; after completion it shows the mode label.
  const lastAssistantId = React.useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const m = messages[i];
      if (m.role === 'assistant' && m.traceId) return m.id;
    }
    return null;
  }, [messages]);

  return (
    <div className="app">
      <header className="topbar floating">
        {/* Left pillbar — brand + research preview */}
        <div className="pillbar">
          <div className="brand-mini">
            <span
              className={'debug-trigger' + (debugGesture.holding ? ' holding' : '')}
              {...debugGesture.handlers}
              aria-hidden="true"
            >
              <NikkoAvatar emotion={liveEmotion} size={34} />
            </span>
            <span className="wordmark">Nikko</span>
          </div>
          <div className="divider" />
          <div className="tip-host research-pill">
            <span className="pill linklike" tabIndex={0}>
              <span className="dot" />Research preview
            </span>
            <div className="tip" role="tooltip">
              Nikko is an open research preview — non-diagnostic, not a clinician,
              implementation publicly visible at{' '}
              <a href="https://github.com/equinox013/nikko-companion" target="_blank" rel="noopener noreferrer">
                github.com/equinox013/nikko-companion
              </a>.
            </div>
          </div>
          {memLoaded && (
            <>
              <div className="divider" />
              {/* memContentRef.current is null after a page reload — the flag
                  persists but the content is gone (SPEC-800).  Show a "re-load"
                  hint so the user knows they need to re-load the file to have
                  full memory context active for this session. */}
              <span
                className="mem-indicator"
                title={
                  memContentRef.current
                    ? (memName ? 'Memory active · ' + memName : 'Memory active')
                    : 'Memory file was loaded — re-load to restore context for this session'
                }
              >
                <span className={memContentRef.current ? 'pulse' : 'pulse dim'} />
                {memContentRef.current
                  ? (memUserName ? `Memory · ${memUserName}` : 'Memory active')
                  : 'Memory · re-load'}
              </span>
            </>
          )}
        </div>

        {/* Right pillbar — memory · theme · quick exit */}
        <div className="pillbar">
          <div className="mem-pop-host" style={{ position: 'relative' }}>
            <button className={'ghostbtn' + (memLoaded ? ' active' : '')}
                    onClick={() => setMemPop(p => !p)}
                    aria-expanded={memPop}
                    title="Personal memory file">
              <svg viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ width: 13, height: 13, marginRight: 6, verticalAlign: '-2px' }}>
                <rect x="2.5" y="6" width="9" height="6.5" rx="1.2" />
                <path d="M4.5 6V4a2.5 2.5 0 0 1 5 0v2" />
                <path d="M7 8.5v2" />
              </svg>
              Memory
            </button>
            {memPop && (
              <div className="popover" role="dialog" aria-label="Personal memory">
                <h4>Personal memory</h4>
                <div className={'status' + (memContentRef.current ? ' on' : '')}>
                  <span className="dot" />
                  {memContentRef.current
                    ? (memName ? 'Loaded · ' + (memName.length > 24 ? memName.slice(0, 22) + '…' : memName) : 'Loaded')
                    : 'No memory file loaded'}
                </div>
                <div className="row">
                  <button onClick={() => { setMemPop(false); setLoadOpen(true); }}>
                    <svg viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M2.5 9V11a1 1 0 0 0 1 1h7a1 1 0 0 0 1-1V9" />
                      <path d="M7 9V2.5" /><path d="M4 5.5 7 2.5l3 3" />
                    </svg>
                    Load
                  </button>
                  <button onClick={() => { setMemPop(false); setMemOpen(true); }}>
                    <svg viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M7 2.5v9M2.5 7h9" />
                    </svg>
                    Generate
                  </button>
                </div>
                <div className="hint">
                  Encrypted on your device. Nothing is uploaded. You can carry the file across sessions.
                </div>
              </div>
            )}
          </div>

          <button className="iconbtn" onClick={onToggleTheme}
                  aria-label={'Switch to ' + (theme === 'light' ? 'dark' : 'light') + ' mode'}
                  title={'Switch to ' + (theme === 'light' ? 'dark' : 'light') + ' mode'}>
            {theme === 'light' ? (
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M11.5 9.5A4 4 0 0 1 6.5 4.5a5 5 0 1 0 5 5z" />
              </svg>
            ) : (
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="8" cy="8" r="3" />
                <path d="M8 1.5v1.5M8 13v1.5M1.5 8h1.5M13 8h1.5M3.4 3.4l1 1M11.6 11.6l1 1M3.4 12.6l1-1M11.6 4.4l1-1" />
              </svg>
            )}
          </button>

          {/* Help button — replays the first-run tutorial. Also accessible via /help in the composer. */}
          <button className="iconbtn" onClick={() => setTutorialOpen(true)}
                  aria-label="Help / replay tutorial"
                  title="Help — type /help or click here to replay the tutorial">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="8" cy="8" r="6" />
              <path d="M8 11.5v-.5" />
              <path d="M8 9.5c0-1.5 2-1.5 2-3a2 2 0 0 0-4 0" />
            </svg>
          </button>

          {/* Topbar save button — appears when pending write-back entries exist.
              REQ-850-093: session-end warning fires via beforeunload; this button
              gives the user an explicit in-session save path at any time. */}
          {pendingEntries.length > 0 && (
            <>
              <div className="divider" />
              <button
                className="ghostbtn mem-save-btn"
                onClick={() => saveMemoryUpdates()}
                title={`Save ${pendingEntries.length} pending memory update${pendingEntries.length !== 1 ? 's' : ''}`}
              >
                <svg viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ width: 13, height: 13, marginRight: 5, verticalAlign: '-2px' }}>
                  <path d="M2.5 9V11a1 1 0 0 0 1 1h7a1 1 0 0 0 1-1V9" />
                  <path d="M7 1.5v8" /><path d="M4.5 6.5 7 9l2.5-2.5" />
                </svg>
                Save memory ({pendingEntries.length})
              </button>
            </>
          )}

          <div className="divider" />

          <button className="ghostbtn danger" onClick={quickExit}
                  title="Quick exit — clears this session and navigates away">
            <svg viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" style={{ width: 13, height: 13, marginRight: 5, verticalAlign: '-2px' }}>
              <path d="M8.5 2.5h-5v9h5" />
              <path d="M6 7h6" />
              <path d="m9.5 4.5 2.5 2.5-2.5 2.5" />
            </svg>
            Quick exit
          </button>
        </div>
      </header>

      <main className="chat floating" data-left={leftTab ? 'open' : 'closed'} data-right={rightTab ? 'open' : 'closed'}>
        {/* Floating tab launchers */}
        {!leftTab && (
          <button className="tab-float left" onClick={() => setLeftTab('mood')} title="Mood diary">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <rect x="2.5" y="3.5" width="11" height="10" rx="1.5" />
              <path d="M2.5 6h11M5 2.5v3M11 2.5v3" />
            </svg>
            Mood diary
          </button>
        )}
        {!rightTab && (
          <button className="tab-float right" onClick={() => {
            // If the last GUIDANCE response returned sources, surface them in
            // the panel automatically — user doesn't need to find the badge.
            if (lastResponseSourcesRef.current.length > 0) {
              setDynamicSources(lastResponseSourcesRef.current);
            }
            setRightTab('sources');
          }} title="Sources">
            Sources
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 2.5h7l2.5 2.5v8.5H3z" />
              <path d="M3 5.5h6M3 8h7M3 10.5h5" />
            </svg>
          </button>
        )}

        {leftTab === 'mood' && (
          <MoodDiaryPanel
            entries={moodEntries}
            onSet={setMoodEntry}
            onClose={() => setLeftTab(null)}
            memoryContent={memContentRef.current}
            onMemoryUpdate={sessionKeyRef.current ? onMemoryRewrite : null}
          />
        )}

        <div className="thread-wrap">
          <div
            className="thread"
            ref={threadRef}
            style={safetyVisible ? { paddingBottom: '290px' } : undefined}
          >
            <div className="thread-inner">
              <div className="session-stamp">Today · session begins</div>
              {messages.map((m, idx) => {
                if (m.role === 'user') {
                  return (
                    <div className="msg user" key={m.id}>
                      <div className="body"><div className="bubble">{m.text}</div></div>
                    </div>
                  );
                }
                return (
                  <React.Fragment key={m.id}>
                  <div className="msg assistant">
                    <div className="avatar-slot">
                      <NikkoAvatar emotion={m.emotion || 'calm'} size={42} />
                    </div>
                    <div className="body">

                      {/* AgentRibbon — pinned to the TOP of the message body so
                          the live pipeline stage / mode label is always the first
                          thing visible above the content. [REQ-FIS-RB4]
                          During processing (_processing=true): shows stage label.
                          After completion: shows mode label (comfort / guidance / crisis). */}
                      {m.traceId && m.id === lastAssistantId && (
                        <AgentRibbon traceId={m.traceId} />
                      )}

                      {m.text === '' && m.streaming ? (
                        <ThinkingBubble coldStart={isColdStart} />
                      ) : (
                        <div className="bubble">
                          <MessageBody
                            text={m.text}
                            sourceOrder={sourceOrderRef.current}
                            onCiteClick={onCiteClick}
                            streaming={!!m.streaming}
                          />
                        </div>
                      )}
                      {/* Sources badge — shown when GUIDANCE mode returned evidence.
                          Only visible after streaming completes (not during ThinkingBubble).
                          Clicking opens the SourcesPanel with the real retrieved URLs. */}
                      {m.sources && m.sources.length > 0 && !m.streaming && (
                        <button
                          className="sources-badge"
                          onClick={() => onSourcesBadgeClick(m.sources)}
                          title="View sources used in this response"
                        >
                          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                            <path d="M2 3h9a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V3z"/>
                            <path d="M5 3V1h7a1 1 0 0 1 1 1v10"/>
                            <path d="M5 7h5M5 10h3"/>
                          </svg>
                          {m.sources.length} source{m.sources.length !== 1 ? 's' : ''} used
                        </button>
                      )}
                      {idx === 0 && showSuggestions && (
                        <div className="suggest-row">
                          {NIKKO_SUGGESTIONS.map(s => (
                            <button key={s} className="suggest" onClick={() => onSend(s)}>{s}</button>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                  {/* [REQ-FIS-MC1] Mood check-in popup — inline in thread after
                      welcome-back message when an existing encrypted file is loaded.
                      Dismissed via Log (writes diary entry) or Skip (no-op). */}
                  {moodCheckIn && m.id === moodCheckIn.wbId && (
                    <MoodCheckInPopup
                      onLog={onMoodCheckInLog}
                      onSkip={() => setMoodCheckIn(null)}
                    />
                  )}
                  </React.Fragment>
                );
              })}
            </div>
          </div>

          <div className="composer-wrap">
            <div className="composer-inner">
              {/* Technique check-in banner — now fires regardless of file state.
                  hasMemory=true  → "Add to memory" queues a proposal card.
                  hasMemory=false → "Create memory file" opens generate modal
                                    with entry pre-populated (bootstrap path). */}
              {techniqueCheckIn && (
                <TechniqueCheckInBanner
                  technique={techniqueCheckIn.technique}
                  hasMemory={!!(memContentRef.current && sessionKeyRef.current)}
                  onAdd={onCheckInAdd}
                  onDismiss={() => setTechniqueCheckIn(null)}
                />
              )}
              {/* Memory proposal cards — one per pending write-back entry.
                  Shown in arrival order; each has Accept / Decline.
                  Accept: saves that single entry and downloads updated file.
                  Decline: removes from pending without writing anything. */}
              {pendingEntries.map((entry) => (
                <MemoryProposalCard
                  key={entry.ts}
                  proposal={entry}
                  onAccept={() => saveMemoryUpdates([entry])}
                  onDecline={() => setPendingEntries(prev => prev.filter(e => e.ts !== entry.ts))}
                />
              ))}
              {memBanner && (
                <MemBanner
                  type={memBanner}
                  onDismiss={() => {
                    clearTimeout(memBannerAutoRef.current);
                    setMemBanner(null);
                  }}
                  onOpenLoad={() => {
                    setMemBanner(null);
                    setLoadOpen(true);
                  }}
                />
              )}
              {safetyVisible && <SafetyBanner onDismiss={() => setSafetyVisible(false)} />}
              {/* maxLength is derived from memContentRef — extended to 1500 if
                  memory signals the user tends to write at length, otherwise 1000. */}
              <Composer onSend={onSend} disabled={streaming} maxLength={deriveCharLimit(memContentRef.current)} />
              {/* G-UI-01: persistent AI disclaimer — always visible per REQ-300-164 */}
              <AiDisclaimer />
            </div>
          </div>
        </div>
        {/* /thread-wrap */}

        {rightTab === 'sources' && (
          <SourcesPanel
            sourceOrder={sourceOrderRef.current}
            activeKey={activeCite}
            onClose={() => setRightTab(null)}
            dynamicSources={dynamicSources}
          />
        )}

        {/* ── Mobile bottom sheet backdrop ─────────────────────────
            Visible only on ≤600px via CSS. Tapping it closes whichever
            panel is open — acts as the dismiss gesture for the sheet. */}
        {(leftTab || rightTab) && (
          <div
            className="sheet-backdrop"
            onClick={() => { setLeftTab(null); setRightTab(null); }}
            aria-hidden="true"
          />
        )}

        {/* ── Mobile bottom tab bar ────────────────────────────────
            Hidden on desktop via CSS (display:none). Replaces the
            .tab-float side buttons on narrow viewports with a native-
            style tab bar. Mood and Sources tabs toggle their sheets;
            opening one auto-closes the other. */}
        <nav className="mobile-tabbar" aria-label="Panels">
          <button
            className={'mtab' + (leftTab === 'mood' ? ' active' : '')}
            aria-pressed={leftTab === 'mood'}
            aria-label="Mood diary"
            onClick={() => {
              setLeftTab(v => v === 'mood' ? null : 'mood');
              setRightTab(null);
            }}
          >
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <rect x="2.5" y="3.5" width="11" height="10" rx="1.5" />
              <path d="M2.5 6h11M5 2.5v3M11 2.5v3" />
            </svg>
            Mood
          </button>
          <button
            className={'mtab sources' + (rightTab === 'sources' ? ' active' : '')}
            aria-pressed={rightTab === 'sources'}
            aria-label="Sources"
            onClick={() => {
              if (rightTab !== 'sources') {
                if (lastResponseSourcesRef.current.length > 0) {
                  setDynamicSources(lastResponseSourcesRef.current);
                }
                setRightTab('sources');
              } else {
                setRightTab(null);
              }
              setLeftTab(null);
            }}
          >
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 2.5h7l2.5 2.5v8.5H3z" />
              <path d="M3 5.5h6M3 8h7M3 10.5h5" />
            </svg>
            Sources
          </button>
        </nav>
      </main>

      {/* Memory modals */}
      {memOpen && (
        <MemoryGenerateModal
          open={memOpen}
          onClose={() => { setMemOpen(false); setPendingBootstrapEntry(null); }}
          onCreated={(md) => { setMemOpen(false); setPendingBootstrapEntry(null); onMemoryLoaded(md, 'nikko-memory', null, true); }}
          initialEntries={pendingBootstrapEntry ? [pendingBootstrapEntry] : []}
        />
      )}
      {loadOpen && (
        <MemoryLoadModal
          open={loadOpen}
          onClose={() => setLoadOpen(false)}
          onLoaded={(md, name, sessionKey) => { setLoadOpen(false); onMemoryLoaded(md, name, sessionKey); }}
        />
      )}

      {/* First-run tutorial */}
      <Tutorial open={tutorialOpen} onSkip={closeTutorial} onDone={closeTutorial} />
      <AgentDebugOverlay open={debugOpen} onClose={() => setDebugOpen(false)} />
    </div>
  );
}

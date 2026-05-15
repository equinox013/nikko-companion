// panels.jsx — Sources panel (right), Mood Diary panel (left), Tutorial overlay.

const { useState: ps, useEffect: pe, useRef: pr } = React;

// ── APA 7 formatter ─────────────────────────────────────────────────
// Produces a best-effort APA 7th edition reference string from a SourceItem
// (the serialised EvidenceItem returned by the backend pipeline).
//
// APA 7 web page / org report format:
//   Author/Org. (Year). Title of page. Site Name. URL
//
// APA 7 journal article format (used when evidence_tier === "peer_reviewed"):
//   Author/Org. (Year). Title. Journal Name. DOI/URL
//
// Because EvidenceItem does not carry individual author names or journal
// volume/issue details, source_name fills the Author/Org position and
// the URL fills the DOI/location position. This is the closest conformant
// representation without richer metadata — flagged as a Phase 5 enhancement
// (fuller PubMed metadata parsing in the retrieval layer).
function formatAPA7(source) {
  const org   = (source.source_name || 'Unknown organisation').trim();
  const year  = source.year ? source.year : 'n.d.';
  const title = (source.title || '(Untitled)').trim();
  const url   = (source.url || '').trim();

  if (source.evidence_tier === 'peer_reviewed') {
    // Journal / peer-reviewed format
    return url
      ? `${org}. (${year}). ${title}. ${url}`
      : `${org}. (${year}). ${title}.`;
  }
  // Web page / grey-literature format — APA 7 requires "Retrieved from" for
  // undated web pages; for dated pages the URL alone is sufficient.
  const location = url
    ? (source.year ? url : `Retrieved from ${url}`)
    : '';
  return location
    ? `${org}. (${year}). ${title}. ${location}`
    : `${org}. (${year}). ${title}.`;
}

// ── Sources panel (right) ───────────────────────────────────────────
// Accepts two source modes:
//
//   dynamicSources (array of SourceItem) — real URLs retrieved by the
//   pipeline's evidence adapters (PubMed + sanctioned web search).
//   Rendered when user clicks the "N sources used" badge under a message.
//   Takes priority over the static NIKKO_SOURCES lookup.
//
//   sourceOrder + NIKKO_SOURCES — legacy static dict used for in-text
//   [^s_key] citations (Phase 5+ when ADP-A learns citation format).
//   Used when dynamicSources is empty.
function SourcesPanel({ sourceOrder, activeKey, onClose, dynamicSources }) {
  const hasDynamic = dynamicSources && dynamicSources.length > 0;

  // Scroll to activeKey card when opened via in-text citation click.
  pe(() => {
    if (!activeKey || hasDynamic) return;
    const el = document.querySelector(`[data-anchor="source-${activeKey}"]`);
    if (el) el.scrollIntoView({ block: 'center' });
  }, [activeKey, hasDynamic]);

  // ── Dynamic sources (from live retrieval) ─────────────────────────
  if (hasDynamic) {
    return (
      <aside className="panel right" aria-label="Sources used">
        <div className="panel-head">
          <div>
            <h3>Sources</h3>
            <div className="meta">
              {dynamicSources.length} reference{dynamicSources.length !== 1 ? 's' : ''} · APA 7
            </div>
          </div>
          <button className="iconbtn" onClick={onClose} aria-label="Close sources">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
              <path d="m4 4 8 8M12 4l-8 8" />
            </svg>
          </button>
        </div>
        <div className="panel-body">
          {dynamicSources.map((s, i) => (
            <div key={i} className="source-card">
              <div className="row">
                <span className="num">{i + 1}</span>
                <span>{s.source_name}</span>
                {s.evidence_tier === 'peer_reviewed' && (
                  <span style={{
                    fontSize: 10, fontWeight: 600, letterSpacing: '0.04em',
                    background: 'var(--accent-muted, rgba(99,102,241,0.12))',
                    color: 'var(--accent, #6366f1)',
                    borderRadius: 4, padding: '1px 5px', marginLeft: 6,
                  }}>Peer-reviewed</span>
                )}
              </div>
              <div className="title">{s.title}</div>
              {s.url && (
                <a className="linkrow" href={s.url} target="_blank" rel="noopener noreferrer">
                  {s.url.replace(/^https?:\/\//, '').slice(0, 60)}{s.url.length > 67 ? '…' : ''}
                </a>
              )}
              <div className="apa">{formatAPA7(s)}</div>
            </div>
          ))}
          <div style={{ fontSize: 11, color: 'var(--muted)', padding: '10px 4px 0' }}>
            References formatted to APA 7th edition (best-effort — full author/volume metadata requires Phase 5 PubMed enrichment).
          </div>
        </div>
      </aside>
    );
  }

  // ── Static sources (in-text [^s_key] citation lookup) ────────────
  const ordered = Object.entries(sourceOrder)
    .sort((a, b) => a[1] - b[1])
    .map(([k, n]) => ({ key: k, num: n, ...(NIKKO_SOURCES[k] || {}) }));
  pe(() => {
    if (!activeKey) return;
    const el = document.querySelector(`[data-anchor="source-${activeKey}"]`);
    if (el) el.scrollIntoView({ block: 'center' });
  }, [activeKey]);
  return (
    <aside className="panel right" aria-label="Sources used">
      <div className="panel-head">
        <div>
          <h3>Sources</h3>
          <div className="meta">{ordered.length} reference{ordered.length === 1 ? '' : 's'} · APA 7</div>
        </div>
        <button className="iconbtn" onClick={onClose} aria-label="Close sources">
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
            <path d="m4 4 8 8M12 4l-8 8" />
          </svg>
        </button>
      </div>
      <div className="panel-body">
        {ordered.length === 0 && (
          <div style={{ color: 'var(--muted)', fontSize: 13, padding: '8px 4px' }}>
            No sources cited yet. They'll appear here when Nikko references one.
          </div>
        )}
        {ordered.map(s => (
          <div key={s.key}
               className={`source-card ${activeKey === s.key ? 'active' : ''}`}
               data-anchor={`source-${s.key}`}>
            <div className="row">
              <span className="num">{s.num}</span>
              <span>{s.org}</span>
            </div>
            <div className="title">{s.title}</div>
            {s.href && s.href !== '#' && (
              <a className="linkrow" href={s.href} target="_blank" rel="noopener noreferrer">
                {s.href.replace(/^https?:\/\//, '').slice(0, 60)}{s.href.length > 67 ? '…' : ''}
              </a>
            )}
            <div className="blurb">{s.blurb}</div>
            {s.apa && <div className="apa">{s.apa}</div>}
          </div>
        ))}
      </div>
    </aside>
  );
}

function todayISO() {
  const d = new Date();
  return d.toISOString().slice(0, 10);
}
function formatDay(iso) {
  const d = new Date(iso + 'T00:00:00');
  return d.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' });
}

// Most common first; rest revealed under "more"
const EMOTION_OPTIONS = [
  'calm', 'tired', 'anxious', 'low', 'hopeful', 'content', 'irritable', 'overwhelmed',
  'grateful', 'numb', 'lonely', 'angry', 'restless', 'focused'
];
const EMOTION_PRIMARY = 8;
const TRIGGER_OPTIONS = [
  'work', 'sleep', 'family', 'health', 'money', 'relationship',
  'study', 'social', 'news', 'nothing specific'
];
const TRIGGER_PRIMARY = 6;
const MOOD_COLORS = ['#c95a5a','#d77452','#db8f4e','#d4a352','#c9b260','#a9b76a','#88b378','#6aab83','#4f9c8c','#3d8a8e'];
const JOURNAL_LIMIT = 4000;
const POMODORO_SECS = 10 * 60;

function MoodDiaryPanel({ entries, onSet, onClose }) {
  const [selectedDay, setSelectedDay] = ps(todayISO());
  const e0 = entries[selectedDay] || { mood: 0, emotions: [], triggers: [], note: '', journal: '' };
  const [draftMood, setDraftMood] = ps(e0.mood || 0);
  const [draftEmotions, setDraftEmotions] = ps(e0.emotions || []);
  const [draftTriggers, setDraftTriggers] = ps(e0.triggers || []);
  const [draftNote, setDraftNote] = ps(e0.note || '');
  const [draftJournal, setDraftJournal] = ps(e0.journal || '');
  const [showAllEmotions, setShowAllEmotions] = ps(false);
  const [showAllTriggers, setShowAllTriggers] = ps(false);
  const [showReflection, setShowReflection] = ps(!!(e0.journal && e0.journal.trim()));

  pe(() => {
    const e = entries[selectedDay] || { mood: 0, emotions: [], triggers: [], note: '', journal: '' };
    setDraftMood(e.mood || 0);
    setDraftEmotions(e.emotions || []);
    setDraftTriggers(e.triggers || []);
    setDraftNote(e.note || '');
    setDraftJournal(e.journal || '');
    setShowReflection(!!(e.journal && e.journal.trim()));
    setShowAllEmotions(false);
    setShowAllTriggers(false);
  }, [selectedDay]);

  const [secsLeft, setSecsLeft] = ps(POMODORO_SECS);
  const [running, setRunning] = ps(false);
  pe(() => {
    if (!running) return;
    const t = setInterval(() => {
      setSecsLeft(s => {
        if (s <= 1) { setRunning(false); return 0; }
        return s - 1;
      });
    }, 1000);
    return () => clearInterval(t);
  }, [running]);
  const mm = String(Math.floor(secsLeft / 60)).padStart(2, '0');
  const ss = String(secsLeft % 60).padStart(2, '0');

  const days = Object.entries(entries).sort((a, b) => b[0].localeCompare(a[0]));
  const toggleIn = (arr, v) => arr.includes(v) ? arr.filter(x => x !== v) : [...arr, v];
  const isEmpty = draftMood === 0 && draftEmotions.length === 0 && draftTriggers.length === 0
                && !draftNote.trim() && !draftJournal.trim();

  const save = () => {
    if (isEmpty) return;
    onSet(selectedDay, {
      mood: draftMood,
      emotions: draftEmotions,
      triggers: draftTriggers,
      note: draftNote.trim(),
      journal: draftJournal.trim(),
    });
  };
  const clearDay = () => {
    setDraftMood(0); setDraftEmotions([]); setDraftTriggers([]);
    setDraftNote(''); setDraftJournal('');
    onSet(selectedDay, null);
  };
  const charsLeft = JOURNAL_LIMIT - draftJournal.length;

  return (
    <aside className="panel left" aria-label="Mood diary">
      <div className="panel-head">
        <div>
          <h3>Mood diary</h3>
          <div className="meta">Stays on your device</div>
        </div>
        <button className="iconbtn" onClick={onClose} aria-label="Close mood diary">
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
            <path d="m4 4 8 8M12 4l-8 8" />
          </svg>
        </button>
      </div>
      <div className="panel-body mood-body">
        <div className="mood-day-stamp">
          {formatDay(selectedDay)}{selectedDay === todayISO() ? ' · today' : ''}
        </div>

        <div className="mood-section">
          <label>How is today, overall?</label>
          <div className="mood-rating-row">
            {[1,2,3,4,5,6,7,8,9,10].map(n => (
              <button key={n}
                      className={`pip ${draftMood === n ? 'on' : ''}`}
                      data-r={n}
                      onClick={() => setDraftMood(n)}
                      aria-label={`Mood ${n} of 10`}>
                {n}
              </button>
            ))}
          </div>
          <div className="mood-scale-ends">
            <span>low</span><span>good</span>
          </div>
        </div>

        <div className="mood-section">
          <label>A line about today</label>
          <textarea
            className="mood-text"
            placeholder="Just a sentence or two — optional."
            value={draftNote}
            onChange={e => setDraftNote(e.target.value)}
            rows={2}
          />
        </div>

        <details className="mood-disclosure" open={draftEmotions.length > 0 || draftTriggers.length > 0}>
          <summary>
            <span>Emotions &amp; context</span>
            <span className="mood-disclosure-count">
              {draftEmotions.length + draftTriggers.length || ''}
            </span>
          </summary>

          <div className="mood-section">
            <label>Emotions</label>
            <div className="mood-chips">
              {(showAllEmotions ? EMOTION_OPTIONS : EMOTION_OPTIONS.slice(0, EMOTION_PRIMARY)).map(em => (
                <button key={em}
                        className={`mood-chip ${draftEmotions.includes(em) ? 'on' : ''}`}
                        onClick={() => setDraftEmotions(arr => toggleIn(arr, em))}>
                  {em}
                </button>
              ))}
              {EMOTION_OPTIONS.length > EMOTION_PRIMARY && (
                <button className="mood-chip ghost"
                        onClick={() => setShowAllEmotions(v => !v)}>
                  {showAllEmotions ? 'less' : `+${EMOTION_OPTIONS.length - EMOTION_PRIMARY} more`}
                </button>
              )}
            </div>
          </div>

          <div className="mood-section">
            <label>What's around it</label>
            <div className="mood-chips">
              {(showAllTriggers ? TRIGGER_OPTIONS : TRIGGER_OPTIONS.slice(0, TRIGGER_PRIMARY)).map(tr => (
                <button key={tr}
                        className={`mood-chip ${draftTriggers.includes(tr) ? 'on' : ''}`}
                        onClick={() => setDraftTriggers(arr => toggleIn(arr, tr))}>
                  {tr}
                </button>
              ))}
              {TRIGGER_OPTIONS.length > TRIGGER_PRIMARY && (
                <button className="mood-chip ghost"
                        onClick={() => setShowAllTriggers(v => !v)}>
                  {showAllTriggers ? 'less' : `+${TRIGGER_OPTIONS.length - TRIGGER_PRIMARY} more`}
                </button>
              )}
            </div>
          </div>
        </details>

        {!showReflection ? (
          <button className="mood-add-reflection" onClick={() => setShowReflection(true)}>
            <span className="plus">+</span>
            <span>Add a 10-minute reflection</span>
          </button>
        ) : (
          <div className="mood-section reflection-block">
            <div className="reflection-head">
              <label>Reflection</label>
              <button className="mood-link" onClick={() => { setShowReflection(false); setRunning(false); }}>
                hide
              </button>
            </div>
            <div className="pomodoro">
              <div>
                <div className={`clock ${running && secsLeft < 60 ? 'warn' : ''}`}>{mm}:{ss}</div>
                <div className="meta">{running ? 'writing…' : (secsLeft === 0 ? 'time up' : 'paused')}</div>
              </div>
              <div style={{ display: 'flex', gap: 6 }}>
                {!running && secsLeft > 0 && (
                  <button onClick={() => setRunning(true)}>{secsLeft === POMODORO_SECS ? 'Start' : 'Resume'}</button>
                )}
                {running && <button onClick={() => setRunning(false)}>Pause</button>}
                <button onClick={() => { setRunning(false); setSecsLeft(POMODORO_SECS); }}>Reset</button>
              </div>
            </div>
            <textarea
              className="mood-text"
              placeholder="Write freely. No one sees this but you."
              value={draftJournal}
              onChange={e => setDraftJournal(e.target.value.slice(0, JOURNAL_LIMIT))}
              rows={6}
              style={{ minHeight: 120 }}
            />
            <div className={`char-count ${charsLeft < 200 ? 'warn' : ''}`}>
              {draftJournal.length} / {JOURNAL_LIMIT}
            </div>
          </div>
        )}

        <div className="mood-actions">
          <button className="btn-secondary" onClick={clearDay}>Clear day</button>
          <button className="btn-primary" onClick={save} disabled={isEmpty}>Save</button>
        </div>

        {days.length > 0 && <div className="mood-divider" />}

        {days.length > 0 && (
          <div className="mood-past-head">Past entries</div>
        )}
        {days.length === 0 && (
          <div className="mood-empty">
            No entries yet. Today is a good place to start.
          </div>
        )}
        <div className="mood-past-list">
          {days.map(([iso, e]) => (
            <button key={iso}
                 className={`mood-row ${selectedDay === iso ? 'active' : ''}`}
                 onClick={() => setSelectedDay(iso)}>
              <span className="mood-row-dot"
                    style={{ background: e.mood ? MOOD_COLORS[e.mood - 1] : 'var(--line)' }}
                    aria-hidden="true" />
              <span className="mood-row-date">{formatDay(iso)}</span>
              <span className="mood-row-summary">
                {e.note
                  ? e.note
                  : (e.emotions && e.emotions.length
                      ? e.emotions.slice(0, 3).join(' · ')
                      : (e.journal ? 'reflection saved' : '—'))}
              </span>
              <span className="mood-row-score">{e.mood ? e.mood : '—'}</span>
            </button>
          ))}
        </div>
      </div>
    </aside>
  );
}

// ── Tutorial overlay ────────────────────────────────────────────────
const TUTORIAL_STEPS = [
  {
    title: "Welcome — is this your first time?",
    body: "Nikko is a quiet place to think out loud. Take 30 seconds to see what's here, or skip ahead any time.",
    features: null,
  },
  {
    title: "What you can do here",
    body: "Four things sit around the conversation. Each one is opt-in, and nothing tracks you between sessions.",
    features: [
      { ico: 'mem',   title: 'Personal Memory', body: 'Optional encrypted memory file you keep on your device. Top-right.' },
      { ico: 'src',   title: 'Sources tab',     body: 'Right side. Anything Nikko cites links to a source with a summary and APA 7 reference.' },
      { ico: 'mood',  title: 'Mood diary',      body: 'Left side. A 1–5 scale and an optional note per day. Stored locally.' },
      { ico: 'exit',  title: 'Quick exit',      body: 'Top-right. One tap clears this session and navigates away.' },
    ],
  },
  {
    title: "A few principles",
    body: "Nikko is a research preview. It's non-diagnostic, doesn't replace a clinician, and won't pretend to remember you between sessions unless you provide your own memory file.",
    features: null,
  },
];

function TutorialFeatureIcon({ kind }) {
  switch (kind) {
    case 'mem':
      return <svg viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><rect x="2.5" y="6" width="9" height="6.5" rx="1.2" /><path d="M4.5 6V4a2.5 2.5 0 0 1 5 0v2" /></svg>;
    case 'src':
      return <svg viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><path d="M3 2.5h6L11.5 5v6.5H3z" /><path d="M3 5.5h5M3 8h6M3 10.5h4" /></svg>;
    case 'mood':
      return <svg viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="3" width="10" height="9" rx="1.4" /><path d="M2 5.5h10M5 2v3M9 2v3" /></svg>;
    case 'exit':
      return <svg viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><path d="M8.5 2.5h-5v9h5" /><path d="M6 7h6" /><path d="m9.5 4.5 2.5 2.5-2.5 2.5" /></svg>;
    default: return null;
  }
}

function Tutorial({ open, onSkip, onDone }) {
  const [step, setStep] = ps(0);
  pe(() => { if (open) setStep(0); }, [open]);
  if (!open) return null;
  const s = TUTORIAL_STEPS[step];
  const isLast = step === TUTORIAL_STEPS.length - 1;
  return (
    <div className="tutorial-veil">
      <div className="tutorial">
        <div className="step-num">Step {step + 1} of {TUTORIAL_STEPS.length}</div>
        <h2>{s.title}</h2>
        <p>{s.body}</p>
        {s.features && (
          <div className="feature-grid">
            {s.features.map(f => (
              <div className="feature" key={f.title}>
                <span className="ico"><TutorialFeatureIcon kind={f.ico} /></span>
                <h4>{f.title}</h4>
                <p>{f.body}</p>
              </div>
            ))}
          </div>
        )}
        <div className="actions">
          <div className="dots">
            {TUTORIAL_STEPS.map((_, i) => <i key={i} className={i === step ? 'on' : ''} />)}
          </div>
          <div className="right-actions">
            <button className="btn-secondary" onClick={onSkip}>Skip</button>
            {step > 0 && <button className="btn-secondary" onClick={() => setStep(step - 1)}>Back</button>}
            {!isLast && <button className="btn-primary" onClick={() => setStep(step + 1)}>Next</button>}
            {isLast && <button className="btn-primary" onClick={onDone}>Get started</button>}
          </div>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { SourcesPanel, MoodDiaryPanel, Tutorial });

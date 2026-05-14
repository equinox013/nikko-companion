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

// ── Composer ──────────────────────────────────────────────────────
function Composer({ onSend, disabled }) {
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
    if (!t || disabled) return;
    onSend(t); setVal('');
  };
  return (
    <div>
      <div className="composer">
        <textarea
          ref={ref}
          value={val}
          onChange={(e) => setVal(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(); } }}
          placeholder="Take your time…"
          rows={1}
          aria-label="Message Nikko"
        />
        <button className="send" onClick={submit} disabled={!val.trim() || disabled} aria-label="Send message">
          <svg viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
            <path d="M2 7h10" /><path d="m8 3 4 4-4 4" />
          </svg>
        </button>
      </div>
      <div className="composer-foot">
        <span><span className="kbd">Enter</span> to send · <span className="kbd">Shift</span>+<span className="kbd">Enter</span> for newline · type <span className="kbd">/help</span> for the tutorial</span>
        <span>Cleared on refresh</span>
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

// ── Chat root ─────────────────────────────────────────────────────
function Chat({ theme, onToggleTheme }) {
  const [messages, setMessages] = useState([
    { id: 'open', role: 'assistant', text: NIKKO_OPENING.text, emotion: NIKKO_OPENING.emotion, streaming: false }
  ]);
  const [streaming, setStreaming] = useState(false);
  const [currentEmotion, setCurrentEmotion] = useState('calm');
  const [safetyVisible, setSafetyVisible] = useState(false);
  const [activeCite, setActiveCite] = useState(null);
  const [leftTab, setLeftTab] = useState(null);   // 'mood' | null
  const [rightTab, setRightTab] = useState(null); // 'sources' | null
  const sourceOrderRef = useRef({});
  const [, forceRerender] = useState(0);
  const threadRef = useRef(null);

  // Stable session ID for this Gate entry (REQ-FIS-SM1).
  // Generated once on mount; passed to every /api/message call.
  const contextID = React.useMemo(() => {
    const bytes = crypto.getRandomValues(new Uint8Array(6));
    const hex = Array.from(bytes).map(b => b.toString(16).padStart(2, '0')).join('');
    return `nikko-${Date.now()}-${hex}`;
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

  // USM memory state
  const [memOpen, setMemOpen] = useState(false);   // generate modal
  const [loadOpen, setLoadOpen] = useState(false); // load modal
  const [memLoaded, setMemLoaded] = useState(false);
  const [memName, setMemName] = useState('');
  const [memPop, setMemPop] = useState(false);     // popover

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

  // Welcome-back assistant message when memory loads
  const onMemoryLoaded = useCallback((name) => {
    setMemLoaded(true);
    setMemName(name);
    setMessages(prev => [...prev, {
      id: 'wb-' + Date.now(),
      role: 'assistant',
      emotion: 'care',
      streaming: false,
      text: "Welcome back. Your memory file is loaded — I'll keep what's there in mind, but the live conversation is what I'll really listen to. You're in charge of what stays."
    }]);
    setTimeout(scrollToBottom, 30);
  }, [scrollToBottom]);

  // Mood diary state — sessionStorage so it doesn't outlive the tab,
  // honouring SPEC-800 zero-retention. (Memory file is the durable channel.)
  const [moodEntries, setMoodEntries] = useState(() => {
    try {
      const raw = sessionStorage.getItem('nikko.mood');
      return raw ? JSON.parse(raw) : {};
    } catch (e) { return {}; }
  });
  useEffect(() => {
    try { sessionStorage.setItem('nikko.mood', JSON.stringify(moodEntries)); } catch (e) {}
  }, [moodEntries]);
  const setMoodEntry = (iso, val) => {
    setMoodEntries(prev => {
      const next = { ...prev };
      if (val === null) delete next[iso]; else next[iso] = val;
      return next;
    });
  };

  // Cite click → open sources panel
  const onCiteClick = useCallback((k) => {
    setActiveCite(k);
    setRightTab('sources');
  }, []);

  // ── streamReply: POST /api/message → SSE → char-by-char animation ──
  // [REQ-FIS-001] Primary chat endpoint. Streams SSE from the Render backend
  // (which orchestrates ADP-B → ADP-A → ADP-C on the HF Space).
  // Falls back to matchNikkoPattern() if the backend is unreachable so the
  // frontend never goes blank during Render cold-start or network errors.
  const streamReply = useCallback(async (userText) => {
    setStreaming(true);
    const id = 'm-' + Date.now();
    setMessages(prev => [...prev, { id, role: 'assistant', text: '', emotion: 'listen', streaming: true, traceId: id }]);
    scrollToBottom();
    setCurrentEmotion('think');

    // [CONCEPT] SSE (Server-Sent Events): a unidirectional HTTP stream where
    // the server pushes events as "event: <name>\ndata: <json>\n\n" blocks.
    // We read it with fetch() + ReadableStream instead of EventSource because
    // EventSource doesn't support POST requests.
    try {
      const response = await fetch(`${BACKEND_URL}/api/message`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: userText, contextID }),
      });

      if (!response.ok) throw new Error(`HTTP ${response.status}`);

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
              setCurrentEmotion(data.emotion || 'listen');

            } else if (currentEvent === 'chunk') {
              // Safety flag check — show banner if crisis detected.
              if (data.safetyFlags?.includes('crisis_detected')) setSafetyVisible(true);

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
              } else {
                // Empty text chunk = emotion-state signal only (e.g. "think").
                setCurrentEmotion(data.emotion || 'think');
              }

            } else if (currentEvent === 'message_end') {
              if (data.safetyFlags?.includes('crisis_detected')) setSafetyVisible(true);
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
      console.warn('[Nikko] Backend unavailable — using local fallback:', err.message);
      const pattern = matchNikkoPattern(userText);
      if (pattern.safety) setSafetyVisible(true);
      const trace = buildAgentTrace(id, userText, pattern);
      NikkoAgentLog.add(trace);
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
  }, [scrollToBottom, contextID]);

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

  return (
    <div className="app">
      <header className="topbar floating">
        {/* Left pillbar — brand + research preview */}
        <div className="pillbar">
          <div className="brand-mini">
            <span
              className={`debug-trigger ${debugGesture.holding ? 'holding' : ''}`}
              {...debugGesture.handlers}
              aria-hidden="true"
            >
              <NikkoAvatar emotion={liveEmotion} size={34} />
            </span>
            <span className="wordmark">Nikko</span>
          </div>
          <div className="divider" />
          <div className="tip-host">
            <span className="pill linklike" tabIndex={0}>
              <span className="dot" />Research preview
            </span>
            <div className="tip" role="tooltip">
              Nikko is an open research preview — non-diagnostic, not a clinician,
              implementation publicly visible at{' '}
              <a href="https://github.com/nikko-research/nikko" target="_blank" rel="noopener noreferrer">
                github.com/nikko-research/nikko
              </a>.
            </div>
          </div>
          {memLoaded && (
            <>
              <div className="divider" />
              <span className="mem-indicator" title={memName ? `Memory: ${memName}` : 'Memory active'}>
                <span className="pulse" />Memory active
              </span>
            </>
          )}
        </div>

        {/* Right pillbar — memory · theme · quick exit */}
        <div className="pillbar">
          <div className="mem-pop-host" style={{ position: 'relative' }}>
            <button className={`ghostbtn ${memLoaded ? 'active' : ''}`}
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
                <div className={`status ${memLoaded ? 'on' : ''}`}>
                  <span className="dot" />
                  {memLoaded
                    ? (memName ? `Loaded · ${memName.length > 24 ? memName.slice(0, 22) + '…' : memName}` : 'Loaded')
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
                  aria-label={`Switch to ${theme === 'light' ? 'dark' : 'light'} mode`}
                  title={`Switch to ${theme === 'light' ? 'dark' : 'light'} mode`}>
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
          <button className="tab-float right" onClick={() => setRightTab('sources')} title="Sources">
            Sources
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 2.5h7l2.5 2.5v8.5H3z" />
              <path d="M3 5.5h6M3 8h7M3 10.5h5" />
            </svg>
          </button>
        )}

        {leftTab === 'mood' && (
          <MoodDiaryPanel entries={moodEntries} onSet={setMoodEntry} onClose={() => setLeftTab(null)} />
        )}

        <div className="thread-wrap">
          <div className="thread" ref={threadRef}>
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
                  <div className="msg assistant" key={m.id}>
                    <div className="avatar-slot">
                      <NikkoAvatar emotion={m.emotion || 'calm'} size={42} />
                    </div>
                    <div className="body">
                      {m.traceId && !m.streaming && <AgentRibbon traceId={m.traceId} />}
                      {m.text === '' && m.streaming ? (
                        <div className="bubble thinking-bubble" aria-label="Nikko is thinking" role="status">
                          <span className="t-dot" />
                          <span className="t-dot" />
                          <span className="t-dot" />
                        </div>
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
                      {idx === 0 && showSuggestions && (
                        <div className="suggest-row">
                          {NIKKO_SUGGESTIONS.map(s => (
                            <button key={s} className="suggest" onClick={() => onSend(s)}>{s}</button>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="composer-wrap">
            <div className="composer-inner">
              {safetyVisible && <SafetyBanner onDismiss={() => setSafetyVisible(false)} />}
              <Composer onSend={onSend} disabled={streaming} />
              {/* G-UI-01: persistent AI disclaimer — always              {safetyVisible && <SafetyBanner onDismiss={() => setSafetyVisible(false)} />}
              <Composer onSend={onSend} disabled={streaming} />
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
          />
        )}
      </main>

      {/* Memory modals */}
      {memOpen && (
        <MemoryGenerateModal
          open={memOpen}
          onClose={() => setMemOpen(false)}
          onCreated={() => setMemOpen(false)}
        />
      )}
      {loadOpen && (
        <MemoryLoadModal
          open={loadOpen}
          onClose={() => setLoadOpen(false)}
          onLoaded={(name) => { setLoadOpen(false); onMemoryLoaded(name); }}
        />
      )}

      {/* First-run tutorial */}
      <Tutorial open={tutorialOpen} onSkip={closeTutorial} onDone={closeTutorial} />

      {/* Agent debug overlay — gesture-gated: 2-click then 3s hold on avatar */}
      <AgentDebugOverlay open={debugOpen} onClose={() => setDebugOpen(false)} />
    </div>
  );
}

Object.assign(window, { Chat });

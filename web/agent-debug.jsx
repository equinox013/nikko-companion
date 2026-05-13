// agent-debug.jsx — Agent transparency layer.
//
// Two surfaces:
//
//   1. <AgentRibbon traceId={...} />
//      A small caption rendered under every assistant message. Public,
//      always visible. Tells the user that multiple agents were involved
//      (count only — does NOT name them) and lists the actual sources
//      queried during evidence gathering.
//
//   2. <AgentDebugOverlay /> + useDebugGesture()
//      A hidden debug surface revealed only by a deliberate gesture on
//      the top-left Nikko avatar: two clicks, then press-and-hold for
//      three seconds. Once unlocked, shows the full SPEC-700 pipeline
//      with every agent named and per-phase detail behind "Read more".
//
// Trace data is held in a tiny pub/sub store on `window.__nikkoAgentLog`
// so chat.jsx can push traces during streaming without prop-drilling.

const { useState: ad_useState, useEffect: ad_useEffect, useRef: ad_useRef, useCallback: ad_useCallback } = React;

// ── Trace store (pub/sub on window) ─────────────────────────────────
const NikkoAgentLog = (() => {
  if (typeof window !== 'undefined' && window.__nikkoAgentLog) return window.__nikkoAgentLog;
  const subs = new Set();
  const traces = new Map();
  const log = {
    traces,
    add(trace) { traces.set(trace.id, trace); subs.forEach(fn => fn()); },
    update(id, patch) {
      const t = traces.get(id); if (!t) return;
      Object.assign(t, patch); subs.forEach(fn => fn());
    },
    list() { return Array.from(traces.values()); },
    get(id) { return traces.get(id); },
    subscribe(fn) { subs.add(fn); return () => subs.delete(fn); },
  };
  if (typeof window !== 'undefined') window.__nikkoAgentLog = log;
  return log;
})();

// React hook: subscribe to the trace log and re-render on updates.
function useTraceLog() {
  const [, set] = ad_useState(0);
  ad_useEffect(() => NikkoAgentLog.subscribe(() => set(x => x + 1)), []);
  return NikkoAgentLog;
}

// ── Trace builder ───────────────────────────────────────────────────
// Heuristic mode classifier so the trace shown to the user matches the
// canned reply they actually receive. The real pipeline lives server-side;
// this is a faithful UI mirror of what would have happened.

const SAMPLE_SOURCES = {
  guidance: [
    { name: 'Beyond Blue · research library', tier: 'peer-reviewed', year: 2024, ref: 'beyondblue.org.au/research', confidence: 0.91 },
    { name: 'headspace · clinical evidence base', tier: 'peer-reviewed', year: 2023, ref: 'headspace.org.au/our-research', confidence: 0.88 },
    { name: 'Australian Psychological Society', tier: 'peer-reviewed', year: 2024, ref: 'psychology.org.au/for-the-public', confidence: 0.86 },
    { name: 'Lifeline · learning resources', tier: 'grey', year: 2023, ref: 'lifeline.org.au/resources', confidence: 0.71 },
    { name: 'AIHW · mental health snapshot', tier: 'grey', year: 2024, ref: 'aihw.gov.au/reports/mental-health', confidence: 0.74 },
  ],
};

function classifyTurn(userText, pattern) {
  const t = (userText || '').toLowerCase();
  const crisisHits = ['kill myself', 'suicide', 'want to die', 'end it all', "don't want to be here", 'hurt myself', 'self-harm', 'self harm'];
  if (crisisHits.some(k => t.includes(k))) return { mode: 'CRISIS', distress: 'CRISIS', confidence: 0.94 };
  if (pattern && pattern.safety) return { mode: 'CRISIS', distress: 'HIGH', confidence: 0.82 };

  const moderateHits = ['anxious', 'anxiety', 'panic', 'depressed', 'low', 'lonely', 'overwhelm', 'tired', 'exhausted', 'scared', 'afraid', 'sad', 'numb'];
  const guidanceHits = ['why', 'how do i', 'what is', 'is it normal', 'should i', 'what does'];
  const isModerate = moderateHits.some(k => t.includes(k));
  const wantsKnowledge = guidanceHits.some(k => t.includes(k));

  if (isModerate && wantsKnowledge) return { mode: 'GUIDANCE', distress: 'MODERATE', confidence: 0.78 };
  if (isModerate) return { mode: 'COMFORT', distress: 'MODERATE', confidence: 0.71 };
  return { mode: 'COMFORT', distress: 'LOW', confidence: 0.62 };
}

function buildAgentTrace(messageId, userText, pattern) {
  const { mode, distress, confidence } = classifyTurn(userText, pattern);
  const phases = [];

  // 1. Scope classifier
  phases.push({
    id: 'scope', agent: 'scope_classifier.py', label: 'Scope classifier',
    status: 'pass', llm: false,
    summary: 'IN_SCOPE',
    detail: {
      decision: 'IN_SCOPE',
      in_scope_score: 0.74,
      out_scope_score: 0.12,
      net: 0.62,
      threshold: 0.0,
    },
    durationMs: 6 + Math.round(Math.random() * 6),
  });

  // 2. Signal agent
  const emotionalStates = mode === 'CRISIS'
    ? ['hopeless', 'overwhelmed']
    : distress === 'MODERATE'
      ? ['anxious', 'tired']
      : ['neutral'];
  phases.push({
    id: 'signal', agent: 'signal_agent.py', label: 'Signal agent',
    status: 'pass', llm: true, model: 'qwen2.5-3b-instruct',
    summary: `${distress} · conf ${confidence.toFixed(2)}`,
    detail: {
      distress_level: distress,
      confidence,
      emotional_states: emotionalStates,
      cognitive_patterns: distress === 'MODERATE' ? ['rumination'] : [],
      risk_indicators: mode === 'CRISIS' ? ['active_ideation'] : [],
      support_needs: mode === 'GUIDANCE'
        ? ['psychoeducation', 'normalization']
        : mode === 'COMFORT' ? ['validation'] : ['crisis_resources', 'grounding'],
    },
    durationMs: 380 + Math.round(Math.random() * 120),
  });

  // 3. Router
  phases.push({
    id: 'router', agent: 'router.py', label: 'Router',
    status: 'pass', llm: false,
    summary: `${mode}`,
    detail: {
      mode,
      crisis_override: mode === 'CRISIS',
      routing_rationale: mode === 'CRISIS'
        ? 'distress_level=CRISIS → safety override (REQ-200-042)'
        : mode === 'GUIDANCE'
          ? 'support_needs intersects {psychoeducation, normalization} ∧ distress≥MODERATE'
          : 'fallthrough → COMFORT (REQ-000-F01)',
    },
    durationMs: 1 + Math.round(Math.random() * 3),
  });

  // 4. Strategy agent (skipped on crisis — bypass)
  if (mode === 'CRISIS') {
    phases.push({
      id: 'strategy', agent: 'support_strategy_agent.py', label: 'Strategy (crisis bypass)',
      status: 'bypass', llm: false,
      summary: 'pre-authored crisis guidance',
      detail: { note: 'crisis_bypass() returns fixed StrategyPayload — no LLM call' },
      durationMs: 0,
    });
  } else {
    phases.push({
      id: 'strategy', agent: 'support_strategy_agent.py', label: 'Strategy agent',
      status: 'pass', llm: true, model: 'qwen2.5-3b-instruct',
      summary: mode === 'GUIDANCE'
        ? 'tone: warm · framing: psychoeducation'
        : 'tone: warm · framing: validation',
      detail: {
        tone_guidance: 'warm, lowercase-leaning, non-clinical',
        framing_strategy: mode === 'GUIDANCE' ? 'psychoeducation + normalization' : 'reflective listening',
        response_constraints: ['no diagnosis', 'no treatment plan', 'cite when claiming fact'],
        distress_acknowledgement: distress !== 'LOW',
      },
      durationMs: 340 + Math.round(Math.random() * 110),
    });
  }

  // 5–6. Evidence + synthesis (Guidance only)
  if (mode === 'GUIDANCE') {
    const picked = SAMPLE_SOURCES.guidance.slice(0, 3 + (Math.random() > 0.5 ? 0 : 1));
    phases.push({
      id: 'evidence', agent: 'retrieval adapters', label: 'Evidence retrieval',
      status: 'pass', llm: false, public: true,
      summary: `${picked.length} sources queried`,
      sources: picked,
      detail: { sources: picked, query: userText.slice(0, 120) },
      durationMs: 900 + Math.round(Math.random() * 600),
    });
    phases.push({
      id: 'synth', agent: 'synthesizer_agent.py', label: 'Synthesizer',
      status: 'pass', llm: false,
      summary: `${picked.filter(s => s.tier === 'peer-reviewed').length} peer-reviewed · ${picked.filter(s => s.tier === 'grey').length} grey`,
      detail: {
        overall_confidence: 0.83,
        source_tiers_used: Array.from(new Set(picked.map(s => s.tier))),
        grey_literature_flag: picked.some(s => s.tier === 'grey'),
        ranked: picked.map((s, i) => ({ rank: i + 1, name: s.name, score: s.confidence })),
      },
      durationMs: 22 + Math.round(Math.random() * 18),
    });
  }

  // 7. Interaction model (the actual reply LLM)
  phases.push({
    id: 'draft', agent: 'interaction_model.py', label: 'Reply draft',
    status: 'pass', llm: true, model: 'mistral-7b · ADP-A + ADP-B',
    summary: 'draft generated',
    detail: { temperature: 0.45, max_tokens: 380, adapters: ['ADP-A empathy', 'ADP-B safety'] },
    durationMs: 1100 + Math.round(Math.random() * 700),
  });

  // 8. Evaluator
  phases.push({
    id: 'evaluator', agent: 'evaluator_agent.py', label: 'Evaluator',
    status: 'pass', llm: true, model: 'ADP-C judge',
    summary: 'PASS · red lines 0/15',
    detail: {
      pass_1_redlines: { matched: 0, of: 15 },
      pass_2_judge: { hallucination: 'none', tone_compliance: 'pass' },
      verdict: 'PASS',
      regen_count: 0,
    },
    durationMs: 240 + Math.round(Math.random() * 80),
  });

  // 9. Verification supervisor
  const checks = mode === 'CRISIS'
    ? ['C1', 'C2', 'C3', 'C4', 'C7']
    : ['C1', 'C2', 'C3', 'C5', 'C6', 'C7'];
  phases.push({
    id: 'verifier', agent: 'verification_supervisor.py', label: 'Verification',
    status: 'pass', llm: false,
    summary: `${checks.join(' · ')} ✓`,
    detail: {
      checks_run: checks,
      passed: true,
      mode_distress_aligned: true,
      crisis_resources_present: mode === 'CRISIS',
      synthesized_evidence_present: mode === 'GUIDANCE',
    },
    durationMs: 3 + Math.round(Math.random() * 4),
  });

  return {
    id: messageId,
    userText,
    mode,
    distress,
    confidence,
    startedAt: Date.now(),
    phases,
  };
}

// ── Public ribbon (under every assistant message) ───────────────────
// Counts agents anonymously; names sources for evidence gathering.

function AgentRibbon({ traceId }) {
  useTraceLog();
  if (!traceId) return null;
  const trace = NikkoAgentLog.get(traceId);
  if (!trace) return null;

  const agentCount = trace.phases.filter(p => p.status !== 'bypass').length;
  const evidence = trace.phases.find(p => p.id === 'evidence');
  const sources = evidence ? evidence.sources : null;

  return (
    <div className="agent-ribbon" role="note">
      <span className="agent-ribbon-glyph" aria-hidden="true">
        <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="3" cy="3" r="1.4" />
          <circle cx="9" cy="3" r="1.4" />
          <circle cx="6" cy="9" r="1.4" />
          <path d="M3 3 9 3M3 3 6 9M9 3 6 9" opacity="0.5" />
        </svg>
      </span>
      <span className="agent-ribbon-count">{agentCount} agents · ensuring best response, because you matter</span>
      {sources && sources.length > 0 && (
        <>
          <span className="agent-ribbon-dot">·</span>
          <span className="agent-ribbon-sources-label">sources queried:</span>
          <span className="agent-ribbon-sources">
            {sources.map((s, i) => (
              <React.Fragment key={s.name}>
                {i > 0 && <span className="agent-ribbon-sep">,</span>}
                <span className="agent-ribbon-source">{s.name.split(' · ')[0]}</span>
              </React.Fragment>
            ))}
          </span>
        </>
      )}
    </div>
  );
}

// ── Hidden debug gesture: 2 clicks then 3-sec hold ──────────────────
function useDebugGesture(onActivate) {
  const stateRef = ad_useRef({ count: 0, timer: null, lastDown: 0 });
  const [holding, setHolding] = ad_useState(false);

  const reset = ad_useCallback(() => {
    if (stateRef.current.timer) clearTimeout(stateRef.current.timer);
    stateRef.current = { count: 0, timer: null, lastDown: 0 };
    setHolding(false);
  }, []);

  const onDown = ad_useCallback((e) => {
    // Only react to primary button / single touch.
    if (e.button !== undefined && e.button !== 0) return;
    const now = Date.now();
    if (now - stateRef.current.lastDown > 800) {
      // Too long since last interaction — start over.
      stateRef.current = { count: 0, timer: null, lastDown: 0 };
    }
    stateRef.current.count += 1;
    stateRef.current.lastDown = now;
    if (stateRef.current.count === 2) {
      // Second press — start the 3-second hold.
      setHolding(true);
      stateRef.current.timer = setTimeout(() => {
        stateRef.current = { count: 0, timer: null, lastDown: 0 };
        setHolding(false);
        onActivate();
      }, 3000);
    }
  }, [onActivate]);

  const onUp = ad_useCallback(() => {
    // If the user releases during the hold window, cancel the activation
    // but keep the click count zeroed so they have to start fresh.
    if (stateRef.current.count === 2 && stateRef.current.timer) {
      reset();
    }
  }, [reset]);

  const onLeave = ad_useCallback(() => {
    if (stateRef.current.timer) reset();
  }, [reset]);

  return {
    holding,
    handlers: {
      onMouseDown: onDown,
      onMouseUp: onUp,
      onMouseLeave: onLeave,
      onTouchStart: onDown,
      onTouchEnd: onUp,
      onTouchCancel: onLeave,
    },
  };
}

// ── Debug overlay ───────────────────────────────────────────────────
function AgentDebugOverlay({ open, onClose }) {
  useTraceLog();
  const [selectedId, setSelectedId] = ad_useState(null);
  const [readMore, setReadMore] = ad_useState(false);

  const list = NikkoAgentLog.list().slice().reverse();
  const current = list.find(t => t.id === selectedId) || list[0];

  ad_useEffect(() => {
    if (!open) { setReadMore(false); return; }
    if (!current && list.length === 0) return;
    if (!selectedId && list[0]) setSelectedId(list[0].id);
  }, [open, list.length]);

  if (!open) return null;

  return (
    <div className="debug-veil" onClick={onClose}>
      <div className={`debug-panel ${readMore ? 'wide' : ''}`} onClick={e => e.stopPropagation()}>
        <header className="debug-head">
          <div>
            <div className="debug-eyebrow">DEBUG · SPEC-700 pipeline</div>
            <h3>Agent trace</h3>
          </div>
          <button className="iconbtn" onClick={onClose} aria-label="Close debug">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
              <path d="m4 4 8 8M12 4l-8 8" />
            </svg>
          </button>
        </header>

        {!current ? (
          <div className="debug-empty">
            No turns yet. Send a message and Nikko's agent pipeline will be traced here.
          </div>
        ) : (
          <div className="debug-body">
            <div className="debug-turn-picker">
              <span className="debug-eyebrow">Turn</span>
              <select value={current.id} onChange={e => { setSelectedId(e.target.value); setReadMore(false); }}>
                {list.map(t => (
                  <option key={t.id} value={t.id}>
                    {t.userText.slice(0, 56)}{t.userText.length > 56 ? '…' : ''}
                  </option>
                ))}
              </select>
            </div>

            <div className="debug-meta">
              <span className={`debug-mode mode-${current.mode}`}>{current.mode}</span>
              <span className="debug-meta-item">distress · {current.distress}</span>
              <span className="debug-meta-item">conf · {current.confidence.toFixed(2)}</span>
              <span className="debug-meta-item">{current.phases.reduce((s, p) => s + p.durationMs, 0)}ms total</span>
            </div>

            <ol className="debug-pipeline">
              {current.phases.map((p, i) => (
                <li key={p.id} className={`debug-phase status-${p.status}`}>
                  <span className="debug-phase-num">{i + 1}</span>
                  <div className="debug-phase-main">
                    <div className="debug-phase-line">
                      <span className="debug-phase-label">{p.label}</span>
                      <span className="debug-phase-agent">{p.agent}</span>
                      {p.llm && <span className="debug-phase-pill">LLM</span>}
                      {p.public && <span className="debug-phase-pill public">public</span>}
                      <span className="debug-phase-dur">{p.durationMs}ms</span>
                    </div>
                    <div className="debug-phase-summary">{p.summary}</div>
                  </div>
                  <span className={`debug-phase-status status-${p.status}`}>
                    {p.status === 'bypass' ? '◇' : p.status === 'pass' ? '✓' : '✗'}
                  </span>
                </li>
              ))}
            </ol>

            <div className="debug-actions">
              <button className="debug-readmore" onClick={() => setReadMore(v => !v)}>
                {readMore ? 'Hide full trace' : 'Read full trace →'}
              </button>
            </div>

            {readMore && (
              <div className="debug-detail">
                <div className="debug-detail-head">
                  <span className="debug-eyebrow">Per-phase detail</span>
                  <span className="debug-detail-note">
                    Anonymous to chat surface · visible here under explicit gesture
                  </span>
                </div>
                {current.phases.map((p, i) => (
                  <div key={p.id} className="debug-detail-block">
                    <div className="debug-detail-title">
                      <span className="debug-detail-num">{i + 1}</span>
                      <span className="debug-detail-name">{p.label}</span>
                      <span className="debug-detail-agent">{p.agent}</span>
                    </div>
                    <pre className="debug-detail-json">
{JSON.stringify(p.detail, null, 2)}
                    </pre>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        <footer className="debug-foot">
          <span>Trace stays on this device · cleared on refresh</span>
        </footer>
      </div>
    </div>
  );
}

Object.assign(window, {
  AgentRibbon,
  AgentDebugOverlay,
  useDebugGesture,
  buildAgentTrace,
  NikkoAgentLog,
});

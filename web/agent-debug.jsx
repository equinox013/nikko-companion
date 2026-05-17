// agent-debug.jsx — Pipeline transparency layer.
const { useState: ad_useState, useEffect: ad_useEffect, useRef: ad_useRef, useCallback: ad_useCallback } = React;

// ── Trace store ──────────────────────────────────────────────────────
const NikkoAgentLog = (() => {
  if (typeof window !== 'undefined' && window.__nikkoAgentLog) return window.__nikkoAgentLog;
  const subs = new Set();
  const traces = new Map();
  const log = {
    traces,
    add(trace) { traces.set(trace.id, trace); subs.forEach(fn => fn()); },
    update(id, patch) { const t = traces.get(id); if (!t) return; Object.assign(t, patch); subs.forEach(fn => fn()); },
    list() { return Array.from(traces.values()); },
    get(id) { return traces.get(id); },
    subscribe(fn) { subs.add(fn); return () => subs.delete(fn); },
  };
  if (typeof window !== 'undefined') window.__nikkoAgentLog = log;
  return log;
})();

function useTraceLog() {
  const [, set] = ad_useState(0);
  ad_useEffect(() => NikkoAgentLog.subscribe(() => set(x => x + 1)), []);
  return NikkoAgentLog;
}

// ── Fallback trace builder (backend unreachable) ─────────────────────
function classifyTurn(userText, pattern) {
  const t = (userText || '').toLowerCase();
  const crisis = ['kill myself','suicide','want to die','end it all',"don't want to be here",'hurt myself'];
  if (crisis.some(k => t.includes(k))) return { mode: 'CRISIS', distress: 'CRISIS' };
  if (pattern && pattern.safety) return { mode: 'CRISIS', distress: 'HIGH' };
  const moderate = ['anxious','anxiety','panic','depressed','low','lonely','overwhelm','tired','sad','numb'];
  if (moderate.some(k => t.includes(k))) return { mode: 'COMFORT', distress: 'MODERATE' };
  return { mode: 'COMFORT', distress: 'LOW' };
}

function buildAgentTrace(messageId, userText, pattern) {
  const { mode, distress } = classifyTurn(userText, pattern);
  return {
    id: messageId, userText, liveData: false,
    is_crisis: mode === 'CRISIS', flags: mode === 'CRISIS' ? ['crisis_detected'] : [],
    verdict: 'APPROVE', regen: false, elapsed: null,
    adp_b: { label: 'Safety / crisis check', verdict: mode === 'CRISIS' ? 'CRISIS' : 'CLEAR', flags: mode === 'CRISIS' ? ['crisis_detected'] : [] },
    adp_a: { label: 'Empathy response draft', chars: null },
    adp_c: { label: 'Quality gate (evaluator)', verdict: 'APPROVE', regen: false },
    _mode: mode, _distress: distress,
  };
}

// ── Public ribbon ────────────────────────────────────────────────────
function AgentRibbon({ traceId }) {
  useTraceLog();
  if (!traceId) return null;
  const trace = NikkoAgentLog.get(traceId);
  if (!trace) return null;
  return (
    <div className="agent-ribbon" role="note">
      <span className="agent-ribbon-glyph" aria-hidden="true">
        <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="3" cy="3" r="1.4"/><circle cx="9" cy="3" r="1.4"/><circle cx="6" cy="9" r="1.4"/>
          <path d="M3 3 9 3M3 3 6 9M9 3 6 9" opacity="0.5"/>
        </svg>
      </span>
      <span className="agent-ribbon-count">3 adapters</span>
    </div>
  );
}

// ── Debug gesture: 2 clicks then 3-sec hold ──────────────────────────
function useDebugGesture(onActivate) {
  const stateRef = ad_useRef({ count: 0, timer: null, lastDown: 0 });
  const [holding, setHolding] = ad_useState(false);
  const reset = ad_useCallback(() => {
    if (stateRef.current.timer) clearTimeout(stateRef.current.timer);
    stateRef.current = { count: 0, timer: null, lastDown: 0 };
    setHolding(false);
  }, []);
  const onDown = ad_useCallback((e) => {
    if (e.button !== undefined && e.button !== 0) return;
    const now = Date.now();
    if (now - stateRef.current.lastDown > 800) stateRef.current = { count: 0, timer: null, lastDown: 0 };
    stateRef.current.count += 1;
    stateRef.current.lastDown = now;
    if (stateRef.current.count === 2) {
      setHolding(true);
      stateRef.current.timer = setTimeout(() => {
        stateRef.current = { count: 0, timer: null, lastDown: 0 };
        setHolding(false);
        onActivate();
      }, 3000);
    }
  }, [onActivate]);
  const onUp = ad_useCallback(() => { if (stateRef.current.count === 2 && stateRef.current.timer) reset(); }, [reset]);
  const onLeave = ad_useCallback(() => { if (stateRef.current.timer) reset(); }, [reset]);
  return { holding, handlers: { onMouseDown: onDown, onMouseUp: onUp, onMouseLeave: onLeave, onTouchStart: onDown, onTouchEnd: onUp, onTouchCancel: onLeave } };
}

// ── Adapter card ──────────────────────────────────────────────────────
function AdapterCard({ step, name, role, verdict, detail, running }) {
  const verdictColor =
    verdict === 'CRISIS'    ? 'var(--rose, #e05)' :
    verdict === 'BYPASSED'  ? 'var(--ink-2)' :
    verdict === 'APPROVE' || verdict === 'CLEAR' || verdict === 'GENERATED' ? 'var(--sage, #2a7)' :
    verdict === 'REGENERATE' ? 'var(--sun, #e90)' : 'var(--ink-2)';
  return (
    <div className="adp-card">
      <div className="adp-card-step">{step}</div>
      <div className="adp-card-body">
        <div className="adp-card-head">
          <span className="adp-card-name">{name}</span>
          <span className="adp-card-role">{role}</span>
        </div>
        {running ? (
          <div className="adp-card-running">
            <span className="t-dot" style={{width:5,height:5}}/>
            <span className="t-dot" style={{width:5,height:5,animationDelay:'0.18s'}}/>
            <span className="t-dot" style={{width:5,height:5,animationDelay:'0.36s'}}/>
            <span style={{fontSize:'0.72rem',color:'var(--ink-2)',marginLeft:6}}>running…</span>
          </div>
        ) : (
          <div className="adp-card-result">
            {verdict && <span className="adp-card-verdict" style={{color: verdictColor}}>{verdict}</span>}
            {detail && <span className="adp-card-detail">{detail}</span>}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Debug overlay ─────────────────────────────────────────────────────
function AgentDebugOverlay({ open, onClose }) {
  useTraceLog();
  const [selectedId, setSelectedId] = ad_useState(null);
  const list = NikkoAgentLog.list().slice().reverse();
  const current = list.find(t => t.id === selectedId) || list[0];
  ad_useEffect(() => {
    if (!open) return;
    if (!selectedId && list[0]) setSelectedId(list[0].id);
  }, [open, list.length]);
  if (!open) return null;

  return (
    <div className="debug-veil" onClick={onClose}>
      <div className="debug-panel" onClick={e => e.stopPropagation()}>
        <header className="debug-head">
          <div>
            <div className="debug-eyebrow">Pipeline trace</div>
            <h3>Nikko adapters</h3>
          </div>
          <button className="iconbtn" onClick={onClose} aria-label="Close">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
              <path d="m4 4 8 8M12 4l-8 8"/>
            </svg>
          </button>
        </header>

        {!current ? (
          <div className="debug-empty">
            Send a message and adapter results will appear here.
          </div>
        ) : (
          <div className="debug-body">
            <div className="debug-turn-picker">
              <span className="debug-eyebrow">Turn</span>
              <select value={current.id} onChange={e => setSelectedId(e.target.value)}>
                {list.map(t => (
                  <option key={t.id} value={t.id}>
                    {(t.userText||'').slice(0,56)}{(t.userText||'').length > 56 ? '…' : ''}
                  </option>
                ))}
              </select>
            </div>

            <div className="debug-meta">
              <span className={`debug-mode mode-${current.is_crisis ? 'CRISIS' : 'COMFORT'}`}>
                {current.is_crisis ? 'CRISIS' : 'COMFORT'}
              </span>
              {current.liveData
                ? <span className="debug-meta-pill live">● live data</span>
                : <span className="debug-meta-pill sim">simulated</span>}
              {current.elapsed ? <span className="debug-meta-item">{parseFloat(current.elapsed).toFixed(1)}s total</span> : null}
              {current.regen ? <span className="debug-meta-pill regen">regen triggered</span> : null}
            </div>

            <div className="adp-cards">
              <AdapterCard step="1" name="ADP-B" role="Gemma-2-2b-it · Safety / crisis"
                verdict={current.adp_b?.verdict}
                detail={current.adp_b?.flags?.length ? `flags: ${current.adp_b.flags.join(', ')}` : 'no flags'}
                running={false}
              />
              <AdapterCard step="2" name="ADP-A" role="Qwen3-4B · Empathy response"
                verdict={current.is_crisis ? 'BYPASSED' : 'GENERATED'}
                detail={current.adp_a?.chars ? `${current.adp_a.chars} chars` : null}
                running={false}
              />
              <AdapterCard step="3" name="ADP-C" role="Gemma-2-2b-it · Quality evaluator"
                verdict={current.adp_c?.verdict}
                detail={current.adp_c?.regen ? 'regen pass triggered' : null}
                running={false}
              />
            </div>

            <details className="debug-raw">
              <summary className="debug-raw-toggle">Raw pipeline payload</summary>
              <pre className="debug-detail-json">{JSON.stringify({
                is_crisis: current.is_crisis, flags: current.flags,
                verdict: current.verdict, regen: current.regen, elapsed: current.elapsed,
                adp_b: current.adp_b, adp_a: current.adp_a, adp_c: current.adp_c,
              }, null, 2)}</pre>
            </details>
          </div>
        )}

        <footer className="debug-foot">
          <span>Trace stays on this device · cleared on refresh</span>
        </footer>
      </div>
    </div>
  );
}

Object.assign(window, { AgentRibbon, AgentDebugOverlay, useDebugGesture, buildAgentTrace, NikkoAgentLog });
 NikkoAgentLog });

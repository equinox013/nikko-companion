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
// [REQ-FIS-RB4] buildAgentTrace produces a synthetic trace with the new
// pre_analysis / signal / router / evidence fields so the expanded overlay
// renders consistently whether data comes from the live pipeline or the
// local fallback.
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
    id: messageId, userText, liveData: false, _processing: false,
    is_crisis: mode === 'CRISIS', flags: mode === 'CRISIS' ? ['crisis_detected'] : [],
    verdict: 'APPROVE', regen: false, elapsed: null, _mode: mode,
    // New trace fields — fallback synthetic values for the expanded overlay cards.
    pre_analysis: { annotations: '' },
    signal: {
      distress_level: distress, confidence: null,
      emotional_states: [], cognitive_patterns: [],
      behavioral_indicators: [], risk_indicators: [],
      support_needs: [], uncertainty_notes: '',
    },
    router: { mode, confidence: null, crisis_override: mode === 'CRISIS' },
    evidence: { sources: [], adapters: 0 },
    adp_b: { label: 'Safety / crisis check', verdict: mode === 'CRISIS' ? 'CRISIS' : 'CLEAR', flags: mode === 'CRISIS' ? ['crisis_detected'] : [] },
    adp_a: { label: 'Empathy response draft', chars: null },
    adp_c: { label: 'Quality gate (evaluator)', verdict: 'APPROVE', regen: false },
  };
}

// ── Public ribbon ────────────────────────────────────────────────────
// [REQ-FIS-RB4] AgentRibbon shows pipeline stage during processing and
// the final mode label after completion.
//
// During processing (_processing=true): shows trace._stage (live stage label
// from keep-alive SSE chunks) in secondary typography.
// After completion: shows the operational mode ("guidance mode" / "comfort mode").
function AgentRibbon({ traceId }) {
  useTraceLog();
  if (!traceId) return null;
  const trace = NikkoAgentLog.get(traceId);
  if (!trace) return null;

  // ── Processing state: show live pipeline stage ─────────────────
  if (trace._processing) {
    return (
      <div className="agent-ribbon processing" role="note">
        <span className="agent-ribbon-glyph" aria-hidden="true">
          <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="3" cy="3" r="1.4"/><circle cx="9" cy="3" r="1.4"/><circle cx="6" cy="9" r="1.4"/>
            <path d="M3 3 9 3M3 3 6 9M9 3 6 9" opacity="0.5"/>
          </svg>
        </span>
        <span className="agent-ribbon-stage">{trace._stage || 'processing…'}</span>
      </div>
    );
  }

  // ── Completed state: show operational mode ──────────────────────
  const mode = trace._mode || (trace.is_crisis ? 'CRISIS' : 'COMFORT');
  const modeLabels = {
    GUIDANCE: 'guidance mode',
    CRISIS:   'crisis mode',
    COMFORT:  'comfort mode',
  };
  const modeLabel = modeLabels[mode] || 'comfort mode';

  return (
    <div className="agent-ribbon" role="note">
      <span className="agent-ribbon-glyph" aria-hidden="true">
        <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="3" cy="3" r="1.4"/><circle cx="9" cy="3" r="1.4"/><circle cx="6" cy="9" r="1.4"/>
          <path d="M3 3 9 3M3 3 6 9M9 3 6 9" opacity="0.5"/>
        </svg>
      </span>
      <span className="agent-ribbon-count">{modeLabel}</span>
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

// ── Analysis card (pre-analysis, signal, router) ─────────────────────
// A lighter card for the Qwen3 analysis preamble steps — no adapter label,
// no verdict badge, just a label and a brief value summary.
function AnalysisCard({ step, name, role, value, empty }) {
  return (
    <div className="adp-card adp-card--analysis">
      <div className="adp-card-step">{step}</div>
      <div className="adp-card-body">
        <div className="adp-card-head">
          <span className="adp-card-name">{name}</span>
          <span className="adp-card-role">{role}</span>
        </div>
        <div className="adp-card-result">
          {empty
            ? <span className="adp-card-detail" style={{fontStyle:'italic'}}>no signals</span>
            : <span className="adp-card-detail">{value}</span>}
        </div>
      </div>
    </div>
  );
}

// ── Debug overlay ─────────────────────────────────────────────────────
// [REQ-FIS-DB6] Expanded overlay now shows Pre-Analysis (Step 0.5),
// Signal (Step 1), and Router (Step 2) cards above the adapter cards.
// Mode badge shows live mode from trace._mode (COMFORT / GUIDANCE / CRISIS).
// Adapter steps renumbered to reflect the new pipeline execution order:
//   ADP-A (empathy) → Step 3
//   ADP-B (safety)  → Step 4
//   ADP-C (eval)    → Step 5
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
              {/* Mode badge driven by live trace._mode — handles COMFORT / GUIDANCE / CRISIS */}
              {(() => {
                const mode = current._mode || (current.is_crisis ? 'CRISIS' : 'COMFORT');
                return (
                  <span className={`debug-mode mode-${mode}`}>{mode}</span>
                );
              })()}
              {current.liveData
                ? <span className="debug-meta-pill live">● live data</span>
                : <span className="debug-meta-pill sim">simulated</span>}
              {current.elapsed ? <span className="debug-meta-item">{parseFloat(current.elapsed).toFixed(1)}s total</span> : null}
              {current.regen ? <span className="debug-meta-pill regen">regen triggered</span> : null}
            </div>

            <div className="adp-cards">
              {/* ── Pre-Analysis (Step 0.5) ─────────────────────────────
                  Qwen3-4B structural pre-analysis (SPEC-100 §16 / REQ-700-SA1).
                  Detects paralinguistic and structural signals before the adapter
                  stack runs. Shown even when empty to make the pipeline visible. */}
              <AnalysisCard
                step="0.5"
                name="Pre-Analysis"
                role="Qwen3-4B · Structural signals (SPEC-100 §16)"
                value={current.pre_analysis?.annotations || ''}
                empty={!current.pre_analysis?.annotations}
              />

              {/* ── Signal (Step 1) ─────────────────────────────────────
                  Combined rule-engine + LLM signal output.
                  Shows distress level and confidence from the signal object. */}
              <AnalysisCard
                step="1"
                name="Signal"
                role="Qwen3-4B · Distress / affect signal"
                value={(() => {
                  const s = current.signal;
                  if (!s) return 'no signal data';
                  const level = s.distress_level || 'UNKNOWN';
                  const conf  = s.confidence != null ? ` · conf ${(s.confidence * 100).toFixed(0)}%` : '';
                  const tone  = s.uncertainty_notes ? ` · ${s.uncertainty_notes.slice(0, 60)}` : '';
                  return `${level}${conf}${tone}`;
                })()}
                empty={!current.signal}
              />

              {/* ── Router (Step 2) ─────────────────────────────────────
                  Deterministic routing decision (COMFORT / GUIDANCE / CRISIS).
                  crisis_override=true means ADP-B forced the CRISIS path. */}
              <AnalysisCard
                step="2"
                name="Router"
                role="Rule-engine · Mode decision"
                value={(() => {
                  const r = current.router;
                  if (!r) return 'no router data';
                  const mode   = r.mode || 'COMFORT';
                  const conf   = r.confidence != null ? ` · conf ${(r.confidence * 100).toFixed(0)}%` : '';
                  const crisis = r.crisis_override ? ' · crisis override' : '';
                  return `${mode}${conf}${crisis}`;
                })()}
                empty={!current.router}
              />

              {/* ── ADP-A (Step 3) ───────────────────────────────────────
                  Qwen3-4B empathy response draft. Runs BEFORE ADP-B in the
                  reordered pipeline (Director-approved 2026-05-22). Draft is
                  discarded if ADP-B fires crisis=True. */}
              <AdapterCard step="3" name="ADP-A" role="Qwen3-4B · Empathy response"
                verdict={current.is_crisis ? 'BYPASSED' : 'GENERATED'}
                detail={current.adp_a?.chars ? `${current.adp_a.chars} chars` : null}
                running={false}
              />

              {/* ── ADP-B (Step 4) ───────────────────────────────────────
                  Gemma-2-2b-it safety classifier. Now runs AFTER ADP-A.
                  Receives pre-analysis annotations injected into its system prompt.
                  crisis=True discards the ADP-A draft and returns crisis resources. */}
              <AdapterCard step="4" name="ADP-B" role="Gemma-2-2b-it · Safety / crisis"
                verdict={current.adp_b?.verdict}
                detail={current.adp_b?.flags?.length ? `flags: ${current.adp_b.flags.join(', ')}` : 'no flags'}
                running={false}
              />

              {/* ── ADP-C (Step 5) ───────────────────────────────────────
                  Gemma-2-2b-it quality evaluator. APPROVE / REGENERATE verdict.
                  REGENERATE triggers a second ADP-A pass (regen=True). */}
              <AdapterCard step="5" name="ADP-C" role="Gemma-2-2b-it · Quality evaluator"
                verdict={current.adp_c?.verdict}
                detail={current.adp_c?.regen ? 'regen pass triggered' : null}
                running={false}
              />
            </div>

            <details className="debug-raw">
              <summary className="debug-raw-toggle">Raw pipeline payload</summary>
              <pre className="debug-detail-json">{JSON.stringify({
                mode: current._mode, is_crisis: current.is_crisis, flags: current.flags,
                verdict: current.verdict, regen: current.regen, elapsed: current.elapsed,
                pre_analysis: current.pre_analysis,
                signal: current.signal,
                router: current.router,
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

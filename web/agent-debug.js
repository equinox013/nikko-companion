const { useState: ad_useState, useEffect: ad_useEffect, useRef: ad_useRef, useCallback: ad_useCallback } = React;
const NikkoAgentLog = (() => {
  if (typeof window !== "undefined" && window.__nikkoAgentLog) return window.__nikkoAgentLog;
  const subs = /* @__PURE__ */ new Set();
  const traces = /* @__PURE__ */ new Map();
  const log = {
    traces,
    add(trace) {
      traces.set(trace.id, trace);
      subs.forEach((fn) => fn());
    },
    update(id, patch) {
      const t = traces.get(id);
      if (!t) return;
      Object.assign(t, patch);
      subs.forEach((fn) => fn());
    },
    list() {
      return Array.from(traces.values());
    },
    get(id) {
      return traces.get(id);
    },
    subscribe(fn) {
      subs.add(fn);
      return () => subs.delete(fn);
    }
  };
  if (typeof window !== "undefined") window.__nikkoAgentLog = log;
  return log;
})();
function useTraceLog() {
  const [, set] = ad_useState(0);
  ad_useEffect(() => NikkoAgentLog.subscribe(() => set((x) => x + 1)), []);
  return NikkoAgentLog;
}
function classifyTurn(userText, pattern) {
  const t = (userText || "").toLowerCase();
  const crisis = ["kill myself", "suicide", "want to die", "end it all", "don't want to be here", "hurt myself"];
  if (crisis.some((k) => t.includes(k))) return { mode: "CRISIS", distress: "CRISIS" };
  if (pattern && pattern.safety) return { mode: "CRISIS", distress: "HIGH" };
  const moderate = ["anxious", "anxiety", "panic", "depressed", "low", "lonely", "overwhelm", "tired", "sad", "numb"];
  if (moderate.some((k) => t.includes(k))) return { mode: "COMFORT", distress: "MODERATE" };
  return { mode: "COMFORT", distress: "LOW" };
}
function buildAgentTrace(messageId, userText, pattern) {
  const { mode, distress } = classifyTurn(userText, pattern);
  return {
    id: messageId,
    userText,
    liveData: false,
    is_crisis: mode === "CRISIS",
    flags: mode === "CRISIS" ? ["crisis_detected"] : [],
    verdict: "APPROVE",
    regen: false,
    elapsed: null,
    adp_b: { label: "Safety / crisis check", verdict: mode === "CRISIS" ? "CRISIS" : "CLEAR", flags: mode === "CRISIS" ? ["crisis_detected"] : [] },
    adp_a: { label: "Empathy response draft", chars: null },
    adp_c: { label: "Quality gate (evaluator)", verdict: "APPROVE", regen: false },
    _mode: mode,
    _distress: distress
  };
}
function AgentRibbon({ traceId }) {
  useTraceLog();
  if (!traceId) return null;
  const trace = NikkoAgentLog.get(traceId);
  if (!trace) return null;
  return /* @__PURE__ */ React.createElement("div", { className: "agent-ribbon", role: "note" }, /* @__PURE__ */ React.createElement("span", { className: "agent-ribbon-glyph", "aria-hidden": "true" }, /* @__PURE__ */ React.createElement("svg", { viewBox: "0 0 12 12", fill: "none", stroke: "currentColor", strokeWidth: "1.4", strokeLinecap: "round", strokeLinejoin: "round" }, /* @__PURE__ */ React.createElement("circle", { cx: "3", cy: "3", r: "1.4" }), /* @__PURE__ */ React.createElement("circle", { cx: "9", cy: "3", r: "1.4" }), /* @__PURE__ */ React.createElement("circle", { cx: "6", cy: "9", r: "1.4" }), /* @__PURE__ */ React.createElement("path", { d: "M3 3 9 3M3 3 6 9M9 3 6 9", opacity: "0.5" }))), /* @__PURE__ */ React.createElement("span", { className: "agent-ribbon-count" }, "3 adapters \xB7 ensuring best response, because you matter"));
}
function useDebugGesture(onActivate) {
  const stateRef = ad_useRef({ count: 0, timer: null, lastDown: 0 });
  const [holding, setHolding] = ad_useState(false);
  const reset = ad_useCallback(() => {
    if (stateRef.current.timer) clearTimeout(stateRef.current.timer);
    stateRef.current = { count: 0, timer: null, lastDown: 0 };
    setHolding(false);
  }, []);
  const onDown = ad_useCallback((e) => {
    if (e.button !== void 0 && e.button !== 0) return;
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
      }, 3e3);
    }
  }, [onActivate]);
  const onUp = ad_useCallback(() => {
    if (stateRef.current.count === 2 && stateRef.current.timer) reset();
  }, [reset]);
  const onLeave = ad_useCallback(() => {
    if (stateRef.current.timer) reset();
  }, [reset]);
  return { holding, handlers: { onMouseDown: onDown, onMouseUp: onUp, onMouseLeave: onLeave, onTouchStart: onDown, onTouchEnd: onUp, onTouchCancel: onLeave } };
}
function AdapterCard({ step, name, role, verdict, detail, running }) {
  const verdictColor = verdict === "CRISIS" ? "var(--rose, #e05)" : verdict === "BYPASSED" ? "var(--ink-2)" : verdict === "APPROVE" || verdict === "CLEAR" || verdict === "GENERATED" ? "var(--sage, #2a7)" : verdict === "REGENERATE" ? "var(--sun, #e90)" : "var(--ink-2)";
  return /* @__PURE__ */ React.createElement("div", { className: "adp-card" }, /* @__PURE__ */ React.createElement("div", { className: "adp-card-step" }, step), /* @__PURE__ */ React.createElement("div", { className: "adp-card-body" }, /* @__PURE__ */ React.createElement("div", { className: "adp-card-head" }, /* @__PURE__ */ React.createElement("span", { className: "adp-card-name" }, name), /* @__PURE__ */ React.createElement("span", { className: "adp-card-role" }, role)), running ? /* @__PURE__ */ React.createElement("div", { className: "adp-card-running" }, /* @__PURE__ */ React.createElement("span", { className: "t-dot", style: { width: 5, height: 5 } }), /* @__PURE__ */ React.createElement("span", { className: "t-dot", style: { width: 5, height: 5, animationDelay: "0.18s" } }), /* @__PURE__ */ React.createElement("span", { className: "t-dot", style: { width: 5, height: 5, animationDelay: "0.36s" } }), /* @__PURE__ */ React.createElement("span", { style: { fontSize: "0.72rem", color: "var(--ink-2)", marginLeft: 6 } }, "running\u2026")) : /* @__PURE__ */ React.createElement("div", { className: "adp-card-result" }, verdict && /* @__PURE__ */ React.createElement("span", { className: "adp-card-verdict", style: { color: verdictColor } }, verdict), detail && /* @__PURE__ */ React.createElement("span", { className: "adp-card-detail" }, detail))));
}
function AgentDebugOverlay({ open, onClose }) {
  useTraceLog();
  const [selectedId, setSelectedId] = ad_useState(null);
  const list = NikkoAgentLog.list().slice().reverse();
  const current = list.find((t) => t.id === selectedId) || list[0];
  ad_useEffect(() => {
    if (!open) return;
    if (!selectedId && list[0]) setSelectedId(list[0].id);
  }, [open, list.length]);
  if (!open) return null;
  return /* @__PURE__ */ React.createElement("div", { className: "debug-veil", onClick: onClose }, /* @__PURE__ */ React.createElement("div", { className: "debug-panel", onClick: (e) => e.stopPropagation() }, /* @__PURE__ */ React.createElement("header", { className: "debug-head" }, /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("div", { className: "debug-eyebrow" }, "Pipeline trace"), /* @__PURE__ */ React.createElement("h3", null, "Nikko adapters")), /* @__PURE__ */ React.createElement("button", { className: "iconbtn", onClick: onClose, "aria-label": "Close" }, /* @__PURE__ */ React.createElement("svg", { viewBox: "0 0 16 16", fill: "none", stroke: "currentColor", strokeWidth: "1.5", strokeLinecap: "round" }, /* @__PURE__ */ React.createElement("path", { d: "m4 4 8 8M12 4l-8 8" })))), !current ? /* @__PURE__ */ React.createElement("div", { className: "debug-empty" }, "Send a message and adapter results will appear here.") : /* @__PURE__ */ React.createElement("div", { className: "debug-body" }, /* @__PURE__ */ React.createElement("div", { className: "debug-turn-picker" }, /* @__PURE__ */ React.createElement("span", { className: "debug-eyebrow" }, "Turn"), /* @__PURE__ */ React.createElement("select", { value: current.id, onChange: (e) => setSelectedId(e.target.value) }, list.map((t) => /* @__PURE__ */ React.createElement("option", { key: t.id, value: t.id }, (t.userText || "").slice(0, 56), (t.userText || "").length > 56 ? "\u2026" : "")))), /* @__PURE__ */ React.createElement("div", { className: "debug-meta" }, /* @__PURE__ */ React.createElement("span", { className: `debug-mode mode-${current.is_crisis ? "CRISIS" : "COMFORT"}` }, current.is_crisis ? "CRISIS" : "COMFORT"), current.liveData ? /* @__PURE__ */ React.createElement("span", { className: "debug-meta-pill live" }, "\u25CF live data") : /* @__PURE__ */ React.createElement("span", { className: "debug-meta-pill sim" }, "simulated"), current.elapsed ? /* @__PURE__ */ React.createElement("span", { className: "debug-meta-item" }, current.elapsed, "s total") : null, current.regen ? /* @__PURE__ */ React.createElement("span", { className: "debug-meta-pill regen" }, "regen triggered") : null), /* @__PURE__ */ React.createElement("div", { className: "adp-cards" }, /* @__PURE__ */ React.createElement(
    AdapterCard,
    {
      step: "1",
      name: "ADP-B",
      role: "Mistral-7B \xB7 Safety / crisis",
      verdict: current.adp_b?.verdict,
      detail: current.adp_b?.flags?.length ? `flags: ${current.adp_b.flags.join(", ")}` : "no flags",
      running: false
    }
  ), /* @__PURE__ */ React.createElement(
    AdapterCard,
    {
      step: "2",
      name: "ADP-A",
      role: "Mistral-7B \xB7 Empathy response",
      verdict: current.is_crisis ? "BYPASSED" : "GENERATED",
      detail: current.adp_a?.chars ? `${current.adp_a.chars} chars` : null,
      running: false
    }
  ), /* @__PURE__ */ React.createElement(
    AdapterCard,
    {
      step: "3",
      name: "ADP-C",
      role: "Mistral-7B \xB7 Quality evaluator",
      verdict: current.adp_c?.verdict,
      detail: current.adp_c?.regen ? "regen pass triggered" : null,
      running: false
    }
  )), /* @__PURE__ */ React.createElement("details", { className: "debug-raw" }, /* @__PURE__ */ React.createElement("summary", { className: "debug-raw-toggle" }, "Raw pipeline payload"), /* @__PURE__ */ React.createElement("pre", { className: "debug-detail-json" }, JSON.stringify({
    is_crisis: current.is_crisis,
    flags: current.flags,
    verdict: current.verdict,
    regen: current.regen,
    elapsed: current.elapsed,
    adp_b: current.adp_b,
    adp_a: current.adp_a,
    adp_c: current.adp_c
  }, null, 2)))), /* @__PURE__ */ React.createElement("footer", { className: "debug-foot" }, /* @__PURE__ */ React.createElement("span", null, "Trace stays on this device \xB7 cleared on refresh"))));
}
Object.assign(window, { AgentRibbon, AgentDebugOverlay, useDebugGesture, buildAgentTrace, NikkoAgentLog });

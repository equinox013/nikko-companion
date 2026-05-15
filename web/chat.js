var NikkoChat = (() => {
  // web/chat.jsx
  var { useState, useEffect, useRef, useCallback } = React;
  function AiDisclaimer() {
    return /* @__PURE__ */ React.createElement("div", { className: "ai-disclaimer", role: "note", "aria-label": "AI limitation notice" }, /* @__PURE__ */ React.createElement(
      "svg",
      {
        viewBox: "0 0 12 12",
        fill: "none",
        stroke: "currentColor",
        strokeWidth: "1.5",
        strokeLinecap: "round",
        strokeLinejoin: "round",
        "aria-hidden": "true"
      },
      /* @__PURE__ */ React.createElement("circle", { cx: "6", cy: "6", r: "5" }),
      /* @__PURE__ */ React.createElement("path", { d: "M6 5v3" }),
      /* @__PURE__ */ React.createElement("circle", { cx: "6", cy: "3.5", r: "0.4", fill: "currentColor", stroke: "none" })
    ), "Nikko is AI and can make mistakes. Do not act on anything without further checking.");
  }
  function sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }
  function renderInline(text, sourceOrder, onCiteClick) {
    const parts = [];
    const re = /(\*\*[^*]+\*\*)|(\[\^s_[a-z_]+\])/g;
    let last = 0, m, i = 0;
    while ((m = re.exec(text)) !== null) {
      if (m.index > last) parts.push({ kind: "text", value: text.slice(last, m.index), key: i++ });
      if (m[1]) parts.push({ kind: "bold", value: m[1].slice(2, -2), key: i++ });
      else if (m[2]) {
        const key = m[2].slice(2, -1);
        if (!(key in sourceOrder)) sourceOrder[key] = Object.keys(sourceOrder).length + 1;
        parts.push({ kind: "cite", sourceKey: key, num: sourceOrder[key], key: i++ });
      }
      last = re.lastIndex;
    }
    if (last < text.length) parts.push({ kind: "text", value: text.slice(last), key: i++ });
    return parts.map((p) => {
      if (p.kind === "text") return /* @__PURE__ */ React.createElement(React.Fragment, { key: p.key }, p.value);
      if (p.kind === "bold") return /* @__PURE__ */ React.createElement("strong", { key: p.key }, p.value);
      if (p.kind === "cite") return /* @__PURE__ */ React.createElement(
        "button",
        {
          key: p.key,
          className: "cite-sup",
          onClick: () => onCiteClick(p.sourceKey),
          title: NIKKO_SOURCES[p.sourceKey]?.title || "Source"
        },
        p.num
      );
      return null;
    });
  }
  function MessageBody({ text, sourceOrder, onCiteClick, streaming }) {
    const paragraphs = text.split(/\n{2,}/);
    return /* @__PURE__ */ React.createElement(React.Fragment, null, paragraphs.map((p, pi) => /* @__PURE__ */ React.createElement("p", { key: pi }, renderInline(p, sourceOrder, onCiteClick), streaming && pi === paragraphs.length - 1 && /* @__PURE__ */ React.createElement("span", { className: "caret", "aria-hidden": "true" }))));
  }
  function SafetyBanner({ onDismiss }) {
    const [expanded, setExpanded] = React.useState(false);
    return /* @__PURE__ */ React.createElement("div", { className: "safety-banner", role: "status" }, /* @__PURE__ */ React.createElement("span", { className: "icon", "aria-hidden": "true" }, /* @__PURE__ */ React.createElement("svg", { viewBox: "0 0 12 12", fill: "none", stroke: "currentColor", strokeWidth: "1.6", strokeLinecap: "round", strokeLinejoin: "round" }, /* @__PURE__ */ React.createElement("path", { d: "M6 1.5C4 4 3 5.5 3 7a3 3 0 0 0 6 0c0-1.5-1-3-3-5.5z" }))), /* @__PURE__ */ React.createElement("div", { className: "body" }, /* @__PURE__ */ React.createElement("strong", null, "If you'd like to talk to a person right now"), /* @__PURE__ */ React.createElement("p", null, "Lifeline ", /* @__PURE__ */ React.createElement("a", { href: "tel:131114" }, "13 11 14"), " \xB7", " ", "Beyond Blue ", /* @__PURE__ */ React.createElement("a", { href: "tel:1300224636" }, "1300 22 4636"), " \xB7", " ", "Suicide Call Back ", /* @__PURE__ */ React.createElement("a", { href: "tel:1300659467" }, "1300 659 467"), " \xB7", " ", "Emergency: ", /* @__PURE__ */ React.createElement("a", { href: "tel:000" }, "000")), expanded && /* @__PURE__ */ React.createElement("p", { className: "safety-banner-extra" }, "QLife (LGBTIQ+) ", /* @__PURE__ */ React.createElement("a", { href: "tel:1800184527" }, "1800 184 527"), " \xB7", " ", "13YARN (First Nations) ", /* @__PURE__ */ React.createElement("a", { href: "tel:139276" }, "13 92 76"), " \xB7", " ", "Kids Helpline ", /* @__PURE__ */ React.createElement("a", { href: "tel:1800551800" }, "1800 55 1800"), " \xB7", " ", "1800RESPECT ", /* @__PURE__ */ React.createElement("a", { href: "tel:1800737732" }, "1800 737 732"), " \xB7", " ", "MensLine ", /* @__PURE__ */ React.createElement("a", { href: "tel:1300789978" }, "1300 78 99 78")), /* @__PURE__ */ React.createElement(
      "button",
      {
        className: "safety-banner-expand",
        onClick: () => setExpanded((e) => !e),
        "aria-expanded": expanded
      },
      expanded ? "Show less" : "More tailored support"
    )), /* @__PURE__ */ React.createElement("button", { className: "dismiss", onClick: onDismiss, "aria-label": "Dismiss" }, /* @__PURE__ */ React.createElement("svg", { viewBox: "0 0 12 12", fill: "none", stroke: "currentColor", strokeWidth: "1.5", strokeLinecap: "round" }, /* @__PURE__ */ React.createElement("path", { d: "m3 3 6 6M9 3l-6 6" }))));
  }
  function Composer({ onSend, disabled }) {
    const [val, setVal] = useState("");
    const ref = useRef(null);
    const autosize = useCallback(() => {
      const el = ref.current;
      if (!el) return;
      el.style.height = "auto";
      el.style.height = Math.min(160, el.scrollHeight) + "px";
    }, []);
    useEffect(() => {
      autosize();
    }, [val, autosize]);
    const submit = () => {
      const t = val.trim();
      if (!t || disabled) return;
      onSend(t);
      setVal("");
    };
    return /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("div", { className: "composer" }, /* @__PURE__ */ React.createElement(
      "textarea",
      {
        ref,
        value: val,
        onChange: (e) => setVal(e.target.value),
        onKeyDown: (e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            submit();
          }
        },
        placeholder: "Take your time\u2026",
        rows: 1,
        "aria-label": "Message Nikko"
      }
    ), /* @__PURE__ */ React.createElement("button", { className: "send", onClick: submit, disabled: !val.trim() || disabled, "aria-label": "Send message" }, /* @__PURE__ */ React.createElement("svg", { viewBox: "0 0 14 14", fill: "none", stroke: "currentColor", strokeWidth: "1.6", strokeLinecap: "round", strokeLinejoin: "round" }, /* @__PURE__ */ React.createElement("path", { d: "M2 7h10" }), /* @__PURE__ */ React.createElement("path", { d: "m8 3 4 4-4 4" })))), /* @__PURE__ */ React.createElement("div", { className: "composer-foot" }, /* @__PURE__ */ React.createElement("span", null, /* @__PURE__ */ React.createElement("span", { className: "kbd" }, "Enter"), " to send \xB7 ", /* @__PURE__ */ React.createElement("span", { className: "kbd" }, "Shift"), "+", /* @__PURE__ */ React.createElement("span", { className: "kbd" }, "Enter"), " for newline \xB7 type ", /* @__PURE__ */ React.createElement("span", { className: "kbd" }, "/help"), " for the tutorial"), /* @__PURE__ */ React.createElement("span", null, "Cleared on refresh")));
  }
  function quickExit() {
    try {
      sessionStorage.clear();
      const keep = ["nikko.theme", "nikko.tutorial.seen"];
      const all = Object.keys(localStorage);
      all.forEach((k) => {
        if (!keep.includes(k)) localStorage.removeItem(k);
      });
    } catch (e) {
    }
    try {
      window.location.replace("https://www.bom.gov.au/");
    } catch (e) {
      window.location.href = "https://www.bom.gov.au/";
    }
  }
  var BACKEND_URL = "https://nikko-companion.onrender.com";
  var THINK_STAGES = [
    { at: 0, label: "Reading your message\u2026" },
    { at: 6, label: "Checking in on what you shared\u2026" },
    { at: 14, label: "Putting together a response for you\u2026" }
  ];
  var AFFIRMATIONS = [
    "Making the best response. Because you matter.",
    "Taking a moment to get this right\u2026",
    "Finding the right words for you\u2026",
    "Still here \u2014 good things take a little time.",
    "Reading between the lines\u2026",
    "You deserve a thoughtful reply."
  ];
  function ThinkingBubble({ coldStart = false }) {
    const [elapsed, setElapsed] = React.useState(0);
    const [affIdx, setAffIdx] = React.useState(0);
    useEffect(() => {
      const start = Date.now();
      const tick = setInterval(() => {
        const s = Math.floor((Date.now() - start) / 1e3);
        setElapsed(s);
        if (s >= 24 && s % 5 === 0) {
          setAffIdx((i) => (i + 1) % AFFIRMATIONS.length);
        }
      }, 1e3);
      return () => clearInterval(tick);
    }, []);
    let label;
    if (elapsed < 24) {
      label = THINK_STAGES.reduce((acc, s) => elapsed >= s.at ? s.label : acc, THINK_STAGES[0].label);
    } else {
      label = AFFIRMATIONS[affIdx];
    }
    return /* @__PURE__ */ React.createElement(
      "div",
      {
        className: "bubble thinking-bubble" + (coldStart ? " cold-start-active" : ""),
        "aria-label": "Nikko is thinking",
        role: "status"
      },
      /* @__PURE__ */ React.createElement("div", { className: "t-dots-row" }, /* @__PURE__ */ React.createElement("span", { className: "t-dot" }), /* @__PURE__ */ React.createElement("span", { className: "t-dot" }), /* @__PURE__ */ React.createElement("span", { className: "t-dot" })),
      /* @__PURE__ */ React.createElement("p", { className: "t-label" }, label),
      coldStart && /* @__PURE__ */ React.createElement(React.Fragment, null, /* @__PURE__ */ React.createElement("div", { className: "cold-start-notice", "aria-live": "polite" }, /* @__PURE__ */ React.createElement(
        "svg",
        {
          viewBox: "0 0 12 12",
          fill: "none",
          stroke: "currentColor",
          strokeWidth: "1.5",
          strokeLinecap: "round",
          strokeLinejoin: "round",
          "aria-hidden": "true"
        },
        /* @__PURE__ */ React.createElement("circle", { cx: "6", cy: "6", r: "5" }),
        /* @__PURE__ */ React.createElement("path", { d: "M6 3.5V6l1.5 1.5" })
      ), /* @__PURE__ */ React.createElement("span", { className: "cold-start-text" }, "Server is waking up \u2014 first load takes ~60\u201390 s"), /* @__PURE__ */ React.createElement("span", { className: "cold-start-elapsed", "aria-label": elapsed + " seconds elapsed" }, elapsed, "s")), /* @__PURE__ */ React.createElement("div", { className: "cold-start-bar", "aria-hidden": "true" }, /* @__PURE__ */ React.createElement("div", { className: "cold-start-bar-fill" })))
    );
  }
  function Chat({ theme, onToggleTheme }) {
    const [messages, setMessages] = useState([
      { id: "open", role: "assistant", text: NIKKO_OPENING.text, emotion: NIKKO_OPENING.emotion, streaming: false }
    ]);
    const [streaming, setStreaming] = useState(false);
    const [isColdStart, setIsColdStart] = useState(false);
    const coldStartTimerRef = useRef(null);
    const [currentEmotion, setCurrentEmotion] = useState("calm");
    const [safetyVisible, setSafetyVisible] = useState(false);
    const [activeCite, setActiveCite] = useState(null);
    const [leftTab, setLeftTab] = useState(null);
    const [rightTab, setRightTab] = useState(null);
    const [dynamicSources, setDynamicSources] = useState([]);
    const sourceOrderRef = useRef({});
    const [, forceRerender] = useState(0);
    const threadRef = useRef(null);
    const contextID = React.useMemo(() => {
      const bytes = crypto.getRandomValues(new Uint8Array(6));
      const hex = Array.from(bytes).map((b) => b.toString(16).padStart(2, "0")).join("");
      return "nikko-" + Date.now() + "-" + hex;
    }, []);
    const [tutorialOpen, setTutorialOpen] = useState(() => {
      try {
        return localStorage.getItem("nikko.tutorial.seen") !== "1";
      } catch (e) {
        return true;
      }
    });
    const [debugOpen, setDebugOpen] = useState(false);
    const debugGesture = useDebugGesture(() => setDebugOpen(true));
    const closeTutorial = () => {
      try {
        localStorage.setItem("nikko.tutorial.seen", "1");
      } catch (e) {
      }
      setTutorialOpen(false);
    };
    const [memOpen, setMemOpen] = useState(false);
    const [loadOpen, setLoadOpen] = useState(false);
    const [memLoaded, setMemLoaded] = useState(false);
    const [memName, setMemName] = useState("");
    const [memPop, setMemPop] = useState(false);
    useEffect(() => {
      if (!memPop) return;
      const onDoc = (e) => {
        if (!e.target.closest || !e.target.closest(".mem-pop-host")) setMemPop(false);
      };
      document.addEventListener("mousedown", onDoc);
      return () => document.removeEventListener("mousedown", onDoc);
    }, [memPop]);
    const scrollToBottom = useCallback(() => {
      const el = threadRef.current;
      if (!el) return;
      requestAnimationFrame(() => {
        el.scrollTop = el.scrollHeight;
      });
    }, []);
    useEffect(() => {
      setTimeout(scrollToBottom, 50);
    }, [messages.length, scrollToBottom]);
    const onMemoryLoaded = useCallback((name) => {
      setMemLoaded(true);
      setMemName(name);
      setMessages((prev) => [...prev, {
        id: "wb-" + Date.now(),
        role: "assistant",
        emotion: "care",
        streaming: false,
        text: "Welcome back. Your memory file is loaded \u2014 I'll keep what's there in mind, but the live conversation is what I'll really listen to. You're in charge of what stays."
      }]);
      setTimeout(scrollToBottom, 30);
    }, [scrollToBottom]);
    const [moodEntries, setMoodEntries] = useState(() => {
      try {
        const raw = sessionStorage.getItem("nikko.mood");
        return raw ? JSON.parse(raw) : {};
      } catch (e) {
        return {};
      }
    });
    useEffect(() => {
      try {
        sessionStorage.setItem("nikko.mood", JSON.stringify(moodEntries));
      } catch (e) {
      }
    }, [moodEntries]);
    const setMoodEntry = (iso, val) => {
      setMoodEntries((prev) => {
        const next = { ...prev };
        if (val === null) delete next[iso];
        else next[iso] = val;
        return next;
      });
    };
    const onCiteClick = useCallback((k) => {
      setActiveCite(k);
      setDynamicSources([]);
      setRightTab("sources");
    }, []);
    const onSourcesBadgeClick = useCallback((sources) => {
      setDynamicSources(sources);
      setActiveCite(null);
      setRightTab("sources");
    }, []);
    const streamReply = useCallback(async (userText) => {
      setStreaming(true);
      setIsColdStart(false);
      const id = "m-" + Date.now();
      setMessages((prev) => [...prev, { id, role: "assistant", text: "", emotion: "listen", streaming: true, traceId: id, sources: [] }]);
      scrollToBottom();
      setCurrentEmotion("think");
      coldStartTimerRef.current = setTimeout(() => setIsColdStart(true), 12e3);
      try {
        const response = await fetch(BACKEND_URL + "/api/message", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: userText, contextID })
        });
        if (!response.ok) throw new Error("HTTP " + response.status);
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let currentEvent = "";
        let accText = "";
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop();
          for (const line of lines) {
            if (line.startsWith("event: ")) {
              currentEvent = line.slice(7).trim();
            } else if (line.startsWith("data: ")) {
              let data;
              try {
                data = JSON.parse(line.slice(6));
              } catch {
                continue;
              }
              if (currentEvent === "message_start") {
                clearTimeout(coldStartTimerRef.current);
                setIsColdStart(false);
                setCurrentEmotion(data.emotion || "listen");
              } else if (currentEvent === "chunk") {
                if (data.safetyFlags && data.safetyFlags.includes("crisis_detected")) setSafetyVisible(true);
                if (data.text) {
                  const emotion = data.emotion || "speak";
                  setCurrentEmotion(emotion);
                  const target = accText + data.text;
                  const stride = 3;
                  let pos = accText.length;
                  while (pos < target.length) {
                    pos = Math.min(target.length, pos + stride);
                    const slice = target.slice(0, pos);
                    setMessages((prev) => prev.map(
                      (m) => m.id === id ? { ...m, text: slice, emotion } : m
                    ));
                    scrollToBottom();
                    await sleep(14 + Math.random() * 10);
                  }
                  accText = target;
                  if (data.trace) {
                    NikkoAgentLog.add({ id, userText, ...data.trace, liveData: true });
                  }
                  if (data.sources && data.sources.length > 0) {
                    setMessages((prev) => prev.map(
                      (m) => m.id === id ? { ...m, sources: data.sources } : m
                    ));
                  }
                } else {
                  setCurrentEmotion(data.emotion || "think");
                }
              } else if (currentEvent === "message_end") {
                if (data.safetyFlags && data.safetyFlags.includes("crisis_detected")) setSafetyVisible(true);
              }
            }
          }
        }
        if (!accText) throw new Error("Empty stream \u2014 backend produced no text");
      } catch (err) {
        clearTimeout(coldStartTimerRef.current);
        setIsColdStart(false);
        console.warn("[Nikko] Backend unavailable \u2014 using local fallback:", err.message);
        const pattern = matchNikkoPattern(userText);
        if (pattern.safety) setSafetyVisible(true);
        const trace = buildAgentTrace(id, userText, pattern);
        NikkoAgentLog.add(trace);
        setMessages((prev) => prev.map(
          (m) => m.id === id ? { ...m, emotion: pattern.chunks[0].emotion } : m
        ));
        setCurrentEmotion("think");
        await sleep(420 + Math.random() * 220);
        let acc = "";
        for (let i = 0; i < pattern.chunks.length; i++) {
          const chunk = pattern.chunks[i];
          setCurrentEmotion(chunk.emotion);
          const target = (acc ? acc + "\n\n" : "") + chunk.text;
          const stride = 3;
          let pos = acc ? acc.length + 2 : 0;
          while (pos < target.length) {
            pos = Math.min(target.length, pos + stride);
            const slice = target.slice(0, pos);
            setMessages((prev) => prev.map(
              (m) => m.id === id ? { ...m, text: slice, emotion: chunk.emotion } : m
            ));
            forceRerender((x) => x + 1);
            scrollToBottom();
            await sleep(14 + Math.random() * 10);
          }
          acc = target;
          await sleep(260);
        }
      }
      setMessages((prev) => prev.map((m) => m.id === id ? { ...m, streaming: false } : m));
      setStreaming(false);
      setCurrentEmotion("calm");
    }, [scrollToBottom, contextID]);
    const onSend = useCallback((text) => {
      if (text.trim().toLowerCase() === "/help") {
        setTutorialOpen(true);
        return;
      }
      setMessages((prev) => [...prev, { id: "u-" + Date.now(), role: "user", text }]);
      scrollToBottom();
      streamReply(text);
    }, [scrollToBottom, streamReply]);
    const liveEmotion = streaming ? currentEmotion : "calm";
    const showSuggestions = messages.length === 1 && !streaming;
    const lastCompletedAssistantId = React.useMemo(() => {
      for (let i = messages.length - 1; i >= 0; i--) {
        const m = messages[i];
        if (m.role === "assistant" && !m.streaming && m.traceId) return m.id;
      }
      return null;
    }, [messages]);
    return /* @__PURE__ */ React.createElement("div", { className: "app" }, /* @__PURE__ */ React.createElement("header", { className: "topbar floating" }, /* @__PURE__ */ React.createElement("div", { className: "pillbar" }, /* @__PURE__ */ React.createElement("div", { className: "brand-mini" }, /* @__PURE__ */ React.createElement(
      "span",
      {
        className: "debug-trigger" + (debugGesture.holding ? " holding" : ""),
        ...debugGesture.handlers,
        "aria-hidden": "true"
      },
      /* @__PURE__ */ React.createElement(NikkoAvatar, { emotion: liveEmotion, size: 34 })
    ), /* @__PURE__ */ React.createElement("span", { className: "wordmark" }, "Nikko")), /* @__PURE__ */ React.createElement("div", { className: "divider" }), /* @__PURE__ */ React.createElement("div", { className: "tip-host" }, /* @__PURE__ */ React.createElement("span", { className: "pill linklike", tabIndex: 0 }, /* @__PURE__ */ React.createElement("span", { className: "dot" }), "Research preview"), /* @__PURE__ */ React.createElement("div", { className: "tip", role: "tooltip" }, "Nikko is an open research preview \u2014 non-diagnostic, not a clinician, implementation publicly visible at", " ", /* @__PURE__ */ React.createElement("a", { href: "https://github.com/nikko-research/nikko", target: "_blank", rel: "noopener noreferrer" }, "github.com/nikko-research/nikko"), ".")), memLoaded && /* @__PURE__ */ React.createElement(React.Fragment, null, /* @__PURE__ */ React.createElement("div", { className: "divider" }), /* @__PURE__ */ React.createElement("span", { className: "mem-indicator", title: memName ? "Memory: " + memName : "Memory active" }, /* @__PURE__ */ React.createElement("span", { className: "pulse" }), "Memory active"))), /* @__PURE__ */ React.createElement("div", { className: "pillbar" }, /* @__PURE__ */ React.createElement("div", { className: "mem-pop-host", style: { position: "relative" } }, /* @__PURE__ */ React.createElement(
      "button",
      {
        className: "ghostbtn" + (memLoaded ? " active" : ""),
        onClick: () => setMemPop((p) => !p),
        "aria-expanded": memPop,
        title: "Personal memory file"
      },
      /* @__PURE__ */ React.createElement("svg", { viewBox: "0 0 14 14", fill: "none", stroke: "currentColor", strokeWidth: "1.5", strokeLinecap: "round", strokeLinejoin: "round", style: { width: 13, height: 13, marginRight: 6, verticalAlign: "-2px" } }, /* @__PURE__ */ React.createElement("rect", { x: "2.5", y: "6", width: "9", height: "6.5", rx: "1.2" }), /* @__PURE__ */ React.createElement("path", { d: "M4.5 6V4a2.5 2.5 0 0 1 5 0v2" }), /* @__PURE__ */ React.createElement("path", { d: "M7 8.5v2" })),
      "Memory"
    ), memPop && /* @__PURE__ */ React.createElement("div", { className: "popover", role: "dialog", "aria-label": "Personal memory" }, /* @__PURE__ */ React.createElement("h4", null, "Personal memory"), /* @__PURE__ */ React.createElement("div", { className: "status" + (memLoaded ? " on" : "") }, /* @__PURE__ */ React.createElement("span", { className: "dot" }), memLoaded ? memName ? "Loaded \xB7 " + (memName.length > 24 ? memName.slice(0, 22) + "\u2026" : memName) : "Loaded" : "No memory file loaded"), /* @__PURE__ */ React.createElement("div", { className: "row" }, /* @__PURE__ */ React.createElement("button", { onClick: () => {
      setMemPop(false);
      setLoadOpen(true);
    } }, /* @__PURE__ */ React.createElement("svg", { viewBox: "0 0 14 14", fill: "none", stroke: "currentColor", strokeWidth: "1.5", strokeLinecap: "round", strokeLinejoin: "round" }, /* @__PURE__ */ React.createElement("path", { d: "M2.5 9V11a1 1 0 0 0 1 1h7a1 1 0 0 0 1-1V9" }), /* @__PURE__ */ React.createElement("path", { d: "M7 9V2.5" }), /* @__PURE__ */ React.createElement("path", { d: "M4 5.5 7 2.5l3 3" })), "Load"), /* @__PURE__ */ React.createElement("button", { onClick: () => {
      setMemPop(false);
      setMemOpen(true);
    } }, /* @__PURE__ */ React.createElement("svg", { viewBox: "0 0 14 14", fill: "none", stroke: "currentColor", strokeWidth: "1.5", strokeLinecap: "round", strokeLinejoin: "round" }, /* @__PURE__ */ React.createElement("path", { d: "M7 2.5v9M2.5 7h9" })), "Generate")), /* @__PURE__ */ React.createElement("div", { className: "hint" }, "Encrypted on your device. Nothing is uploaded. You can carry the file across sessions."))), /* @__PURE__ */ React.createElement(
      "button",
      {
        className: "iconbtn",
        onClick: onToggleTheme,
        "aria-label": "Switch to " + (theme === "light" ? "dark" : "light") + " mode",
        title: "Switch to " + (theme === "light" ? "dark" : "light") + " mode"
      },
      theme === "light" ? /* @__PURE__ */ React.createElement("svg", { viewBox: "0 0 16 16", fill: "none", stroke: "currentColor", strokeWidth: "1.5", strokeLinecap: "round", strokeLinejoin: "round" }, /* @__PURE__ */ React.createElement("path", { d: "M11.5 9.5A4 4 0 0 1 6.5 4.5a5 5 0 1 0 5 5z" })) : /* @__PURE__ */ React.createElement("svg", { viewBox: "0 0 16 16", fill: "none", stroke: "currentColor", strokeWidth: "1.5", strokeLinecap: "round", strokeLinejoin: "round" }, /* @__PURE__ */ React.createElement("circle", { cx: "8", cy: "8", r: "3" }), /* @__PURE__ */ React.createElement("path", { d: "M8 1.5v1.5M8 13v1.5M1.5 8h1.5M13 8h1.5M3.4 3.4l1 1M11.6 11.6l1 1M3.4 12.6l1-1M11.6 4.4l1-1" }))
    ), /* @__PURE__ */ React.createElement(
      "button",
      {
        className: "iconbtn",
        onClick: () => setTutorialOpen(true),
        "aria-label": "Help / replay tutorial",
        title: "Help \u2014 type /help or click here to replay the tutorial"
      },
      /* @__PURE__ */ React.createElement("svg", { viewBox: "0 0 16 16", fill: "none", stroke: "currentColor", strokeWidth: "1.5", strokeLinecap: "round", strokeLinejoin: "round" }, /* @__PURE__ */ React.createElement("circle", { cx: "8", cy: "8", r: "6" }), /* @__PURE__ */ React.createElement("path", { d: "M8 11.5v-.5" }), /* @__PURE__ */ React.createElement("path", { d: "M8 9.5c0-1.5 2-1.5 2-3a2 2 0 0 0-4 0" }))
    ), /* @__PURE__ */ React.createElement("div", { className: "divider" }), /* @__PURE__ */ React.createElement(
      "button",
      {
        className: "ghostbtn danger",
        onClick: quickExit,
        title: "Quick exit \u2014 clears this session and navigates away"
      },
      /* @__PURE__ */ React.createElement("svg", { viewBox: "0 0 14 14", fill: "none", stroke: "currentColor", strokeWidth: "1.6", strokeLinecap: "round", strokeLinejoin: "round", style: { width: 13, height: 13, marginRight: 5, verticalAlign: "-2px" } }, /* @__PURE__ */ React.createElement("path", { d: "M8.5 2.5h-5v9h5" }), /* @__PURE__ */ React.createElement("path", { d: "M6 7h6" }), /* @__PURE__ */ React.createElement("path", { d: "m9.5 4.5 2.5 2.5-2.5 2.5" })),
      "Quick exit"
    ))), /* @__PURE__ */ React.createElement("main", { className: "chat floating", "data-left": leftTab ? "open" : "closed", "data-right": rightTab ? "open" : "closed" }, !leftTab && /* @__PURE__ */ React.createElement("button", { className: "tab-float left", onClick: () => setLeftTab("mood"), title: "Mood diary" }, /* @__PURE__ */ React.createElement("svg", { viewBox: "0 0 16 16", fill: "none", stroke: "currentColor", strokeWidth: "1.5", strokeLinecap: "round", strokeLinejoin: "round" }, /* @__PURE__ */ React.createElement("rect", { x: "2.5", y: "3.5", width: "11", height: "10", rx: "1.5" }), /* @__PURE__ */ React.createElement("path", { d: "M2.5 6h11M5 2.5v3M11 2.5v3" })), "Mood diary"), !rightTab && /* @__PURE__ */ React.createElement("button", { className: "tab-float right", onClick: () => setRightTab("sources"), title: "Sources" }, "Sources", /* @__PURE__ */ React.createElement("svg", { viewBox: "0 0 16 16", fill: "none", stroke: "currentColor", strokeWidth: "1.5", strokeLinecap: "round", strokeLinejoin: "round" }, /* @__PURE__ */ React.createElement("path", { d: "M3 2.5h7l2.5 2.5v8.5H3z" }), /* @__PURE__ */ React.createElement("path", { d: "M3 5.5h6M3 8h7M3 10.5h5" }))), leftTab === "mood" && /* @__PURE__ */ React.createElement(MoodDiaryPanel, { entries: moodEntries, onSet: setMoodEntry, onClose: () => setLeftTab(null) }), /* @__PURE__ */ React.createElement("div", { className: "thread-wrap" }, /* @__PURE__ */ React.createElement("div", { className: "thread", ref: threadRef }, /* @__PURE__ */ React.createElement("div", { className: "thread-inner" }, /* @__PURE__ */ React.createElement("div", { className: "session-stamp" }, "Today \xB7 session begins"), messages.map((m, idx) => {
      if (m.role === "user") {
        return /* @__PURE__ */ React.createElement("div", { className: "msg user", key: m.id }, /* @__PURE__ */ React.createElement("div", { className: "body" }, /* @__PURE__ */ React.createElement("div", { className: "bubble" }, m.text)));
      }
      return /* @__PURE__ */ React.createElement("div", { className: "msg assistant", key: m.id }, /* @__PURE__ */ React.createElement("div", { className: "avatar-slot" }, /* @__PURE__ */ React.createElement(NikkoAvatar, { emotion: m.emotion || "calm", size: 42 })), /* @__PURE__ */ React.createElement("div", { className: "body" }, m.id === lastCompletedAssistantId && /* @__PURE__ */ React.createElement(AgentRibbon, { traceId: m.traceId }), m.text === "" && m.streaming ? /* @__PURE__ */ React.createElement(ThinkingBubble, { coldStart: isColdStart }) : /* @__PURE__ */ React.createElement("div", { className: "bubble" }, /* @__PURE__ */ React.createElement(
        MessageBody,
        {
          text: m.text,
          sourceOrder: sourceOrderRef.current,
          onCiteClick,
          streaming: !!m.streaming
        }
      )), m.sources && m.sources.length > 0 && !m.streaming && /* @__PURE__ */ React.createElement(
        "button",
        {
          className: "sources-badge",
          onClick: () => onSourcesBadgeClick(m.sources),
          title: "View sources used in this response"
        },
        /* @__PURE__ */ React.createElement("svg", { viewBox: "0 0 16 16", fill: "none", stroke: "currentColor", strokeWidth: "1.5", strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": "true" }, /* @__PURE__ */ React.createElement("path", { d: "M2 3h9a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V3z" }), /* @__PURE__ */ React.createElement("path", { d: "M5 3V1h7a1 1 0 0 1 1 1v10" }), /* @__PURE__ */ React.createElement("path", { d: "M5 7h5M5 10h3" })),
        m.sources.length,
        " source",
        m.sources.length !== 1 ? "s" : "",
        " used"
      ), idx === 0 && showSuggestions && /* @__PURE__ */ React.createElement("div", { className: "suggest-row" }, NIKKO_SUGGESTIONS.map((s) => /* @__PURE__ */ React.createElement("button", { key: s, className: "suggest", onClick: () => onSend(s) }, s)))));
    }))), /* @__PURE__ */ React.createElement("div", { className: "composer-wrap" }, /* @__PURE__ */ React.createElement("div", { className: "composer-inner" }, safetyVisible && /* @__PURE__ */ React.createElement(SafetyBanner, { onDismiss: () => setSafetyVisible(false) }), /* @__PURE__ */ React.createElement(Composer, { onSend, disabled: streaming }), /* @__PURE__ */ React.createElement(AiDisclaimer, null)))), rightTab === "sources" && /* @__PURE__ */ React.createElement(
      SourcesPanel,
      {
        sourceOrder: sourceOrderRef.current,
        activeKey: activeCite,
        onClose: () => setRightTab(null),
        dynamicSources
      }
    )), memOpen && /* @__PURE__ */ React.createElement(
      MemoryGenerateModal,
      {
        open: memOpen,
        onClose: () => setMemOpen(false),
        onCreated: () => setMemOpen(false)
      }
    ), loadOpen && /* @__PURE__ */ React.createElement(
      MemoryLoadModal,
      {
        open: loadOpen,
        onClose: () => setLoadOpen(false),
        onLoaded: (name) => {
          setLoadOpen(false);
          onMemoryLoaded(name);
        }
      }
    ), /* @__PURE__ */ React.createElement(Tutorial, { open: tutorialOpen, onSkip: closeTutorial, onDone: closeTutorial }), /* @__PURE__ */ React.createElement(AgentDebugOverlay, { open: debugOpen, onClose: () => setDebugOpen(false) }));
  }
  Object.assign(window, { Chat });
})();

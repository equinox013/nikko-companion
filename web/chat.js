const { useState, useEffect, useRef, useCallback } = React;
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
function parseDiaryEntries(md) {
  if (!md) return {};
  const re = /^##\s*Mood Diary\s*$/m;
  const match = md.match(re);
  if (!match) return {};
  const start = match.index + match[0].length;
  const next = md.indexOf("\n##", start);
  const body = (next === -1 ? md.slice(start) : md.slice(start, next)).replace(/<!--[\s\S]*?-->/g, "").trim();
  if (!body) return {};
  const result = {};
  for (const block of body.split(/\n\n+/)) {
    const lines = block.trim().split("\n");
    if (!lines[0]) continue;
    const parts = lines[0].split(" | ");
    const iso = parts[0]?.trim();
    if (!iso || !/^\d{4}-\d{2}-\d{2}$/.test(iso)) continue;
    const entry = { mood: 0, emotions: [], triggers: [], note: "", journal: "" };
    for (let i = 1; i < parts.length; i++) {
      const p = parts[i].trim();
      if (p.startsWith("mood:")) {
        const n = parseInt(p.slice(5).trim(), 10);
        if (!isNaN(n) && n >= 1 && n <= 10) entry.mood = n;
      } else if (p.startsWith("emotions:")) {
        entry.emotions = p.slice(9).split(",").map((s) => s.trim()).filter(Boolean);
      } else if (p.startsWith("triggers:")) {
        entry.triggers = p.slice(9).split(",").map((s) => s.trim()).filter(Boolean);
      }
    }
    if (lines[1]?.startsWith("note:")) entry.note = lines[1].slice(5).trim();
    result[iso] = entry;
  }
  return result;
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
const CHAR_LIMIT_DEFAULT = 1e3;
const CHAR_LIMIT_EXTENDED = 1500;
const _VERBOSE_SIGNALS = [
  "ramble",
  "rambles",
  "tend to write",
  "write a lot",
  "write quite a lot",
  "verbose",
  "verbosity",
  "lengthy",
  "long messages",
  "long message",
  "write long",
  "quite a lot to say"
];
function deriveCharLimit(memContent) {
  if (!memContent) return CHAR_LIMIT_DEFAULT;
  const lower = memContent.toLowerCase();
  const isVerbose = _VERBOSE_SIGNALS.some((sig) => lower.includes(sig));
  return isVerbose ? CHAR_LIMIT_EXTENDED : CHAR_LIMIT_DEFAULT;
}
function Composer({ onSend, disabled, maxLength }) {
  const limit = maxLength || CHAR_LIMIT_DEFAULT;
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
    if (!t || disabled || val.length > limit) return;
    onSend(t);
    setVal("");
  };
  const remaining = limit - val.length;
  const showCounter = val.length >= limit * 0.6;
  const counterClass = val.length > limit ? "composer-count over" : val.length >= limit * 0.8 ? "composer-count warn" : "composer-count";
  return /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement(
    "div",
    {
      className: "composer",
      onClick: (e) => {
        if (e.target.closest(".send")) return;
        ref.current?.focus();
      }
    },
    /* @__PURE__ */ React.createElement(
      "textarea",
      {
        ref,
        value: val,
        onChange: (e) => {
          setVal(e.target.value);
        },
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
    ),
    /* @__PURE__ */ React.createElement("button", { className: "send", onClick: submit, disabled: !val.trim() || disabled || val.length > limit, "aria-label": "Send message" }, /* @__PURE__ */ React.createElement("svg", { viewBox: "0 0 14 14", fill: "none", stroke: "currentColor", strokeWidth: "1.6", strokeLinecap: "round", strokeLinejoin: "round" }, /* @__PURE__ */ React.createElement("path", { d: "M2 7h10" }), /* @__PURE__ */ React.createElement("path", { d: "m8 3 4 4-4 4" })))
  ), /* @__PURE__ */ React.createElement("div", { className: "composer-foot" }, /* @__PURE__ */ React.createElement("span", null, /* @__PURE__ */ React.createElement("span", { className: "kbd" }, "Enter"), " to send \xB7 ", /* @__PURE__ */ React.createElement("span", { className: "kbd" }, "Shift"), "+", /* @__PURE__ */ React.createElement("span", { className: "kbd" }, "Enter"), " for newline \xB7 type ", /* @__PURE__ */ React.createElement("span", { className: "kbd" }, "/help"), " for the tutorial"), /* @__PURE__ */ React.createElement("span", { className: "composer-foot-right" }, showCounter && /* @__PURE__ */ React.createElement("span", { className: counterClass, "aria-live": "polite", "aria-label": `${remaining} characters remaining` }, remaining < 0 ? `${Math.abs(remaining)} over` : remaining), /* @__PURE__ */ React.createElement("span", null, "Cleared on refresh"))));
}
function MemBanner({ type, onDismiss, onOpenLoad }) {
  return /* @__PURE__ */ React.createElement("div", { className: "mem-banner", role: "status", "aria-live": "polite" }, /* @__PURE__ */ React.createElement("span", { className: "mem-banner-icon", "aria-hidden": "true" }, type === "loaded" ? (
    // Lock icon — memory is secure and active
    /* @__PURE__ */ React.createElement("svg", { viewBox: "0 0 12 12", width: "12", height: "12", fill: "none", stroke: "currentColor", strokeWidth: "1.5", strokeLinecap: "round", strokeLinejoin: "round" }, /* @__PURE__ */ React.createElement("rect", { x: "2", y: "5.5", width: "8", height: "5.5", rx: "1" }), /* @__PURE__ */ React.createElement("path", { d: "M4 5.5V4a2 2 0 0 1 4 0v1.5" }), /* @__PURE__ */ React.createElement("path", { d: "M6 7.5v1.5" }))
  ) : (
    // Info icon — gentle nudge, not an alert
    /* @__PURE__ */ React.createElement("svg", { viewBox: "0 0 12 12", width: "12", height: "12", fill: "none", stroke: "currentColor", strokeWidth: "1.5", strokeLinecap: "round", strokeLinejoin: "round" }, /* @__PURE__ */ React.createElement("circle", { cx: "6", cy: "6", r: "4.5" }), /* @__PURE__ */ React.createElement("path", { d: "M6 5v3" }), /* @__PURE__ */ React.createElement("circle", { cx: "6", cy: "3.5", r: "0.4", fill: "currentColor", stroke: "none" }))
  )), /* @__PURE__ */ React.createElement("div", { className: "mem-banner-body" }, type === "loaded" ? "Memory loaded \u2014 I'll keep your context in mind." : "Give Nikko a memory file for a more personal experience."), type === "hint" && /* @__PURE__ */ React.createElement("button", { className: "mem-banner-action", onClick: onOpenLoad }, "Set up"), /* @__PURE__ */ React.createElement("button", { className: "dismiss", onClick: onDismiss, "aria-label": "Dismiss banner" }, /* @__PURE__ */ React.createElement("svg", { viewBox: "0 0 10 10", width: "10", height: "10", fill: "none", stroke: "currentColor", strokeWidth: "1.5", strokeLinecap: "round" }, /* @__PURE__ */ React.createElement("path", { d: "m2.5 2.5 5 5M7.5 2.5l-5 5" }))));
}
function TechniqueCheckInBanner({ technique, onAdd, onDismiss, hasMemory }) {
  return /* @__PURE__ */ React.createElement("div", { className: "technique-checkin-banner", role: "status", "aria-live": "polite" }, /* @__PURE__ */ React.createElement("span", { className: "technique-checkin-icon", "aria-hidden": "true" }, /* @__PURE__ */ React.createElement(
    "svg",
    {
      viewBox: "0 0 14 14",
      fill: "none",
      stroke: "currentColor",
      strokeWidth: "1.5",
      strokeLinecap: "round",
      strokeLinejoin: "round"
    },
    /* @__PURE__ */ React.createElement("rect", { x: "2.5", y: "6", width: "9", height: "6.5", rx: "1.2" }),
    /* @__PURE__ */ React.createElement("path", { d: "M4.5 6V4a2.5 2.5 0 0 1 5 0v2" }),
    /* @__PURE__ */ React.createElement("path", { d: "M7 8.5v2" })
  )), /* @__PURE__ */ React.createElement("div", { className: "technique-checkin-body" }, /* @__PURE__ */ React.createElement("strong", null, "Worth remembering?"), hasMemory ? /* @__PURE__ */ React.createElement("p", null, "If ", technique, " helps, I can add it to your memory file.") : /* @__PURE__ */ React.createElement("p", null, "If ", technique, " helps, you can save it to a memory file. I'll create one with it already included.")), /* @__PURE__ */ React.createElement("div", { className: "technique-checkin-actions" }, /* @__PURE__ */ React.createElement(
    "button",
    {
      className: "technique-checkin-yes",
      onClick: onAdd,
      "aria-label": hasMemory ? `Add ${technique} to memory file` : `Create memory file with ${technique}`
    },
    hasMemory ? "Add to memory" : "Create memory file"
  ), /* @__PURE__ */ React.createElement(
    "button",
    {
      className: "technique-checkin-no",
      onClick: onDismiss,
      "aria-label": "Dismiss suggestion"
    },
    "Not now"
  )));
}
function MemoryProposalCard({ proposal, onAccept, onDecline }) {
  return /* @__PURE__ */ React.createElement("div", { className: "mem-proposal-card", role: "complementary", "aria-label": "Memory suggestion" }, /* @__PURE__ */ React.createElement("div", { className: "mem-proposal-icon", "aria-hidden": "true" }, /* @__PURE__ */ React.createElement("svg", { viewBox: "0 0 14 14", fill: "none", stroke: "currentColor", strokeWidth: "1.5", strokeLinecap: "round", strokeLinejoin: "round" }, /* @__PURE__ */ React.createElement("rect", { x: "2.5", y: "6", width: "9", height: "6.5", rx: "1.2" }), /* @__PURE__ */ React.createElement("path", { d: "M4.5 6V4a2.5 2.5 0 0 1 5 0v2" }), /* @__PURE__ */ React.createElement("path", { d: "M7 8.5v2" }))), /* @__PURE__ */ React.createElement("div", { className: "mem-proposal-body" }, /* @__PURE__ */ React.createElement("div", { className: "mem-proposal-label" }, "Add to memory?"), /* @__PURE__ */ React.createElement("div", { className: "mem-proposal-entry" }, /* @__PURE__ */ React.createElement("span", { className: "mem-proposal-section" }, proposal.section), " \u2014 ", proposal.entry)), /* @__PURE__ */ React.createElement("div", { className: "mem-proposal-actions" }, /* @__PURE__ */ React.createElement("button", { className: "mem-proposal-accept", onClick: onAccept, "aria-label": "Accept and add to memory" }, "Accept"), /* @__PURE__ */ React.createElement("button", { className: "mem-proposal-decline", onClick: onDecline, "aria-label": "Decline memory suggestion" }, "Decline")));
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
const BACKEND_URL = "https://nikko-companion.onrender.com";
const THINK_STAGES = [
  { at: 0, label: "Reading your message\u2026" },
  { at: 6, label: "Checking in on what you shared\u2026" },
  { at: 14, label: "Putting together a response for you\u2026" }
];
const AFFIRMATIONS = [
  "Making the best response. Because you matter.",
  "Taking a moment to get this right\u2026",
  "Finding the right words for you\u2026",
  "Still here \u2014 good things take a little time.",
  "Reading between the lines\u2026",
  "You deserve a thoughtful reply."
];
const CHECKIN_EMOTIONS = ["calm", "tired", "anxious", "low", "sad", "hopeful", "content", "overwhelmed", "numb", "irritable"];
function MoodCheckInPopup({ onLog, onSkip }) {
  const [rating, setRating] = React.useState(null);
  const [selected, setSelected] = React.useState([]);
  const toggleEmotion = (e) => {
    setSelected((prev) => prev.includes(e) ? prev.filter((x) => x !== e) : [...prev, e]);
  };
  const handleLog = () => {
    if (!rating) return;
    onLog({ rating, emotions: selected });
  };
  return /* @__PURE__ */ React.createElement("div", { className: "mood-checkin-popup", role: "form", "aria-label": "Quick mood check-in" }, /* @__PURE__ */ React.createElement("div", { className: "mood-checkin-header" }, /* @__PURE__ */ React.createElement("span", { className: "mood-checkin-title" }, "Quick check-in"), /* @__PURE__ */ React.createElement("span", { className: "mood-checkin-sub" }, "How are you feeling right now?")), /* @__PURE__ */ React.createElement("div", { className: "mood-checkin-rating", "aria-label": "Mood rating 1 to 10" }, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((n) => /* @__PURE__ */ React.createElement(
    "button",
    {
      key: n,
      "data-r": n,
      className: "mood-checkin-num" + (rating === n ? " active" : ""),
      onClick: () => setRating(n),
      "aria-pressed": rating === n,
      "aria-label": `${n} out of 10`
    },
    n
  ))), /* @__PURE__ */ React.createElement("div", { className: "mood-checkin-scale-hint" }, /* @__PURE__ */ React.createElement("span", null, "1 = very low"), /* @__PURE__ */ React.createElement("span", null, "10 = great")), /* @__PURE__ */ React.createElement("div", { className: "mood-checkin-chips", "aria-label": "Emotion chips, optional" }, CHECKIN_EMOTIONS.map((e) => /* @__PURE__ */ React.createElement(
    "button",
    {
      key: e,
      className: "mood-chip" + (selected.includes(e) ? " active" : ""),
      onClick: () => toggleEmotion(e),
      "aria-pressed": selected.includes(e)
    },
    e
  ))), /* @__PURE__ */ React.createElement("div", { className: "mood-checkin-actions" }, /* @__PURE__ */ React.createElement("button", { className: "mood-checkin-skip", onClick: onSkip }, "Skip"), /* @__PURE__ */ React.createElement(
    "button",
    {
      className: "mood-checkin-log",
      onClick: handleLog,
      disabled: !rating,
      "aria-disabled": !rating
    },
    "Log mood"
  )));
}
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
    ), /* @__PURE__ */ React.createElement("span", { className: "cold-start-text" }, "Server is waking up \u2014 first load takes ~60\u201390"), /* @__PURE__ */ React.createElement("span", { className: "cold-start-elapsed", "aria-label": elapsed + " seconds elapsed" }, elapsed, "s")), /* @__PURE__ */ React.createElement("div", { className: "cold-start-bar", "aria-hidden": "true" }, /* @__PURE__ */ React.createElement("div", { className: "cold-start-bar-fill" })))
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
  const lastResponseSourcesRef = useRef([]);
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
  const [memUserName, setMemUserName] = useState("");
  const memContentRef = useRef(null);
  const sessionKeyRef = useRef(null);
  const [memPop, setMemPop] = useState(false);
  const [memContentVersion, setMemContentVersion] = useState(0);
  const [pendingEntries, setPendingEntries] = useState([]);
  const [pendingBootstrapEntry, setPendingBootstrapEntry] = useState(null);
  const [techniqueCheckIn, setTechniqueCheckIn] = useState(null);
  const [memBanner, setMemBanner] = useState(null);
  const memBannerAutoRef = useRef(null);
  const hintShownRef = useRef(false);
  const moodCheckInShownRef = useRef(false);
  const [moodCheckIn, setMoodCheckIn] = useState(null);
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
  useEffect(() => {
    setTimeout(scrollToBottom, 80);
  }, [moodCheckIn, scrollToBottom]);
  useEffect(() => {
    setTimeout(scrollToBottom, 80);
  }, [safetyVisible, scrollToBottom]);
  useEffect(() => {
    setTimeout(scrollToBottom, 80);
  }, [memBanner, scrollToBottom]);
  useEffect(() => {
    setTimeout(scrollToBottom, 80);
  }, [techniqueCheckIn, scrollToBottom]);
  useEffect(() => {
    setTimeout(scrollToBottom, 80);
  }, [pendingEntries.length, scrollToBottom]);
  const onMemoryLoaded = useCallback((md, name, sessionKey = null, isNew = false) => {
    memContentRef.current = md || null;
    sessionKeyRef.current = sessionKey;
    setMemLoaded(true);
    setMemName(name);
    const parsedDiary = parseDiaryEntries(md);
    if (Object.keys(parsedDiary).length > 0) setMoodEntries(parsedDiary);
    const userName = typeof parseMemoryName === "function" ? parseMemoryName(md) : "";
    setMemUserName(userName);
    let chatText;
    if (isNew) {
      chatText = userName ? `Your memory file is ready, ${userName}. I'll keep what's there in mind as we talk \u2014 you're in charge of what stays.` : `Your memory file is ready. I'll keep what's there in mind as we talk \u2014 you're in charge of what stays.`;
    } else {
      const greeting = userName ? `Welcome back, ${userName}.` : "Welcome back.";
      chatText = `${greeting} Your memory file is loaded \u2014 I'll keep what's there in mind, but the live conversation is what I'll really listen to. You're in charge of what stays.`;
    }
    const wbId = "wb-" + Date.now();
    setMessages((prev) => [...prev, {
      id: wbId,
      role: "assistant",
      emotion: "care",
      streaming: false,
      text: chatText
    }]);
    setTimeout(scrollToBottom, 30);
    if (!isNew && sessionKey && !moodCheckInShownRef.current) {
      moodCheckInShownRef.current = true;
      setTimeout(() => setMoodCheckIn({ wbId }), 200);
    }
    clearTimeout(memBannerAutoRef.current);
    setMemBanner("loaded");
    memBannerAutoRef.current = setTimeout(() => setMemBanner(null), 7e3);
  }, [scrollToBottom]);
  useEffect(() => {
    if (memLoaded || hintShownRef.current || memBanner) return;
    const userCount = messages.filter((m) => m.role === "user").length;
    if (userCount >= 3) {
      hintShownRef.current = true;
      setMemBanner("hint");
    }
  }, [messages, memLoaded, memBanner]);
  useEffect(() => () => clearTimeout(memBannerAutoRef.current), []);
  const [moodEntries, setMoodEntries] = useState({});
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
  const INPUT_WORD_CAPS = { concise: 150, standard: 300, verbose: 600 };
  const DEFAULT_WORD_CAP = 300;
  const applyInputCap = useCallback((text) => {
    const md = memContentRef.current;
    if (!md) return text;
    const prefs = typeof parseMemoryPrefs === "function" ? parseMemoryPrefs(md) : {};
    const capKey = prefs.input_length || "standard";
    const cap = INPUT_WORD_CAPS[capKey] !== void 0 ? INPUT_WORD_CAPS[capKey] : DEFAULT_WORD_CAP;
    const words = text.split(/\s+/);
    if (words.length <= cap) return text;
    return words.slice(0, cap).join(" ") + " [message truncated per user preference]";
  }, []);
  const saveMemoryUpdates = useCallback(async (entries = null) => {
    if (!memContentRef.current || !sessionKeyRef.current) return;
    const toApply = entries || pendingEntries;
    if (!toApply.length) return;
    let updated = memContentRef.current;
    for (const e of toApply) {
      if (typeof applyMemoryEntry === "function") {
        updated = applyMemoryEntry(updated, e.section, e.entry);
      }
    }
    try {
      const enc = await encryptMemoryWithKey(updated, sessionKeyRef.current);
      const baseName = (memName || "nikko-memory").replace(/\s+/g, "-");
      downloadFile(baseName, enc);
      memContentRef.current = updated;
      if (entries) {
        const savedTs = new Set(entries.map((e) => e.ts));
        setPendingEntries((prev) => prev.filter((e) => !savedTs.has(e.ts)));
      } else {
        setPendingEntries([]);
      }
    } catch (err) {
      console.error("[Nikko USM] Re-encryption failed:", err);
    }
  }, [pendingEntries, memName]);
  const onMemoryRewrite = useCallback(async (updatedMd) => {
    if (!sessionKeyRef.current) return;
    try {
      const enc = await encryptMemoryWithKey(updatedMd, sessionKeyRef.current);
      const baseName = (memName || "nikko-memory").replace(/\s+/g, "-");
      downloadFile(baseName, enc);
      memContentRef.current = updatedMd;
      setMemContentVersion((v) => v + 1);
    } catch (err) {
      console.error("[Nikko USM] Memory rewrite failed:", err);
    }
  }, [memName]);
  const onCheckInAdd = useCallback(() => {
    if (!techniqueCheckIn) return;
    if (memContentRef.current && sessionKeyRef.current) {
      setPendingEntries((prev) => [...prev, { ...techniqueCheckIn, ts: Date.now() }]);
    } else {
      setPendingBootstrapEntry(techniqueCheckIn);
      setMemOpen(true);
    }
    setTechniqueCheckIn(null);
  }, [techniqueCheckIn]);
  const onMoodCheckInLog = useCallback(({ rating, emotions }) => {
    const today = (/* @__PURE__ */ new Date()).toISOString().split("T")[0];
    const entry = { mood: rating, emotions, triggers: "" };
    setMoodEntry(today, entry);
    const formatted = typeof formatDiaryEntry === "function" ? formatDiaryEntry(today, entry) : `${today} | mood: ${rating} | emotions: ${emotions.join(", ")} | triggers: `;
    setPendingEntries((prev) => [...prev, {
      section: "## Mood Diary",
      entry: formatted,
      ts: Date.now()
    }]);
    setMoodCheckIn(null);
  }, [setMoodEntry]);
  useEffect(() => {
    if (!pendingEntries.length) return;
    const handler = (e) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [pendingEntries.length]);
  const streamReply = useCallback(async (userText) => {
    setStreaming(true);
    setIsColdStart(false);
    const id = "m-" + Date.now();
    setMessages((prev) => [...prev, { id, role: "assistant", text: "", emotion: "listen", streaming: true, traceId: id, sources: [] }]);
    scrollToBottom();
    setCurrentEmotion("think");
    NikkoAgentLog.add({ id, userText, _processing: true, _stage: "understanding your message" });
    coldStartTimerRef.current = setTimeout(() => setIsColdStart(true), 12e3);
    try {
      const cappedText = applyInputCap(userText);
      const reqBody = { text: cappedText, contextID };
      if (memContentRef.current) {
        reqBody.memoryContext = memContentRef.current.slice(0, 8e3);
      }
      const historyRaw = messages.filter(
        (m) => m.id !== "open" && !String(m.id).startsWith("wb-") && !m.streaming && m.text && (m.role === "user" || m.role === "assistant")
      ).slice(-20).map((m) => ({ role: m.role, text: m.text }));
      if (historyRaw.length > 0) {
        reqBody.conversationHistory = historyRaw;
      }
      const response = await fetch(BACKEND_URL + "/api/message", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(reqBody)
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
              if (data.stage) NikkoAgentLog.update(id, { _stage: data.stage });
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
                  NikkoAgentLog.update(id, {
                    ...data.trace,
                    _mode: (data.trace.mode || "").toUpperCase() || void 0,
                    liveData: true,
                    _processing: false
                  });
                }
                if (data.sources && data.sources.length > 0) {
                  setMessages((prev) => prev.map(
                    (m) => m.id === id ? { ...m, sources: data.sources } : m
                  ));
                  lastResponseSourcesRef.current = data.sources;
                }
                if (data.memory_proposal && memContentRef.current && sessionKeyRef.current) {
                  setPendingEntries((prev) => [...prev, {
                    ...data.memory_proposal,
                    ts: Date.now()
                  }]);
                }
                if (data.technique_recommended && !data.memory_proposal) {
                  setTechniqueCheckIn(data.technique_recommended);
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
      NikkoAgentLog.update(id, { ...trace, _processing: false });
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
  }, [scrollToBottom, contextID, applyInputCap]);
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
  const lastAssistantId = React.useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const m = messages[i];
      if (m.role === "assistant" && m.traceId) return m.id;
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
  ), /* @__PURE__ */ React.createElement("span", { className: "wordmark" }, "Nikko")), /* @__PURE__ */ React.createElement("div", { className: "divider" }), /* @__PURE__ */ React.createElement("div", { className: "tip-host research-pill" }, /* @__PURE__ */ React.createElement("span", { className: "pill linklike", tabIndex: 0 }, /* @__PURE__ */ React.createElement("span", { className: "dot" }), "Research preview"), /* @__PURE__ */ React.createElement("div", { className: "tip", role: "tooltip" }, "Nikko is an open research preview \u2014 non-diagnostic, not a clinician, implementation publicly visible at", " ", /* @__PURE__ */ React.createElement("a", { href: "https://github.com/equinox013/nikko-companion", target: "_blank", rel: "noopener noreferrer" }, "github.com/equinox013/nikko-companion"), ".")), memLoaded && /* @__PURE__ */ React.createElement(React.Fragment, null, /* @__PURE__ */ React.createElement("div", { className: "divider" }), /* @__PURE__ */ React.createElement(
    "span",
    {
      className: "mem-indicator",
      title: memContentRef.current ? memName ? "Memory active \xB7 " + memName : "Memory active" : "Memory file was loaded \u2014 re-load to restore context for this session"
    },
    /* @__PURE__ */ React.createElement("span", { className: memContentRef.current ? "pulse" : "pulse dim" }),
    memContentRef.current ? memUserName ? `Memory \xB7 ${memUserName}` : "Memory active" : "Memory \xB7 re-load"
  ))), /* @__PURE__ */ React.createElement("div", { className: "pillbar" }, /* @__PURE__ */ React.createElement("div", { className: "mem-pop-host", style: { position: "relative" } }, /* @__PURE__ */ React.createElement(
    "button",
    {
      className: "ghostbtn" + (memLoaded ? " active" : ""),
      onClick: () => setMemPop((p) => !p),
      "aria-expanded": memPop,
      title: "Personal memory file"
    },
    /* @__PURE__ */ React.createElement("svg", { viewBox: "0 0 14 14", fill: "none", stroke: "currentColor", strokeWidth: "1.5", strokeLinecap: "round", strokeLinejoin: "round", style: { width: 13, height: 13, marginRight: 6, verticalAlign: "-2px" } }, /* @__PURE__ */ React.createElement("rect", { x: "2.5", y: "6", width: "9", height: "6.5", rx: "1.2" }), /* @__PURE__ */ React.createElement("path", { d: "M4.5 6V4a2.5 2.5 0 0 1 5 0v2" }), /* @__PURE__ */ React.createElement("path", { d: "M7 8.5v2" })),
    "Memory"
  ), memPop && /* @__PURE__ */ React.createElement("div", { className: "popover", role: "dialog", "aria-label": "Personal memory" }, /* @__PURE__ */ React.createElement("h4", null, "Personal memory"), /* @__PURE__ */ React.createElement("div", { className: "status" + (memContentRef.current ? " on" : "") }, /* @__PURE__ */ React.createElement("span", { className: "dot" }), memContentRef.current ? memName ? "Loaded \xB7 " + (memName.length > 24 ? memName.slice(0, 22) + "\u2026" : memName) : "Loaded" : "No memory file loaded"), /* @__PURE__ */ React.createElement("div", { className: "row" }, /* @__PURE__ */ React.createElement("button", { onClick: () => {
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
  ), pendingEntries.length > 0 && /* @__PURE__ */ React.createElement(React.Fragment, null, /* @__PURE__ */ React.createElement("div", { className: "divider" }), /* @__PURE__ */ React.createElement(
    "button",
    {
      className: "ghostbtn mem-save-btn",
      onClick: () => saveMemoryUpdates(),
      title: `Save ${pendingEntries.length} pending memory update${pendingEntries.length !== 1 ? "s" : ""}`
    },
    /* @__PURE__ */ React.createElement("svg", { viewBox: "0 0 14 14", fill: "none", stroke: "currentColor", strokeWidth: "1.5", strokeLinecap: "round", strokeLinejoin: "round", style: { width: 13, height: 13, marginRight: 5, verticalAlign: "-2px" } }, /* @__PURE__ */ React.createElement("path", { d: "M2.5 9V11a1 1 0 0 0 1 1h7a1 1 0 0 0 1-1V9" }), /* @__PURE__ */ React.createElement("path", { d: "M7 1.5v8" }), /* @__PURE__ */ React.createElement("path", { d: "M4.5 6.5 7 9l2.5-2.5" })),
    "Save memory (",
    pendingEntries.length,
    ")"
  )), /* @__PURE__ */ React.createElement("div", { className: "divider" }), /* @__PURE__ */ React.createElement(
    "button",
    {
      className: "ghostbtn danger",
      onClick: quickExit,
      title: "Quick exit \u2014 clears this session and navigates away"
    },
    /* @__PURE__ */ React.createElement("svg", { viewBox: "0 0 14 14", fill: "none", stroke: "currentColor", strokeWidth: "1.6", strokeLinecap: "round", strokeLinejoin: "round", style: { width: 13, height: 13, marginRight: 5, verticalAlign: "-2px" } }, /* @__PURE__ */ React.createElement("path", { d: "M8.5 2.5h-5v9h5" }), /* @__PURE__ */ React.createElement("path", { d: "M6 7h6" }), /* @__PURE__ */ React.createElement("path", { d: "m9.5 4.5 2.5 2.5-2.5 2.5" })),
    "Quick exit"
  ))), /* @__PURE__ */ React.createElement("main", { className: "chat floating", "data-left": leftTab ? "open" : "closed", "data-right": rightTab ? "open" : "closed" }, !leftTab && /* @__PURE__ */ React.createElement("button", { className: "tab-float left", onClick: () => setLeftTab("mood"), title: "Mood diary" }, /* @__PURE__ */ React.createElement("svg", { viewBox: "0 0 16 16", fill: "none", stroke: "currentColor", strokeWidth: "1.5", strokeLinecap: "round", strokeLinejoin: "round" }, /* @__PURE__ */ React.createElement("rect", { x: "2.5", y: "3.5", width: "11", height: "10", rx: "1.5" }), /* @__PURE__ */ React.createElement("path", { d: "M2.5 6h11M5 2.5v3M11 2.5v3" })), "Mood diary"), !rightTab && /* @__PURE__ */ React.createElement("button", { className: "tab-float right", onClick: () => {
    if (lastResponseSourcesRef.current.length > 0) {
      setDynamicSources(lastResponseSourcesRef.current);
    }
    setRightTab("sources");
  }, title: "Sources" }, "Sources", /* @__PURE__ */ React.createElement("svg", { viewBox: "0 0 16 16", fill: "none", stroke: "currentColor", strokeWidth: "1.5", strokeLinecap: "round", strokeLinejoin: "round" }, /* @__PURE__ */ React.createElement("path", { d: "M3 2.5h7l2.5 2.5v8.5H3z" }), /* @__PURE__ */ React.createElement("path", { d: "M3 5.5h6M3 8h7M3 10.5h5" }))), leftTab === "mood" && /* @__PURE__ */ React.createElement(
    MoodDiaryPanel,
    {
      entries: moodEntries,
      onSet: setMoodEntry,
      onClose: () => setLeftTab(null),
      memoryContent: memContentRef.current,
      onMemoryUpdate: sessionKeyRef.current ? onMemoryRewrite : null
    }
  ), /* @__PURE__ */ React.createElement("div", { className: "thread-wrap" }, /* @__PURE__ */ React.createElement(
    "div",
    {
      className: "thread",
      ref: threadRef,
      style: safetyVisible ? { paddingBottom: "290px" } : void 0
    },
    /* @__PURE__ */ React.createElement("div", { className: "thread-inner" }, /* @__PURE__ */ React.createElement("div", { className: "session-stamp" }, "Today \xB7 session begins"), messages.map((m, idx) => {
      if (m.role === "user") {
        return /* @__PURE__ */ React.createElement("div", { className: "msg user", key: m.id }, /* @__PURE__ */ React.createElement("div", { className: "body" }, /* @__PURE__ */ React.createElement("div", { className: "bubble" }, m.text)));
      }
      return /* @__PURE__ */ React.createElement(React.Fragment, { key: m.id }, /* @__PURE__ */ React.createElement("div", { className: "msg assistant" }, /* @__PURE__ */ React.createElement("div", { className: "avatar-slot" }, /* @__PURE__ */ React.createElement(NikkoAvatar, { emotion: m.emotion || "calm", size: 42 })), /* @__PURE__ */ React.createElement("div", { className: "body" }, m.traceId && m.id === lastAssistantId && /* @__PURE__ */ React.createElement(AgentRibbon, { traceId: m.traceId }), m.text === "" && m.streaming ? /* @__PURE__ */ React.createElement(ThinkingBubble, { coldStart: isColdStart }) : /* @__PURE__ */ React.createElement("div", { className: "bubble" }, /* @__PURE__ */ React.createElement(
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
      ), idx === 0 && showSuggestions && /* @__PURE__ */ React.createElement("div", { className: "suggest-row" }, NIKKO_SUGGESTIONS.map((s) => /* @__PURE__ */ React.createElement("button", { key: s, className: "suggest", onClick: () => onSend(s) }, s))))), moodCheckIn && m.id === moodCheckIn.wbId && /* @__PURE__ */ React.createElement(
        MoodCheckInPopup,
        {
          onLog: onMoodCheckInLog,
          onSkip: () => setMoodCheckIn(null)
        }
      ));
    }))
  ), /* @__PURE__ */ React.createElement("div", { className: "composer-wrap" }, /* @__PURE__ */ React.createElement("div", { className: "composer-inner" }, techniqueCheckIn && /* @__PURE__ */ React.createElement(
    TechniqueCheckInBanner,
    {
      technique: techniqueCheckIn.technique,
      hasMemory: !!(memContentRef.current && sessionKeyRef.current),
      onAdd: onCheckInAdd,
      onDismiss: () => setTechniqueCheckIn(null)
    }
  ), pendingEntries.map((entry) => /* @__PURE__ */ React.createElement(
    MemoryProposalCard,
    {
      key: entry.ts,
      proposal: entry,
      onAccept: () => saveMemoryUpdates([entry]),
      onDecline: () => setPendingEntries((prev) => prev.filter((e) => e.ts !== entry.ts))
    }
  )), memBanner && /* @__PURE__ */ React.createElement(
    MemBanner,
    {
      type: memBanner,
      onDismiss: () => {
        clearTimeout(memBannerAutoRef.current);
        setMemBanner(null);
      },
      onOpenLoad: () => {
        setMemBanner(null);
        setLoadOpen(true);
      }
    }
  ), safetyVisible && /* @__PURE__ */ React.createElement(SafetyBanner, { onDismiss: () => setSafetyVisible(false) }), /* @__PURE__ */ React.createElement(Composer, { onSend, disabled: streaming, maxLength: deriveCharLimit(memContentRef.current) }), /* @__PURE__ */ React.createElement(AiDisclaimer, null)))), rightTab === "sources" && /* @__PURE__ */ React.createElement(
    SourcesPanel,
    {
      sourceOrder: sourceOrderRef.current,
      activeKey: activeCite,
      onClose: () => setRightTab(null),
      dynamicSources
    }
  ), (leftTab || rightTab) && /* @__PURE__ */ React.createElement(
    "div",
    {
      className: "sheet-backdrop",
      onClick: () => {
        setLeftTab(null);
        setRightTab(null);
      },
      "aria-hidden": "true"
    }
  ), /* @__PURE__ */ React.createElement("nav", { className: "mobile-tabbar", "aria-label": "Panels" }, /* @__PURE__ */ React.createElement(
    "button",
    {
      className: "mtab" + (leftTab === "mood" ? " active" : ""),
      "aria-pressed": leftTab === "mood",
      "aria-label": "Mood diary",
      onClick: () => {
        setLeftTab((v) => v === "mood" ? null : "mood");
        setRightTab(null);
      }
    },
    /* @__PURE__ */ React.createElement("svg", { viewBox: "0 0 16 16", fill: "none", stroke: "currentColor", strokeWidth: "1.5", strokeLinecap: "round", strokeLinejoin: "round" }, /* @__PURE__ */ React.createElement("rect", { x: "2.5", y: "3.5", width: "11", height: "10", rx: "1.5" }), /* @__PURE__ */ React.createElement("path", { d: "M2.5 6h11M5 2.5v3M11 2.5v3" })),
    "Mood"
  ), /* @__PURE__ */ React.createElement(
    "button",
    {
      className: "mtab sources" + (rightTab === "sources" ? " active" : ""),
      "aria-pressed": rightTab === "sources",
      "aria-label": "Sources",
      onClick: () => {
        if (rightTab !== "sources") {
          if (lastResponseSourcesRef.current.length > 0) {
            setDynamicSources(lastResponseSourcesRef.current);
          }
          setRightTab("sources");
        } else {
          setRightTab(null);
        }
        setLeftTab(null);
      }
    },
    /* @__PURE__ */ React.createElement("svg", { viewBox: "0 0 16 16", fill: "none", stroke: "currentColor", strokeWidth: "1.5", strokeLinecap: "round", strokeLinejoin: "round" }, /* @__PURE__ */ React.createElement("path", { d: "M3 2.5h7l2.5 2.5v8.5H3z" }), /* @__PURE__ */ React.createElement("path", { d: "M3 5.5h6M3 8h7M3 10.5h5" })),
    "Sources"
  ))), memOpen && /* @__PURE__ */ React.createElement(
    MemoryGenerateModal,
    {
      open: memOpen,
      onClose: () => {
        setMemOpen(false);
        setPendingBootstrapEntry(null);
      },
      onCreated: (md) => {
        setMemOpen(false);
        setPendingBootstrapEntry(null);
        onMemoryLoaded(md, "nikko-memory", null, true);
      },
      initialEntries: pendingBootstrapEntry ? [pendingBootstrapEntry] : []
    }
  ), loadOpen && /* @__PURE__ */ React.createElement(
    MemoryLoadModal,
    {
      open: loadOpen,
      onClose: () => setLoadOpen(false),
      onLoaded: (md, name, sessionKey) => {
        setLoadOpen(false);
        onMemoryLoaded(md, name, sessionKey);
      }
    }
  ), /* @__PURE__ */ React.createElement(Tutorial, { open: tutorialOpen, onSkip: closeTutorial, onDone: closeTutorial }), /* @__PURE__ */ React.createElement(AgentDebugOverlay, { open: debugOpen, onClose: () => setDebugOpen(false) }));
}

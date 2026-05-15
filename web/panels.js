(() => {
  const { useState: ps, useEffect: pe, useRef: pr } = React;
  function formatAuthors(authors) {
    if (!authors || authors.length === 0) return null;
    if (authors.length === 1) return authors[0];
    if (authors.length <= 20) {
      return authors.slice(0, -1).join(", ") + ", & " + authors[authors.length - 1];
    }
    return authors.slice(0, 19).join(", ") + ", ..." + authors[authors.length - 1];
  }
  function formatAPA7(source) {
    const authorStr = formatAuthors(source.authors) || (source.source_name || "Unknown organisation").trim();
    const year = source.year ? source.year : "n.d.";
    const title = (source.title || "(Untitled)").trim();
    const url = (source.url || "").trim();
    if (source.evidence_tier === "peer_reviewed") {
      return url ? `${authorStr} (${year}). ${title}. ${url}` : `${authorStr} (${year}). ${title}.`;
    }
    const location = url ? source.year ? url : `Retrieved from ${url}` : "";
    return location ? `${authorStr} (${year}). ${title}. ${location}` : `${authorStr} (${year}). ${title}.`;
  }
  function SourcesPanel({ sourceOrder, activeKey, onClose, dynamicSources }) {
    const hasDynamic = dynamicSources && dynamicSources.length > 0;
    pe(() => {
      if (!activeKey || hasDynamic) return;
      const el = document.querySelector(`[data-anchor="source-${activeKey}"]`);
      if (el) el.scrollIntoView({ block: "center" });
    }, [activeKey, hasDynamic]);
    if (hasDynamic) {
      return /* @__PURE__ */ React.createElement("aside", { className: "panel right", "aria-label": "Sources used" }, /* @__PURE__ */ React.createElement("div", { className: "panel-head" }, /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("h3", null, "Sources"), /* @__PURE__ */ React.createElement("div", { className: "meta" }, dynamicSources.length, " reference", dynamicSources.length !== 1 ? "s" : "", " \xB7 APA 7")), /* @__PURE__ */ React.createElement("button", { className: "iconbtn", onClick: onClose, "aria-label": "Close sources" }, /* @__PURE__ */ React.createElement("svg", { viewBox: "0 0 16 16", fill: "none", stroke: "currentColor", strokeWidth: "1.5", strokeLinecap: "round" }, /* @__PURE__ */ React.createElement("path", { d: "m4 4 8 8M12 4l-8 8" })))), /* @__PURE__ */ React.createElement("div", { className: "panel-body" }, dynamicSources.map((s, i) => /* @__PURE__ */ React.createElement("div", { key: i, className: "source-card" }, /* @__PURE__ */ React.createElement("div", { className: "row" }, /* @__PURE__ */ React.createElement("span", { className: "num" }, i + 1), /* @__PURE__ */ React.createElement("span", null, s.source_name), s.evidence_tier === "peer_reviewed" && /* @__PURE__ */ React.createElement("span", { style: {
        fontSize: 10,
        fontWeight: 600,
        letterSpacing: "0.04em",
        background: "var(--accent-muted, rgba(99,102,241,0.12))",
        color: "var(--accent, #6366f1)",
        borderRadius: 4,
        padding: "1px 5px",
        marginLeft: 6
      } }, "Peer-reviewed")), /* @__PURE__ */ React.createElement("div", { className: "title" }, s.title), s.url && /* @__PURE__ */ React.createElement("a", { className: "linkrow", href: s.url, target: "_blank", rel: "noopener noreferrer" }, s.url.replace(/^https?:\/\//, "").slice(0, 60), s.url.length > 67 ? "…" : ""), /* @__PURE__ */ React.createElement("div", { className: "apa" }, formatAPA7(s)))), /* @__PURE__ */ React.createElement("div", { style: { fontSize: 11, color: "var(--muted)", padding: "10px 4px 0" } }, "References formatted to APA 7th edition (best-effort — full author/volume metadata requires Phase 5 PubMed enrichment).")));
    }
    const ordered = Object.entries(sourceOrder).sort((a, b) => a[1] - b[1]).map(([k, n]) => ({ key: k, num: n, ...NIKKO_SOURCES[k] || {} }));
    pe(() => {
      if (!activeKey) return;
      const el = document.querySelector(`[data-anchor="source-${activeKey}"]`);
      if (el) el.scrollIntoView({ block: "center" });
    }, [activeKey]);
    return /* @__PURE__ */ React.createElement("aside", { className: "panel right", "aria-label": "Sources used" }, /* @__PURE__ */ React.createElement("div", { className: "panel-head" }, /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("h3", null, "Sources"), /* @__PURE__ */ React.createElement("div", { className: "meta" }, ordered.length, " reference", ordered.length === 1 ? "" : "s", " \xB7 APA 7")), /* @__PURE__ */ React.createElement("button", { className: "iconbtn", onClick: onClose, "aria-label": "Close sources" }, /* @__PURE__ */ React.createElement("svg", { viewBox: "0 0 16 16", fill: "none", stroke: "currentColor", strokeWidth: "1.5", strokeLinecap: "round" }, /* @__PURE__ */ React.createElement("path", { d: "m4 4 8 8M12 4l-8 8" })))), /* @__PURE__ */ React.createElement("div", { className: "panel-body" }, ordered.length === 0 && /* @__PURE__ */ React.createElement("div", { style: { color: "var(--muted)", fontSize: 13, padding: "8px 4px" } }, "No sources cited yet. They'll appear here when Nikko references one."), ordered.map((s) => /* @__PURE__ */ React.createElement(
      "div",
      {
        key: s.key,
        className: `source-card ${activeKey === s.key ? "active" : ""}`,
        "data-anchor": `source-${s.key}`
      },
      /* @__PURE__ */ React.createElement("div", { className: "row" }, /* @__PURE__ */ React.createElement("span", { className: "num" }, s.num), /* @__PURE__ */ React.createElement("span", null, s.org)),
      /* @__PURE__ */ React.createElement("div", { className: "title" }, s.title),
      s.href && s.href !== "#" && /* @__PURE__ */ React.createElement("a", { className: "linkrow", href: s.href, target: "_blank", rel: "noopener noreferrer" }, s.href.replace(/^https?:\/\//, "").slice(0, 60), s.href.length > 67 ? "…" : ""),
      /* @__PURE__ */ React.createElement("div", { className: "blurb" }, s.blurb),
      s.apa && /* @__PURE__ */ React.createElement("div", { className: "apa" }, s.apa)
    ))));
  }
  function todayISO() {
    const d = /* @__PURE__ */ new Date();
    return d.toISOString().slice(0, 10);
  }
  function formatDay(iso) {
    const d = /* @__PURE__ */ new Date(iso + "T00:00:00");
    return d.toLocaleDateString(void 0, { weekday: "short", month: "short", day: "numeric" });
  }
  const EMOTION_OPTIONS = [
    "calm",
    "tired",
    "anxious",
    "low",
    "hopeful",
    "content",
    "irritable",
    "overwhelmed",
    "grateful",
    "numb",
    "lonely",
    "angry",
    "restless",
    "focused"
  ];
  const EMOTION_PRIMARY = 8;
  const TRIGGER_OPTIONS = [
    "work",
    "sleep",
    "family",
    "health",
    "money",
    "relationship",
    "study",
    "social",
    "news",
    "nothing specific"
  ];
  const TRIGGER_PRIMARY = 6;
  const MOOD_COLORS = ["#c95a5a", "#d77452", "#db8f4e", "#d4a352", "#c9b260", "#a9b76a", "#88b378", "#6aab83", "#4f9c8c", "#3d8a8e"];
  const JOURNAL_LIMIT = 4e3;
  const POMODORO_SECS = 10 * 60;
  function MoodDiaryPanel({ entries, onSet, onClose }) {
    const [selectedDay, setSelectedDay] = ps(todayISO());
    const e0 = entries[selectedDay] || { mood: 0, emotions: [], triggers: [], note: "", journal: "" };
    const [draftMood, setDraftMood] = ps(e0.mood || 0);
    const [draftEmotions, setDraftEmotions] = ps(e0.emotions || []);
    const [draftTriggers, setDraftTriggers] = ps(e0.triggers || []);
    const [draftNote, setDraftNote] = ps(e0.note || "");
    const [draftJournal, setDraftJournal] = ps(e0.journal || "");
    const [showAllEmotions, setShowAllEmotions] = ps(false);
    const [showAllTriggers, setShowAllTriggers] = ps(false);
    const [showReflection, setShowReflection] = ps(!!(e0.journal && e0.journal.trim()));
    pe(() => {
      const e = entries[selectedDay] || { mood: 0, emotions: [], triggers: [], note: "", journal: "" };
      setDraftMood(e.mood || 0);
      setDraftEmotions(e.emotions || []);
      setDraftTriggers(e.triggers || []);
      setDraftNote(e.note || "");
      setDraftJournal(e.journal || "");
      setShowReflection(!!(e.journal && e.journal.trim()));
      setShowAllEmotions(false);
      setShowAllTriggers(false);
    }, [selectedDay]);
    const [secsLeft, setSecsLeft] = ps(POMODORO_SECS);
    const [running, setRunning] = ps(false);
    pe(() => {
      if (!running) return;
      const t = setInterval(() => {
        setSecsLeft((s) => {
          if (s <= 1) {
            setRunning(false);
            return 0;
          }
          return s - 1;
        });
      }, 1e3);
      return () => clearInterval(t);
    }, [running]);
    const mm = String(Math.floor(secsLeft / 60)).padStart(2, "0");
    const ss = String(secsLeft % 60).padStart(2, "0");
    const days = Object.entries(entries).sort((a, b) => b[0].localeCompare(a[0]));
    const toggleIn = (arr, v) => arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v];
    const isEmpty = draftMood === 0 && draftEmotions.length === 0 && draftTriggers.length === 0 && !draftNote.trim() && !draftJournal.trim();
    const save = () => {
      if (isEmpty) return;
      onSet(selectedDay, {
        mood: draftMood,
        emotions: draftEmotions,
        triggers: draftTriggers,
        note: draftNote.trim(),
        journal: draftJournal.trim()
      });
    };
    const clearDay = () => {
      setDraftMood(0);
      setDraftEmotions([]);
      setDraftTriggers([]);
      setDraftNote("");
      setDraftJournal("");
      onSet(selectedDay, null);
    };
    const charsLeft = JOURNAL_LIMIT - draftJournal.length;
    return /* @__PURE__ */ React.createElement("aside", { className: "panel left", "aria-label": "Mood diary" }, /* @__PURE__ */ React.createElement("div", { className: "panel-head" }, /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("h3", null, "Mood diary"), /* @__PURE__ */ React.createElement("div", { className: "meta" }, "Stays on your device")), /* @__PURE__ */ React.createElement("button", { className: "iconbtn", onClick: onClose, "aria-label": "Close mood diary" }, /* @__PURE__ */ React.createElement("svg", { viewBox: "0 0 16 16", fill: "none", stroke: "currentColor", strokeWidth: "1.5", strokeLinecap: "round" }, /* @__PURE__ */ React.createElement("path", { d: "m4 4 8 8M12 4l-8 8" })))), /* @__PURE__ */ React.createElement("div", { className: "panel-body mood-body" }, /* @__PURE__ */ React.createElement("div", { className: "mood-day-stamp" }, formatDay(selectedDay), selectedDay === todayISO() ? " \xB7 today" : ""), /* @__PURE__ */ React.createElement("div", { className: "mood-section" }, /* @__PURE__ */ React.createElement("label", null, "How is today, overall?"), /* @__PURE__ */ React.createElement("div", { className: "mood-rating-row" }, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((n) => /* @__PURE__ */ React.createElement(
      "button",
      {
        key: n,
        className: `pip ${draftMood === n ? "on" : ""}`,
        "data-r": n,
        onClick: () => setDraftMood(n),
        "aria-label": `Mood ${n} of 10`
      },
      n
    ))), /* @__PURE__ */ React.createElement("div", { className: "mood-scale-ends" }, /* @__PURE__ */ React.createElement("span", null, "low"), /* @__PURE__ */ React.createElement("span", null, "good"))), /* @__PURE__ */ React.createElement("div", { className: "mood-section" }, /* @__PURE__ */ React.createElement("label", null, "A line about today"), /* @__PURE__ */ React.createElement(
      "textarea",
      {
        className: "mood-text",
        placeholder: "Just a sentence or two — optional.",
        value: draftNote,
        onChange: (e) => setDraftNote(e.target.value),
        rows: 2
      }
    )), /* @__PURE__ */ React.createElement("details", { className: "mood-disclosure", open: draftEmotions.length > 0 || draftTriggers.length > 0 }, /* @__PURE__ */ React.createElement("summary", null, /* @__PURE__ */ React.createElement("span", null, "Emotions & context"), /* @__PURE__ */ React.createElement("span", { className: "mood-disclosure-count" }, draftEmotions.length + draftTriggers.length || "")), /* @__PURE__ */ React.createElement("div", { className: "mood-section" }, /* @__PURE__ */ React.createElement("label", null, "Emotions"), /* @__PURE__ */ React.createElement("div", { className: "mood-chips" }, (showAllEmotions ? EMOTION_OPTIONS : EMOTION_OPTIONS.slice(0, EMOTION_PRIMARY)).map((em) => /* @__PURE__ */ React.createElement(
      "button",
      {
        key: em,
        className: `mood-chip ${draftEmotions.includes(em) ? "on" : ""}`,
        onClick: () => setDraftEmotions((arr) => toggleIn(arr, em))
      },
      em
    )), EMOTION_OPTIONS.length > EMOTION_PRIMARY && /* @__PURE__ */ React.createElement(
      "button",
      {
        className: "mood-chip ghost",
        onClick: () => setShowAllEmotions((v) => !v)
      },
      showAllEmotions ? "less" : `+${EMOTION_OPTIONS.length - EMOTION_PRIMARY} more`
    ))), /* @__PURE__ */ React.createElement("div", { className: "mood-section" }, /* @__PURE__ */ React.createElement("label", null, "What's around it"), /* @__PURE__ */ React.createElement("div", { className: "mood-chips" }, (showAllTriggers ? TRIGGER_OPTIONS : TRIGGER_OPTIONS.slice(0, TRIGGER_PRIMARY)).map((tr) => /* @__PURE__ */ React.createElement(
      "button",
      {
        key: tr,
        className: `mood-chip ${draftTriggers.includes(tr) ? "on" : ""}`,
        onClick: () => setDraftTriggers((arr) => toggleIn(arr, tr))
      },
      tr
    )), TRIGGER_OPTIONS.length > TRIGGER_PRIMARY && /* @__PURE__ */ React.createElement(
      "button",
      {
        className: "mood-chip ghost",
        onClick: () => setShowAllTriggers((v) => !v)
      },
      showAllTriggers ? "less" : `+${TRIGGER_OPTIONS.length - TRIGGER_PRIMARY} more`
    )))), !showReflection ? /* @__PURE__ */ React.createElement("button", { className: "mood-add-reflection", onClick: () => setShowReflection(true) }, /* @__PURE__ */ React.createElement("span", { className: "plus" }, "+"), /* @__PURE__ */ React.createElement("span", null, "Add a 10-minute reflection")) : /* @__PURE__ */ React.createElement("div", { className: "mood-section reflection-block" }, /* @__PURE__ */ React.createElement("div", { className: "reflection-head" }, /* @__PURE__ */ React.createElement("label", null, "Reflection"), /* @__PURE__ */ React.createElement("button", { className: "mood-link", onClick: () => {
      setShowReflection(false);
      setRunning(false);
    } }, "hide")), /* @__PURE__ */ React.createElement("div", { className: "pomodoro" }, /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("div", { className: `clock ${running && secsLeft < 60 ? "warn" : ""}` }, mm, ":", ss), /* @__PURE__ */ React.createElement("div", { className: "meta" }, running ? "writing…" : secsLeft === 0 ? "time up" : "paused")), /* @__PURE__ */ React.createElement("div", { style: { display: "flex", gap: 6 } }, !running && secsLeft > 0 && /* @__PURE__ */ React.createElement("button", { onClick: () => setRunning(true) }, secsLeft === POMODORO_SECS ? "Start" : "Resume"), running && /* @__PURE__ */ React.createElement("button", { onClick: () => setRunning(false) }, "Pause"), /* @__PURE__ */ React.createElement("button", { onClick: () => {
      setRunning(false);
      setSecsLeft(POMODORO_SECS);
    } }, "Reset"))), /* @__PURE__ */ React.createElement(
      "textarea",
      {
        className: "mood-text",
        placeholder: "Write freely. No one sees this but you.",
        value: draftJournal,
        onChange: (e) => setDraftJournal(e.target.value.slice(0, JOURNAL_LIMIT)),
        rows: 6,
        style: { minHeight: 120 }
      }
    ), /* @__PURE__ */ React.createElement("div", { className: `char-count ${charsLeft < 200 ? "warn" : ""}` }, draftJournal.length, " / ", JOURNAL_LIMIT)), /* @__PURE__ */ React.createElement("div", { className: "mood-actions" }, /* @__PURE__ */ React.createElement("button", { className: "btn-secondary", onClick: clearDay }, "Clear day"), /* @__PURE__ */ React.createElement("button", { className: "btn-primary", onClick: save, disabled: isEmpty }, "Save")), days.length > 0 && /* @__PURE__ */ React.createElement("div", { className: "mood-divider" }), days.length > 0 && /* @__PURE__ */ React.createElement("div", { className: "mood-past-head" }, "Past entries"), days.length === 0 && /* @__PURE__ */ React.createElement("div", { className: "mood-empty" }, "No entries yet. Today is a good place to start."), /* @__PURE__ */ React.createElement("div", { className: "mood-past-list" }, days.map(([iso, e]) => /* @__PURE__ */ React.createElement(
      "button",
      {
        key: iso,
        className: `mood-row ${selectedDay === iso ? "active" : ""}`,
        onClick: () => setSelectedDay(iso)
      },
      /* @__PURE__ */ React.createElement(
        "span",
        {
          className: "mood-row-dot",
          style: { background: e.mood ? MOOD_COLORS[e.mood - 1] : "var(--line)" },
          "aria-hidden": "true"
        }
      ),
      /* @__PURE__ */ React.createElement("span", { className: "mood-row-date" }, formatDay(iso)),
      /* @__PURE__ */ React.createElement("span", { className: "mood-row-summary" }, e.note ? e.note : e.emotions && e.emotions.length ? e.emotions.slice(0, 3).join(" \xB7 ") : e.journal ? "reflection saved" : "—"),
      /* @__PURE__ */ React.createElement("span", { className: "mood-row-score" }, e.mood ? e.mood : "—")
    )))));
  }
  const TUTORIAL_STEPS = [
    {
      title: "Welcome — is this your first time?",
      body: "Nikko is a quiet place to think out loud. Take 30 seconds to see what's here, or skip ahead any time.",
      features: null
    },
    {
      title: "What you can do here",
      body: "Four things sit around the conversation. Each one is opt-in, and nothing tracks you between sessions.",
      features: [
        { ico: "mem", title: "Personal Memory", body: "Optional encrypted memory file you keep on your device. Top-right." },
        { ico: "src", title: "Sources tab", body: "Right side. Anything Nikko cites links to a source with a summary and APA 7 reference." },
        { ico: "mood", title: "Mood diary", body: "Left side. A 1–5 scale and an optional note per day. Stored locally." },
        { ico: "exit", title: "Quick exit", body: "Top-right. One tap clears this session and navigates away." }
      ]
    },
    {
      title: "A few principles",
      body: "Nikko is a research preview. It's non-diagnostic, doesn't replace a clinician, and won't pretend to remember you between sessions unless you provide your own memory file.",
      features: null
    }
  ];
  function TutorialFeatureIcon({ kind }) {
    switch (kind) {
      case "mem":
        return /* @__PURE__ */ React.createElement("svg", { viewBox: "0 0 14 14", fill: "none", stroke: "currentColor", strokeWidth: "1.4", strokeLinecap: "round", strokeLinejoin: "round" }, /* @__PURE__ */ React.createElement("rect", { x: "2.5", y: "6", width: "9", height: "6.5", rx: "1.2" }), /* @__PURE__ */ React.createElement("path", { d: "M4.5 6V4a2.5 2.5 0 0 1 5 0v2" }));
      case "src":
        return /* @__PURE__ */ React.createElement("svg", { viewBox: "0 0 14 14", fill: "none", stroke: "currentColor", strokeWidth: "1.4", strokeLinecap: "round", strokeLinejoin: "round" }, /* @__PURE__ */ React.createElement("path", { d: "M3 2.5h6L11.5 5v6.5H3z" }), /* @__PURE__ */ React.createElement("path", { d: "M3 5.5h5M3 8h6M3 10.5h4" }));
      case "mood":
        return /* @__PURE__ */ React.createElement("svg", { viewBox: "0 0 14 14", fill: "none", stroke: "currentColor", strokeWidth: "1.4", strokeLinecap: "round", strokeLinejoin: "round" }, /* @__PURE__ */ React.createElement("rect", { x: "2", y: "3", width: "10", height: "9", rx: "1.4" }), /* @__PURE__ */ React.createElement("path", { d: "M2 5.5h10M5 2v3M9 2v3" }));
      case "exit":
        return /* @__PURE__ */ React.createElement("svg", { viewBox: "0 0 14 14", fill: "none", stroke: "currentColor", strokeWidth: "1.4", strokeLinecap: "round", strokeLinejoin: "round" }, /* @__PURE__ */ React.createElement("path", { d: "M8.5 2.5h-5v9h5" }), /* @__PURE__ */ React.createElement("path", { d: "M6 7h6" }), /* @__PURE__ */ React.createElement("path", { d: "m9.5 4.5 2.5 2.5-2.5 2.5" }));
      default:
        return null;
    }
  }
  function Tutorial({ open, onSkip, onDone }) {
    const [step, setStep] = ps(0);
    pe(() => {
      if (open) setStep(0);
    }, [open]);
    if (!open) return null;
    const s = TUTORIAL_STEPS[step];
    const isLast = step === TUTORIAL_STEPS.length - 1;
    return /* @__PURE__ */ React.createElement("div", { className: "tutorial-veil" }, /* @__PURE__ */ React.createElement("div", { className: "tutorial" }, /* @__PURE__ */ React.createElement("div", { className: "step-num" }, "Step ", step + 1, " of ", TUTORIAL_STEPS.length), /* @__PURE__ */ React.createElement("h2", null, s.title), /* @__PURE__ */ React.createElement("p", null, s.body), s.features && /* @__PURE__ */ React.createElement("div", { className: "feature-grid" }, s.features.map((f) => /* @__PURE__ */ React.createElement("div", { className: "feature", key: f.title }, /* @__PURE__ */ React.createElement("span", { className: "ico" }, /* @__PURE__ */ React.createElement(TutorialFeatureIcon, { kind: f.ico })), /* @__PURE__ */ React.createElement("h4", null, f.title), /* @__PURE__ */ React.createElement("p", null, f.body)))), /* @__PURE__ */ React.createElement("div", { className: "actions" }, /* @__PURE__ */ React.createElement("div", { className: "dots" }, TUTORIAL_STEPS.map((_, i) => /* @__PURE__ */ React.createElement("i", { key: i, className: i === step ? "on" : "" }))), /* @__PURE__ */ React.createElement("div", { className: "right-actions" }, /* @__PURE__ */ React.createElement("button", { className: "btn-secondary", onClick: onSkip }, "Skip"), step > 0 && /* @__PURE__ */ React.createElement("button", { className: "btn-secondary", onClick: () => setStep(step - 1) }, "Back"), !isLast && /* @__PURE__ */ React.createElement("button", { className: "btn-primary", onClick: () => setStep(step + 1) }, "Next"), isLast && /* @__PURE__ */ React.createElement("button", { className: "btn-primary", onClick: onDone }, "Get started")))));
  }
  Object.assign(window, { SourcesPanel, MoodDiaryPanel, Tutorial });
})();

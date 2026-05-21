const NIKKO_MEM_HEADER = "# Nikko Personal Memory File";
const NIKKO_MEM_FILE_MAGIC = "NIKKO-MEM-v1";
const NIKKO_MEM_EXT = ".nikko-mem.enc";
function makeEmptyMemoryMd({
  name = "",
  tone = "balanced",
  responseLength = "standard",
  inputLength = "standard",
  dontHelp = [],
  // array of selected DONT_HELP_OPTIONS keys
  dontHelpOther = "",
  currentContext = ""
} = {}) {
  const today = (/* @__PURE__ */ new Date()).toISOString().slice(0, 10);
  const DONT_HELP_LABELS = {
    minimise: 'Minimising ("others have it worse")',
    generic_health: 'Generic health advice ("just sleep more / exercise")',
    pro_redirects: "Frequent professional redirects",
    multi_questions: "Multiple questions at once"
  };
  const dontHelpLines = [
    ...dontHelp.map((k) => `- ${DONT_HELP_LABELS[k] || k}`),
    ...dontHelpOther.trim() ? [`- ${dontHelpOther.trim()}`] : []
  ].join("\n");
  const supportContent = [
    dontHelpLines ? `Things that don't help:
${dontHelpLines}` : null,
    currentContext.trim() ? `Current context:
${currentContext.trim()}` : null
  ].filter(Boolean).join("\n\n");
  return `${NIKKO_MEM_HEADER}
> Generated: ${today} | Version: 1.2

## Name
${name.trim()}

## User Preferences
tone: ${tone}
response_length: ${responseLength}
input_length: ${inputLength}

## Emotional Patterns
<!-- Derived from mood diary \u2014 updated when you regenerate your memory file -->

## Mood Diary
<!-- Timestamped entries: YYYY-MM-DD | mood: <descriptor> | energy: <optional> -->
<!-- note: <optional free-text> -->

## Helpful Interventions
<!-- Nikko will suggest entries here when it notices something helped -->

## Support Notes
${supportContent || "<!-- Specific guidance for how Nikko should respond to you -->"}
`;
}
function parseMemoryName(md) {
  if (!md) return "";
  const match = md.match(/^##\s*Name\s*\n([^\n#]*)/m);
  if (!match) return "";
  return match[1].trim();
}
function parseMemoryPrefs(md) {
  if (!md) return {};
  const match = md.match(/^##\s*User Preferences\s*\n([\s\S]*?)(?=\n##|$)/m);
  if (!match) return {};
  const prefs = {};
  for (const line of match[1].split("\n")) {
    const pair = line.match(/^([\w_]+):\s*(.+)$/);
    if (pair) prefs[pair[1]] = pair[2].trim();
  }
  return prefs;
}
const TONE_OPTIONS = [
  { value: "understanding", label: "Understanding", tooltip: "Nikko focuses on making you feel heard first. Validation over advice, unless you ask." },
  { value: "balanced", label: "Balanced", tooltip: "Nikko acknowledges what you're feeling and gently offers perspective when it fits." },
  { value: "practical", label: "Practical", tooltip: "Nikko keeps the empathy brief and moves toward what you can actually do." }
];
const LENGTH_OPTIONS = [
  { value: "brief", label: "Brief", tooltip: "2\u20133 sentences. Good if long replies feel overwhelming or you just need a quick check-in." },
  { value: "standard", label: "Standard", tooltip: "Nikko writes as much as the moment calls for. Works for most conversations." },
  { value: "detailed", label: "Detailed", tooltip: "Nikko unpacks things fully. Better when you want depth or are working something through." }
];
const INPUT_OPTIONS = [
  { value: "concise", label: "I get to the point", tooltip: "Nikko reads up to ~150 words of your message. Fast responses, best for short inputs." },
  { value: "standard", label: "Standard", tooltip: "Nikko reads up to ~300 words. Handles most conversations comfortably." },
  { value: "verbose", label: "I tend to ramble", tooltip: "Nikko reads up to ~600 words so nothing important gets cut off. Expect slightly longer waits." }
];
const DONT_HELP_OPTIONS = [
  { key: "minimise", label: 'Minimising ("others have it worse")' },
  { key: "generic_health", label: 'Generic health advice ("just sleep more / exercise")' },
  { key: "pro_redirects", label: "Frequent professional redirects" },
  { key: "multi_questions", label: "Multiple questions at once" }
];
function OptionPill({ value, current, onSelect, label, tooltip }) {
  return /* @__PURE__ */ React.createElement("div", { className: "opill-host" }, /* @__PURE__ */ React.createElement(
    "button",
    {
      type: "button",
      className: "opill" + (current === value ? " opill-active" : ""),
      onClick: () => onSelect(value),
      "aria-pressed": current === value
    },
    label
  ), tooltip && /* @__PURE__ */ React.createElement("div", { className: "opill-tip", role: "tooltip" }, tooltip));
}
function PillGroup({ label, value, onChange, options }) {
  return /* @__PURE__ */ React.createElement("div", { className: "pill-group" }, /* @__PURE__ */ React.createElement("div", { className: "pill-group-label" }, label), /* @__PURE__ */ React.createElement("div", { className: "pill-row" }, options.map((opt) => /* @__PURE__ */ React.createElement(
    OptionPill,
    {
      key: opt.value,
      value: opt.value,
      current: value,
      onSelect: onChange,
      label: opt.label,
      tooltip: opt.tooltip
    }
  ))));
}
async function deriveKey(password, salt) {
  const enc = new TextEncoder();
  const baseKey = await crypto.subtle.importKey(
    "raw",
    enc.encode(password),
    "PBKDF2",
    false,
    ["deriveKey"]
  );
  return crypto.subtle.deriveKey(
    { name: "PBKDF2", salt, iterations: 31e4, hash: "SHA-256" },
    baseKey,
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt", "decrypt"]
  );
}
function b64encode(buf) {
  const bytes = new Uint8Array(buf);
  let s = "";
  for (let i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
  return btoa(s);
}
function b64decode(s) {
  const raw = atob(s);
  const out = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}
async function encryptMemory(plaintext, password) {
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const key = await deriveKey(password, salt);
  const ct = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv },
    key,
    new TextEncoder().encode(plaintext)
  );
  const payload = {
    magic: NIKKO_MEM_FILE_MAGIC,
    kdf: "PBKDF2-SHA256",
    iter: 31e4,
    cipher: "AES-256-GCM",
    salt: b64encode(salt),
    iv: b64encode(iv),
    ct: b64encode(ct)
  };
  return `# Nikko Encrypted Memory (do not edit)
# Algorithm: AES-256-GCM \xB7 Key: PBKDF2-SHA256 (310,000 iters)
# Open this file only with Nikko.
${JSON.stringify(payload)}
`;
}
async function decryptMemory(fileText, password) {
  const line = fileText.split("\n").find((l) => l.trim().startsWith("{"));
  if (!line) throw new Error("Not a valid Nikko encrypted memory file.");
  let payload;
  try {
    payload = JSON.parse(line);
  } catch (e) {
    throw new Error("Could not parse memory file payload.");
  }
  if (payload.magic !== NIKKO_MEM_FILE_MAGIC) {
    throw new Error("Missing Nikko magic marker \u2014 this does not appear to be a Nikko memory file.");
  }
  const salt = b64decode(payload.salt);
  const iv = b64decode(payload.iv);
  const ct = b64decode(payload.ct);
  const key = await deriveKey(password, salt);
  try {
    const pt = await crypto.subtle.decrypt({ name: "AES-GCM", iv }, key, ct);
    return new TextDecoder().decode(pt);
  } catch (e) {
    throw new Error("Decryption failed. Wrong password, or the file has been tampered with.");
  }
}
async function decryptMemoryKeepKey(fileText, password) {
  const line = fileText.split("\n").find((l) => l.trim().startsWith("{"));
  if (!line) throw new Error("Not a valid Nikko encrypted memory file.");
  let payload;
  try {
    payload = JSON.parse(line);
  } catch (e) {
    throw new Error("Could not parse memory file payload.");
  }
  if (payload.magic !== NIKKO_MEM_FILE_MAGIC) {
    throw new Error("Missing Nikko magic marker \u2014 this does not appear to be a Nikko memory file.");
  }
  const salt = b64decode(payload.salt);
  const iv = b64decode(payload.iv);
  const ct = b64decode(payload.ct);
  const key = await deriveKey(password, salt);
  let pt;
  try {
    pt = await crypto.subtle.decrypt({ name: "AES-GCM", iv }, key, ct);
  } catch (e) {
    throw new Error("Decryption failed. Wrong password, or the file has been tampered with.");
  }
  const md = new TextDecoder().decode(pt);
  return { md, sessionKey: { key, salt } };
}
async function encryptMemoryWithKey(plaintext, sessionKey) {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ct = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv },
    sessionKey.key,
    new TextEncoder().encode(plaintext)
  );
  const payload = {
    magic: NIKKO_MEM_FILE_MAGIC,
    kdf: "PBKDF2-SHA256",
    iter: 31e4,
    cipher: "AES-256-GCM",
    salt: b64encode(sessionKey.salt),
    // original salt preserved
    iv: b64encode(iv),
    ct: b64encode(ct)
  };
  return `# Nikko Encrypted Memory (do not edit)
# Algorithm: AES-256-GCM \xB7 Key: PBKDF2-SHA256 (310,000 iters)
# Open this file only with Nikko.
${JSON.stringify(payload)}
`;
}
function applyMemoryEntry(md, section, entry) {
  const today = (/* @__PURE__ */ new Date()).toISOString().slice(0, 10);
  const safeEntry = entry.slice(0, 200);
  const dateLine = `${today} \u2014 ${safeEntry}`;
  const sectionRe = new RegExp(`(^##\\s*${section}\\s*$)`, "m");
  const match = md.match(sectionRe);
  if (!match) {
    return md.trimEnd() + `

## ${section}
${dateLine}
`;
  }
  const sectionStart = match.index + match[0].length;
  const nextSection = md.indexOf("\n##", sectionStart);
  const insertAt = nextSection === -1 ? md.length : nextSection;
  const sectionBody = md.slice(sectionStart, insertAt);
  const bodyWithoutPlaceholder = sectionBody.replace(/\n?<!-- [^>]* -->/g, "");
  return md.slice(0, sectionStart) + bodyWithoutPlaceholder.trimEnd() + `

${dateLine}
` + md.slice(insertAt);
}
function isValidMemoryMd(text) {
  return text.trimStart().startsWith(NIKKO_MEM_HEADER);
}
function downloadFile(name, content) {
  const blob = new Blob([content], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => {
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, 200);
}
function MemoryGenerateModal({ open, onClose, onCreated }) {
  const [step, setStep] = React.useState("disclosure");
  const [acked, setAcked] = React.useState(false);
  const [skipped, setSkipped] = React.useState(false);
  const [name, setName] = React.useState("");
  const [tone, setTone] = React.useState("balanced");
  const [responseLength, setRespLen] = React.useState("standard");
  const [inputLength, setInputLen] = React.useState("standard");
  const [dontHelp, setDontHelp] = React.useState([]);
  const [dontHelpOther, setDontHelpOther] = React.useState("");
  const [currentContext, setContext] = React.useState("");
  const [pw1, setPw1] = React.useState("");
  const [pw2, setPw2] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState("");
  React.useEffect(() => {
    if (open) {
      setStep("disclosure");
      setAcked(false);
      setSkipped(false);
      setName("");
      setTone("balanced");
      setRespLen("standard");
      setInputLen("standard");
      setDontHelp([]);
      setDontHelpOther("");
      setContext("");
      setPw1("");
      setPw2("");
      setErr("");
      setBusy(false);
    }
  }, [open]);
  if (!open) return null;
  const toggleDontHelp = (key) => setDontHelp((prev) => prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]);
  const generate = async () => {
    setErr("");
    if (pw1.length < 8) {
      setErr("Password must be at least 8 characters.");
      return;
    }
    if (pw1 !== pw2) {
      setErr("Passwords don't match.");
      return;
    }
    setBusy(true);
    try {
      const md = makeEmptyMemoryMd({
        name,
        tone,
        responseLength,
        inputLength,
        dontHelp,
        dontHelpOther,
        currentContext
      });
      const enc = await encryptMemory(md, pw1);
      downloadFile("nikko-memory" + NIKKO_MEM_EXT, enc);
      onCreated && onCreated(md);
      onClose();
    } catch (e) {
      setErr(e.message || "Could not create the file.");
    } finally {
      setBusy(false);
    }
  };
  const renderDisclosure = () => /* @__PURE__ */ React.createElement(React.Fragment, null, /* @__PURE__ */ React.createElement("h2", null, "Create your ", /* @__PURE__ */ React.createElement("em", null, "Personal Memory"), " file"), /* @__PURE__ */ React.createElement("p", { className: "lede" }, "Read this carefully. Your memory file lives only on your device \u2014 Nikko's servers will never receive it."), /* @__PURE__ */ React.createElement("ul", { className: "warn-list" }, /* @__PURE__ */ React.createElement("li", null, /* @__PURE__ */ React.createElement("strong", null, "Open-source encryption:"), " AES-256-GCM is robust under current standards, but no security guarantee is absolute."), /* @__PURE__ */ React.createElement("li", null, /* @__PURE__ */ React.createElement("strong", null, "Don't include identifying information"), " \u2014 full name, date of birth, government IDs, or anything that could identify you."), /* @__PURE__ */ React.createElement("li", null, /* @__PURE__ */ React.createElement("strong", null, "Store the file somewhere safe"), " \u2014 not in a shared drive or unencrypted backup."), /* @__PURE__ */ React.createElement("li", null, /* @__PURE__ */ React.createElement("strong", null, "Don't reuse a password"), " you use elsewhere."), /* @__PURE__ */ React.createElement("li", null, /* @__PURE__ */ React.createElement("strong", null, "If you lose your password, the file is unrecoverable."), " There is no reset.")), /* @__PURE__ */ React.createElement(
    "div",
    {
      className: `gate-attest ${acked ? "checked" : ""}`,
      onClick: () => setAcked((a) => !a),
      role: "checkbox",
      "aria-checked": acked,
      tabIndex: 0,
      onKeyDown: (e) => {
        if (e.key === " " || e.key === "Enter") {
          e.preventDefault();
          setAcked((a) => !a);
        }
      }
    },
    /* @__PURE__ */ React.createElement("span", { className: "check", "aria-hidden": "true" }, /* @__PURE__ */ React.createElement("svg", { viewBox: "0 0 12 12", fill: "none", stroke: "currentColor", strokeWidth: "2", strokeLinecap: "round", strokeLinejoin: "round" }, /* @__PURE__ */ React.createElement("path", { d: "M2.5 6.5 5 9l4.5-5.5" }))),
    /* @__PURE__ */ React.createElement("span", { className: "label" }, /* @__PURE__ */ React.createElement("strong", null, "I've read and understood the above."), /* @__PURE__ */ React.createElement("small", null, "I will safeguard the file and password myself."))
  ), /* @__PURE__ */ React.createElement("div", { className: "actions" }, /* @__PURE__ */ React.createElement("button", { className: "btn-secondary", onClick: onClose }, "Cancel"), /* @__PURE__ */ React.createElement("button", { className: "btn-primary", disabled: !acked, onClick: () => setStep("name-gate") }, "Continue")));
  const renderNameGate = () => /* @__PURE__ */ React.createElement(React.Fragment, null, /* @__PURE__ */ React.createElement("h2", null, "What should Nikko call you?"), /* @__PURE__ */ React.createElement("p", { className: "lede" }, "Completely optional. If you add your name, Nikko will use it naturally in conversation."), /* @__PURE__ */ React.createElement("div", { className: "input-row" }, /* @__PURE__ */ React.createElement("label", { htmlFor: "memname" }, "Name"), /* @__PURE__ */ React.createElement(
    "input",
    {
      id: "memname",
      type: "text",
      value: name,
      onChange: (e) => setName(e.target.value),
      autoFocus: true,
      placeholder: "e.g. Sam",
      maxLength: 60
    }
  )), /* @__PURE__ */ React.createElement("div", { className: "modal-gate-choice" }, /* @__PURE__ */ React.createElement(
    "div",
    {
      className: "modal-gate-label",
      onClick: () => {
        setSkipped(false);
        setStep("style");
      },
      role: "button",
      tabIndex: 0,
      onKeyDown: (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          setSkipped(false);
          setStep("style");
        }
      }
    },
    /* @__PURE__ */ React.createElement("span", { className: "modal-gate-icon" }, "\u2726"),
    /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("strong", null, "Personalise"), /* @__PURE__ */ React.createElement("div", { className: "modal-gate-hint" }, "Set your preferred tone, response style, and what you'd like Nikko to avoid."))
  ), /* @__PURE__ */ React.createElement(
    "div",
    {
      className: "modal-gate-label",
      onClick: () => {
        setSkipped(true);
        setStep("password");
      },
      role: "button",
      tabIndex: 0,
      onKeyDown: (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          setSkipped(true);
          setStep("password");
        }
      }
    },
    /* @__PURE__ */ React.createElement("span", { className: "modal-gate-icon" }, "\u2192"),
    /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("strong", null, "Skip to password"), /* @__PURE__ */ React.createElement("div", { className: "modal-gate-hint" }, "Use Nikko's defaults. You can personalise later by regenerating your file."))
  )), /* @__PURE__ */ React.createElement("div", { className: "actions" }, /* @__PURE__ */ React.createElement("button", { className: "btn-secondary", onClick: () => setStep("disclosure") }, "Back")));
  const renderStyle = () => /* @__PURE__ */ React.createElement(React.Fragment, null, /* @__PURE__ */ React.createElement("h2", null, "How should Nikko respond?"), /* @__PURE__ */ React.createElement("p", { className: "lede" }, "Hover each option to see what it means. You can update these later by regenerating your file."), /* @__PURE__ */ React.createElement(PillGroup, { label: "Tone", value: tone, onChange: setTone, options: TONE_OPTIONS }), /* @__PURE__ */ React.createElement(PillGroup, { label: "Response length", value: responseLength, onChange: setRespLen, options: LENGTH_OPTIONS }), /* @__PURE__ */ React.createElement(PillGroup, { label: "Your message style", value: inputLength, onChange: setInputLen, options: INPUT_OPTIONS }), inputLength === "verbose" && /* @__PURE__ */ React.createElement("p", { className: "pill-warn" }, "\u26A0 Reading longer messages takes a bit more time."), /* @__PURE__ */ React.createElement("div", { className: "actions" }, /* @__PURE__ */ React.createElement("button", { className: "btn-secondary", onClick: () => setStep("name-gate") }, "Back"), /* @__PURE__ */ React.createElement("button", { className: "btn-primary", onClick: () => setStep("support") }, "Continue")));
  const renderSupport = () => /* @__PURE__ */ React.createElement(React.Fragment, null, /* @__PURE__ */ React.createElement("h2", null, "Anything Nikko should know?"), /* @__PURE__ */ React.createElement("p", { className: "lede" }, "Both sections are optional. These help Nikko tailor its responses from the start."), /* @__PURE__ */ React.createElement("div", { className: "modal-section" }, /* @__PURE__ */ React.createElement("div", { className: "pill-group-label" }, "Things that don't help"), /* @__PURE__ */ React.createElement("ul", { className: "check-list" }, DONT_HELP_OPTIONS.map((opt) => /* @__PURE__ */ React.createElement(
    "li",
    {
      key: opt.key,
      className: `check-item ${dontHelp.includes(opt.key) ? "checked" : ""}`,
      onClick: () => toggleDontHelp(opt.key),
      role: "checkbox",
      "aria-checked": dontHelp.includes(opt.key),
      tabIndex: 0,
      onKeyDown: (e) => {
        if (e.key === " " || e.key === "Enter") {
          e.preventDefault();
          toggleDontHelp(opt.key);
        }
      }
    },
    /* @__PURE__ */ React.createElement("span", { className: "check", "aria-hidden": "true" }, /* @__PURE__ */ React.createElement("svg", { viewBox: "0 0 12 12", fill: "none", stroke: "currentColor", strokeWidth: "2", strokeLinecap: "round", strokeLinejoin: "round" }, /* @__PURE__ */ React.createElement("path", { d: "M2.5 6.5 5 9l4.5-5.5" }))),
    /* @__PURE__ */ React.createElement("span", null, opt.label)
  ))), /* @__PURE__ */ React.createElement("div", { className: "input-row", style: { marginTop: "0.5rem" } }, /* @__PURE__ */ React.createElement("label", { htmlFor: "dontHelpOther" }, "Anything else?"), /* @__PURE__ */ React.createElement(
    "input",
    {
      id: "dontHelpOther",
      type: "text",
      value: dontHelpOther,
      onChange: (e) => setDontHelpOther(e.target.value),
      placeholder: "e.g. Don't suggest breathing exercises",
      maxLength: 120
    }
  ))), /* @__PURE__ */ React.createElement("div", { className: "modal-section" }, /* @__PURE__ */ React.createElement("div", { className: "pill-group-label" }, "Current life context", " ", /* @__PURE__ */ React.createElement("span", { style: { fontWeight: 400, opacity: 0.6 } }, "(optional)")), /* @__PURE__ */ React.createElement(
    "textarea",
    {
      className: "modal-textarea",
      value: currentContext,
      onChange: (e) => setContext(e.target.value),
      placeholder: "e.g. Going through a career change, finding it hard to focus lately.",
      maxLength: 400,
      rows: 3
    }
  )), /* @__PURE__ */ React.createElement("div", { className: "actions" }, /* @__PURE__ */ React.createElement("button", { className: "btn-secondary", onClick: () => setStep("style") }, "Back"), /* @__PURE__ */ React.createElement("button", { className: "btn-primary", onClick: () => setStep("password") }, "Continue")));
  const renderPassword = () => /* @__PURE__ */ React.createElement(React.Fragment, null, /* @__PURE__ */ React.createElement("h2", null, "Set your password"), /* @__PURE__ */ React.createElement("p", { className: "lede" }, "This password derives the encryption key. It can't be reset \u2014 write it down somewhere safe before continuing."), err && /* @__PURE__ */ React.createElement("div", { className: "err" }, err), /* @__PURE__ */ React.createElement("div", { className: "input-row" }, /* @__PURE__ */ React.createElement("label", { htmlFor: "pw1" }, "Password"), /* @__PURE__ */ React.createElement("input", { id: "pw1", type: "password", value: pw1, onChange: (e) => setPw1(e.target.value), autoFocus: true, placeholder: "At least 8 characters" })), /* @__PURE__ */ React.createElement("div", { className: "input-row" }, /* @__PURE__ */ React.createElement("label", { htmlFor: "pw2" }, "Confirm password"), /* @__PURE__ */ React.createElement("input", { id: "pw2", type: "password", value: pw2, onChange: (e) => setPw2(e.target.value), placeholder: "Type it again" })), /* @__PURE__ */ React.createElement("div", { className: "actions" }, /* @__PURE__ */ React.createElement("button", { className: "btn-secondary", onClick: () => setStep(skipped ? "name-gate" : "support"), disabled: busy }, "Back"), /* @__PURE__ */ React.createElement("button", { className: "btn-primary", onClick: generate, disabled: busy }, busy ? "Generating\u2026" : "Generate & download")));
  return /* @__PURE__ */ React.createElement("div", { className: "modal-veil", onClick: onClose }, /* @__PURE__ */ React.createElement("div", { className: "modal", onClick: (e) => e.stopPropagation() }, step === "disclosure" && renderDisclosure(), step === "name-gate" && renderNameGate(), step === "style" && renderStyle(), step === "support" && renderSupport(), step === "password" && renderPassword()));
}
function MemoryLoadModal({ open, onClose, onLoaded }) {
  const [file, setFile] = React.useState(null);
  const [fileText, setFileText] = React.useState("");
  const [over, setOver] = React.useState(false);
  const [pw, setPw] = React.useState("");
  const [err, setErr] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const inputRef = React.useRef(null);
  React.useEffect(() => {
    if (open) {
      setFile(null);
      setFileText("");
      setPw("");
      setErr("");
      setBusy(false);
    }
  }, [open]);
  if (!open) return null;
  const handleFile = async (f) => {
    setErr("");
    if (!f) return;
    const name = f.name.toLowerCase();
    if (!name.endsWith(".md") && !name.endsWith(".enc")) {
      setErr("Unsupported file type. Please drop a .nikko-mem.enc or .md file.");
      return;
    }
    const text = await f.text();
    if (name.endsWith(".md")) {
      if (!isValidMemoryMd(text)) {
        setErr(`Not a valid Nikko memory file. The file must begin with "${NIKKO_MEM_HEADER}".`);
        return;
      }
    } else {
      if (!text.includes(NIKKO_MEM_FILE_MAGIC)) {
        setErr("This .enc file does not contain the Nikko memory marker.");
        return;
      }
    }
    setFile(f);
    setFileText(text);
  };
  const onDrop = (e) => {
    e.preventDefault();
    setOver(false);
    const f = e.dataTransfer.files && e.dataTransfer.files[0];
    if (f) handleFile(f);
  };
  const submit = async () => {
    if (!file) return;
    setBusy(true);
    setErr("");
    try {
      const isEnc2 = file.name.toLowerCase().endsWith(".enc");
      let md, sessionKey;
      if (isEnc2) {
        const result = await decryptMemoryKeepKey(fileText, pw);
        md = result.md;
        sessionKey = result.sessionKey;
      } else {
        md = fileText;
        sessionKey = null;
      }
      if (!isValidMemoryMd(md)) throw new Error("Decrypted content is not a Nikko memory file.");
      onLoaded(md, file.name, sessionKey);
      onClose();
    } catch (e) {
      setErr(e.message || "Could not load the file.");
    } finally {
      setBusy(false);
    }
  };
  const isEnc = file && file.name.toLowerCase().endsWith(".enc");
  return /* @__PURE__ */ React.createElement("div", { className: "modal-veil", onClick: onClose }, /* @__PURE__ */ React.createElement("div", { className: "modal", onClick: (e) => e.stopPropagation() }, /* @__PURE__ */ React.createElement("h2", null, "Load your ", /* @__PURE__ */ React.createElement("em", null, "memory"), " file"), /* @__PURE__ */ React.createElement("p", { className: "lede" }, "Drop your ", /* @__PURE__ */ React.createElement("code", null, ".nikko-mem.enc"), " file (or a plaintext ", /* @__PURE__ */ React.createElement("code", null, ".md"), " with the Nikko header). The file is decrypted in your browser only."), err && /* @__PURE__ */ React.createElement("div", { className: "err" }, err), /* @__PURE__ */ React.createElement(
    "input",
    {
      ref: inputRef,
      type: "file",
      accept: ".enc,.md",
      style: { display: "none" },
      onChange: (e) => handleFile(e.target.files && e.target.files[0])
    }
  ), /* @__PURE__ */ React.createElement(
    "div",
    {
      className: `dropzone ${over ? "over" : ""}`,
      onClick: () => inputRef.current && inputRef.current.click(),
      onDragOver: (e) => {
        e.preventDefault();
        setOver(true);
      },
      onDragLeave: () => setOver(false),
      onDrop,
      role: "button",
      tabIndex: 0
    },
    file ? /* @__PURE__ */ React.createElement(React.Fragment, null, "Loaded: ", /* @__PURE__ */ React.createElement("span", { className: "filename" }, file.name)) : /* @__PURE__ */ React.createElement(React.Fragment, null, "Drop a memory file here, or ", /* @__PURE__ */ React.createElement("strong", { style: { color: "var(--accent)" } }, "browse"), ".", /* @__PURE__ */ React.createElement("br", null), /* @__PURE__ */ React.createElement("span", { className: "filename" }, "Accepts .nikko-mem.enc \xB7 .md"))
  ), isEnc && /* @__PURE__ */ React.createElement("div", { className: "input-row" }, /* @__PURE__ */ React.createElement("label", { htmlFor: "loadpw" }, "Password"), /* @__PURE__ */ React.createElement("input", { id: "loadpw", type: "password", value: pw, onChange: (e) => setPw(e.target.value), autoFocus: true })), /* @__PURE__ */ React.createElement("div", { className: "actions" }, /* @__PURE__ */ React.createElement("button", { className: "btn-secondary", onClick: onClose, disabled: busy }, "Cancel"), /* @__PURE__ */ React.createElement("button", { className: "btn-primary", onClick: submit, disabled: !file || busy || isEnc && !pw }, busy ? "Decrypting\u2026" : "Load memory"))));
}
Object.assign(window, {
  NIKKO_MEM_HEADER,
  NIKKO_MEM_EXT,
  NIKKO_MEM_FILE_MAGIC,
  makeEmptyMemoryMd,
  encryptMemory,
  decryptMemory,
  isValidMemoryMd,
  downloadFile,
  parseMemoryName,
  parseMemoryPrefs,
  // New write-back helpers (SPEC-850 §9 steps 3 + 6):
  decryptMemoryKeepKey,
  encryptMemoryWithKey,
  applyMemoryEntry,
  MemoryGenerateModal,
  MemoryLoadModal
});

// memory.jsx — User Sovereign Memory (USM) crypto + UI per SPEC-850.
// All encryption is client-side via Web Crypto. Files are .nikko-mem.enc;
// plaintext fallback is .md but only valid if the header marker matches.

const NIKKO_MEM_HEADER = '# Nikko Personal Memory File';
const NIKKO_MEM_FILE_MAGIC = 'NIKKO-MEM-v1';
const NIKKO_MEM_EXT = '.nikko-mem.enc';

/**
 * Build the memory file Markdown from personalisation choices.
 * All parameters are optional — safe to call with no args for a blank template.
 */
function makeEmptyMemoryMd({
  name          = '',
  tone          = 'balanced',
  responseLength = 'standard',
  inputLength   = 'standard',
  dontHelp      = [],      // array of selected DONT_HELP_OPTIONS keys
  dontHelpOther = '',
  currentContext = '',
} = {}) {
  const today = new Date().toISOString().slice(0, 10);

  const DONT_HELP_LABELS = {
    minimise:        'Minimising ("others have it worse")',
    generic_health:  'Generic health advice ("just sleep more / exercise")',
    pro_redirects:   'Frequent professional redirects',
    multi_questions: 'Multiple questions at once',
  };

  const dontHelpLines = [
    ...dontHelp.map(k => `- ${DONT_HELP_LABELS[k] || k}`),
    ...(dontHelpOther.trim() ? [`- ${dontHelpOther.trim()}`] : []),
  ].join('\n');

  const supportContent = [
    dontHelpLines     ? `Things that don't help:\n${dontHelpLines}` : null,
    currentContext.trim() ? `Current context:\n${currentContext.trim()}`   : null,
  ].filter(Boolean).join('\n\n');

  return `${NIKKO_MEM_HEADER}
> Generated: ${today} | Version: 1.2

## Name
${name.trim()}

## User Preferences
tone: ${tone}
response_length: ${responseLength}
input_length: ${inputLength}

## Emotional Patterns
<!-- Derived from mood diary — updated when you regenerate your memory file -->

## Mood Diary
<!-- Timestamped entries: YYYY-MM-DD | mood: <descriptor> | energy: <optional> -->
<!-- note: <optional free-text> -->

## Helpful Interventions
<!-- Nikko will suggest entries here when it notices something helped -->

## Support Notes
${supportContent || '<!-- Specific guidance for how Nikko should respond to you -->'}
`;
}

/** Extract the Name field from a parsed memory Markdown string. Returns '' if absent. */
function parseMemoryName(md) {
  if (!md) return '';
  const match = md.match(/^##\s*Name\s*\n([^\n#]*)/m);
  if (!match) return '';
  return match[1].trim();
}

/**
 * Extract structured key:value pairs from the ## User Preferences section.
 * Returns an object, e.g. { tone: 'practical', response_length: 'brief', input_length: 'standard' }
 */
function parseMemoryPrefs(md) {
  if (!md) return {};
  const match = md.match(/^##\s*User Preferences\s*\n([\s\S]*?)(?=\n##|$)/m);
  if (!match) return {};
  const prefs = {};
  for (const line of match[1].split('\n')) {
    const pair = line.match(/^([\w_]+):\s*(.+)$/);
    if (pair) prefs[pair[1]] = pair[2].trim();
  }
  return prefs;
}

// ── Personalisation pill selector components ───────────────────────

const TONE_OPTIONS = [
  { value: 'understanding', label: 'Understanding', tooltip: 'Nikko focuses on making you feel heard first. Validation over advice, unless you ask.' },
  { value: 'balanced',      label: 'Balanced',      tooltip: "Nikko acknowledges what you're feeling and gently offers perspective when it fits." },
  { value: 'practical',     label: 'Practical',     tooltip: 'Nikko keeps the empathy brief and moves toward what you can actually do.' },
];
const LENGTH_OPTIONS = [
  { value: 'brief',    label: 'Brief',    tooltip: '2–3 sentences. Good if long replies feel overwhelming or you just need a quick check-in.' },
  { value: 'standard', label: 'Standard', tooltip: 'Nikko writes as much as the moment calls for. Works for most conversations.' },
  { value: 'detailed', label: 'Detailed', tooltip: 'Nikko unpacks things fully. Better when you want depth or are working something through.' },
];
const INPUT_OPTIONS = [
  { value: 'concise',  label: 'I get to the point', tooltip: 'Nikko reads up to ~150 words of your message. Fast responses, best for short inputs.' },
  { value: 'standard', label: 'Standard',            tooltip: 'Nikko reads up to ~300 words. Handles most conversations comfortably.' },
  { value: 'verbose',  label: 'I tend to ramble',    tooltip: 'Nikko reads up to ~600 words so nothing important gets cut off. Expect slightly longer waits.' },
];
const DONT_HELP_OPTIONS = [
  { key: 'minimise',        label: 'Minimising ("others have it worse")' },
  { key: 'generic_health',  label: 'Generic health advice ("just sleep more / exercise")' },
  { key: 'pro_redirects',   label: 'Frequent professional redirects' },
  { key: 'multi_questions', label: 'Multiple questions at once' },
];

function OptionPill({ value, current, onSelect, label, tooltip }) {
  return (
    <div className="opill-host">
      <button
        type="button"
        className={'opill' + (current === value ? ' opill-active' : '')}
        onClick={() => onSelect(value)}
        aria-pressed={current === value}
      >
        {label}
      </button>
      {tooltip && <div className="opill-tip" role="tooltip">{tooltip}</div>}
    </div>
  );
}

function PillGroup({ label, value, onChange, options }) {
  return (
    <div className="pill-group">
      <div className="pill-group-label">{label}</div>
      <div className="pill-row">
        {options.map(opt => (
          <OptionPill
            key={opt.value}
            value={opt.value}
            current={value}
            onSelect={onChange}
            label={opt.label}
            tooltip={opt.tooltip}
          />
        ))}
      </div>
    </div>
  );
}

// ── Web Crypto helpers ─────────────────────────────────────────────
async function deriveKey(password, salt) {
  const enc = new TextEncoder();
  const baseKey = await crypto.subtle.importKey(
    'raw', enc.encode(password), 'PBKDF2', false, ['deriveKey']
  );
  return crypto.subtle.deriveKey(
    { name: 'PBKDF2', salt, iterations: 310000, hash: 'SHA-256' },
    baseKey,
    { name: 'AES-GCM', length: 256 },
    false,
    ['encrypt', 'decrypt']
  );
}

function b64encode(buf) {
  const bytes = new Uint8Array(buf);
  let s = '';
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
    { name: 'AES-GCM', iv },
    key,
    new TextEncoder().encode(plaintext)
  );
  // File envelope: human-readable header + JSON payload (b64)
  const payload = {
    magic: NIKKO_MEM_FILE_MAGIC,
    kdf: 'PBKDF2-SHA256',
    iter: 310000,
    cipher: 'AES-256-GCM',
    salt: b64encode(salt),
    iv: b64encode(iv),
    ct: b64encode(ct),
  };
  return `# Nikko Encrypted Memory (do not edit)
# Algorithm: AES-256-GCM · Key: PBKDF2-SHA256 (310,000 iters)
# Open this file only with Nikko.
${JSON.stringify(payload)}
`;
}

async function decryptMemory(fileText, password) {
  // Find the JSON payload line
  const line = fileText.split('\n').find(l => l.trim().startsWith('{'));
  if (!line) throw new Error('Not a valid Nikko encrypted memory file.');
  let payload;
  try { payload = JSON.parse(line); }
  catch (e) { throw new Error('Could not parse memory file payload.'); }
  if (payload.magic !== NIKKO_MEM_FILE_MAGIC) {
    throw new Error('Missing Nikko magic marker — this does not appear to be a Nikko memory file.');
  }
  const salt = b64decode(payload.salt);
  const iv = b64decode(payload.iv);
  const ct = b64decode(payload.ct);
  const key = await deriveKey(password, salt);
  try {
    const pt = await crypto.subtle.decrypt({ name: 'AES-GCM', iv }, key, ct);
    return new TextDecoder().decode(pt);
  } catch (e) {
    throw new Error('Decryption failed. Wrong password, or the file has been tampered with.');
  }
}

// Validate plaintext .md is a Nikko memory file
function isValidMemoryMd(text) {
  return text.trimStart().startsWith(NIKKO_MEM_HEADER);
}

function downloadFile(name, content) {
  const blob = new Blob([content], { type: 'text/plain' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { document.body.removeChild(a); URL.revokeObjectURL(url); }, 200);
}

// ── Generate modal: 5-step personalisation flow ────────────────────
// Steps: disclosure → name-gate → style → support → password
// Users can skip personalisation at name-gate; Back from password
// returns to name-gate (skipped) or support (personalised).
function MemoryGenerateModal({ open, onClose, onCreated }) {
  const [step, setStep]                   = React.useState('disclosure');
  const [acked, setAcked]                 = React.useState(false);
  const [skipped, setSkipped]             = React.useState(false);   // true when "Skip to password" chosen
  const [name, setName]                   = React.useState('');
  const [tone, setTone]                   = React.useState('balanced');
  const [responseLength, setRespLen]      = React.useState('standard');
  const [inputLength, setInputLen]        = React.useState('standard');
  const [dontHelp, setDontHelp]           = React.useState([]);
  const [dontHelpOther, setDontHelpOther] = React.useState('');
  const [currentContext, setContext]      = React.useState('');
  const [pw1, setPw1]                     = React.useState('');
  const [pw2, setPw2]                     = React.useState('');
  const [busy, setBusy]                   = React.useState(false);
  const [err, setErr]                     = React.useState('');

  React.useEffect(() => {
    if (open) {
      setStep('disclosure'); setAcked(false); setSkipped(false);
      setName(''); setTone('balanced'); setRespLen('standard'); setInputLen('standard');
      setDontHelp([]); setDontHelpOther(''); setContext('');
      setPw1(''); setPw2(''); setErr(''); setBusy(false);
    }
  }, [open]);

  if (!open) return null;

  const toggleDontHelp = (key) =>
    setDontHelp(prev => prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key]);

  const generate = async () => {
    setErr('');
    if (pw1.length < 8) { setErr('Password must be at least 8 characters.'); return; }
    if (pw1 !== pw2)    { setErr("Passwords don't match."); return; }
    setBusy(true);
    try {
      const md = makeEmptyMemoryMd({
        name, tone, responseLength, inputLength,
        dontHelp, dontHelpOther, currentContext,
      });
      const enc = await encryptMemory(md, pw1);
      downloadFile('nikko-memory' + NIKKO_MEM_EXT, enc);
      onCreated && onCreated(md);
      onClose();
    } catch (e) {
      setErr(e.message || 'Could not create the file.');
    } finally {
      setBusy(false);
    }
  };

  // ── Step: Disclosure ──────────────────────────────────────────────
  const renderDisclosure = () => (
    <>
      <h2>Create your <em>Personal Memory</em> file</h2>
      <p className="lede">Read this carefully. Your memory file lives only on your device — Nikko's servers will never receive it.</p>
      <ul className="warn-list">
        <li><strong>Open-source encryption:</strong> AES-256-GCM is robust under current standards, but no security guarantee is absolute.</li>
        <li><strong>Don't include identifying information</strong> — full name, date of birth, government IDs, or anything that could identify you.</li>
        <li><strong>Store the file somewhere safe</strong> — not in a shared drive or unencrypted backup.</li>
        <li><strong>Don't reuse a password</strong> you use elsewhere.</li>
        <li><strong>If you lose your password, the file is unrecoverable.</strong> There is no reset.</li>
      </ul>
      <div
        className={`gate-attest ${acked ? 'checked' : ''}`}
        onClick={() => setAcked(a => !a)}
        role="checkbox"
        aria-checked={acked}
        tabIndex={0}
        onKeyDown={(e) => { if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); setAcked(a => !a); } }}
      >
        <span className="check" aria-hidden="true">
          <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M2.5 6.5 5 9l4.5-5.5" />
          </svg>
        </span>
        <span className="label">
          <strong>I've read and understood the above.</strong>
          <small>I will safeguard the file and password myself.</small>
        </span>
      </div>
      <div className="actions">
        <button className="btn-secondary" onClick={onClose}>Cancel</button>
        <button className="btn-primary" disabled={!acked} onClick={() => setStep('name-gate')}>Continue</button>
      </div>
    </>
  );

  // ── Step: Name + gate choice ──────────────────────────────────────
  const renderNameGate = () => (
    <>
      <h2>What should Nikko call you?</h2>
      <p className="lede">Completely optional. If you add your name, Nikko will use it naturally in conversation.</p>
      <div className="input-row">
        <label htmlFor="memname">Name</label>
        <input
          id="memname"
          type="text"
          value={name}
          onChange={e => setName(e.target.value)}
          autoFocus
          placeholder="e.g. Sam"
          maxLength={60}
        />
      </div>
      <div className="modal-gate-choice">
        <div
          className="modal-gate-label"
          onClick={() => { setSkipped(false); setStep('style'); }}
          role="button"
          tabIndex={0}
          onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSkipped(false); setStep('style'); } }}
        >
          <span className="modal-gate-icon">✦</span>
          <div>
            <strong>Personalise</strong>
            <div className="modal-gate-hint">Set your preferred tone, response style, and what you'd like Nikko to avoid.</div>
          </div>
        </div>
        <div
          className="modal-gate-label"
          onClick={() => { setSkipped(true); setStep('password'); }}
          role="button"
          tabIndex={0}
          onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSkipped(true); setStep('password'); } }}
        >
          <span className="modal-gate-icon">→</span>
          <div>
            <strong>Skip to password</strong>
            <div className="modal-gate-hint">Use Nikko's defaults. You can personalise later by regenerating your file.</div>
          </div>
        </div>
      </div>
      <div className="actions">
        <button className="btn-secondary" onClick={() => setStep('disclosure')}>Back</button>
      </div>
    </>
  );

  // ── Step: Style (tone + lengths) ──────────────────────────────────
  const renderStyle = () => (
    <>
      <h2>How should Nikko respond?</h2>
      <p className="lede">Hover each option to see what it means. You can update these later by regenerating your file.</p>
      <PillGroup label="Tone" value={tone} onChange={setTone} options={TONE_OPTIONS} />
      <PillGroup label="Response length" value={responseLength} onChange={setRespLen} options={LENGTH_OPTIONS} />
      <PillGroup label="Your message style" value={inputLength} onChange={setInputLen} options={INPUT_OPTIONS} />
      {inputLength === 'verbose' && (
        <p className="pill-warn">⚠ Reading longer messages takes a bit more time.</p>
      )}
      <div className="actions">
        <button className="btn-secondary" onClick={() => setStep('name-gate')}>Back</button>
        <button className="btn-primary" onClick={() => setStep('support')}>Continue</button>
      </div>
    </>
  );

  // ── Step: Support preferences ─────────────────────────────────────
  const renderSupport = () => (
    <>
      <h2>Anything Nikko should know?</h2>
      <p className="lede">Both sections are optional. These help Nikko tailor its responses from the start.</p>
      <div className="modal-section">
        <div className="pill-group-label">Things that don't help</div>
        <ul className="check-list">
          {DONT_HELP_OPTIONS.map(opt => (
            <li
              key={opt.key}
              className={`check-item ${dontHelp.includes(opt.key) ? 'checked' : ''}`}
              onClick={() => toggleDontHelp(opt.key)}
              role="checkbox"
              aria-checked={dontHelp.includes(opt.key)}
              tabIndex={0}
              onKeyDown={e => { if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); toggleDontHelp(opt.key); } }}
            >
              <span className="check" aria-hidden="true">
                <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M2.5 6.5 5 9l4.5-5.5" />
                </svg>
              </span>
              <span>{opt.label}</span>
            </li>
          ))}
        </ul>
        <div className="input-row" style={{ marginTop: '0.5rem' }}>
          <label htmlFor="dontHelpOther">Anything else?</label>
          <input
            id="dontHelpOther"
            type="text"
            value={dontHelpOther}
            onChange={e => setDontHelpOther(e.target.value)}
            placeholder="e.g. Don't suggest breathing exercises"
            maxLength={120}
          />
        </div>
      </div>
      <div className="modal-section">
        <div className="pill-group-label">
          Current life context{' '}
          <span style={{ fontWeight: 400, opacity: 0.6 }}>(optional)</span>
        </div>
        <textarea
          className="modal-textarea"
          value={currentContext}
          onChange={e => setContext(e.target.value)}
          placeholder="e.g. Going through a career change, finding it hard to focus lately."
          maxLength={400}
          rows={3}
        />
      </div>
      <div className="actions">
        <button className="btn-secondary" onClick={() => setStep('style')}>Back</button>
        <button className="btn-primary" onClick={() => setStep('password')}>Continue</button>
      </div>
    </>
  );

  // ── Step: Password ────────────────────────────────────────────────
  const renderPassword = () => (
    <>
      <h2>Set your password</h2>
      <p className="lede">This password derives the encryption key. It can't be reset — write it down somewhere safe before continuing.</p>
      {err && <div className="err">{err}</div>}
      <div className="input-row">
        <label htmlFor="pw1">Password</label>
        <input id="pw1" type="password" value={pw1} onChange={e => setPw1(e.target.value)} autoFocus placeholder="At least 8 characters" />
      </div>
      <div className="input-row">
        <label htmlFor="pw2">Confirm password</label>
        <input id="pw2" type="password" value={pw2} onChange={e => setPw2(e.target.value)} placeholder="Type it again" />
      </div>
      <div className="actions">
        {/* Back destination: name-gate if skipped personalisation, support if not */}
        <button className="btn-secondary" onClick={() => setStep(skipped ? 'name-gate' : 'support')} disabled={busy}>Back</button>
        <button className="btn-primary" onClick={generate} disabled={busy}>
          {busy ? 'Generating…' : 'Generate & download'}
        </button>
      </div>
    </>
  );

  return (
    <div className="modal-veil" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        {step === 'disclosure' && renderDisclosure()}
        {step === 'name-gate'  && renderNameGate()}
        {step === 'style'      && renderStyle()}
        {step === 'support'    && renderSupport()}
        {step === 'password'   && renderPassword()}
      </div>
    </div>
  );
}

// ── Load modal: dropzone + password ────────────────────────────────
function MemoryLoadModal({ open, onClose, onLoaded }) {
  const [file, setFile] = React.useState(null);
  const [fileText, setFileText] = React.useState('');
  const [over, setOver] = React.useState(false);
  const [pw, setPw] = React.useState('');
  const [err, setErr] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const inputRef = React.useRef(null);

  React.useEffect(() => {
    if (open) { setFile(null); setFileText(''); setPw(''); setErr(''); setBusy(false); }
  }, [open]);

  if (!open) return null;

  const handleFile = async (f) => {
    setErr('');
    if (!f) return;
    const name = f.name.toLowerCase();
    if (!name.endsWith('.md') && !name.endsWith('.enc')) {
      setErr('Unsupported file type. Please drop a .nikko-mem.enc or .md file.');
      return;
    }
    const text = await f.text();
    if (name.endsWith('.md')) {
      // Plaintext: must have header marker
      if (!isValidMemoryMd(text)) {
        setErr(`Not a valid Nikko memory file. The file must begin with "${NIKKO_MEM_HEADER}".`);
        return;
      }
    } else {
      // .enc file — verify magic before asking for password
      if (!text.includes(NIKKO_MEM_FILE_MAGIC)) {
        setErr('This .enc file does not contain the Nikko memory marker.');
        return;
      }
    }
    setFile(f);
    setFileText(text);
  };

  const onDrop = (e) => {
    e.preventDefault(); setOver(false);
    const f = e.dataTransfer.files && e.dataTransfer.files[0];
    if (f) handleFile(f);
  };

  const submit = async () => {
    if (!file) return;
    setBusy(true); setErr('');
    try {
      const isEnc = file.name.toLowerCase().endsWith('.enc');
      const md = isEnc ? await decryptMemory(fileText, pw) : fileText;
      if (!isValidMemoryMd(md)) throw new Error('Decrypted content is not a Nikko memory file.');
      onLoaded(md, file.name);
      onClose();
    } catch (e) {
      setErr(e.message || 'Could not load the file.');
    } finally {
      setBusy(false);
    }
  };

  const isEnc = file && file.name.toLowerCase().endsWith('.enc');

  return (
    <div className="modal-veil" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <h2>Load your <em>memory</em> file</h2>
        <p className="lede">Drop your <code>.nikko-mem.enc</code> file (or a plaintext <code>.md</code> with the Nikko header). The file is decrypted in your browser only.</p>
        {err && <div className="err">{err}</div>}
        <input
          ref={inputRef}
          type="file"
          accept=".enc,.md"
          style={{ display: 'none' }}
          onChange={(e) => handleFile(e.target.files && e.target.files[0])}
        />
        <div
          className={`dropzone ${over ? 'over' : ''}`}
          onClick={() => inputRef.current && inputRef.current.click()}
          onDragOver={(e) => { e.preventDefault(); setOver(true); }}
          onDragLeave={() => setOver(false)}
          onDrop={onDrop}
          role="button"
          tabIndex={0}
        >
          {file ? (
            <>
              Loaded: <span className="filename">{file.name}</span>
            </>
          ) : (
            <>Drop a memory file here, or <strong style={{ color: 'var(--accent)' }}>browse</strong>.<br /><span className="filename">Accepts .nikko-mem.enc · .md</span></>
          )}
        </div>
        {isEnc && (
          <div className="input-row">
            <label htmlFor="loadpw">Password</label>
            <input id="loadpw" type="password" value={pw} onChange={e => setPw(e.target.value)} autoFocus />
          </div>
        )}
        <div className="actions">
          <button className="btn-secondary" onClick={onClose} disabled={busy}>Cancel</button>
          <button className="btn-primary" onClick={submit} disabled={!file || busy || (isEnc && !pw)}>
            {busy ? 'Decrypting…' : 'Load memory'}
          </button>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, {
  NIKKO_MEM_HEADER, NIKKO_MEM_EXT, NIKKO_MEM_FILE_MAGIC,
  makeEmptyMemoryMd, encryptMemory, decryptMemory, isValidMemoryMd, downloadFile,
  parseMemoryName, parseMemoryPrefs,
  MemoryGenerateModal, MemoryLoadModal,
});

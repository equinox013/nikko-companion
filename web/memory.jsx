// memory.jsx — User Sovereign Memory (USM) crypto + UI per SPEC-850.
// All encryption is client-side via Web Crypto. Files are .nikko-mem.enc;
// plaintext fallback is .md but only valid if the header marker matches.

const NIKKO_MEM_HEADER = '# Nikko Personal Memory File';
const NIKKO_MEM_FILE_MAGIC = 'NIKKO-MEM-v1';
const NIKKO_MEM_EXT = '.nikko-mem.enc';

function makeEmptyMemoryMd(name = '') {
  const today = new Date().toISOString().slice(0, 10);
  const nameLine = name.trim() ? name.trim() : '';
  return `${NIKKO_MEM_HEADER}
> Generated: ${today} | Version: 1.1

## Name
${nameLine}

## User Preferences
<!-- Tone, communication style, what user wants Nikko to know about how they prefer to interact -->

## Emotional Patterns
<!-- Recurring themes, known triggers, self-reported patterns -->

## Mood Diary
<!-- Timestamped entries: YYYY-MM-DD | mood: <descriptor> | energy: <optional> -->
<!-- note: <optional free-text approved by user> -->

## Helpful Interventions
<!-- Coping strategies and responses the user has found effective -->

## Support Notes
<!-- Specific guidance for Nikko's response style based on user experience -->
`;
}

/** Extract the Name field from a parsed memory Markdown string. Returns '' if absent. */
function parseMemoryName(md) {
  if (!md) return '';
  const match = md.match(/^##\s*Name\s*\n([^\n#]*)/m);
  if (!match) return '';
  return match[1].trim();
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

// ── Generate modal: disclosure + password ──────────────────────────
function MemoryGenerateModal({ open, onClose, onCreated }) {
  const [step, setStep] = React.useState('disclosure'); // disclosure | password
  const [acked, setAcked] = React.useState(false);
  const [name, setName] = React.useState('');
  const [pw1, setPw1] = React.useState('');
  const [pw2, setPw2] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState('');

  React.useEffect(() => {
    if (open) { setStep('disclosure'); setAcked(false); setName(''); setPw1(''); setPw2(''); setErr(''); setBusy(false); }
  }, [open]);

  if (!open) return null;

  const generate = async () => {
    setErr('');
    if (pw1.length < 8) { setErr('Password must be at least 8 characters.'); return; }
    if (pw1 !== pw2) { setErr('Passwords don\'t match.'); return; }
    setBusy(true);
    try {
      const md = makeEmptyMemoryMd(name);
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

  return (
    <div className="modal-veil" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        {step === 'disclosure' ? (
          <>
            <h2>Create your <em>Personal Memory</em> file</h2>
            <p className="lede">Read this disclaimer carefully. Your memory file lives only on your device — Nikko's servers will never receive it.</p>
            <ul className="warn-list">
              <li><strong>Open-source encryption:</strong> the implementation is publicly visible. AES-256-GCM is robust under current standards, but no security guarantee is absolute.</li>
              <li><strong>Don't include identifying information</strong> — full name, date of birth, government IDs, contact details, anything that could identify you.</li>
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
              <button className="btn-primary" disabled={!acked} onClick={() => setStep('password')}>Continue</button>
            </div>
          </>
        ) : (
          <>
            <h2>Set your password</h2>
            <p className="lede">This password derives the encryption key. It can't be reset — write it down somewhere safe before continuing.</p>
            {err && <div className="err">{err}</div>}
            <div className="input-row">
              <label htmlFor="memname">Your name <span style={{ fontWeight: 400, opacity: 0.6 }}>(optional)</span></label>
              <input id="memname" type="text" value={name} onChange={e => setName(e.target.value)} autoFocus placeholder="What should Nikko call you?" maxLength={60} />
            </div>
            <div className="input-row">
              <label htmlFor="pw1">Password</label>
              <input id="pw1" type="password" value={pw1} onChange={e => setPw1(e.target.value)} placeholder="At least 8 characters" />
            </div>
            <div className="input-row">
              <label htmlFor="pw2">Confirm password</label>
              <input id="pw2" type="password" value={pw2} onChange={e => setPw2(e.target.value)} placeholder="Type it again" />
            </div>
            <div className="actions">
              <button className="btn-secondary" onClick={() => setStep('disclosure')} disabled={busy}>Back</button>
              <button className="btn-primary" onClick={generate} disabled={busy}>
                {busy ? 'Generating…' : 'Generate & download'}
              </button>
            </div>
          </>
        )}
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
  parseMemoryName,
  MemoryGenerateModal, MemoryLoadModal,
});

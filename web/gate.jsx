// gate.jsx — Welcome / consent gate. Single screen, all four disclosures stacked,
// 18+ self-attestation checkbox required before "Enter".

const GATE_DISCLOSURES = [
  {
    icon: 'au',
    title: 'Australia only',
    body: 'Nikko is currently available in Australia. Crisis resources shown are Australian services.',
  },
  {
    icon: 'lang',
    title: 'English only',
    body: 'Nikko can only interpret and respond in English. Other languages are not supported in this preview.',
  },
  {
    icon: 'lock',
    title: 'Private by design',
    body: 'No user data is collected, stored, or used for training. Your messages stay between you and the model for the length of this session.',
  },
  {
    icon: 'session',
    title: 'Session-scoped',
    body: 'Your conversation is private and will be cleared if you close or refresh this page.',
  },
  {
    icon: 'beaker',
    title: 'Research preview',
    body: 'Nikko is a non-diagnostic wellbeing companion. It does not replace a clinician, and it cannot make care decisions on your behalf.',
  },
];

function GateIcon({ kind }) {
  switch (kind) {
    case 'au':
      return (
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M8 1.5C5 4.5 4 6.5 4 9a4 4 0 0 0 8 0c0-2.5-1-4.5-4-7.5z" />
        </svg>
      );
    case 'lang':
      return (
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M2.5 4.5h6" />
          <path d="M5.5 3.5v1" />
          <path d="M3.5 4.5c0 2.2 1.6 4 3.5 4.5" />
          <path d="M7.5 4.5c-.2 1.6-1.4 2.9-3 3.7" />
          <path d="M9 13.5 11.5 8l2.5 5.5" />
          <path d="M9.7 12h3.6" />
        </svg>
      );
    case 'lock':
      return (
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <rect x="3" y="7" width="10" height="7" rx="1.5" />
          <path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2" />
        </svg>
      );
    case 'session':
      return (
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M2.5 8a5.5 5.5 0 1 0 1.6-3.9" />
          <path d="M2 3v3h3" />
        </svg>
      );
    case 'beaker':
      return (
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M6 2v4.5L3 12.5A1.5 1.5 0 0 0 4.4 14.5h7.2A1.5 1.5 0 0 0 13 12.5L10 6.5V2" />
          <path d="M5 2h6" />
        </svg>
      );
    default:
      return null;
  }
}

function Gate({ onEnter }) {
  const [checked, setChecked] = React.useState(false);
  return (
    <div className="gate" role="dialog" aria-modal="true" aria-labelledby="gate-title">
      <div className="gate-card">
        <div className="gate-mark">
          <NikkoAvatar emotion="calm" size={84} />
        </div>
        <h1 id="gate-title" className="gate-title">Welcome to <em>Nikko</em></h1>
        <p className="gate-sub">A quiet place to think out loud. Please read the following before we begin.</p>

        <div className="gate-list">
          {GATE_DISCLOSURES.map((d) => (
            <div className="gate-item" key={d.title}>
              <span className="glyph"><GateIcon kind={d.icon} /></span>
              <div>
                <h4>{d.title}</h4>
                <p>{d.body}</p>
              </div>
            </div>
          ))}
        </div>

        <div
          className={`gate-attest ${checked ? 'checked' : ''}`}
          onClick={() => setChecked(c => !c)}
          role="checkbox"
          aria-checked={checked}
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); setChecked(c => !c); }
          }}
        >
          <span className="check" aria-hidden="true">
            <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M2.5 6.5 5 9l4.5-5.5" />
            </svg>
          </span>
          <span className="label">
            <strong>I confirm I am 18 or older and have read the above.</strong>
            <small>If you are in immediate danger, please call 000 (Australia) or Lifeline 13 11 14.</small>
          </span>
        </div>

        <button
          type="button"
          className="gate-cta"
          disabled={!checked}
          onClick={() => checked && onEnter()}
        >
          Enter the conversation
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
            <path d="M2.5 7h9" />
            <path d="M8 3.5 11.5 7 8 10.5" />
          </svg>
        </button>

        <div className="gate-foot">
          Research preview · Australia ·{' '}
          <a href="eula.html" target="_blank" rel="noopener noreferrer">Terms of Use</a>
          {' '}·{' '}
          <a href="privacy.html" target="_blank" rel="noopener noreferrer">Privacy Policy</a>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { Gate });

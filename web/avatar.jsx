// avatar.jsx — Sun avatar. Single warm sun palette (#CE844C).
// IDLE state ('calm' / 'idle') shows the sun body only — no glyph, no animation.
// Glyphs and animation appear only when Nikko is actively doing something
// (listening, thinking, searching, speaking, caring).

const NIKKO_SUN = '#CE844C';

const NIKKO_EMOTIONS = {
  // idle — sun body only, no glyph, no ray motion
  calm:    { rays: 'idle',  glyph: null,         active: false },
  idle:    { rays: 'idle',  glyph: null,         active: false },
  // active states
  listen:  { rays: 'idle',  glyph: 'question',   active: true },
  search:  { rays: 'spin',  glyph: 'squiggle',   active: true },
  speak:   { rays: 'pulse', glyph: 'smile',      active: true },
  care:    { rays: 'idle',  glyph: 'softsmile',  active: true },
  think:   { rays: 'pulse', glyph: 'pulse',      active: true },
};

// Pre-computed ray endpoints around a 32-radius ring at center (40,40)
const RAYS = (() => {
  const out = [];
  const N = 12;
  for (let i = 0; i < N; i++) {
    const a = (i / N) * Math.PI * 2 - Math.PI / 2;
    const r1 = 22, r2 = 30;
    out.push({
      x1: 40 + Math.cos(a) * r1,
      y1: 40 + Math.sin(a) * r1,
      x2: 40 + Math.cos(a) * r2,
      y2: 40 + Math.sin(a) * r2,
      key: i,
    });
  }
  return out;
})();

function NikkoGlyph({ kind }) {
  if (!kind) return null;
  switch (kind) {
    case 'smile':
      return (
        <path d="M34.5 40 Q40 45.5 45.5 40" stroke="currentColor"
              strokeWidth="2" strokeLinecap="round" fill="none" />
      );
    case 'softsmile':
      return (
        <path d="M35 40.5 Q40 43.6 45 40.5" stroke="currentColor"
              strokeWidth="1.8" strokeLinecap="round" fill="none" />
      );
    case 'question':
      return (
        <g fill="currentColor">
          <path d="M37.4 37.6 Q37.4 35.4 39.6 35.4 Q41.8 35.4 41.8 37.2 Q41.8 38.4 40.7 39.2 Q39.7 39.9 39.7 41.4"
                stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" fill="none" />
          <circle cx="39.7" cy="43.8" r="1.05" />
        </g>
      );
    case 'squiggle':
      return (
        <path d="M33 40 Q35.5 37.5 38 40 T43 40 T48 40" stroke="currentColor"
              strokeWidth="1.8" strokeLinecap="round" fill="none">
          <animate attributeName="d"
                   values="M33 40 Q35.5 37.5 38 40 T43 40 T48 40;
                           M33 40 Q35.5 42.5 38 40 T43 40 T48 40;
                           M33 40 Q35.5 37.5 38 40 T43 40 T48 40"
                   dur="1.4s" repeatCount="indefinite" />
        </path>
      );
    case 'pulse':
      return (
        <g fill="currentColor">
          <circle cx="36" cy="40" r="1.2">
            <animate attributeName="opacity" values="0.3;1;0.3" dur="1.4s" begin="0s" repeatCount="indefinite" />
          </circle>
          <circle cx="40" cy="40" r="1.2">
            <animate attributeName="opacity" values="0.3;1;0.3" dur="1.4s" begin="0.2s" repeatCount="indefinite" />
          </circle>
          <circle cx="44" cy="40" r="1.2">
            <animate attributeName="opacity" values="0.3;1;0.3" dur="1.4s" begin="0.4s" repeatCount="indefinite" />
          </circle>
        </g>
      );
    default:
      return null;
  }
}

function NikkoAvatar({ emotion = 'calm', size = 36, style: styleProp, showHalo = true }) {
  const e = NIKKO_EMOTIONS[emotion] || NIKKO_EMOTIONS.calm;
  const id = React.useId();
  const sun = NIKKO_SUN;
  const dur = e.rays === 'spin' ? '8s' : '0s';
  const animate = e.rays === 'spin';
  const showRays = e.active; // rays visible only when active

  return (
    <span className="sun-mark" style={{ width: size, height: size, ...styleProp }}>
      <svg viewBox="0 0 80 80" width={size} height={size} aria-hidden="true"
           style={{ display: 'block', overflow: 'visible' }}>
        <defs>
          <radialGradient id={`g-${id}`} cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor={sun} stopOpacity="0.5" />
            <stop offset="55%" stopColor={sun} stopOpacity="0.18" />
            <stop offset="100%" stopColor={sun} stopOpacity="0" />
          </radialGradient>
          <radialGradient id={`s-${id}`} cx="50%" cy="40%" r="65%">
            <stop offset="0%" stopColor={sun} stopOpacity="1" />
            <stop offset="100%" stopColor={sun} stopOpacity="0.7" />
          </radialGradient>
        </defs>
        {showHalo && (
          <circle cx="40" cy="40" r="38" fill={`url(#g-${id})`}>
            {e.active && (
              <animate attributeName="r" values="34;40;34" dur="3.8s" repeatCount="indefinite" />
            )}
          </circle>
        )}
        {/* rays — only when active */}
        {showRays && (
          <g style={animate
              ? { transformOrigin: '40px 40px', animation: `nikko-spin ${dur} linear infinite` }
              : { transformOrigin: '40px 40px' }}>
            {RAYS.map(r => (
              <line key={r.key} x1={r.x1} y1={r.y1} x2={r.x2} y2={r.y2}
                    stroke={sun} strokeWidth="1.6" strokeLinecap="round" opacity="0.85">
                {e.rays === 'pulse' && (
                  <animate attributeName="opacity"
                           values="0.4;0.95;0.4" dur="2.4s"
                           begin={`${r.key * 0.08}s`} repeatCount="indefinite" />
                )}
              </line>
            ))}
          </g>
        )}
        {/* sun body — always shown */}
        <circle cx="40" cy="40" r="16" fill={`url(#s-${id})`} stroke={sun} strokeWidth="0.8" strokeOpacity="0.6" />
        {/* inner glyph — only when active */}
        {e.glyph && (
          <g style={{ color: 'rgba(255,255,255,0.95)' }}>
            <NikkoGlyph kind={e.glyph} />
          </g>
        )}
      </svg>
    </span>
  );
}

if (typeof document !== 'undefined' && !document.getElementById('nikko-avatar-kf')) {
  const s = document.createElement('style');
  s.id = 'nikko-avatar-kf';
  s.textContent = `@keyframes nikko-spin { from { transform: rotate(0); } to { transform: rotate(360deg); } }`;
  document.head.appendChild(s);
}

Object.assign(window, { NikkoAvatar, NIKKO_EMOTIONS, NIKKO_SUN });

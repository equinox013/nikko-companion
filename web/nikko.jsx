// nikko.jsx — Root app. Always starts in light mode unless user previously
// chose dark and clicks the toggle next session.

const NIKKO_DECOR_BUBBLES = [
  ['L',  3, 12, 22, 30,  0,  false], ['L',  9,  4, 14, 24,  6,  true ],
  ['L',  2, 28, 30, 38, 12,  false], ['L', 12, 18, 18, 28, 18,  true ],
  ['L',  5, 42, 26, 34,  3,  false], ['L', 10, 60, 12, 22, 22,  true ],
  ['L',  4, 76, 20, 32,  9,  false], ['R',  4,  8, 26, 36,  2,  true ],
  ['R', 11, 22, 16, 26, 14,  false], ['R',  3, 38, 22, 30,  7,  true ],
  ['R',  8, 54, 30, 40, 20,  false], ['R',  5, 68, 14, 24,  4,  true ],
  ['R', 12, 84, 18, 28, 16,  false], ['R',  3, 92, 24, 34, 10,  true ],
];
const NIKKO_DECOR_SPARKLES = [
  ['L',  4,  8, 14, 26, 4.0, 0],   ['L', 10, 18, 22, 38, 5.6, 1.2],
  ['L',  3, 32, 12, 22, 3.2, 0.6], ['L',  8, 48, 18, 30, 4.8, 2.1],
  ['L',  4, 64, 14, 26, 5.0, 0.4], ['L', 11, 78, 20, 36, 4.2, 1.8],
  ['L',  3, 90, 12, 24, 3.6, 2.6], ['R',  5,  6, 18, 30, 4.4, 0.8],
  ['R', 10, 22, 14, 26, 5.2, 2.0], ['R',  3, 38, 24, 40, 4.0, 0.2],
  ['R',  9, 54, 12, 22, 3.4, 1.4], ['R',  4, 70, 20, 34, 5.6, 0.6],
  ['R', 11, 86, 14, 26, 4.6, 2.2], ['R',  3, 96, 16, 28, 3.8, 1.0],
];

function Decor() {
  return (
    <div className="decor" aria-hidden="true">
      <div className="bubbles">
        {NIKKO_DECOR_BUBBLES.map((b, i) => {
          const [side, edge, bottomVh, size, dur, delay, cool] = b;
          const style = {
            [side === 'L' ? 'left' : 'right']: `${edge}%`,
            width: size, height: size,
            bottom: `${bottomVh - 100}vh`,
            animationDuration: `${dur}s`,
            animationDelay: `-${delay}s`,
          };
          return <span key={i} className={`bubble-orb${cool ? ' cool' : ''}`} style={style} />;
        })}
      </div>
      <div className="sparkles">
        {NIKKO_DECOR_SPARKLES.map((s, i) => {
          const [side, edge, topPct, size, spin, pulse, pulseDelay] = s;
          const style = {
            [side === 'L' ? 'left' : 'right']: `${edge}%`,
            top: `${topPct}%`,
            width: size, height: size,
            animationDuration: `${spin}s, ${pulse}s`,
            animationDelay: `0s, -${pulseDelay}s`,
          };
          return (
            <span key={i} className="spark" style={style}>
              <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <path d="M12 1 L13.6 10.4 L23 12 L13.6 13.6 L12 23 L10.4 13.6 L1 12 L10.4 10.4 Z" />
              </svg>
            </span>
          );
        })}
      </div>
    </div>
  );
}

function App() {
  // Read persisted theme on init so the chat inherits whatever the user set
  // on the loading screen. Falls back to 'light' if nothing is stored.
  // NOTE: the loading screen (loading.js) also reads this value — both must
  // use the same localStorage key ('nikko.theme') to stay in sync.
  const [theme, setTheme] = React.useState(() => {
    try { return localStorage.getItem('nikko.theme') || 'light'; } catch (e) { return 'light'; }
  });
  const [entered, setEntered] = React.useState(false);

  React.useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.dataset.aesthetic = 'organic';
    try { localStorage.setItem('nikko.theme', theme); } catch (e) {}
  }, [theme]);

  // Signal the loading screen that React has mounted (the reactOk gate).
  // The backendOk gate is handled independently by loading.js polling /health.
  // Both gates must pass before the loader fades (REQ-FIS-LS9).
  React.useEffect(() => {
    if (window.NikkoLoading && typeof window.NikkoLoading.reactReady === 'function') {
      window.NikkoLoading.reactReady();
    }
  }, []);

  const toggleTheme = React.useCallback(() => {
    setTheme(t => t === 'light' ? 'dark' : 'light');
  }, []);

  return (
    <>
      <Decor />
      {!entered && <Gate onEnter={() => setEntered(true)} />}
      {entered && <Chat theme={theme} onToggleTheme={toggleTheme} />}
    </>
  );
}

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<App />);
      <Decor />
      {!entered && <Gate onEnter={() => setEntered(true)} />}
      {entered && <Chat theme={theme} onToggleTheme={toggleTheme} />}
    </>
  );
}

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<App />);

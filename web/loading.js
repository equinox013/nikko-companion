// loading.js -- Nikko cold-start loading screen driver.
// Builds particle layers, runs the carousel, exposes window.NikkoLoading.ready(),
// and fades itself out (revealing #root) once the backend is reachable.
//
// Two-gate model:
//   backendOk  -- Fly.io /health returned 200 (or 12s safety-net fired)
//   reactOk    -- nikko.jsx has mounted and called NikkoLoading.ready()
// fadeOut() only runs when BOTH are true.
(function () {
  'use strict';

  const root = document.documentElement;
  const loader = document.getElementById('nikko-loader');
  if (!loader) return;

  // theme -- read persisted value so loader matches what nikko.jsx will pick up.
  let saved = 'light';
  try { saved = localStorage.getItem('nikko.theme') || 'light'; } catch (e) {}
  root.dataset.theme = saved === 'dark' ? 'dark' : 'light';

  const themeBtn = loader.querySelector('.nl-theme');
  function syncThemeBtn() {
    const t = root.dataset.theme;
    themeBtn.classList.toggle('active', t === 'dark');
    themeBtn.setAttribute('aria-label', t === 'dark' ? 'Switch to light mode' : 'Switch to dark mode');
  }
  syncThemeBtn();
  themeBtn.addEventListener('click', () => {
    const next = root.dataset.theme === 'dark' ? 'light' : 'dark';
    root.dataset.theme = next;
    try { localStorage.setItem('nikko.theme', next); } catch (e) {}
    syncThemeBtn();
  });

  // carousel
  const track = loader.querySelector('.nl-track');
  const viewport = loader.querySelector('.nl-viewport');
  const dotsEl = loader.querySelector('.nl-dots');
  const cards = Array.from(track.children);
  const N = cards.length;
  let idx = 0, auto = null;
  const AUTO_MS = 4000;

  cards.forEach((_, i) => {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'nl-dot';
    b.setAttribute('role', 'tab');
    b.setAttribute('aria-label', 'Go to card ' + (i + 1));
    b.innerHTML = '<i></i>';
    b.addEventListener('click', () => go(i, true));
    dotsEl.appendChild(b);
  });

  function go(next, userInitiated) {
    idx = ((next % N) + N) % N;
    track.style.transform = 'translate3d(' + (-idx * 100) + '%, 0, 0)';
    Array.from(dotsEl.children).forEach((d, i) => {
      d.setAttribute('aria-current', i === idx ? 'true' : 'false');
    });
    if (userInitiated) restartAuto();
  }
  function startAuto() { stopAuto(); auto = setInterval(() => go(idx + 1, false), AUTO_MS); }
  function stopAuto() { if (auto) { clearInterval(auto); auto = null; } }
  function restartAuto() { startAuto(); }

  go(0, false);
  startAuto();
  viewport.addEventListener('mouseenter', stopAuto);
  viewport.addEventListener('mouseleave', startAuto);

  // swipe
  let startX = 0, dx = 0, dragging = false;
  viewport.addEventListener('pointerdown', (e) => {
    dragging = true; startX = e.clientX; dx = 0;
    viewport.setPointerCapture(e.pointerId);
    track.style.transition = 'none';
  });
  viewport.addEventListener('pointermove', (e) => {
    if (!dragging) return;
    dx = e.clientX - startX;
    track.style.transform = 'translate3d(calc(' + (-idx * 100) + '% + ' + dx + 'px), 0, 0)';
  });
  function endDrag() {
    if (!dragging) return;
    dragging = false;
    track.style.transition = '';
    const w = viewport.clientWidth || 1;
    if (Math.abs(dx) > w * 0.18) go(idx + (dx < 0 ? 1 : -1), true);
    else go(idx, false);
    dx = 0;
  }
  viewport.addEventListener('pointerup', endDrag);
  viewport.addEventListener('pointercancel', endDrag);

  // particles
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const bubblesLayer = loader.querySelector('.nl-bubbles-layer');
  const starsA = loader.querySelector('.nl-stars.a');
  const starsB = loader.querySelector('.nl-stars.b');
  const rand = (a, b) => a + Math.random() * (b - a);

  const BUBBLE_COUNT = reduced ? 8 : 15;
  for (let i = 0; i < BUBBLE_COUNT; i++) {
    const el = document.createElement('span');
    el.className = 'nl-bubble' + (Math.random() < 0.4 ? ' cool' : '');
    const size = rand(14, 36);
    el.style.width = el.style.height = size + 'px';
    el.style.left = rand(2, 96) + '%';
    const dur = rand(16, 28);
    el.style.animationDuration = dur + 's';
    el.style.animationDelay = (-rand(0, dur)) + 's';
    bubblesLayer.appendChild(el);
  }

  const STAR_COUNT = reduced ? 20 : 40;
  for (let i = 0; i < STAR_COUNT; i++) {
    const el = document.createElement('span');
    el.className = 'nl-star' + (Math.random() < 0.45 ? ' blue' : '');
    const sz = rand(1.2, 2.8);
    el.style.width = el.style.height = sz + 'px';
    el.style.left = rand(0, 100) + '%';
    el.style.top = rand(0, 100) + '%';
    const dur = rand(2.4, 6.5);
    el.style.animationDuration = dur + 's';
    el.style.animationDelay = (-rand(0, dur)) + 's';
    (i % 2 === 0 ? starsA : starsB).appendChild(el);
  }

  // Two-gate ready / fade-out
  // backendOk: health check passed (Fly.io /health returns 200) or safety-net fired.
  // reactOk:   nikko.jsx mounted and called NikkoLoading.ready().
  // Both must be true before the loader fades out.
  var MIN_DISPLAY_MS = 1500;
  var TIMEOUT_MS = 60000;
  var FADE_MS = 400;
  var statusEl = loader.querySelector('.nl-status');
  var statusText = loader.querySelector('.nl-status-text');
  var t0 = performance.now();
  var backendOk = false, reactOk = false, fired = false;
  var timeoutHandle = null;
  var timeoutMsgEl = null;

  function fadeOut() {
    if (fired) return;
    fired = true;
    clearTimeout(timeoutHandle);
    hideTimeoutMessage();
    if (statusText) statusText.textContent = 'Connected';
    statusEl.classList.add('ready');
    setTimeout(() => {
      loader.classList.add('leaving');
      stopAuto();
      setTimeout(() => {
        loader.setAttribute('aria-busy', 'false');
        if (loader.parentNode) loader.parentNode.removeChild(loader);
        window.dispatchEvent(new CustomEvent('nikko:loading:done'));
      }, FADE_MS);
    }, 220);
  }

  function tryFinish() {
    if (!backendOk || !reactOk) return;
    var elapsed = performance.now() - t0;
    if (elapsed >= MIN_DISPLAY_MS) fadeOut();
    else setTimeout(fadeOut, MIN_DISPLAY_MS - elapsed);
  }

  // REQ-FIS-LS11: 60-second timeout UX.
  function showTimeoutMessage() {
    if (timeoutMsgEl || fired) return;
    timeoutMsgEl = document.createElement('div');
    timeoutMsgEl.className = 'nl-timeout';
    timeoutMsgEl.setAttribute('role', 'status');
    var p = document.createElement('p');
    p.textContent = 'Nikko is taking a moment to wake up. This can happen after a period of inactivity. Hang tight.';
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'nl-retry';
    btn.textContent = 'Try again';
    btn.addEventListener('click', resetTimeout);
    timeoutMsgEl.appendChild(p);
    timeoutMsgEl.appendChild(btn);
    var footer = loader.querySelector('.nl-footer');
    if (footer) footer.insertBefore(timeoutMsgEl, footer.firstChild);
    if (statusText) statusText.textContent = 'Still waking up...';
  }

  function hideTimeoutMessage() {
    if (timeoutMsgEl && timeoutMsgEl.parentNode) {
      timeoutMsgEl.parentNode.removeChild(timeoutMsgEl);
    }
    timeoutMsgEl = null;
  }

  function startTimeoutTimer() {
    clearTimeout(timeoutHandle);
    timeoutHandle = setTimeout(showTimeoutMessage, TIMEOUT_MS);
  }

  function resetTimeout() {
    hideTimeoutMessage();
    if (statusText) statusText.textContent = 'Waking Nikko up...';
    startTimeoutTimer();
    window.dispatchEvent(new CustomEvent('nikko:loading:retry'));
  }

  // ── Health poll (REQ-FIS-LS2) ──────────────────────────────────────────────
  // Polls GET /health on the Fly.io backend every 3 seconds.
  // On 200: sets backendOk = true, calls tryFinish(), stops polling.
  // On any other outcome: updates status text and retries.
  // The 60-second timeout UX runs in parallel via startTimeoutTimer().
  var BACKEND_URL = 'https://nikko-backend.fly.dev';
  var POLL_INTERVAL_MS = 3000;
  var pollHandle = null;

  function startHealthPoll() {
    stopHealthPoll();
    pollHandle = setInterval(function () {
      if (fired) { stopHealthPoll(); return; }
      fetch(BACKEND_URL + '/health', { method: 'GET', cache: 'no-store' })
        .then(function (res) {
          if (res.ok) {
            // Backend is up. Signal the backendOk gate and try to finish.
            stopHealthPoll();
            clearTimeout(timeoutHandle);
            hideTimeoutMessage();
            if (statusText) statusText.textContent = 'Connected';
            backendOk = true;
            tryFinish();
          }
          // Non-200 (e.g. 503 during cold-start): keep polling silently.
        })
        .catch(function () {
          // Network error or DNS failure: keep polling.
          // Status text updated by showTimeoutMessage() at 60s if still stuck.
        });
    }, POLL_INTERVAL_MS);
    // Kick off an immediate first probe so there's no 3s wait on load.
    fetch(BACKEND_URL + '/health', { method: 'GET', cache: 'no-store' })
      .then(function (res) {
        if (res.ok && !fired) {
          stopHealthPoll();
          clearTimeout(timeoutHandle);
          hideTimeoutMessage();
          if (statusText) statusText.textContent = 'Connected';
          backendOk = true;
          tryFinish();
        }
      })
      .catch(function () {});
  }

  function stopHealthPoll() {
    if (pollHandle) { clearInterval(pollHandle); pollHandle = null; }
  }

  // Wire resetTimeout to also restart the poll.
  var _origResetTimeout = resetTimeout;
  resetTimeout = function () {
    stopHealthPoll();
    _origResetTimeout();
    startHealthPoll();
    window.dispatchEvent(new CustomEvent('nikko:loading:retry'));
  };

  startHealthPoll();
  startTimeoutTimer();

  // ── Public NikkoLoading API ────────────────────────────────────────────────
  window.NikkoLoading = {
    // Called by nikko.jsx on first mount (React gate).
    // In Phase 5+, nikko.jsx calls reactReady(); ready() is kept as an alias
    // so existing code doesn't break.
    reactReady: function () { reactOk = true; tryFinish(); },
    ready:      function () { reactOk = true; tryFinish(); },

    // Called internally by the health poll. Exposed for testing only.
    backendReady: function () { backendOk = true; tryFinish(); },

    // Called on unrecoverable backend error to update the status line.
    fail: function (msg) {
      if (statusText) statusText.textContent = msg || "Couldn't reach Nikko";
    }
  };

  // Safety net: if React never mounts (e.g. CDN outage or slow connection),
  // open both gates and let the user through after 12s.
  setTimeout(function () {
    if (!fired) { backendOk = true; reactOk = true; tryFinish(); }
  }, 12000);
})();
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        
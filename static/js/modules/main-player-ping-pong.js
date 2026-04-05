/**
 * Two stacked <video> elements: the hidden one preloads the next playlist file;
 * on auto-advance, swap visibility so the next decode is already warm (true stitch handoff).
 */

const TAIL_SEC = 22;

/**
 * @param {object} opts
 * @param {HTMLVideoElement} opts.playerA
 * @param {HTMLVideoElement} opts.playerB
 * @param {HTMLElement} opts.wrapper
 * @param {Array} opts.queue
 * @param {() => number} opts.getCurrentIndex
 * @param {() => HTMLVideoElement} opts.getActiveMedia
 * @param {(el: HTMLVideoElement) => void} opts.setActiveMedia
 * @param {() => number} opts.getVolume
 */
export function initMainPlayerPingPong(opts) {
  const {
    playerA,
    playerB,
    wrapper,
    queue,
    getCurrentIndex,
    getActiveMedia,
    setActiveMedia,
    getVolume,
  } = opts;

  if (!playerA || !playerB || !wrapper) {
    return { tryStitchToNextTrack: () => {} };
  }

  let preloadKey = null;
  /** @type {string|null} absolute URL of passive once it has fired loadeddata for current preload */
  let passiveReadyAbs = null;
  let preloadLoadAborter = null;

  if (window.getComputedStyle(wrapper).position === 'static') {
    wrapper.style.position = 'relative';
  }
  playerB.style.display = 'none';

  function getPassive(active) {
    return active === playerA ? playerB : playerA;
  }

  function urlsMatch(el, urlStr) {
    if (!el?.src || !urlStr) return false;
    try {
      return new URL(el.src).href === new URL(urlStr, window.location.origin).href;
    } catch {
      return false;
    }
  }

  function onTimeUpdate(ev) {
    const m = ev.target;
    if (!m.duration || !Number.isFinite(m.duration) || m.paused) return;
    const idx = getCurrentIndex();
    if (idx < 0 || idx + 1 >= queue.length) return;
    if (m.duration - m.currentTime > TAIL_SEC) return;
    const next = queue[idx + 1];
    if (!next?.url) return;
    let abs;
    try {
      abs = new URL(next.url, window.location.origin).href;
    } catch {
      return;
    }
    const key = `${idx}|${abs}`;
    if (preloadKey === key) return;
    preloadKey = key;
    passiveReadyAbs = null;
    preloadLoadAborter?.abort();
    preloadLoadAborter = new AbortController();
    const { signal } = preloadLoadAborter;
    const passive = getPassive(m);
    const onPassiveLoaded = () => {
      try {
        if (urlsMatch(passive, next.url)) passiveReadyAbs = abs;
      } catch {
        /* ignore */
      }
    };
    passive.addEventListener('loadeddata', onPassiveLoaded, { signal });
    try {
      passive.preload = 'auto';
      passive.muted = true;
      passive.src = next.url;
      passive.load();
    } catch (e) {
      preloadLoadAborter?.abort();
      console.warn('Main player ping-pong preload failed:', e);
    }
  }

  playerA.addEventListener('timeupdate', onTimeUpdate);
  playerB.addEventListener('timeupdate', onTimeUpdate);

  function tryStitchToNextTrack(nextTrack) {
    if (!nextTrack?.url) return;
    const active = getActiveMedia();
    const passive = getPassive(active);
    let nextAbs;
    try {
      nextAbs = new URL(nextTrack.url, window.location.origin).href;
    } catch {
      return;
    }
    const passiveReady =
      urlsMatch(passive, nextTrack.url) &&
      (passive.readyState >= 2 || passiveReadyAbs === nextAbs);
    if (!passiveReady) return;
    try {
      passive.volume = typeof getVolume === 'function' ? getVolume() : active.volume;
      passive.playbackRate = active.playbackRate;
      passive.muted = active.muted;
      passive.currentTime = 0;
      passive.style.display = 'block';
      active.style.display = 'none';
      active.pause();
      active.removeAttribute('src');
      try {
        active.load();
      } catch (e) {
        /* ignore */
      }
      setActiveMedia(passive);
      preloadKey = null;
      passiveReadyAbs = null;
      void passive.play();
    } catch (e) {
      console.warn('Ping-pong stitch failed:', e);
    }
  }

  return { tryStitchToNextTrack };
}

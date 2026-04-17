// Preview Gallery Module
// Encapsulates logic for handling preview sources (manual/youtube/media),
// navigation, dots rendering, fetching from YouTube, and promote-to-manual.

import { YT_THUMB_BROADCAST } from './youtube-thumbnail-autofetch.js';

export function initPreviewGallery(options) {
  const {
    videoId,
    imgEl,
    captionEl,
    dotsEl,
    prevBtn,
    nextBtn,
    fetchBtn,
    promoteBtn,
    playBtn,
    backBtn,
    mediaUrl,
    toast = (msg)=>{ try { window.ToastNotifications?.showToast(msg, { position: 'bottom' }); } catch {} }
  } = options;

  const sourceKeys = ['manual', 'youtube', 'media'];
  let currentIdx = -1;
  let available = [];
  let isPlayerActive = false;
  let videoEl = null;
  /** Avoid overlapping auto-fetch POSTs if `playing` fires repeatedly (buffering). */
  let autoYoutubeFetchInflight = false;

  function sourceLabel(src) {
    if (src === 'manual') return 'Manual preview image';
    if (src === 'youtube') return 'From YouTube thumbnail';
    if (src === 'media') return 'Generated on the fly from media file';
    return '';
  }

  async function loadPreviewInfo() {
    try {
      const resp = await fetch(`/api/track/${videoId}/preview_info`);
      const data = await resp.json();
      const list = Array.isArray(data.available_previews) ? data.available_previews : [];
      const map = { manual: 'manual', from_youtube: 'youtube', from_media_file: 'media' };
      const result = list.map(x => map[x.source]).filter(Boolean);
      if (!result.length) {
        for (const s of sourceKeys) {
          const test = await fetch(`/api/track/${videoId}/preview.png?src=${s}`, { method: 'GET' });
          if (test.ok) result.push(s);
        }
      }
      return result;
    } catch { return []; }
  }

  /** Same POST as the "Fetch from YouTube" button; updates `available`, UI, optional toast. */
  async function runFetchYoutubeThumbnail({ showToastOnOk = true } = {}) {
    const resp = await fetch(`/api/track/${videoId}/fetch_youtube_thumbnail`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ quality: 'auto', force: true })
    });
    const data = await resp.json();
    if (!resp.ok || data.status !== 'ok') {
      return { ok: false, error: data?.error || 'Failed to fetch from YouTube' };
    }
    available = await loadPreviewInfo();
    const idxY = available.indexOf('youtube');
    currentIdx = idxY >= 0 ? idxY : 0;
    if (available.length) {
      setPreviewSource(available[currentIdx]);
      renderDots();
    }
    if (showToastOnOk) toast('YouTube thumbnail fetched');
    return { ok: true };
  }

  function setPreviewSource(src) {
    if (!imgEl) return;
    const base = `/api/track/${videoId}/preview.png?src=${src}`;
    imgEl.src = `${base}&t=${Date.now()}`;
    if (captionEl) captionEl.textContent = sourceLabel(src);
    fetch(`/api/track/${videoId}/preview_info`).then(r=>r.json()).then(data => {
      try {
        const list = Array.isArray(data.available_previews) ? data.available_previews : [];
        const map = { manual: 'manual', youtube: 'from_youtube', media: 'from_media_file' };
        const wanted = map[src];
        const item = list.find(x => x.source === wanted);
        const path = item?.path || '';
        imgEl.title = path ? `Thumbnail path: ${path}` : imgEl.title;
        if (captionEl) captionEl.title = imgEl.title;
      } catch {}
    }).catch(()=>{});
  }

  function getActiveSource() {
    if (!available || !available.length || currentIdx < 0) return 'media';
    return available[currentIdx];
  }

  function enterPlayerMode() {
    if (isPlayerActive || !imgEl || !mediaUrl) return;
    try {
      // Create <video> next to the image
      videoEl = document.createElement('video');
      videoEl.src = mediaUrl;
      videoEl.controls = true;
      videoEl.preload = 'metadata';
      videoEl.playsInline = true;
      videoEl.autoplay = true;
      const src = getActiveSource();
      videoEl.poster = `/api/track/${videoId}/preview.png?src=${src}&t=${Date.now()}`;
      videoEl.style.maxWidth = '100%';
      videoEl.style.borderRadius = '8px';
      videoEl.style.border = '1px solid var(--border)';
      videoEl.style.background = 'var(--bg-card)';

      imgEl.style.display = 'none';
      imgEl.parentElement.insertBefore(videoEl, imgEl.nextSibling);
      if (dotsEl) dotsEl.style.display = 'none';
      playBtn && (playBtn.style.display = 'none');
      backBtn && (backBtn.style.display = 'inline-flex');
      isPlayerActive = true;

      // While inline playback: if there is no saved YouTube thumbnail file, fetch it (same as the button).
      const onInlinePlaying = async () => {
        try {
          const avail = await loadPreviewInfo();
          if (avail.includes('youtube')) {
            videoEl.removeEventListener('playing', onInlinePlaying);
            return;
          }
          if (autoYoutubeFetchInflight) return;
          autoYoutubeFetchInflight = true;
          const r = await runFetchYoutubeThumbnail({ showToastOnOk: false });
          if (r.ok) {
            videoEl.removeEventListener('playing', onInlinePlaying);
            try {
              const src = getActiveSource();
              videoEl.poster = `/api/track/${videoId}/preview.png?src=${src}&t=${Date.now()}`;
            } catch { /* ignore */ }
            toast('YouTube thumbnail fetched');
          }
        } catch {
          /* keep listener for a later playing event */
        } finally {
          autoYoutubeFetchInflight = false;
        }
      };
      videoEl.addEventListener('playing', onInlinePlaying);

      // Try to start playback immediately; fall back to starting when ready
      const tryStart = () => {
        try {
          const p = videoEl.play();
          if (p && typeof p.then === 'function') { p.catch(() => {}); }
        } catch {}
      };
      if (videoEl.readyState >= 2) {
        tryStart();
      } else {
        videoEl.addEventListener('canplay', tryStart, { once: true });
        videoEl.addEventListener('loadeddata', tryStart, { once: true });
      }
    } catch (e) {
      toast('Failed to open inline player');
    }
  }

  function exitPlayerMode() {
    if (!isPlayerActive) return;
    try {
      if (videoEl) {
        try { videoEl.pause(); } catch {}
        videoEl.remove();
      }
      videoEl = null;
      imgEl.style.display = '';
      if (dotsEl) dotsEl.style.display = '';
      playBtn && (playBtn.style.display = 'inline-flex');
      backBtn && (backBtn.style.display = 'none');
      isPlayerActive = false;
    } catch (e) {
      isPlayerActive = false;
    }
  }

  function sourcesKey(arr) {
    return (arr || []).join('|');
  }

  /**
   * Refresh gallery when preview files change (e.g. YouTube thumbnail finished downloading
   * in another view / background after this page loaded).
   * @returns {boolean} true if UI was updated
   */
  function applySourcesUpdate(next) {
    if (!next || !next.length) return false;
    if (sourcesKey(next) === sourcesKey(available)) return false;
    const old = available;
    const oldKey = old[currentIdx] ?? old[0];
    let newIdx = next.indexOf(oldKey);
    // Was only generated-from-media; YouTube file appeared → show it (same as default priority)
    if (
      old.length === 1 &&
      old[0] === 'media' &&
      next.includes('youtube') &&
      !old.includes('youtube')
    ) {
      newIdx = next.indexOf('youtube');
    } else if (newIdx < 0) {
      newIdx = 0;
    }
    available = next;
    currentIdx = newIdx;
    prevBtn && (prevBtn.disabled = !available.length);
    nextBtn && (nextBtn.disabled = !available.length);
    setPreviewSource(available[currentIdx]);
    renderDots();
    return true;
  }

  async function syncPreviewSourcesFromServer() {
    const next = await loadPreviewInfo();
    if (!next.length) return;
    applySourcesUpdate(next);
  }

  function paintActive(idx) {
    if (!dotsEl) return;
    dotsEl.querySelectorAll('button[data-idx]')?.forEach((b, i)=>{
      if (i===idx) { b.style.background='var(--accent)'; b.style.color='#fff'; b.style.borderColor='var(--accent)'; }
      else { b.style.background=''; b.style.color=''; b.style.borderColor='var(--border)'; }
    });
  }

  function renderDots() {
    if (!dotsEl) return;
    dotsEl.innerHTML = available.map((s, i) => `<button class="inline-action" data-idx="${i}" title="${sourceLabel(s)}" style="padding:2px 8px;">●</button>`).join('');
    dotsEl.querySelectorAll('button[data-idx]')?.forEach(btn => {
      btn.addEventListener('click', () => {
        const i = parseInt(btn.getAttribute('data-idx'));
        if (!Number.isNaN(i)) {
          currentIdx = i;
          setPreviewSource(available[currentIdx]);
          paintActive(currentIdx);
        }
      });
    });
    paintActive(currentIdx);
  }

  async function init() {
    available = await loadPreviewInfo();
    const hasAny = available.length > 0;
    prevBtn && (prevBtn.disabled = !hasAny);
    nextBtn && (nextBtn.disabled = !hasAny);
    if (!hasAny) return;
    currentIdx = 0;
    setPreviewSource(available[currentIdx]);
    renderDots();

    prevBtn && prevBtn.addEventListener('click', () => {
      if (isPlayerActive) exitPlayerMode();
      if (!available.length) return;
      currentIdx = (currentIdx - 1 + available.length) % available.length;
      setPreviewSource(available[currentIdx]);
      paintActive(currentIdx);
    });
    nextBtn && nextBtn.addEventListener('click', () => {
      if (isPlayerActive) exitPlayerMode();
      if (!available.length) return;
      currentIdx = (currentIdx + 1) % available.length;
      setPreviewSource(available[currentIdx]);
      paintActive(currentIdx);
    });

    fetchBtn && fetchBtn.addEventListener('click', async () => {
      if (isPlayerActive) exitPlayerMode();
      const btn = fetchBtn;
      const orig = btn.textContent;
      try {
        btn.disabled = true;
        btn.textContent = 'Fetching…';
        const r = await runFetchYoutubeThumbnail({ showToastOnOk: true });
        if (!r.ok) {
          btn.textContent = 'Failed';
          toast(r.error || 'Failed to fetch from YouTube');
          setTimeout(()=>{ btn.textContent = orig; btn.disabled = false; }, 1200);
          return;
        }
        btn.textContent = 'Done';
        setTimeout(()=>{ btn.textContent = orig; btn.disabled = false; }, 800);
      } catch (e) {
        btn.textContent = 'Error';
        toast('Unexpected error');
        setTimeout(()=>{ btn.textContent = orig; btn.disabled = false; }, 1200);
      }
    });

    promoteBtn && promoteBtn.addEventListener('click', async () => {
      if (!available.length) return;
      const src = available[currentIdx];
      if (src === 'manual') { toast('Already manual'); return; }

      try {
        promoteBtn.disabled = true;
        let ok = false;
        // If player is active and we have a video element, capture current frame by timestamp
        if (isPlayerActive && videoEl && typeof videoEl.currentTime === 'number') {
          const ts = Math.max(0, Number(videoEl.currentTime) || 0);
          const resp = await fetch(`/api/track/${videoId}/set_manual_from_timestamp`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ time: ts, width: 1280, overwrite: true })
          });
          const data = await resp.json().catch(()=>({}));
          if (resp.ok && data && data.status === 'ok') {
            ok = true;
            toast('Manual image saved from current frame');
          } else {
            toast(data?.error || 'Failed to save manual from current frame');
          }
        }

        // Otherwise fallback to promoting current preview source
        if (!ok) {
          const confirmMsg = `Set current (${sourceLabel(src)}) as Manual? This may overwrite existing manual image.`;
          if (!window.confirm(confirmMsg)) { promoteBtn.disabled = false; return; }
          const resp2 = await fetch(`/api/track/${videoId}/promote_preview`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ src, overwrite: true })
          });
          const data2 = await resp2.json().catch(()=>({}));
          if (!resp2.ok || !data2 || data2.status !== 'ok') {
            toast(data2?.error || 'Failed to set manual');
          } else {
            ok = true;
            toast('Manual image saved');
          }
        }

        if (ok) {
          // refresh available; manual should now be present
          available = await loadPreviewInfo();
          const idxM = available.indexOf('manual');
          if (idxM >= 0) currentIdx = idxM;
          renderDots();
          // If player is active, update poster to manual for visual consistency
          if (isPlayerActive && videoEl) {
            videoEl.poster = `/api/track/${videoId}/preview.png?src=manual&t=${Date.now()}`;
          } else {
            setPreviewSource(available[currentIdx]);
          }
        }
      } catch (e) {
        toast('Unexpected error');
      } finally {
        promoteBtn.disabled = false;
      }
    });

    // Play / Back buttons
    playBtn && (playBtn.onclick = () => { enterPlayerMode(); });
    backBtn && (backBtn.onclick = () => { exitPlayerMode(); });
    // Initialize buttons state
    backBtn && (backBtn.style.display = 'none');

    // Catch thumbnails saved while user was on the player (race) or in another tab.
    // Button "Fetch from YouTube" updates the img as soon as POST returns; background fetch
    // should feel the same — tight retries first, then slower polling.
    const BURST_MS = [0, 40, 90, 180, 350, 700, 1400];
    const STEADY_MS = 2000;
    const STEADY_MAX_TICKS = 40;

    let steadyTimer = null;
    let steadyTicks = 0;
    /** @type {number[]} */
    const burstTimeoutIds = [];

    const stopWatchers = () => {
      burstTimeoutIds.splice(0).forEach((id) => clearTimeout(id));
      if (steadyTimer != null) {
        clearInterval(steadyTimer);
        steadyTimer = null;
      }
    };

    const tryCatchYoutubeFile = async () => {
      if (available.includes('youtube')) {
        stopWatchers();
        return;
      }
      const next = await loadPreviewInfo();
      if (!next.length) return;
      if (applySourcesUpdate(next) && next.includes('youtube')) {
        stopWatchers();
      }
    };

    const maybeWatchYoutubeArrival = () => {
      if (available.includes('youtube')) return;

      BURST_MS.forEach((delay) => {
        const id = window.setTimeout(() => void tryCatchYoutubeFile(), delay);
        burstTimeoutIds.push(id);
      });

      steadyTicks = 0;
      steadyTimer = window.setInterval(async () => {
        steadyTicks += 1;
        if (steadyTicks > STEADY_MAX_TICKS) {
          stopWatchers();
          return;
        }
        await tryCatchYoutubeFile();
      }, STEADY_MS);
    };
    maybeWatchYoutubeArrival();

    const onVisibility = () => {
      if (document.visibilityState !== 'visible') return;
      void syncPreviewSourcesFromServer();
    };
    document.addEventListener('visibilitychange', onVisibility);

    const onPageShow = (ev) => {
      if (ev.persisted) void syncPreviewSourcesFromServer();
    };
    window.addEventListener('pageshow', onPageShow);

    let thumbBc = null;
    try {
      thumbBc = new BroadcastChannel(YT_THUMB_BROADCAST);
      thumbBc.addEventListener('message', (ev) => {
        const d = ev.data;
        if (d?.type === 'fetched' && d.videoId === videoId) {
          void syncPreviewSourcesFromServer();
        }
      });
    } catch {
      /* ignore */
    }
    window.addEventListener(
      'pagehide',
      () => {
        stopWatchers();
        try {
          thumbBc?.close();
        } catch {
          /* ignore */
        }
      },
      { once: true },
    );
  }

  return { init };
}



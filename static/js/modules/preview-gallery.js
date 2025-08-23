// Preview Gallery Module
// Encapsulates logic for handling preview sources (manual/youtube/media),
// navigation, dots rendering, fetching from YouTube, and promote-to-manual.

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
        const resp = await fetch(`/api/track/${videoId}/fetch_youtube_thumbnail`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ quality: 'auto', force: true })
        });
        const data = await resp.json();
        if (!resp.ok || data.status !== 'ok') {
          btn.textContent = 'Failed';
          toast(data?.error || 'Failed to fetch from YouTube');
          setTimeout(()=>{ btn.textContent = orig; btn.disabled = false; }, 1200);
          return;
        }
        // refresh available and focus youtube if present
        available = await loadPreviewInfo();
        const idxY = available.indexOf('youtube');
        currentIdx = idxY >= 0 ? idxY : 0;
        if (available.length) {
          setPreviewSource(available[currentIdx]);
          renderDots();
        }
        toast('YouTube thumbnail fetched');
        btn.textContent = 'Done';
        setTimeout(()=>{ btn.textContent = orig; btn.disabled = false; }, 800);
      } catch (e) {
        btn.textContent = 'Error';
        toast('Unexpected error');
        setTimeout(()=>{ btn.textContent = orig; btn.disabled = false; }, 1200);
      }
    });

    promoteBtn && promoteBtn.addEventListener('click', async () => {
      if (isPlayerActive) exitPlayerMode();
      if (!available.length) return;
      const src = available[currentIdx];
      if (src === 'manual') { toast('Already manual'); return; }
      const confirmMsg = `Set current (${sourceLabel(src)}) as Manual? This may overwrite existing manual image.`;
      if (!window.confirm(confirmMsg)) return;
      try {
        promoteBtn.disabled = true;
        const resp = await fetch(`/api/track/${videoId}/promote_preview`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ src, overwrite: true })
        });
        const data = await resp.json();
        if (!resp.ok || data.status !== 'ok') {
          toast(data?.error || 'Failed to set manual');
        } else {
          toast('Manual image saved');
          // refresh available; manual should now be present
          available = await loadPreviewInfo();
          const idxM = available.indexOf('manual');
          if (idxM >= 0) currentIdx = idxM;
          renderDots();
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
  }

  return { init };
}



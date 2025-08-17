// Unified tracklist renderer with optional Smart grouping separators

/**
 * Render playlist track list with optional Smart grouping separators.
 * Caller is responsible for initializing tooltips after render.
 *
 * @param {Object} params
 * @param {HTMLElement} params.listElem - UL element to render into
 * @param {Array} params.queue - Array of track objects
 * @param {number} params.currentIndex - Current playing index
 * @param {boolean} params.isSmart - Whether Smart grouping is active
 * @param {Function} params.getBucketLabel - (track) => string bucket label
 * @param {Function} params.getBucketSlug - (label) => string slug id
 * @param {Function} params.createTrackTooltipHTML - (track) => string tooltip HTML
 * @param {Function} params.onPlayIndex - (idx:number) => void
 * @param {Function} [params.createDeleteButton] - (track, idx) => HTMLElement | null
 */
export function renderTrackList({
  listElem,
  queue,
  currentIndex,
  isSmart,
  getBucketLabel,
  getBucketSlug,
  createTrackTooltipHTML,
  onPlayIndex,
  createDeleteButton
}) {
  if (!listElem) return;
  // Mark list with current mode for CSS guards
  // Defer to next microtask to avoid race with mode toggles
  Promise.resolve().then(() => {
    listElem.dataset.smart = isSmart ? '1' : '0';
  });
  listElem.innerHTML = '';

  let lastBucket = null;

  queue.forEach((track, idx) => {
    let slug = null;
    if (isSmart && typeof getBucketLabel === 'function') {
      const bucket = getBucketLabel(track);
      slug = typeof getBucketSlug === 'function' ? getBucketSlug(bucket) : null;
      if (bucket !== lastBucket) {
        lastBucket = bucket;
        const sep = document.createElement('li');
        sep.className = 'group-separator';
        sep.textContent = bucket;
        if (slug) sep.dataset.group = slug;
        listElem.appendChild(sep);
      }
    }

    const li = document.createElement('li');
    li.dataset.index = idx;
    if (slug) li.dataset.group = slug;
    if (idx === currentIndex) li.classList.add('playing');

    // Tooltip
    const tooltipHTML = createTrackTooltipHTML(track);
    li.setAttribute('data-tooltip-html', tooltipHTML);

    // Row content
    const trackContent = document.createElement('div');
    trackContent.className = 'track-content';
    trackContent.style.cssText = 'display: flex; justify-content: space-between; align-items: center; width: 100%;';

    const trackInfo = document.createElement('div');
    trackInfo.className = 'track-info';
    trackInfo.style.cssText = 'flex: 1; cursor: pointer;';
    const displayName = (track.name || '').replace(/\s*\[.*?\]$/, '');
    trackInfo.textContent = `${idx + 1}. ${displayName}`;
    trackInfo.onclick = () => onPlayIndex(idx);

    trackContent.appendChild(trackInfo);

    if (typeof createDeleteButton === 'function') {
      const btn = createDeleteButton(track, idx);
      if (btn) trackContent.appendChild(btn);
    }

    li.appendChild(trackContent);
    listElem.appendChild(li);
  });
}



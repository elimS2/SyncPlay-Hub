// Playlist scroll utilities
// Keeps the currently playing track aligned to the top of the playlist panel

/**
 * Compute element offsetTop relative to a specific ancestor
 * Falls back to cumulative offset via offsetParent chain
 * @param {HTMLElement} element
 * @param {HTMLElement} ancestor
 * @returns {number}
 */
function getOffsetTopRelativeTo(element, ancestor) {
  let offset = 0;
  let node = element;
  while (node && node !== ancestor) {
    offset += node.offsetTop || 0;
    node = node.offsetParent;
  }
  return offset;
}

/**
 * Get element top relative to scroller using DOMRects (robust to nested layouts)
 * @param {HTMLElement} element
 * @param {HTMLElement} scroller
 * @returns {number}
 */
function getRelativeTop(element, scroller) {
  const elRect = element.getBoundingClientRect();
  const scRect = scroller.getBoundingClientRect();
  return (elRect.top - scRect.top) + scroller.scrollTop;
}

/**
 * Find the nearest scrollable ancestor up to a limit element
 * @param {HTMLElement} start
 * @param {HTMLElement} limit
 * @returns {HTMLElement|null}
 */
function findScrollableAncestor(start, limit) {
  let node = start;
  while (node && node !== document.body && node !== limit) {
    const style = window.getComputedStyle(node);
    const overflowY = style.overflowY;
    if ((overflowY === 'auto' || overflowY === 'scroll') && node.scrollHeight > node.clientHeight + 1) {
      return node;
    }
    node = node.parentElement;
  }
  // Check limit itself
  if (limit) {
    const style = window.getComputedStyle(limit);
    const overflowY = style.overflowY;
    if ((overflowY === 'auto' || overflowY === 'scroll') && limit.scrollHeight > limit.clientHeight + 1) {
      return limit;
    }
  }
  return null;
}

/**
 * Scroll playlist so that the active track (`li.playing`) becomes the first visible item.
 * Clamps to the maximum scroll so the list does not overscroll.
 * No-op when elements are not present or the panel is hidden.
 * @param {{ smooth?: boolean }} options
 */
export function scrollActiveTrackToTop(options = {}) {
  const { smooth = false } = options;

  const panel = document.getElementById('playlistPanel');
  const list = document.getElementById('tracklist');
  if (!panel || !list) return;

  // If the whole panel is hidden/collapsed, skip
  if (panel.offsetParent === null) return;

  const active = list.querySelector('li.playing');
  if (!active) return;

  // Determine actual scroll container: prefer the container user currently scrolled
  // Prefer the nearest scrollable ancestor from the active item up to panel
  let scroller = findScrollableAncestor(active, panel) || list;

  // Defer until after DOM has painted to avoid jitter
  requestAnimationFrame(() => {
    // If scroller is the same element that contains LI children (the UL),
    // desiredTop should be active.offsetTop. If scroller is the outer panel
    // and the UL is inside, compute relative offset against the scroller's
    // content origin (subtract UL's offset within scroller).
    const desiredTop = getRelativeTop(active, scroller);
    const maxScroll = Math.max(0, scroller.scrollHeight - scroller.clientHeight);
    // Align active item to the very top of the scroller
    let newScrollTop = Math.max(0, Math.min(desiredTop, maxScroll));
    // Snap to integer pixels to avoid half-line visual artifacts
    newScrollTop = Math.round(newScrollTop);
    // Avoid micro-moves
    if (Math.abs(scroller.scrollTop - newScrollTop) < 1) return;

    try {
      scroller.scrollTo({ top: newScrollTop, behavior: smooth ? 'smooth' : 'auto' });
    } catch (_) {
      // Fallback for browsers without scroll options
      scroller.scrollTop = newScrollTop;
    }
  });
}



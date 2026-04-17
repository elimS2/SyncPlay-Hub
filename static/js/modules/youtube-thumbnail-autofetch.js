/**
 * When playback starts, ensure the track has a saved YouTube thumbnail file
 * (same API as the track page "Fetch from YouTube" button). Silent; no UI.
 */

/** @type {Map<string, 'done' | number>} */
const autoFetchState = new Map();

const RETRY_MS = 90_000;

/** Same-origin tabs: track page can refresh preview when this fetch completes in the player. */
export const YT_THUMB_BROADCAST = 'yt-thumb-v1';

/**
 * @param {string|null|undefined} videoId
 */
export function scheduleAutoFetchYoutubeThumbnailIfMissing(videoId) {
  if (videoId == null || String(videoId).trim() === '') return;
  const id = String(videoId);
  if (autoFetchState.get(id) === 'done') return;
  const failedAt = autoFetchState.get(id);
  if (typeof failedAt === 'number' && Date.now() - failedAt < RETRY_MS) return;

  void (async () => {
    try {
      const r = await fetch(`/api/track/${encodeURIComponent(id)}/preview_info`);
      const data = await r.json();
      const list = Array.isArray(data.available_previews) ? data.available_previews : [];
      if (list.some((x) => x.source === 'from_youtube')) {
        autoFetchState.set(id, 'done');
        return;
      }
      const post = await fetch(`/api/track/${encodeURIComponent(id)}/fetch_youtube_thumbnail`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ quality: 'auto', force: true }),
      });
      const d = await post.json().catch(() => ({}));
      if (post.ok && d.status === 'ok') {
        autoFetchState.set(id, 'done');
        try {
          const ch = new BroadcastChannel(YT_THUMB_BROADCAST);
          ch.postMessage({ type: 'fetched', videoId: id });
          ch.close();
        } catch {
          /* ignore */
        }
      } else {
        autoFetchState.set(id, Date.now());
      }
    } catch {
      autoFetchState.set(id, Date.now());
    }
  })();
}

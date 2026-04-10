/**
 * Start of the current track playback session (client clock), for comparing with play_history.ts.
 * Used so only likes/dislikes after this moment show as active on the player.
 */

let sessionVideoId = null;
let sessionStartedAtMs = 0;

/**
 * Call when switching to a new current track (e.g. loadTrack).
 * @param {string|null|undefined} videoId
 */
export function markTrackPlaybackSessionStart(videoId) {
  sessionVideoId =
    videoId != null && String(videoId).trim() !== '' ? String(videoId) : null;
  sessionStartedAtMs = Date.now();
}

export function getTrackPlaybackSession() {
  return { videoId: sessionVideoId, startedAtMs: sessionStartedAtMs };
}

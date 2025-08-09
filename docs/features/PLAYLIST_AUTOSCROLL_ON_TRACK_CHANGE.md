## Feature: Auto-scroll playlist so the current track is pinned to the top on track change

### Initial Prompt (translated)
Keep playlist players (like `http://192.168.88.82:8000/playlist/TopMusic6`) in sync so that when a playlist is displayed, switching to the next track auto-scrolls the playlist such that the currently playing track becomes the first visible item at the top of the list. For example, if a playlist has 100 tracks and the 23rd is playing, not all tracks fit without scrolling. When moving to the next track, auto-scroll so the playing track appears at the top of the visible list. Exception: when playing the last tracks in the playlist (no more scroll room), do nothing beyond the maximum scroll.

### Summary and Goals
- Ensure the playlist panel automatically scrolls on every track change (manual next/prev, click on a track, auto-advance on `ended`, remote control updates) so the active track is aligned at the top of the scrollable area, if possible.
- Respect boundaries: do not overscroll beyond `maxScroll = scrollHeight - clientHeight`.
- Target all playlist-based players where the playlist is visible (regular playlist player; extendable to virtual/likes player if applicable).
- Keep behavior simple, predictable, and performant (no jitter; minimal layout thrashing).

### Non-Goals
- Do not implement per-user persistent settings in this iteration (we may add a toggle later, see Future Enhancements).
- Do not change playlist rendering structure or styling beyond what is required for accurate scrolling.

### Current Architecture Findings (as of repository snapshot)
- HTML structure of the player includes:
  - Container `#playlistPanel.playlist-panel` with scrollable track list
  - Inside it: `ul#tracklist.side-list` with `li` children; the active item gets class `playing`
  - Source: `templates/components/player_base.html`
- Regular playlist player:
  - `static/player.js` defines `renderList()`, `loadTrack(idx, autoplay)`, `playIndex(idx)` and wires `setupMediaEndedHandler`.
  - `loadTrack` delegates into `utilsLoadTrack(...)` (from `static/js/modules/player/playlist-utils.js::loadTrack`) which updates media, calls `renderList()` and updates UI.
  - `setupMediaEndedHandler` (from `static/js/modules/controls.js`) advances to the next track by calling `playIndex(nextIndex)`.
- Modules:
  - `static/js/modules/player/playlist-utils.js::loadTrack(...)` already calls `renderList()` after setting `currentIndex`, ensuring DOM reflects the active track.
  - The event bus and controls are modularized; the `ended` event and control actions converge via `playIndex`/`loadTrack` → `renderList`.

Implication: a single, centralized hook right after `renderList()` (or at the end of `renderList`) can implement the auto-scroll reliably across change paths.

### UX and Behavioral Requirements
- On any track change, auto-scroll the playlist so the active `li.playing` is aligned to the top of `#playlistPanel`.
- If aligning to top would exceed `maxScroll`, clamp to `maxScroll` so the end of the list is visible without blank space.
- If the playlist panel is hidden/collapsed, defer or skip scrolling to avoid unnecessary work.
- Avoid jitter: perform the scroll after DOM update using `requestAnimationFrame`.
- Scrolling mode: initially use immediate scroll; consider a smooth scroll optional preference (future).

### Design
Introduce a small UI utility to position the active track at the top of the playlist view.

Proposed function (pseudo-code):
```
function scrollActiveTrackToTop(options = { smooth: false }) {
  const panel = document.getElementById('playlistPanel');
  const list = document.getElementById('tracklist');
  if (!panel || !list) return;
  const active = list.querySelector('li.playing');
  if (!active) return;

  // Measure after render
  requestAnimationFrame(() => {
    const desiredTop = active.offsetTop; // relative to parent (UL)
    const maxScroll = panel.scrollHeight - panel.clientHeight;
    const newScrollTop = Math.max(0, Math.min(desiredTop, maxScroll));
    panel.scrollTo({ top: newScrollTop, behavior: options.smooth ? 'smooth' : 'auto' });
  });
}
```

Integration points (regular playlist):
- Option A (preferred): Call `scrollActiveTrackToTop()` at the end of `renderList()` in `static/player.js` (after `.playing` class is set).
- Option B: Call `scrollActiveTrackToTop()` right after `renderList()` inside `static/js/modules/player/playlist-utils.js::loadTrack()`; this centralizes across consumers that call `renderList()` via `loadTrack`.

Edge handling:
- If `#playlistPanel` has additional padding/margin or the `ul#tracklist` is not at offset 0, the `offsetTop` approach still works because we scroll the container to the element’s top position relative to its scroll origin (the UL content). If required, we can compute via `getBoundingClientRect()` difference plus current `scrollTop`.
- Near the end of the list, clamping to `maxScroll` prevents overscroll.

Visibility handling:
- If `#playlistPanel` is hidden (e.g., toggled closed), we skip or defer. A simple check is `panel.offsetParent !== null` to approximate visibility. If hidden, we can set a flag to run once when it becomes visible.

### Step-by-step Implementation Plan
1) Create a small utility function (e.g., `scrollActiveTrackToTop`) in a dedicated module `static/js/modules/playlist-scroll.js`. STATUS: Done.
2) Re-export helper via `static/js/modules/index.js` for centralized imports. STATUS: Done.
3) Integration point A: Append a call at the end of `renderList()` in `static/player.js`. STATUS: Replaced.
   - Centralized approach implemented instead: call `scrollActiveTrackToTop()` inside `static/js/modules/player/playlist-utils.js::loadTrack()` right after `renderList()`. This ensures both regular and virtual players benefit without duplicate edits.
4) Ensure call is wrapped in `requestAnimationFrame` to avoid layout thrashing. STATUS: Done (inside helper).
5) Add boundary clamp: `newScrollTop = Math.min(desiredTop, panel.scrollHeight - panel.clientHeight)`. STATUS: Done.
6) Add visibility guard to avoid unnecessary work when panel is hidden. STATUS: Done.
7) Verify that auto-advance via `ended` event also triggers the behavior (through `playIndex` → `loadTrack` → `renderList`). STATUS: Done (verified by user on likes player; Next and auto-advance).
8) Validate the same approach for virtual/likes playlist player (`static/player-virtual.js`) if it renders `#playlistPanel`/`#tracklist` similarly; integrate the same hook. STATUS: Done (verified on likes player).
9) Cross-browser sanity: check offset calculation in Chromium-based browsers (primary target) and Firefox. STATUS: Pending.

### Acceptance Criteria
- When switching tracks (Next/Prev buttons, clicking another track, auto-advance), the active track becomes the top visible list item when possible.
- When the active track is near the bottom of the playlist, the list scrolls to its maximum position without blank space; the track may be below the very top if no room remains.
- No visible jitter; scroll occurs immediately after list re-render.
- No regressions to playlist rendering, selection, or controls.

Status: Met (validated interactively on likes player). Pending: optional cross-check on regular playlist page.

### Manual Test Checklist
- Open a large playlist (e.g., `http://192.168.88.82:8000/playlist/TopMusic6`).
- Ensure `#playlistPanel` is visible (toggle if necessary).
- Scroll the playlist to mid-range manually (e.g., so item ~23 is visible but not at the top).
- Start playing item 23.
  - Click Next → verify item 24 becomes the first visible row (aligned to top).
  - Click Prev → verify item 23 becomes the first visible row.
- Let track finish (auto-advance) → verify next track becomes first visible.
- Jump to a distant item by clicking it in the list → verify it becomes the first visible.
- Near end of playlist: navigate to the last 3–5 tracks; Next should clamp at list end without overscrolling (no blank area below list).
- Collapse the playlist panel (if supported) and change tracks → ensure no errors; when reopened, list is in a reasonable position.
- Remote control page influence (if applicable): changing tracks via remote should also cause auto-scroll in the main player.
- Casting integration unaffected (if used); only the UI list scrolls.

### Implementation Status Log
- 2025-08-09: Implemented `scrollActiveTrackToTop` in `static/js/modules/playlist-scroll.js`; re-exported via `static/js/modules/index.js`.
- 2025-08-09: Centralized integration: call helper inside `static/js/modules/player/playlist-utils.js::loadTrack()` after `renderList()`. Removed per-player call from `static/player.js`. Result: both regular and virtual players covered without duplication. Lint: clean.
- 2025-08-09: Fix scroll container selection and offset calculations. Helper now picks nearest scrollable ancestor and uses DOMRects to compute precise `desiredTop`. Also snaps `scrollTop` to integer to avoid half-line artifacts.
- 2025-08-09: Behavior validated on likes player (`/likes_player/...`): Next and auto-advance place the active track at the top correctly after additional fixes.

### Verification Results (interactive)
- Likes player (`/likes_player/1`):
  - Jump to distant track, scroll elsewhere, Next/Prev, auto-advance → active item is aligned to top as expected, without half-line artifacts.
  - Smart/Shuffle changes do not affect correctness; alignment uses the current queue and the DOM's `.playing` state after re-render.
- Regular playlist page (`/playlist/...`):
  - Suggested to verify the same interaction set (Next/Prev, click-to-play, auto-advance, end-of-list clamp). If confirmed OK, feature can be considered fully complete.

### Performance Considerations
- Single DOM query for `#playlistPanel`, `#tracklist`, and `li.playing` per change.
- Use DOMRect-based relative position calculation to avoid offsetParent quirks in nested layouts.
- One `requestAnimationFrame`-wrapped `scrollTo` call; negligible overhead.
- No continuous listeners; only invoked on track change.

### Telemetry and Debugging
- Optionally log a single debug line (behind an existing debug flag) with current index, desiredTop, and final scrollTop.
- Avoid verbose logging in production builds.

### Future Enhancements
- Add a user preference toggle: “Auto-scroll active track to top” (persist in localStorage or server-side playlist preferences). Default: enabled.
- Add “smooth” scroll behavior as a preference.
- Consider sticky header offset if a fixed header overlaps the playlist panel in certain layouts.

### Risks and Mitigations
- Risk: Wrong scroll container (if CSS changes). Mitigation: isolate logic in one helper; adjust container selection centrally.
- Risk: Jank if `renderList` reflows heavily. Mitigation: measure and scroll in `requestAnimationFrame`; keep operations minimal.
- Risk: Virtual/likes player uses a different structure. Mitigation: confirm structure and add the same hook if needed.

### Rollout Plan
1) Implement for the regular playlist player (`static/player.js`).
2) Manual verification using the checklist above.
3) Extend to virtual/likes player if it shares the same playlist panel.
4) Add optional preference toggle in a follow-up if desired.

### Files Likely to Change
- `static/js/modules/ui-effects.js` or new `static/js/modules/playlist-scroll.js`: add `scrollActiveTrackToTop`.
- `static/player.js`: call the helper after `renderList()`.
- `static/js/modules/player/playlist-utils.js`: optional alternative integration point (call after `renderList()`).
- `static/player-virtual.js`: mirror change if applicable.

### Definition of Done
- Feature implemented and verified on the target playlist page.
- No console errors, no regressions in player controls.
- Behavior matches acceptance criteria across manual test steps.



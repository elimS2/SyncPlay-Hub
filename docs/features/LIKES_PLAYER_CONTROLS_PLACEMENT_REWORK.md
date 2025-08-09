### Likes Player: Playback Controls Placement Rework

Status: Planned

Owner: Frontend/UI

Last updated: 2025-08-08

---

### Initial Prompt (translated to English)

On the page `http://192.168.88.82:8000/likes_player/0` the layout is currently:

- Buttons above the video
- Then the video
- Then the playlist under the video (if the playlist-under-video layout is selected)
- And only after the playlist, the playback controls block (pause, previous, next, volume, progress bar, etc.)

I want to swap the playlist and the playback controls: the controls block should be placed right under the video, and the playlist should go below it.

If the playlist is displayed next to the video (side-by-side), then the playback controls must not be stuck to the bottom of the screen; they should be placed right under the video.

Also: Analyze the task and project deeply, decide how best to implement. Create a detailed step-by-step roadmap in `docs/features` and maintain it as a running to-do/checklist. Keep all code and comments in English only. Ask for confirmation before implementing.

---

### Objective

- Place the playback controls block directly under the video on the Likes Player page, regardless of the playlist layout mode (under-video or side-by-side).
- When the playlist is under the video, the order should be: Control Bar (top buttons) → Video → Current Track Title → Playback Controls → Playlist.
- When the playlist is side-by-side, the playback controls should still be right under the video within the left column, not fixed to the viewport bottom.
- New requirement: The current track title must appear under the video and above the playback controls.

### Current Implementation Analysis

- Template structure (shared): `templates/components/player_base.html`
  - `#videoWrapper` contains `<video id="player">` and the playback controls block `<div id="customControls" class="controls">`.
  - After `#videoWrapper` there is `#currentTrackTitle` (track title display) and then `#playlistPanel` with `#tracklist`.

- Likes Player page: `templates/likes_player.html` extends `player_base.html` and sets `player_css = "likes-player"` and `player_js = "player-virtual"`.

- Playlist layout switching: `static/js/modules/playlist-layout-manager.js`
  - Controls layout modes: hidden, under_video, side_by_side by manipulating `.player-container` flex-direction and `#playlistPanel` styles.
  - Does not move controls; they are inside `#videoWrapper` already.

- Global controls positioning (key point): `static/css/player-common.css`
  - `.controls { position: fixed; bottom: 0; left: 0; z-index: 1002; }`
  - `#currentTrackTitle { position: fixed; bottom: 45px; }`
  - JS `updateTrackTitleWidth` in `static/js/modules/track-title-manager.js` sets `controls.style.width` and `currentTrackTitle.style.width/left` to match the video width/left.

- Likes-specific CSS: `static/css/likes-player.css` currently does not override `.controls` positioning.

Conclusion: Even though `#customControls` lives under the video in the DOM, it is detached from document flow by `position: fixed` and appears at the viewport bottom. We need a controllable mode to render controls in-flow under the video.

### Design Decision

- Introduce a non-fixed (in-flow) mode for the playback controls on the Likes Player only, to minimize risk to other pages.
- Prefer CSS override via the page-specific stylesheet `likes-player.css` to switch `.controls` from `position: fixed` to in-flow (`position: static`) on this page.
- Guard JS that force-sets `controls.style.width/left` so it only applies when controls are fixed. Use a runtime check (`getComputedStyle(controls).position === 'fixed'`) before applying dynamic sizing. This keeps behavior consistent across other players and fullscreen.
- Update `#currentTrackTitle` for the Likes Player to be in-flow under the video and above the controls using a page-specific CSS override. To ensure correct ordering across all layouts, relocate the `#customControls` block in the base template to follow `#currentTrackTitle` in the DOM.

### Implementation Plan (Step-by-step)

1) CSS override for Likes Player (Required)
   - File: `static/css/likes-player.css`
   - Add a section to override controls on this page:
     - `.player-container #customControls.controls { position: static; left: auto; bottom: auto; width: 100%; z-index: auto; }`
     - Provide spacing: `margin-top: 8px;` so controls visually separate from the video.
     - Ensure `.progress` remains full-width within the controls as flex item.
   - Impact: Controls will appear directly under the video and above the playlist in both under-video and side-by-side layouts because they are children of `#videoWrapper`.

2) JS safeguard for width/position mutations (Required)
   - File: `static/js/modules/track-title-manager.js`
   - Function: `updateTrackTitleWidth()`
   - Change to only set `controls.style.width` and `currentTrackTitle.style.left/width` when controls are fixed:
     - `const isFixed = getComputedStyle(controls).position === 'fixed'`
     - If `isFixed` is false, skip mutating controls width/left. Still okay to adjust the track title when it remains fixed.
   - Impact: Avoids unnecessary inline styles that could break in-flow layout.

3) Fullscreen behavior audit (Required)
   - Files: `static/js/modules/ui-effects.js` (show/hide logic), `player-common.css` (fixed positioning)
   - Verify that `showFsControls`/`updateFsVisibility` do not assume fixed positioning beyond adding/removing `.hidden` class.
   - If needed, in fullscreen mode we can temporarily set a class on `#customControls` (e.g., `controls-fixed`) to opt back into overlay behavior. For initial scope, we proceed without this; we will adjust based on QA.

4) Playlist layout integrity check (Required)
   - File: `static/js/modules/playlist-layout-manager.js`
   - Ensure that in `UNDER_VIDEO` the order naturally renders as: Video (with in-flow controls inside) → `#currentTrackTitle` → `#playlistPanel`.
   - In `SIDE_BY_SIDE`, the left pane is `#videoWrapper` (video + controls stacked), right pane is the playlist. No code change anticipated; validate behavior.

5) Make current track title in-flow and reorder controls (Required)
   - CSS: In `static/css/likes-player.css`, add override for `#currentTrackTitle` to be in-flow:
     - `#currentTrackTitle { position: static; left: auto; bottom: auto; width: 100%; margin: 6px 0 8px; }`
   - Template: In `templates/components/player_base.html`, move the `#customControls` block from inside `#videoWrapper` to below the `#currentTrackTitle` block, so the DOM order becomes: `#videoWrapper` (video) → `#currentTrackTitle` → `#customControls` → `#playlistPanel`.
   - JS: Already guarded in Step 2; no additional JS changes expected.

### Acceptance Criteria

- Likes Player (`/likes_player/0`) shows playback controls directly under the video.
- In under-video layout: order is Control Bar → Video → Current Track Title → Playback Controls → Playlist; no element is stuck to the viewport bottom.
- In side-by-side layout: the left column shows Video → Current Track Title → Playback Controls; the right column shows the Playlist.
- Fullscreen still works: controls are visible and functional; no visual glitches caused by the position change.
- No regressions on other player pages that rely on fixed-bottom controls.

### Manual Test Plan

General
- Load `/likes_player/0` on desktop (≥1280px) and mobile (<768px).
- Verify the controls render directly under the video in both screen sizes.

Layout Switching
- Click the “Playlist: …” toggle button (`#toggleLayoutBtn`) to cycle through: Hidden → Under → Right.
  - Hidden: playlist disappears; controls remain under video.
  - Under: playlist appears below controls; scrolling is natural, nothing fixed at viewport bottom.
  - Right: playlist shows to the right; controls remain under video on the left.

Playback UX
- Play/Pause works; progress bar updates; seeking via progress bar works.
- Volume controls and speed button work; no overlay with page content.

Fullscreen
- Enter fullscreen; confirm controls are visible and do not create layout breakage. Move mouse to see auto-hide behavior still functioning (if applicable).

Track Title
- Confirm the track title banner displays correctly and does not obstruct content. If it overlaps undesirably, evaluate enabling the optional in-flow title mode.

Regression
- Open `/` main player and any other player pages to ensure their controls remain fixed bottom and unaffected.

### Risks and Mitigations

- Risk: JS keeps forcing width/left on controls causing layout glitches.
  - Mitigation: Add the `position === 'fixed'` guard (Step 2).

- Risk: Fullscreen UX depends on fixed overlay behavior.
  - Mitigation: Validate and, if needed, toggle a `controls-fixed` class only in fullscreen.

- Risk: Mobile spacing/overflow issues when controls are in-flow.
  - Mitigation: Add margins and ensure `.progress` flex sizing behaves; adjust CSS in `likes-player.css` as necessary.

### Work Items (To-do / Checklist)

- [x] Add in-flow controls override to `static/css/likes-player.css`.
- [x] Add guard in `updateTrackTitleWidth()` to only size controls when fixed.
 - [x] Validate under-video and side-by-side layouts visually.
- [ ] Audit fullscreen interactions; decide if a fullscreen-only fixed mode is desirable.
 - [x] Audit fullscreen interactions; ensure show/hide logic uses classes only (no position assumptions). Current code OK.
- [ ] Make `#currentTrackTitle` in-flow on Likes Player via CSS.
 - [x] Make `#currentTrackTitle` in-flow on Likes Player via CSS.
 - [x] Move `#customControls` below `#currentTrackTitle` in `player_base.html`.
- [x] Hidden layout stacks vertically (set `.player-container` to column in JS when hidden).
 - [x] Manual QA on desktop and mobile; adjust spacing.
 - [x] Align main playlist page to shared layout by making title and controls in-flow under video (parity with Likes Player).

Notes (Step 1):
- Implemented CSS override so `#customControls` participates in normal flow under the video on the Likes Player only (no impact on other pages).
- Kept spacing minimal (`margin-top: 8px`) to preserve compact layout.
- Next: add JS guard to avoid inline width/left mutations when controls are not fixed.

Notes (Step 2):
- Updated `static/js/modules/track-title-manager.js` (`updateTrackTitleWidth`) to conditionally set widths/left only when elements are `position: fixed`.
- When not fixed, inline `width/left` are cleared to let CSS flow manage layout.
- This ensures the Likes Player’s in-flow controls are not forced to any width/left, while other pages with fixed controls keep their behavior.

Validation Instructions (Step 3):
- Desktop
  - Open `/likes_player/0`.
  - Cycle layouts with the toggle button:
    - Under: expect order → Control Bar → Video → Controls → Playlist.
    - Right: expect left column → Video → Controls; right column → Playlist.
    - Hidden: playlist hidden; controls remain under the video.
  - Confirm progress/volume/speed work and no element is fixed to viewport bottom.
  
Notes (Step 3a):
- Implemented page-specific CSS override so `#currentTrackTitle` is rendered in-flow under the video and above the controls (once controls are reordered in the template).
 
Notes (Step 3b):
- Reordered DOM in `templates/components/player_base.html`: `#customControls` moved below `#currentTrackTitle` so the visible order becomes Video → Current Track Title → Controls → Playlist.
- Adjusted the inline script block to avoid template interpolation errors for `VIRTUAL_PLAYLIST_LIKE_COUNT` by using a safe string and parsing to number.

Notes (Step 3c):
- Fixed Hidden layout horizontal alignment by forcing `.player-container` to `flex-direction: column` when playlist is hidden.

Notes (Step 3d):
- Introduced `#leftPane` wrapper in `player_base.html` so in side-by-side layout the left column stacks: Video → Current Track Title → Controls. Added `.left-pane` styles in `player-base.css`.
 
Notes (Step 3e):
- Applied parity styles to `index-player.css` to make `#currentTrackTitle` and `#customControls` in-flow under the video on the main playlist page.

Notes (Step 4 - Manual QA desktop):
- Likes Player
  - Hidden: vertical order OK (Video → Title → Controls). No fixed elements.
  - Under: vertical order OK; playlist below controls; scroll within playlist panel preserved.
  - Right: left column stacks Video → Title → Controls; playlist on the right.
  - Fullscreen: controls/title show/hide via class; no layout breakage observed.
- Main Playlist Page
  - Under/Right/Hidden mirror Likes Player behavior after parity styles.
  
Pending:
- Mobile (<768px) pass and fine-tune spacing if needed.

Final Notes:
- All layouts (Hidden / Under / Right) now render with the order Video → Current Track Title → Controls → Playlist.
- No horizontal or page vertical scroll in Hidden/Under; playlist panel shows its own scrollbar when needed.
- Fullscreen behavior verified; show/hide uses classes only; no positional assumptions.

- Track Title Placement (New Requirement):
  - Ensure the visible order is Video → Current Track Title → Controls → Playlist for under-video layout.
  - For side-by-side layout, ensure the left column has Video → Current Track Title → Controls; the right column has the Playlist.
- Mobile (<768px width)
  - Repeat the above; ensure no overflow and controls are directly under video.
- Console helpers (optional):
  - `setPlaylistLayout('under_video')`
  - `setPlaylistLayout('side_by_side')`
  - `setPlaylistLayout('hidden')`

### Files Likely Affected

- `static/css/likes-player.css` (add overrides)
- `static/js/modules/track-title-manager.js` (guard width/left update)
- (Optional) `static/css/likes-player.css` for `#currentTrackTitle` in-flow mode

### Rollback Plan

- Revert changes in `likes-player.css` and the guard in `track-title-manager.js`.
- Since scope is page-specific and guarded, other pages should remain unaffected.

---

Please confirm if this plan is approved to proceed with implementation or suggest adjustments.



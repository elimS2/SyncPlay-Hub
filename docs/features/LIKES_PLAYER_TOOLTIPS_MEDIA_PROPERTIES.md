Title: Add Media Properties (Bitrate, Type, Resolution) to Likes Player Track Tooltips

Status: Implemented (manual verification completed)
Owner: Frontend + API (Playlist)
Related pages: `/likes_player/<n>`, `/track/<video_id>`
Last updated: 2025-08-10

1) Initial Prompt (translated to English)

The following is an exact translation of the original task prompt to preserve intent without “telephone game” effects.

"On the page at http://192.168.88.82:8000/track/Igv1NkF8938 we display Bitrate, Type, Resolution, but on the page http://192.168.88.82:8000/likes_player/1, when you hover over a track in the playlist, these are not displayed in the tooltips. Let’s display them there as well, perhaps somewhere near File Size and Duration. And maybe highlight this as a separate group of properties, similar to how we have the Playback statistics grouped. — Analyze the Task and Project — Deeply analyze our task, our project and decide how best to implement this. — Create Roadmap — Create a detailed, step-by-step plan of actions to implement this task in a separate file-document. We have a folder docs/features for this. If there is no such folder, create it. Document in this file all discovered and attempted problems, nuances and solutions as we proceed. You will use this file as a todo checklist, updating it and documenting what’s done, how it’s done, what issues arose, and what decisions were made. For history, do not delete items; only update their status and comment. If during implementation it becomes clear that something needs to be added, add it to this document. This will help to maintain context and not forget planned work. Remember that code and comments in the project must be in English only. When you finish the plan, stop and ask me if I agree to start implementing it or if anything needs to be adjusted. Also include manual testing steps — what needs to be clicked in the interface. — SOLID, DRY, KISS, Separation of Concerns, Single Level of Abstraction, Clean Code Practices. Follow UI/UX principles: User-Friendly, Intuitive, Consistency, Accessibility, Feedback, Simplicity, Aesthetic & Modern, Performance, Responsive Design. Use Best Practices."

2) Problem Overview

- The Track Detail page (`/track/<video_id>`) already shows media properties such as Bitrate, Resolution, and Type (filetype) under "File Properties".
- In the Likes Player (`/likes_player/<n>`), hovering a track shows a custom tooltip built in JavaScript. The tooltip currently includes YouTube/channel info, Duration, File Size, Last Played, and a grouped section "Playback Statistics", but it does not include Bitrate, Resolution, or Type.
- We want to add these media properties into the Likes Player tooltips, ideally grouped together in a section similar to the existing "Playback Statistics" group, and positioned near Duration and File Size for coherence.

3) Current Implementation (as of writing)

- Tooltip generation:
  - Function `createTrackTooltipHTML(track)` in `static/js/modules/ui-effects.js` constructs the HTML for the tooltip. It already appends a titled group for "Playback Statistics" using a `.tooltip-section` divider and a set of `.tooltip-row` lines.
  - The tooltip system is initialized from both players by setting `data-tooltip-html` on `<li>` elements and invoking `setupGlobalTooltip(listElem)`; CSS lives in `static/css/player-base.css` (class `.custom-tooltip`, `.tooltip-section`, `.tooltip-row`).

- Likes Player data source:
  - Likes Player fetches data from `GET /api/tracks_by_likes/<like_count>` implemented in `controllers/api/playlist_api.py` (`api_tracks_by_likes`).
  - The endpoint returns `size_bytes` but currently does not include `bitrate`, `resolution`, or `filetype` in its SELECT/response.

- Track Detail page:
  - Uses server-rendered template `templates/track.html` and shows `bitrate`, `resolution`, and `filetype` from the `tracks` table.
  - Media properties are updated by `api_rescan_track_media` (`controllers/api/tracks_api.py`) and post-download workers; the `tracks` table holds `bitrate`, `resolution`, and `filetype`.

Conclusion: Frontend tooltip function already has a good extension point. API for likes needs to include additional fields from `tracks` to render Bitrate/Resolution/Type in the tooltip.

4) Goals

- Show Bitrate, Resolution, and Type alongside Duration and File Size in Likes Player tooltips.
- Group these fields into a distinct, labeled section (e.g., "Media Properties" or "File Properties") similar to the existing "Playback Statistics" group.
- Keep the UI concise, readable, and consistent; handle missing values gracefully.
- Ensure no regressions in tooltip behavior or positioning for different playlist layouts (Under Video vs Side by Side).

5) Non-Goals

- No changes to how Track Detail page renders. It already displays these properties.
- No new database schema changes are required.
- No background jobs or rescans are triggered from likes tooltips.

6) Design Proposal

6.1 Data Model and API

- Add `t.bitrate`, `t.resolution`, and `t.filetype` to the SELECT list in `api_tracks_by_likes` and include them in the JSON response per-track item as `bitrate`, `resolution`, and `filetype` keys.
- Keep `size_bytes` as-is. No changes to duration-related fields are needed.
- Backward compatibility: If some older tracks lack these fields, the frontend renders placeholders (e.g., "-" or "Unknown").

6.2 Frontend (Tooltip Content)

- In `createTrackTooltipHTML(track)`:
  - Introduce a new section after channel/YouTube metadata and before or after "Playback Statistics":
    - Section title: "Media Properties" (consistent with Track Detail’s "File Properties"; we choose "Media Properties" to avoid confusion with file lists).
    - Rows within this section (order for readability):
      1) Duration (already computed from `youtube_duration_string` or `youtube_duration`)
      2) File Size (from `size_bytes`)
      3) Bitrate (from `bitrate`, rendered as e.g., `128 kbps` when present; integer formatting to kbps)
      4) Resolution (from `resolution`, e.g., `1920x1080`)
      5) Type (from `filetype`, e.g., `mp4`)
  - Remove the earlier ungrouped Duration and File Size lines from the general list to avoid duplication, moving them into the new section for consistency.
  - Use consistent icons and `.tooltip-row` markup. For accessibility, keep meaningful text labels; icons are decorative.

- Tooltip layout and positioning remain controlled by existing logic in `setupGlobalTooltip` and CSS in `player-base.css`. This change adds content only.

6.3 UX/UI Considerations

- Consistency: Grouping mirrors the existing "Playback Statistics" pattern, improving scanability.
- Simplicity: Do not overload the tooltip; we add only five concise rows under one new section.
- Accessibility: Ensure text is present for each value; placeholder "-" or "Unknown" is acceptable. Icons remain non-essential.
- Responsiveness/overflow: Current tooltip CSS (`max-width: 300px`) and `white-space: nowrap` should be sufficient. Resolutions and types are short.

7) Implementation Plan (Step-by-Step)

- [ ] API: Extend `api_tracks_by_likes` to include media properties
  - [x] Update SQL SELECT to add `t.bitrate`, `t.resolution`, `t.filetype`.
- [x] Extend SQL SELECT and API response to include `t.video_fps` and `t.video_codec` for richer media info.
  - [x] Include these fields in the `track` dict returned for each item.
  - [x] Verify endpoint returns expected fields for a known track (validated indirectly via UI; optional JSON spot-check recommended).

- [ ] Frontend: Update tooltip generation
  - [x] Modify `createTrackTooltipHTML(track)` in `static/js/modules/ui-effects.js`:
    - [x] Add a `.tooltip-section` titled "Media Properties".
    - [x] Move existing Duration and File Size into this section.
    - [x] Add Bitrate, Resolution, and Type rows (graceful fallback when values are absent).
    - [x] Keep calculation of Duration (from YouTube fields) and File Size (using `formatFileSize`).
    - [x] Maintain existing styling and structure.

- [ ] QA/Verification
  - [x] Hover various tracks in `/likes_player/1` and other like counts (tooltip works).
  - [x] Compare visible values against `/track/<video_id>` for the same item (values match).
  - [x] Test both playlist layouts (Under Video and Side by Side) to ensure tooltip position and occlusion remain acceptable.
  - [x] Test tracks with missing `bitrate`, `resolution`, `filetype` to ensure placeholders are shown.
- [x] Test tracks with missing `video_fps` / `video_codec` to ensure placeholders are shown.
  - [x] Confirm no console errors, and that performance remains acceptable with large lists.

8) Manual Testing Steps (UI)

1. Open `http://192.168.88.82:8000/likes_player/1`.
2. Ensure playlist is visible. If needed, toggle layout via the "Playlist: Right" button to try both Under and Side-by-Side layouts.
3. Hover over the first 3–5 tracks:
   - Verify the tooltip displays a new section header: "Media Properties".
   - Within that section verify rows for: Duration, File Size, Bitrate, Resolution, Type.
   - Check value formatting: Duration as `mm:ss` (or from YouTube string), File Size formatted (e.g., `123.4 MB`), Bitrate in `kbps`, Resolution as `WIDTHxHEIGHT`, Type as extension.
4. Open one of these tracks in a new tab via `/track/<video_id>` and verify that the Bitrate/Resolution/Type values match what is shown on the detail page (allowing for `-` when unknown).
5. Optionally perform a rescan on the Track Detail page (Rescan media properties), then refresh Likes Player and confirm updated values appear in the tooltip.
6. Check for any overlap issues of the tooltip with hovered rows in the Under Video layout; the existing positioning logic should offset below when possible.

9) Edge Cases and Fallbacks

- Tracks without probed media properties (bitrate/resolution/filetype missing): show `-`.
- Audio-only tracks: Resolution may be `-`; do not infer misleading values.
- Extremely large/small bitrates: render integer kbps (rounded); avoid lengthy decimals.
- File Size unknown (`size_bytes` null): fallback to `-`.

10) Performance Considerations

- The API adds three fields to the SELECT and response per track (`bitrate`, `resolution`, `filetype`). This is negligible overhead compared to existing payloads and should not noticeably affect rendering.
- Tooltip generation is per-hover and uses existing shared logic; no additional DOM listeners are created.

11) Backward Compatibility and Risk

- Frontend code should check for field presence and fallback to placeholders; no hard dependency on these fields being present for older endpoints.
- The change to `api_tracks_by_likes` is additive (new fields only); no clients are expected to break.

12) Implementation Details and Best Practices

- Follow SOLID, DRY, KISS; limit the change scope to the relevant function and endpoint.
- Keep naming explicit and consistent (`bitrate`, `resolution`, `filetype`).
- Also expose `video_fps`, `video_codec` for video media when available.
- Maintain separation of concerns: API enriches data; UI renders with minimal formatting logic.
- Keep code in English (variables, strings, comments, UI labels).

13) Acceptance Criteria

- Likes Player tooltips contain a clearly labeled group "Media Properties".
- The group lists Duration, File Size, Bitrate, Resolution, and Type with correct formatting.
- Values match the Track Detail page (where available).
- Tooltip behavior/positioning remains consistent across layouts.
- No console errors; API returns new fields for likes endpoints.

14) Task Checklist (living document)

- [ ] Extend `api_tracks_by_likes` with `bitrate`, `resolution`, `filetype` fields
- [ ] Update tooltip content in `createTrackTooltipHTML`
- [ ] Manual UI verification across layouts
- [ ] Verify data correctness against `/track/<video_id>`
- [ ] Final pass for accessibility and consistency

15) Future Improvements (Optional)

- Surface YouTube available qualities summary (already computed for Track Detail) in the tooltip as a compact line.
- Add an inline "Rescan media" action from tooltip (contextually out of scope for now).



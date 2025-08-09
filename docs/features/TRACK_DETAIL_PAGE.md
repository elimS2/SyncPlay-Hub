# Track Detail Page (Track Properties View)

## Initial Prompt

Translated from the original request to preserve exact context:

"I want that, for example, here: http://192.168.88.82:8000/tracks, one could click on a track and go to viewing the properties/characteristics of the track on the track page. We could define such a page address http://192.168.88.82:8000/track; we could also show it like http://192.168.88.82:8000/track?youtube_id=EA6u_Xkt8ss or something like that.

=== Analyse the Task and project ===

Deeply analyze our task and our project and decide how to best implement this.

=== Create Roadmap ===

Compose a detailed, extensive step-by-step plan of actions to implement this task in a separate file-document. We have a folder docs/features for this. If there is no such folder, create it. Document in as much detail as possible all issues, nuances, and solutions already discovered and tried, if any. As you progress implementing this task, you will use this file as a todo checklist; you will update this file and document in it what has been done, how it has been done, what problems arose, and what decisions were made. For history do not delete items; you can only update their status and comment them. If during implementation it becomes clear that something needs to be added as tasks, add it to this document. This will help us keep the context window, remember what we have already done, and not forget to do what was planned. Remember that only the English language is allowed in code and comments, labels of the project. When you write the plan, stop and ask me whether I agree to start implementing it or if something needs to be adjusted in it.

Also include in the plan steps for manual testing, i.e., what needs to be clicked in the interface."

---

## Context and Current State

- Framework: Flask-based web app (`app.py`).
- Existing pages:
  - `/tracks` renders `templates/tracks.html` with the DB-backed list of tracks (including stats, playlist names, deleted flag, etc.).
  - The "Video ID" column currently links externally to YouTube: `https://youtu.be/{{ t['video_id'] }}`.
- Database:
  - `tracks` table stores local track info and playback statistics.
  - `track_playlists` ↔ `playlists` map track-to-playlist relations.
  - `youtube_video_metadata` table stores extended YouTube metadata with `youtube_id` and many fields.
  - Helpers exist: `get_youtube_metadata_by_id(conn, youtube_id)` and batch variants.
- No dedicated page exists yet for a single track detail view.

## Goals

- Add an internal Track Detail page with comprehensive information for a single track.
- Make the track listed on `/tracks` clickable to open this page.
- Provide a clean, modern, responsive UI that matches the app style and reuses the existing sidebar/layout.

## Non-Goals (for initial iteration)

- No changes to DB schema are required.
- No editing/modifying track data from the detail page (read-only view first).
- No playlist management actions on the first iteration (can be planned later).

## URL Design

- Canonical route: `/track/<video_id>` (REST-friendly, readable, bookmarkable).
- Compatibility route: `/track?youtube_id=<id>` that redirects (302) to `/track/<id>`.
- Optional: support `/track/<video_id>/` with or without trailing slash (Flask can handle or redirect).

## Data Model and Sources

- Primary track info: `tracks` table by `video_id`.
- Playlist memberships: join `track_playlists` with `playlists` to produce a list of playlist names (and optionally relative paths).
- Extended metadata: `youtube_video_metadata` by `youtube_id` (title, description, channel, timestamps, duration, etc.).
- Deleted-state and usage statistics come from `tracks` fields.

## Backend Changes (Separation of Concerns)

- Add a DB helper in `database.py`:
  - `get_track_with_playlists(conn, video_id: str) -> Optional[Dict]` that returns a single dict combining:
    - Track row fields from `tracks`.
    - Aggregated playlist names (list and comma-joined string), playlist count.
  - Keep SQL grouped and optimized (single query with LEFT JOIN and GROUP_CONCAT where appropriate).
- Add a Flask route in `app.py`:
  - `@app.route("/track")` reads `youtube_id` query param and redirects to canonical path if present; 400 if missing.
  - `@app.route("/track/<video_id>")` loads:
    - `track = get_track_with_playlists(conn, video_id)`
    - `metadata = get_youtube_metadata_by_id(conn, video_id)`
    - Returns 404 if track not found; metadata is optional.
    - Renders `templates/track.html` with a unified context that merges track + metadata.

## Template and Frontend Changes

- New `templates/track.html`:
  - Reuse sidebar and global styles (`sidebar_styles.html`, layout wrappers) for consistency.
  - Page layout sections:
    - Header: title (prefer metadata.title; fallback to `tracks.name`), `video_id`, external actions (Open on YouTube, Copy link).
    - Key properties grid: duration (both file and metadata duration if different), size, bitrate, resolution, filetype, deleted state, stats (starts, finishes, nexts, prevs, likes).
    - Playlist memberships: list with links to `/playlist/<relpath>` where applicable.
    - YouTube metadata: channel, uploader, publish timestamps, description (collapsible), availability/live status.
    - Audit: last start/finish timestamps.
    - Optional: collapsible raw JSON for debugging (`metadata`, `track`).
- New `static/css/track.css` with minimal, page-specific styling, leveraging existing variables and patterns from `tracks.css` for visual consistency.
- Update `templates/tracks.html`:
  - Make the Title and/or Video ID clickable to internal page: link to `/track/{{ t['video_id'] }}`.
  - Optionally keep a small external YouTube icon link next to video ID for quick access.

## Optional API (future-proof)

- Optional: `GET /api/track/<video_id>` returning merged JSON (track + metadata + playlists). Not required for server-rendered page; keep for later if we need a SPA-like view.

## UX, Accessibility, and Consistency

- Keyboard-accessible links and focus states.
- Clear external link icons with `target="_blank"` and `rel="noopener"`.
- Graceful empty states: if metadata missing, show informative note and a button to fetch metadata later (future enhancement).
- Responsive layout with readable typography; consistent with existing pages.

## Performance Considerations

- Single DB round-trip for track + playlists via JOIN.
- Separate retrieval for metadata (single indexed lookup by `youtube_id`).
- No N+1 queries. Cache-friendly path.

## Telemetry and Logging (Minimal)

- Log a server-side info message when a track detail is viewed (optional): `log_message("[Track] View: <video_id>")`.

## Security

- Validate `video_id` as 11-char YouTube ID pattern where appropriate.
- Ensure we do not render unescaped user content in templates (Jinja autoescape on; sanitize long descriptions with `<pre>` or controlled markup).

## Migration / Compatibility

- No DB migrations.
- No breaking changes to existing routes.

## Manual Test Plan (UI Clickthrough)

1. Navigate to `/tracks`.
2. Click on the track Title; expect navigation to `/track/<video_id>`.
3. Verify the header shows the title and the video ID.
4. Verify properties: duration, size, bitrate, resolution, filetype, stats are visible and formatted.
5. Verify playlists section lists all associated playlists; links navigate to `/playlist/<relpath>`.
6. Verify the YouTube metadata panel:
   - Title matches (if available).
   - Channel/uploader data shown.
   - Description is collapsible; expand/collapse works.
7. Click "Open on YouTube"; new tab opens with the correct video.
8. Copy link button copies the canonical URL to clipboard (visual confirmation/toast if implemented).
9. Try direct URL `/track?youtube_id=<id>`; expect redirect to `/track/<id>`.
10. Try invalid ID `/track/INVALID12345`; expect 404 page.
11. Try a deleted track (if present) and ensure deleted badge is shown.
12. Verify mobile responsiveness on narrow viewport.

## Acceptance Criteria

- Track entries on `/tracks` are clickable and open an internal detail page.
- `/track/<video_id>` renders a page with:
  - Track core info, stats, and playlist memberships.
  - YouTube metadata if available; otherwise a clear empty state.
  - Links to YouTube and copyable canonical link.
- `/track?youtube_id=<id>` redirects to the canonical path.
- The implementation follows SOLID, DRY, KISS, and Separation of Concerns.
- The UI is consistent with existing pages and responsive.

## Risks and Edge Cases

- Missing metadata: handled with an empty state (no crash).
- Tracks not found in DB but metadata exists (rare): return 404 for track page.
- Extremely long descriptions: use collapsible container and constrained width.
- Special characters in titles/descriptions: rely on auto-escaping; no unsafe HTML injection.

## Rollout Plan

- Implement behind no flag (low risk).
- Deploy and smoke-test on local network.
- Monitor logs for errors and adjust.

## Step-by-Step Implementation Plan (Checklist)

- [x] Backend: Add `get_track_with_playlists(conn, video_id)` in `database.py` (unit-tested query logic).
  - Notes: Implemented with JOINs and GROUP_CONCAT using safe custom separators; returns `playlists_list`, `playlist_relpaths_list`, `playlists` (human-readable), `playlist_count`, and deleted-state fields.
- [x] Backend: Add routes in `app.py`:
  - [x] `/track` (query param handler → redirect)
  - [x] `/track/<video_id>` (renders detail page)
  - Notes: Input validation via regex for YouTube ID; loads `track` and `metadata`, 404 if track not found.
- [x] Template: Create `templates/track.html` (sections described above).
  - Notes: Minimal inline CSS included for immediate readability; dedicated `track.css` pending.
- [x] CSS: Add `static/css/track.css` for page-specific styling.
  - Notes: Connected to `track.html`; inline styles removed from template.
- [x] Template: Update `templates/tracks.html` to link to internal detail page.
  - Notes: Title and video ID now link to `/track/<video_id>`; external YouTube link preserved as small icon.
- [x] Logging: Optional server-side log on page view.
  - Notes: `log_message("[Track] View: <video_id>")` added in `track_page`.
- [x] Manual testing: Execute the UI test plan.
  - Notes: Verified navigation, properties rendering, playlists linking, metadata section, external link, copy link, and 404 for invalid ID; adjusted template to avoid `zip` filter dependency (used index-based loop).
- [x] Docs: Update this file with statuses, decisions, and any fixes made during implementation.
  - Notes: Checklist statuses updated and notes recorded; ready for review/closure.

## Additional: Manual Tests UI

- Added navigation entry "Manual Tests" in sidebar linking to `/tests`.
- Created tests pages:
  - `/tests` – index of manual tests.
  - `/tests/track_detail` – interactive checklist (radio Pass/Fail/Not tested) with localStorage persistence.
- Files:
  - `app.py` – routes `tests_index`, `tests_track_detail`.
  - `templates/tests/index.html`, `templates/tests/track_detail.html`.
  - `static/css/tests.css`.
  - `templates/sidebar.html` – menu link.

---

## UI/UX Polish Plan for Track Detail Page (Iteration 2)

Observed issues (dark theme screenshot):
- Buttons/pills text unreadable (white text on white background). Our `track.css` uses fixed colors and `color: inherit` that conflict with dark theme tokens.
- Cards/sections are too narrow and spacing is inconsistent.
- Typography contrast and hierarchy are not aligned with `tracks.css` and global styles.

Design decisions:
- Reuse existing design tokens from `player-base.css` and patterns from `tracks.css` for consistency across pages.
- Centralize common components (btn, card, badge, pill) to avoid style drift and ensure DRY.
- Constrain content width and improve responsive grid behavior.

Actionable plan:
1) Create `static/css/components.css` (shared UI primitives):
   - `.card`, `.section-title`, `.btn`, `.btn-primary`, `.btn-secondary`, `.badge`, `.badge-active`, `.badge-deleted`, `.pill`, `.muted`, `.mono`.
   - Use variables: `var(--bg-primary)`, `var(--bg-secondary)`, `var(--bg-card)`, `var(--bg-hover)`, `var(--text-primary)`, `var(--text-secondary)`, `var(--border)`, `var(--accent)`, `var(--accent-hover)`.
   - Ensure sufficient color contrast for dark/light modes (no `color: inherit` on light surfaces).
2) Refactor `static/css/track.css`:
   - Remove hard-coded colors; rely on tokens.
   - Add `.main-content { max-width: 1200px; margin: 0 auto; }` for readable line lengths.
   - Improve `.grid` to 1 column on <1024px, 2 columns on >=1024px.
   - Harmonize paddings/margins with `tracks.css`.
3) Update `templates/track.html`:
   - Ensure buttons/pills use `.btn-secondary`/`.pill` with proper contrast.
   - Remove inline styles and extraneous wrappers.
   - Keep semantic structure and accessibility (aria labels for external link icon).
4) Quick QA:
   - Visual check dark theme (current), verify all texts are readable.
   - Mobile viewport check.
   - Regression check for other pages (no global side-effects).

Acceptance criteria (UI polish):
- All controls and pills have readable text in dark theme.
- Content width is constrained; sections align with consistent spacing.
- Visual style matches `tracks.css` (cards, typography, colors).
- No regressions on `/tracks` and other pages.

Checklist (Iteration 2):
- [x] Components: add `static/css/components.css` and include where needed.
  - Notes: Created and connected; tokens used for color/contrast.
- [x] Track CSS: refactor to tokens, layout, spacing.
  - Notes: Removed hard-coded colors, added container width, prepared grid; kept classes aligned with components.
- [x] Template: align classes, remove inline styles, add aria labels.
  - Notes: Replaced inline margins with `.section`, added aria-label on external link, applied `.btn-secondary`, `.container-narrow`.
- [x] Manual UI test: dark + mobile + contrast.
  - Notes: Adjusted KV grid label width and added `overflow-wrap:anywhere` for long paths; hid empty Playlists card.
- [x] Docs: update this roadmap section with final notes/screens.
  - Notes: Iteration 2 completed. Final look: readable controls in dark theme, constrained content width, consistent spacing; content no longer goes under sidebar (page-specific `.main-content { margin-left: var(--sidebar-width) }`).

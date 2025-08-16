## Max YouTube Quality column on /tracks

### Initial Prompt (translated to English)

"On our page at `http://192.168.88.82:8000/track/HKyrtF7zG_Q` there is a YouTube Qualities section that can display the available formats for the video.

For example, Summary may show:
video: 720p, 360p, 144p | audio: 141kbps opus, 130kbps 2, 73kbps opus ⟲ Rescan YouTube ↻ Refresh

or:
video: 1596p, 1064p, 798p, 532p, 354p, 266p | audio: 129kbps 2, 127kbps opus, 64kbps opus ⟲ Rescan YouTube ↻ Refresh

If you expand Show Details, it lists all formats like:
- 401: 1596p · 24fps · av01.0.12m.08 · 7012kbps · mp4 · 2160p

I want the `/tracks` page to display, in a new column called max_quality, the maximum available quality for each video. In the example above it should be 2160p (if I’m not mistaken).

Some tracks don’t have this data yet because YouTube Qualities were not requested (the video was downloaded before this feature was introduced and nobody clicked ⟲ Rescan YouTube). In such cases the column should simply show a dash.

— Analyze the Task and Project —
Deeply analyze our task, our project and decide how best to implement it.

— Create Roadmap —
Create a detailed, step-by-step plan of actions to implement this task in a separate document under `docs/features`. If such a folder doesn’t exist, create it. Thoroughly document all discovered and tested problems, nuances, and solutions. As you progress, use this file as a to-do checklist: update it and document what’s been done, how it was done, what problems arose, and what decisions were made. Do not delete items for history; update their status or comment. If it becomes clear during implementation that something needs to be added, add it to this document. Remember that code and comments must be in English only. When you write the plan, stop and ask me whether I agree to start implementing it or if anything needs to be adjusted. Also include manual testing steps (what to click in the UI).

— SOLID, DRY, KISS, UI/UX, etc —
Follow principles: SOLID, DRY, KISS, Separation of Concerns, Single Level of Abstraction, Clean Code Practices. Follow UI/UX principles: User-Friendly, Intuitive, Consistency, Accessibility, Feedback, Simplicity, Aesthetic & Modern, Performance, Responsive Design. Use Best Practices."


### 1) Background and Current State

- Track Detail page `/track/<video_id>` already shows "YouTube Qualities" with buttons: ⟲ Rescan YouTube and ↻ Refresh.
  - Template: `templates/track.html` renders summary and details, and fetches `/api/track/<video_id>/youtube_formats`.
  - API: `controllers/api/tracks_api.py`
    - `POST /track/<video_id>/rescan_youtube_metadata` → enqueues job
    - `GET /track/<video_id>/youtube_formats` → returns `available_formats` and `available_qualities_summary` from DB
- Storage: `youtube_video_metadata` has TEXT columns `available_formats` (JSON, normalized) and `available_qualities_summary`.
  - Insert/update: `database.upsert_youtube_metadata()`
  - Extraction: `utils/metadata_utils.create_metadata_dict_from_entry()` builds normalized formats and summary from yt-dlp `entry['formats']`.
- Tracks list page `/tracks`
  - Route: `app.py` → `tracks_page()`
  - Data: built via `database.get_tracks_with_filters_page(...)`, then rendered by `templates/tracks.html`.
  - Current columns: index, title, video_id, playlists, duration, size, bitrate, resolution, type, starts, finishes, nexts, prevs, likes, last_start, last_finish, deleted.


### 2) Goal

- Add a new column "Max YouTube Quality" (key: `max_quality`) to `/tracks` that shows the highest available YouTube video resolution for each track, derived from stored `available_formats`.
- When no formats are stored (never rescanned), render a dash `-`.


### 3) Definition of "Max YouTube Quality"

- Consider only entries with actual video: `vcodec` present and not `none`, and `height` present and > 0.
- Select the maximum by `height` (numeric). FPS is not part of the max-quality comparison; only resolution height.
- Label format: `"{height}p"` (e.g., 2160p, 1440p, 1080p). Do not append "60"; keep label simple and consistent for a table column.
- Ignore storyboard formats and audio-only formats for this computation.
- If no valid video formats exist → `max_quality = None` → display `-`.


### 4) High-Level Design

- MVP: compute per page in Python (no schema change)
  - After obtaining the page of tracks, collect their `video_id`s.
  - Fetch YouTube metadata batch via `database.get_youtube_metadata_batch(conn, video_ids)`.
  - For each metadata row:
    - Parse `available_formats` JSON string (if not null) into a list.
    - Compute `max_quality` using the definition above.
  - Pass a mapping `video_id -> max_quality_label` to the template.
  - Update `templates/tracks.html` to add a new column and render `max_quality_map.get(t['video_id'], '-')`.

- Optional Phase 2 (future): persist precomputed values
  - Add columns in `youtube_video_metadata`: `max_available_height INTEGER`, `max_quality_label TEXT`.
  - Update during metadata save and expose for direct JOIN. This avoids parsing JSON per request and enables server-side sorting/filtering by max quality.


### 5) UI/UX Considerations

- Column header: "Max YouTube Quality"; cell content: `2160p`, `1440p`, `-`.
- Position column near `resolution` to keep related properties together.
- Respect existing responsive table styles in `static/css/tracks.css`.
- If the project supports column visibility preferences, add the new column key `max_quality` to that logic (labels, default visibility, responsive rules).
- Add optional, non-destructive client-side filter controls for `Max YouTube Quality` on `/tracks` with persisted threshold (localStorage).


### 6) Implementation Plan (MVP)

1. Backend: compute map for the current page
   - In `app.py` → `tracks_page()`:
     - After retrieving `tracks` for the page, build `video_ids = [t['video_id'] for t in tracks]`.
     - Call `get_youtube_metadata_batch(conn, video_ids)`.
     - For each `row` in batch, read `available_formats` (TEXT) and `json.loads()` it; skip on JSON error.
     - Compute `max_height = max(f['height'])` over entries with `vcodec` not `none` and numeric `height`.
     - Convert to label: `max_quality_label = f"{max_height}p"`.
     - Store in dict: `max_quality_map[video_id] = label`.
   - Pass `max_quality_map` to the template context.

2. Template: add a new column
   - In `templates/tracks.html`:
     - Add `<th data-col="max_quality" class="col col-max_quality">Max YouTube Quality</th>` after the `resolution` column.
     - Add corresponding `<td data-col="max_quality" class="col col-max_quality">{{ max_quality_map.get(t['video_id'], '-') }}</td>`.

3. Styles
   - In `static/css/tracks.css`:
     - Add `.col-max_quality { /* width/alignment if needed */ }`.
     - Ensure responsive breakpoints either show or hide this column according to the existing strategy.

4. Empty/legacy data handling
   - If a track has no `youtube_video_metadata` row or `available_formats` is empty/invalid → render `-`.

5. Performance
   - Only one extra query per page via `get_youtube_metadata_batch`.
   - JSON parsing for up to `per_page` items (default 200) is acceptable.
   - No N+1 queries.


### 7) Edge Cases

- No formats in DB (older tracks) → `-`.
- Audio-only entries present, no video entries → `-`.
- Storyboard formats present → ignored.
- Corrupted JSON in `available_formats` → guarded with try/except → `-`.
- Multiple entries with the same `height` and different fps/codecs → still show `{height}p`.


### 8) Manual Test Plan

Prerequisites:
- Server is running; DB contains several tracks; some tracks have YouTube formats saved (after a previous rescan).

Steps:
1. Open `/tracks`.
   - Verify a new column "Max YouTube Quality" appears after the `Resolution` column.
   - For tracks with saved formats: values like `2160p`, `1440p`, `1080p` are displayed.
   - For tracks without formats: `-` is displayed.
2. Navigate to a track that currently shows `-` and open `/track/<video_id>`.
   - Click "⟲ Rescan YouTube" and wait for the toast that a job was started.
   - After job completion (or a short wait), click "↻ Refresh" in the YouTube Qualities section and verify formats are shown.
3. Return to `/tracks` (refresh page) and verify that the same track now shows the proper max quality (e.g., `2160p`).
4. Spot check a track whose details show a highest resolution in the list (e.g., 2160p) and confirm the column matches.
5. Test Max Quality client filter:
   - Click thresholds in the "Max YouTube Quality" filter group: All, ≥2160p, ≥1440p, ≥1080p, ≥720p.
   - Ensure rows with lower values or dashes are hidden accordingly.
   - Reload the page and confirm the last chosen threshold persists.


### 9) Future Enhancements (Phase 2+)

- Persist computed values in `youtube_video_metadata` for sorting and filtering server-side:
  - Add `max_available_height INTEGER` and `max_quality_label TEXT` with a migration.
  - Update in `utils/metadata_utils` during save.
  - Extend `/tracks` filtering UI to filter by minimum max quality (e.g., ≥1080p).
- Add a small info icon in the cell to open the Track Detail YouTube Qualities panel in a new tab.

### 9b) Server-side Filtering & Pagination for Max YouTube Quality (New)

Problem:
- Current Max Quality filter on `/tracks` is client-side only. It hides rows after the page is fetched. Pagination and total counts are calculated server-side without this filter, so a user may see only a few matches per page and cannot navigate to all filtered results efficiently.

Decision:
- Implement a true server-side filter and pagination by max quality threshold using denormalized columns in `youtube_video_metadata`.

Data Model Changes:
- Add columns to `youtube_video_metadata`:
  - `max_available_height INTEGER` — maximum video height found in `available_formats` (0 or NULL when unknown)
  - `max_quality_label TEXT` — display label like `2160p`
- Backfill strategy:
  - Default: leave NULL until a rescan updates the row
  - Optional (later): lightweight backfill job to parse existing `available_formats` and fill values

Backend Changes:
- Compute/update these fields inside `utils/metadata_utils.create_metadata_dict_from_entry()` when saving metadata (existing rescan flow will update).
- In `app.py -> tracks_page()`:
  - Parse a new GET param `min_max_quality` (values like 720, 1080, 1440, 2160)
  - Pass `min_max_quality` into DB listing call
- In `database.get_tracks_with_filters_page(...)`:
  - The query already LEFT JOINs `youtube_video_metadata ym`. Extend WHERE when `min_max_quality` is provided: `ym.max_available_height >= ?`
  - Apply the same condition in the `count_sql` and `page_sql` to keep total and page rows consistent
  - Tracks with NULL `max_available_height` will not pass the threshold (treat as 0)
- Consider adding an index for performance (optional): `CREATE INDEX IF NOT EXISTS idx_ym_max_height ON youtube_video_metadata(max_available_height)`

UI Changes:
- Replace the current client-side Max Quality filter on `/tracks` with a server-side submission control:
  - Add a hidden input `min_max_quality` to the filters form
  - Buttons (All, ≥2160p, ≥1440p, ≥1080p, ≥720p) set the hidden value and submit the form
  - Show a small summary text with the active threshold
- Remove the localStorage-based client-only filter logic (or no-op it) to avoid confusion

Manual Test Plan (Server-side):
1. Open `/tracks?min_max_quality=720&per_page=200` and verify up to 200 items match the filter on the first page.
2. Check pagination shows total and page count for the filtered set; Next page includes remaining matches (e.g., 30 on page 2 if total 230).
3. Change threshold to `1080` and verify counts/pages update accordingly.
4. Ensure tracks with no YouTube formats (NULL max height) are excluded, and those gain visibility after Rescan YouTube updates metadata.

Risks & Mitigations:
- Old rows missing denormalized fields → excluded by design until a rescan; communicate via tooltip/help.
- Query performance on large datasets → optional index on `max_available_height`.

Status: Implemented.
Notes:
- One-time backfill script added: `scripts/backfill_max_youtube_quality.py` (no network).
- Pagination link generation in `templates/tracks.html` adjusted to handle URLs without existing `page` param.

### 9c) Batch Enqueue for Missing YouTube Qualities via Maintenance Page (New)

Goal:
- Allow periodically enqueuing Single Video Metadata Extraction jobs for tracks that do not yet have YouTube Qualities, with an adjustable limit (e.g., 100) from `/maintenance`.

Implementation:
- API endpoint: `POST /api/scan_missing_youtube_qualities` in `controllers/api/metadata_api.py`.
  - Request JSON: `{ limit?: number, force_update?: boolean (default true), dry_run?: boolean }`.
  - Criteria (not deleted): missing qualities when `youtube_video_metadata` row is absent OR `available_formats` empty/NULL OR `max_available_height` NULL.
  - Enqueues `JobType.SINGLE_VIDEO_METADATA_EXTRACTION` (LOW priority) up to `limit` items.
  - Returns `{ status, tracks_found, jobs_created, jobs_failed }` (or preview for `dry_run`).
- UI (`templates/maintenance.html` → Metadata Operations section):
  - Added number input for Limit and button “Enqueue Missing YouTube Qualities”.
  - Calls the endpoint with the provided limit; shows status.

Manual Test:
1) Open `/maintenance` → Metadata Operations.
2) Enter limit (e.g., 100) and click the button.
3) Verify success message with jobs count; check `/jobs` page for queued jobs.
4) After jobs complete, YouTube Qualities appear on `/track/<id>` and max quality on `/tracks`.


### 10) Checklist (living document)

- [x] Backend: compute `max_quality_map` in `tracks_page()` using batch metadata fetch
- [x] Template: add `<th>`/`<td>` for `max_quality`
- [x] Styles: ensure column is responsive and readable
- [x] Manual tests: run through the steps above (smoke and interactive checks passed)
- [ ] Code review for SOLID/DRY/KISS and UI consistency
- [x] Wire into column-visibility preference UI (added checkbox and defaults)
 - [x] Client-side filter controls for Max Quality with persisted threshold
 - [x] Migration: add `max_available_height` and `max_quality_label` to `youtube_video_metadata` (plus safeguard in `database.py`)
 - [x] Compute/update fields in `utils/metadata_utils`
 - [x] Backend: add `min_max_quality` filter in `/tracks` (controller + DB query)
 - [x] UI: convert Max Quality filters to server-submitted parameter and remove client-only filtering
 - [x] One-time backfill script to populate fields from existing `available_formats`
 - [x] Manual tests for server-side pagination with filter
 - [x] Maintenance: endpoint and UI to enqueue missing YouTube Qualities with limit


### Notes on Principles and Practices

- SOLID/SoC: Computation isolated to controller; no JSON parsing in templates.
- DRY: Reuse existing batch metadata accessors; single computation function in controller scope.
- KISS: Label only contains resolution height (e.g., `2160p`).
- Performance: Single batch DB call and O(N) JSON parse per page; acceptable.
- UI/UX: Non-intrusive column; uses `-` fallback; aligns with existing table style.
 - Client filter: non-destructive, instant feedback, persists in localStorage, no extra server load.

### Implementation Nuances encountered

- Kept computation in `app.py: tracks_page()` using `get_youtube_metadata_batch()` and `json.loads()` with fail-safe guards to avoid breaking the page if JSON is corrupt or missing.
- Decided to strictly use highest `height` across video-capable formats (`vcodec` != 'none') and ignore FPS/codec for the max label to keep the column compact and sortable.
- Added CSS rule `.col-max_quality { white-space: nowrap; }` to prevent line-wrapping of labels like `2160p`.

### Next Step

- Update column visibility controls (if required) to include `max_quality` with sensible defaults. Optionally, consider adding server-side sorting/filtering by max quality in a future phase.



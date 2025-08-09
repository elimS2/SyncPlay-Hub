## Feature: On-demand media properties rescan (bitrate, resolution) on Track page

### Goal
- Add a small button near the Bitrate and Resolution fields on the Track Detail page (`/track/<video_id>`) to rescan media properties from the currently stored local file and update the database accordingly.

### Initial Prompt (translated)

The user request translated to English for exact context preservation:

"I want a button on the page at http://192.168.88.82:8000/track/EBj73_z1a9M next to bitrate and resolution that would rescan the bitrate and resolution and update it in the database. That is, a utility or some code should obtain this information directly from the file that is currently saved on disk.

=== Analyse the Task and project ===

Deeply analyze our task, our project, and decide how best to implement it.

==================================================

=== Create Roadmap ===

Create a detailed, step-by-step plan of actions for implementing this task in a separate document file. We have a folder docs/features for this. If there is no such folder, create it. Document in this file all issues, nuances, and solutions already discovered and tried, if any. As you progress with implementing this task, you will use this file as a to-do checklist, updating this file and documenting what is done, how it is done, what problems occurred, and what solutions were made. For history, do not delete items, only update their status and comment. If during the implementation it becomes clear that something needs to be added from sub-tasks — add it to this document. This will help us preserve the context window, remember what we have already done, and not forget to do what was planned. Remember that in the code and comments, project text must be only in English. When you finish the plan, stop and ask me if I agree to start implementing it or if anything needs to be adjusted.

Also include steps for manual testing, i.e., what to click in the interface.

==================================================

=== SOLID, DRY, KISS, UI/UX, etc ===

Follow the principles: SOLID, DRY, KISS, Separation of Concerns, Single Level of Abstraction, Clean Code Practices.
Follow UI/UX principles: User-Friendly, Intuitive, Consistency, Accessibility, Feedback, Simplicity, Aesthetic & Modern, Performance, Responsive Design.
Use Best Practices."

---

### Current state analysis

- Track detail page rendering:
  - `app.py` route `track_page(video_id)` renders `templates/track.html` with `track` and `metadata` contexts.
  - In `templates/track.html`, Bitrate and Resolution are displayed from DB fields:

    ```41:60:templates/track.html
    <div class="muted">Bitrate</div><div>{% if track.get('bitrate') %}{{ (track['bitrate']/1000)|int }} kbps{% else %}-{% endif %}</div>
    <div class="muted">Resolution</div><div>{{ track.get('resolution') or '-' }}</div>
    ```

- Database schema (SQLite) includes media fields on `tracks` table:

  ```56:73:database.py
  CREATE TABLE IF NOT EXISTS tracks (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      video_id TEXT NOT NULL UNIQUE,
      name TEXT NOT NULL,
      relpath TEXT NOT NULL,
      duration REAL,
      size_bytes INTEGER,
      bitrate INTEGER,
      resolution TEXT,
      filetype TEXT,
      ...
  );
  ```

- Existing media probing logic using `ffprobe` already exists and is used during scans:
  - `scan_to_db.py::ffprobe_duration(path)` returns `(duration, bitrate, resolution)` using `ffprobe`.
  - `controllers/api/channels_files_api.py::api_rescan_files()` defines an identical helper inside bulk-rescan endpoint.

- Source of truth for local file path:
  - `tracks.relpath` (relative to ROOT_DIR) + `controllers/api/shared.get_root_dir()` gives the absolute path to the media file that should be probed.

### Requirements

- Add an API to rescan media properties (bitrate and resolution) for a single `video_id`.
- The API should probe the existing local file derived from DB `relpath`.
- Update the `tracks` table with new values, minimally `bitrate` and `resolution`. Optionally refresh `duration` and `size_bytes` if present.
- Provide clear JSON response with updated values and status/errors.
- Add a small inline UI button next to Bitrate/Resolution on the Track page to trigger the rescan.
- Provide basic UX feedback (loading state, success toast, error message). Keep it simple and consistent with existing styles.

### Design decisions

- Separation of Concerns, DRY:
  - Extract a reusable `ffprobe_media_properties(path: Path) -> tuple[Optional[float], Optional[int], Optional[str]]` to a shared utility (e.g., `utils/metadata_utils.py` or new `utils/media_probe.py`) to eliminate duplication across `scan_to_db.py` and `channels_files_api.py`.
  - Use a dedicated API blueprint module (proposed: `controllers/api/tracks_api.py`) to host per-track operations.

- API shape:
  - Method: `POST`
  - URL: `/api/track/<video_id>/rescan_media`
  - Body: optional `{ "refresh_duration": bool, "refresh_size": bool }` (defaults false/false). MVP can omit body entirely.
  - Response: `{ status: "ok", video_id, bitrate, resolution, duration, size_bytes }` on success; `{ status: "error", error }` on failure.
  - Timeouts: run `ffprobe` with a reasonable timeout (10–15s). Return error if timed out or file missing.

- DB updates:
  - Add a small helper in `database.py`: `update_track_media_properties(conn, video_id, *, bitrate=None, resolution=None, duration=None, size_bytes=None)` that performs a partial `UPDATE` with only provided fields.
  - Alternatively, implement the direct UPDATE in the endpoint (acceptable for MVP). For maintainability, prefer the helper.

- UI/UX:
  - Add a tiny inline button/icon next to Bitrate/Resolution rows (single button for both properties to keep UI minimal). Label: "Rescan" with a refresh icon (Unicode or simple text) and `title="Rescan media properties"`.
  - On click: call the API, show disabled/loading state, then either update values in place or reload the page. MVP: reload the page for simplicity and consistency.
  - Use existing `track.css` styles; add a minimal `.inline-action` class if needed.

- Error handling and feedback:
  - If file is missing: return 404-like JSON and render a toast or inline message.
  - If `ffprobe` is not available/returns N/A: set fields to `None` where appropriate; show a warning.

### Implementation plan (step-by-step)

1) Backend utilities (DRY)
   - [x] Create `utils/media_probe.py` with `ffprobe_media_properties(path: Path, timeout: int = 10)` using JSON ffprobe output to extract duration, overall bitrate, and resolution (`"{width}x{height}"`).
   - [x] Replace/centralize duplicated helpers in `scan_to_db.py` and `controllers/api/channels_files_api.py` to call the new utility (can be a follow-up if scope needs to be minimal now).

2) Database helper
   - [x] In `database.py`, add `def update_track_media_properties(conn, video_id: str, *, bitrate: Optional[int] = None, resolution: Optional[str] = None, duration: Optional[float] = None, size_bytes: Optional[int] = None) -> bool` that builds a dynamic UPDATE for provided fields.
   - [ ] Unit-test lightly or rely on manual testing by checking persisted values on the UI.

3) API endpoint
   - [x] Create `controllers/api/tracks_api.py` blueprint with route: `@tracks_bp.route("/track/<video_id>/rescan_media", methods=["POST"])`.
   - [x] Steps inside endpoint:
       - [x] Validate `video_id` format.
       - [x] Fetch `relpath` from DB using `SELECT relpath FROM tracks WHERE video_id = ?`.
       - [x] Resolve absolute path: `get_root_dir() / relpath`; validate existence and that it is a file.
       - [x] Call `ffprobe_media_properties` to get new `(duration, bitrate, resolution)`; compute `size_bytes = file.stat().st_size`.
       - [x] Update DB with `update_track_media_properties` for provided non-None fields (minimally bitrate, resolution). Optionally refresh duration and size based on request flags.
       - [x] Return JSON payload with new values.
   - [ ] Register `tracks_bp` in `controllers/api/__init__.py` under the main `api_bp`.
   - [x] Register `tracks_bp` in `controllers/api/__init__.py` under the main `api_bp`.

4) Frontend (templates/track.html)
   - [x] Add a small inline button next to Bitrate/Resolution rows. Example: `<button class="inline-action" id="rescanMediaBtn" title="Rescan media properties">⟲ Rescan</button>`.
   - [x] Add a small `<script>` at the bottom of the template to POST to `/api/track/{{ video_id }}/rescan_media`, toggle loading state, and on success update DOM nodes for bitrate/resolution (no full reload in MVP).
   - [x] Add minimal styles in `static/css/track.css` for `.inline-action`.

5) Logging and observability
   - [x] Log start/end of per-track rescan with `video_id` and results in endpoint (`controllers/api/tracks_api.py`).
   - [x] Library scan worker logs progress every ~100 tracks and final summary via `job.log_info`.
   - [ ] Consider adding a lightweight event to `play_history` (optional) to record maintenance activities.

6) Edge cases
   - [ ] Audio-only tracks: `resolution` should be `None`/`-`; ensure UI displays `-`.
   - [ ] `ffprobe` returns `N/A` or missing fields: fallback to previous DB values unless explicitly overwritten with `None`.
   - [ ] Missing file: return error and display a user-friendly message; do not change DB values.
   - [ ] Very large files or corrupted media: ensure timeout and error handling.

7) Documentation
   - [ ] This roadmap will be updated during implementation. Do not remove completed items; mark them and add brief notes.

### Data model impact

- No schema changes required. Using existing `tracks.bitrate` (INTEGER) and `tracks.resolution` (TEXT). Optional update of `duration` and `size_bytes` with already existing columns.

### Security considerations

- Endpoint is internal (same LAN); no authentication currently. If needed later, add a simple token gate or admin-only route.
- Sanitize `video_id` format; resolve path strictly via `relpath` to avoid path traversal.

### Performance considerations

- Rescan is on-demand for a single track; `ffprobe` is fast. Add a 10–15s timeout to avoid hanging worker.
- Avoid spawning multiple rescans for the same track concurrently in the UI (disable button while running).

### UI/UX guidelines applied

- Consistency: button styling matches existing `track.css` aesthetic.
- Feedback: button disabled while running and shows a simple success/failure toast or reloads the page.
- Feedback: button disabled while running and shows a simple success/failure toast using `static/js/modules/toast-notifications.js`.
- Simplicity: one button that refreshes both Bitrate and Resolution at once.

### Testing plan (manual)

1) Happy path
   - Open `/track/<video_id>` for a known media file.
   - Note current Bitrate and Resolution values.
   - Click "Rescan"; wait for completion.
   - Verify values updated (or remained the same) and the page reflects changes.
   - Refresh the page to confirm persistence.

2) Audio-only file
   - Open a track with `.mp3`/`.m4a`.
   - Click "Rescan"; verify Resolution is `-` and Bitrate is set if available.

3) Missing file
   - Temporarily move/rename the underlying file.
   - Click "Rescan"; expect error message and no DB changes.

4) Corrupted or unsupported file
   - Try a problematic file; ensure timeout handling and a clear error response.

5) N/A values from ffprobe
   - Ensure the code correctly interprets `N/A` and does not crash; UI shows `-`.

6) Performance/regression
   - Click the button multiple times; ensure button disables during in-flight request and no duplicates are created.

### Acceptance criteria

- A POST endpoint `/api/track/<video_id>/rescan_media` updates `tracks.bitrate` and `tracks.resolution` based on the current local file.
- Track page shows a small inline button near Bitrate/Resolution to trigger rescan.
- On success, the UI reflects updated values (by reload or DOM update) and the values persist in DB.
- Proper error responses for missing file or probe failures; no DB corruption.

### Rollout plan

- Implement backend (utility + DB helper + endpoint).
- Implement frontend button and simple JS handler.
- Manual test on local environment with several files.
- Monitor logs for errors; iterate on edge cases if discovered.

### Maintenance page integration (jobs)

- [x] Add Library Scan worker to rescan media properties for all non-deleted tracks:
  - New worker: `services/job_workers/library_scan_worker.py` handling `JobType.LIBRARY_SCAN`.
  - Registers on startup in `app.py` alongside other workers.
- [x] Add button to `templates/maintenance.html` to enqueue a Library Rescan job via `/api/jobs` (type `library_scan`).
- [ ] Verify job executes and updates bitrate/resolution across library; monitor logs.

### Jobs page monitoring enhancements

- [x] Expose `Library Scan` job type in `/jobs`:
  - Added to job creation form and job type filter.
  - Dynamic parameters for this type: `refresh_duration` and `refresh_size` (select Yes/No).
- [x] Auto-refresh queue status and job list every 5s (already present on the page).
- [x] Job details modal: "Load Logs" button shows job, stdout, stderr, progress, summary logs when available.
- [ ] Optional: auto-refresh logs within the modal every 5–10s while it is open.
- [ ] Optional: add "Open Logs" button directly in the jobs table rows for one-click access.

### Stability and noise reduction

- [x] Prefer ffprobe-first for video probing to avoid noisy moviepy warnings (attachments in MKV/WebM).
- [x] Suppress non-critical `UserWarning` from moviepy when fallback is used.
- [x] Fix: replace non-existent `job.log_warning` with `job.log_info` in `LibraryScanWorker`.

### Dedicated test page for manual verification

To make QA predictable and repeatable, add a dedicated test page similar to the existing `tests/track_detail` page, but focused on media rescan scenarios.

- [x] Create template: `templates/tests/media_properties_rescan.html` that lists clickable test cases as proper relative links (no plain/non-clickable path texts). Examples:
  - Valid track (replace with a known existing video ID):
    - `<a href="/track/EBj73_z1a9M">/track/EBj73_z1a9M</a>`
  - Invalid ID should show 404 page:
    - `<a href="/track/INVALID12345">/track/INVALID12345</a>`
  - Audio-only track (if available):
    - `<a href="/track/AAAAAAAAAAA">/track/AAAAAAAAAAA</a>`
  - Missing file case (link to a track known to be deleted or moved):
    - `<a href="/track/BBBBBBBBBBB">/track/BBBBBBBBBBB</a>`
  - Edge case file (very large, or previously problematic):
    - `<a href="/track/CCCCCCCCCCC">/track/CCCCCCCCCCC</a>`

- [x] Add a route in `app.py` (e.g., `@app.route("/tests/media_rescan")`) to render the page.
- [x] Add a link from `templates/tests/index.html` to `"/tests/media_rescan"` for discoverability.
- [ ] Keep the page simple, using existing test styles, and ensure all items are true anchors (`<a href="...">`) with relative paths.

This page will be used during acceptance to verify:
- The track page loads for the given IDs and shows the Rescan button.
- Rescan behaves as expected in each scenario (success, 404, missing file, audio-only, edge case).

### Future improvements (optional)

- Batch rescan from the Track page for all media properties, including codec, channels, sample rate.
- Job-queue based async rescan for long files, with progress indicator.
- Add per-track audit events for maintenance actions.

### Open questions

- Should duration and size be forcibly refreshed alongside bitrate/resolution? (Default proposal: yes, but keep them optional in API.)
- Where to place the shared probe utility to best fit current module boundaries: `utils/metadata_utils.py` vs `utils/media_probe.py`? (Proposal: new `utils/media_probe.py`.)



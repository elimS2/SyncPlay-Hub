YouTube Available Qualities on Track Detail Page — Roadmap

Initial Prompt

"At http://192.168.88.82:8000/track/wk4v4MxcUQI on this page there is a Rescan button. Can we display on this page not only the current downloaded bitrate, but also what is available on YouTube? And maybe create a separate field in the table that stores this information. That is, an additional command/script/code should be triggered that fetches the metadata from YouTube and obtains the list of available qualities for this video. Perhaps, in principle, we can just create and run the Single Video Metadata Extraction job, and if it doesn’t currently include information about which qualities are available on YouTube, then add it. Essentially, this would be a metadata rescan. — Analyze the Task and Project — Deeply analyze our task, our project and decide how best to implement this. — Create Roadmap — Create a detailed, step-by-step plan of actions to implement this task in a separate file-document. We have a folder docs/features for this. If there is no such folder, create it. Document in this file as thoroughly as possible all discovered and tested problems, nuances and solutions, if any. As you progress with implementation, you will use this file as a to-do checklist, updating it and documenting what’s been done, how it was done, what problems arose, and what decisions were made. For history, do not delete items; you can only update their status and comment. If during implementation it becomes clear that something needs to be added to the tasks, add it to this document. This will help us preserve the context window, remember what we have already done, and not forget to do what was planned. Remember that code and comments, project labels must be only in English. When you write the plan, stop and ask me whether I agree to start implementing it or if something needs to be adjusted. Also include steps for manual testing, i.e., what needs to be clicked in the interface. — SOLID, DRY, KISS, UI/UX, etc — Follow principles: SOLID, DRY, KISS, Separation of Concerns, Single Level of Abstraction, Clean Code Practices. Follow UI/UX principles: User-Friendly, Intuitive, Consistency, Accessibility, Feedback, Simplicity, Aesthetic & Modern, Performance, Responsive Design. Use Best Practices."


1. Background and Current State

- Track Detail page (`/track/<video_id>`) is rendered by `track_page()` and template `templates/track.html`.
  - Current UI shows file-based media properties (Duration, Size, Bitrate, Resolution, Type, Relpath) with an inline "Rescan" button that calls `/api/track/<video_id>/rescan_media` to re-probe the local file via `ffprobe`.
- YouTube metadata is stored in `youtube_video_metadata` and retrieved for the page via `get_youtube_metadata_by_id()`.
- A Job Queue exists with `SINGLE_VIDEO_METADATA_EXTRACTION` implemented in `SingleVideoMetadataWorker`, which runs `yt-dlp --dump-json` and stores metadata using `utils.metadata_utils.save_video_metadata_from_entry()` and `database.upsert_youtube_metadata()`.
- Today, we do not persist the list of available YouTube formats/qualities. The Track page does not show them.

Key references:
- templates/track.html: inline Rescan for local media properties.
- controllers/api/tracks_api.py: `POST /api/track/<video_id>/rescan_media`.
- services/job_workers/single_video_metadata_worker.py: extracts and saves YouTube metadata.
- utils/metadata_utils.py and database.py: metadata mapping and upsert logic.


2. Goals and Non-Goals

- Goals
  - Display on the Track Detail page the available YouTube qualities (formats) for the video in addition to the locally downloaded bitrate/resolution.
  - Persist this information in the database to avoid repeated network calls and to enable quick display.
  - Integrate with the existing Single Video Metadata Extraction job, extending it to also save `formats` and a compact summary.
  - Provide a Rescan flow to refresh YouTube formats on demand.

- Non-Goals
  - Do not implement automatic background refresh on every page view (avoid rate limits and latency). Manual rescan suffices in MVP.
  - Do not build a full job status polling UI on this page in MVP (we already have Jobs page). Simple feedback is enough.


3. Data Model Changes

- Add new columns to `youtube_video_metadata` via a migration:
  - `available_formats` TEXT — raw JSON-serialized array of yt-dlp `formats` (trimmed/normalized to essential fields to reduce size).
  - `available_qualities_summary` TEXT — compact human-readable summary (e.g., a comma-separated list of video resolutions and top audio bitrates/codecs) for quick UI rendering.

Notes:
- Keeping formats in `youtube_video_metadata` maintains separation from local file properties in `tracks`.
- The summary helps fast rendering without client-side heavy processing; UI can render the summary and optionally expand into the raw list.


4. Backend Changes

- Migration
  - Create `database/migrations/migration_008_add_youtube_formats.py` to add the two columns.
  - Update `database._ensure_schema()` post-creation column-checks for backfill on older DBs.

- Metadata extraction pipeline
  - Extend `utils.metadata_utils.create_metadata_dict_from_entry()` to:
    - Read `entry.get('formats', [])`.
    - Normalize each format to a compact dict subset (e.g., `format_id`, `format_note`, `ext`, `vcodec`, `acodec`, `tbr`/`abr`, `asr`, `fps`, `width`, `height`, `filesize`/`filesize_approx`).
    - Serialize to JSON for `available_formats`.
    - Produce `available_qualities_summary` (e.g., highest video resolution with fps and codec; top 3 video ladders; top 2 audio bitrates with codec).
  - Extend `database.upsert_youtube_metadata()` to include the two new fields.
  - In `SingleVideoMetadataWorker`, keep using `save_video_metadata_from_entry()` so changes are centralized.

- New API endpoints (Track-focused)
  - `POST /api/track/<video_id>/rescan_youtube_metadata`
    - Validates `video_id`, enqueues `SINGLE_VIDEO_METADATA_EXTRACTION` with `force_update=true`.
    - Returns `{ status: 'started', job_id }`.
  - `GET /api/track/<video_id>/youtube_formats`
    - Returns `{ status: 'ok', available_formats, available_qualities_summary, updated_at }` from DB for light-weight UI refresh.

Rationale:
- Avoid blocking HTTP while yt-dlp runs; use Job Queue for network/CPU-bound work. A separate GET allows the UI to fetch updated data without full page reload.


5. Frontend/UI Changes (templates/track.html)

- Add a new "YouTube Qualities" section below file properties:
  - Shows `available_qualities_summary` by default.
  - A small "Show details" toggler expands to a list/table of formats from `available_formats`.
  - Add a button "Rescan YouTube" that calls the new `rescan_youtube_metadata` endpoint, disables during request, shows toast, and then refetches via `GET /api/track/<video_id>/youtube_formats` to refresh the section.

UX notes:
- Keep the current local media "Rescan" button unchanged to preserve SoC.
- Use consistent small inline action styles (`.inline-action`).
- Provide clear success/error toasts.


6. Manual Test Plan

Prerequisites
- Server running, Job Queue active (already started in `app.py`).
- A track exists for the tested `video_id`.

Steps
1) Open `/track/<video_id>`
   - Verify existing file properties render as before.
2) Verify the new "YouTube Qualities" section:
   - If metadata exists: summary is visible; details toggle expands a list of formats.
   - If metadata is missing: show an informational empty state.
3) Click "Rescan YouTube"
   - Observe disabled state + loading label.
   - On success, a toast with job started and job id.
4) After a short delay (or via a "Refresh" link), the UI fetches `GET /api/track/<id>/youtube_formats`:
   - Summary updates; formats list is available.
5) Click existing "Rescan" (local media) to ensure no regressions.
6) Edge cases:
   - Private/age-restricted/unavailable video: endpoint returns error toast; UI remains stable.
   - Slow job: repeated manual refresh fetches older data until job completes.


7. Edge Cases and Considerations

- yt-dlp output size: we store a compact subset of `formats` to limit DB bloat.
- Rate limiting: manual-only rescan avoids background storms.
- Cookies: worker already supports cookies for restricted content.
- Existing metadata: `force_update=true` ensures refresh even if metadata exists.
- Audio-only content: summary should handle no video formats gracefully.
- Shorts: treat as regular videos; formats often limited.


8. Implementation Steps (Checklist)

- [x] Migration: add columns `available_formats` (TEXT), `available_qualities_summary` (TEXT).
- [x] `database._ensure_schema()` backfill for older DBs.
- [x] Extend `utils.metadata_utils.create_metadata_dict_from_entry()` to extract/normalize `formats` and compute summary.
- [x] Extend `database.upsert_youtube_metadata()` to persist the new fields.
- [x] New endpoints in `controllers/api/tracks_api.py`:
  - [x] `POST /api/track/<video_id>/rescan_youtube_metadata` (enqueue job, force_update).
  - [x] `GET /api/track/<video_id>/youtube_formats` (serve from DB).
- [x] Update `templates/track.html` to render YouTube Qualities section, add buttons, client fetch/refresh.
- [x] Add basic styles if needed (reuse existing CSS components).
- [x] Improve readability in dark theme (high-contrast palette, readable links, larger buttons).
- [ ] Smoke test locally; verify Jobs and DB.
- [ ] Document behavior in `docs/features/` and update this file with outcomes.


9. Open Questions (to confirm before implementation)

- Do we prefer one combined "Rescan" that triggers both local media probe and YouTube metadata, or keep two separate buttons? Proposal: keep separate for clarity and reliability.
- Summary format: is a compact one-line summary enough, or should we render top N video and audio formats explicitly on the page? Proposal: show summary + collapsible details.
- Any cap on the number of formats to store/display? Proposal: store all normalized formats, display top N in details with a "Show more" expander.


10. Rollout and Migration

- Safe migration via `ALTER TABLE` with IF NOT EXISTS checks in bootstrap.
- No breaking API changes; new endpoints are additive.
- If migration fails, YouTube qualities UI gracefully hides and a tooltip suggests running migration.


11. Definition of Done

- New DB columns present and populated after rescan.
- Track page shows YouTube qualities summary and details.
- Rescan YouTube button enqueues job and UI can refresh to show updated results.
- No regressions to existing rescan media flow.


12. Appendix: Data Normalization for Formats

- Per format fields to keep:
  - `format_id`, `format_note`, `ext`, `vcodec`, `acodec`, `tbr` (kbps), `abr` (kbps), `asr` (Hz), `fps`, `width`, `height`, `filesize` or `filesize_approx`.
- Summary derivation:
  - Highest `height` and `fps` across video; list unique ladders (e.g., 2160p, 1440p, 1080p60, 720p, 480p).
  - Highest audio `abr` and codec; list top two.


Status Log (to be updated during implementation)

- 2025-08-09: Draft roadmap created. Pending approval to proceed with implementation.
- 2025-08-09: Implemented DB migration `008` and `_ensure_schema` backfill for new columns in `youtube_video_metadata`.
- 2025-08-09: Added formats normalization and summary generation; wired new fields into upsert logic.
- 2025-08-09: Implemented API endpoints for YouTube rescan and formats retrieval.
- 2025-08-09: Updated Track page UI with YouTube Qualities section; reused existing inline-action styles; client-side fetch/refresh implemented.


13. Enhancement: Redownload in Selected Quality (New Scope)

Goal
- Allow the user to redownload a track in a different YouTube quality while keeping the same DB record (`video_id`), replacing the on-disk file and updating DB fields (including `relpath` if extension changes).

Design
- API: `POST /api/track/<video_id>/redownload`
  - Body: `{ format_id?: string, format_selector?: string, audio_only?: boolean }`
  - Behavior: enqueues `SINGLE_VIDEO_DOWNLOAD` with:
    - `playlist_url`: `https://www.youtube.com/watch?v=<video_id>`
    - `target_folder`: directory of current `relpath` (ensures in-place replacement)
    - `format_selector`: derived from `format_id` (e.g., `"<format_id>+bestaudio/best"` for video) or pass-through
    - `force_overwrites: true`, `ignore_archive: true`
  - Returns: `{ status: 'started', job_id }`

- Worker completion/update
  - After successful download, update DB to reflect the new file:
    - Locate the downloaded file by scanning `target_folder` for filename ending with `[<video_id>].<ext>` (latest mtime)
    - Update `tracks.relpath` to the new relative path
    - Optionally trigger media rescan (bitrate/resolution/size) using existing utilities

- UI
  - In the "YouTube Qualities" details list, add small actions:
    - “Download this quality” next to each video format (uses `format_id`)
    - A compact dropdown + single button variant for mobile
  - After enqueue, show toast with job id. User can press Refresh later to see updated summary.

Implementation Steps (Checklist)
- [x] API endpoint `POST /api/track/<video_id>/redownload` to enqueue `SINGLE_VIDEO_DOWNLOAD` with proper parameters.
- [x] Enhance `PlaylistDownloadWorker` (single video path) to update `tracks.relpath` post-download for this `video_id` and trigger media rescan.
- [x] UI: add actions in formats list to request redownload with selected `format_id`.
- [x] Manual tests: verify overwrite works, `relpath` updates on extension change, media properties refreshed, DB keeps same `video_id`.

14. Enhancement: MP4 Normalization without Recode (1080p preferred)

Design
- Prefer MP4/H.264 + AAC selection and remux into MP4 (no re-encode):
  - Selector chain: `bestvideo[ext=mp4][vcodec*=avc1][height=1080]+bestaudio[ext=m4a] / 137+140 / bestvideo[ext=mp4][vcodec*=avc1][height<=1080]+bestaudio[ext=m4a] / best[ext=mp4]`.
- If no compatible MP4 pair exists, keep original container (no recode).
- Worker adds `--merge-output-format mp4` to enforce MP4 remux when possible.

Status
- [x] Implemented API defaults (`prefer_mp4=true`, `target_height=1080`).
- [x] Worker merges into MP4 when possible; otherwise preserves original.
- [x] Old-variants cleanup after DB relpath points to new file.

Notes
- Safety: use `force_overwrites` to replace existing file; ensure rollback behavior on failure (no DB change if file missing).
- For audio-only requests, choose correct `format_selector` to avoid muxing video.



## Feature: Add Frame Rate (FPS) and Codec to Track Media Properties (Rescanable)

### Initial Prompt

"At http://192.168.88.82:8000/track/novsAgKSNKU the page already shows Size, Bitrate, and Resolution, which can be rescanned by clicking the Rescan button.

Or you can rescan the entire library here: http://192.168.88.82:8000/maintenance by clicking Enqueue Library Rescan.

So. I want to add frame rate and codec. If these fields do not exist in the database, then add them via a migration.

=== Analyse the Task and project ===

Deeply analyze our task and our project and decide how best to implement it.

==================================================

=== Create Roadmap ===

Create a detailed, step-by-step plan of actions to implement this task in a separate file-document. We have a folder docs/features for this. If there is no such folder, create it. Document in the file, as thoroughly as possible, all discovered and tried problems, nuances and solutions, if any. As you progress with this task you will use this file as a todo-checklist, you will update this file and document what has been done, how it was done, what problems arose and what decisions were made. For history, do not delete items, only update their status and add comments. If during the implementation it becomes clear that something needs to be added to the tasks – add it to this document. This will help us preserve context, remember what has already been done, and not forget to do what was planned. Remember that only the English language is allowed in the code and comments, labels of the project. When you write the plan, pause and ask me if I agree to start implementing it or if anything needs to be adjusted in it.

Include in the plan steps for manual testing, i.e., what needs to be clicked in the interface.

==================================================

=== SOLID, DRY, KISS, UI/UX, etc ===

Follow the principles: SOLID, DRY, KISS, Separation of Concerns, Single Level of Abstraction, Clean Code Practices.
Follow UI/UX principles: User-Friendly, Intuitive, Consistency, Accessibility, Feedback, Simplicity, Aesthetic & Modern, Performance, Responsive Design.
Use Best Practices."

---

### Current state analysis

- Track Detail page (`templates/track.html`) shows file-based media properties: Duration, Size, Bitrate, Resolution, Type, Relpath. There is an inline Rescan button that calls the per-track rescan endpoint.
- Per-track rescan endpoint: `POST /api/track/<video_id>/rescan_media` in `controllers/api/tracks_api.py` currently probes and updates Bitrate, Resolution (optional Duration and Size) using `utils.media_probe.ffprobe_media_properties`.
- Full-library rescan is supported via Jobs: Maintenance page has "Enqueue Library Rescan (Jobs)" which creates a `library_scan` job processed by `services/job_workers/library_scan_worker.py` to update Bitrate/Resolution (and optionally Duration/Size) across all tracks.
- Database: `tracks` table includes `duration`, `size_bytes`, `bitrate`, `resolution`, `filetype` and play counters. There are SQLite migrations under `database/migrations/` and a migration manager. YouTube metadata is stored separately in `youtube_video_metadata` and is unrelated to local file media properties.
- Media probing utility (`utils/media_probe.py`) uses a Python-first approach and `ffprobe` fallback. It currently returns `(duration_seconds, bitrate_bps, resolution_string)` and does not expose frame rate or codec yet.

Implication: To add FPS and Codec we need to (1) extend DB schema, (2) enhance probing to extract FPS and video codec for video tracks, (3) plumb these through per-track rescan and library rescan flows, and (4) render them on the Track Detail page and update live when Rescan is clicked.

### Goals and scope

- Persist two new media properties on `tracks`:
  - `video_fps` (REAL) — frame rate in frames per second; supports fractional rates (e.g., 29.97).
  - `video_codec` (TEXT) — codec identifier (e.g., `h264`, `hevc`, `vp9`, `av1`).
- Extend rescan flows (single track + library job) to probe and update these fields alongside existing media properties.
- Extend Track Detail UI to display FPS and Codec. Ensure the inline Rescan updates these values without a full page reload.
- Backwards compatibility: no breaking changes to existing endpoints or flows; only additive fields and optional JSON response additions.

Out of scope (for this feature):
- Adding FPS/codec to Likes tooltips or to list views. Can be considered later if desired.
- YouTube formats section is unaffected; it already has its own rescan flow.

### Design decisions

- Data types: use `REAL` for FPS to preserve 23.976/29.97; use `TEXT` for codec (lowercased short name from ffprobe stream `codec_name` when available).
- Probing API shape: avoid breaking the existing `(duration, bitrate, resolution)` tuple contract. Add a new function `ffprobe_media_properties_ex(path)` returning a dict with keys: `duration`, `bitrate`, `resolution`, `video_fps`, `video_codec`. Internally reuse most logic from current function. Existing callers can stay as-is; updated callers (rescan endpoints/jobs) can switch to the extended function.
- DB updates: extend `database.update_track_media_properties` to optionally accept `video_fps` and `video_codec`. Keep it safe to ignore `None` values.
- UI: add two rows under File Properties on `templates/track.html` and extend the client-side Rescan handler to update them.
- Migration: create a new migration file `migration_009_add_video_fps_and_codec.py` to add columns (if missing) and backfill nothing (leave NULL until next rescan). Use the existing migration framework.

### Step-by-step implementation plan

1) Database migration [Required]
   - [ ] Create `database/migrations/migration_009_add_video_fps_and_codec.py` with a `Migration009` class.
   - [ ] In `up()`: `ALTER TABLE tracks ADD COLUMN video_fps REAL` if missing; `ALTER TABLE tracks ADD COLUMN video_codec TEXT` if missing. In `down()`: optionally drop or no-op (SQLite drop column is non-trivial; document as no-op).
   - [ ] Description: "Add video_fps (REAL) and video_codec (TEXT) to tracks table".
   - [ ] Run migration locally via migration manager to verify success.

2) Probing utility [Required]
   - [ ] Add `ffprobe_media_properties_ex(path: Path, timeout=10) -> dict` in `utils/media_probe.py`.
   - [ ] Populate keys: `duration`, `bitrate`, `resolution`, `video_fps`, `video_codec`.
   - [ ] Extraction rules:
       - Prefer ffprobe for video: parse the first `stream` with `codec_type == 'video'`.
       - `video_fps`: from `avg_frame_rate` or `r_frame_rate` (e.g., `30000/1001` -> 29.97). Round to 2 decimals for storage.
       - `video_codec`: from `codec_name` (lowercased), fallback to `codec_tag_string` if needed.
       - Keep existing bitrate logic (container or max stream bitrate), and resolution as `width x height`.
       - For audio-only files set `video_fps = None`, `video_codec = None`.
   - [ ] Keep existing `ffprobe_media_properties` unchanged for backwards compatibility.

3) Database helpers [Required]
   - [ ] Update `database.update_track_media_properties(...)` to accept `video_fps: Optional[float]` and `video_codec: Optional[str]` and include them in dynamic SET clause if values are not None.
   - [ ] Update `database.upsert_track(...)` to include the new fields where appropriate (optional now; useful for full rescans that upsert). If not touched now, ensure future scans can set them via the update function.

4) Single-track rescan API [Required]
   - [ ] In `controllers/api/tracks_api.py::api_rescan_track_media`, switch from the tuple-returning probe to the new extended dict-returning probe.
   - [ ] Update the `update_kwargs` to include `video_fps` and `video_codec` when present.
   - [ ] Extend the JSON response to include `video_fps` and `video_codec` so the UI can update inline without reload.
   - [ ] Logging: include fps/codec in the summary line.

5) Library rescan worker [Required]
   - [ ] In `services/job_workers/library_scan_worker.py`, switch probing to the extended function and update `video_fps` and `video_codec` along with existing fields.
   - [ ] Make sure job logs include counters; optionally add a small summary of how many tracks gained fps/codec.

6) Track Detail UI [Required]
   - [ ] `templates/track.html`: add two rows under File Properties:
       - Frame rate: render `{{ track.get('video_fps') or '-' }}` with formatting (e.g., `29.97 fps` if float)
       - Codec: render `{{ track.get('video_codec') or '-' }}`
   - [ ] Adjust the Rescan JS handler to:
       - Update `#fpsValue` and `#codecValue` nodes if present in the response.
       - Keep button behavior consistent (disable during in-flight; show toasts on success/errors).

7) Server render context [Validation]
   - [ ] Track page fetch uses `database.get_track_with_playlists(conn, video_id)` which selects `t.*`, so new columns will be present automatically. Validate no additional code changes are needed here.

8) Testing and validation [Required]
   - [ ] Unit-level manual validation on a local sample of files (MP4, MKV, WEBM; 24/29.97/30/60 fps; AVC/HEVC/VP9/AV1).
   - [ ] Audio-only files: ensure fps/codec render as `-` and are not set in DB (NULL).
   - [ ] Files missing on disk: API returns proper error; no DB changes.
   - [ ] Maintenance page job: enqueue and observe logs; verify random tracks get `video_fps`/`video_codec` populated post-run.
   - [ ] Regression: Bitrate/Resolution unaffected; Rescan button behavior unchanged.

9) Performance considerations
   - [ ] Reuse existing ffprobe JSON to avoid multiple calls.
   - [ ] Only compute FPS if we have a video stream; do not post-process for audio.
   - [ ] Keep timeouts conservative (same as current) and handle exceptions gracefully.

10) Documentation and rollout
   - [ ] This roadmap file will track status. Do not delete completed items; mark with [x] and add notes.
   - [ ] Add a brief note in `docs/README.md` if needed pointing to this feature doc.
   - [ ] Commit message should follow conventional commits format and be in English per repo policy.

### Manual testing checklist (UI walkthrough)

1) Track Detail page (video file)
   - Open `/track/<video_id>` for a known video file.
   - Verify File Properties shows: Size, Bitrate, Resolution, Frame rate (e.g., 29.97 fps), Codec (e.g., h264), Type, Relpath.
   - Click "Rescan". Observe button disables, shows feedback, and on success:
     - Bitrate updates if changed
     - Resolution updates if changed
     - Frame rate updates ("xx.xx fps")
     - Codec updates (short name, lowercase)
   - Refresh the page to confirm values persist.

2) Track Detail page (audio-only file)
   - Open a track with `.mp3`/`.m4a`.
   - Verify Frame rate and Codec display as `-`.
   - Click "Rescan"; still `-` for fps/codec.

3) Missing file case
   - Temporarily rename the underlying media file for a test track.
   - Click "Rescan"; expect toast error and HTTP 404 from API; no DB changes.

4) Maintenance page (library rescan)
   - Open `/maintenance`.
   - Click "Enqueue Library Rescan (Jobs)". Note the job id toast.
   - After job finishes, spot-check a few tracks that previously had NULL fps/codec and confirm they are now populated.

5) Edge cases
   - 23.976/29.97 fps rounding: show with two decimals.
   - Multi-stream containers: pick the primary video stream (lowest index) for fps/codec.
   - Corrupted or unsupported files: handled via error responses; no crashes.

### Acceptance criteria

- New DB columns exist: `tracks.video_fps` (REAL), `tracks.video_codec` (TEXT), created via migration.
- `utils.media_probe` exposes an extended probing function returning fps and codec for video files.
- Per-track rescan API updates fps/codec and returns them in response; UI updates inline.
- Library rescan job populates fps/codec across the library.
- UI remains responsive and user-friendly; no regressions to existing media properties.

Note: For smoother rollout on existing databases, schema auto-ensure was added in `database._ensure_schema` to automatically add `video_fps` and `video_codec` columns if missing. Dedicated migration remains the primary mechanism for versioning, but auto-ensure prevents failures on environments where migration is not yet executed.

### Risks and mitigations

- SQLite ALTER TABLE limitations: we only add columns (safe). Down migration will be a documented no-op to avoid destructive operations.
- ffprobe variability: some files may lack `avg_frame_rate`; fallback to `r_frame_rate` and robust parsing.
- Non-video tracks: ensure we never set misleading fps/codec; use NULL and render `-`.

### Implementation notes (SoC, SOLID, DRY, KISS)

- Keep probing logic isolated in `utils/media_probe.py`. Do not embed ffprobe parsing in controllers or workers.
- Use dynamic field updates in DB helpers to avoid overwriting existing values with NULL.
- UI changes minimal and localized to `templates/track.html` script and markup.

### Open questions

- Do we want to expose fps/codec in list APIs (e.g., Likes/Tracks lists) later? Not needed now.
- For codec naming, prefer ffprobe `codec_name` (e.g., `h264`). Any need to map to friendly names (e.g., "H.264")? For now use raw lowercase name.

---

### Status log (to be updated during implementation)

- [x] Migration created (migration_009_add_video_fps_and_codec) and ready to apply.
- [x] Probing extended with fps/codec (new function ffprobe_media_properties_ex).
- [x] DB update helpers support new fields (update_track_media_properties accepts video_fps, video_codec).
- [x] Single-track rescan API returns and persists fps/codec.
- [x] Library rescan worker updates fps/codec.
- [x] UI renders fps/codec and live-updates after rescan (Track Detail page).
- [ ] Manual tests passed for video and audio tracks.

### Audio media properties extension

- [x] Migration created for audio fields: `audio_codec` (TEXT), `audio_bitrate` (INTEGER bps), `audio_sample_rate` (INTEGER Hz).
- [x] Schema auto-ensure adds these columns if missing at startup.
- [x] Probing extended to capture audio codec/bitrate/sample rate in `ffprobe_media_properties_ex`.
- [x] Persist audio fields in DB on rescan and library job (single-track endpoint returns audio fields as well).
- [x] UI/Tooltips: render audio info concisely (e.g., `AAC · 128 kbps · 48 kHz`) where appropriate.

### Additional scope (follow-up tasks)

### Likes Player tooltips

- [x] Extend API and rendering to include compact Video row and Audio row.
  - [x] API now returns `bitrate`, `resolution`, `video_fps`, `video_codec`, and audio fields.
  - [x] Tooltips render `Video: codec · 1080p · 23.98fps · 1753 kbps` and `Audio: CODEC · kbps/VBR · kHz`.

### Optional/Follow-ups

- [ ] Expose numeric audio bitrate estimate in list APIs to render `~ N kbps (est)` in tooltips when available (сейчас для неизвестного показывается `VBR`).
- [ ] Finalize manual test checklist across diverse files; mark as passed.



# Set Manual Thumbnail from Current Video Frame – Roadmap and Implementation Log

Status: Completed
Owner: Frontend (Track Detail UI) + Backend (`tracks_api.py`)
Last Updated: 2025-08-23

## Initial Prompt (translated)

I want to be able to set the manual thumbnail from the current video frame. For example, I start inline playback and see a frame I want to make the thumbnail. I can either pause and click the “Set Manual” button or click it during playback, and this frame becomes the thumbnail.

## Analyse the Task and Project

We already have a centralized preview system (manual/youtube/media) with priority and storage in THUMBNAILS_DIR (fallback to static/previews). We also have an inline player on the track page and a Promote-to-Manual button that copies an existing preview to manual.

We need to add a way to set manual directly from an arbitrary timestamp in the underlying media file. The most reliable approach is server-side frame extraction using ffmpeg at the requested timestamp, ensuring consistent PNG output and avoiding client-side CORS/tainted-canvas pitfalls. The UI should reuse the existing “Set as Manual” button when the player is active, using the currentTime of the <video> element.

## Goals
- Allow setting `<video_id>_manual.png` from the current frame time of the inline player. [New]
- Maintain storage and atomic replace rules (THUMBNAILS_DIR → fallback to static/previews). [Consistent]
- Keep the existing Promote-to-Manual (source → manual) behavior when no player is active. [No regression]
- Preserve UX simplicity: one button works both paused and during playback. [KISS]

## Design Overview

Approach: server-side extraction via ffmpeg with timestamp (in seconds), triggered by a new API.

- API: `POST /api/track/<video_id>/set_manual_from_timestamp`
  - Request JSON: `{ "time": number, "width": number=1280, "overwrite": true }`
  - Behavior:
    - Validate `time` range against media duration if available; clamp or 400 on invalid.
    - Ensure target directory exists, write to temp file in the same directory, then `os.replace` to `<video_id>_manual.png`.
    - Use PNG for consistency.
  - Response: `{ status: "ok", path, width, height }` or `{ status: "error", error }`.
  - Security: time bounds, ffmpeg timeout, path sanitation, log inputs.

- ffmpeg command (accurate seek):
  - `ffmpeg -nostdin -y -i "<file>" -ss <time> -frames:v 1 -vf "scale='min(1280,iw)':-2" "<tmp>.png"`
  - Rationale: Post-input `-ss` for precision; scale to max width (configurable), even height.

- UI integration (`preview-gallery.js`):
  - If player active → get `videoEl.currentTime`, call API, then refresh `available_previews`, switch to `manual`, force-refresh image with cache-buster.
  - If player inactive → fall back to existing promote flow (`/promote_preview` for current source).
  - Button label remains “Set as Manual”; tooltip clarifies behavior when player is active.

- Storage/fallback:
  - Same as elsewhere: prefer THUMBNAILS_DIR; fallback to `static/previews` when unwritable.
  - Temp files created in the target directory to avoid cross-drive `WinError 17`.

## Detailed Plan (Step-by-step)

1) Backend API in `controllers/api/tracks_api.py` [Done]
   - Add handler `api_set_manual_from_timestamp(video_id)`:
     - Parse and validate JSON body (time, width, overwrite default=true).
     - Resolve media path for this video (track.relpath or candidate same_id_files), ensure file exists.
     - Build target path `<video_id>_manual.png` using THUMBNAILS_DIR or fallback.
     - Run ffmpeg extraction with timeout and `-nostdin -y` flags.
     - On success, atomic replace target; return JSON with final path and dimensions.
     - On failure, return structured error with context.

2) Frontend changes in `static/js/modules/preview-gallery.js` [Done]
   - In Promote-to-Manual click handler:
     - If player is active and mediaUrl exists → call new API with `videoEl.currentTime`.
     - Else → preserve existing behavior (promote current preview source).
   - After success → refresh previews via `/preview_info`, set current source to `manual`, update dots and caption.
   - Show toasts for success/error, add minimal button disabled states.

3) Validation & Edge Cases [Planned]
   - If media not found or HEAD fails → show toast and keep state.
   - If `time` out of range → clamp or return 400 with a helpful message.
   - Handle ffmpeg absence or failure gracefully with clear error text.

4) Configuration [Planned]
   - Reuse existing `.env` and shared config (THUMBNAILS_DIR, etc.).
   - Optional: expose default width via env (e.g., `FRAME_EXTRACT_WIDTH=1280`).

5) Manual Testing Checklist [Completed]
   - [x] While playing: press “Set as Manual” → manual preview updates to the current frame.
   - [x] While paused: press “Set as Manual” → picks paused frame.
   - [x] With player inactive: “Set as Manual” promotes current preview source (legacy behavior).
   - [x] Remount the page; verify manual preview persists.
   - [x] Remove write permissions to THUMBNAILS_DIR (simulate) → fallback to `static/previews` works.
   - [x] Non-ASCII filenames and spaces in relpath → extraction succeeds.

6) Risks & Mitigations [Planned]
   - Precision vs speed of seek → use post-input `-ss` for precision.
   - Cross-drive temp moves on Windows → create temp next to target and `os.replace`.
   - Large/long files → set reasonable ffmpeg timeout and surface errors.

7) Definition of Done [Completed]
   - [x] New API implemented with validation and robust file handling.
   - [x] UI integrates timestamp-based capture only when player is active.
   - [x] Existing promote flow unchanged for non-player state.
   - [x] Docs updated; tests in checklist pass.

---

## Changelog (to be updated during implementation)
- [x] Implement API: set manual from timestamp
- [x] Integrate UI trigger (active player → timestamp; otherwise → legacy promote)
- [ ] Add env knob for default width (optional)
- [x] Manual tests pass across cases
- [x] Documentation polish

### Finalization notes
- Feature completed and verified on page.



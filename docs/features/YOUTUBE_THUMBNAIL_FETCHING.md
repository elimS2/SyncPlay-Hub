# YouTube Thumbnail Fetching – Roadmap and Implementation Log

Status: Planned
Owner: Backend + Frontend (Track Detail UI)
Last Updated: <set on first commit>

## Initial Prompt (translated)

The user asked to add the ability to obtain a thumbnail image from YouTube. Before writing code, analyze the task and the project deeply and decide how to implement it best.

Then, create a detailed, step-by-step roadmap in a dedicated document (this file) under docs/features. Use it as a living TODO checklist: document what is done, how it was done, encountered problems, and solutions. Do not delete old items; update their status and add comments. If new subtasks appear, add them here. Include steps for manual testing in the UI.

Follow SOLID, DRY, KISS, Separation of Concerns, Single Level of Abstraction, and Clean Code practices. Follow UI/UX principles: User-Friendly, Intuitive, Consistent, Accessible, Feedback, Simple, Modern, High Performance, Responsive. Use best practices.

## Goals

- Allow fetching a thumbnail directly from YouTube (i.ytimg.com) for a given `video_id`.
- Integrate with the existing centralized preview system and storage.
- Keep network fetch decoupled from page rendering; use an explicit action (button or API flag).
- Maintain a deterministic priority across preview sources.

## Current State (Context Summary)

- Centralized preview pipeline already exists, with priority: `manual → from_youtube → from_media_file`.
- Storage location is configurable via `.env` `THUMBNAILS_DIR`; fallback is `static/previews/`.
- Existing API endpoints:
  - `GET /api/track/<id>/preview.png` – serves/creates previews based on priority, supports `refresh=1`.
  - `GET /api/track/<id>/preview_info` – returns diagnostic info about the effective preview file and source.
- UI Track Detail uses only the API endpoint (`preview.png`) and shows a path tooltip and source label.

## High-Level Design

### Sources and Order
- We keep the default order: `manual → from_youtube → from_media_file`.
- We may add `.env` `PREVIEW_PRIORITY` later to override order (non-blocking).

### Fetch Strategy (YouTube CDN)
- Try the following URLs with short timeouts and fallbacks (stop on first success):
  1) `https://i.ytimg.com/vi/<VIDEO_ID>/maxresdefault.jpg`
  2) `https://i.ytimg.com/vi/<VIDEO_ID>/sddefault.jpg`
  3) `https://i.ytimg.com/vi/<VIDEO_ID>/hqdefault.jpg`
  4) `https://i.ytimg.com/vi/<VIDEO_ID>/mqdefault.jpg`
  5) `https://i.ytimg.com/vi/<VIDEO_ID>/default.jpg`
- Validate content-type as an image and reject tiny “placeholder” sizes if needed (e.g., width < 120).
- Save normalized to `<video_id>_from_youtube.png` in `THUMBNAILS_DIR` or `static/previews/`.
- Use atomic write: temp file → `os.replace`.

## Detailed Design Notes (English translation of the proposal)

### Thumbnail Source (YouTube CDN)
- Use standard YouTube image URLs:
  - `https://i.ytimg.com/vi/<VIDEO_ID>/maxresdefault.jpg` (preferred)
  - Fallbacks: `sddefault.jpg` → `hqdefault.jpg` → `mqdefault.jpg` → `default.jpg`
- Check availability in order (HEAD/GET with ~3–5s timeout). If 404, move to the next.

### Where and How to Store
- Save into `THUMBNAILS_DIR` (if set) otherwise `static/previews/` with the name `<video_id>_from_youtube.png` (consistent with current scheme and format).
- Convert to PNG for uniformity: either via ffmpeg (as already used) or via PIL if acceptable.
- On write: ensure directory exists (`mkdir -p`), use timeouts, and perform atomic replace (write to a temp file → `os.replace`).

### API Endpoint
- New endpoint, for example:
  - `POST /api/track/<video_id>/fetch_youtube_thumbnail`
- Options:
  - `quality` = `maxres|sd|hq|auto` (where `auto` means try in the order above)
  - `force=true` to overwrite existing files
- Returns JSON: `status`, `source_url`, `saved_path`, `width/height` (if detected), and `error` on failure.
- Security: strictly allow only `i.ytimg.com` (to avoid SSRF), use timeouts, and limit response size.

### Integration with Current Preview Logic
- Keep the source priority either as-is or configurable:
  - Current: `manual → from_youtube → from_media_file`.
  - Optionally add an `.env` switch: `PREVIEW_PRIORITY=manual,youtube,media`.
- In `preview.png`:
  - By default, do NOT fetch from the network (to avoid blocking page render).
  - If `<video_id>_from_youtube.png` is missing, do not auto-fetch; optionally allow on-the-fly fetch via `?fetch_youtube=1` (or through a dedicated UI button).

### UI
- In the Preview card add a button:
  - “Fetch from YouTube” (or “Update from YouTube” if the file already exists).
  - On click, `POST` to `fetch_youtube_thumbnail`; on success, update the image (append `?t=<timestamp>` to bypass cache).
  - Keep the tooltip “Thumbnail path: …” and set the label to “From YouTube thumbnail”.

### Settings / Config
- `.env`:
  - `THUMBNAILS_DIR` — already exists
  - `YOUTUBE_THUMB_TIMEOUT=5`
  - `YOUTUBE_THUMB_ORDER=maxres,sd,hq,mq,default` (optional)
  - `PREVIEW_PRIORITY=manual,youtube,media` (optional)
- Log the final chosen URL and size.

### Reliability and Edge Cases
- If `maxres` does not exist (frequent 404) — correctly fall back to `sd/hq/mq/default`.
- If the image is a tiny placeholder (e.g., 120×90) — treat as low quality and continue trying or fall back to video frame.
- Handle network errors without breaking the page; UI shows a “failed to fetch” toast.
- Fallback persistence [Done]: if writing to `THUMBNAILS_DIR` fails, the image is saved to `static/previews/` and served from there.

### Debugging
- Extend `GET /api/track/<id>/preview_info` with `youtube_url_tried`, `selected_youtube_url`, and `reason`.
- Add `?refresh=1` to `fetch_youtube_thumbnail` to re-download and overwrite PNG.

### Rationale
- Decouple online fetching (button/explicit flag) from page rendering (no synchronous network during render).
- Single PNG format and centralized storage simplify cache and consistency.
- Configurable source order aligns with our existing priority system.

### API Endpoints
- `POST /api/track/<video_id>/fetch_youtube_thumbnail`
  - Body (JSON, optional):
    - `quality`: `maxres|sd|hq|mq|default|auto` (default: `auto` tries in order above)
    - `force`: `true|false` (default: `false`) – overwrite existing `_from_youtube.png`
  - Response: `{ status, video_id, source_url, saved_path, width, height, message? }`
  - Security: allow only `i.ytimg.com`; timeout ~5s; cap content size.
  - Failure returns `{ status: 'error', error }`.

### UI Changes
- In `templates/track.html` Preview card add a small toolbar:
  - Button “Fetch from YouTube” (disabled while loading).
  - On success, reload the `<img>` `src` with a cache-buster `?t=<timestamp>` and update the label to “From YouTube thumbnail”.
  - Show toast notifications for success/error.

### Config
- Add optional `.env` keys:
  - `YOUTUBE_THUMB_TIMEOUT=5`
  - `YOUTUBE_THUMB_ORDER=maxres,sd,hq,mq,default` (optional)
  - `PREVIEW_PRIORITY=manual,youtube,media` (optional later)

### Observability and Debugging
- Extend `preview_info` with `youtube_url_tried` (array) and `selected_youtube_url` when applicable.
- Log fetch attempts and outcomes.

## Step-by-Step Plan (Roadmap)

1) Backend: utility for YouTube thumbnail fetch [Done]
   - Implement a function `fetch_youtube_thumbnail(video_id, quality='auto')`:
     - Build URL list based on `quality`.
     - Fetch with timeout; validate response and basic dimensions.
     - Return bytes or a temp file path and the final `source_url`.

2) Backend: writer/normalizer to PNG [Done]
   - Reuse existing ffmpeg normalization to PNG into destination dir (`THUMBNAILS_DIR` or fallback).
   - Name: `<video_id>_from_youtube.png`, atomic replace.

3) API: POST /api/track/<id>/fetch_youtube_thumbnail [Done]
   - Validate `video_id` and body; call utility; write PNG; return JSON with `saved_path` and `source_url`.
   - Support `force=true` to overwrite.
   - Add error handling and logging.

4) Integrate with preview resolver [Done]
   - No automatic network on page load; preview.png continues to use existing priority.
   - After a successful fetch, preview.png immediately serves the new file.

5) UI: Add button and client logic [Done]
   - Add a small “Fetch from YouTube” button in the Preview card.
   - On click: POST to API, then refresh `<img>` via `?t=<Date.now()>` and update label.
   - Use existing toast system for feedback.

6) Diagnostics [Done]
   - Extended `preview_info` with `youtube_url_tried` and `selected_youtube_url` when fetch created the image.

7) Config wiring [Done]
   - `.env` keys supported and wired: `YOUTUBE_THUMB_TIMEOUT`, `YOUTUBE_THUMB_ORDER`, `PREVIEW_PRIORITY`.
   - Values are read in `app.py` and passed to API init; used by fetch logic and preview selection.
   - `PREVIEW_PRIORITY` controls serving order (e.g., `manual,youtube,media` or `manual,media,youtube`).

8) Manual Testing Checklist [Updated]
   - A) With THUMBNAILS_DIR set:
     - Open a track with no previews; click “Fetch from YouTube” → file `<id>_from_youtube.png` appears in THUMBNAILS_DIR; UI shows it.
     - Click again with `force` (option in UI or query) → file is replaced.
     - Verify `preview_info` displays `source: from_youtube` and correct `path`.
   - B) With THUMBNAILS_DIR unset (fallback):
     - Repeat A; verify files land in `static/previews/`.
   - C) Offline/404 case:
     - Simulate by blocking `i.ytimg.com` or use a bogus ID; API returns error; UI shows toast; no file written.
   - D) Priority behavior:
     - Place a `<id>_manual.png` and verify it overrides YouTube.
     - Remove manual; YouTube should take precedence; if none, falls back to media frame.

9) Risks and Mitigations [Updated]
   - Network dependency: Keep it explicit (button/flag), timeouts, retries minimal.
   - Incorrect thumbnail matches: We rely on `video_id` and YouTube CDN; avoid scraping HTML.
   - Large responses or content-type spoofing: validate `Content-Type` and size limits.
   - File permissions: fall back to `static/previews/` if write to `THUMBNAILS_DIR` fails (future improvement toggle).

10) Definition of Done [Updated]
   - API endpoint implemented with tests (manual) and logs.
   - UI button works and updates preview immediately.
   - Docs updated with `.env` options and usage.
   - `preview_info` shows additional YouTube fields.

## Open Questions

- Should we persist chosen YouTube quality (maxres/sd/hq/etc.) in DB for auditing?
- Do we want a daily/periodic refresh job for out-of-date thumbnails? (Probably not now.)

## Planned Enhancement: Thumbnail Gallery / Slideshow

Purpose: Allow users to view all available thumbnails for a track (e.g., YouTube thumbnail and first frame from media) and switch between them like in an album or slideshow.

### Requirements
- In the Preview card on the Track Detail page, add a mini-gallery UI:
  - Sources to include: `manual`, `from_youtube`, `from_media_file` (only if a file exists for the source).
  - Show navigation controls (Prev/Next) and small clickable dots or thumbnails to jump to a specific source.
  - Keep tooltip updated with the actual path for the currently displayed image.
  - Do NOT change the saved default priority or selection automatically; this is a viewer, not a setter.
- Optional: Add a “Set as manual” action to copy the currently viewed image as `<video_id>_manual.png` (explicit confirmation required). [Done]

### API / Data
- Extend `preview_info` with a list of available sources and their absolute paths:
  - `available_previews: [{ source: 'manual'|'from_youtube'|'from_media_file', path: string }]`
  - Keep existing fields.

- New endpoint: `POST /api/track/<video_id>/promote_preview` [Done]
  - Body: `{ src: 'youtube'|'media'|'manual', overwrite?: boolean }`
  - Copies the selected source file to `<video_id>_manual.png` (atomic replace).

### UI/UX
- Add a compact toolbar under the image with:
  - `◀ Prev` / `Next ▶` buttons
  - Clickable indicators (dots) to select a source directly [Done]
  - A label reflecting the source (“Manual preview image”, “From YouTube thumbnail”, “Generated on the fly from media file”)
  - Update `<img>` `src` with cache buster when switching
  - Button “Set as Manual” that promotes the current image [Done]
  - Decision: mini-thumbnails are NOT required and will not be implemented (dots are sufficient)

### Manual Testing
- With both YouTube and media frame present:
  - Verify navigation switches image and updates tooltip/label
  - Verify missing sources (e.g., no manual) are not displayed
- With only one source present:
  - Verify controls are disabled or hidden appropriately
 - Press “Set as Manual” and confirm `<video_id>_manual.png` is created/updated, UI still navigates sources

### Future Option (separate task)
- Provide an action to “Promote current image to Manual” which saves the currently displayed file as `<video_id>_manual.png`.

## Changelog (to be updated during implementation)

- [x] Implement fetch utility (YouTube CDN with fallbacks)
- [x] Implement normalize/write to PNG (with atomic replace)
- [x] Add API endpoint: `POST /api/track/<id>/fetch_youtube_thumbnail`
- [x] Extend diagnostics (`preview_info`: available sources, paths, YouTube URLs)
- [x] Add UI button and client code (fetch + cache-buster)
- [x] Gallery/slideshow with dots and Prev/Next, active highlighting, centered layout
- [x] Promote to Manual endpoint and UI; fixed Windows cross-disk move via same-dir temp
- [x] Fallback persistence to `static/previews/` when primary dir fails
- [x] Dual-directory resolution and refresh clean-up
- [x] Manual test pass (A–D) and UX refinements
- [x] Documentation polish
 - [x] JS refactor: gallery moved to `static/js/modules/preview-gallery.js` and imported in `templates/track.html`



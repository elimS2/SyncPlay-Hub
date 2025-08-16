## Future Plans

This document captures concise follow-ups and optional enhancements. Keep it short and link back to feature roadmaps for details.

### Backend
- Add lightweight audit events (optional)
  - Record maintenance actions (per-track rescan, library rescan) to `play_history` or a dedicated audit table for traceability.

- Expand batch rescan scope (optional)
  - Include codec, channels, sample rate, and other technical metadata in the rescan results (store via new columns only if justified by use-cases).

- Library rescan robustness
  - Improve partial-failure handling: continue on errors, aggregate error summary, expose counters in job logs (already partially implemented, extend as needed).
  - Add configurable rate limiting/throttling for very large libraries (sleep between batches).

### Frontend (Track page and Maintenance/Jobs)
- Track page
  - Optional controls to also refresh `duration` and `size_bytes` from UI (currently API supports flags; UI defaults to off).

- Jobs page (/jobs)
  - Auto-refresh logs in the job details modal every 5–10 seconds while the modal is open.
  - Add one-click “Open Logs” action in table rows to open the modal and load logs immediately.

### Observability & Logging
- Structured progress reporting
  - Emit periodic progress (processed/total, updated, missing) to a dedicated `progress.log` for long-running jobs with stable formatting.
  - Surface summarized metrics (updated, skipped, missing) in job completion message.

### Testing & QA
- Manual testing
  - Verify all “Edge cases” from the roadmap: audio-only files (resolution `-`), missing files, corrupted/unsupported files, very large files, `ffprobe` N/A handling (fallbacks).
  - Confirm end-to-end library rescan updates are visible in `/track/<video_id>` and `/tracks`.

- Automated checks (optional)
  - Add smoke tests for API `/api/track/<video_id>/rescan_media` (happy path + missing file).
  - Add a small integration test that invokes Library Scan worker against a tiny fixture set.

### Performance & UX polish
- Keep ffprobe-first for video to avoid noisy warnings; moviepy only as fallback (done). Monitor logs and adjust if needed.
- Consider per-batch UI progress (e.g., polling a `/api/jobs/<id>` progress endpoint) for very long scans.

### Documentation & Housekeeping
- Roadmap maintenance
  - Periodically reconcile this file with `docs/features/MEDIA_PROPERTIES_RESCAN.md` to mark completed items and prune stale ones.
  - Keep this document short; link back to the roadmap for details.

References
 - Media properties rescan: `docs/features/MEDIA_PROPERTIES_RESCAN.md`
 - Intermittent 403/SABR mitigation: `docs/features/INTERMITTENT_403_SABR_ROADMAP.md`

---

## Intermittent 403/SABR Mitigation – Next Steps (Concise)

For full context and rationale, see `docs/features/INTERMITTENT_403_SABR_ROADMAP.md`. Below are compact future items only.

### Backend
- Cookie health concurrency safety (file locking)
  - Add cross-process file lock/mutex around `_health.json` updates (current writes are atomic, but not locked). Keep it simple on Windows (msvcrt) and POSIX (fcntl), or use a small lock file.

- Proxy rotation parity for playlists
  - `download_playlist.py`: add optional rotation over `PROXY_URLS` similar to single-video ladder.

- Failure-path cleanup
  - On download failure, optionally clean up stale `.part`/`.tmp` files older than N minutes in the target folder.

- Job queue backoff configurability via env
  - Teach `services/job_types.RetryConfig` to read `.env` (initial_delay, backoff_multiplier, max_delay, jitter) for system-wide tuning.

- Effective config logging
  - On worker init, log effective non-sensitive settings (retry ladder enabled, attempts, backoff window, client alignment flag, proxy count, cookies dir).

### Frontend / Admin
- Cookies health UX polish
  - Format timestamps as human-readable datetime; add quick filters (unseen / clean / failed recently).
  - Optional: button to deprioritize a specific cookie for X minutes.

### Observability
- Minimal counters
  - Emit a small summary line per job completion: attempts used, client path taken, cookie(s) used, final result.

### Documentation
- Keep `INTERMITTENT_403_SABR_ROADMAP.md` in sync
  - Mark the above items as “Future” in the checklist; review quarterly.

---

## Tracks Table Filters – Future Work (Concise)

For full scope and decisions, see `docs/features/TRACKS_TABLE_COLUMN_FILTERS.md`.

### UX & Accessibility
- Persist collapsed/expanded state of Filters/Columns panels in localStorage.
- Add “filter chips” (active filters summary) with one-click removal.
- Improve empty-state when filters yield no results (show quick “Reset filters” action).
- Keyboard navigation and ARIA for filters (fieldset/legend, aria-expanded, focus outlines).
- Per-page selector (e.g., 100/200/500) and server-side sort controls (column + order) via query params.

### Backend & Performance
- Add indices if needed after measurement: `tracks(resolution)`, `tracks(filetype)`, `tracks(play_likes)`, optionally `tracks(duration)`, `tracks(bitrate)`.
- Consider lightweight caching for facet counters (short TTL) to reduce repeated aggregations.
- Harden query param parsing (limits on number of selections, sane defaults, clamp ranges).
- Optional: expose `/api/tracks/facets` for dynamic (AJAX) facets in Phase 2.

### Testing & Observability
- Finalize manual checklist runs and mark results in the roadmap.
- Add unit/integration tests for SQL filter builder and pagination.
- Log timing metrics for page and facet-count queries (debug-level) to help future tuning.



## Future Plans (Media Properties Rescan and Job Queue UX)

This document captures follow-up items and optional enhancements derived from the implementation plan in `docs/features/MEDIA_PROPERTIES_RESCAN.md`. It is intentionally concise; for full context and technical background, see the roadmap document.

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
- Roadmap and implementation details: `docs/features/MEDIA_PROPERTIES_RESCAN.md`



Intermittent YouTube 403/SABR Failures: Diagnosis and Remediation Roadmap

Status: Draft
Owner: Job Queue / Download subsystem
Scope: `services/job_workers/playlist_download_worker.py`, `utils/cookies_manager.py`, job retry/backoff logic, logging/observability

1) Problem Statement and Observations

- Symptom: Single-video downloads sometimes fail with HTTP 403 and SABR warnings, then succeed on a later attempt with the same video URL.
- Representative stderr:
  - "WARNING: [youtube]: Some web client https formats have been skipped as they are missing a url. YouTube is forcing SABR streaming for this client."
  - "ERROR: unable to download video data: HTTP Error 403: Forbidden"
- Notable patterns from logs:
  - yt-dlp often prints "Downloading tv client config" and "tv player API JSON", indicating a TV client profile.
  - On failures, yt-dlp ends up selecting a single progressive format like `18` and then 403s.
  - On success, we frequently see `137+251` being selected and download completes.
  - Different cookies files are used per attempt (rotating). Some cookies work; others trigger SABR/403; success is intermittent.

Hypothesis: Intermittent 403s are caused by a combination of YouTube anti-abuse heuristics (SABR), client profile selection, cookie quality/validity, and possibly IP/rate limiting. Choosing a different YouTube client via `--extractor-args` or rotating to a healthier cookies file often avoids SABR-gated streams and yields stable direct URLs for formats like `137+251`.

2) Goals and Acceptance Criteria

- Stabilize single-video downloads so that the same URL consistently succeeds without manual retries.
- Implement deterministic, observable retry ladder that changes yt-dlp client/cookies/flags on detection of SABR/403.
- Reduce failure rate due to SABR/403 by ≥90% while keeping performance and file naming unchanged.
- Preserve current behaviors: archive usage, metadata/thumbnails embedding, DB scan, and cleanup.

3) Root Causes (Likely)

- SABR gating for the default client chosen by yt-dlp under some conditions (esp. TV client), returning formats without direct URLs.
- Cookie files with low trust/expired sessions triggering additional gating.
- IP/rate-limiting bursts causing transient 403.
- UA-client mismatch: desktop UA while yt-dlp negotiates a TV client can increase suspicion.

4) Technical Strategy (High-Level)

- Detect SABR/403/missing-URL conditions and rerun yt-dlp with alternate extractor client(s) and/or a different cookies file.
- Make the retry ladder explicit, with short backoff and jitter. Keep attempts bounded (e.g., 3–4 tries).
- Prefer stable formats `137+251` or `best[height<=1080]` when available; avoid progressive fallback unless unavoidable.
- Track cookie health and prefer recently successful cookie files.
- Optional: allow proxy fallback if configured.

5) Implementation Plan (Step-by-Step)

5.1 Add robust retry ladder to single video downloads

- Location: `services/job_workers/playlist_download_worker.py::_download_single_video`
- Add a controlled loop of attempts (e.g., up to 4):
  1) Attempt A (current behavior):
     - `-f 137+251/best[height<=1080]/best`
     - Desktop UA (current) and current cookie selection
  2) If stderr contains any of: "SABR", "missing a url", "403": retry with extractor args:
     - `--extractor-args "youtube:player_client=android"`
     - Keep format preference `137+251/...`
  3) If still failing with same markers: rotate cookie file (new random healthy cookie), add small jitter (e.g., 2–5s sleep), and retry with:
     - `--extractor-args "youtube:player_client=web"`
  4) Final fallback:
     - Try `--extractor-args "youtube:player_client=ios"`
     - Optionally add `--force-ipv4` and `--http-chunk-size 10M`
- For each attempt, log clearly: chosen `player_client`, cookie file used, and detected failure reason.

Notes:
- We deliberately avoid the TV client because logs indicate SABR more often with it.
- We keep attempts small to avoid long job durations.

5.1.1 Correct flags hygiene

- Ensure we never pass unsupported flags. For example, do not append `--no-download-archive`; instead, simply omit `--download-archive` when ignoring archive is desired.
- Keep path quoting safe on Windows (already handled by subprocess arguments, not manual shell quoting).

5.2 Cookie rotation with health scoring

- Location: `utils/cookies_manager.py`
- Extend `get_random_cookie_file()` to become `get_cookie_file(prefer_healthy=True)` with in-memory and on-disk small state (e.g., JSON in `D:/music/Youtube/Cookies/_health.json`):
  - Track last N outcomes per cookie: success/failure timestamps.
  - Prefer cookies with recent successes; temporarily deprioritize cookies that caused SABR/403 in the last X minutes.
  - Provide a simple exponentially-decaying score.
- Backward compatible: if the health state file is missing, behave like current random selection.

5.3 Optional proxy rotation (config-driven)

- Location: `.env` and `playlist_download_worker`.
- Support `PROXY_URLS` list (comma-separated). On repeated 403s and if proxies are provided, try next proxy in the list for the next attempt.
- Preserve current single-proxy behavior when only `PROXY_URL` is set.

5.4 Improve logging & observability

- Augment logs for each attempt with a compact line:
  - `attempt=2 client=android cookie=cookies10.txt proxy=none format="137+251" result=403 sabr=true`
- Persist final attempt summaries into job logs (already captured by job system).

5.5 Tuning yt-dlp flags (conservative)

- Keep: `--extractor-retries 3`, `--fragment-retries 10`, `--restrict-filenames`, metadata/thumbnails embedding.
- Add on specific fallback attempts only:
  - `--force-ipv4` (can help on certain ISPs)
  - `--http-chunk-size 10M` (mitigates some 403/timeout edge cases)
- Do NOT change default UA globally; client override via extractor args is preferred.

5.6 Backoff and jitter

- Between attempts, sleep random 1–5s to reduce burstiness that can trigger rate limits.
- Keep overall single-video timeout at 1 hour; per-attempt timeout unchanged.

5.7 Safeguards

- Stop retries on non-network errors unrelated to SABR/403 (e.g., 404, private video).
- Respect `download_archive` semantics across attempts.

5.8 Playlist downloads parity

- Location: `services/job_workers/playlist_download_worker.py::_download_playlist` and `download_playlist.py`.
- Propagate extractor args and cookie selection into playlist downloads:
  - Add optional passthrough of `--extractor-args` and selected cookie file to `download_playlist.py`.
  - If `download_playlist.py` invokes yt-dlp per playlist only, add flags globally for the run; if it invokes yt-dlp per entry, consider per-entry retry ladder (lightweight: first run with preferred client, no per-entry retry storm).
  - At minimum, apply the same client preference (`player_client=android`) and format preference (`137+251/best[height<=1080]/best`).
- Keep archive behavior unchanged for playlists.

5.9 Job Queue coordination

- Avoid exponential retry storms by aligning internal attempt ladder with job-level retries:
  - Classify errors: if SABR/403 detected after internal ladder exhausted → return a retryable failure (let the job queue delay and retry once or twice with a larger backoff).
  - For permanent errors (404, private, removed) → mark as non-retryable to stop the job.
- Make retry/backoff caps configurable via `.env` (e.g., `YTDLP_MAX_ATTEMPTS`, `YTDLP_BACKOFF_MIN_MS`, `YTDLP_BACKOFF_MAX_MS`).

5.10 yt-dlp version management

- Enforce a minimum yt-dlp version known to contain recent YouTube extractor fixes.
- On worker start (or first use), log `yt-dlp --version` and warn if outdated; provide an upgrade command in logs/docs.
- Optionally feature-flag a self-check that stops the ladder if version is too old.

5.11 User-Agent alignment (optional)

- For attempts where we switch `player_client`, optionally align UA:
  - android: a modern Android Chrome UA
  - web: a desktop Chrome UA (current default)
  - ios: a modern iOS Safari UA
- Keep this behind a flag `YTDLP_ALIGN_UA_WITH_CLIENT=1` (default off) to minimize change risk.

6) Data Model / Compatibility

- No DB schema changes.
- Add a small JSON file for cookie health in the Cookies folder (if writeable). If not writeable, silently skip health tracking and continue with random selection.
- Concurrency: write cookie health file atomically (write to temp, then `os.replace`) to avoid partial writes; serialize updates with a simple file lock or per-process mutex to prevent corruption on Windows.

7) Rollout Plan

- Phase 1: Implement retry ladder and enhanced logging; ship behind a feature flag env `YTDLP_RETRY_LADDER=1` (default on).
- Phase 2: Add cookie health scoring (can be enabled with `COOKIE_HEALTH=1`).
- Phase 3: Optional proxy rotation if configured via `.env`.
- Provide sample `.env` entries and sensible defaults; log effective configuration on worker startup.

8) Manual Test Plan (UI Click-Through)

- From the web UI:
  1) Open `Jobs` page.
  2) Create several `single_video_download` jobs with known URLs that intermittently failed.
  3) Observe job logs:
     - On a first failure, confirm automatic retry attempts with different `player_client` values and possibly different cookie files.
     - Confirm final success for at least 90% of previously flaky URLs.
  4) Verify post-download flow remains intact:
     - DB scan runs and reports new track(s).
     - Temporary files cleaned up in the target folder.
  5) Repeat with `download_archive=True` to ensure no duplicates.
  6) If proxies are configured, repeat test with/without proxy to compare.

8.1 CLI/Test harness steps

- Run a controlled single-video download from shell to verify attempts and flags mapping:
  - Attempt A (web): `yt-dlp -f 137+251/best[height<=1080]/best --cookies <file> <url>`
  - Attempt B (android): `yt-dlp --extractor-args "youtube:player_client=android" -f 137+251/best[height<=1080]/best --cookies <file> <url>`
  - Attempt C (ios): `yt-dlp --extractor-args "youtube:player_client=ios" -f 137+251/best[height<=1080]/best --cookies <file> <url>`
- Validate stderr markers (SABR/403) and ensure next attempt choice matches the ladder.

9) Risks and Mitigations

- Risk: Some client profiles may be rate-limited in certain regions.
  - Mitigation: Keep the retry ladder diverse and bounded; add backoff and jitter.
- Risk: Cookie health file write failures on restricted environments.
  - Mitigation: Soft-fail to current random behavior.
- Risk: Over-logging.
  - Mitigation: Keep one concise line per attempt; full stderr captured already.

10) Maintenance and Telemetry

- Track failure reasons (SABR/403/other) in logs to evaluate improvements over time.
- Consider a small admin page section to list cookie files and their recent success rates (future enhancement).

11) Configuration (.env) quick reference

```
# Retry ladder
YTDLP_RETRY_LADDER=1
YTDLP_MAX_ATTEMPTS=4
YTDLP_BACKOFF_MIN_MS=1000
YTDLP_BACKOFF_MAX_MS=5000
YTDLP_ALIGN_UA_WITH_CLIENT=0

# Cookies
YOUTUBE_COOKIES_DIR=D:/music/Youtube/Cookies
COOKIE_HEALTH=1
COOKIE_HEALTH_PATH=D:/music/Youtube/Cookies/_health.json

# Proxy (optional)
PROXY_URL=
PROXY_URLS=
```

12) Initial Prompt (English Translation)

"Analyze why some tracks are downloaded successfully while others fail. Later, if we try to download the same track again, it may succeed. So the problem is not the track—one and the same track may succeed or fail depending on the attempt.

— Analyze the Task and project —

Perform an in-depth analysis of our task and our project, and decide how best to implement this.

— Create Roadmap —

Create a detailed, comprehensive step-by-step action plan for implementing this task in a separate file-document. We have a folder docs/features for this. If such a folder does not exist, create it. Capture in the document as many already discovered and tried problems, nuances, and solutions as possible, if any. As you progress with the implementation of this task, you will use this file as a to-do checklist; you will update this file and document what has been done, how it was done, what problems arose, and what solutions were chosen. For history, do not delete points; you may only update their status and comment on them. If during implementation it becomes clear that something should be added to the tasks, add it to this document. This will help us preserve the context window, remember what we have already done, and not forget what we planned to do. Remember that only the English language is allowed in the code and comments, and in project copy. When you write the plan, stop and ask me if I agree to start implementing it or if something needs to be adjusted.

Include this prompt that I wrote in the plan itself, but translate it into English. You can call it something like 'Initial Prompt'. This is necessary to preserve the task context in our roadmap file as accurately as possible without the "broken telephone" effect.

Also include steps for manual testing in the plan, i.e., what needs to be clicked through in the interface.

— SOLID, DRY, KISS, UI/UX, etc —

Follow the principles: SOLID, DRY, KISS, Separation of Concerns, Single Level of Abstraction, Clean Code Practices. Follow UI/UX principles: User-Friendly, Intuitive, Consistency, Accessibility, Feedback, Simplicity, Aesthetic & Modern, Performance, Responsive Design. Use Best Practices."

13) Acceptance Checklist (To Update During Execution)

- [ ] Retry ladder implemented with `player_client` switching and cookie rotation
- [ ] Clear attempt-level logging added
- [ ] Cookie health scoring optional and working
- [ ] Optional proxy rotation respected from `.env`
- [ ] Manual tests pass on a sample of flaky URLs
- [ ] Failure rate reduced by ≥90%
- [ ] No regressions in archive, DB scan, and cleanup flows
- [ ] Playlist downloads receive client/cookie flags; no regressions
- [ ] Job queue retry/backoff aligned; no double retry storms
- [ ] yt-dlp minimum version check and warning in logs
- [ ] Atomic cookie health writes under concurrency

Progress (2025-08-09):

- [x] Implement retry ladder for single-video flow with `player_client` switching (web → android → web+rotated-cookie → ios+rotated-cookie) and jittered backoff.
- [x] Add concise attempt-level logging and safe archive handling (omit `--no-download-archive`).
- [x] Keep format preference `137+251/best[height<=1080]/best`; success path unchanged (DB scan + cleanup).
- [x] Cookie health scoring: select healthier cookies, record outcomes with atomic JSON, integrate with worker.
- [x] Playlist parity: enforce `137+251/best[height<=1080]/best`, add `player_client` (env `YTDLP_PLAYLIST_CLIENT`, default `android`) and optional UA alignment in `download_playlist.py`.
- [x] Queue coordination: in single-video worker, raise `RuntimeError("network: SABR/403...")` after exhausted attempts to classify as retryable; existing queue will mark as retry with backoff.
- [x] yt-dlp version check logging: log detected version in both single-video worker and playlist script; warn if below `YTDLP_MIN_VERSION` (default `2025.8.20`).
- [x] Optional proxy rotation: support `PROXY_URLS` (comma-separated) and per-attempt proxy selection/rotation in single-video ladder.
- [x] Admin UI and API: add `/api/system/cookies/health` endpoint and "Show Cookies Health" section to `templates/maintenance.html` to visualize cookie success/failure stats from `_health.json`.

14) Known pitfalls and fixes

- Do not use non-existent flags like `--no-download-archive`.
- On repeated failures, ensure partial `.part` files are cleaned only when safe. Keep current success-path cleanup; consider adding failure-path cleanup for stale `.part` files older than N minutes.
- Avoid using the TV client profile which correlates with SABR in our logs.



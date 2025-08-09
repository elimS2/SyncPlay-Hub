## SQLite concurrency and "database is locked" mitigation roadmap

Status: Draft

Owner: YouTube Downloader Project

Last updated: 2025-08-09

---

### Problem statement

We intermittently get "database is locked" when concurrent actions happen during heavy operations, for example:

- Adding a channel via `/channels` which enqueues many download jobs, while at the same time:
  - Deleting a currently playing track in `likes_player` UI
  - Clicking Retry for a job in `/jobs`

Observed in job logs and UI errors: `sqlite3.OperationalError: database is locked`.

Impact:

- User actions fail (delete, retry) or are delayed
- Playback telemetry (seek/volume/history) sometimes not recorded
- Potential user confusion and degraded UX under load

Environment assumptions:

- Single-process Flask app + background job workers (threads)
- SQLite database file `tracks.db`
- Windows host, filesystem locks can be sensitive

---

### Initial Prompt (verbatim, translated to English)

I added, at `http://192.168.88.82:8000/channels`, via the “add channel” button a download of videos from the link `https://www.youtube.com/@ImagineDragonsVEVO/videos` and I can see that at `http://192.168.88.82:8000/jobs` a queue of download tasks has formed. If during the download I, for example, delete some track via the delete button on the page `http://192.168.88.82:8000/likes_player/0` which plays here `http://192.168.88.82:8000/likes_player/0`, or I click Retry for some task at `http://192.168.88.82:8000/jobs`, then I may get a "database locked" error.

=== Analyse the Task and project ===

Deeply analyze our task and project and decide how best to implement it.

=== Create Roadmap ===

Create a detailed, step-by-step plan for implementing this task in a separate document file. We have a folder `docs/features` for this. If there is no such folder, create it. Document in the file, as thoroughly as possible, all the discovered and tested issues, nuances and solutions, if any. As you progress with implementing this task, you will use this file as a to-do checklist, updating this document and documenting what has been done, how it was done, what problems arose and what decisions were made. For history, do not delete items; only update their status and comment. If during implementation it becomes clear that new tasks need to be added, add them to this document. This will help us keep context, remember what has already been done, and not forget what was planned. Remember that only the English language is allowed in code and comments and project strings. When you write the plan, stop and ask me if I agree to start implementing it or if anything needs to be adjusted.

Also include steps for manual testing, i.e. what needs to be clicked through in the interface.

=== SOLID, DRY, KISS, UI/UX, etc ===

Follow the principles: SOLID, DRY, KISS, Separation of Concerns, Single Level of Abstraction, Clean Code Practices.
Follow UI/UX principles: User-Friendly, Intuitive, Consistency, Accessibility, Feedback, Simplicity, Aesthetic & Modern, Performance, Responsive Design.
Use Best Practices.

---

### Current architecture and likely root causes

- Multiple places create SQLite connections concurrently:
  - Central helper:
    - `database.get_connection()` opens a new connection per call with default settings (no busy timeout tuning, no WAL):

```1:45:database.py
def get_connection():
    """Return sqlite3 connection (creates file/tables if needed)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    _ensure_schema(conn)
    return conn
```

- Job queue opens its own connections (and sometimes uses an optimizer/pool):

```96:110:services/job_queue_service.py
def _init_database(self):
    with sqlite3.connect(self.db_path) as conn:
        # create/ensure job_queue table...
```

```181:191:services/job_queue_service.py
def _get_next_job(self) -> Optional[Job]:
    if self._database_optimizer:
        with self._database_optimizer.get_optimized_connection() as conn:
            return self._get_next_job_from_connection(conn)
    else:
        with sqlite3.connect(self.db_path) as conn:
            return self._get_next_job_from_connection(conn)
```

```322:407:services/job_queue_service.py
def _update_job_completion(...):
    with sqlite3.connect(self.db_path) as conn:
        # UPDATE job_queue ...
        conn.commit()
```

- Optimizer/connection pool exists but is not consistently used across the app:

```20:35:utils/database_optimizer.py
class ConnectionPool:
    def __init__(..., timeout: float = 30.0):
        # Applies PRAGMAs: journal_mode=WAL, synchronous=NORMAL, cache_size, temp_store, mmap_size
        # Uses check_same_thread=False, timeout=self.timeout
```

Symptoms explained:

- Without global WAL and busy timeouts, concurrent writers (job queue status updates + UI delete + telemetry inserts) easily collide.
- Several operations run inside short but frequent write transactions (UPDATE/INSERT with immediate commit), increasing lock contention.
- Inconsistent connection configuration (some using WAL via optimizer, others without) reduces WAL benefits.

---

### Goals and acceptance criteria

- Eliminate user-visible "database is locked" during normal concurrent usage.
- Maintain integrity and performance under load (channel sync downloads + active playback + admin actions).
- Keep changes minimally invasive first; allow iterative hardening.

Acceptance tests (high level):

- While a large channel sync is running, repeatedly:
  - Delete tracks from Likes Player
  - Press Retry on failed jobs
  - Generate frequent playback seek/volume events
  No "database is locked" surfaces in UI or logs for 10+ minutes.

---

### Implementation plan (phased)

Phase 1 – Quick systemic mitigations (low risk)

1) Centralize connection settings in `database.get_connection`:
   - Use `timeout=30.0`
   - Apply PRAGMAs per-connection:
     - `PRAGMA journal_mode=WAL`
     - `PRAGMA synchronous=NORMAL`
     - `PRAGMA foreign_keys=ON`
     - `PRAGMA busy_timeout=30000`
     - Optionally: `PRAGMA temp_store=MEMORY`, `PRAGMA mmap_size=268435456`, `PRAGMA cache_size=-64000`
   - Consider `check_same_thread=False` only if a connection is used across threads (preferred: do not share connections; keep one-connection-per-operation).

2) Introduce a small retry helper for transient `sqlite3.OperationalError` with message containing "database is locked":
   - Exponential backoff, max ~5 retries, base delay 50–100ms.
   - Apply to the most contention-prone write paths:
     - Job queue status updates (`_get_next_job_from_connection`, `_update_job_completion`, `retry_job`, `cancel_job`)
     - Playback telemetry writers (`record_event`, volume/seek, likes/dislikes)
     - Delete/restore flows in channels/files APIs.

3) Replace direct `sqlite3.connect(...)` in job queue with a shared helper:
   - Either import `database.get_connection()` (preferred) or a local wrapper that applies the same PRAGMAs/timeout.
   - Keep using context managers and short transactions.

4) Ensure connections close promptly:
   - Audit delete/move flows to ensure DB connection is not held while performing long file I/O; open connection only for the DB mutation moment, then close.

Deliverables Phase 1:

- Updated `database.get_connection` with PRAGMAs and timeout
- Lightweight retry utility and adopted on critical write paths
- Job queue adjusted to use the unified connection settings

Phase 2 – Broader consistency + read-only optimization

5) Provide `get_read_connection()` using SQLite URI with `mode=ro` for heavy read-only endpoints to avoid writer blocking where feasible.

6) Expand adoption of unified helper across controllers/services:
   - Replace raw `sqlite3.connect(...)` occurrences in services and scripts that run inside the app lifecycle.

7) Optionally leverage `utils/database_optimizer.DatabaseOptimizer` in the job queue consistently, or sunset it if the unified helper suffices.

Phase 3 – Operational safeguards

8) Schedule maintenance operations (VACUUM/ANALYZE) during idle windows only; prevent maintenance while active workers are running.

9) Add structured logging around DB retries to detect hot spots.

10) Add a minimal health panel (or endpoint) to surface WAL mode, busy timeout, and current lock stats.

---

### Detailed task checklist

- [x] Implement PRAGMA and timeout configuration in `database.get_connection`
- [x] Add retry helper in `database.py` (pure function with callable argument)
- [ ] Apply retry helper to:
  - [x] `database.record_event` write section
  - [x] `controllers/api/*` endpoints that write (delete/restore/trash/likes)
  - [x] `services/job_queue_service.py` write hotspots
- [ ] Replace direct `sqlite3.connect` in job queue with unified helper
- [ ] Audit file delete/move flows to shorten DB connection holding
- [ ] Implement `get_read_connection()` for read-only pages if beneficial
- [ ] Guard maintenance tasks from running under load
- [ ] Add logging for retry occurrences and durations
- [ ] Manual test pass (see below)

---

### Manual testing steps (UI click-through)

Prepare:

1) Start the app; ensure database upgraded and WAL active.
2) Navigate to `/channels` and add a channel, e.g. `https://www.youtube.com/@ImagineDragonsVEVO/videos`.
3) Navigate to `/jobs` and confirm a large queue forms and workers process jobs.

Concurrent interaction tests:

4) Open `/likes_player/0` and start playback of liked tracks.
5) While downloads are active, perform:
   - Delete current playing track via delete button
   - Immediately undo/restore if available
   - Repeatedly seek within the track and adjust volume rapidly for 15–30 seconds

6) In `/jobs`, select several failed jobs and press Retry rapidly (including repeated clicks).

Expected results:

- No visible "database is locked" errors in the UI
- Deletions/restores complete successfully
- Job retries transition to pending/running reliably
- Seek/volume events continue to be recorded without error messages in logs

Verification:

- Review server logs and job logs for absence of `database is locked`
- Spot-check `play_history` growth and job status transitions

---

### Risks, trade-offs, and notes

- WAL requires filesystem support (Windows supports WAL). WAL file size should be monitored.
- `busy_timeout` and retries increase latency under extreme contention but greatly improve perceived reliability.
- Avoid long-running transactions; keep writes short and infrequent where possible.

---

### Rollout plan

1) Implement Phase 1 changes behind minimal risk toggles (no schema changes).
2) Deploy and observe under typical workload.
3) If residual lock events remain, proceed with Phase 2 optimizations.

---

### Open questions

- Should we migrate all app-internal scripts to the unified helper, or only those executed within the web process/worker?
- Do we want a global pool for the entire app, or keep per-operation short-lived connections with consistent PRAGMAs?

---

### Next step

If you approve this roadmap, I will proceed with Phase 1 (central PRAGMAs/timeout, retry helper, unify job queue connections) and then run the manual tests.



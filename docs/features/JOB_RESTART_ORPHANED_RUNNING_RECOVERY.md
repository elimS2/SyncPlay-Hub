# Feature: Reliable Job Recovery on Server Restart

## Status
- Status: Planned
- Owner: Job Queue & System Control
- Created: 2025-08-23

---

## Initial Prompt (translated to English)
There is the following problem. If, for example, on the Jobs page (`http://192.168.88.82:8000/jobs`) a queue of tasks (e.g., Single Video Download) is formed and I click Restart server on that page, or click restart on another page, then during the restart the current task remains in the Running status and no longer updates its status. At the same time, the next task in the queue also transitions to Running, and that one completes correctly and then the next one is picked up. But the one that got stuck will hang until I press cancel and then retry it again. How can we make it complete correctly? Or at least restart automatically?

Do not write code yet; analyze the situation and say how you would fix it.

=== Analyse the Task and project ===
Deeply analyze our task, our project, and decide how best to implement this.

=== Create Roadmap ===
Create a detailed step-by-step implementation plan for this task in a separate document file. We have a folder `docs/features` for this. If such a folder does not exist, create it. Document in this file all discovered and tried issues, nuances, and solutions as much as possible, if any. As we progress with the implementation of this task, you will use this file as a todo checklist, updating it and documenting what was done, how it was done, which issues occurred, and what decisions were made. For history, do not delete items; you can only update their status and comment. If during implementation it becomes clear that something needs to be added as tasks, add them to this document. This will help us maintain context, remember what has been done, and not forget what was planned. Keep in mind that only the English language is allowed in the project's code and comments. When you write the plan, stop and ask me whether I agree to start implementing it or whether something needs to be adjusted.

Include this very prompt in the plan (translated into English). You can call it something like "Initial Prompt". This is needed to preserve the original task context in our roadmap file.

Also include steps for manual testing, i.e., what to click in the UI.

=== SOLID, DRY, KISS, UI/UX, etc ===
Follow the principles: SOLID, DRY, KISS, Separation of Concerns, Single Level of Abstraction, Clean Code Practices.
Follow UI/UX principles: User-Friendly, Intuitive, Consistency, Accessibility, Feedback, Simplicity, Aesthetic & Modern, Performance, Responsive Design.
Use Best Practices.

---

## Problem Analysis

- Symptom: After clicking Restart, the currently running job remains in `running` state indefinitely and is never resumed or transitioned. The next job may start and complete, but the previous one remains stuck until manually cancelled and retried.
- User impact: Requires manual intervention (Cancel → Retry). Queue appears inconsistent, with phantom `running` jobs.

### Root Cause (code-level)
- Restart implementation (`controllers/api/system_api.py` → `POST /api/restart`) spawns a new process and force-exits the current process via `os._exit(0)` without coordinating with the Job Queue Service.
- The Job Queue Service (`services/job_queue_service.py`) maintains in-memory `self._running_jobs` and marks DB rows `status='running'` when a job is picked. On abrupt process exit:
  - In-memory `self._running_jobs` is lost.
  - DB rows already updated to `running` remain `running` forever.
- On startup, there is no sweep that resets orphaned `running` jobs. The worker loop does a periodic zombie cleanup (`_cleanup_zombie_jobs`) every 5 minutes and only marks as `zombie` after a threshold (default ~60 minutes or 2x timeout). This is too late and does not requeue immediately.
- There is graceful shutdown logic (`shutdown()` in `JobQueueService`) that can cancel or mark jobs, but it is never invoked by the restart endpoint.

### Constraints and considerations
- Jobs may be mid-stream (downloads, file writes). Abruptly ending them can leave partial files. Recovery must be idempotent and safe.
- We run with `max_workers=1` today, but the solution should scale to multiple workers.
- We already have `worker_id`, `started_at`, and reasonable status vocabulary (`retrying`, `zombie`, `timeout`, etc.).

---

## Goals
- Ensure no orphaned `running` jobs persist across server restarts.
- Automatically and quickly recover interrupted jobs after restart (preferably immediately).
- Minimize user intervention and keep the UI consistent.
- Preserve data integrity (handle partial files gracefully).

---

## High-Level Design

1) Graceful restart path (no cancellation)
- Before spawning the new process, pause dequeuing and prepare for restart:
  - Stop accepting new jobs; do not cancel the currently running job.
  - Option A (recommended): proactively mark the currently running job(s) for immediate resume by setting status to `retrying` with `next_retry_at = NOW()`, and nullify `started_at`/`worker_id`. This ensures automatic resume after restart.
  - Option B: do nothing and let the startup recovery sweep requeue `running` jobs instantly on boot.
- Rationale: guarantees the job continues after restart without requiring manual cancel/retry.

2) Startup recovery sweep
- On Job Queue Service startup, perform a one-time sweep to detect any orphaned `running` jobs and immediately transition them to a recoverable state:
  - Preferred: move to `retrying` with `next_retry_at = NOW()`, reset `started_at`, `worker_id`, optional increment of `retry_count`, and set `error_message = 'Recovered after server restart'`.
  - Alternative: move directly to `pending` (simpler), but `retrying` keeps semantics consistent with error/retry flow.
- Rationale: even if the restart was uncoordinated (e.g., process crash), startup will self-heal the queue.

3) Optional: Heartbeat/instance binding (future-proof)
- Record server instance ID (PID or UUID) in a runtime setting and optionally tie `worker_id` to instance. On startup, any `running` job bound to a prior instance is considered orphaned and is recovered immediately. This is a future enhancement; not required for initial fix.

4) UX feedback
- Jobs page: no change strictly required. Optionally, show a subtle banner “Jobs recovered after restart” when the sweep runs (future improvement).

---

## Implementation Plan (Step-by-step)

- Phase 1 — Minimal reliable fix
  1. Restart endpoint integration
     - Update `POST /api/restart` to perform a restart-safe queue pause: stop dequeuing; optionally execute "eager resume on restart" (set `running` → `retrying` with `next_retry_at=NOW()`, reset `started_at`/`worker_id`). Do not cancel.
  2. Startup sweep
     - On Job Queue Service initialization or `start()`, run a one-time recovery function:
       - Find all jobs with `status = 'running'`.
       - Update them to `retrying` (or `pending`) with:
         - `started_at = NULL`, `worker_id = NULL`;
         - `next_retry_at = CURRENT_TIMESTAMP` (if `retrying`);
         - `error_message = 'Recovered after server restart'` (or similar);
         - optionally bump `retry_count` by 1 (configurable; default: do not increment).
     - Log how many jobs were recovered.

- Phase 2 — Robustness & ergonomics
  3. Shorten zombie cleanup interval and threshold (optional) or keep as-is since startup sweep will handle common case.
  4. Add configuration flags (env or DB settings):
     - `job_restart_recovery_strategy = retrying|pending` (default: `retrying`).
     - `job_restart_shutdown_timeout_seconds` (default: `10`).
     - `job_restart_increment_retry_on_recover` (default: `false`).
  5. Worker safety for interrupted jobs (downloads):
     - Ensure workers can handle residual/partial files on retry (e.g., temp file cleanup or resume logic). Validate current workers behavior; document where needed.

- Phase 3 — Future-proofing (optional)
  6. Instance-aware recovery:
     - Record a `server_instance_id` on startup; propagate `worker_id` accordingly.
     - On recovery sweep, only consider `running` jobs not bound to current instance.
  7. UI affordances (optional):
     - Show recovered count in the Jobs page banner for transparency.

---

## Manual Test Plan (UI-driven)

2) Expected with the fix (resume after restart)
- After restart, the previously running job is automatically re-queued (status quickly becomes `retrying` or `pending` and then `running`) and completes without manual actions.
- The queue proceeds with the recovered job; no phantom `running` remains.

---

## Acceptance Criteria
- No jobs remain stuck in `running` after restart without an active worker.
- On startup, orphaned `running` jobs are recovered automatically and executed without manual Cancel/Retry.
- Graceful restart path updates job statuses deterministically (finish or cancel with message) before process exit.
- Manual test plan passes on Single Video Download and at least one other job type (e.g., Quick Sync).

---

## Tasks (living checklist)
- [x] Integrate restart-safe queue pause in `/api/restart` (no cancellation; eager resume optional).
- [ ] Implement startup recovery sweep for `running` → `retrying` (or `pending`).
- [ ] Add configuration toggles (strategy, timeout, increment retry on recover).
- [ ] Validate worker behavior on retried interrupted jobs (partial file handling).
- [ ] Add logging and lightweight telemetry (recovered/resumed count).
- [ ] Run manual test plan; capture screenshots/log excerpts.

---

## Notes & References
- Restart endpoint: `controllers/api/system_api.py` `POST /api/restart`.
- Job Queue Service lifecycle and shutdown logic: `services/job_queue_service.py` (`start()`, `shutdown()`, `_cleanup_zombie_jobs`).
- Status vocabulary and job model: `services/job_types.py`.

---

## Implementation Notes (Phase 1 — Step 1)

- Added queue pause and eager resume preparation:
  - `services/job_queue_service.py`
    - New field: `_paused` to control dequeuing.
    - `pause_dequeuing()` to pause new job intake.
    - `prepare_for_restart(eager_resume=True)` to mark in-memory running jobs as `retrying` with `next_retry_at = CURRENT_TIMESTAMP`, clearing `started_at` and `worker_id`, and pausing dequeuing. Also mirrors changes in-memory for consistency.
    - Ensured `start()` unpauses the queue by resetting `_paused = False`.
  - `controllers/api/system_api.py`
    - In `POST /api/restart`, before spawning a new process: call `get_job_queue_service().prepare_for_restart(eager_resume=True)` and log count of jobs marked for resume.

- Rationale: No cancellation on restart. Running tasks are prepared to resume immediately after restart, removing the need for manual Cancel/Retry and preventing phantom `running` states.

- Side effects:
  - If a job finishes between marking and process exit, it will persist as completed; requeue marking does not run again on startup for completed jobs.
  - Multi-worker setups still supported: we only touch jobs tracked in current process memory (`self._running_jobs`).

### Checklist updates
- [x] Integrate restart-safe queue pause in `/api/restart` (no cancellation; eager resume optional).
- [ ] Implement startup recovery sweep for `running` → `retrying` (or `pending`).
- [ ] Add configuration toggles (strategy, timeout, increment retry on recover).
- [ ] Validate worker behavior on retried interrupted jobs (partial file handling).
- [ ] Add logging and lightweight telemetry (recovered/resumed count).
- [ ] Run manual test plan; capture screenshots/log excerpts.

## Implementation Notes (Phase 1 — Step 2)

- Added startup recovery sweep so that any `running` jobs left in DB are immediately recovered on boot:
  - `services/job_queue_service.py`
    - New private method `_startup_recovery_sweep(strategy='retrying', increment_retry=False)`.
    - Constructor now: pauses dequeuing, runs recovery sweep, starts worker threads, then unpauses.
    - Default strategy: `retrying` with `next_retry_at = CURRENT_TIMESTAMP`, clearing `started_at`/`worker_id`, preserving retry_count.

- Rationale: even если сервер упал без подготовки к рестарту, “застрявшие” `running` не висят, а сразу переочередаются и продолжаются.

- Notes:
  - Sweep не трогает статусы кроме `running`.
  - Конфиг по стратегии можно расширить позже (env/DB setting), сейчас зашит дефолт.

### Checklist updates
- [x] Implement startup recovery sweep for `running` → `retrying` (or `pending`).

## Implementation Notes (Phase 2 — Config flags)

- Configurable settings (via DB user settings):
  - `job_restart_recovery_strategy`: `retrying` (default) or `pending` — controls startup sweep behavior.
  - `job_restart_increment_retry_on_recover`: `true|false` (default `false`) — whether to bump retry_count on recovery.
  - `job_restart_eager_resume`: `true|false` (default `true`) — whether `/api/restart` marks in-flight jobs for immediate resume before process exit.

- Code changes:
  - `services/job_queue_service.__init__`: reads `job_restart_recovery_strategy` and `job_restart_increment_retry_on_recover` to drive `_startup_recovery_sweep` behavior.
  - `controllers/api/system_api.py:/api/restart`: reads `job_restart_eager_resume` to decide whether to mark running jobs for resume.

- Defaults chosen for minimal surprise and immediate continuation after restart.

### Checklist updates
- [x] Add configuration toggles (strategy, increment retry on recover, eager resume on restart).

## Implementation Notes (Priority Boost for Recovered Jobs)

- Behavior:
  - Recovered jobs (via startup sweep) receive a priority boost if their current priority is below target.
  - Target priority and enabling are configurable.

- Settings:
  - `job_restart_boost_priority`: `true|false` (default `true`).
  - `job_restart_boost_target_priority`: `LOW|NORMAL|HIGH|URGENT|CRITICAL` (default `HIGH`).

- Code:
  - `services/job_queue_service._startup_recovery_sweep(..., boost_priority=True, boost_target='HIGH')` — raises `priority` with `CASE WHEN priority < target THEN target`.
  - `/api/restart` also reads boost settings (currently used for symmetry; boost occurs in sweep; prepare-step remains focused on status/markers).

### Checklist updates
- [x] Priority boost for recovered jobs (configurable target).

## Implementation Notes (Telemetry)

- Added runtime counters to queue stats:
  - `recovery.recovered_jobs`: number of jobs recovered by startup sweep.
  - `recovery.prepared_for_resume`: number of jobs marked by `/api/restart` prepare step.
  - `recovery.priority_boosted`: number of jobs whose priority was boosted.
- Exposed via `GET /api/jobs/queue/status` → `queue_stats.recovery`.

### Checklist updates
- [x] Add logging/telemetry counters for recovery and resume.

## Implementation Notes (UI Telemetry)

- Jobs page (`templates/jobs.html`):
  - Queue Status now shows: Recovered Jobs, Prepared for Resume, Priority Boosted.
  - Values come from `GET /api/jobs/queue/status` → `queue_stats.recovery`.

### Manual Test
- Trigger `/api/restart` with a running job → after restart, open `/jobs` and verify counters reflect prepared/resumed/boosted as applicable.
- Kill process with running job → start server → verify Recovered counter increases.

### Checklist updates
- [x] Expose recovery telemetry in Jobs UI.

## Implementation Notes (UI Recovery Banner)

- Added a non-intrusive banner on `/jobs` above Queue Status when recovery counters indicate activity:
  - Shows: `recovered`, `prepared`, `boosted` counts.
  - Auto-hides when counts are zero.

### Manual Test
- Restart path: run a job → click Restart → after restart open `/jobs` and verify banner appears with prepared/boosted counts.
- Crash path: kill process with running job → start server → verify banner shows recovered count.

### Checklist updates
- [x] Add UI banner for recovery activity on Jobs page.

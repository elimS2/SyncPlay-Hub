## Recurring Task Scheduler – Roadmap and Implementation Plan

Created: 2025-08-28  
Status: Planned  
Owner: Engineering  

---

### Problem Statement

We need first-class, user-configurable scheduling for repetitive background tasks:
- Database backups: choose time and recurrence instead of fixed once-per-day.
- Periodic “Quick Sync” of a specific channel group (e.g., News, Lawyers) with configurable frequency.

Today, automatic backups are handled by a dedicated `AutoBackupService` that checks hourly and runs once per day at a configured time. Quick Sync is available via APIs/UI as on-demand actions but lacks scheduling.

Goal: Introduce a general-purpose recurring scheduler that can manage multiple task types (backups, quick sync for a group, future maintenance tasks) with a clean UI and APIs.

---

### Current State (As-Is)

- Jobs:
  - Job Queue system with workers: `BackupWorker`, `QuickSyncWorker`, etc. (`services/job_workers/**`)
  - Pages: `/jobs` (template `templates/jobs.html`) to monitor and manage jobs.
- Backups:
  - `AutoBackupService` runs in a background thread, configured via `/backups` page and `controllers/api/backup_api.py`.
  - Supports: `enabled`, `schedule_time` (HH:MM UTC), `retention_days`, `check_interval`.
  - Creates `JobType.DATABASE_BACKUP` tasks with reasonable defaults.
- Channels and Quick Sync:
  - Channel groups API and UI exist (`controllers/api/channels_*`, `templates/channels.html`).
  - Quick Sync endpoints for single channel and for an entire group (`controllers/api/channels_sync_api.py`).
  - `ChannelSyncService.quick_sync_channel_group(...)` creates `QUICK_SYNC` jobs for group channels.

Limitations:
- Only backups have a daily schedule via a dedicated service; other periodic tasks are not schedulable.
- No unified place to view/manage all schedules.

---

### High-Level Solution (To-Be)

Introduce a generic Recurring Task Scheduler with:
- Persistent schedules stored in DB.
- Background service that evaluates schedules and enqueues corresponding jobs.
- REST API to CRUD schedules and trigger runs.
- UI to manage schedules globally and contextually from relevant pages (`/backups`, `/channels`).

Backwards compatibility: keep existing backup UI functional; migrate auto-backup configuration into the scheduler (with a compatibility path during transition).

---

### Scope and Requirements

Functional:
- Create, edit, enable/disable, delete schedules.
- Supported task types (initial):
  - `DATABASE_BACKUP` (job data: backup_type, retention_days, cleanup_old, force_backup=false)
  - `QUICK_SYNC_GROUP` (params: group_id)
- Supported recurrences (initial):
  - Daily at HH:MM (UTC)
  - Weekly on selected weekdays at HH:MM (UTC)
  - Fixed interval: every N hours/minutes
  - (Optional later) Cron-like expression
- Manual “Run now” for any schedule.
- Prevent duplicate runs; store `last_run_at` and compute `next_run_at`.

Non-Functional:
- Robust against restarts; no missed duplicate runs.
- Minimal background footprint.
- Clear UI/UX with validation and feedback.

Out of scope (initial):
- Timezone per schedule beyond UTC (can add later).
- Complex cron parser; we’ll start with a simplified model and keep room to extend.

---

### Data Model

New table `scheduled_tasks` (SQLite):
- `id` INTEGER PRIMARY KEY
- `name` TEXT NOT NULL
- `task_type` TEXT NOT NULL  // enum: DATABASE_BACKUP, QUICK_SYNC_GROUP, ...
- `enabled` INTEGER NOT NULL DEFAULT 1  // boolean
- `schedule_kind` TEXT NOT NULL  // enum: daily | weekly | interval | cron
- `schedule_time` TEXT NULL  // HH:MM for daily/weekly
- `schedule_days` TEXT NULL  // JSON array of weekdays ["mon","tue",...]
- `interval_minutes` INTEGER NULL  // for interval kind
- `cron_expr` TEXT NULL  // reserved for future
- `timezone` TEXT NOT NULL DEFAULT 'UTC'
- `params_json` TEXT NOT NULL  // schedule-specific parameters (e.g., {"group_id":7,"retention_days":30})
- `last_run_at` TEXT NULL  // ISO
- `next_run_at` TEXT NULL  // ISO (optional cache)
- `created_at` TEXT NOT NULL
- `updated_at` TEXT NOT NULL

Notes:
- We intentionally keep both a normalized shape and a `params_json` for task-specific props.
- `schedule_kind` guards which fields are used.

---

### Services and Scheduling Logic

New service: `services/recurring_scheduler_service.py`
- Background thread (daemon) similar to `AutoBackupService`.
- Evaluation loop every 60 seconds (configurable):
  1) Load enabled schedules.
  2) For each schedule, check if it should fire now (window-based check like AutoBackupService to tolerate polling).
  3) If yes, enqueue appropriate job(s) and update `last_run_at` (and compute next `next_run_at`).

Dispatchers per `task_type`:
- `DATABASE_BACKUP`: create `JobType.DATABASE_BACKUP` with `JobData` mapping from `params_json` (respect existing defaults and retention).
- `QUICK_SYNC_GROUP`: use `ChannelSyncService.quick_sync_channel_group(group_id)` (preferred) or directly enqueue `QUICK_SYNC` jobs using Job Queue Service.

Duplicate prevention:
- Edge window check (like existing backup service) + idempotence via `last_run_at` date boundary per schedule.

Migration strategy for auto-backup:
- Phase 1: Keep `AutoBackupService` on. Add scheduler-based backup disabled by default.
- Phase 2: Move `/backups` UI to create/update the unified schedule entry; disable `AutoBackupService` once scheduler is active.
- Phase 3: Optionally remove `AutoBackupService` or keep as fallback.

---

### API Endpoints

New blueprint `controllers/api/scheduler_api.py`:
- `GET /api/schedules` – list all schedules
- `POST /api/schedules` – create schedule
- `GET /api/schedules/<id>` – get one
- `PATCH /api/schedules/<id>` – update schedule
- `DELETE /api/schedules/<id>` – delete schedule
- `POST /api/schedules/<id>/toggle` – enable/disable
- `POST /api/schedules/<id>/run_now` – trigger immediately

Validation:
- `schedule_kind` in {daily, weekly, interval, cron}
- For daily/weekly: `schedule_time` required (HH:MM UTC)
- For weekly: `schedule_days` non-empty subset of weekdays
- For interval: `interval_minutes` ≥ 5 (guardrails)
- `task_type` must be allowed values; `params_json` must contain required keys (e.g., `group_id` for quick sync group)

Compatibility endpoints (Phase 2):
- `/api/backup_config` can internally manage a backing schedule row with `task_type=DATABASE_BACKUP`.

---

### UI/UX Changes

Global schedules page (new):
- `GET /schedules` with `templates/schedules.html` – list, create, edit, enable/disable, delete, run-now.
- Filters by task type.

Backups page (`/backups`):
- Replace the current time-only config modal with a Schedule Editor modal powered by the scheduler APIs.
- Show the current backup schedule state; allow run now, enable/disable.

Channels page (`/channels`):
- For each group card (e.g., News, Lawyers), add an overflow menu or button “Schedule Quick Sync”.
- Modal to create/edit a schedule:
  - Choose recurrence kind (daily/weekly/interval)
  - Time or interval
  - Summary of next run
  - Save → creates/updates a `QUICK_SYNC_GROUP` schedule with `params_json = { group_id }`.

Feedback and affordances:
- Inline validation messages.
- Toast notifications on save/delete/run-now.
- Clear indication of UTC.

Accessibility:
- Keyboard navigation, labels for inputs, sufficient contrast.

---

### Security and Reliability

- All schedule mutations behind authenticated API (same as existing admin flows).
- Server-side validation of schedule and params.
- Defensive try/catch around job enqueue, with logging.
- Scheduler thread starts at app boot, stops on shutdown (mirroring current services).

---

### Performance Considerations

- Evaluation loop every 60 seconds; low overhead operations.
- Keep SQL queries simple; load schedules once per tick.
- Debounce flooding: one run per scheduled window.

---

### Step-by-Step Implementation Plan

1) Database layer
- Add `scheduled_tasks` table and CRUD in `database.py`.
- Migration helper guarded by existence checks.

2) Scheduler service
- Implement `services/recurring_scheduler_service.py` with a background loop and dispatchers.
- Unit-test schedule evaluation for daily/weekly/interval.

3) API layer
- Add `controllers/api/scheduler_api.py` with endpoints listed above.
- Validation utilities for schedule payloads.

4) Integration at startup/shutdown
- Start scheduler in `app.py` (alongside existing services).
- Provide stop hook on shutdown.

5) UI – Global page
- `templates/schedules.html` with list/table and modals.
- Minimal CSS reusing existing style.

6) UI – Backups
- Replace/configure existing modal to drive scheduler row for `DATABASE_BACKUP`.
- Keep `/api/backup_*` endpoints working by mapping to scheduler row (phase 2).

7) UI – Channels
- Add “Schedule Quick Sync” action per group in `templates/channels.html`.
- Modal -> create or update a `QUICK_SYNC_GROUP` schedule.

8) Telemetry and logging
- Log schedule creations, updates, runs, and failures.

9) Manual testing and QA
- See “Manual Test Plan” below.

10) Documentation
- Update README section for scheduling.

---

### Risks and Mitigations

- Schedule duplication (backup via old service and new scheduler):
  - Mitigate by disabling AutoBackup once the scheduler backup is enabled (UI notice).
- Time window edge cases around DST/timezones:
  - Initially restrict to UTC; add per-schedule timezone later.
- Job queue stoppage:
  - Surface service/queue health on schedules page; log errors.

---

### Manual Test Plan (UI Walkthrough)

Backups:
1. Open `/backups`.
2. Click “Configure Schedule”.
3. Choose Daily at 02:00 UTC; save.
4. Verify a schedule appears on `/schedules` with task type DATABASE_BACKUP.
5. Click “Run now”; verify new job appears in `/jobs` with type Database Backup and completes.
6. Wait until next window or simulate time: verify auto-enqueue works once and only once per day.

Quick Sync for a group:
1. Open `/channels`.
2. Find group “News”; click “Schedule Quick Sync”.
3. Choose “Daily at 05:30 UTC”; save.
4. Verify schedule presence in `/schedules` with task type QUICK_SYNC_GROUP and `group_id`.
5. Click “Run now”; verify QUICK_SYNC jobs are created for the group (see `/jobs`).
6. Confirm that the next run prediction updates and no duplicate runs happen in the same window.

Schedules page:
1. Open `/schedules`; verify list with filters and statuses.
2. Toggle enable/disable; confirm status updates.
3. Edit schedule (switch to Weekly Mon,Wed,Fri at 04:00); save. Verify next run.
4. Delete schedule; verify removal.

---

### Initial Prompt (Translated to English)

On the page at http://127.0.0.1:8000/jobs we have a task queue running. There is also a database backup task that appears once a day:

Job #23848 Details
Type: Database Backup
Status: completed
Priority: normal
Retries: 0/3
Created: 08/28/2025, 02:56:09
Started: 08/28/2025, 05:56:10
Duration: 5s
Worker: Not assigned
Job Parameters:
{
  "job_data": "JobData({'backup_type': 'full', 'retention_days': 30, 'cleanup_old': False, 'force_backup': False, 'source': 'auto_backup_service'})",
  "max_retries": 2
}

I want the ability to control the backup schedule: specify at what time and with what recurrence to execute this task. I also want the ability to set periodic execution of another task; for example, once a day I want to set up a quick sync for a specific group of channels.

For instance, on the page at http://127.0.0.1:8000/channels there is a channel group “News” and a channel group “Lawyers”. I want to be able to configure a schedule for quick synchronization of such groups.

Analyze the task and the project and decide how best to implement this.

Create a detailed, step-by-step plan (a roadmap) as a separate document in docs/features. If there is no such folder, create it. Document any discovered issues, nuances, and solutions. As we progress, we will use this file as a to-do checklist, updating its status, documenting what is done, how it is done, and decisions made. Do not delete items for history; update status and comment instead. If additional tasks arise, add them to this document. The codebase allows only the English language (variables, functions, comments, UI strings, API responses, etc.). After writing the plan, stop and ask me whether I agree to start implementing it or if anything needs adjustment.

Include steps for manual testing in the interface.

Follow SOLID, DRY, KISS, Separation of Concerns, Single Level of Abstraction, and Clean Code practices. Follow UI/UX principles: user-friendly, intuitive, consistent, accessible, with feedback, simple, modern, performant, and responsive design. Use best practices.

---

### Task Checklist (Living Roadmap)

- [x] Database: add `scheduled_tasks` table and CRUD in `database.py`
- [x] Service: implement `recurring_scheduler_service.py` with evaluation loop and dispatchers
- [x] API: create `scheduler_api.py` with full CRUD + run-now + toggle
- [x] Startup/Shutdown: wire scheduler into `app.py`
- [x] UI: new `/schedules` page (list, create, edit, toggle, delete, run-now)
- [x] UI: integrate schedule editor in `/backups` (backup schedule)
- [x] UI: add “Schedule Quick Sync” per group in `/channels`
- [ ] Logging/Telemetry improvements for scheduled runs
- [x] Docs: update README with scheduling section
- [ ] QA: complete manual test plan above

Notes (2025-08-28):
- Implemented `database/migrations/migration_012_add_scheduled_tasks.py` creating `scheduled_tasks` with indices and trigger.
- Added CRUD helpers in `database.py`: `create_scheduled_task`, `get_scheduled_tasks`, `get_scheduled_task_by_id`, `update_scheduled_task`, `set_scheduled_task_enabled`, `touch_scheduled_task_run`, `delete_scheduled_task`.
- Implemented `services/recurring_scheduler_service.py` with UTC evaluation, daily/weekly/interval support, and dispatchers for DATABASE_BACKUP and QUICK_SYNC_GROUP. Cron is stubbed for future.
- Implemented `controllers/api/scheduler_api.py`: list/create/get/update/delete/toggle/run_now. Registered in `controllers/api/__init__.py`.
- Wired `RecurringSchedulerService` start/stop in `app.py` (start after Job Queue, stop on shutdown).
 - Added `templates/schedules.html` with CRUD, toggle, and run-now using Scheduler API; route `/schedules`, sidebar entry under System Management.
- Integrated Scheduler into `/backups`: Schedule Backup modal backed by Scheduler API for `DATABASE_BACKUP` (daily/weekly/interval, retention days). Kept existing AutoBackup controls intact.
 - Added group-level scheduler in `/channels`: button “Schedule Quick Sync” with modal to create/update/delete a `QUICK_SYNC_GROUP` schedule (daily/weekly/interval), and ability to run now.

UI updates (2025-08-28):
- Schedules page: for `QUICK_SYNC_GROUP` added Group dropdown populated from `/api/channels/channel_groups` (no need to enter ID manually).
- Time inputs (Schedules + Backups) normalized to 24-hour format; in Schedules switched to masked text `HH:MM` to avoid AM/PM UI in some browsers.
- Basic scheduler logging added: evaluation summary, due schedule, dispatched job info.

Operational notes:
- Apply migration 012 (scheduled_tasks) before using the Scheduler API.

Notes:
- Phase 2 may deprecate `AutoBackupService` in favor of unified scheduler or keep it as a fallback.

---

### Implementation Notes and Decisions

- Start with daily/weekly/interval; design data model to later accept cron.
- Keep UTC everywhere initially to avoid timezone complexity.
- Reuse existing workers and services for job execution to remain DRY.
- Prefer small, composable UI modals tied to new APIs.

---

### Open Questions

- Should we migrate existing backup configuration into a schedule automatically on first startup after deployment?
- Any group-level permissions/visibility constraints for who can schedule Quick Sync?


---

### Post-deployment Checklist

- [x] Apply DB migration 012 (`scheduled_tasks`) to the active DB in `.env` (e.g., `D:\music\Youtube\DB\tracks.db`).
- [x] Restart server to load new exports from `database/__init__.py`.
- [x] Verify `/schedules` and `GET /api/schedules` respond without errors.

### Manual QA – High Priority

1) Schedules page
   - Create QUICK_SYNC_GROUP with Group dropdown, daily 05:30 → Save → Run now → check `/jobs` and logs.
   - Create DATABASE_BACKUP (interval 5 min for test) → Run now → check `/jobs` and logs.
2) Automatic run
   - For an interval=5 schedule, wait for automatic trigger; confirm log lines `[Scheduler] Evaluating` and `Due schedule` and job creation.
3) Time input
   - Ensure all time inputs accept only `HH:MM` (24h).
4) CRUD
   - Edit, disable/enable, delete; verify API and UI reflect changes.

### Known Issues and Fixes

- [x] Database package did not expose scheduled task CRUD initially
  - Fix: Exported `create_scheduled_task`, `get_scheduled_tasks`, `get_scheduled_task_by_id`, `update_scheduled_task`, `set_scheduled_task_enabled`, `touch_scheduled_task_run`, `delete_scheduled_task` in `database/__init__.py`.
- [x] Runtime error "no such table: scheduled_tasks"
  - Fix: Applied migration to the actual runtime DB path from `.env` and restarted.

### Next Steps

1) Logging/Telemetry (pending)
   - Log schedule evaluations and dispatch outcomes (schedule id/type/params, job ids) in the main log.
   - Display “Next run” prediction per schedule in `/schedules` (compute client-side initially).
   - Show service health badge (running/stopped) and last evaluation timestamp on `/schedules`.

2) UX polish (pending)
   - Client-side validation for time HH:MM, interval ≥ 5, weekly days non-empty.
   - Replace blocking `alert()` with toasts; disable Run Now on invalid configs.

3) Backup config guidance (pending)
   - Document replacing AutoBackup with unified scheduler; optionally hide AutoBackup when a backup schedule exists.

4) QA (pending)
   - Execute Manual Test Plan across `/schedules`, `/backups`, `/channels`.


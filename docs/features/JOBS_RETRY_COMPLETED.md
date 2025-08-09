Title: Enable Retry for Completed Jobs on Jobs Admin Page
Status: Completed
Owner: Job Queue / Admin UI
Last Updated: 2025-08-09

1) Initial Prompt

The following is the exact task statement translated to English to preserve context:

"On the jobs page at http://192.168.88.82:8000/jobs we can move cancelled or failed jobs back to pending using the retry button. Implement the same ability for completed jobs. Analyze the task and the project in depth and decide how to best implement it. Create a detailed, step-by-step roadmap for implementing this task in a separate document file. We have a folder docs/features for this; if it doesn’t exist, create it. Document in this file all discovered and tried issues, nuances, and solutions as thoroughly as possible. As you progress with implementation, use this file as a to‑do checklist; keep updating it and document what was done, how it was done, what issues arose, and what decisions were made. For history, do not delete items; only update their status and add comments. If during implementation it becomes clear that new tasks should be added, add them to this document. This will help us keep context, remember what we already did, and not forget what was planned. Remember that only the English language is allowed in code and comments and project strings. After writing the plan, stop and ask me whether I agree to start implementing it or something needs to be adjusted in it. Also include manual testing steps (what should be clicked in the interface). Follow SOLID, DRY, KISS, Separation of Concerns, Single Level of Abstraction, Clean Code Practices, and good UI/UX principles."

2) Background and Current State

- Jobs page UI (`templates/jobs.html`) currently shows a Retry button only when `job.status` is one of: `failed`, `cancelled`, `timeout`. This applies both in the table row actions and inside the job details modal.
- API endpoint `POST /api/jobs/<id>/retry` implemented in `controllers/api/jobs_api.py` only allows retry for statuses: `FAILED`, `CANCELLED`, `TIMEOUT`.
- Service method `JobQueueService.retry_job(job_id)` in `services/job_queue_service.py` also restricts retriable statuses to `['failed', 'cancelled', 'timeout']`. It resets key fields and sets `status = 'pending'`, clearing timestamps such as `started_at`, `completed_at`, and fields like `worker_id`, `error_message`, `failure_type`, `next_retry_at`.
- Database CHECK constraint already supports all statuses including `completed` (see migration `migration_003_add_missing_job_statuses.py`). No schema change is required for this feature.

Implications of retrying a completed job:
- Re-running a completed download job should be idempotent due to existing archive usage, so duplicate content is unlikely to be redownloaded. For metadata and other jobs, re-running usually refreshes results and is safe. We keep behavior consistent with existing single-job retry semantics: we requeue the same job record rather than creating a new job.

3) Goals and Non-Goals

- Goals:
  - Allow users to Retry completed jobs from the jobs page. The action should move the job to `pending` and let workers pick it up again.
  - Preserve current UX patterns (button placement, toasts, pagination, filters).
  - Maintain auditability by keeping the same job record but resetting runtime fields as already done by the service.

- Non-Goals (for this change):
  - Bulk retry operations for multiple jobs.
  - Changing retry counters or adding separate “requeue” endpoints.
  - Modifying worker logic or job semantics beyond enabling completed → pending via retry.

4) Design Overview

- Keep KISS: extend existing retry capability to include `completed` state.
- Minimal changes across three layers:
  1) UI: render the Retry button for `completed` status alongside `failed`, `cancelled`, `timeout` both in the jobs table and in the job modal.
  2) API: allow `JobStatus.COMPLETED` in the whitelist for retry eligibility.
  3) Service: allow `'completed'` in the SQL-level status check before resetting to `pending`.

Behavioral notes:
- The service already protects against retrying running jobs via an in-memory `_running_jobs` check.
- Retrying a completed job resets `completed_at` and other runtime fields, exactly like failed/cancelled/timeout retries.
- We do not increment `retry_count` for this operation (match current service logic), keeping semantics consistent with existing retry behavior.

5) Implementation Plan (Step-by-Step)

- Backend: API
  - File: `controllers/api/jobs_api.py`
  - Change: in `api_retry_job`, extend allowed statuses to include `JobStatus.COMPLETED`.
  - Update error message text accordingly.
  - Verify that logging remains consistent.

- Backend: Service
  - File: `services/job_queue_service.py`
  - Change: in `retry_job`, extend the status guard to accept `'completed'` in addition to `['failed', 'cancelled', 'timeout']`.
  - No changes to the UPDATE SQL other than allowing the transition. Fields reset already cover the completed → pending use case.

- Frontend: Jobs page UI
  - File: `templates/jobs.html`
  - Table actions: include `completed` in the conditional that renders the Retry button.
  - Job modal: include `completed` in the conditional that renders the Retry button.
  - Optional UX nicety: add a title/tooltip on the Retry button: "Re-queue this completed job and run it again".

- Logging/Observability
  - Confirm existing log message `[Jobs API] Retried job #<id>` is emitted.
  - Confirm counters and pagination refresh as today.

6) Acceptance Criteria

- From the jobs page, a job with status `completed` displays the Retry button in both row actions and the details modal.
- Clicking Retry on a completed job succeeds (HTTP 200), and the job status becomes `pending` quickly after.
- The job is picked up by a worker and runs again according to its job type.
- No regressions for retrying `failed`, `cancelled`, or `timeout` jobs.
- No ability to retry `running` jobs; existing safeguards remain intact.

7) Manual Testing Guide

- UI walkthrough:
  1) Open `http://192.168.88.82:8000/jobs`.
  2) In the Status filter, select `completed` and click Refresh/Load if needed.
  3) Pick a job row with status `completed` and verify the Retry button is present.
  4) Click Retry; observe a success toast and that the job status transitions to `pending` upon refresh (the list should update automatically as today, or click Reload Jobs).
  5) Click the job to open the details modal; verify Retry is present for `completed` status and works from the modal as well.
  6) Monitor the job logs and final status after the worker processes it.

- API checks (optional):
  - `POST /api/jobs/<id>/retry` for a `completed` job returns `{ status: "ok" }` and message like "queued for retry".
  - For disallowed states (e.g., `running`), the API returns HTTP 400 with an explanatory error.

- Functional scenarios:
  - Retry a completed single video download job; confirm no duplicate file is created due to archive behavior.
  - Retry a completed metadata extraction job; confirm it runs again without errors.

8) Risks and Mitigations

- Risk: Re-running completed download may attempt to redownload content.
  - Mitigation: Archive files prevent duplicates; keep behavior unchanged.
- Risk: Confusion about semantics of retrying completed jobs.
  - Mitigation: Tooltip text added to clarify that Retry re-queues the same job.

9) Rollback Plan

- If issues are discovered, revert the changes that added `completed` to retry-eligible statuses in both API and service, and revert the UI conditionals in `templates/jobs.html`.

10) Work Items Checklist (To-Do)

- [x] Update `controllers/api/jobs_api.py` to allow retry for `COMPLETED`.
- [x] Update `services/job_queue_service.py` to allow retry for `'completed'`.
- [x] Update `templates/jobs.html` table actions to show Retry for `completed`.
- [x] Update `templates/jobs.html` modal actions to show Retry for `completed`.
- [x] Add optional tooltip to Retry button for clarity.
- [x] Manual test across job types and statuses.
- [x] Verify no regressions and that counters/pagination remain correct.

11) Compliance and Principles

- Adheres to SOLID, DRY, KISS, Separation of Concerns, Single Level of Abstraction, and Clean Code Practices.
- UI/UX principles followed: intuitive controls, consistency with existing buttons, clear feedback via toasts, minimal cognitive load.

12) Progress Updates

- 2025-08-09: API updated in `controllers/api/jobs_api.py` to accept `JobStatus.COMPLETED` for `/jobs/<id>/retry`. Error text and docstring adjusted. Lint clean.
- 2025-08-09: Service updated in `services/job_queue_service.py` to allow `'completed'` in `retry_job` status guard. Docstring updated. Lint clean.
- 2025-08-09: UI updated in `templates/jobs.html` to show Retry for `completed` in both the table and the job details modal, with tooltip text for clarity.
- 2025-08-09: Manual testing completed by user: Retry for completed jobs works as expected; status transitions to `pending`, workers pick the job, no regressions observed. Task marked as Completed.



#!/usr/bin/env python3
"""
Recurring Scheduler Service

Background service that evaluates persisted schedules and enqueues jobs accordingly.

Supported task types (initial):
- DATABASE_BACKUP → enqueue JobType.DATABASE_BACKUP using current backup defaults
- QUICK_SYNC_GROUP → create Quick Sync jobs for all channels in the group

Time semantics:
- All schedules are evaluated in UTC.
- Tolerates polling by using a small execution window based on evaluation interval.
"""

from __future__ import annotations

import threading
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from controllers.api.shared import get_connection, log_message
import database as db


class RecurringSchedulerService:
    """Evaluates scheduled tasks and dispatches corresponding jobs."""

    def __init__(self, *, check_interval_seconds: int = 60):
        self.check_interval_seconds = max(5, int(check_interval_seconds))
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            self.logger.warning("RecurringSchedulerService is already running")
            return
        self.logger.info(
            f"Starting RecurringSchedulerService (interval {self.check_interval_seconds}s)"
        )
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, name="RecurringScheduler", daemon=True
        )
        self._thread.start()
        self.logger.info("RecurringSchedulerService started")

    def stop(self) -> None:
        if not self._thread or not self._thread.is_alive():
            self.logger.info("RecurringSchedulerService is not running")
            return
        self.logger.info("Stopping RecurringSchedulerService...")
        self._stop_event.set()
        self._thread.join(timeout=10)
        if self._thread.is_alive():
            self.logger.warning("RecurringSchedulerService did not stop gracefully")
        else:
            self.logger.info("RecurringSchedulerService stopped")

    # ---------- Core loop ----------

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._evaluate_once()
            except Exception as exc:
                self.logger.error(f"RecurringSchedulerService loop error: {exc}")
            # Wait for next tick or stop
            if self._stop_event.wait(self.check_interval_seconds):
                break

    def _evaluate_once(self) -> None:
        conn = get_connection()
        try:
            schedules = db.get_scheduled_tasks(conn, only_enabled=True)
        finally:
            conn.close()

        if not schedules:
            return

        now_utc = datetime.utcnow()
        window = timedelta(seconds=self.check_interval_seconds)

        try:
            log_message(f"[Scheduler] Evaluating {len(schedules)} enabled schedule(s) at {now_utc.isoformat()}Z")
        except Exception:
            self.logger.info(f"[Scheduler] Evaluating {len(schedules)} enabled schedule(s)")

        for sched in schedules:
            try:
                if self._should_run(sched, now_utc, window):
                    try:
                        log_message(
                            f"[Scheduler] Due schedule id={sched.get('id')} type={sched.get('task_type')} kind={sched.get('schedule_kind')}"
                        )
                    except Exception:
                        pass
                    self._dispatch_schedule(sched, now_utc)
            except Exception as exc:
                self.logger.error(f"Schedule dispatch error (id={sched.get('id')}): {exc}")

    # ---------- Evaluation helpers ----------

    def _should_run(self, sched: Dict[str, Any], now: datetime, window: timedelta) -> bool:
        """Decide if schedule should run in this tick.

        Windowed check to tolerate polling intervals. Uses UTC.
        """
        kind = (sched.get('schedule_kind') or '').lower()
        tz = (sched.get('timezone') or 'UTC').upper()
        if tz != 'UTC':
            # For v1 only UTC supported
            self.logger.warning(
                f"Schedule id={sched.get('id')} uses unsupported timezone '{tz}', treating as UTC"
            )

        last_run = self._parse_iso(sched.get('last_run_at'))
        # Prevent double-run in the same window
        if last_run and (now - last_run) < window:
            return False

        if kind == 'interval':
            interval_minutes = sched.get('interval_minutes') or 0
            if interval_minutes <= 0:
                return False
            if not last_run:
                return True  # first run
            return now >= (last_run + timedelta(minutes=int(interval_minutes)))

        # Daily/Weekly share time-of-day logic
        sched_time = sched.get('schedule_time')
        if not sched_time or len(sched_time.split(':')) != 2:
            return False
        try:
            hour, minute = [int(x) for x in sched_time.split(':')]
        except Exception:
            return False

        scheduled_dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if kind == 'daily':
            # Run if now in [scheduled_dt, scheduled_dt + window) and not already run today
            if last_run and last_run.date() == now.date():
                return False
            return 0 <= (now - scheduled_dt).total_seconds() < window.total_seconds()

        if kind == 'weekly':
            # Check weekday
            raw_days = sched.get('schedule_days')
            days: Optional[List[str]] = raw_days if isinstance(raw_days, list) else None
            # get_scheduled_tasks() already JSON-decodes schedule_days into list
            if not days:
                return False
            weekday_map = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
            today = weekday_map[now.weekday()]
            if today not in {d.lower() for d in days}:
                return False
            if last_run and last_run.date() == now.date():
                return False
            return 0 <= (now - scheduled_dt).total_seconds() < window.total_seconds()

        if kind == 'cron':
            # Not implemented in v1
            return False

        return False

    @staticmethod
    def _parse_iso(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            # Accept both with/without timezone suffix
            if value.endswith('Z'):
                value = value[:-1]
            return datetime.fromisoformat(value)
        except Exception:
            return None

    # ---------- Dispatchers ----------

    def _dispatch_schedule(self, sched: Dict[str, Any], now: datetime) -> None:
        task_type = (sched.get('task_type') or '').upper()
        sched_id = sched.get('id')
        if task_type == 'DATABASE_BACKUP':
            self._dispatch_database_backup(sched)
        elif task_type == 'QUICK_SYNC_GROUP':
            self._dispatch_quick_sync_group(sched)
        else:
            self.logger.warning(f"Unknown scheduled task_type='{task_type}' (id={sched_id})")
            return

        # Touch last_run_at; optional next_run_at can be computed later/UI-side
        conn = get_connection()
        try:
            db.touch_scheduled_task_run(
                conn,
                sched_id,
                last_run_at=now.strftime('%Y-%m-%d %H:%M:%S'),
            )
        finally:
            conn.close()

    def _dispatch_database_backup(self, sched: Dict[str, Any]) -> None:
        try:
            from services.job_queue_service import get_job_queue_service
            from services.job_types import JobType, JobPriority, JobData, create_job_with_defaults
        except Exception as exc:
            self.logger.error(f"Cannot import job queue for backup: {exc}")
            return

        # Map schedule params to backup job data
        params = sched.get('params') or {}
        job_data = JobData(
            backup_type=params.get('backup_type', 'full'),
            retention_days=params.get('retention_days', 30),
            cleanup_old=params.get('cleanup_old', False),
            force_backup=False,
            source='recurring_scheduler',
        )

        service = get_job_queue_service()
        job = create_job_with_defaults(
            JobType.DATABASE_BACKUP,
            job_data=job_data,
            priority=JobPriority.NORMAL,
        )
        job_id = service.add_job(job)
        try:
            log_message(
                f"[Scheduler] Scheduled DATABASE_BACKUP job #{job_id} (schedule id={sched.get('id')}, retention_days={job_data.get('retention_days')})"
            )
        except Exception:
            pass

    def _dispatch_quick_sync_group(self, sched: Dict[str, Any]) -> None:
        params = sched.get('params') or {}
        group_id = params.get('group_id')
        if not isinstance(group_id, int):
            self.logger.error("QUICK_SYNC_GROUP schedule missing integer group_id in params")
            return
        try:
            from services.channel_sync_service import ChannelSyncService
            service = ChannelSyncService()
            result = service.quick_sync_channel_group(group_id=group_id)
            status = result.get('status')
            if status != 'started':
                self.logger.error(f"Quick Sync group schedule failed: {result}")
            else:
                try:
                    log_message(
                        f"[Scheduler] Quick Sync group started (schedule id={sched.get('id')}, group_id={group_id}, jobs_created={result.get('jobs_created', 0)})"
                    )
                except Exception:
                    pass
        except Exception as exc:
            self.logger.error(f"Failed to dispatch QUICK_SYNC_GROUP: {exc}")


# Singleton helpers
_recurring_scheduler: Optional[RecurringSchedulerService] = None


def get_recurring_scheduler_service(*, check_interval_seconds: int = 60) -> RecurringSchedulerService:
    global _recurring_scheduler
    if _recurring_scheduler is None:
        _recurring_scheduler = RecurringSchedulerService(check_interval_seconds=check_interval_seconds)
    return _recurring_scheduler


def start_recurring_scheduler_service(*, check_interval_seconds: int = 60) -> None:
    service = get_recurring_scheduler_service(check_interval_seconds=check_interval_seconds)
    service.start()


def stop_recurring_scheduler_service() -> None:
    global _recurring_scheduler
    if _recurring_scheduler is not None:
        _recurring_scheduler.stop()


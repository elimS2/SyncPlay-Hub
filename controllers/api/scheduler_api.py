"""Scheduler API endpoints.

CRUD and actions for recurring scheduled tasks.
"""

from __future__ import annotations

import json
from typing import Optional, Dict, Any, List
from flask import Blueprint, request, jsonify

import database as db
from .shared import get_connection, log_message
from services.recurring_scheduler_service import (
    get_recurring_scheduler_service,
)


scheduler_bp = Blueprint("scheduler", __name__)


def _validate_schedule_payload(data: Dict[str, Any], is_update: bool = False) -> Optional[str]:
    required = {"name", "task_type", "schedule_kind"}
    if not is_update:
        for k in required:
            if k not in data:
                return f"Missing required field: {k}"

    kind = (data.get("schedule_kind") or "").lower()
    if kind not in {"daily", "weekly", "interval", "cron"}:
        return "Invalid schedule_kind"

    if kind in {"daily", "weekly"}:
        st = data.get("schedule_time")
        if st is None:
            return "schedule_time is required for daily/weekly"
        parts = str(st).split(":")
        if len(parts) != 2:
            return "schedule_time must be HH:MM"
        try:
            h, m = int(parts[0]), int(parts[1])
            if not (0 <= h <= 23 and 0 <= m <= 59):
                return "schedule_time out of range"
        except Exception:
            return "schedule_time must be HH:MM"
        if kind == "weekly":
            days = data.get("schedule_days")
            if not isinstance(days, list) or not days:
                return "schedule_days must be a non-empty list for weekly"

    if kind == "interval":
        interval = data.get("interval_minutes")
        if not isinstance(interval, int) or interval < 5:
            return "interval_minutes must be integer >= 5"

    # Task-specific validation
    t = (data.get("task_type") or "").upper()
    if t == "QUICK_SYNC_GROUP":
        params = data.get("params") or {}
        if not isinstance(params.get("group_id"), int):
            return "params.group_id must be integer for QUICK_SYNC_GROUP"

    return None


@scheduler_bp.route("/schedules", methods=["GET"])
def api_list_schedules():
    try:
        only_enabled = request.args.get("enabled")
        only_enabled_bool = None
        if only_enabled is not None:
            only_enabled_bool = True if only_enabled in ("1", "true", "True") else False
        task_type = request.args.get("task_type")

        conn = get_connection()
        schedules = db.get_scheduled_tasks(conn, only_enabled=only_enabled_bool, task_type=task_type)
        conn.close()
        return jsonify({"status": "ok", "schedules": schedules})
    except Exception as exc:
        log_message(f"[Scheduler API] list error: {exc}")
        return jsonify({"status": "error", "error": str(exc)}), 500


@scheduler_bp.route("/schedules", methods=["POST"])
def api_create_schedule():
    try:
        data = request.get_json() or {}
        err = _validate_schedule_payload(data, is_update=False)
        if err:
            return jsonify({"status": "error", "error": err}), 400

        conn = get_connection()
        new_id = db.create_scheduled_task(
            conn,
            name=data["name"],
            task_type=data["task_type"],
            schedule_kind=data["schedule_kind"],
            enabled=bool(data.get("enabled", True)),
            schedule_time=data.get("schedule_time"),
            schedule_days=data.get("schedule_days"),
            interval_minutes=data.get("interval_minutes"),
            cron_expr=data.get("cron_expr"),
            timezone=data.get("timezone", "UTC"),
            params=data.get("params"),
        )
        conn.close()

        log_message(f"[Scheduler API] Created schedule #{new_id} ({data.get('name')})")
        return jsonify({"status": "ok", "id": new_id})
    except Exception as exc:
        log_message(f"[Scheduler API] create error: {exc}")
        return jsonify({"status": "error", "error": str(exc)}), 500


@scheduler_bp.route("/schedules/<int:schedule_id>", methods=["GET"])
def api_get_schedule(schedule_id: int):
    try:
        conn = get_connection()
        row = db.get_scheduled_task_by_id(conn, schedule_id)
        conn.close()
        if not row:
            return jsonify({"status": "error", "error": "Schedule not found"}), 404
        item = dict(row)
        try:
            item['schedule_days'] = json.loads(item.get('schedule_days') or 'null')
        except Exception:
            item['schedule_days'] = None
        try:
            item['params'] = json.loads(item.get('params_json') or '{}')
        except Exception:
            item['params'] = {}
        return jsonify({"status": "ok", "schedule": item})
    except Exception as exc:
        log_message(f"[Scheduler API] get error: {exc}")
        return jsonify({"status": "error", "error": str(exc)}), 500


@scheduler_bp.route("/schedules/<int:schedule_id>", methods=["PATCH"])
def api_update_schedule(schedule_id: int):
    try:
        data = request.get_json() or {}
        err = _validate_schedule_payload(data, is_update=True)
        if err:
            return jsonify({"status": "error", "error": err}), 400

        update_kwargs: Dict[str, Any] = {}
        allowed = {
            'name', 'task_type', 'enabled', 'schedule_kind', 'schedule_time',
            'schedule_days', 'interval_minutes', 'cron_expr', 'timezone', 'params'
        }
        for k in allowed:
            if k in data:
                if k == 'params':
                    update_kwargs['params_json'] = json.dumps(data[k] or {})
                else:
                    update_kwargs[k] = data[k]

        conn = get_connection()
        ok = db.update_scheduled_task(conn, schedule_id, **update_kwargs)
        conn.close()
        if not ok:
            return jsonify({"status": "error", "error": "Nothing to update or schedule not found"}), 400
        return jsonify({"status": "ok"})
    except Exception as exc:
        log_message(f"[Scheduler API] update error: {exc}")
        return jsonify({"status": "error", "error": str(exc)}), 500


@scheduler_bp.route("/schedules/<int:schedule_id>", methods=["DELETE"])
def api_delete_schedule(schedule_id: int):
    try:
        conn = get_connection()
        ok = db.delete_scheduled_task(conn, schedule_id)
        conn.close()
        if not ok:
            return jsonify({"status": "error", "error": "Schedule not found"}), 404
        return jsonify({"status": "ok"})
    except Exception as exc:
        log_message(f"[Scheduler API] delete error: {exc}")
        return jsonify({"status": "error", "error": str(exc)}), 500


@scheduler_bp.route("/schedules/<int:schedule_id>/toggle", methods=["POST"])
def api_toggle_schedule(schedule_id: int):
    try:
        data = request.get_json() or {}
        enabled = bool(data.get('enabled', True))

        conn = get_connection()
        ok = db.set_scheduled_task_enabled(conn, schedule_id, enabled)
        conn.close()
        if not ok:
            return jsonify({"status": "error", "error": "Schedule not found"}), 404
        return jsonify({"status": "ok", "enabled": enabled})
    except Exception as exc:
        log_message(f"[Scheduler API] toggle error: {exc}")
        return jsonify({"status": "error", "error": str(exc)}), 500


@scheduler_bp.route("/schedules/<int:schedule_id>/run_now", methods=["POST"])
def api_run_now(schedule_id: int):
    """Trigger schedule immediately by emulating a due evaluation."""
    try:
        conn = get_connection()
        row = db.get_scheduled_task_by_id(conn, schedule_id)
        conn.close()
        if not row:
            return jsonify({"status": "error", "error": "Schedule not found"}), 404

        # Let the service dispatch this schedule on-demand
        from services.recurring_scheduler_service import RecurringSchedulerService
        service = get_recurring_scheduler_service()
        import json as _json
        sched = dict(row)
        try:
            sched['schedule_days'] = _json.loads(sched.get('schedule_days') or 'null')
        except Exception:
            sched['schedule_days'] = None
        try:
            sched['params'] = _json.loads(sched.get('params_json') or '{}')
        except Exception:
            sched['params'] = {}

        # Call internal dispatch and mark run time
        from datetime import datetime as _dt
        now = _dt.utcnow()
        RecurringSchedulerService._dispatch_schedule(service, sched, now)  # type: ignore
        return jsonify({"status": "ok", "message": "Triggered"})
    except Exception as exc:
        log_message(f"[Scheduler API] run_now error: {exc}")
        return jsonify({"status": "error", "error": str(exc)}), 500



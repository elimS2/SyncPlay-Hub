#!/usr/bin/env python3
"""
Backup API Controller

API endpoints for managing automatic database backups.
"""

from flask import Blueprint, jsonify, request
from datetime import datetime
from typing import Dict, Any

# Import services
from services.auto_backup_service import get_auto_backup_service
from services.job_queue_service import get_job_queue_service
from services.job_types import JobType, JobStatus

from .shared import log_message, get_root_dir

backup_bp = Blueprint("backup_api", __name__)


@backup_bp.route("/backup_status")
def api_backup_status():
    """Get status of automatic backup service."""
    try:
        backup_service = get_auto_backup_service()
        status = backup_service.get_status()
        
        return jsonify({
            "status": "ok",
            "auto_backup_status": status
        })
        
    except Exception as exc:
        log_message(f"Auto backup status error: {exc}")
        return jsonify({"status": "error", "message": str(exc)}), 500


@backup_bp.route("/backup_config", methods=["GET"])
def api_get_backup_config():
    """Get current backup configuration."""
    try:
        backup_service = get_auto_backup_service()
        config = {
            'enabled': backup_service.enabled,
            'schedule_time': backup_service.schedule_time,
            'retention_days': backup_service.retention_days,
            'check_interval': backup_service.check_interval
        }
        
        return jsonify({
            "status": "ok",
            "config": config
        })
        
    except Exception as exc:
        log_message(f"Get backup config error: {exc}")
        return jsonify({"status": "error", "message": str(exc)}), 500


@backup_bp.route("/backup_config", methods=["POST"])
def api_update_backup_config():
    """Update backup configuration."""
    try:
        data = request.get_json() or {}
        
        # Validate input
        valid_keys = {'enabled', 'schedule_time', 'retention_days', 'check_interval'}
        config_update = {}
        
        for key, value in data.items():
            if key not in valid_keys:
                return jsonify({
                    "status": "error", 
                    "message": f"Invalid config key: {key}"
                }), 400
            config_update[key] = value
        
        # Validate schedule_time format if provided
        if 'schedule_time' in config_update:
            try:
                time_parts = config_update['schedule_time'].split(':')
                if len(time_parts) != 2:
                    raise ValueError()
                hour, minute = map(int, time_parts)
                if not (0 <= hour <= 23 and 0 <= minute <= 59):
                    raise ValueError()
            except (ValueError, AttributeError):
                return jsonify({
                    "status": "error",
                    "message": "Invalid schedule_time format. Use HH:MM (24-hour format)"
                }), 400
        
        # Validate retention_days
        if 'retention_days' in config_update:
            if not isinstance(config_update['retention_days'], int) or config_update['retention_days'] < 1:
                return jsonify({
                    "status": "error",
                    "message": "retention_days must be a positive integer"
                }), 400
        
        # Validate check_interval
        if 'check_interval' in config_update:
            if not isinstance(config_update['check_interval'], int) or config_update['check_interval'] < 1:
                return jsonify({
                    "status": "error",
                    "message": "check_interval must be a positive integer (minutes)"
                }), 400
        
        # Update configuration
        backup_service = get_auto_backup_service()
        backup_service.update_config(config_update)
        
        log_message(f"Auto backup configuration updated: {config_update}")
        
        return jsonify({
            "status": "ok",
            "message": "Configuration updated successfully",
            "new_config": {
                'enabled': backup_service.enabled,
                'schedule_time': backup_service.schedule_time,
                'retention_days': backup_service.retention_days,
                'check_interval': backup_service.check_interval
            }
        })
        
    except Exception as exc:
        log_message(f"Update backup config error: {exc}")
        return jsonify({"status": "error", "message": str(exc)}), 500


@backup_bp.route("/backup_force", methods=["POST"])
def api_force_backup():
    """Force immediate backup creation."""
    try:
        backup_service = get_auto_backup_service()
        job_id = backup_service.force_backup_now()
        
        log_message(f"Manual backup forced with job ID: {job_id}")
        
        return jsonify({
            "status": "ok",
            "message": "Backup job scheduled successfully",
            "job_id": job_id
        })
        
    except Exception as exc:
        log_message(f"Force backup error: {exc}")
        return jsonify({"status": "error", "message": str(exc)}), 500


@backup_bp.route("/backup_jobs")
def api_backup_jobs():
    """Get list of recent backup jobs."""
    try:
        job_service = get_job_queue_service(max_workers=1)
        
        # Get recent DATABASE_BACKUP jobs
        backup_jobs = job_service.get_jobs(
            job_type=JobType.DATABASE_BACKUP,
            limit=20
        )
        
        jobs_data = []
        for job in backup_jobs:
            job_info = {
                'id': job.id,
                'status': job.status.value,
                'created_at': job.created_at.isoformat() if job.created_at else None,
                'started_at': job.started_at.isoformat() if job.started_at else None,
                'completed_at': job.completed_at.isoformat() if job.completed_at else None,
                'error_message': job.error_message,
                'retry_count': job.retry_count,
                'source': job.job_data.get('source', 'unknown')
            }
            
            # Add timing info
            if job.started_at and job.completed_at:
                duration = (job.completed_at - job.started_at).total_seconds()
                job_info['duration_seconds'] = duration
            
            jobs_data.append(job_info)
        
        return jsonify({
            "status": "ok",
            "jobs": jobs_data,
            "total_count": len(jobs_data)
        })
        
    except Exception as exc:
        log_message(f"Get backup jobs error: {exc}")
        return jsonify({"status": "error", "message": str(exc)}), 500


@backup_bp.route("/backup_job/<int:job_id>")
def api_backup_job_details(job_id: int):
    """Get detailed information about a specific backup job."""
    try:
        job_service = get_job_queue_service(max_workers=1)
        job = job_service.get_job(job_id)
        
        if not job:
            return jsonify({
                "status": "error",
                "message": "Job not found"
            }), 404
        
        if job.job_type != JobType.DATABASE_BACKUP:
            return jsonify({
                "status": "error",
                "message": "Job is not a backup job"
            }), 400
        
        job_details = {
            'id': job.id,
            'job_type': job.job_type.value,
            'status': job.status.value,
            'priority': job.priority.value,
            'created_at': job.created_at.isoformat() if job.created_at else None,
            'started_at': job.started_at.isoformat() if job.started_at else None,
            'completed_at': job.completed_at.isoformat() if job.completed_at else None,
            'error_message': job.error_message,
            'retry_count': job.retry_count,
            'max_retries': job.max_retries,
            'worker_id': job.worker_id,
            'log_file_path': job.log_file_path,
            'job_data': dict(job.job_data.items()) if job.job_data else {}
        }
        
        # Add timing info
        if job.started_at:
            if job.completed_at:
                duration = (job.completed_at - job.started_at).total_seconds()
                job_details['duration_seconds'] = duration
            else:
                # Still running
                duration = (datetime.utcnow() - job.started_at).total_seconds()
                job_details['running_seconds'] = duration
        
        return jsonify({
            "status": "ok",
            "job": job_details
        })
        
    except Exception as exc:
        log_message(f"Get backup job details error: {exc}")
        return jsonify({"status": "error", "message": str(exc)}), 500


@backup_bp.route("/backup_job/<int:job_id>/cancel", methods=["POST"])
def api_cancel_backup_job(job_id: int):
    """Cancel a pending backup job."""
    try:
        job_service = get_job_queue_service(max_workers=1)
        
        # Check if job exists and is a backup job
        job = job_service.get_job(job_id)
        if not job:
            return jsonify({
                "status": "error",
                "message": "Job not found"
            }), 404
        
        if job.job_type != JobType.DATABASE_BACKUP:
            return jsonify({
                "status": "error",
                "message": "Job is not a backup job"
            }), 400
        
        # Try to cancel the job
        success = job_service.cancel_job(job_id)
        
        if success:
            log_message(f"Backup job {job_id} cancelled successfully")
            return jsonify({
                "status": "ok",
                "message": "Job cancelled successfully"
            })
        else:
            return jsonify({
                "status": "error",
                "message": "Job could not be cancelled (may be running or already completed)"
            }), 400
        
    except Exception as exc:
        log_message(f"Cancel backup job error: {exc}")
        return jsonify({"status": "error", "message": str(exc)}), 500 
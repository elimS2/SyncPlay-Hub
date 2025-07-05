"""Jobs API endpoints."""

from pathlib import Path
from flask import Blueprint, request, jsonify
from datetime import datetime

from .shared import log_message
from services.job_queue_service import get_job_queue_service
from services.job_types import JobType, JobPriority, JobStatus

# Create blueprint
jobs_bp = Blueprint('jobs', __name__)

@jobs_bp.route("/jobs", methods=["GET"])
def api_get_jobs():
    """Get list of jobs with optional filtering."""
    try:
        # Parse query parameters
        status_filter = request.args.get('status')
        job_type_filter = request.args.get('type')
        limit = int(request.args.get('limit', 50))
        offset = int(request.args.get('offset', 0))
        
        # Convert string filters to enums
        status_enum = None
        if status_filter:
            try:
                status_enum = JobStatus(status_filter)
            except ValueError:
                return jsonify({"status": "error", "error": f"Invalid status: {status_filter}"}), 400
        
        job_type_enum = None
        if job_type_filter:
            try:
                job_type_enum = JobType(job_type_filter)
            except ValueError:
                return jsonify({"status": "error", "error": f"Invalid job type: {job_type_filter}"}), 400
        
        # Get job queue service
        service = get_job_queue_service()
        
        # Get jobs
        jobs = service.get_jobs(
            status=status_enum,
            job_type=job_type_enum,
            limit=limit,
            offset=offset
        )
        
        # Convert jobs to JSON-serializable format
        jobs_data = []
        for job in jobs:
            job_data = {
                'id': job.id,
                'job_type': job.job_type.value,
                'status': job.status.value,
                'priority': job.priority.value,
                'retry_count': job.retry_count,
                'max_retries': job.max_retries,
                'created_at': job.created_at.isoformat() if job.created_at else None,
                'started_at': job.started_at.isoformat() if job.started_at else None,
                'completed_at': job.completed_at.isoformat() if job.completed_at else None,
                'worker_id': job.worker_id,
                'timeout_seconds': job.timeout_seconds,
                'parent_job_id': job.parent_job_id,
                'error_message': job.error_message,
                'log_file_path': job.log_file_path,
                'job_data': job.job_data._data,
                'elapsed_time': job.get_elapsed_time()
            }
            jobs_data.append(job_data)
        
        # Note: Removed noisy log_message for job retrieval - too frequent for debugging value
        
        return jsonify({
            "status": "ok",
            "jobs": jobs_data,
            "count": len(jobs_data),
            "limit": limit,
            "offset": offset
        })
        
    except Exception as e:
        log_message(f"[Jobs API] Error getting jobs: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

@jobs_bp.route("/jobs/count", methods=["GET"])
def api_get_jobs_count():
    """Get count of jobs with optional filtering."""
    try:
        # Parse query parameters
        status_filter = request.args.get('status')
        job_type_filter = request.args.get('type')
        
        # Convert string filters to enums
        status_enum = None
        if status_filter:
            try:
                status_enum = JobStatus(status_filter)
            except ValueError:
                return jsonify({"status": "error", "error": f"Invalid status: {status_filter}"}), 400
        
        job_type_enum = None
        if job_type_filter:
            try:
                job_type_enum = JobType(job_type_filter)
            except ValueError:
                return jsonify({"status": "error", "error": f"Invalid job type: {job_type_filter}"}), 400
        
        # Get job queue service
        service = get_job_queue_service()
        
        # Get job count
        count = service.get_jobs_count(
            status=status_enum,
            job_type=job_type_enum
        )
        
        return jsonify({
            "status": "ok",
            "count": count
        })
        
    except Exception as e:
        log_message(f"[Jobs API] Error getting jobs count: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

@jobs_bp.route("/jobs", methods=["POST"])
def api_create_job():
    """Create a new job."""
    try:
        data = request.get_json() or {}
        
        # Validate required fields
        job_type = data.get('job_type')
        if not job_type:
            return jsonify({"status": "error", "error": "job_type is required"}), 400
        
        # Convert job_type to enum
        try:
            job_type_enum = JobType(job_type)
        except ValueError:
            return jsonify({"status": "error", "error": f"Invalid job_type: {job_type}"}), 400
        
        # Parse priority
        priority_str = data.get('priority', 'NORMAL')
        try:
            priority_enum = JobPriority[priority_str.upper()]
        except KeyError:
            return jsonify({"status": "error", "error": f"Invalid priority: {priority_str}"}), 400
        
        # Extract job parameters
        job_params = data.get('parameters', {})
        parent_job_id = data.get('parent_job_id')
        
        # Get job queue service
        service = get_job_queue_service()
        
        # Create and add job
        job_id = service.create_and_add_job(
            job_type_enum,
            priority=priority_enum,
            parent_job_id=parent_job_id,
            **job_params
        )
        
        log_message(f"[Jobs API] Created job #{job_id} (type={job_type}, priority={priority_str})")
        
        return jsonify({
            "status": "ok",
            "job_id": job_id,
            "message": f"Job created successfully"
        }), 201
        
    except Exception as e:
        log_message(f"[Jobs API] Error creating job: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

@jobs_bp.route("/jobs/<int:job_id>", methods=["GET"])
def api_get_job(job_id: int):
    """Get details of a specific job."""
    try:
        # Get job queue service
        service = get_job_queue_service()
        
        # Get job
        job = service.get_job(job_id)
        if not job:
            return jsonify({"status": "error", "error": "Job not found"}), 404
        
        # Convert to JSON-serializable format
        job_data = {
            'id': job.id,
            'job_type': job.job_type.value,
            'status': job.status.value,
            'priority': job.priority.value,
            'retry_count': job.retry_count,
            'max_retries': job.max_retries,
            'created_at': job.created_at.isoformat() if job.created_at else None,
            'started_at': job.started_at.isoformat() if job.started_at else None,
            'completed_at': job.completed_at.isoformat() if job.completed_at else None,
            'worker_id': job.worker_id,
            'timeout_seconds': job.timeout_seconds,
            'parent_job_id': job.parent_job_id,
            'error_message': job.error_message,
            'log_file_path': job.log_file_path,
            'job_data': job.job_data._data,
            'elapsed_time': job.get_elapsed_time()
        }
        
        return jsonify({
            "status": "ok",
            "job": job_data
        })
        
    except Exception as e:
        log_message(f"[Jobs API] Error getting job {job_id}: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

@jobs_bp.route("/jobs/<int:job_id>/retry", methods=["POST"])
def api_retry_job(job_id: int):
    """Retry a failed job."""
    try:
        # Get job queue service
        service = get_job_queue_service()
        
        # Get current job
        job = service.get_job(job_id)
        if not job:
            return jsonify({"status": "error", "error": "Job not found"}), 404
        
        # Check if job can be retried
        if job.status not in [JobStatus.FAILED, JobStatus.CANCELLED, JobStatus.TIMEOUT]:
            return jsonify({
                "status": "error", 
                "error": f"Job cannot be retried in status '{job.status.value}'"
            }), 400
        
        # Retry job
        success = service.retry_job(job_id)
        
        if success:
            log_message(f"[Jobs API] Retried job #{job_id}")
            return jsonify({
                "status": "ok",
                "message": f"Job #{job_id} queued for retry"
            })
        else:
            return jsonify({
                "status": "error",
                "error": "Failed to retry job"
            }), 500
        
    except Exception as e:
        log_message(f"[Jobs API] Error retrying job {job_id}: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

@jobs_bp.route("/jobs/<int:job_id>", methods=["DELETE"])
def api_cancel_job(job_id: int):
    """Cancel a pending or running job."""
    try:
        # Get job queue service
        service = get_job_queue_service()
        
        # Cancel job - now returns (success, message)
        success, message = service.cancel_job(job_id)
        
        if success:
            log_message(f"[Jobs API] Cancelled job #{job_id}: {message}")
            return jsonify({
                "status": "ok",
                "message": message
            })
        else:
            log_message(f"[Jobs API] Failed to cancel job #{job_id}: {message}")
            return jsonify({
                "status": "error",
                "error": message
            }), 400
        
    except Exception as e:
        log_message(f"[Jobs API] Error cancelling job {job_id}: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

@jobs_bp.route("/jobs/queue/status", methods=["GET"])
def api_get_queue_status():
    """Get overall job queue status and statistics."""
    try:
        # Get job queue service
        service = get_job_queue_service()
        
        # Get queue statistics
        stats = service.get_queue_stats()
        
        # Note: Removed noisy log_message for queue status - too frequent for debugging value
        
        return jsonify({
            "status": "ok",
            "queue_stats": stats
        })
        
    except Exception as e:
        log_message(f"[Jobs API] Error getting queue status: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

@jobs_bp.route("/jobs/logs/<int:job_id>", methods=["GET"])
def api_get_job_logs(job_id: int):
    """Get log content for a specific job."""
    try:
        # Get job queue service
        service = get_job_queue_service()
        
        # Get job
        job = service.get_job(job_id)
        if not job:
            return jsonify({"status": "error", "error": "Job not found"}), 404
        
        # Read log files if they exist
        logs = {}
        
        if job.log_file_path:
            log_dir = Path(job.log_file_path)
            
            log_files = {
                'job': 'job.log',
                'stdout': 'stdout.log', 
                'stderr': 'stderr.log',
                'progress': 'progress.log',
                'summary': 'summary.txt'
            }
            
            for log_type, filename in log_files.items():
                log_file = log_dir / filename
                if log_file.exists():
                    try:
                        with open(log_file, 'r', encoding='utf-8') as f:
                            logs[log_type] = f.read()
                    except Exception as e:
                        logs[log_type] = f"Error reading log: {e}"
                else:
                    logs[log_type] = "Log file not found"
        
        return jsonify({
            "status": "ok",
            "job_id": job_id,
            "logs": logs
        })
        
    except Exception as e:
        log_message(f"[Jobs API] Error getting logs for job {job_id}: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500


        return jsonify({
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500

 
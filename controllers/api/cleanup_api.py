"""Cleanup API endpoints for maintenance operations."""

import os
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify

from .shared import log_message, get_root_dir
from utils.job_logging import cleanup_old_job_logs

# Create blueprint
cleanup_bp = Blueprint('cleanup', __name__)

def _format_file_size(size_bytes):
    """Format file size in human readable format."""
    if size_bytes == 0:
        return "0 B"
    
    units = ['B', 'KB', 'MB', 'GB']
    unit_index = 0
    size = float(size_bytes)
    
    while size >= 1024.0 and unit_index < len(units) - 1:
        size /= 1024.0
        unit_index += 1
    
    return f"{size:.1f} {units[unit_index]}"

@cleanup_bp.route("/cleanup/logs", methods=["POST"])
def api_cleanup_old_logs():
    """Clean up old log files and job logs."""
    try:
        data = request.get_json() or {}
        days_to_keep = data.get('days_to_keep', 30)  # Default: keep logs for 30 days
        
        log_message(f"[Cleanup] Starting log cleanup - keeping logs for {days_to_keep} days")
        
        root_dir = get_root_dir()
        if not root_dir:
            return jsonify({"status": "error", "error": "Server configuration error"}), 500
        
        # Get base directory (parent of Playlists)
        base_dir = root_dir.parent
        logs_dir = base_dir / "Logs"
        
        files_deleted = 0
        size_freed = 0
        
        # Clean up old job logs using existing utility
        if logs_dir.exists():
            try:
                cleanup_old_job_logs(str(logs_dir), days_to_keep)
                log_message(f"[Cleanup] Job logs cleanup completed")
            except Exception as e:
                log_message(f"[Cleanup] Warning: Job logs cleanup failed: {e}")
        
        # Clean up old main log files
        if logs_dir.exists():
            cutoff_date = datetime.now() - timedelta(days=days_to_keep)
            
            for log_file in logs_dir.glob("*.log*"):
                try:
                    if log_file.is_file():
                        # Check file modification time
                        file_mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
                        
                        # Skip current main log file
                        if log_file.name == "SyncPlay-Hub.log":
                            continue
                            
                        if file_mtime < cutoff_date:
                            file_size = log_file.stat().st_size
                            log_file.unlink()
                            files_deleted += 1
                            size_freed += file_size
                            log_message(f"[Cleanup] Deleted old log: {log_file.name}")
                            
                except Exception as e:
                    log_message(f"[Cleanup] Warning: Could not delete {log_file}: {e}")
                    continue
        
        # Clean up rotated log files (*.log.1, *.log.2, etc.)
        if logs_dir.exists():
            for log_file in logs_dir.glob("*.log.*"):
                try:
                    if log_file.is_file() and log_file.suffix.replace('.', '').isdigit():
                        file_size = log_file.stat().st_size
                        log_file.unlink()
                        files_deleted += 1
                        size_freed += file_size
                        log_message(f"[Cleanup] Deleted rotated log: {log_file.name}")
                except Exception as e:
                    log_message(f"[Cleanup] Warning: Could not delete {log_file}: {e}")
                    continue
        
        formatted_size = _format_file_size(size_freed)
        
        log_message(f"[Cleanup] Log cleanup completed: {files_deleted} files deleted, {formatted_size} freed")
        
        return jsonify({
            "status": "ok",
            "message": f"Log cleanup completed successfully",
            "files_deleted": files_deleted,
            "size_freed": size_freed,
            "formatted_size": formatted_size,
            "days_kept": days_to_keep
        })
        
    except Exception as e:
        log_message(f"[Cleanup] Error during log cleanup: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

@cleanup_bp.route("/cleanup/temp", methods=["POST"])
def api_cleanup_temp_files():
    """Clean up temporary files."""
    try:
        log_message("[Cleanup] Starting temporary files cleanup")
        
        root_dir = get_root_dir()
        if not root_dir:
            return jsonify({"status": "error", "error": "Server configuration error"}), 500
        
        # Get base directory (parent of Playlists)
        base_dir = root_dir.parent
        
        files_deleted = 0
        size_freed = 0
        
        # Common temp file patterns
        temp_patterns = [
            "*.tmp",
            "*.temp",
            "*.part",
            "*.ytdl",
            "*.download",
            "*.partial",
            "*.incomplete"
        ]
        
        # Directories to search for temp files
        search_dirs = [
            base_dir / "Playlists",
            base_dir / "Downloads",
            base_dir / "Temp",
            base_dir / "Cache"
        ]
        
        for search_dir in search_dirs:
            if not search_dir.exists():
                continue
                
            log_message(f"[Cleanup] Searching for temp files in: {search_dir}")
            
            for pattern in temp_patterns:
                for temp_file in search_dir.rglob(pattern):
                    try:
                        if temp_file.is_file():
                            # Check if file is older than 1 day
                            file_mtime = datetime.fromtimestamp(temp_file.stat().st_mtime)
                            if datetime.now() - file_mtime > timedelta(days=1):
                                file_size = temp_file.stat().st_size
                                temp_file.unlink()
                                files_deleted += 1
                                size_freed += file_size
                                log_message(f"[Cleanup] Deleted temp file: {temp_file}")
                    except Exception as e:
                        log_message(f"[Cleanup] Warning: Could not delete {temp_file}: {e}")
                        continue
        
        # Clean up Python cache files
        for cache_dir in base_dir.rglob("__pycache__"):
            try:
                if cache_dir.is_dir():
                    for cache_file in cache_dir.rglob("*.pyc"):
                        try:
                            file_size = cache_file.stat().st_size
                            cache_file.unlink()
                            files_deleted += 1
                            size_freed += file_size
                        except Exception:
                            continue
                    # Try to remove empty cache directory
                    try:
                        cache_dir.rmdir()
                        log_message(f"[Cleanup] Removed empty cache directory: {cache_dir}")
                    except Exception:
                        pass
            except Exception as e:
                log_message(f"[Cleanup] Warning: Could not process cache directory {cache_dir}: {e}")
                continue
        
        formatted_size = _format_file_size(size_freed)
        
        log_message(f"[Cleanup] Temp files cleanup completed: {files_deleted} files deleted, {formatted_size} freed")
        
        return jsonify({
            "status": "ok",
            "message": f"Temporary files cleanup completed successfully",
            "files_deleted": files_deleted,
            "size_freed": size_freed,
            "formatted_size": formatted_size
        })
        
    except Exception as e:
        log_message(f"[Cleanup] Error during temp files cleanup: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

@cleanup_bp.route("/cleanup/status", methods=["GET"])
def api_cleanup_status():
    """Get information about files that can be cleaned up."""
    try:
        root_dir = get_root_dir()
        if not root_dir:
            return jsonify({"status": "error", "error": "Server configuration error"}), 500
        
        # Get base directory (parent of Playlists)
        base_dir = root_dir.parent
        logs_dir = base_dir / "Logs"
        
        # Count old log files
        old_log_files = 0
        old_log_size = 0
        
        if logs_dir.exists():
            cutoff_date = datetime.now() - timedelta(days=30)
            
            for log_file in logs_dir.glob("*.log*"):
                try:
                    if log_file.is_file() and log_file.name != "SyncPlay-Hub.log":
                        file_mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
                        if file_mtime < cutoff_date:
                            old_log_files += 1
                            old_log_size += log_file.stat().st_size
                except Exception:
                    continue
        
        # Count temp files
        temp_files = 0
        temp_size = 0
        
        temp_patterns = ["*.tmp", "*.temp", "*.part", "*.ytdl", "*.download", "*.partial", "*.incomplete"]
        search_dirs = [base_dir / "Playlists", base_dir / "Downloads", base_dir / "Temp", base_dir / "Cache"]
        
        for search_dir in search_dirs:
            if not search_dir.exists():
                continue
                
            for pattern in temp_patterns:
                for temp_file in search_dir.rglob(pattern):
                    try:
                        if temp_file.is_file():
                            file_mtime = datetime.fromtimestamp(temp_file.stat().st_mtime)
                            if datetime.now() - file_mtime > timedelta(days=1):
                                temp_files += 1
                                temp_size += temp_file.stat().st_size
                    except Exception:
                        continue
        
        return jsonify({
            "status": "ok",
            "cleanup_info": {
                "old_log_files": old_log_files,
                "old_log_size": old_log_size,
                "old_log_size_formatted": _format_file_size(old_log_size),
                "temp_files": temp_files,
                "temp_size": temp_size,
                "temp_size_formatted": _format_file_size(temp_size),
                "total_files": old_log_files + temp_files,
                "total_size": old_log_size + temp_size,
                "total_size_formatted": _format_file_size(old_log_size + temp_size)
            }
        })
        
    except Exception as e:
        log_message(f"[Cleanup] Error getting cleanup status: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500 
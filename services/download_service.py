"""Service for managing active downloads and background tasks."""

import threading
import time
from typing import Dict, List

# Global state for active downloads
ACTIVE_DOWNLOADS: Dict[str, dict] = {}
_downloads_lock = threading.Lock()

def add_active_download(task_id: str, title: str, url: str, download_type: str = "download"):
    """Add a new active download task."""
    import datetime
    
    with _downloads_lock:
        ACTIVE_DOWNLOADS[task_id] = {
            "title": title,
            "url": url,
            "type": download_type,
            "status": "starting",
            "start_time": time.time(),
            "thread_id": threading.get_ident(),
            "process_id": __import__('os').getpid(),
        }

def update_download_status(task_id: str, status: str):
    """Update the status of an active download."""
    with _downloads_lock:
        if task_id in ACTIVE_DOWNLOADS:
            ACTIVE_DOWNLOADS[task_id]["status"] = status

def remove_active_download(task_id: str):
    """Remove a download task from active list."""
    with _downloads_lock:
        ACTIVE_DOWNLOADS.pop(task_id, None)

def get_active_downloads() -> Dict[str, dict]:
    """Get dictionary of all active downloads with runtime information."""
    import datetime
    
    with _downloads_lock:
        current_time = time.time()
        downloads = {}
        
        for task_id, download in ACTIVE_DOWNLOADS.items():
            runtime_seconds = int(current_time - download["start_time"])
            runtime_str = str(datetime.timedelta(seconds=runtime_seconds))
            
            # Color coding based on status
            status_color = {
                "starting": "#4caf50",
                "initial scan": "#ff9800", 
                "scan complete": "#2196f3",
                "scanning metadata": "#9c27b0",
                "downloading": "#4caf50",
                "updating database": "#607d8b",
                "completed": "#8bc34a",
                "error": "#f44336"
            }.get(download["status"], "#757575")
            
            downloads[task_id] = {
                "title": download["title"],
                "url": download["url"],
                "type": download["type"],
                "status": download["status"],
                "status_color": status_color,
                "runtime": runtime_str,
                "thread_id": download["thread_id"],
                "process_id": download["process_id"],
            }
        
        return downloads 
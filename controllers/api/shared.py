"""Shared components for API modules."""

import re
import threading
import json
from pathlib import Path
from flask import Blueprint, request, jsonify, send_from_directory, abort

from services.playlist_service import scan_tracks, _ensure_subdir, list_playlists, set_root_dir
from services.download_service import get_active_downloads, add_active_download, update_download_status, remove_active_download
from services.streaming_service import get_streams, create_stream, get_stream, update_stream_state, add_stream_client, remove_stream_client, get_stream_state
from services.job_queue_service import get_job_queue_service
from services.job_types import JobType, JobPriority, JobStatus
from utils.logging_utils import log_message
from database import get_connection, record_event
from scan_to_db import scan as scan_library
import database as db
import queue

# Global ROOT_DIR and THUMBNAILS_DIR will be set by main app
ROOT_DIR = None
THUMBNAILS_DIR = None
YOUTUBE_THUMB_TIMEOUT = 5.0
YOUTUBE_THUMB_ORDER = ["maxresdefault.jpg", "sddefault.jpg", "hqdefault.jpg", "mqdefault.jpg", "default.jpg"]
PREVIEW_PRIORITY = ["manual", "youtube", "media"]

def get_root_dir():
    """Get current ROOT_DIR value."""
    return ROOT_DIR

def get_thumbnails_dir():
    """Get configured thumbnails directory root (may be None)."""
    return THUMBNAILS_DIR

# Global state for remote control - in a real app this would be in Redis/database
PLAYER_STATE = {
    'current_track': None,
    'playing': False,
    'volume': 1.0,
    'progress': 0,
    'playlist': [],
    'current_index': -1,
    'last_update': None,
    'player_type': None,  # 'regular' or 'virtual'
    'player_source': None,  # Track which player is active
    'like_active': False,  # Like button state for current session
    'dislike_active': False  # Dislike button state for current session
}

# Command queue for remote control
COMMAND_QUEUE = []

def init_api_controller(root_dir: Path, thumbnails_dir: Path | None = None, yt_timeout: float = 5.0, yt_order: list[str] | None = None, preview_priority: list[str] | None = None):
    """Initialize the API controller with directories."""
    global ROOT_DIR, THUMBNAILS_DIR, YOUTUBE_THUMB_TIMEOUT, YOUTUBE_THUMB_ORDER, PREVIEW_PRIORITY
    ROOT_DIR = root_dir
    THUMBNAILS_DIR = thumbnails_dir
    try:
        YOUTUBE_THUMB_TIMEOUT = float(yt_timeout) if yt_timeout else 5.0
    except Exception:
        YOUTUBE_THUMB_TIMEOUT = 5.0
    if yt_order and isinstance(yt_order, list) and yt_order:
        YOUTUBE_THUMB_ORDER = yt_order
    if preview_priority and isinstance(preview_priority, list) and preview_priority:
        # Sanitize values
        allowed = {"manual", "youtube", "media"}
        clean = [p for p in preview_priority if p in allowed]
        if clean:
            PREVIEW_PRIORITY = clean
    set_root_dir(root_dir)

def get_youtube_thumb_config():
    return YOUTUBE_THUMB_TIMEOUT, YOUTUBE_THUMB_ORDER

def get_preview_priority():
    return PREVIEW_PRIORITY

def _format_file_size(size_bytes):
    """Format file size in human readable format."""
    if size_bytes == 0:
        return "0 B"
    size_names = ["B", "KB", "MB", "GB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024
        i += 1
    return f"{size_bytes:.1f} {size_names[i]}"

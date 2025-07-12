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

# Global ROOT_DIR will be set by main app
ROOT_DIR = None

def get_root_dir():
    """Get current ROOT_DIR value."""
    return ROOT_DIR

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

def init_api_controller(root_dir: Path):
    """Initialize the API controller with root directory."""
    global ROOT_DIR
    ROOT_DIR = root_dir
    set_root_dir(root_dir)

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

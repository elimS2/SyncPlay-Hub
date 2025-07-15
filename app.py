#!/usr/bin/env python3
"""
Refactored YouTube Playlist Player - Main Application
"""

import argparse
import datetime
import os
import sys
from pathlib import Path

from flask import Flask, render_template, send_from_directory, abort, jsonify

# Import our new modules
from utils.logging_utils import init_logging, setup_logging, log_message
from services.playlist_service import list_playlists, set_root_dir
from services.download_service import get_active_downloads
from services.streaming_service import get_streams, get_stream
from controllers.api import api_bp, init_api_router
from controllers.api.trash_api import trash_bp

# Import database functions
from database import get_connection, iter_tracks_with_playlists, get_history_page, get_user_setting, set_user_setting

# Add psutil import for process checking (optional)
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    print("Warning: psutil not installed. Server duplicate detection disabled.")
    print("Install with: pip install psutil")

# Create Flask app
app = Flask(__name__)

# Global variables (will be set by main)
ROOT_DIR = None
LOGS_DIR = None
SERVER_START_TIME = None

def _get_local_ip() -> str:
    """Get local IP address for external access."""
    import socket
    try:
        # Connect to a remote address to determine local IP
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"

def _get_pid_file_path():
    """Get path to PID file for server instance tracking."""
    # Store PID file in temp directory or current directory
    return Path.cwd() / "syncplay_hub.pid"

def _write_pid_file():
    """Write current PID to file."""
    pid_file = _get_pid_file_path()
    try:
        with open(pid_file, 'w') as f:
            f.write(str(os.getpid()))
        return True
    except Exception:
        return False

def _read_pid_file():
    """Read PID from file if exists."""
    pid_file = _get_pid_file_path()
    if not pid_file.exists():
        return None
    try:
        with open(pid_file, 'r') as f:
            return int(f.read().strip())
    except (ValueError, FileNotFoundError):
        return None

def _remove_pid_file():
    """Remove PID file."""
    pid_file = _get_pid_file_path()
    try:
        pid_file.unlink(missing_ok=True)
    except Exception:
        pass

def _is_process_running(pid):
    """Check if process with given PID is running THIS specific app.py file."""
    if not pid or not PSUTIL_AVAILABLE:
        return False
    
    try:
        proc = psutil.Process(pid)
        if not proc.is_running():
            return False
        
        cmdline = proc.cmdline()
        if not cmdline:
            return False
        
        # Get the current app.py full path for comparison
        current_app_path = Path(__file__).resolve()
        
        # Check if process is running THIS specific app.py file
        for arg in cmdline:
            try:
                arg_path = Path(arg).resolve()
                if arg_path == current_app_path:
                    return True
            except (OSError, ValueError):
                continue
        
        return False
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return False

def _check_port_in_use(port):
    """Check if specified port is already in use."""
    try:
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            result = s.connect_ex(('localhost', port))
            return result == 0  # 0 means connection successful (port in use)
    except Exception:
        return False

def _check_server_already_running(port=8000):
    """Check if server is already running and display info."""
    if not PSUTIL_AVAILABLE:
        # Without psutil, only check port
        if _check_port_in_use(port):
            print("⚠️ WARNING: Port already in use!")
            print("=" * 50)
            print(f"🌐 Port {port} is being used by another process")
            print("🔍 Cannot check if it's our server (psutil not available)")
            print("💡 Install psutil for better process detection:")
            print("   pip install psutil")
            print("💡 Or manually check processes:")
            print(f"   netstat -ano | findstr :{port}")
            print("=" * 50)
            return True
        return False
    
    existing_pid = _read_pid_file()
    if existing_pid and _is_process_running(existing_pid):
        try:
            proc = psutil.Process(existing_pid)
            create_time = datetime.datetime.fromtimestamp(proc.create_time())
            uptime = datetime.datetime.now() - create_time
            uptime_str = str(uptime).split('.')[0]  # Remove microseconds
            
            # Additional check: verify this process is using the expected port
            port_in_use = _check_port_in_use(port)
            
            print("🚨 SERVER ALREADY RUNNING!")
            print("=" * 50)
            print(f"📋 Process PID: {existing_pid}")
            print(f"📁 Working directory: {proc.cwd()}")
            print(f"⏰ Started at: {create_time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"⏳ Uptime: {uptime_str}")
            print(f"💾 Memory: {proc.memory_info().rss / 1024 / 1024:.1f} MB")
            print(f"🌐 Port {port}: {'🔴 IN USE' if port_in_use else '🟢 available'}")
            print(f"🔗 Command line: {' '.join(proc.cmdline())}")
            print("=" * 50)
            print("❌ New server startup cancelled.")
            print("💡 To stop the running server use:")
            print(f"   taskkill /PID {existing_pid} /F")
            print("   or go to web interface and click 'Stop Server'")
            return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            # Process no longer exists, remove stale PID file
            _remove_pid_file()
            return False
    
    # If no PID file but port is in use, check if it might be our server
    if _check_port_in_use(port):
        print("⚠️ WARNING: Port already in use!")
        print("=" * 50)
        print(f"🌐 Port {port} is being used by another process")
        print("🔍 Possibly a server running without PID file")
        print("💡 Check processes manually:")
        print(f"   netstat -ano | findstr :{port}")
        print("=" * 50)
        return True
    
    # Clean up stale PID file if process is not running
    if existing_pid:
        _remove_pid_file()
    
    return False

# -------- PAGE ROUTES --------

@app.route("/")
@app.route("/playlists")
def playlists_page():
    """Homepage – list all playlists (sub-folders)."""
    playlists = list_playlists(ROOT_DIR)
    
    # Calculate uptime
    uptime = datetime.datetime.now() - SERVER_START_TIME
    uptime_str = str(uptime).split('.')[0]  # Remove microseconds
    
    server_info = {
        "pid": os.getpid(),
        "start_time": SERVER_START_TIME.strftime("%Y-%m-%d %H:%M:%S"),
        "current_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "uptime": uptime_str
    }
    active_downloads = get_active_downloads()
    return render_template("playlists.html", playlists=playlists, server_ip=_get_local_ip(), 
                          server_info=server_info, active_downloads=active_downloads)

@app.route("/playlist/<path:playlist_path>")
def playlist_page(playlist_path: str):
    """Playlist view – identical to previous homepage."""
    # validate path
    from services.playlist_service import _ensure_subdir
    _ensure_subdir(Path(playlist_path))
    return render_template("index.html", server_ip=_get_local_ip(), 
                          playlist_rel=playlist_path, playlist_name=Path(playlist_path).name)

@app.route("/tracks")
def tracks_page():
    """DB Tracks Page with optional search functionality."""
    from flask import request
    search_query = request.args.get("search", "").strip()
    include_deleted = request.args.get("include_deleted") == "1"
    
    conn = get_connection()
    tracks = list(iter_tracks_with_playlists(conn, search_query if search_query else None, include_deleted))
    conn.close()
    
    # Calculate uptime for server info
    uptime = datetime.datetime.now() - SERVER_START_TIME
    uptime_str = str(uptime).split('.')[0]  # Remove microseconds
    
    server_info = {
        "pid": os.getpid(),
        "start_time": SERVER_START_TIME.strftime("%Y-%m-%d %H:%M:%S"),
        "current_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "uptime": uptime_str
    }
    
    return render_template("tracks.html", tracks=tracks, search_query=search_query, 
                         include_deleted=include_deleted, server_info=server_info)

@app.route("/history")
@app.route("/events")
def events_page():
    """Events Page (formerly History Page) with server-side filtering."""
    from flask import request
    page = int(request.args.get("page", 1))
    
    # Get filter parameters from URL
    event_types_param = request.args.get("event_types")  # None if not present
    track_filter = request.args.get("track_filter", "").strip()
    video_id_filter = request.args.get("video_id_filter", "").strip()
    
    # Parse event types (comma-separated)
    event_types = None
    if event_types_param is not None:  # Parameter exists (could be empty)
        if event_types_param.strip():  # Parameter has content
            event_types = [t.strip() for t in event_types_param.split(",") if t.strip()]
        else:  # Parameter is empty - show no events
            event_types = []
    
    # Convert empty strings to None for database function
    track_filter = track_filter if track_filter else None
    video_id_filter = video_id_filter if video_id_filter else None
    
    conn = get_connection()
    rows, has_next = get_history_page(
        conn, 
        page=page, 
        per_page=1000,
        event_types=event_types,
        track_filter=track_filter,
        video_id_filter=video_id_filter
    )
    rows = [dict(r) for r in rows]
    conn.close()
    
    # Pass filter parameters to template for maintaining state
    filter_params = {
        'event_types': event_types if event_types is not None else None,
        'event_types_filter_applied': event_types is not None,
        'track_filter': track_filter or '',
        'video_id_filter': video_id_filter or ''
    }
    
    # Calculate uptime for server info
    uptime = datetime.datetime.now() - SERVER_START_TIME
    uptime_str = str(uptime).split('.')[0]  # Remove microseconds
    server_info = {
        'pid': os.getpid(),
        'start_time': SERVER_START_TIME.strftime('%Y-%m-%d %H:%M:%S'),
        'current_time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'uptime': uptime_str
    }
    
    return render_template("history.html", history=rows, page=page, has_next=has_next, filters=filter_params, request=request, server_info=server_info)

@app.route("/backups")
def backups_page():
    """Database Backups Page."""
    # Calculate uptime for server info
    uptime = datetime.datetime.now() - SERVER_START_TIME
    uptime_str = str(uptime).split('.')[0]  # Remove microseconds
    server_info = {
        'pid': os.getpid(),
        'start_time': SERVER_START_TIME.strftime('%Y-%m-%d %H:%M:%S'),
        'current_time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'uptime': uptime_str
    }
    
    return render_template("backups.html", server_info=server_info)

@app.route("/favicon.ico")
def favicon():
    """Serve favicon."""
    return send_from_directory(os.path.join(app.root_path, 'static'), 'favicon.ico', mimetype='image/vnd.microsoft.icon')

@app.route("/media/<path:filename>")
def media(filename: str):
    """Serve media files."""
    return send_from_directory(ROOT_DIR, filename, as_attachment=False)

def _list_log_files():
    """Return sorted list of *.log paths inside LOGS_DIR (main log first, then newest first)."""
    if not LOGS_DIR:
        return []
    
    all_logs = list(LOGS_DIR.glob("*.log"))
    main_log = LOGS_DIR / "SyncPlay-Hub.log"
    
    # Separate main log from others
    main_logs = [log for log in all_logs if log.name == "SyncPlay-Hub.log"]
    other_logs = [log for log in all_logs if log.name != "SyncPlay-Hub.log"]
    
    # Sort others by modification time (newest first)
    other_logs_sorted = sorted(other_logs, key=lambda p: p.stat().st_mtime, reverse=True)
    
    # Return main log first, then others
    return main_logs + other_logs_sorted

@app.route("/logs")
def logs_page():
    """Show available log files."""
    log_files = _list_log_files()
    logs_info = []
    
    for log_path in log_files:
        try:
            stat = log_path.stat()
            logs_info.append({
                'name': log_path.name,
                'size_bytes': stat.st_size,
                'size_human': _format_file_size(stat.st_size),
                'modified_timestamp': stat.st_mtime,
                'modified_date': datetime.datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                'is_main': log_path.name == "SyncPlay-Hub.log"
            })
        except OSError:
            # Skip files that can't be accessed
            continue
    
    return render_template("logs.html", logs=logs_info)

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

@app.route("/log/<path:log_name>")
def log_view(log_name: str):
    """View log file with live streaming."""
    # Security checks like original
    if ".." in log_name or "/" in log_name or not log_name.endswith(".log"):
        abort(404)
    
    log_path = LOGS_DIR / log_name
    if not log_path.exists() or not log_path.is_file():
        abort(404)
    
    return render_template("log_view.html", log_name=log_name)

@app.route("/stream_log/<path:log_name>")
def stream_log(log_name: str):
    """Stream log file content via Server-Sent Events with tail functionality."""
    import time
    from collections import deque
    from flask import Response
    
    # Security checks like original
    if "/" in log_name or ".." in log_name or not log_name.endswith(".log"):
        abort(404)
    
    log_path = LOGS_DIR / log_name
    if not log_path.exists() or not log_path.is_file():
        abort(404)
    
    def generate():
        # Send last 200 lines first (like tail)
        try:
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                last_lines = deque(f, maxlen=200)
                for line in last_lines:
                    yield f"data: {line.rstrip()}\n\n"

                # Follow file for new content
                f.seek(0, 2)  # move to end
                while True:
                    line = f.readline()
                    if line:
                        yield f"data: {line.rstrip()}\n\n"
                    else:
                        time.sleep(1)
        except GeneratorExit:
            return
        except Exception:
            yield f"data: Error reading log file\n\n"
    
    return Response(generate(), mimetype="text/event-stream")

@app.route("/static_log/<path:log_name>")
def static_log(log_name: str):
    """Serve log file as plain text."""
    # Security checks like original
    if "/" in log_name or ".." in log_name or not log_name.endswith(".log"):
        abort(404)
    
    log_path = LOGS_DIR / log_name
    if not log_path.exists() or not log_path.is_file():
        abort(404)
    
    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        
        from flask import Response
        return Response(content, mimetype="text/plain; charset=utf-8")
    except Exception:
        abort(500)

@app.route("/streams")
def streams_page():
    """Streams Page."""
    return render_template("streams.html", streams=get_streams())

@app.route("/stream/<stream_id>")
def stream_page(stream_id: str):
    """Stream view."""
    stream = get_stream(stream_id)
    if not stream:
        abort(404)
    return render_template("stream_view.html", stream=stream, stream_id=stream_id)

@app.route("/files")
def files_page():
    """File browser page."""
    return render_template("files.html")

@app.route("/remote")
def remote_page():
    """Mobile remote control page."""
    return render_template("remote.html", server_ip=_get_local_ip())

@app.route("/channels")
def channels_page():
    """Channel management page."""
    return render_template("channels.html")

@app.route("/deleted")
def deleted_tracks_page():
    """Deleted tracks restoration page."""
    # Calculate uptime for server info
    uptime = datetime.datetime.now() - SERVER_START_TIME
    uptime_str = str(uptime).split('.')[0]  # Remove microseconds
    server_info = {
        'pid': os.getpid(),
        'start_time': SERVER_START_TIME.strftime('%Y-%m-%d %H:%M:%S'),
        'current_time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'uptime': uptime_str
    }
    
    return render_template("deleted.html", server_info=server_info)

@app.route("/jobs")
def jobs_page():
    """Job Queue management page."""
    return render_template("jobs.html")

@app.route("/settings", methods=['GET', 'POST'])
def settings_page():
    """Settings management page."""
    from flask import request, redirect, url_for, flash
    
    # Load environment config
    env_config = _load_env_config()
    
    # Calculate uptime for server info
    uptime = datetime.datetime.now() - SERVER_START_TIME
    uptime_str = str(uptime).split('.')[0]  # Remove microseconds
    server_info = {
        'pid': os.getpid(),
        'start_time': SERVER_START_TIME.strftime('%Y-%m-%d %H:%M:%S'),
        'current_time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'uptime': uptime_str
    }
    
    if request.method == 'POST':
        try:
            # Get delay value from form
            delay_seconds = int(request.form.get('job_execution_delay_seconds', 0))
            
            # Validate delay (0 to 86400 seconds = 24 hours)
            if delay_seconds < 0 or delay_seconds > 86400:
                raise ValueError("Delay must be between 0 and 86400 seconds (24 hours)")
            
            # Save setting to database
            conn = get_connection()
            set_user_setting(conn, 'job_execution_delay_seconds', str(delay_seconds))
            conn.close()
            
            log_message(f"Settings updated: job_execution_delay_seconds = {delay_seconds}")
            return redirect(url_for('settings_page'))
            
        except ValueError as e:
            log_message(f"Settings validation error: {e}")
            return render_template("settings.html", error=str(e), delay_seconds=request.form.get('job_execution_delay_seconds', 0), env_config=env_config, server_info=server_info)
        except Exception as e:
            log_message(f"Settings save error: {e}")
            return render_template("settings.html", error="Failed to save settings", delay_seconds=request.form.get('job_execution_delay_seconds', 0), env_config=env_config, server_info=server_info)
    
    # GET request - load current settings
    try:
        conn = get_connection()
        delay_seconds = get_user_setting(conn, 'job_execution_delay_seconds', '0')
        conn.close()
        return render_template("settings.html", delay_seconds=int(delay_seconds), env_config=env_config, server_info=server_info)
    except Exception as e:
        log_message(f"Settings load error: {e}")
        return render_template("settings.html", delay_seconds=0, error="Failed to load settings", env_config=env_config, server_info=server_info)

@app.route("/maintenance")
def maintenance_page():
    """System maintenance page."""
    # Calculate uptime for server info
    uptime = datetime.datetime.now() - SERVER_START_TIME
    uptime_str = str(uptime).split('.')[0]  # Remove microseconds
    server_info = {
        'pid': os.getpid(),
        'start_time': SERVER_START_TIME.strftime('%Y-%m-%d %H:%M:%S'),
        'current_time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'uptime': uptime_str
    }
    
    return render_template("maintenance.html", server_info=server_info)

@app.route("/likes")
def likes_playlists_page():
    """Virtual playlists by likes page."""
    return render_template("likes_playlists.html")

@app.route("/likes_player/<int:like_count>")
def likes_player_page(like_count: int):
    """Player page for virtual playlist by like count."""
    return render_template("likes_player.html", like_count=like_count)

# Register API blueprints
app.register_blueprint(api_bp)
app.register_blueprint(trash_bp, url_prefix='/api')

def _load_env_config():
    """Load configuration from .env file."""
    config = {}
    env_path = Path(__file__).parent / '.env'
    
    if env_path.exists():
        try:
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip().lstrip('\ufeff')  # Remove BOM
                    if line and '=' in line and not line.startswith('#'):
                        key, value = line.split('=', 1)
                        config[key.strip()] = value.strip()
        except Exception as e:
            print(f"Warning: Failed to load .env file: {e}")
    
    return config

@app.route("/api/server_info")
def get_server_info():
    """API endpoint to get current server information for dynamic updates."""
    uptime = datetime.datetime.now() - SERVER_START_TIME
    uptime_str = str(uptime).split('.')[0]  # Remove microseconds
    
    server_info = {
        "pid": os.getpid(),
        "start_time": SERVER_START_TIME.strftime("%Y-%m-%d %H:%M:%S"),
        "current_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "uptime": uptime_str
    }
    
    return jsonify(server_info)

def main():
    """Main entry point."""
    global ROOT_DIR, LOGS_DIR, SERVER_START_TIME
    
    # Load configuration from .env file
    env_config = _load_env_config()
    
    parser = argparse.ArgumentParser(description="YouTube Playlist Player")
    parser.add_argument("--root", type=Path, default=Path.cwd() / "downloads", help="Root directory for playlists")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    parser.add_argument("--logs", type=Path, help="Logs directory (default: root/Logs)")
    parser.add_argument("--force", action="store_true", help="Force start even if server already running")
    args = parser.parse_args()
    
    # Check if server is already running (unless --force is used)
    if not args.force and _check_server_already_running(args.port):
        sys.exit(1)

    # Parse arguments like original web_player.py
    BASE_DIR = args.root.resolve()
    PLAYLISTS_DIR = BASE_DIR / "Playlists"
    DB_DIR = BASE_DIR / "DB"
    
    # Validate structure like original
    if not PLAYLISTS_DIR.exists():
        raise SystemExit(f"Playlists folder '{PLAYLISTS_DIR}' not found (expected inside base dir)")
    DB_DIR.mkdir(parents=True, exist_ok=True)
    
    # Set ROOT_DIR to PLAYLISTS_DIR like original!
    ROOT_DIR = PLAYLISTS_DIR
    LOGS_DIR = args.logs or (BASE_DIR / "Logs")
    SERVER_START_TIME = datetime.datetime.now()
    
    # Ensure directories exist
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Set database path - use DB_PATH from .env file if available, otherwise use default
    from database import set_db_path
    db_path_from_env = env_config.get('DB_PATH')
    if db_path_from_env:
        db_path = Path(db_path_from_env)
        print(f"Using database path from .env: {db_path}")
    else:
        db_path = DB_DIR / "tracks.db"
        print(f"Using default database path: {db_path}")
    
    set_db_path(db_path)
    
    # Initialize logging
    init_logging(LOGS_DIR, os.getpid(), SERVER_START_TIME)
    setup_logging()
    
    # Initialize services
    set_root_dir(ROOT_DIR)
    init_api_router(ROOT_DIR)
    
    # Make LOGS_DIR available globally for API controller
    from utils.logging_utils import set_logs_dir
    set_logs_dir(LOGS_DIR)
    
    # Start auto-delete service for channel management
    from services.auto_delete_service import start_auto_delete_service
    start_auto_delete_service(ROOT_DIR)
    
    # Start auto backup service for daily database backups
    from services.auto_backup_service import start_auto_backup_service
    backup_config = {
        'enabled': True,
        'schedule_time': "02:00",  # 2 AM UTC
        'retention_days': 30,
        'check_interval': 60  # Check every hour
    }
    start_auto_backup_service(backup_config)
    
    # Initialize and start Job Queue Service
    from services.job_queue_service import get_job_queue_service
    from services.job_workers import ChannelDownloadWorker, MetadataExtractionWorker, CleanupWorker, PlaylistDownloadWorker, BackupWorker, QuickSyncWorker
    
    # Force reload the single video metadata worker to ensure latest code
    import importlib
    import services.job_workers.single_video_metadata_worker
    importlib.reload(services.job_workers.single_video_metadata_worker)
    from services.job_workers.single_video_metadata_worker import SingleVideoMetadataWorker
    
    try:
        # Use only 1 worker to prevent parallel execution issues
        job_service = get_job_queue_service(max_workers=1)
        
        # Register workers
        job_service.register_worker(ChannelDownloadWorker())
        job_service.register_worker(MetadataExtractionWorker())
        job_service.register_worker(CleanupWorker())
        job_service.register_worker(PlaylistDownloadWorker())
        job_service.register_worker(BackupWorker())
        job_service.register_worker(SingleVideoMetadataWorker())
        job_service.register_worker(QuickSyncWorker())
        
        # Start the service
        job_service.start()
        log_message("Job Queue Service started successfully")
        
    except Exception as e:
        log_message(f"Warning: Failed to start Job Queue Service: {e}")
    
    # Write PID file to track this server instance
    if not _write_pid_file():
        log_message("Warning: Could not create PID file")
    
    # Log startup
    log_message(f"Starting server PID {os.getpid()} at {SERVER_START_TIME.strftime('%Y-%m-%d %H:%M:%S')}")
    log_message(f"Root directory: {ROOT_DIR}")
    log_message(f"Logs directory: {LOGS_DIR}")
    if not db_path.exists():
        log_message(f"Warning: Database not found at {db_path}")
    else:
        log_message(f"Using existing database: {db_path}")
    
    # Start Flask app
    try:
        app.run(host=args.host, port=args.port, debug=False)
    except KeyboardInterrupt:
        log_message("Server stopped by user")
    except Exception as e:
        log_message(f"Server error: {e}")
    finally:
        # Stop auto-delete service
        from services.auto_delete_service import stop_auto_delete_service
        stop_auto_delete_service()
        
        # Stop auto backup service
        from services.auto_backup_service import stop_auto_backup_service
        stop_auto_backup_service()
        
        # Stop Job Queue Service
        try:
            job_service = get_job_queue_service(max_workers=1)
            job_service.stop()
            log_message("Job Queue Service stopped successfully")
        except Exception as e:
            log_message(f"Warning: Error stopping Job Queue Service: {e}")
        
        # Clean up PID file on exit
        _remove_pid_file()
        log_message(f"Server PID {os.getpid()} shutdown complete")

if __name__ == "__main__":
    main() 
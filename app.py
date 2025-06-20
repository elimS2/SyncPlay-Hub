#!/usr/bin/env python3
"""
Refactored YouTube Playlist Player - Main Application
"""

import argparse
import datetime
import os
import sys
from pathlib import Path

from flask import Flask, render_template, send_from_directory, abort

# Import our new modules
from utils.logging_utils import init_logging, setup_logging, log_message
from services.playlist_service import list_playlists, set_root_dir
from services.download_service import get_active_downloads
from services.streaming_service import get_streams, get_stream
from controllers.api_controller import api_bp, init_api_controller

# Import database functions
from database import get_connection, iter_tracks_with_playlists, get_history_page

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

# -------- PAGE ROUTES --------

@app.route("/")
def playlists_page():
    """Homepage – list all playlists (sub-folders)."""
    playlists = list_playlists(ROOT_DIR)
    
    # Calculate uptime
    uptime = datetime.datetime.now() - SERVER_START_TIME
    uptime_str = str(uptime).split('.')[0]  # Remove microseconds
    
    server_info = {
        "pid": os.getpid(),
        "start_time": SERVER_START_TIME.strftime("%Y-%m-%d %H:%M:%S"),
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
    """DB Tracks Page."""
    conn = get_connection()
    tracks = list(iter_tracks_with_playlists(conn))
    conn.close()
    return render_template("tracks.html", tracks=tracks)

@app.route("/history")
def history_page():
    """History Page."""
    from flask import request
    page = int(request.args.get("page", 1))
    conn = get_connection()
    rows, has_next = get_history_page(conn, page=page, per_page=1000)
    rows = [dict(r) for r in rows]
    conn.close()
    return render_template("history.html", history=rows, page=page, has_next=has_next)

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
    """Streams page."""
    streams = get_streams()
    return render_template("streams.html", streams=streams)

@app.route("/stream/<stream_id>")
def stream_page(stream_id: str):
    """Stream view page."""
    stream = get_stream(stream_id)
    if not stream:
        abort(404)
    return render_template("stream_view.html", stream_id=stream_id, stream_title=stream.get("title", "Stream"), server_ip=_get_local_ip())

# Register API blueprint
app.register_blueprint(api_bp)

def main():
    """Main entry point."""
    global ROOT_DIR, LOGS_DIR, SERVER_START_TIME
    
    parser = argparse.ArgumentParser(description="YouTube Playlist Player")
    parser.add_argument("--root", type=Path, default=Path.cwd() / "downloads", help="Root directory for playlists")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    parser.add_argument("--logs", type=Path, help="Logs directory (default: root/Logs)")
    args = parser.parse_args()

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
    
    # Set database path to existing DB/tracks.db (original structure)
    from database import set_db_path
    db_path = DB_DIR / "tracks.db"
    set_db_path(db_path)
    
    # Initialize logging
    init_logging(LOGS_DIR, os.getpid(), SERVER_START_TIME)
    setup_logging()
    
    # Initialize services
    set_root_dir(ROOT_DIR)
    init_api_controller(ROOT_DIR)
    
    # Make LOGS_DIR available globally for API controller
    from utils.logging_utils import set_logs_dir
    set_logs_dir(LOGS_DIR)
    
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

if __name__ == "__main__":
    main() 
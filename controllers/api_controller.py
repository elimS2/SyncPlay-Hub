"""API endpoints controller."""

import re
import threading
import json
from pathlib import Path
from flask import Blueprint, request, jsonify, send_from_directory, abort

from services.playlist_service import scan_tracks, _ensure_subdir, list_playlists, set_root_dir
from services.download_service import get_active_downloads, add_active_download, update_download_status, remove_active_download
from services.streaming_service import get_streams, create_stream, get_stream, update_stream_state, add_stream_client, remove_stream_client, get_stream_state
from utils.logging_utils import log_message
from database import get_connection, record_event
from scan_to_db import scan as scan_library
import database as db
import queue

# Create blueprint
api_bp = Blueprint('api', __name__, url_prefix='/api')

# Global ROOT_DIR will be set by main app
ROOT_DIR = None

# Global state for remote control - in a real app this would be in Redis/database
PLAYER_STATE = {
    'current_track': None,
    'playing': False,
    'volume': 1.0,
    'progress': 0,
    'playlist': [],
    'current_index': -1,
    'last_update': None
}

# Command queue for remote control
COMMAND_QUEUE = []

def init_api_controller(root_dir: Path):
    """Initialize the API controller with root directory."""
    global ROOT_DIR
    ROOT_DIR = root_dir
    set_root_dir(root_dir)

@api_bp.route("/tracks", defaults={"subpath": ""})
@api_bp.route("/tracks/<path:subpath>")
def api_tracks(subpath: str):
    """Get tracks from a directory."""
    base_dir = _ensure_subdir(Path(subpath)) if subpath else ROOT_DIR
    tracks = scan_tracks(base_dir)
    return jsonify(tracks)

@api_bp.route("/playlists")
def api_playlists():
    """Get list of all playlists."""
    return jsonify(list_playlists(ROOT_DIR))

@api_bp.route("/active_downloads")
def api_active_downloads():
    """Get current active downloads status."""
    return jsonify(get_active_downloads())

@api_bp.route("/scan", methods=["POST"])
def api_scan():
    """Scan Playlists directory and update database."""
    try:
        scan_library(ROOT_DIR)
        return jsonify({"status": "ok"})
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500

@api_bp.route("/backup", methods=["POST"])
def api_backup():
    """Create database backup."""
    try:
        from database import create_backup
        result = create_backup(ROOT_DIR)
        
        if result['success']:
            log_message(f"Database backup created: {result['backup_folder']}")
            return jsonify({
                "status": "ok", 
                "backup_path": result['backup_path'],
                "timestamp": result['timestamp'],
                "size_bytes": result['size_bytes']
            })
        else:
            log_message(f"Database backup failed: {result['error']}")
            return jsonify({
                "status": "error", 
                "message": result['error']
            }), 500
            
    except Exception as exc:
        log_message(f"Database backup error: {exc}")
        return jsonify({"status": "error", "message": str(exc)}), 500

@api_bp.route("/backups")
def api_backups():
    """Get list of all database backups."""
    try:
        from database import list_backups
        backups = list_backups(ROOT_DIR)
        return jsonify({"status": "ok", "backups": backups})
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500

@api_bp.route("/event", methods=["POST"])
def api_event():
    """Record playback events."""
    data = {}  # fallback
    try:
        from flask import current_app
        data = current_app.request_json_cache if hasattr(current_app, 'request_json_cache') else None
    except Exception:
        pass
    if not data:
        data = request.get_json(force=True, silent=True) or {}
    
    video_id = data.get("video_id")
    ev = data.get("event")
    pos = data.get("position")
    if not video_id or ev not in {"start", "finish", "next", "prev", "like", "play", "pause"}:
        return jsonify({"status": "error", "message": "bad payload"}), 400
    
    conn = get_connection()
    record_event(conn, video_id, ev, position=pos)
    conn.close()
    return jsonify({"status": "ok"})

@api_bp.route("/add_playlist", methods=["POST"])
def api_add_playlist():
    """Receive a YouTube playlist URL and start background download if not present."""
    payload = request.get_json(force=True, silent=True) or {}
    url = (payload.get("url") or "").strip()
    if not url:
        return jsonify({"status": "error", "message": "missing url"}), 400

    # Extract playlist ID quickly to sanity-check the URL
    m = re.search(r"list=([A-Za-z0-9_-]+)", url)
    if not m:
        return jsonify({"status": "error", "message": "not a playlist url"}), 400

    # Log immediate start of playlist processing
    log_message(f"[AddPlaylist] Received request for URL: {url}")
    
    # Import here to avoid heavy deps on start-up
    from download_playlist import fetch_playlist_metadata, download_playlist as _dl_playlist
    from yt_dlp.utils import sanitize_filename

    # Background worker to download and rescan DB
    def _worker():
        import contextlib, datetime, sys
        import uuid
        
        # Generate unique task ID
        task_id = uuid.uuid4().hex[:8]
        
        try:
            # Register initial task with placeholder title
            add_active_download(task_id, "Fetching metadata...", url, "download")
            
            # Fetch metadata first (this was moved from main thread)
            log_message(f"[AddPlaylist] Fetching playlist metadata... | Task ID: {task_id}")
            
            # Create callback for metadata fetching progress
            def metadata_progress_callback(msg):
                if any(keyword in msg for keyword in ["[Info]", "[Warning]", "[Progress]"]):
                    log_message(f"[AddPlaylist] {msg}")
                # Update status for specific progress messages
                if "Quick scan in progress" in msg:
                    update_download_status(task_id, "initial scan")
                elif "Quick scan completed" in msg:
                    update_download_status(task_id, "scan complete")
            
            title, _ids = fetch_playlist_metadata(url, debug=False, progress_callback=metadata_progress_callback)
            log_message(f"[AddPlaylist] Metadata fetched successfully: {title} | Task ID: {task_id}")
            
            folder_name = sanitize_filename(title, restricted=True)
            target_dir = ROOT_DIR / folder_name
            
            # Check if already exists
            if target_dir.exists():
                log_message(f"[AddPlaylist] Playlist already exists: {title} | Task ID: {task_id}")
                remove_active_download(task_id)
                return
            
            # Update task with real title
            from services.download_service import _downloads_lock, ACTIVE_DOWNLOADS
            with _downloads_lock:
                if task_id in ACTIVE_DOWNLOADS:
                    ACTIVE_DOWNLOADS[task_id]["title"] = title
                    ACTIVE_DOWNLOADS[task_id]["status"] = "preparing"
            
            # ensure playlist row has source_url set
            try:
                from database import get_connection  # local import
                from database import upsert_playlist  # local import
                conn = get_connection()
                relpath = str(folder_name)
                upsert_playlist(conn, title, relpath, source_url=url)
                conn.commit()
                conn.close()
            except Exception:
                pass
            
        except Exception as exc:
            log_message(f"[AddPlaylist] Metadata error: {exc} | Task ID: {task_id}")
            update_download_status(task_id, "error")
            import time
            time.sleep(5)  # Keep error visible for 5 seconds
            remove_active_download(task_id)
            return
        
        from utils.logging_utils import LOGS_DIR
        LOGS_DIR_LOCAL = LOGS_DIR or (Path.cwd() / "Logs")
        log_path = LOGS_DIR_LOCAL / "download_playlist.log"
        LOGS_DIR_LOCAL.mkdir(parents=True, exist_ok=True)
        
        # Log start to both main server log and download log
        start_msg = f"[AddPlaylist] Starting download: {title} | URL: {url} | Task ID: {task_id} | Logging to {log_path}"
        log_message(start_msg)  # Main server log
        
        with open(log_path, "a", encoding="utf-8", buffering=1) as lf:
            # Custom print function that writes to both file and main log
            def dual_print(msg, flush=True):
                # Write to download log file
                print(msg, file=lf, flush=flush)
                # Also log important messages to main server log
                if any(keyword in msg for keyword in ["[START]", "[DONE]", "[ERROR]", "[Info] Playlist contains", "[Info] Detailed scan completed"]):
                    log_message(f"[AddPlaylist] {msg}")
            
            # Redirect stdout/stderr to file only, but keep dual logging for important messages
            with contextlib.redirect_stdout(lf), contextlib.redirect_stderr(lf):
                dual_print("="*60)
                dual_print(f"[START] {datetime.datetime.now():%Y-%m-%d %H:%M:%S} | Playlist: {title} | URL: {url}")
                try:
                    # Update status to downloading
                    update_download_status(task_id, "downloading")
                    
                    # Create callback to send progress to main log
                    def progress_callback(msg):
                        # Log important progress messages to main server log
                        if any(keyword in msg for keyword in ["[Info]", "[Warning]", "[Summary]", "[Progress]"]):
                            log_message(f"[AddPlaylist] {msg}")
                        # Update status based on progress
                        if "Starting detailed metadata scan" in msg:
                            update_download_status(task_id, "scanning metadata")
                        elif "Detailed scan completed" in msg:
                            update_download_status(task_id, "downloading files")
                    
                    _dl_playlist(url, ROOT_DIR, audio_only=False, sync=True, debug=False, progress_callback=progress_callback)
                    
                    # Update status to finalizing
                    update_download_status(task_id, "updating database")
                    
                    # Update DB after download
                    from scan_to_db import scan as scan_library  # local import
                    scan_library(ROOT_DIR)
                    success_msg = f"[DONE]  {datetime.datetime.now():%Y-%m-%d %H:%M:%S}  Successfully downloaded {title}"
                    dual_print(success_msg)
                    
                    # Mark as completed
                    update_download_status(task_id, "completed")
                    
                except Exception as e:
                    error_msg = f"[ERROR] {datetime.datetime.now():%Y-%m-%d %H:%M:%S}  {e}"
                    dual_print(error_msg)
                    update_download_status(task_id, "error")
                finally:
                    dual_print("="*60)
                    # Remove from active downloads after a short delay
                    import time
                    time.sleep(5)  # Keep visible for 5 seconds after completion
                    remove_active_download(task_id)

    threading.Thread(target=_worker, daemon=True).start()
    return jsonify({"status": "started"})

@api_bp.route("/resync", methods=["POST"])
def api_resync():
    """Resync an existing playlist."""
    data = request.get_json(force=True, silent=True) or {}
    relpath = (data.get("relpath") or "").strip()
    if not relpath:
        return jsonify({"status": "error", "message": "missing relpath"}), 400

    conn = get_connection()
    row = db.get_playlist_by_relpath(conn, relpath)
    conn.close()
    if not row:
        return jsonify({"status": "error", "message": "playlist not found"}), 404
    url = row["source_url"]
    if not url:
        return jsonify({"status": "error", "message": "source url not stored for playlist"}), 400

    # Kick off same worker logic but using existing folder name
    folder_name = relpath

    def _worker():
        import contextlib, datetime
        import uuid
        
        # Generate unique task ID
        task_id = uuid.uuid4().hex[:8]
        
        # Register this resync task
        add_active_download(task_id, folder_name, url, "resync")
        
        from utils.logging_utils import LOGS_DIR
        LOGS_DIR_LOCAL = LOGS_DIR or (Path.cwd() / "Logs")
        log_path = LOGS_DIR_LOCAL / "download_playlist.log"
        
        # Log start to both main server log and download log
        start_msg = f"[Resync] Starting resync: {folder_name} | URL: {url} | Task ID: {task_id} | Logging to {log_path}"
        log_message(start_msg)
        
        with open(log_path, "a", encoding="utf-8", buffering=1) as lf:
            # Custom print function that writes to both file and main log
            def dual_print(msg, flush=True):
                # Write to download log file
                print(msg, file=lf, flush=flush)
                # Also log important messages to main server log
                if any(keyword in msg for keyword in ["[START]", "[DONE]", "[ERROR]", "[Info] Playlist contains", "[Info] Detailed scan completed"]):
                    log_message(f"[Resync] {msg}")
            
            # Redirect stdout/stderr to file only, but keep dual logging for important messages
            with contextlib.redirect_stdout(lf), contextlib.redirect_stderr(lf):
                dual_print("="*60)
                dual_print(f"[START] {datetime.datetime.now():%Y-%m-%d %H:%M:%S} | Resync: {folder_name} | URL: {url}")
                try:
                    # Update status to resyncing
                    update_download_status(task_id, "resyncing")
                    
                    # Create callback to send progress to main log
                    def progress_callback(msg):
                        # Log important progress messages to main server log
                        if any(keyword in msg for keyword in ["[Info]", "[Warning]", "[Summary]", "[Progress]"]):
                            log_message(f"[Resync] {msg}")
                        # Update status based on progress
                        if "Starting detailed metadata scan" in msg:
                            update_download_status(task_id, "scanning metadata")
                        elif "Detailed scan completed" in msg:
                            update_download_status(task_id, "downloading files")
                    
                    _dl_playlist = __import__("download_playlist").download_playlist
                    _dl_playlist(url, ROOT_DIR, audio_only=False, sync=True, debug=False, progress_callback=progress_callback)
                    
                    # Update status to finalizing
                    update_download_status(task_id, "updating database")
                    
                    scan_library(ROOT_DIR)
                    success_msg = f"[DONE] {datetime.datetime.now():%Y-%m-%d %H:%M:%S}"
                    dual_print(success_msg)
                    
                    # Mark as completed
                    update_download_status(task_id, "completed")
                    
                except Exception as e:
                    error_msg = f"[ERROR] {datetime.datetime.now():%Y-%m-%d %H:%M:%S} {e}"
                    dual_print(error_msg)
                    update_download_status(task_id, "error")
                finally:
                    dual_print("="*60)
                    # Remove from active downloads after a short delay
                    import time
                    time.sleep(5)  # Keep visible for 5 seconds after completion
                    remove_active_download(task_id)

    threading.Thread(target=_worker, daemon=True).start()
    return jsonify({"status": "started"})

@api_bp.route("/link_playlist", methods=["POST"])
def api_link_playlist():
    """Link existing playlist to URL."""
    data = request.get_json(force=True, silent=True) or {}
    relpath = (data.get("relpath") or "").strip()
    url = (data.get("url") or "").strip()
    if not relpath or not url:
        return jsonify({"status": "error", "message": "missing relpath or url"}), 400

    # quick playlist id validation
    m = re.search(r"list=([A-Za-z0-9_-]+)", url)
    if not m:
        return jsonify({"status": "error", "message": "not a playlist url"}), 400

    conn = get_connection()
    row = db.get_playlist_by_relpath(conn, relpath)
    if not row:
        conn.close()
        return jsonify({"status": "error", "message": "playlist not found"}), 404

    conn.execute("UPDATE playlists SET source_url=? WHERE relpath=?", (url, relpath))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})

@api_bp.route("/restart", methods=["POST"])
def api_restart():
    """Restart Flask server using self-restart mechanism."""
    import subprocess
    import sys
    import os
    import datetime
    
    def restart_server():
        # Give a moment for the response to be sent
        import time
        time.sleep(0.5)
        
        # Log current PID before restart
        current_pid = os.getpid()
        log_message(f"Initiating restart of server PID {current_pid} at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Build restart command with same arguments + --force to bypass duplicate check
        restart_cmd = [sys.executable] + sys.argv + ["--force"]
        
        try:
            # Start new process in same console window (no CREATE_NEW_CONSOLE)
            if os.name == 'nt':  # Windows
                # Use subprocess without creating new console window
                subprocess.Popen(restart_cmd, creationflags=0)
            else:  # Unix/Linux/Mac
                subprocess.Popen(restart_cmd)
            
            log_message(f"New server process started, terminating current PID {current_pid}")
            
            # Clean up PID file before exit to allow new process to start
            try:
                from pathlib import Path
                pid_file = Path.cwd() / "syncplay_hub.pid"
                pid_file.unlink(missing_ok=True)
                log_message("PID file cleaned up for restart")
            except Exception as e:
                log_message(f"Warning: Could not clean PID file: {e}")
            
            # Give new process time to start before terminating
            time.sleep(1.5)
            os._exit(0)  # Force exit current process
            
        except Exception as e:
            log_message(f"Error during restart: {e}")
    
    # Start restart in a separate thread
    threading.Thread(target=restart_server, daemon=True).start()
    
    return jsonify({"status": "ok", "message": "Server restarting..."})

@api_bp.route("/stop", methods=["POST"])
def api_stop():
    """Stop Flask server gracefully."""
    import os
    import datetime
    
    def stop_server():
        # Give a moment for the response to be sent
        import time
        time.sleep(0.5)
        
        # Log current PID before stopping
        current_pid = os.getpid()
        log_message(f"Stopping server PID {current_pid} at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Clean up PID file before exit
        try:
            from pathlib import Path
            pid_file = Path.cwd() / "syncplay_hub.pid"
            pid_file.unlink(missing_ok=True)
            log_message("PID file cleaned up")
        except Exception as e:
            log_message(f"Warning: Could not clean PID file: {e}")
        
        log_message("Server stopped gracefully")
        log_message("You can restart the server by running the same command again")
        
        # Graceful shutdown using Flask's built-in mechanism
        func = request.environ.get('werkzeug.server.shutdown')
        if func is None:
            # Fallback for different WSGI servers
            import signal
            os.kill(os.getpid(), signal.SIGTERM)
        else:
            func()
    
    # Start stop in a separate thread
    threading.Thread(target=stop_server, daemon=True).start()
    
    return jsonify({"status": "ok", "message": "Server stopping..."})

# -------- STREAMING API ENDPOINTS --------

@api_bp.route("/streams")
def api_streams():
    """Get list of active streams."""
    return jsonify(get_streams())

@api_bp.route("/create_stream", methods=["POST"])
def api_create_stream():
    """Create a new stream."""
    data = request.get_json(force=True, silent=True) or {}
    title = data.get("title") or "Untitled Stream"
    
    stream_id = create_stream(
        title=title,
        queue_data=data.get("queue", []),
        idx=data.get("idx", 0),
        position=data.get("position", 0)
    )
    
    from flask import url_for
    return jsonify({
        "id": stream_id,
        "url": url_for("stream_page", stream_id=stream_id, _external=True)
    })

@api_bp.route("/stream_event/<stream_id>", methods=["POST"])
def api_stream_event(stream_id: str):
    """Update stream state."""
    evt = request.get_json(force=True, silent=True) or {}
    
    success = update_stream_state(stream_id, evt)
    if not success:
        return jsonify({"status": "error", "message": "stream not found"}), 404
    
    return jsonify({"status": "ok"})

@api_bp.route("/stream_feed/<stream_id>")
def api_stream_feed(stream_id: str):
    """Server-sent events feed for stream."""
    from flask import Response
    
    stream = get_stream(stream_id)
    if not stream:
        return jsonify({"status": "error", "message": "stream not found"}), 404
    
    client_queue = add_stream_client(stream_id)
    if not client_queue:
        return jsonify({"status": "error", "message": "stream not found"}), 404
    
    def gen():
        try:
            # Send initial state
            init_payload = json.dumps({"init": get_stream_state(stream_id)})
            yield f"data: {init_payload}\n\n"
            
            # Listen for new events
            while True:
                msg = client_queue.get()
                yield f"data: {json.dumps(msg)}\n\n"
        except GeneratorExit:
            pass
        finally:
            remove_stream_client(stream_id, client_queue)
    
    return Response(gen(), mimetype="text/event-stream")

@api_bp.route("/browse", defaults={"subpath": ""})
@api_bp.route("/browse/<path:subpath>")
def api_browse(subpath: str):
    """Browse directory structure and files."""
    try:
        # Start from ROOT_DIR parent to show the full data structure
        base_dir = ROOT_DIR.parent if ROOT_DIR else Path.cwd()
        
        # Handle subpath safely
        if subpath:
            target_dir = base_dir / subpath
            # Security check: ensure path is within base_dir
            target_dir = target_dir.resolve()
            if base_dir not in target_dir.parents and target_dir != base_dir:
                return jsonify({"error": "Invalid path"}), 400
        else:
            target_dir = base_dir
        
        if not target_dir.exists() or not target_dir.is_dir():
            return jsonify({"error": "Directory not found"}), 404
        
        items = []
        try:
            for item in sorted(target_dir.iterdir()):
                if item.name.startswith('.'):
                    continue  # Skip hidden files
                    
                item_data = {
                    "name": item.name,
                    "path": str(item.relative_to(base_dir)).replace("\\", "/"),
                    "is_dir": item.is_dir()
                }
                
                if item.is_file():
                    try:
                        stat = item.stat()
                        item_data.update({
                            "size": stat.st_size,
                            "size_human": _format_file_size(stat.st_size),
                            "modified": stat.st_mtime,
                            "is_media": item.suffix.lower() in {".mp3", ".m4a", ".opus", ".webm", ".flac", ".mp4", ".mkv", ".mov"}
                        })
                    except OSError:
                        item_data.update({
                            "size": 0,  
                            "size_human": "0 B",
                            "modified": 0,
                            "is_media": False
                        })
                
                items.append(item_data)
        except PermissionError:
            return jsonify({"error": "Permission denied"}), 403
        
        # Add parent navigation (if not at root)
        parent_path = ""
        if target_dir != base_dir:
            parent_rel = target_dir.parent.relative_to(base_dir)
            parent_path = str(parent_rel).replace("\\", "/") if str(parent_rel) != "." else ""
        
        return jsonify({
            "current_path": str(target_dir.relative_to(base_dir)).replace("\\", "/") if target_dir != base_dir else "",
            "parent_path": parent_path,
            "can_go_up": target_dir != base_dir,
            "items": items
        })
        
    except Exception as exc:
        log_message(f"[Browse] Error: {exc}")
        return jsonify({"error": str(exc)}), 500

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

@api_bp.route("/download_file/<path:filepath>")
def api_download_file(filepath: str):
    """Download a file from the data directory."""
    try:
        base_dir = ROOT_DIR.parent if ROOT_DIR else Path.cwd()
        file_path = base_dir / filepath
        
        # Security check
        file_path = file_path.resolve()
        if base_dir not in file_path.parents and file_path != base_dir:
            return jsonify({"error": "Invalid path"}), 400
        
        if not file_path.exists() or not file_path.is_file():
            return jsonify({"error": "File not found"}), 404
        
        return send_from_directory(base_dir, filepath, as_attachment=True)
        
    except Exception as exc:
        log_message(f"[DownloadFile] Error: {exc}")
        return jsonify({"error": str(exc)}), 500

# ==============================
# REMOTE CONTROL API ENDPOINTS  
# ==============================

@api_bp.route("/remote/status")
def api_remote_status():
    """Get current player status for remote control."""
    return jsonify(PLAYER_STATE)

@api_bp.route("/remote/play", methods=["POST"])
def api_remote_play():
    """Toggle play/pause."""
    global COMMAND_QUEUE
    COMMAND_QUEUE.append({
        'type': 'play',
        'timestamp': __import__('time').time()
    })
    
    log_message("[Remote] Play/pause command queued")
    return jsonify({"status": "ok", "command": "queued"})

@api_bp.route("/remote/next", methods=["POST"])
def api_remote_next():
    """Skip to next track."""
    global COMMAND_QUEUE
    COMMAND_QUEUE.append({
        'type': 'next',
        'timestamp': __import__('time').time()
    })
    
    log_message("[Remote] Next track command queued")
    return jsonify({"status": "ok", "command": "queued"})

@api_bp.route("/remote/prev", methods=["POST"])
def api_remote_prev():
    """Skip to previous track."""
    global COMMAND_QUEUE
    COMMAND_QUEUE.append({
        'type': 'prev',
        'timestamp': __import__('time').time()
    })
    
    log_message("[Remote] Previous track command queued")
    return jsonify({"status": "ok", "command": "queued"})

@api_bp.route("/remote/stop", methods=["POST"])
def api_remote_stop():
    """Stop playback."""
    global PLAYER_STATE
    PLAYER_STATE['playing'] = False
    PLAYER_STATE['progress'] = 0
    PLAYER_STATE['last_update'] = __import__('time').time()
    
    log_message("[Remote] Playback stopped")
    return jsonify({"status": "ok"})

@api_bp.route("/remote/volume", methods=["POST"])
def api_remote_volume():
    """Set volume."""
    global COMMAND_QUEUE, PLAYER_STATE
    data = request.get_json() or {}
    volume = data.get('volume', 1.0)
    video_id = data.get('video_id')
    position = data.get('position')
    
    # Clamp volume between 0 and 1
    volume = max(0.0, min(1.0, float(volume)))
    
    # Save volume to database and record change event
    try:
        conn = get_connection()
        volume_from = db.get_user_volume(conn)
        db.set_user_volume(conn, volume)
        
        # Record volume change event
        if abs(volume - volume_from) >= 0.01:  # Only record if change is >= 1%
            # Try to get current track info from player state
            if not video_id and PLAYER_STATE['current_track']:
                video_id = PLAYER_STATE['current_track'].get('video_id', 'system')
            if not video_id:
                video_id = 'system'
            
            if not position and PLAYER_STATE['progress']:
                position = PLAYER_STATE['progress']
                
            db.record_volume_change(
                conn, 
                video_id, 
                volume_from, 
                volume, 
                position=position,
                additional_data='remote'
            )
        
        conn.close()
    except Exception as e:
        log_message(f"[Remote] Warning: Could not save volume to database: {e}")
    
    COMMAND_QUEUE.append({
        'type': 'volume',
        'volume': volume,
        'timestamp': __import__('time').time()
    })
    
    log_message(f"[Remote] Volume command queued and saved: {int(volume * 100)}%")
    return jsonify({"status": "ok", "command": "queued"})

@api_bp.route("/remote/like", methods=["POST"])
def api_remote_like():
    """Like current track."""
    global PLAYER_STATE
    if PLAYER_STATE['current_track'] and 'video_id' in PLAYER_STATE['current_track']:
        video_id = PLAYER_STATE['current_track']['video_id']
        
        # Record like event in database
        try:
            conn = get_connection()
            record_event(conn, video_id, 'like', position=PLAYER_STATE['progress'])
            conn.close()
            
            log_message(f"[Remote] Liked track: {PLAYER_STATE['current_track'].get('name', 'Unknown')}")
            return jsonify({"status": "ok"})
        except Exception as e:
            log_message(f"[Remote] Error recording like: {e}")
            return jsonify({"status": "error", "message": str(e)}), 500
    
    return jsonify({"status": "error", "message": "No current track"}), 400

@api_bp.route("/remote/shuffle", methods=["POST"])
def api_remote_shuffle():
    """Shuffle playlist."""
    global PLAYER_STATE
    if PLAYER_STATE['playlist']:
        import random
        random.shuffle(PLAYER_STATE['playlist'])
        PLAYER_STATE['current_index'] = 0
        PLAYER_STATE['current_track'] = PLAYER_STATE['playlist'][0] if PLAYER_STATE['playlist'] else None
        PLAYER_STATE['progress'] = 0
        PLAYER_STATE['last_update'] = __import__('time').time()
        
        log_message("[Remote] Playlist shuffled")
        return jsonify({"status": "ok", "track": PLAYER_STATE['current_track']})
    
    return jsonify({"status": "error", "message": "No playlist loaded"}), 400

@api_bp.route("/remote/youtube", methods=["POST"])
def api_remote_youtube():
    """Open current track on YouTube."""
    global PLAYER_STATE
    if PLAYER_STATE['current_track'] and 'video_id' in PLAYER_STATE['current_track']:
        video_id = PLAYER_STATE['current_track']['video_id']
        youtube_url = f"https://www.youtube.com/watch?v={video_id}"
        
        log_message(f"[Remote] YouTube link requested: {youtube_url}")
        return jsonify({"status": "ok", "url": youtube_url})
    
    return jsonify({"status": "error", "message": "No current track"}), 400

@api_bp.route("/remote/fullscreen", methods=["POST"])
def api_remote_fullscreen():
    """Toggle fullscreen (placeholder - actual implementation would be client-side)."""
    log_message("[Remote] Fullscreen toggle requested")
    return jsonify({"status": "ok", "message": "Fullscreen toggle sent to client"})

@api_bp.route("/remote/sync_internal", methods=["POST"])
def api_remote_sync_internal():
    """Internal sync endpoint for player to update server state."""
    global PLAYER_STATE
    data = request.get_json() or {}
    
    # Update server state with player data
    PLAYER_STATE.update(data)
    PLAYER_STATE['last_update'] = __import__('time').time()
    
    return jsonify({"status": "ok"})

@api_bp.route("/remote/commands")
def api_remote_commands():
    """Get and clear pending remote commands."""
    global COMMAND_QUEUE
    commands = COMMAND_QUEUE.copy()
    COMMAND_QUEUE.clear()
    
    if commands:
        log_message(f"[Remote] Returning {len(commands)} commands to player")
    
    return jsonify(commands)

@api_bp.route("/remote/load_playlist", methods=["POST"])
def api_remote_load_playlist():
    """Load a playlist into the remote player."""
    global PLAYER_STATE
    data = request.get_json() or {}
    playlist_path = data.get('playlist_path', '')
    
    try:
        # Import scan_tracks to get playlist data
        from services.playlist_service import scan_tracks, _ensure_subdir
        
        if playlist_path:
            base_dir = _ensure_subdir(Path(playlist_path))
            tracks = scan_tracks(base_dir)
        else:
            tracks = scan_tracks(ROOT_DIR)
        
        if tracks:
            PLAYER_STATE['playlist'] = tracks
            PLAYER_STATE['current_index'] = 0
            PLAYER_STATE['current_track'] = tracks[0]
            PLAYER_STATE['progress'] = 0
            PLAYER_STATE['playing'] = False
            PLAYER_STATE['last_update'] = __import__('time').time()
            
            log_message(f"[Remote] Playlist loaded: {len(tracks)} tracks")
            return jsonify({"status": "ok", "tracks_count": len(tracks)})
        else:
            return jsonify({"status": "error", "message": "No tracks found"}), 400
            
    except Exception as e:
        log_message(f"[Remote] Error loading playlist: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ==============================
# VOLUME SETTINGS API ENDPOINTS  
# ==============================

@api_bp.route("/volume/get")
def api_get_volume():
    """Get saved user volume setting."""
    try:
        conn = get_connection()
        volume = db.get_user_volume(conn)
        conn.close()
        
        log_message(f"[Volume] Retrieved saved volume: {int(volume * 100)}%")
        return jsonify({"volume": volume, "volume_percent": int(volume * 100)})
        
    except Exception as e:
        log_message(f"[Volume] Error retrieving volume: {e}")
        return jsonify({"error": str(e), "volume": 1.0, "volume_percent": 100}), 500

@api_bp.route("/volume/set", methods=["POST"])
def api_set_volume():
    """Save user volume setting."""
    try:
        data = request.get_json() or {}
        volume = data.get('volume', 1.0)
        volume_from = data.get('volume_from')
        video_id = data.get('video_id', 'system')
        position = data.get('position')
        source = data.get('source', 'web')  # web, remote, gesture, etc.
        
        # Validate and clamp volume
        volume = max(0.0, min(1.0, float(volume)))
        
        # Save to database
        conn = get_connection()
        
        # Get previous volume if not provided
        if volume_from is None:
            volume_from = db.get_user_volume(conn)
        else:
            volume_from = max(0.0, min(1.0, float(volume_from)))
            
        # Save new volume
        db.set_user_volume(conn, volume)
        
        # Record volume change event if there's a meaningful change
        if abs(volume - volume_from) >= 0.01:  # Only record if change is >= 1%
            db.record_volume_change(
                conn, 
                video_id, 
                volume_from, 
                volume, 
                position=position,
                additional_data=source
            )
        
        conn.close()
        
        log_message(f"[Volume] Volume saved: {int(volume_from * 100)}% → {int(volume * 100)}% (source: {source})")
        return jsonify({
            "status": "ok", 
            "volume": volume, 
            "volume_percent": int(volume * 100),
            "volume_from": volume_from,
            "change_recorded": abs(volume - volume_from) >= 0.01
        })
        
    except Exception as e:
        log_message(f"[Volume] Error saving volume: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

# ==============================
# SEEK EVENTS API ENDPOINTS  
# ==============================

@api_bp.route("/seek", methods=["POST"])
def api_record_seek():
    """Record seek/scrub event."""
    try:
        data = request.get_json() or {}
        video_id = data.get('video_id')
        seek_from = data.get('seek_from')
        seek_to = data.get('seek_to')
        source = data.get('source', 'web')  # web, remote, keyboard, etc.
        
        # Validate required fields
        if not video_id:
            return jsonify({"status": "error", "error": "video_id is required"}), 400
        
        if seek_from is None or seek_to is None:
            return jsonify({"status": "error", "error": "seek_from and seek_to are required"}), 400
        
        # Validate numeric values
        try:
            seek_from = float(seek_from)
            seek_to = float(seek_to)
        except (ValueError, TypeError):
            return jsonify({"status": "error", "error": "seek_from and seek_to must be numbers"}), 400
        
        # Only record meaningful seeks (> 1 second difference)
        if abs(seek_to - seek_from) < 1.0:
            return jsonify({"status": "ok", "message": "Seek too small, not recorded"})
        
        # Record seek event
        conn = get_connection()
        db.record_seek_event(conn, video_id, seek_from, seek_to, additional_data=source)
        conn.close()
        
        # Calculate seek direction and distance
        seek_diff = seek_to - seek_from
        direction = "forward" if seek_diff > 0 else "backward"
        distance = abs(seek_diff)
        
        log_message(f"[Seek] {direction} seek: {seek_from:.1f}s → {seek_to:.1f}s ({distance:.1f}s) on {video_id} (source: {source})")
        
        return jsonify({
            "status": "ok", 
            "seek_from": seek_from,
            "seek_to": seek_to,
            "direction": direction,
            "distance": distance,
            "source": source
        })
        
    except Exception as e:
        log_message(f"[Seek] Error recording seek: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500 
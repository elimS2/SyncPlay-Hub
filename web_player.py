#!/usr/bin/env python3
"""Simple web player for downloaded YouTube playlist tracks.

Usage:
    python web_player.py --root downloads --host 0.0.0.0 --port 8000

Open in browser: http://localhost:8000/
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import List
import socket
import re
import datetime
import threading
import uuid
import queue
import time
import json
import os

from flask import Flask, jsonify, render_template, send_from_directory, url_for, abort, request, Response

import database as db
from database import get_connection, iter_tracks_with_playlists, record_event, get_history_page
from database import upsert_playlist

# We'll reuse scan function from scan_to_db.py
from scan_to_db import scan as scan_library

import log_utils  # noqa: F401 – applies timestamp+PID prefix to all print() calls
import logging
from logging.handlers import RotatingFileHandler
import sys
import io

app = Flask(
    __name__,
    static_folder="static",
    template_folder="templates",
)

# ROOT_DIR will point to the Playlists directory (BASE_DIR / "Playlists")
ROOT_DIR: Path  # set in main()

# Where the database file lives (BASE_DIR / "DB" / tracks.db)
DB_FILE: Path  # set in main()

# Server start time and PID for restart verification
SERVER_START_TIME = datetime.datetime.now()
SERVER_PID = os.getpid()

# Global dictionary to track active download processes
ACTIVE_DOWNLOADS = {}  # {task_id: {title, url, start_time, type, status}}
_downloads_lock = threading.Lock()

# Global logging
unified_logger = None

class AnsiCleaningStream:
    """Stream wrapper that removes ANSI codes before writing to file"""
    
    def __init__(self, original_stream, file_handler):
        self.original_stream = original_stream
        self.file_handler = file_handler
        
    def write(self, text):
        # Write original (with colors) to console
        self.original_stream.write(text)
        
        # Don't write to file here - let the DualStreamHandler handle it
        # This prevents double logging
        
        return len(text)
    
    def flush(self):
        self.original_stream.flush()
        
    def _remove_ansi_codes(self, text):
        """Remove ANSI escape codes from text"""
        import re
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', text)
    
    def __getattr__(self, name):
        # Delegate other attributes to original stream
        return getattr(self.original_stream, name)

class DualStreamHandler(logging.Handler):
    """Custom handler that writes to both console and file simultaneously"""
    
    def __init__(self, file_handler):
        super().__init__()
        self.file_handler = file_handler
        
    def emit(self, record):
        try:
            # Get original message and clean it
            original_msg = record.getMessage()
            clean_msg = self._remove_ansi_codes(original_msg)
            
            # Remove Flask's timestamp from HTTP logs for cleaner output
            clean_msg = self._remove_flask_timestamp(clean_msg)
            
            # For console: use cleaned message (log_utils will add timestamp+PID)
            print(clean_msg, flush=True)
            
            # Create a copy of the record with cleaned message for file handler
            file_record = logging.LogRecord(
                record.name, record.levelno, record.pathname, record.lineno,
                clean_msg, (), record.exc_info, record.funcName, record.stack_info
            )
            file_record.created = record.created
            file_record.msecs = record.msecs
            file_record.relativeCreated = record.relativeCreated
            file_record.thread = record.thread
            file_record.threadName = record.threadName
            file_record.processName = record.processName
            file_record.process = record.process
            
            # Write to file (file_handler will add its own timestamp+PID formatting)
            self.file_handler.emit(file_record)
            
        except Exception:
            self.handleError(record)
    
    def _remove_flask_timestamp(self, message):
        """Remove Flask's built-in timestamp from HTTP log messages"""
        if ' - - [' in message and '] "' in message:
            # Extract just the IP and request part, skip the timestamp
            parts = message.split(' - - [', 1)
            if len(parts) == 2:
                ip_part = parts[0]
                rest_parts = parts[1].split('] ', 1)
                if len(rest_parts) == 2:
                    request_part = rest_parts[1]
                    return f"{ip_part} - - {request_part}"
        return message
    
    def _remove_ansi_codes(self, text):
        """Remove ANSI escape codes from text"""
        import re
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', text)

def log_message(message):
    """Log function that writes simultaneously to both console and file"""
    if unified_logger:
        unified_logger.info(message)
    else:
        # Fallback if logger not initialized
        print(message, flush=True)


def add_active_download(task_id: str, title: str, url: str, download_type: str = "download"):
    """Register a new active download task"""
    import threading
    with _downloads_lock:
        ACTIVE_DOWNLOADS[task_id] = {
            "title": title,
            "url": url,
            "start_time": datetime.datetime.now(),
            "type": download_type,  # "download" or "resync"
            "status": "starting",
            "thread_id": threading.get_ident(),  # Thread ID
            "process_id": os.getpid()  # Process ID (same as server)
        }


def update_download_status(task_id: str, status: str):
    """Update the status of an active download"""
    with _downloads_lock:
        if task_id in ACTIVE_DOWNLOADS:
            ACTIVE_DOWNLOADS[task_id]["status"] = status


def remove_active_download(task_id: str):
    """Remove a completed download task"""
    with _downloads_lock:
        ACTIVE_DOWNLOADS.pop(task_id, None)


def get_active_downloads():
    """Get copy of current active downloads"""
    with _downloads_lock:
        # Create a copy with calculated runtime
        active = {}
        for task_id, info in ACTIVE_DOWNLOADS.items():
            runtime = datetime.datetime.now() - info["start_time"]
            active[task_id] = {
                **info,
                "runtime": str(runtime).split('.')[0]  # Remove microseconds
            }
        return active

VIDEO_ID_RE = re.compile(r"\[([A-Za-z0-9_-]{11})\]$")

# ---- constants ----

MEDIA_EXTS = {".mp3", ".m4a", ".opus", ".webm", ".flac", ".mp4", ".mkv", ".mov"}

# ---- Live Streams ----

# In-memory store: {stream_id: {"state":{...}, "clients":set(), "title":str, "created":ts}}
STREAMS: dict[str, dict] = {}
_streams_lock = threading.Lock()


def _prune_streams():
    """Remove streams with no clients for >30 min."""
    now = time.time()
    with _streams_lock:
        stale = [sid for sid, s in STREAMS.items() if not s["clients"] and now - s["created"] > 1800]
        for sid in stale:
            STREAMS.pop(sid, None)


# API: list active streams


@app.route("/api/streams")
def api_streams():
    _prune_streams()
    with _streams_lock:
        items = [
            {
                "id": sid,
                "title": s.get("title", "Stream"),
                "listeners": len(s["clients"]),
            }
            for sid, s in STREAMS.items()
        ]
    return jsonify(items)


@app.route("/api/create_stream", methods=["POST"])
def api_create_stream():
    data = request.get_json(force=True, silent=True) or {}
    title = data.get("title") or "Untitled Stream"
    stream_id = uuid.uuid4().hex[:8]
    with _streams_lock:
        STREAMS[stream_id] = {
            "state": {
                "queue": data.get("queue", []),
                "idx": data.get("idx", 0),
                "position": data.get("position", 0),
                "paused": True,
            },
            "clients": set(),
            "title": title,
            "created": time.time(),
        }
    return jsonify({"id": stream_id, "url": url_for("stream_page", stream_id=stream_id, _external=True)})


@app.route("/api/stream_event/<stream_id>", methods=["POST"])
def api_stream_event(stream_id: str):
    evt = request.get_json(force=True, silent=True) or {}
    with _streams_lock:
        s = STREAMS.get(stream_id)
        if not s:
            return jsonify({"status": "error", "message": "stream not found"}), 404
        # update state
        action = evt.get("action")
        if action in {"play", "pause", "seek", "next", "prev"}:
            # generic update of known fields
            for key in ("idx", "position", "paused"):
                if key in evt:
                    s["state"][key] = evt[key]
            s["state"]["last_action"] = action
        # fan-out to clients
        for q in list(s["clients"]):
            try:
                q.put(evt, timeout=0.1)
            except Exception:
                pass
    return jsonify({"status": "ok"})


@app.route("/api/stream_feed/<stream_id>")
def api_stream_feed(stream_id: str):
    with _streams_lock:
        s = STREAMS.get(stream_id)
        if not s:
            abort(404)
        q: queue.Queue = queue.Queue()
        s["clients"].add(q)

    def gen():
        try:
            # send initial state
            init_payload = json.dumps({"init": s['state']})
            yield f"data: {init_payload}\n\n"
            while True:
                msg = q.get()
                yield f"data: {json.dumps(msg)}\n\n"
        except GeneratorExit:
            pass
        finally:
            with _streams_lock:
                st = STREAMS.get(stream_id)
                if st:
                    st["clients"].discard(q)

    return Response(gen(), mimetype="text/event-stream")


# Stream pages


@app.route("/streams")
def streams_page():
    return render_template("streams.html")


@app.route("/stream/<stream_id>")
def stream_page(stream_id: str):
    with _streams_lock:
        s = STREAMS.get(stream_id)
        if not s:
            abort(404)
    return render_template("stream_view.html", stream_id=stream_id, stream_title=s.get("title", "Stream"), server_ip=_get_local_ip())


def scan_tracks(scan_root: Path) -> List[dict]:
    """Return list of media files under scan_root (recursive).

    The returned URLs/relpaths are always relative to the global ROOT_DIR so that
    they can be served correctly by the /media endpoint.
    """
    files = []
    for p in scan_root.rglob("*.*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in {".mp3", ".m4a", ".opus", ".webm", ".flac", ".mp4", ".mkv", ".mov"}:
            continue
        rel_to_root = p.relative_to(ROOT_DIR)
        m = VIDEO_ID_RE.search(p.stem)
        vid = m.group(1) if m else ""
        files.append({
            "name": p.stem,
            "relpath": str(rel_to_root).replace("\\", "/"),
            "url": url_for("media", filename=str(rel_to_root).replace("\\", "/")),
            "video_id": vid,
            "last_play": _get_last_play_ts(vid),
        })
    return files


# ------------------------
# Helper functions
# ------------------------


def _ensure_subdir(requested: Path) -> Path:
    """Return absolute path under ROOT_DIR or abort 404 if traversal is attempted."""
    try:
        # Ensure the resolved path is inside ROOT_DIR (prevent path traversal)
        requested_abs = (ROOT_DIR / requested).resolve()
        if ROOT_DIR not in requested_abs.parents and requested_abs != ROOT_DIR:
            raise ValueError
        return requested_abs
    except Exception:
        abort(404)


def list_playlists(root: Path) -> List[dict]:
    """Return first-level sub-directories that contain at least one media file."""
    # Fetch meta from DB once
    meta = {}
    try:
        conn = get_connection()
        for row in conn.execute(
            """
            SELECT p.id, p.relpath, p.track_count, p.last_sync_ts, p.source_url,
                   COALESCE(SUM(t.play_starts + t.play_nexts + t.play_prevs + t.play_finishes),0) AS play_total,
                   COALESCE(SUM(t.play_likes),0) AS like_total,
                   COALESCE(SUM(CASE WHEN (t.last_start_ts IS NULL AND t.last_finish_ts IS NULL) OR 
                                         COALESCE(t.last_finish_ts, t.last_start_ts) < datetime('now','-30 days') THEN 1 ELSE 0 END),0) AS forgotten_total
            FROM playlists p
            LEFT JOIN track_playlists tp ON tp.playlist_id = p.id
            LEFT JOIN tracks t ON t.id = tp.track_id
            GROUP BY p.id
            """):
            meta[row[1]] = {
                "track_count": row[2],
                "last_sync_ts": row[3],
                "source_url": row[4],
                "play_total": row[5],
                "like_total": row[6],
                "forgotten_total": row[7],
            }
        conn.close()
    except Exception:
        pass

    playlists = []
    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        # does this dir contain at least one media file (recursively)?
        has_media = any(p.suffix.lower() in MEDIA_EXTS for p in d.rglob("*.*"))
        if has_media:
            rel = str(d.relative_to(root)).replace("\\", "/")
            dbinfo = meta.get(rel)
            count = dbinfo["track_count"] if dbinfo and dbinfo["track_count"] is not None else "?"
            last_sync_str = dbinfo["last_sync_ts"][:16].replace("T", " ") if dbinfo and dbinfo["last_sync_ts"] else "-"
            has_source = bool(dbinfo and dbinfo["source_url"])
            playlists.append({
                "name": d.name,
                "relpath": rel,
                "url": url_for("playlist_page", playlist_path=rel),
                "count": count,
                "last_sync": last_sync_str,
                "has_source": has_source,
                "plays": dbinfo.get("play_total", 0) if dbinfo else 0,
                "likes": dbinfo.get("like_total", 0) if dbinfo else 0,
                "forgotten": dbinfo.get("forgotten_total", 0) if dbinfo else 0,
            })
    
    # Sort by forgotten count (descending) by default
    playlists.sort(key=lambda x: x["forgotten"], reverse=True)
    
    return playlists


# -------- API ROUTES --------


@app.route("/api/tracks", defaults={"subpath": ""})
@app.route("/api/tracks/<path:subpath>")
def api_tracks(subpath: str):
    base_dir = _ensure_subdir(Path(subpath)) if subpath else ROOT_DIR
    tracks = scan_tracks(base_dir)
    return jsonify(tracks)


@app.route("/api/playlists")
def api_playlists():
    return jsonify(list_playlists(ROOT_DIR))


@app.route("/api/active_downloads")
def api_active_downloads():
    """Get current active downloads status"""
    return jsonify(get_active_downloads())


@app.route("/media/<path:filename>")
def media(filename: str):
    return send_from_directory(ROOT_DIR, filename, as_attachment=False)


# Helper to determine local LAN IP (for Chromecast)


def _get_local_ip() -> str:
    """Return this machine's LAN IP address (best effort)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Whether the address is reachable is irrelevant; we just need to select the interface
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


# -------- PAGE ROUTES --------


@app.route("/")
def playlists_page():
    """Homepage – list all playlists (sub-folders)."""
    playlists = list_playlists(ROOT_DIR)
    server_info = {
        "pid": SERVER_PID,
        "start_time": SERVER_START_TIME.strftime("%Y-%m-%d %H:%M:%S"),
        "uptime": str(datetime.datetime.now() - SERVER_START_TIME).split('.')[0]  # Remove microseconds
    }
    active_downloads = get_active_downloads()
    return render_template("playlists.html", playlists=playlists, server_ip=_get_local_ip(), 
                          server_info=server_info, active_downloads=active_downloads)


@app.route("/playlist/<path:playlist_path>")
def playlist_page(playlist_path: str):
    """Playlist view – identical to previous homepage."""
    # validate path
    _ensure_subdir(Path(playlist_path))
    from pathlib import Path as _Path
    return render_template("index.html", server_ip=_get_local_ip(), playlist_rel=playlist_path, playlist_name=_Path(playlist_path).name)


# -------- DB Tracks Page --------


@app.route("/tracks")
def tracks_page():
    conn = get_connection()
    tracks = list(iter_tracks_with_playlists(conn))
    conn.close()
    return render_template("tracks.html", tracks=tracks)


# -------- History Page --------


@app.route("/history")
def history_page():
    page = int(request.args.get("page", 1))
    conn = get_connection()
    rows, has_next = get_history_page(conn, page=page, per_page=1000)
    rows = [dict(r) for r in rows]
    conn.close()
    return render_template("history.html", history=rows, page=page, has_next=has_next)


# -------- Scan API --------


@app.route("/api/scan", methods=["POST"])
def api_scan():
    """Scan Playlists directory and update database."""
    try:
        scan_library(ROOT_DIR)
        return jsonify({"status": "ok"})
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500


# -------- Add Playlist API --------


@app.route("/api/add_playlist", methods=["POST"])
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
    from yt_dlp.utils import sanitize_filename  # type: ignore

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
        
        LOGS_DIR_LOCAL = globals().get("LOGS_DIR", Path.cwd() / "Logs")
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
                    from database import scan_library  # local import
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

    import threading

    threading.Thread(target=_worker, daemon=True).start()
    return jsonify({"status": "started"})


# -------- Event API --------


@app.route("/api/event", methods=["POST"])
def api_event():
    data = {}  # fallback
    try:
        data = app.request_json_cache if hasattr(app, 'request_json_cache') else None
    except Exception:
        pass
    if not data:
        data = getattr(__import__('flask'), 'request').get_json(force=True, silent=True) or {}
    video_id = data.get("video_id")
    ev = data.get("event")
    pos = data.get("position")
    if not video_id or ev not in {"start", "finish", "next", "prev", "like"}:
        return jsonify({"status": "error", "message": "bad payload"}), 400
    conn = get_connection()
    record_event(conn, video_id, ev, position=pos)
    conn.close()
    return jsonify({"status": "ok"})


# Retrieve last play timestamp helper

def _get_last_play_ts(video_id: str):
    if not video_id:
        return None
    conn = get_connection()
    row = conn.execute("SELECT last_start_ts, last_finish_ts FROM tracks WHERE video_id=?", (video_id,)).fetchone()
    conn.close()
    if not row:
        return None
    ts1 = row["last_start_ts"]
    ts2 = row["last_finish_ts"]
    # return latest
    if ts1 and ts2:
        return ts1 if ts1 > ts2 else ts2
    return ts1 or ts2


# -------- Logs routes --------


def _list_log_files() -> List[Path]:
    """Return sorted list of *.log paths inside LOGS_DIR (main log first, then newest first)."""
    logs_dir = globals().get("LOGS_DIR")
    if not logs_dir:
        return []
    
    all_logs = list(logs_dir.glob("*.log"))
    main_log = logs_dir / "SyncPlay-Hub.log"
    
    # Separate main log from others
    main_logs = [log for log in all_logs if log.name == "SyncPlay-Hub.log"]
    other_logs = [log for log in all_logs if log.name != "SyncPlay-Hub.log"]
    
    # Sort others by modification time (newest first)
    other_logs_sorted = sorted(other_logs, key=lambda p: p.stat().st_mtime, reverse=True)
    
    # Return main log first, then others
    return main_logs + other_logs_sorted


@app.route("/logs")
def logs_page():
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
    """Format file size in human readable format"""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    
    if i == 0:
        return f"{int(size_bytes)} {size_names[i]}"
    else:
        return f"{size_bytes:.1f} {size_names[i]}"


@app.route("/log/<path:log_name>")
def log_view_page(log_name: str):
    # security: ensure no traversal
    if "/" in log_name or ".." in log_name or not log_name.endswith(".log"):
        abort(404)
    logs_dir = globals().get("LOGS_DIR")
    if not (logs_dir / log_name).exists():
        abort(404)
    return render_template("log_view.html", log_name=log_name)


@app.route("/stream_log/<path:log_name>")
def stream_log(log_name: str):
    import time
    from collections import deque
    from flask import Response

    # security checks
    if "/" in log_name or ".." in log_name or not log_name.endswith(".log"):
        abort(404)
    logs_dir = globals().get("LOGS_DIR")
    file_path = logs_dir / log_name
    if not file_path.exists():
        abort(404)

    def generate():
        # Send last 200 lines first
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                last_lines = deque(f, maxlen=200)
                for line in last_lines:
                    yield f"data: {line.rstrip()}\n\n"

                # Follow file
                f.seek(0, 2)  # move to end
                while True:
                    line = f.readline()
                    if line:
                        yield f"data: {line.rstrip()}\n\n"
                    else:
                        time.sleep(1)
        except GeneratorExit:
            return

    return Response(generate(), mimetype="text/event-stream")


@app.route("/static_log/<path:log_name>")
def static_log(log_name: str):
    """Serve log file as plain text for browser viewing"""
    # security checks
    if "/" in log_name or ".." in log_name or not log_name.endswith(".log"):
        abort(404)
    logs_dir = globals().get("LOGS_DIR")
    file_path = logs_dir / log_name
    if not file_path.exists():
        abort(404)
    
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        
        from flask import Response
        return Response(content, mimetype="text/plain; charset=utf-8")
    except Exception:
        abort(500)


# -------- Resync playlist API --------


@app.route("/api/resync", methods=["POST"])
def api_resync():
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
        
        LOGS_DIR_LOCAL = globals().get("LOGS_DIR", Path.cwd() / "Logs")
        log_path = LOGS_DIR_LOCAL / "download_playlist.log"
        
        # Log start to both main server log and download log
        start_msg = f"[Resync] Starting resync: {folder_name} | URL: {url} | Task ID: {task_id} | Logging to {log_path}"
        log_message(start_msg)  # Main server log
        
        with open(log_path, "a", encoding="utf-8", buffering=1) as lf:
            # Custom print function that writes to both file and main log
            def dual_print(msg, flush=True):
                # Write to download log file
                print(msg, file=lf, flush=flush)
                # Also log important messages to main server log
                if any(keyword in msg for keyword in ["[RESYNC]", "[DONE]", "[ERROR]", "[Info] Playlist contains", "[Info] Detailed scan completed"]):
                    log_message(f"[Resync] {msg}")
            
            # Redirect stdout/stderr to file only, but keep dual logging for important messages
            with contextlib.redirect_stdout(lf), contextlib.redirect_stderr(lf):
                dual_print("="*60)
                dual_print(f"[RESYNC] {datetime.datetime.now():%Y-%m-%d %H:%M:%S} | Playlist: {folder_name}")
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

    import threading
    threading.Thread(target=_worker, daemon=True).start()
    return jsonify({"status": "started"})


# -------- Link existing playlist to URL --------


@app.route("/api/link_playlist", methods=["POST"])
def api_link_playlist():
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


@app.route("/api/restart", methods=["POST"])
def api_restart():
    """Restart Flask server using self-restart mechanism."""
    import subprocess
    import sys
    
    def restart_server():
        # Give a moment for the response to be sent
        import time
        time.sleep(0.5)
        
        # Log current PID before restart
        current_pid = os.getpid()
        log_message(f"Initiating restart of server PID {current_pid} at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Build restart command with same arguments
        restart_cmd = [sys.executable] + sys.argv
        
        try:
            # Start new process in same console window (no CREATE_NEW_CONSOLE)
            if os.name == 'nt':  # Windows
                # Use subprocess without creating new console window
                subprocess.Popen(restart_cmd, creationflags=0)
            else:  # Unix/Linux/Mac
                subprocess.Popen(restart_cmd)
            
            log_message(f"New server process started, terminating current PID {current_pid}")
            
            # Give new process time to start before terminating
            time.sleep(1.5)
            os._exit(0)  # Force exit current process
            
        except Exception as e:
            log_message(f"Error during restart: {e}")
    
    # Start restart in a separate thread
    threading.Thread(target=restart_server, daemon=True).start()
    
    return jsonify({"status": "ok", "message": "Server restarting..."})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    """Stop Flask server gracefully."""
    
    def stop_server():
        # Give a moment for the response to be sent
        import time
        time.sleep(0.5)
        
        # Log current PID before stopping
        current_pid = os.getpid()
        log_message(f"Stopping server PID {current_pid} at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
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


if __name__ == "__main__":
    
    parser = argparse.ArgumentParser(description="Local web player for downloaded tracks")
    parser.add_argument("--root", default="downloads", help="Base folder containing Playlists/ and DB/")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    BASE_DIR = Path(args.root).resolve()
    PLAYLISTS_DIR = BASE_DIR / "Playlists"
    DB_DIR = BASE_DIR / "DB"

    if not PLAYLISTS_DIR.exists():
        raise SystemExit(f"Playlists folder '{PLAYLISTS_DIR}' not found (expected inside base dir)")
    DB_DIR.mkdir(parents=True, exist_ok=True)

    LOGS_DIR = BASE_DIR / "Logs"
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    ROOT_DIR = PLAYLISTS_DIR
    DB_FILE = DB_DIR / "tracks.db"

    # Expose LOGS_DIR globally so api_add_playlist can access
    globals()["LOGS_DIR"] = LOGS_DIR

    # configure database path
    db.set_db_path(DB_FILE)

    # Setup unified logging system
    main_log_file = LOGS_DIR / "SyncPlay-Hub.log"
    
    # Create file handler
    file_handler = RotatingFileHandler(main_log_file, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
    file_handler.setFormatter(logging.Formatter('%(asctime)s [PID %(process)d] %(message)s', '%Y-%m-%d %H:%M:%S'))
    
    # Create our unified logger with dual stream handler
    unified_logger = logging.getLogger('syncplay_unified')
    unified_logger.setLevel(logging.INFO)
    unified_logger.propagate = False
    
    # Add dual stream handler that writes to both console and file
    dual_handler = DualStreamHandler(file_handler)
    dual_handler.setFormatter(logging.Formatter('%(message)s'))  # Simple format since timestamp is added by log_utils
    unified_logger.addHandler(dual_handler)
    
    # Configure Flask's werkzeug logger to use our unified system
    werkzeug_logger = logging.getLogger('werkzeug')
    werkzeug_logger.handlers.clear()  # Remove default handlers
    werkzeug_logger.addHandler(dual_handler)
    werkzeug_logger.propagate = False
    
    # Also configure the root Flask logger
    flask_logger = logging.getLogger('flask')
    flask_logger.handlers.clear()
    flask_logger.addHandler(dual_handler)
    flask_logger.propagate = False
    
    # Configure the main app logger
    app.logger.handlers.clear()
    app.logger.addHandler(dual_handler)
    app.logger.propagate = False
    
    # Intercept stdout/stderr to catch any direct prints from Flask
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    sys.stdout = AnsiCleaningStream(original_stdout, file_handler)
    sys.stderr = AnsiCleaningStream(original_stderr, file_handler)
    
    # Make unified logger available globally
    globals()['unified_logger'] = unified_logger
    

    log_message(f"Starting server PID {SERVER_PID} at {SERVER_START_TIME.strftime('%Y-%m-%d %H:%M:%S')}")
    app.run(host=args.host, port=args.port, debug=False) 
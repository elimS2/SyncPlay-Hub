#!/usr/bin/env python3
"""
Refactored YouTube Playlist Player - Main Application
"""

import argparse
import datetime
import os
import sys
from pathlib import Path
import json

from flask import Flask, render_template, send_from_directory, abort, jsonify, redirect, url_for, request

# Import our new modules
from utils.logging_utils import init_logging, setup_logging, log_message
from services.playlist_service import list_playlists, set_root_dir
from services.download_service import get_active_downloads
from services.streaming_service import get_streams, get_stream
from controllers.api import api_bp, init_api_router
from controllers.api.trash_api import trash_bp

# Import database functions
from database import (
    get_connection,
    iter_tracks_with_playlists,
    iter_tracks_with_playlists_filtered,
    get_distinct_resolutions,
    get_distinct_filetypes,
    get_tracks_with_filters_page,
    get_resolution_counts,
    get_filetype_counts,
    get_history_page,
    get_user_setting,
    set_user_setting,
    get_track_with_playlists,
    get_youtube_metadata_by_id,
    get_youtube_metadata_batch,
)

import re
YT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

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

def build_server_info():
    """Build server info dict once per request for templates and APIs."""
    try:
        now = datetime.datetime.now()
        if not SERVER_START_TIME:
            return {
                'pid': os.getpid(),
                'start_time': None,
                'current_time': now.strftime('%Y-%m-%d %H:%M:%S'),
                'uptime': 'N/A',
            }
        uptime = now - SERVER_START_TIME
        uptime_str = str(uptime).split('.')[0]
        return {
            'pid': os.getpid(),
            'start_time': SERVER_START_TIME.strftime('%Y-%m-%d %H:%M:%S'),
            'current_time': now.strftime('%Y-%m-%d %H:%M:%S'),
            'uptime': uptime_str,
        }
    except Exception:
        return None

@app.context_processor
def inject_server_info():
    return { 'server_info': build_server_info() }

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
    
    active_downloads = get_active_downloads()
    return render_template("playlists.html", playlists=playlists, server_ip=_get_local_ip(), 
                          active_downloads=active_downloads)

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

    # Parse filters from query params
    # resolution can be comma-separated and/or repeated multiple times (checkboxes)
    # Support both resolution and resolution[] naming schemes
    raw_resolution_params = request.args.getlist("resolution") + request.args.getlist("resolution[]")
    # Fallback: if only a single 'resolution' present in query string, getlist still returns [value]
    resolutions_selected = []
    for p in raw_resolution_params:
        if p:
            resolutions_selected.extend([s.strip() for s in p.split(",") if s.strip()])
    # Deduplicate while preserving order
    resolutions_selected = list(dict.fromkeys(resolutions_selected))

    # filetypes multi-select (checkboxes)
    raw_filetype_params = request.args.getlist("filetype") + request.args.getlist("filetype[]")
    filetypes_selected = []
    for ft in raw_filetype_params:
        if ft:
            filetypes_selected.extend([s.strip() for s in ft.split(",") if s.strip()])
    filetypes_selected = list(dict.fromkeys(filetypes_selected))

    # Duration range (seconds)
    min_duration = request.args.get("min_duration")
    max_duration = request.args.get("max_duration")
    try:
        min_duration_val = int(min_duration) if (min_duration is not None and str(min_duration).strip() != "") else None
        if min_duration_val is not None and min_duration_val < 0:
            min_duration_val = 0
    except ValueError:
        min_duration_val = None
    try:
        max_duration_val = int(max_duration) if (max_duration is not None and str(max_duration).strip() != "") else None
        if max_duration_val is not None and max_duration_val < 0:
            max_duration_val = 0
    except ValueError:
        max_duration_val = None

    # Bitrate range (kbps in UI → convert to bps for DB)
    min_bitrate = request.args.get("min_bitrate_kbps")
    max_bitrate = request.args.get("max_bitrate_kbps")
    try:
        min_bitrate_bps = int(min_bitrate) * 1000 if (min_bitrate is not None and str(min_bitrate).strip() != "") else None
        if min_bitrate_bps is not None and min_bitrate_bps < 0:
            min_bitrate_bps = 0
    except ValueError:
        min_bitrate_bps = None
    try:
        max_bitrate_bps = int(max_bitrate) * 1000 if (max_bitrate is not None and str(max_bitrate).strip() != "") else None
        if max_bitrate_bps is not None and max_bitrate_bps < 0:
            max_bitrate_bps = 0
    except ValueError:
        max_bitrate_bps = None

    # Size range (MB in UI → convert to bytes for DB)
    min_size_mb = request.args.get("min_size_mb")
    max_size_mb = request.args.get("max_size_mb")
    try:
        min_size_bytes = int(float(min_size_mb) * 1048576) if (min_size_mb is not None and str(min_size_mb).strip() != "") else None
        if min_size_bytes is not None and min_size_bytes < 0:
            min_size_bytes = 0
    except (ValueError, TypeError):
        min_size_bytes = None
    try:
        max_size_bytes = int(float(max_size_mb) * 1048576) if (max_size_mb is not None and str(max_size_mb).strip() != "") else None
        if max_size_bytes is not None and max_size_bytes < 0:
            max_size_bytes = 0
    except (ValueError, TypeError):
        max_size_bytes = None

    # min_likes integer parsing
    min_likes_param = request.args.get("min_likes")
    min_likes = None
    if min_likes_param is not None and str(min_likes_param).strip() != "":
        try:
            min_likes = max(0, int(min_likes_param))
        except ValueError:
            min_likes = None

    # Max YouTube Quality (height) threshold parsing (server-side filter)
    min_max_quality_param = request.args.get("min_max_quality")
    min_max_quality = None
    if min_max_quality_param is not None and str(min_max_quality_param).strip() != "":
        try:
            min_max_quality = max(0, int(min_max_quality_param))
        except ValueError:
            min_max_quality = None

    conn = get_connection()
    try:
        # Facets: list of available resolutions
        facets_resolutions = get_distinct_resolutions(conn)
        facets_filetypes = get_distinct_filetypes(conn)

        # Pagination
        page = request.args.get("page", default=1, type=int)
        per_page = request.args.get("per_page", default=200, type=int)
        if per_page <= 0 or per_page > 1000:
            per_page = 200

        tracks, total_count = get_tracks_with_filters_page(
            conn,
            search_query=search_query if search_query else None,
            include_deleted=include_deleted,
            resolutions=resolutions_selected if resolutions_selected else None,
            filetypes=filetypes_selected if filetypes_selected else None,
            min_duration=min_duration_val,
            max_duration=max_duration_val,
            min_bitrate_bps=min_bitrate_bps,
            max_bitrate_bps=max_bitrate_bps,
            min_size_bytes=min_size_bytes,
            max_size_bytes=max_size_bytes,
            min_likes=min_likes,
            min_max_quality=min_max_quality,
            page=page,
            per_page=per_page,
        )

        # Compute Max YouTube Quality per track for the current page using batch metadata fetch
        max_quality_map = {}
        try:
            video_ids = [t['video_id'] for t in tracks] if tracks else []
            if video_ids:
                metadata_map = get_youtube_metadata_batch(conn, video_ids) or {}
                for vid, row in metadata_map.items():
                    raw_formats = None
                    try:
                        raw_formats = row['available_formats']
                    except Exception:
                        raw_formats = None
                    formats = None
                    try:
                        formats = json.loads(raw_formats) if raw_formats else None
                    except Exception:
                        formats = None
                    max_height = 0
                    if isinstance(formats, list):
                        for f in formats:
                            if not isinstance(f, dict):
                                continue
                            vcodec = str(f.get('vcodec') or '').lower()
                            if not vcodec or vcodec == 'none':
                                continue
                            height = f.get('height')
                            if isinstance(height, (int, float)) and height and height > max_height:
                                max_height = int(height)
                    if max_height > 0:
                        max_quality_map[vid] = f"{max_height}p"
        except Exception:
            # Fail-safe: do not block page rendering on unexpected errors
            max_quality_map = {}

        # Faceted counts (computed excluding the facet itself)
        resolution_counts = get_resolution_counts(
            conn,
            search_query=search_query if search_query else None,
            include_deleted=include_deleted,
            filetypes=filetypes_selected if filetypes_selected else None,
            min_duration=min_duration_val,
            max_duration=max_duration_val,
            min_bitrate_bps=min_bitrate_bps,
            max_bitrate_bps=max_bitrate_bps,
            min_size_bytes=min_size_bytes,
            max_size_bytes=max_size_bytes,
            min_likes=min_likes,
        )
        filetype_counts = get_filetype_counts(
            conn,
            search_query=search_query if search_query else None,
            include_deleted=include_deleted,
            resolutions=resolutions_selected if resolutions_selected else None,
            min_duration=min_duration_val,
            max_duration=max_duration_val,
            min_bitrate_bps=min_bitrate_bps,
            max_bitrate_bps=max_bitrate_bps,
            min_size_bytes=min_size_bytes,
            max_size_bytes=max_size_bytes,
            min_likes=min_likes,
        )
    finally:
        conn.close()
    
    # Filters model passed to template
    filters = {
        "resolutions": resolutions_selected,
        "filetypes": filetypes_selected,
        "min_likes": min_likes if min_likes is not None else "",
        "min_duration": min_duration_val if min_duration_val is not None else "",
        "max_duration": max_duration_val if max_duration_val is not None else "",
        "min_bitrate_kbps": int(min_bitrate_bps/1000) if isinstance(min_bitrate_bps, int) else "",
        "max_bitrate_kbps": int(max_bitrate_bps/1000) if isinstance(max_bitrate_bps, int) else "",
        "min_size_mb": round(min_size_bytes/1048576, 1) if isinstance(min_size_bytes, int) else "",
        "max_size_mb": round(max_size_bytes/1048576, 1) if isinstance(max_size_bytes, int) else "",
        "min_max_quality": min_max_quality if min_max_quality is not None else "",
        "applied": bool(resolutions_selected) or bool(filetypes_selected) or (min_likes is not None) or (min_duration_val is not None) or (max_duration_val is not None) or (min_bitrate_bps is not None) or (max_bitrate_bps is not None) or (min_size_bytes is not None) or (max_size_bytes is not None) or (min_max_quality is not None),
    }
    facets = {
        "resolutions": facets_resolutions,
        "filetypes": facets_filetypes,
        "resolution_counts": resolution_counts if 'resolution_counts' in locals() else {},
        "filetype_counts": filetype_counts if 'filetype_counts' in locals() else {},
    }

    # Pagination info
    pagination = {
        "page": page,
        "per_page": per_page,
        "total": total_count if 'total_count' in locals() else len(tracks),
    }

    return render_template(
        "tracks.html",
        tracks=tracks,
        search_query=search_query,
        include_deleted=include_deleted,
        filters=filters,
        facets=facets,
        pagination=pagination,
        max_quality_map=max_quality_map if 'max_quality_map' in locals() else {},
    )

@app.route("/track")
def track_redirect():
    """Compatibility entry: redirect /track?youtube_id= to canonical /track/<video_id>.

    Accepts youtube_id|video_id|id as query parameter names for flexibility.
    """
    video_id = (request.args.get("youtube_id") or
                request.args.get("video_id") or
                request.args.get("id"))
    if not video_id:
        abort(400)
    if not YT_ID_RE.match(video_id):
        abort(400)
    return redirect(url_for("track_page", video_id=video_id), code=302)

@app.route("/track/<video_id>")
def track_page(video_id: str):
    """Track Detail page.

    Renders a detailed view of track properties and YouTube metadata.
    """
    if not YT_ID_RE.match(video_id):
        abort(400)

    conn = get_connection()
    try:
        track = get_track_with_playlists(conn, video_id)
        if not track:
            abort(404)
        metadata_row = get_youtube_metadata_by_id(conn, video_id)
        # Ensure template receives JSON-serializable dict
        metadata = dict(metadata_row) if metadata_row else None
    finally:
        conn.close()

    # Find on-disk files that match this video_id by filename pattern: *[VIDEO_ID].ext
    same_id_files = []
    same_id_files_info = []
    try:
        if ROOT_DIR:
            import re
            # Match literal [VIDEO_ID] anywhere in the stem (not only at the very end)
            pattern = re.compile(r"\[" + re.escape(video_id) + r"\]")

            # Ensure DB relpath is included if exists on disk
            try:
                db_rel = track.get("relpath") if isinstance(track, dict) else None
                if db_rel:
                    db_abs = (ROOT_DIR / db_rel).resolve()
                    if db_abs.exists() and db_abs.is_file():
                        relp = str(db_abs.relative_to(ROOT_DIR)).replace("\\", "/")
                        if relp not in same_id_files:
                            same_id_files.append(relp)
                            st = db_abs.stat()
                            same_id_files_info.append({
                                "rel": relp,
                                "size_bytes": st.st_size,
                                "size_human": _format_file_size(st.st_size),
                                "modified": datetime.datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                            })
            except Exception:
                pass
            # Scan only this track's parent directory for performance and correctness
            start_dir = None
            try:
                db_rel = track.get("relpath") if isinstance(track, dict) else None
                if db_rel:
                    start_dir = (ROOT_DIR / db_rel).resolve().parent
            except Exception:
                start_dir = None

            search_root = start_dir if start_dir and start_dir.exists() else ROOT_DIR

            for path in search_root.rglob("*.*"):
                try:
                    if not path.is_file():
                        continue
                    if pattern.search(path.stem):
                        rel = str(path.relative_to(ROOT_DIR)).replace("\\", "/")
                        if rel not in same_id_files:
                            same_id_files.append(rel)
                            st = path.stat()
                            same_id_files_info.append({
                                "rel": rel,
                                "size_bytes": st.st_size,
                                "size_human": _format_file_size(st.st_size),
                                "modified": datetime.datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                            })
                except Exception:
                    continue
    except Exception:
        # Fail-safe: do not break page on scanning errors
        same_id_files = []

    # Optional telemetry
    try:
        log_message(f"[Track] View: {video_id}")
    except Exception:
        pass

    # Try to find an image thumbnail among files with the same [VIDEO_ID]
    thumbnail_rel = None
    thumbnail_abs_hint = None
    try:
        preferred_exts = [".webp", ".jpg", ".jpeg", ".png"]
        # Preserve order preference
        for ext in preferred_exts:
            for rel in same_id_files:
                try:
                    if rel.lower().endswith(ext):
                        thumbnail_rel = rel
                        try:
                            if ROOT_DIR:
                                thumbnail_abs_hint = str((ROOT_DIR / rel).resolve())
                        except Exception:
                            thumbnail_abs_hint = None
                        break
                except Exception:
                    continue
            if thumbnail_rel:
                break
    except Exception:
        thumbnail_rel = None

    # Prepare absolute hint for centralized preview location in static/previews
    preview_abs_hint = None
    try:
        # Prefer THUMBNAILS_DIR if configured via env during startup (stored in API shared via init)
        tdir = None
        try:
            from controllers.api.shared import THUMBNAILS_DIR as _TDIR
            tdir = _TDIR
        except Exception:
            tdir = None
        previews_dir = (Path(tdir) if tdir else (Path(app.root_path) / "static" / "previews")).resolve()
        manual = previews_dir / f"{video_id}_manual.png"
        from_yt = previews_dir / f"{video_id}_from_youtube.png"
        from_media = previews_dir / f"{video_id}_from_media_file.png"
        if manual.exists():
            preview_abs_hint = str(manual)
            preview_label = "Manual preview image"
        elif from_yt.exists():
            preview_abs_hint = str(from_yt)
            preview_label = "From YouTube thumbnail"
        elif from_media.exists():
            preview_abs_hint = str(from_media)
            preview_label = "Generated on the fly from media file"
        else:
            # Likely fallback that will be generated on first request
            preview_abs_hint = str(from_media)
            preview_label = "Generated on the fly from media file"
    except Exception:
        preview_abs_hint = None
        preview_label = "Generated on the fly from media file"

    # If adjacent thumbnail is in use, adjust label accordingly
    try:
        if thumbnail_rel:
            preview_label = "From YouTube thumbnail"
    except Exception:
        pass

    return render_template(
        "track.html",
        track=track,
        metadata=metadata,
        video_id=video_id,
        same_id_files=same_id_files,
        same_id_files_info=sorted(same_id_files_info, key=lambda x: x.get('modified') or '' , reverse=True),
        same_id_count=len(same_id_files),
        thumbnail_rel=thumbnail_rel,
        thumbnail_abs_hint=thumbnail_abs_hint,
        preview_abs_hint=preview_abs_hint,
        preview_label=preview_label,
    )

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
    
    return render_template("history.html", history=rows, page=page, has_next=has_next, filters=filter_params, request=request)

@app.route("/backups")
def backups_page():
    """Database Backups Page."""
    return render_template("backups.html")

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

@app.route("/schedules")
def schedules_page():
    """Recurring Schedules management page."""
    return render_template("schedules.html")

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
    return render_template("deleted.html")

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

@app.route("/tests")
def tests_index():
    """Manual tests index page."""
    tests = [
        {
            'id': 'track_detail',
            'name': 'Track Detail Page – Manual Test Plan',
            'description': 'End-to-end manual validation of the /track/<video_id> page.'
        },
    ]
    return render_template('tests/index.html', tests=tests)

@app.route("/tests/track_detail")
def tests_track_detail():
    """Manual test page for Track Detail feature with pass/fail controls."""
    return render_template('tests/track_detail.html')

@app.route("/tests/media_rescan")
def tests_media_rescan():
    """Manual links page for Media Properties Rescan feature."""
    return render_template('tests/media_properties_rescan.html')

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
    server_info = build_server_info()
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
    # Resolve optional thumbnails directory and YouTube config from .env
    thumbnails_dir = None
    yt_timeout = 5.0
    yt_order = None
    preview_priority = None
    try:
        tdir = env_config.get('THUMBNAILS_DIR')
        if tdir:
            thumbnails_dir = Path(tdir).resolve()
            print(f"Using thumbnails directory from .env: {thumbnails_dir}")
        if env_config.get('YOUTUBE_THUMB_TIMEOUT'):
            yt_timeout = float(env_config.get('YOUTUBE_THUMB_TIMEOUT'))
        if env_config.get('YOUTUBE_THUMB_ORDER'):
            raw = env_config.get('YOUTUBE_THUMB_ORDER')
            # Expect comma-separated suffixes (e.g., maxres,sd,hq,mq,default)
            mapping = {
                'maxres': 'maxresdefault.jpg',
                'sd': 'sddefault.jpg',
                'hq': 'hqdefault.jpg',
                'mq': 'mqdefault.jpg',
                'default': 'default.jpg',
            }
            parts = [p.strip().lower() for p in raw.split(',') if p.strip()]
            resolved = [mapping.get(p, p) for p in parts]
            if resolved:
                yt_order = resolved
        if env_config.get('PREVIEW_PRIORITY'):
            rawp = env_config.get('PREVIEW_PRIORITY')
            parts = [p.strip().lower() for p in rawp.split(',') if p.strip()]
            preview_priority = parts if parts else None
    except Exception as _:
        thumbnails_dir = None
    init_api_router(ROOT_DIR, thumbnails_dir, yt_timeout, yt_order, preview_priority)
    
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
    from services.job_workers import ChannelDownloadWorker, MetadataExtractionWorker, CleanupWorker, PlaylistDownloadWorker, BackupWorker, QuickSyncWorker, LibraryScanWorker
    
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
        job_service.register_worker(LibraryScanWorker())
        
        # Start the service
        job_service.start()
        log_message("Job Queue Service started successfully")

        # Start Recurring Scheduler Service (after Job Queue is ready)
        try:
            from services.recurring_scheduler_service import start_recurring_scheduler_service
            start_recurring_scheduler_service(check_interval_seconds=60)
            log_message("Recurring Scheduler Service started successfully")
        except Exception as e:
            log_message(f"Warning: Failed to start Recurring Scheduler Service: {e}")
        
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
        
        # Stop Recurring Scheduler Service
        try:
            from services.recurring_scheduler_service import stop_recurring_scheduler_service
            stop_recurring_scheduler_service()
            log_message("Recurring Scheduler Service stopped successfully")
        except Exception as e:
            log_message(f"Warning: Error stopping Recurring Scheduler Service: {e}")
        
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
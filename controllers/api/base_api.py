"""Base API endpoints for core system operations."""

from pathlib import Path
from flask import Blueprint, request, jsonify
from .shared import ROOT_DIR, get_connection, log_message, record_event
from services.playlist_service import scan_tracks, _ensure_subdir, list_playlists
from services.download_service import get_active_downloads

# Create blueprint
base_bp = Blueprint('base', __name__)

@base_bp.route("/tracks", defaults={"subpath": ""})
@base_bp.route("/tracks/<path:subpath>")
def api_tracks(subpath: str):
    """Get tracks from a directory."""
    base_dir = _ensure_subdir(Path(subpath)) if subpath else ROOT_DIR
    tracks = scan_tracks(base_dir)
    return jsonify(tracks)

@base_bp.route("/playlists")
def api_playlists():
    """Get list of all playlists."""
    return jsonify(list_playlists(ROOT_DIR))

@base_bp.route("/active_downloads")
def api_active_downloads():
    """Get current active downloads status."""
    return jsonify(get_active_downloads())

@base_bp.route("/scan", methods=["POST"])
def api_scan():
    """Scan Playlists directory and update database."""
    try:
        from scan_to_db import scan as scan_library
        scan_library(ROOT_DIR)
        return jsonify({"status": "ok"})
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500

@base_bp.route("/backup", methods=["POST"])
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

@base_bp.route("/backups")
def api_backups():
    """Get list of all database backups."""
    try:
        from database import list_backups
        backups = list_backups(ROOT_DIR)
        return jsonify({"status": "ok", "backups": backups})
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500

@base_bp.route("/event", methods=["POST"])
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
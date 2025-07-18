"""Base API endpoints for core system operations."""

from pathlib import Path
from flask import Blueprint, request, jsonify
from .shared import get_root_dir, get_connection, log_message, record_event
from services.playlist_service import scan_tracks, _ensure_subdir, list_playlists
from services.download_service import get_active_downloads

# Create blueprint
base_bp = Blueprint('base', __name__)

@base_bp.route("/tracks", defaults={"subpath": ""})
@base_bp.route("/tracks/<path:subpath>")
def api_tracks(subpath: str):
    """Get tracks from a directory."""
    root_dir = get_root_dir()
    if not root_dir:
        return jsonify({"error": "Server configuration error"}), 500
    base_dir = _ensure_subdir(Path(subpath)) if subpath else root_dir
    tracks = scan_tracks(base_dir)
    return jsonify(tracks)

@base_bp.route("/playlists")
def api_playlists():
    """Get list of all playlists."""
    root_dir = get_root_dir()
    if not root_dir:
        return jsonify({"error": "Server configuration error"}), 500
    return jsonify(list_playlists(root_dir))

@base_bp.route("/active_downloads")
def api_active_downloads():
    """Get current active downloads status."""
    return jsonify(get_active_downloads())

@base_bp.route("/scan", methods=["POST"])
def api_scan():
    """Scan Playlists directory and update database."""
    try:
        root_dir = get_root_dir()
        if not root_dir:
            return jsonify({"error": "Server configuration error"}), 500
        from scan_to_db import scan as scan_library
        scan_library(root_dir)
        return jsonify({"status": "ok"})
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500

@base_bp.route("/backup", methods=["POST"])
def api_backup():
    """Create database backup."""
    try:
        root_dir = get_root_dir()
        if not root_dir:
            return jsonify({"error": "Server configuration error"}), 500
        from database import create_backup
        result = create_backup(root_dir)
        
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
        root_dir = get_root_dir()
        if not root_dir:
            return jsonify({"error": "Server configuration error"}), 500
        from database import list_backups
        backups = list_backups(root_dir)
        return jsonify({"status": "ok", "backups": backups})
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500

@base_bp.route("/database/maintenance", methods=["POST"])
def api_database_maintenance():
    """Run database maintenance operations."""
    try:
        log_message("Starting database maintenance...")
        
        # Import database optimizer
        from utils.database_optimizer import DatabaseOptimizer
        
        # Create optimizer instance
        optimizer = DatabaseOptimizer()
        
        # Run maintenance with force=True to execute immediately
        result = optimizer.run_maintenance(force=True)
        
        if result.get('success', False):
            log_message(f"Database maintenance completed successfully in {result.get('duration', 0):.2f}s")
            return jsonify({
                "status": "ok",
                "message": "Database maintenance completed successfully",
                "details": result
            })
        else:
            log_message(f"Database maintenance failed: {result.get('reason', 'Unknown error')}")
            return jsonify({
                "status": "error",
                "message": result.get('reason', 'Database maintenance failed')
            }), 500
            
    except Exception as exc:
        log_message(f"Database maintenance error: {exc}")
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
    if not video_id or ev not in {"start", "finish", "next", "prev", "like", "dislike", "play", "pause"}:
        return jsonify({"status": "error", "message": "bad payload"}), 400
    
    conn = get_connection()
    record_event(conn, video_id, ev, position=pos)
    conn.close()
    return jsonify({"status": "ok"})

@base_bp.route("/event_types")
def api_event_types():
    """Get all available event types from the database."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Get all unique event types from play_history table
        cursor.execute("SELECT DISTINCT event FROM play_history ORDER BY event")
        event_types = [row[0] for row in cursor.fetchall()]
        
        conn.close()
        
        log_message(f"[Events] Retrieved {len(event_types)} unique event types: {event_types}")
        return jsonify({
            "status": "ok",
            "event_types": event_types
        })
        
    except Exception as e:
        log_message(f"[Events] Error retrieving event types: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500 
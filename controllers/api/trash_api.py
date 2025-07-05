"""Trash API endpoints."""

import shutil
from pathlib import Path
from flask import Blueprint, request, jsonify

from .shared import get_connection, log_message, get_root_dir, record_event, _format_file_size
import database as db

# Create blueprint
trash_bp = Blueprint('trash', __name__)

@trash_bp.route("/deleted_tracks")
def api_get_deleted_tracks():
    """Get deleted tracks for restoration page."""
    try:
        conn = get_connection()
        deleted_tracks_raw = db.get_deleted_tracks(conn)
        
        # Convert SQLite Row objects to dictionaries for JSON serialization
        deleted_tracks = []
        for row in deleted_tracks_raw:
            track_dict = dict(row)
            deleted_tracks.append(track_dict)
        
        # Get unique channel groups for the filter
        channel_groups = []
        unique_groups = set()
        for track in deleted_tracks:
            group_name = track.get('channel_group')
            if group_name and group_name not in unique_groups:
                unique_groups.add(group_name)
                channel_groups.append({'name': group_name})
        
        # Sort channel groups alphabetically
        channel_groups.sort(key=lambda x: x['name'])
        
        conn.close()
        
        log_message(f"[Restore] Retrieved {len(deleted_tracks)} deleted tracks and {len(channel_groups)} channel groups")
        return jsonify({
            "status": "ok", 
            "tracks": deleted_tracks,
            "channel_groups": channel_groups
        })
        
    except Exception as e:
        log_message(f"[Restore] Error retrieving deleted tracks: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

@trash_bp.route("/restore_track", methods=["POST"])
def api_restore_track():
    """Restore a deleted track."""
    try:
        data = request.get_json() or {}
        track_id = data.get('track_id')
        restore_method = data.get('method', 'file')  # 'file' or 'redownload'
        
        # Validate required fields
        if not track_id:
            return jsonify({"status": "error", "error": "Track ID is required"}), 400
        
        if restore_method not in ['file', 'redownload']:
            return jsonify({"status": "error", "error": "Invalid restore method. Must be 'file' or 'redownload'"}), 400
        
        conn = get_connection()
        
        # TODO: Implement actual restoration logic in Phase 4.2 (Restoration Logic)
        # For now, just mark as restored in database
        result = db.restore_deleted_track(conn, track_id)
        
        if result:
            log_message(f"[Restore] Track {track_id} marked as restored (method: {restore_method})")
            conn.close()
            return jsonify({
                "status": "placeholder", 
                "message": f"Track marked as restored",
                "track_id": track_id,
                "method": restore_method,
                "note": "Actual file restoration implementation coming in Phase 4.2"
            })
        else:
            conn.close()
            return jsonify({"status": "error", "error": "Track not found or already restored"}), 404
        
    except Exception as e:
        log_message(f"[Restore] Error restoring track: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

@trash_bp.route("/trash_stats")
def api_get_trash_stats():
    """Get trash folder statistics (size and file count)."""
    try:
        root_dir = get_root_dir()
        if not root_dir:
            return jsonify({"status": "error", "error": "Server configuration error"}), 500
        
        trash_dir = root_dir.parent / "Trash"
        
        if not trash_dir.exists():
            return jsonify({
                "status": "ok",
                "total_size": 0,
                "total_files": 0,
                "formatted_size": "0 B",
                "trash_path": str(trash_dir)
            })
        
        total_size = 0
        total_files = 0
        
        # Recursively calculate size of all files in trash
        for file_path in trash_dir.rglob("*"):
            if file_path.is_file():
                try:
                    file_size = file_path.stat().st_size
                    total_size += file_size
                    total_files += 1
                except (OSError, PermissionError) as e:
                    log_message(f"[Trash] Warning: Could not access {file_path}: {e}")
                    continue
        
        # Format size for display
        formatted_size = _format_file_size(total_size)
        
        log_message(f"[Trash] Statistics: {total_files} files, {formatted_size}")
        
        return jsonify({
            "status": "ok",
            "total_size": total_size,
            "total_files": total_files,
            "formatted_size": formatted_size,
            "trash_path": str(trash_dir)
        })
        
    except Exception as e:
        log_message(f"[Trash] Error getting trash stats: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

@trash_bp.route("/clear_trash", methods=["POST"])
def api_clear_trash():
    """Clear all files from trash folder (but keep database records)."""
    try:
        data = request.get_json() or {}
        confirm = data.get('confirm', False)
        
        if not confirm:
            return jsonify({"status": "error", "error": "Confirmation required"}), 400
        
        root_dir = get_root_dir()
        if not root_dir:
            return jsonify({"status": "error", "error": "Server configuration error"}), 500
        
        trash_dir = root_dir.parent / "Trash"
        
        if not trash_dir.exists():
            return jsonify({
                "status": "ok",
                "message": "Trash folder is already empty",
                "files_deleted": 0,
                "size_freed": 0
            })
        
        # Get stats before deletion
        files_deleted = 0
        size_freed = 0
        
        for file_path in trash_dir.rglob("*"):
            if file_path.is_file():
                try:
                    file_size = file_path.stat().st_size
                    file_path.unlink()
                    files_deleted += 1
                    size_freed += file_size
                    log_message(f"[Trash] Deleted: {file_path}")
                except (OSError, PermissionError) as e:
                    log_message(f"[Trash] Warning: Could not delete {file_path}: {e}")
                    continue
        
        # Remove empty directories
        try:
            for dir_path in reversed(list(trash_dir.rglob("*"))):
                if dir_path.is_dir() and not list(dir_path.iterdir()):
                    dir_path.rmdir()
                    log_message(f"[Trash] Removed empty directory: {dir_path}")
        except Exception as e:
            log_message(f"[Trash] Warning: Could not remove some empty directories: {e}")
        
        # Update database: mark all deleted tracks as not restorable from file 
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE deleted_tracks
            SET can_restore = 0
            WHERE trash_path IS NOT NULL AND can_restore = 1
        """)
        affected_records = cursor.rowcount
        conn.commit()
        conn.close()
        
        formatted_size = _format_file_size(size_freed)
        
        log_message(f"[Trash] Cleared trash: {files_deleted} files deleted, {formatted_size} freed")
        log_message(f"[Trash] Updated {affected_records} database records (marked as not restorable)")
        
        return jsonify({
            "status": "ok",
            "message": f"Trash cleared successfully",
            "files_deleted": files_deleted,
            "size_freed": size_freed,
            "formatted_size": formatted_size,
            "database_records_updated": affected_records
        })
        
    except Exception as e:
        log_message(f"[Trash] Error clearing trash: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500 
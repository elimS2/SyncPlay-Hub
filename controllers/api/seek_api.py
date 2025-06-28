"""Seek events API endpoints."""

from flask import Blueprint, request, jsonify
from .shared import get_connection, log_message
import database as db

# Create blueprint
seek_bp = Blueprint('seek', __name__)

@seek_bp.route("/seek", methods=["POST"])
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
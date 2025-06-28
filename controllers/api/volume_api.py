"""Volume settings API endpoints."""

from flask import Blueprint, request, jsonify
from .shared import get_connection, log_message
import database as db

# Create blueprint
volume_bp = Blueprint('volume', __name__)

@volume_bp.route("/volume/get")
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

@volume_bp.route("/volume/set", methods=["POST"])
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
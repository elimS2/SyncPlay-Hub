"""Remote control API endpoints."""

import random
import time
from pathlib import Path
from flask import Blueprint, request, jsonify
from .shared import PLAYER_STATE, COMMAND_QUEUE, get_root_dir, get_connection, log_message, record_event
import database as db

# Create blueprint
remote_bp = Blueprint('remote', __name__)

@remote_bp.route("/remote/status")
def api_remote_status():
    """Get current player status for remote control."""
    return jsonify(PLAYER_STATE)

@remote_bp.route("/remote/play", methods=["POST"])
def api_remote_play():
    """Toggle play/pause."""
    global COMMAND_QUEUE
    COMMAND_QUEUE.append({
        'type': 'play',
        'timestamp': time.time()
    })
    
    log_message(f"[Remote] Play/pause command queued. Queue length: {len(COMMAND_QUEUE)}")
    return jsonify({"status": "ok", "command": "queued"})

@remote_bp.route("/remote/next", methods=["POST"])
def api_remote_next():
    """Skip to next track."""
    global COMMAND_QUEUE
    COMMAND_QUEUE.append({
        'type': 'next',
        'timestamp': time.time()
    })
    
    log_message(f"[Remote] Next track command queued. Queue length: {len(COMMAND_QUEUE)}")
    return jsonify({"status": "ok", "command": "queued"})

@remote_bp.route("/remote/prev", methods=["POST"])
def api_remote_prev():
    """Skip to previous track."""
    global COMMAND_QUEUE
    COMMAND_QUEUE.append({
        'type': 'prev',
        'timestamp': time.time()
    })
    
    log_message("[Remote] Previous track command queued")
    return jsonify({"status": "ok", "command": "queued"})

@remote_bp.route("/remote/stop", methods=["POST"])
def api_remote_stop():
    """Stop playback."""
    global PLAYER_STATE
    PLAYER_STATE['playing'] = False
    PLAYER_STATE['progress'] = 0
    PLAYER_STATE['last_update'] = time.time()
    
    log_message("[Remote] Playback stopped")
    return jsonify({"status": "ok"})

@remote_bp.route("/remote/volume", methods=["POST"])
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
        'timestamp': time.time()
    })
    
    log_message(f"[Remote] Volume command queued and saved: {int(volume * 100)}%")
    return jsonify({"status": "ok", "command": "queued"})

@remote_bp.route("/remote/like", methods=["POST"])
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


@remote_bp.route("/remote/dislike", methods=["POST"])
def api_remote_dislike():
    """Dislike current track."""
    global PLAYER_STATE
    if PLAYER_STATE['current_track'] and 'video_id' in PLAYER_STATE['current_track']:
        video_id = PLAYER_STATE['current_track']['video_id']
        
        # Record dislike event in database
        try:
            conn = get_connection()
            record_event(conn, video_id, 'dislike', position=PLAYER_STATE['progress'])
            conn.close()
            
            log_message(f"[Remote] Disliked track: {PLAYER_STATE['current_track'].get('name', 'Unknown')}")
            return jsonify({"status": "ok"})
        except Exception as e:
            log_message(f"[Remote] Error recording dislike: {e}")
            return jsonify({"status": "error", "message": str(e)}), 500
    
    return jsonify({"status": "error", "message": "No current track"}), 400

@remote_bp.route("/remote/shuffle", methods=["POST"])
def api_remote_shuffle():
    """Shuffle playlist."""
    global PLAYER_STATE
    if PLAYER_STATE['playlist']:
        random.shuffle(PLAYER_STATE['playlist'])
        PLAYER_STATE['current_index'] = 0
        PLAYER_STATE['current_track'] = PLAYER_STATE['playlist'][0] if PLAYER_STATE['playlist'] else None
        PLAYER_STATE['progress'] = 0
        PLAYER_STATE['last_update'] = time.time()
        
        log_message("[Remote] Playlist shuffled")
        return jsonify({"status": "ok", "track": PLAYER_STATE['current_track']})
    
    return jsonify({"status": "error", "message": "No playlist loaded"}), 400

@remote_bp.route("/remote/youtube", methods=["POST"])
def api_remote_youtube():
    """Open current track on YouTube."""
    global PLAYER_STATE
    if PLAYER_STATE['current_track'] and 'video_id' in PLAYER_STATE['current_track']:
        video_id = PLAYER_STATE['current_track']['video_id']
        youtube_url = f"https://www.youtube.com/watch?v={video_id}"
        
        log_message(f"[Remote] YouTube link requested: {youtube_url}")
        return jsonify({"status": "ok", "url": youtube_url})
    
    return jsonify({"status": "error", "message": "No current track"}), 400

@remote_bp.route("/remote/fullscreen", methods=["POST"])
def api_remote_fullscreen():
    """Toggle fullscreen (placeholder - actual implementation would be client-side)."""
    log_message("[Remote] Fullscreen toggle requested")
    return jsonify({"status": "ok", "message": "Fullscreen toggle sent to client"})

@remote_bp.route("/remote/sync_internal", methods=["POST"])
def api_remote_sync_internal():
    """Internal sync endpoint for player to update server state."""
    global PLAYER_STATE
    data = request.get_json() or {}
    
    # Get player type from request
    player_type = data.get('player_type', 'regular')
    player_source = data.get('player_source', 'unknown')
    
    # Update server state with player data
    PLAYER_STATE.update(data)
    PLAYER_STATE['last_update'] = time.time()
    PLAYER_STATE['player_type'] = player_type
    PLAYER_STATE['player_source'] = player_source
    
    # Note: Removed frequent sync logging to avoid log spam
    
    return jsonify({"status": "ok"})

@remote_bp.route("/remote/commands")
def api_remote_commands():
    """Get and clear pending remote commands."""
    global COMMAND_QUEUE
    commands = COMMAND_QUEUE.copy()
    COMMAND_QUEUE.clear()
    
    if commands:
        log_message(f"[Remote] Returning {len(commands)} commands to player: {[cmd['type'] for cmd in commands]}")
    
    return jsonify(commands)

@remote_bp.route("/remote/load_playlist", methods=["POST"])
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
            root_dir = get_root_dir()
            if not root_dir:
                return jsonify({"error": "Server configuration error"}), 500
            tracks = scan_tracks(root_dir)
        
        if tracks:
            PLAYER_STATE['playlist'] = tracks
            PLAYER_STATE['current_index'] = 0
            PLAYER_STATE['current_track'] = tracks[0]
            PLAYER_STATE['progress'] = 0
            PLAYER_STATE['playing'] = False
            PLAYER_STATE['last_update'] = time.time()
            
            log_message(f"[Remote] Playlist loaded: {len(tracks)} tracks")
            return jsonify({"status": "ok", "tracks_count": len(tracks)})
        else:
            return jsonify({"status": "error", "message": "No tracks found"}), 400
            
    except Exception as e:
        log_message(f"[Remote] Error loading playlist: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500 
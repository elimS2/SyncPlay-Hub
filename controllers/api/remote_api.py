"""Remote control API endpoints."""

import random
import re
import time
from pathlib import Path
from urllib.parse import unquote

from flask import Blueprint, request, jsonify

from .shared import (
    COMMAND_QUEUE,
    PLAYER_STATE,
    get_connection,
    get_root_dir,
    log_message,
    record_event,
)
from services.playlist_service import list_playlists
import database as db

_LIKES_PLAYER_PATH = re.compile(r"^/likes_player/(\d+)/?$")
_PLAYLIST_PATH = re.compile(r"^/playlist/(.+)/?$")

# Create blueprint
remote_bp = Blueprint('remote', __name__)


def _is_safe_playlist_relpath(rel: str) -> bool:
    """True if rel resolves to a directory under ROOT_DIR (no path traversal)."""
    root_dir = get_root_dir()
    if not root_dir or not rel or ".." in rel:
        return False
    try:
        root_resolved = root_dir.resolve()
        requested_abs = (root_dir / rel).resolve()
        if root_resolved not in requested_abs.parents and requested_abs != root_resolved:
            return False
        return requested_abs.is_dir()
    except (OSError, ValueError, RuntimeError):
        return False


def validate_switch_source_path(path: str) -> bool:
    """Allow only /likes_player/<int> or /playlist/<relpath> pointing at a real folder under ROOT_DIR."""
    if not path or not isinstance(path, str):
        return False
    path = path.strip()
    if not path.startswith("/") or ".." in path:
        return False
    if _LIKES_PLAYER_PATH.match(path):
        return True
    m = _PLAYLIST_PATH.match(path)
    if not m:
        return False
    rel = unquote(m.group(1)).strip().strip("/")
    if not rel:
        return False
    return _is_safe_playlist_relpath(rel)

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
    PLAYER_STATE['volume'] = volume

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
    global PLAYER_STATE, COMMAND_QUEUE
    if PLAYER_STATE['current_track'] and 'video_id' in PLAYER_STATE['current_track']:
        video_id = PLAYER_STATE['current_track']['video_id']
        
        # Record like event in database
        try:
            conn = get_connection()
            record_event(conn, video_id, 'like', position=PLAYER_STATE['progress'])
            conn.close()
            
            # Update like state in PLAYER_STATE
            PLAYER_STATE['like_active'] = True
            PLAYER_STATE['dislike_active'] = False  # Reset dislike when liking
            PLAYER_STATE['last_update'] = time.time()
            
            # Add command to queue for player synchronization
            COMMAND_QUEUE.append({
                'type': 'like',
                'timestamp': time.time()
            })
            
            log_message(f"[Remote] Liked track: {PLAYER_STATE['current_track'].get('name', 'Unknown')}")
            return jsonify({"status": "ok"})
        except Exception as e:
            log_message(f"[Remote] Error recording like: {e}")
            return jsonify({"status": "error", "message": str(e)}), 500
    
    return jsonify({"status": "error", "message": "No current track"}), 400


@remote_bp.route("/remote/dislike", methods=["POST"])
def api_remote_dislike():
    """Dislike current track."""
    global PLAYER_STATE, COMMAND_QUEUE
    if PLAYER_STATE['current_track'] and 'video_id' in PLAYER_STATE['current_track']:
        video_id = PLAYER_STATE['current_track']['video_id']
        
        # Record dislike event in database
        try:
            conn = get_connection()
            record_event(conn, video_id, 'dislike', position=PLAYER_STATE['progress'])
            conn.close()
            
            # Update dislike state in PLAYER_STATE
            PLAYER_STATE['dislike_active'] = True
            PLAYER_STATE['like_active'] = False  # Reset like when disliking
            PLAYER_STATE['last_update'] = time.time()
            
            # Add command to queue for player synchronization
            COMMAND_QUEUE.append({
                'type': 'dislike',
                'timestamp': time.time()
            })
            
            log_message(f"[Remote] Disliked track: {PLAYER_STATE['current_track'].get('name', 'Unknown')}")
            return jsonify({"status": "ok"})
        except Exception as e:
            log_message(f"[Remote] Error recording dislike: {e}")
            return jsonify({"status": "error", "message": str(e)}), 500
    
    return jsonify({"status": "error", "message": "No current track"}), 400

@remote_bp.route("/remote/delete", methods=["POST"])
def api_remote_delete():
    """Delete current track."""
    global PLAYER_STATE, COMMAND_QUEUE
    if PLAYER_STATE['current_track'] and 'video_id' in PLAYER_STATE['current_track']:
        video_id = PLAYER_STATE['current_track']['video_id']
        
        # Add command to queue for player synchronization with remote flag
        COMMAND_QUEUE.append({
            'type': 'delete',
            'timestamp': time.time(),
            'from_remote': True  # Flag to indicate this came from remote control
        })
        
        log_message(f"[Remote] Delete command queued for track: {PLAYER_STATE['current_track'].get('name', 'Unknown')}")
        return jsonify({"status": "ok", "command": "queued"})
    
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

    def _track_vid(track):
        if not track or not isinstance(track, dict):
            return None
        return track.get('video_id')

    prev_vid = _track_vid(PLAYER_STATE.get('current_track'))

    # Get player type from request
    player_type = data.get('player_type', 'regular')
    player_source = data.get('player_source', 'unknown')

    # Update server state with player data
    PLAYER_STATE.update(data)
    PLAYER_STATE['last_update'] = time.time()
    PLAYER_STATE['player_type'] = player_type
    PLAYER_STATE['player_source'] = player_source

    new_vid = _track_vid(PLAYER_STATE.get('current_track'))
    if prev_vid != new_vid:
        # Periodic sync omits like_active/dislike_active; do not carry session reactions to a new track.
        if 'like_active' not in data:
            PLAYER_STATE['like_active'] = False
        if 'dislike_active' not in data:
            PLAYER_STATE['dislike_active'] = False

    # Note: Removed frequent sync logging to avoid log spam

    return jsonify({"status": "ok"})

@remote_bp.route("/remote/playlist_sources")
def api_remote_playlist_sources():
    """Folders and virtual (by net likes) player URLs for the remote playlist picker."""
    root_dir = get_root_dir()
    if not root_dir:
        return jsonify({"status": "error", "message": "Server configuration error"}), 500
    try:
        from .playlist_api import compute_like_stats_list

        conn = get_connection()
        like_stats = compute_like_stats_list(conn)
        conn.close()
    except Exception as e:
        log_message(f"[Remote] playlist_sources like_stats failed: {e}")
        like_stats = []

    regular = []
    for p in list_playlists(root_dir):
        regular.append(
            {
                "path": p["url"],
                "name": p["name"],
                "count": p["count"],
                "label": f"{p['name']} ({p['count']} tracks)",
            }
        )

    virtual = []
    for row in like_stats:
        if not row.get("count"):
            continue
        likes = row["likes"]
        virtual.append(
            {
                "path": f"/likes_player/{likes}",
                "likes": likes,
                "count": row["count"],
                "label": f"❤️ {likes} net likes — {row['count']} tracks",
            }
        )

    return jsonify({"status": "ok", "regular": regular, "virtual": virtual})


@remote_bp.route("/remote/switch_source", methods=["POST"])
def api_remote_switch_source():
    """Tell the TV/browser player to open another playlist URL (navigation)."""
    global COMMAND_QUEUE
    data = request.get_json() or {}
    path = (data.get("path") or "").strip()
    if not validate_switch_source_path(path):
        return jsonify({"status": "error", "message": "Invalid or unknown playlist path"}), 400
    COMMAND_QUEUE.append(
        {
            "type": "switch_source",
            "path": path,
            "timestamp": time.time(),
        }
    )
    log_message(f"[Remote] Switch player source queued: {path}")
    return jsonify({"status": "ok", "command": "queued"})


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
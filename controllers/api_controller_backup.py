"""API endpoints controller."""

# Imports moved to controllers/api/shared.py

# Create blueprint
api_bp = Blueprint('api', __name__, url_prefix='/api')

# Global variables moved to controllers/api/shared.py

# ========================================
# BASE API ENDPOINTS (MOVED)
# ========================================
# Base endpoints moved to controllers/api/base_api.py:
# - /tracks, /playlists, /active_downloads, /scan, /backup, /backups, /event

# ==========================================
# PLAYLIST API ENDPOINTS moved to controllers/api/playlist_api.py
# ==========================================
# Playlist endpoints moved:
# - /add_playlist (POST) - complex worker with threading
# - /resync (POST) - resync existing playlist
# - /link_playlist (POST) - link playlist to URL

# ========================================
# SYSTEM CONTROL API ENDPOINTS (MOVED)
# ========================================
# System endpoints moved to controllers/api/system_api.py:
# - /restart, /stop

# -------- STREAMING API ENDPOINTS --------

# ========================================
# STREAMING API ENDPOINTS (MOVED)
# ========================================
# Streaming endpoints moved to controllers/api/streaming_api.py:
# - /streams, /create_stream, /stream_event, /stream_feed

# ========================================
# FILE BROWSER API ENDPOINTS (MOVED)
# ========================================
# Browser endpoints moved to controllers/api/browser_api.py:
# - /browse, /download_file

# ========================================
# REMOTE CONTROL API ENDPOINTS (MOVED)
# ========================================
# Remote control endpoints moved to controllers/api/remote_api.py:
# - /remote/status, /remote/play, /remote/next, /remote/prev, /remote/stop
# - /remote/volume, /remote/like, /remote/shuffle, /remote/youtube, /remote/fullscreen
# - /remote/sync_internal, /remote/commands, /remote/load_playlist (13 endpoints)

# ==============================
# VOLUME SETTINGS API ENDPOINTS  
# ==============================

# Volume endpoints moved to controllers/api/volume_api.py

# ========================================
# SEEK EVENTS API ENDPOINTS (MOVED)
# ========================================
# Seek endpoint moved to controllers/api/seek_api.py 

# ========================================
# CHANNELS SYSTEM API ENDPOINTS (MOVED)
# ========================================
# All channels endpoints moved to controllers/api/channels_api.py:
# - /channel_groups, /channels/<int:group_id>, /create_channel_group
# - /add_channel, /sync_channel_group/<int:group_id>, /sync_channel/<int:channel_id>
# - /refresh_channel_stats/<int:channel_id>, /deleted_tracks, /restore_track
# - /delete_track, /remove_channel/<int:channel_id>


# ==========================================
# JOB QUEUE API ENDPOINTS moved to controllers/api/jobs_api.py
# ========================================== 
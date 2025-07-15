"""Playlist API endpoints."""

import re
import threading
from pathlib import Path
from flask import Blueprint, request, jsonify

from .shared import get_root_dir, get_connection, log_message
from services.download_service import add_active_download, update_download_status, remove_active_download
import database as db

# Create blueprint
playlist_bp = Blueprint('playlist', __name__)

@playlist_bp.route("/add_playlist", methods=["POST"])
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
    from yt_dlp.utils import sanitize_filename

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
                # Update status for specific progress messages
                if "Quick scan in progress" in msg:
                    update_download_status(task_id, "initial scan")
                elif "Quick scan completed" in msg:
                    update_download_status(task_id, "scan complete")
            
            title, _ids = fetch_playlist_metadata(url, debug=False, progress_callback=metadata_progress_callback)
            log_message(f"[AddPlaylist] Metadata fetched successfully: {title} | Task ID: {task_id}")
            
            folder_name = sanitize_filename(title, restricted=True)
            root_dir = get_root_dir()
            if not root_dir:
                log_message(f"[AddPlaylist] Error: ROOT_DIR not initialized")
                remove_active_download(task_id)
                return
                
            target_dir = root_dir / folder_name
            
            # Check if already exists
            if target_dir.exists():
                log_message(f"[AddPlaylist] Playlist already exists: {title} | Task ID: {task_id}")
                remove_active_download(task_id)
                return
            
            # Update task with real title
            from services.download_service import _downloads_lock, ACTIVE_DOWNLOADS
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
        
        from utils.logging_utils import LOGS_DIR
        LOGS_DIR_LOCAL = LOGS_DIR or (Path.cwd() / "Logs")
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
                    
                    _dl_playlist(url, root_dir, audio_only=False, sync=True, debug=False, progress_callback=progress_callback)
                    
                    # Update status to finalizing
                    update_download_status(task_id, "updating database")
                    
                    from scan_to_db import scan as scan_library  # local import
                    scan_library(root_dir)
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

    threading.Thread(target=_worker, daemon=True).start()
    return jsonify({"status": "started"})

@playlist_bp.route("/resync", methods=["POST"])
def api_resync():
    """Resync an existing playlist."""
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
        
        from utils.logging_utils import LOGS_DIR
        LOGS_DIR_LOCAL = LOGS_DIR or (Path.cwd() / "Logs")
        log_path = LOGS_DIR_LOCAL / "download_playlist.log"
        
        # Log start to both main server log and download log
        start_msg = f"[Resync] Starting resync: {folder_name} | URL: {url} | Task ID: {task_id} | Logging to {log_path}"
        log_message(start_msg)
        
        with open(log_path, "a", encoding="utf-8", buffering=1) as lf:
            # Custom print function that writes to both file and main log
            def dual_print(msg, flush=True):
                # Write to download log file
                print(msg, file=lf, flush=flush)
                # Also log important messages to main server log
                if any(keyword in msg for keyword in ["[START]", "[DONE]", "[ERROR]", "[Info] Playlist contains", "[Info] Detailed scan completed"]):
                    log_message(f"[Resync] {msg}")
            
            # Redirect stdout/stderr to file only, but keep dual logging for important messages
            with contextlib.redirect_stdout(lf), contextlib.redirect_stderr(lf):
                dual_print("="*60)
                dual_print(f"[START] {datetime.datetime.now():%Y-%m-%d %H:%M:%S} | Resync: {folder_name} | URL: {url}")
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
                    root_dir = get_root_dir()
                    if not root_dir:
                        error_msg = f"[ERROR] ROOT_DIR not initialized"
                        dual_print(error_msg)
                        update_download_status(task_id, "error")
                        return
                        
                    _dl_playlist(url, root_dir, audio_only=False, sync=True, debug=False, progress_callback=progress_callback)
                    
                    # Update status to finalizing
                    update_download_status(task_id, "updating database")
                    
                    from scan_to_db import scan as scan_library
                    scan_library(root_dir)
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

    threading.Thread(target=_worker, daemon=True).start()
    return jsonify({"status": "started"})

@playlist_bp.route("/link_playlist", methods=["POST"])
def api_link_playlist():
    """Link existing playlist to URL."""
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

@playlist_bp.route("/tracks_by_likes/<int:like_count>", methods=["GET"])
def api_tracks_by_likes(like_count):
    """Get all tracks that have exactly the specified number of likes."""
    try:
        from database import get_dislike_counts_batch
        conn = get_connection()
        
        # Step 1: Get all tracks with basic data (no subqueries for performance)
        # Still filter by include_in_likes but calculate net_likes in code
        query = """
        SELECT 
            t.video_id,
            COALESCE(ym.title, t.name) as name,
            t.relpath,
            t.duration,
            t.play_likes,
            t.play_starts,
            t.play_finishes,
            t.play_nexts,
            t.play_prevs,
            t.last_start_ts,
            t.last_finish_ts,
            COALESCE(t.last_finish_ts, t.last_start_ts) as last_play,
            ym.timestamp,
            ym.release_timestamp,
            ym.release_year,
            ym.title as youtube_title,
            ym.channel,
            ym.duration as youtube_duration,
            ym.duration_string as youtube_duration_string,
            ym.view_count as youtube_view_count,
            ym.uploader,
            ym.channel_url,
            ym.uploader_url,
            ym.uploader_id,
            ym.updated_at as youtube_metadata_updated,
            t.size_bytes
        FROM tracks t
        LEFT JOIN youtube_video_metadata ym ON ym.youtube_id = t.video_id
        LEFT JOIN channels ch ON (
            ch.url = ym.channel_url OR 
            ch.url LIKE '%' || ym.channel || '%' OR 
            ym.channel_url LIKE '%' || ch.url || '%' OR
            -- NEW: Match @channelname format from uploader_id and uploader_url
            (ym.uploader_id IS NOT NULL AND (
                ch.url LIKE '%' || ym.uploader_id || '%' OR
                ch.url LIKE '%' || REPLACE(ym.uploader_id, '@', '') || '%'
            )) OR
            (ym.uploader_url IS NOT NULL AND (
                ch.url LIKE '%' || REPLACE(REPLACE(ym.uploader_url, 'https://www.youtube.com/', ''), '/videos', '') || '%'
            ))
        )
        LEFT JOIN channel_groups cg ON cg.id = ch.channel_group_id
        WHERE t.video_id NOT IN (SELECT video_id FROM deleted_tracks)
            AND (cg.include_in_likes = 1)
        ORDER BY COALESCE(ym.title, t.name)
        """
        
        cursor = conn.execute(query)
        all_tracks = cursor.fetchall()
        
        # Step 2: Get all video IDs for batch processing
        video_ids = [row[0] for row in all_tracks if row[0]]  # row[0] is video_id
        
        # Step 3: Get all dislike counts in one batch query
        dislike_counts = get_dislike_counts_batch(conn, video_ids)
        
        # Step 4: Process tracks and filter by like_count
        tracks = []
        for row in all_tracks:
            video_id = row[0]
            play_likes = row[4] or 0
            
            # Calculate net likes (likes - dislikes)
            play_dislikes = dislike_counts.get(video_id, 0)
            net_likes = play_likes - play_dislikes
            
            # Filter by requested like count
            if net_likes != like_count:
                continue
            
            # Convert to format expected by player.js
            track = {
                "video_id": video_id,
                "name": row[1],
                "relpath": row[2],
                "duration": row[3] or 0,
                "play_likes": play_likes,
                "play_starts": row[5] or 0,
                "play_finishes": row[6] or 0,
                "play_nexts": row[7] or 0,
                "play_prevs": row[8] or 0,
                "last_start_ts": row[9],
                "last_finish_ts": row[10],
                "last_play": row[11],
                "timestamp": row[12],  # YouTube publish timestamp
                "release_timestamp": row[13],
                "release_year": row[14],
                "play_dislikes": play_dislikes,  # From batch query
                "net_likes": net_likes,  # Calculated in code
                "url": f"/media/{row[2]}",  # Use relpath, not video_id
                
                # Add YouTube metadata fields for tooltips (matching scan_tracks format)
                "youtube_title": row[15],
                "youtube_channel": row[16],
                "youtube_duration": row[17],
                "youtube_duration_string": row[18],
                "youtube_view_count": row[19],
                "youtube_uploader": row[20],
                "youtube_channel_url": row[21],
                "youtube_uploader_url": row[22],
                "youtube_uploader_id": row[23],
                "youtube_metadata_updated": row[24],
                "size_bytes": row[25] or 0,  # Add file size for tooltip
                
                # Add properly named timestamp fields for compatibility
                "youtube_timestamp": row[12],
                "youtube_release_timestamp": row[13],
                "youtube_release_year": row[14]
            }
            
            # Add channel handle (@channelname) info - same logic as scan_tracks
            channel_handle = None
            if row[21] and '@' in row[21]:  # channel_url
                url_parts = row[21].split('@')
                if len(url_parts) > 1:
                    channel_handle = '@' + url_parts[1].split('/')[0]
            elif row[22] and '@' in row[22]:  # uploader_url
                url_parts = row[22].split('@')
                if len(url_parts) > 1:
                    channel_handle = '@' + url_parts[1].split('/')[0]
            elif row[23] and row[23].startswith('@'):  # uploader_id
                channel_handle = row[23]
            
            if channel_handle:
                track["youtube_channel_handle"] = channel_handle
            
            tracks.append(track)
        
        conn.close()
        
        log_message(f"[Virtual Playlist] Found {len(tracks)} tracks with {like_count} likes (optimized)")
        
        return jsonify({
            "status": "ok",
            "tracks": tracks,
            "like_count": like_count,
            "total_tracks": len(tracks)
        })
        
    except Exception as e:
        log_message(f"[Virtual Playlist] Error getting tracks by likes: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@playlist_bp.route("/like_stats", methods=["GET"])
def api_like_stats():
    """Get statistics about tracks grouped by like count."""
    try:
        from database import get_dislike_counts_batch
        conn = get_connection()
        
        # Step 1: Get all tracks with basic data (no subqueries for performance)
        query = """
        SELECT 
            t.video_id,
            t.play_likes,
            COALESCE(ym.title, t.name) as name
        FROM tracks t
        LEFT JOIN youtube_video_metadata ym ON ym.youtube_id = t.video_id
        LEFT JOIN channels ch ON (
            ch.url = ym.channel_url OR 
            ch.url LIKE '%' || ym.channel || '%' OR 
            ym.channel_url LIKE '%' || ch.url || '%' OR
            -- NEW: Match @channelname format from uploader_id and uploader_url
            (ym.uploader_id IS NOT NULL AND (
                ch.url LIKE '%' || ym.uploader_id || '%' OR
                ch.url LIKE '%' || REPLACE(ym.uploader_id, '@', '') || '%'
            )) OR
            (ym.uploader_url IS NOT NULL AND (
                ch.url LIKE '%' || REPLACE(REPLACE(ym.uploader_url, 'https://www.youtube.com/', ''), '/videos', '') || '%'
            ))
        )
        LEFT JOIN channel_groups cg ON cg.id = ch.channel_group_id
        WHERE t.video_id NOT IN (SELECT video_id FROM deleted_tracks)
            AND (cg.include_in_likes = 1)
        ORDER BY name
        """
        
        cursor = conn.execute(query)
        all_tracks = cursor.fetchall()
        
        # Step 2: Get all video IDs for batch processing  
        video_ids = [row[0] for row in all_tracks if row[0]]  # row[0] is video_id
        
        # Step 3: Get all dislike counts in one batch query
        dislike_counts = get_dislike_counts_batch(conn, video_ids)
        
        # Step 4: Process tracks and group by net_likes
        like_groups = {}  # net_likes -> list of track names
        
        for row in all_tracks:
            video_id = row[0]
            play_likes = row[1] or 0
            track_name = row[2] or "Unknown"
            
            # Calculate net likes (likes - dislikes)
            play_dislikes = dislike_counts.get(video_id, 0)
            net_likes = play_likes - play_dislikes
            
            # Only include tracks with net_likes >= 0
            if net_likes >= 0:
                if net_likes not in like_groups:
                    like_groups[net_likes] = []
                
                # Add track name (truncated for samples)
                track_sample = track_name[:30] + "..." if len(track_name) > 30 else track_name
                like_groups[net_likes].append(track_sample)
        
        # Step 5: Build response
        like_stats = []
        for net_likes in sorted(like_groups.keys()):
            tracks_in_group = like_groups[net_likes]
            count = len(tracks_in_group)
            
            # Limit sample to first 3 tracks
            sample_parts = tracks_in_group[:3]
            if len(tracks_in_group) > 3:
                sample_parts.append("...")
            
            like_stats.append({
                "likes": net_likes,  # Using net_likes (likes - dislikes) as "likes"
                "count": count,
                "sample_tracks": " • ".join(sample_parts)
            })
        
        conn.close()
        
        return jsonify({
            "status": "ok",
            "like_stats": like_stats,
            "total_categories": len(like_stats)
        })
        
    except Exception as e:
        log_message(f"[Virtual Playlist] Error getting like stats: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@playlist_bp.route("/save_display_preference", methods=["POST"])
def api_save_display_preference():
    """Save display preference for a playlist and sync with matching channel group."""
    data = request.get_json(force=True, silent=True) or {}
    relpath = (data.get("relpath") or "").strip()
    preference = (data.get("preference") or "").strip()
    
    if not relpath or not preference:
        return jsonify({"status": "error", "message": "missing relpath or preference"}), 400

    # Validate preference value
    valid_preferences = ["shuffle", "smart", "order_by_date"]
    if preference not in valid_preferences:
        return jsonify({"status": "error", "message": f"invalid preference, must be one of: {valid_preferences}"}), 400

    try:
        conn = get_connection()
        
        # Check if playlist exists
        row = db.get_playlist_by_relpath(conn, relpath)
        if not row:
            conn.close()
            return jsonify({"status": "error", "message": "playlist not found"}), 404

        playlist_name = row["name"]
        
        # Update display preference for playlist
        conn.execute("UPDATE playlists SET display_preferences=? WHERE relpath=?", (preference, relpath))
        
        # Check if there's a channel group with the same name
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, behavior_type, play_order FROM channel_groups WHERE name = ?", (playlist_name,))
        channel_group = cursor.fetchone()
        
        channel_group_updated = False
        if channel_group:
            group_id, group_name, behavior_type, current_play_order = channel_group
            
            # Map playlist preference to channel group play_order
            new_play_order = None
            
            if preference == "shuffle":
                new_play_order = "random"
            elif preference == "smart":
                # For smart preference, use behavior-specific default
                if behavior_type == "music":
                    new_play_order = "random"
                elif behavior_type == "news":
                    new_play_order = "newest_first"
                elif behavior_type == "education":
                    new_play_order = "oldest_first"
                elif behavior_type == "podcasts":
                    new_play_order = "newest_first"
                else:
                    new_play_order = "random"  # fallback
            elif preference == "order_by_date":
                new_play_order = "oldest_first"
            
            # Update channel group play_order if it's different
            if new_play_order and new_play_order != current_play_order:
                cursor.execute("UPDATE channel_groups SET play_order = ? WHERE id = ?", (new_play_order, group_id))
                channel_group_updated = True
                log_message(f"[Channel Group Sync] Updated play_order for group '{group_name}' from '{current_play_order}' to '{new_play_order}'")
        
        conn.commit()
        conn.close()
        
        message = f"Display preference saved: {preference}"
        if channel_group_updated:
            message += f" (also updated matching channel group)"
        
        log_message(f"[Playlist Preferences] Saved '{preference}' for playlist '{relpath}'" + 
                   (f" and synced with channel group '{playlist_name}'" if channel_group_updated else ""))
        return jsonify({"status": "ok", "message": message})
        
    except Exception as e:
        log_message(f"[Playlist Preferences] Error saving preference: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@playlist_bp.route("/get_display_preference", methods=["GET"])
def api_get_display_preference():
    """Get display preference for a playlist."""
    relpath = request.args.get("relpath", "").strip()
    
    if not relpath:
        return jsonify({"status": "error", "message": "missing relpath parameter"}), 400

    try:
        conn = get_connection()
        
        # Get playlist with display preference
        row = db.get_playlist_by_relpath(conn, relpath)
        if not row:
            conn.close()
            return jsonify({"status": "error", "message": "playlist not found"}), 404
        
        # Get display preference or default to shuffle
        display_preference = row["display_preferences"] if row["display_preferences"] else "shuffle"
        
        conn.close()
        
        return jsonify({
            "status": "ok", 
            "preference": display_preference,
            "playlist_name": row["name"] if row["name"] else "Unknown"
        })
        
    except Exception as e:
        log_message(f"[Playlist Preferences] Error getting preference: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@playlist_bp.route("/save_playback_speed", methods=["POST"])
def api_save_playback_speed():
    """Save playback speed for a playlist."""
    data = request.get_json(force=True, silent=True) or {}
    relpath = (data.get("relpath") or "").strip()
    speed = data.get("speed")
    
    if not relpath or speed is None:
        return jsonify({"status": "error", "message": "missing relpath or speed"}), 400

    # Validate speed value
    valid_speeds = [0.5, 0.75, 1, 1.25, 1.5, 1.75, 2, 2.5]
    if speed not in valid_speeds:
        return jsonify({"status": "error", "message": f"invalid speed, must be one of: {valid_speeds}"}), 400

    try:
        conn = get_connection()
        
        # Check if playlist exists
        row = db.get_playlist_by_relpath(conn, relpath)
        if not row:
            conn.close()
            return jsonify({"status": "error", "message": "playlist not found"}), 404

        # Update playback speed
        conn.execute("UPDATE playlists SET playback_speed=? WHERE relpath=?", (speed, relpath))
        conn.commit()
        conn.close()
        
        log_message(f"[Playlist Speed] Saved '{speed}x' for playlist '{relpath}'")
        return jsonify({"status": "ok", "message": f"Playback speed saved: {speed}x"})
        
    except Exception as e:
        log_message(f"[Playlist Speed] Error saving speed: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@playlist_bp.route("/get_playback_speed", methods=["GET"])
def api_get_playback_speed():
    """Get playback speed for a playlist."""
    relpath = request.args.get("relpath", "").strip()
    
    if not relpath:
        return jsonify({"status": "error", "message": "missing relpath parameter"}), 400

    try:
        conn = get_connection()
        
        # Get playlist with playback speed
        row = db.get_playlist_by_relpath(conn, relpath)
        if not row:
            conn.close()
            return jsonify({"status": "error", "message": "playlist not found"}), 404
        
        # Get playback speed or default to 1.0
        playback_speed = row["playback_speed"] if row["playback_speed"] else 1.0
        
        conn.close()
        
        return jsonify({
            "status": "ok", 
            "speed": playback_speed,
            "playlist_name": row["name"] if row["name"] else "Unknown"
        })
        
    except Exception as e:
        log_message(f"[Playlist Speed] Error getting speed: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@playlist_bp.route("/get_playlist_settings", methods=["GET"])
def api_get_playlist_settings():
    """Get all settings for a playlist (display preference and playback speed)."""
    relpath = request.args.get("relpath", "").strip()
    
    if not relpath:
        return jsonify({"status": "error", "message": "missing relpath parameter"}), 400

    try:
        conn = get_connection()
        
        # Get playlist with all settings
        row = db.get_playlist_by_relpath(conn, relpath)
        if not row:
            conn.close()
            return jsonify({"status": "error", "message": "playlist not found"}), 404
        
        # Get settings or defaults
        display_preference = row["display_preferences"] if row["display_preferences"] else "shuffle"
        playback_speed = row["playback_speed"] if row["playback_speed"] else 1.0
        
        conn.close()
        
        return jsonify({
            "status": "ok", 
            "display_preference": display_preference,
            "playback_speed": playback_speed,
            "playlist_name": row["name"] if row["name"] else "Unknown"
        })
        
    except Exception as e:
        log_message(f"[Playlist Settings] Error getting settings: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500 

 
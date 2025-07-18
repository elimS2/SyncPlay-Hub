"""Channel Files API endpoints."""

import re
import threading
import shutil
import datetime
import subprocess
from pathlib import Path
from flask import Blueprint, request, jsonify

from .shared import get_connection, log_message, get_root_dir, record_event
import database as db

# Create blueprint
channels_files_bp = Blueprint('channels_files', __name__)

@channels_files_bp.route("/delete_track", methods=["POST"])
def api_delete_track():
    """Delete a track from playlist by moving it to trash."""
    try:
        data = request.get_json() or {}
        video_id = data.get('video_id')
        
        log_message(f"[Delete] DEBUG: Received delete request")
        log_message(f"[Delete] DEBUG: Request data: {data}")
        log_message(f"[Delete] DEBUG: Video ID: {video_id}")
        
        # Validate required fields
        if not video_id:
            log_message(f"[Delete] ERROR: No video_id provided in request")
            return jsonify({"status": "error", "error": "Video ID is required"}), 400
        
        conn = get_connection()
        
        # Get track information from database
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, name, relpath, video_id, channel_group
            FROM tracks 
            WHERE video_id = ?
        """, (video_id,))
        
        track = cursor.fetchone()
        if not track:
            log_message(f"[Delete] ERROR: Track not found in database for video_id: {video_id}")
            
            # Let's try to find this track by searching for similar patterns
            log_message(f"[Delete] DEBUG: Searching for tracks with similar video_id patterns...")
            cursor.execute("""
                SELECT id, name, relpath, video_id, channel_group
                FROM tracks 
                WHERE video_id LIKE ?
                ORDER BY id DESC
                LIMIT 5
            """, (f"%{video_id}%",))
            
            similar_tracks = cursor.fetchall()
            if similar_tracks:
                log_message(f"[Delete] DEBUG: Found {len(similar_tracks)} tracks with similar video_id:")
                for i, sim_track in enumerate(similar_tracks):
                    log_message(f"[Delete] DEBUG:   {i+1}. ID:{sim_track[0]} video_id:'{sim_track[3]}' name:'{sim_track[1]}'")
            else:
                log_message(f"[Delete] DEBUG: No tracks found with similar video_id patterns")
            
            # Try to find by filename pattern
            filename_pattern = f"%{video_id}%"
            cursor.execute("""
                SELECT id, name, relpath, video_id, channel_group
                FROM tracks 
                WHERE name LIKE ? OR relpath LIKE ?
                ORDER BY id DESC
                LIMIT 5
            """, (filename_pattern, filename_pattern))
            
            filename_matches = cursor.fetchall()
            if filename_matches:
                log_message(f"[Delete] DEBUG: Found {len(filename_matches)} tracks with filename pattern:")
                for i, match_track in enumerate(filename_matches):
                    log_message(f"[Delete] DEBUG:   {i+1}. ID:{match_track[0]} video_id:'{match_track[3]}' name:'{match_track[1]}'")
            else:
                log_message(f"[Delete] DEBUG: No tracks found with filename pattern")
            
            # Check if there are ANY tracks from the same channel/folder
            log_message(f"[Delete] DEBUG: Checking for tracks in Channel-Halsey folder...")
            cursor.execute("""
                SELECT id, name, relpath, video_id, channel_group
                FROM tracks 
                WHERE relpath LIKE '%Channel-Halsey%'
                ORDER BY id DESC
                LIMIT 5
            """)
            
            halsey_tracks = cursor.fetchall()
            if halsey_tracks:
                log_message(f"[Delete] DEBUG: Found {len(halsey_tracks)} tracks in Channel-Halsey:")
                for i, halsey_track in enumerate(halsey_tracks):
                    log_message(f"[Delete] DEBUG:   {i+1}. ID:{halsey_track[0]} video_id:'{halsey_track[3]}' path:'{halsey_track[2]}'")
            else:
                log_message(f"[Delete] DEBUG: No tracks found in Channel-Halsey folder in database!")
            
            # Show some recent tracks for context
            cursor.execute("""
                SELECT id, name, relpath, video_id, channel_group
                FROM tracks 
                ORDER BY id DESC
                LIMIT 3
            """)
            
            recent_tracks = cursor.fetchall()
            if recent_tracks:
                log_message(f"[Delete] DEBUG: Last 3 tracks in database for reference:")
                for i, rec_track in enumerate(recent_tracks):
                    log_message(f"[Delete] DEBUG:   {i+1}. ID:{rec_track[0]} video_id:'{rec_track[3]}' name:'{rec_track[1]}'")
            
            # Check total track count
            cursor.execute("SELECT COUNT(*) FROM tracks")
            total_count = cursor.fetchone()[0]
            log_message(f"[Delete] DEBUG: Total tracks in database: {total_count}")
            
            # Try to scan this specific file and see what video_id it would extract
            log_message(f"[Delete] DEBUG: Attempting to simulate file scan for debugging...")
            
            # Get the file path that was being played
            media_path = data.get('file_path', '')  # We need to add this to the request
            if not media_path:
                log_message(f"[Delete] DEBUG: No file_path provided, cannot simulate scan")
            else:
                import re
                from pathlib import Path
                
                # Decode URL encoding if present
                from urllib.parse import unquote
                decoded_path = unquote(media_path)
                log_message(f"[Delete] DEBUG: Media path from request: {decoded_path}")
                
                # Extract filename
                file_path = Path(decoded_path)
                file_stem = file_path.stem
                log_message(f"[Delete] DEBUG: File stem for regex: '{file_stem}'")
                
                # Apply same regex as scan_tracks
                video_id_match = re.search(r"\[([A-Za-z0-9_-]{11})\]$", file_stem)
                extracted_video_id = video_id_match.group(1) if video_id_match else None
                
                log_message(f"[Delete] DEBUG: Regex match result: {video_id_match}")
                log_message(f"[Delete] DEBUG: Extracted video_id from filename: '{extracted_video_id}'")
                log_message(f"[Delete] DEBUG: Requested video_id: '{video_id}'")
                log_message(f"[Delete] DEBUG: video_id match: {extracted_video_id == video_id}")
            
            conn.close()
            return jsonify({"status": "error", "error": "Track not found in database. Please rescan files first."}), 404
        
        track_id = track[0]
        track_name = track[1]
        track_relpath = track[2]
        channel_group = track[4] if track[4] else 'Unknown'
        
        log_message(f"[Delete] DEBUG: Found track in database:")
        log_message(f"[Delete] DEBUG: - Track ID: {track_id}")
        log_message(f"[Delete] DEBUG: - Track Name: {track_name}")
        log_message(f"[Delete] DEBUG: - Relative Path: {track_relpath}")
        log_message(f"[Delete] DEBUG: - Video ID: {video_id}")
        log_message(f"[Delete] DEBUG: - Channel Group: {channel_group}")
        
        # Construct full file path
        root_dir = get_root_dir()
        if not root_dir:
            log_message(f"[Delete] ERROR: ROOT_DIR not initialized")
            return jsonify({"status": "error", "error": "Server configuration error"}), 500
            
        log_message(f"[Delete] DEBUG: ROOT_DIR: {root_dir}")
        
        full_file_path = root_dir / track_relpath
        log_message(f"[Delete] DEBUG: Full file path to delete: {full_file_path}")
        log_message(f"[Delete] DEBUG: Full file path absolute: {full_file_path.resolve()}")
        log_message(f"[Delete] DEBUG: File exists check: {full_file_path.exists()}")
        
        if not full_file_path.exists():
            log_message(f"[Delete] ERROR: File not found on disk: {full_file_path}")
            log_message(f"[Delete] ERROR: Attempted to access: {full_file_path.resolve()}")
            return jsonify({"status": "error", "error": "File not found on disk"}), 404
        
        # Extract channel name from YouTube metadata for trash organization
        # Based on user requirement: D:\music\Youtube\Playlists\Trash\@channelname\videos\
        channel_folder = "Unknown"
        log_message(f"[Delete] Analyzing track path: {track_relpath}")
        
        # Try to get channel info from youtube_video_metadata first
        try:
            cursor.execute("""
                SELECT channel, channel_url, uploader_url
                FROM youtube_video_metadata 
                WHERE youtube_id = ?
            """, (video_id,))
            
            metadata = cursor.fetchone()
            if metadata:
                channel_name = metadata[0]  # channel
                channel_url = metadata[1]   # channel_url
                uploader_url = metadata[2]  # uploader_url
                
                # Extract @channelname from URLs
                extracted_name = None
                
                # Try channel_url first (e.g., https://www.youtube.com/@halsey)
                if channel_url and '@' in channel_url:
                    url_parts = channel_url.split('@')
                    if len(url_parts) > 1:
                        extracted_name = url_parts[1].split('/')[0]
                        log_message(f"[Delete] Extracted @{extracted_name} from channel_url: {channel_url}")
                
                # Try uploader_url as backup (e.g., https://www.youtube.com/@halsey)
                elif uploader_url and '@' in uploader_url:
                    url_parts = uploader_url.split('@')
                    if len(url_parts) > 1:
                        extracted_name = url_parts[1].split('/')[0]
                        log_message(f"[Delete] Extracted @{extracted_name} from uploader_url: {uploader_url}")
                
                # Use extracted name if found, otherwise use channel name
                if extracted_name:
                    channel_folder = extracted_name.replace(' ', '_')
                elif channel_name:
                    channel_folder = channel_name.replace(' ', '_')
                
                log_message(f"[Delete] Using YouTube metadata channel: {channel_folder}")
            else:
                log_message(f"[Delete] No YouTube metadata found for video_id: {video_id}")
        except Exception as e:
            log_message(f"[Delete] Error getting YouTube metadata: {e}")
        
        # Fallback to path-based extraction if metadata didn't work
        if channel_folder == "Unknown":
            if "Channel-" in track_relpath:
                # Extract channel name from path like "New Music/Channel-Artist/video.mp4"
                channel_match = re.search(r'Channel-([^/\\]+)', track_relpath)
                if channel_match:
                    channel_folder = channel_match.group(1).replace(' ', '_')
                    log_message(f"[Delete] Extracted from Channel- pattern: {channel_folder}")
                else:
                    log_message(f"[Delete] Found Channel- in path but failed to extract name")
            else:
                # For regular playlists, use the playlist name as channel
                path_parts = Path(track_relpath).parts
                if len(path_parts) > 0:
                    channel_folder = path_parts[0].replace(' ', '_')
                    log_message(f"[Delete] Using playlist name as channel: {channel_folder}")
        
        log_message(f"[Delete] Final channel folder for trash: {channel_folder}")
        
        # Create trash directory structure: Trash/channelname/videos/
        # ROOT_DIR points to D:\music\Youtube\Playlists, so we need to go up one level for Trash
        trash_dir = root_dir.parent / "Trash" / channel_folder / "videos"
        trash_dir.mkdir(parents=True, exist_ok=True)
        
        # Sanitize filename for Windows filesystem compatibility
        def sanitize_filename(filename):
            """Remove or replace invalid characters for Windows filesystem"""
            # Invalid characters for Windows: < > : " | ? * and control chars
            invalid_chars = '<>:"|?*'
            sanitized = filename
            for char in invalid_chars:
                sanitized = sanitized.replace(char, '_')
            # Also replace control characters
            sanitized = ''.join(c if ord(c) >= 32 else '_' for c in sanitized)
            return sanitized.strip()
        
        # Generate unique filename in trash if file already exists
        sanitized_name = sanitize_filename(full_file_path.name)
        target_file = trash_dir / sanitized_name
        
        if target_file.exists():
            # Add timestamp to avoid conflicts
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            name_parts = sanitized_name.rsplit('.', 1)
            if len(name_parts) == 2:
                new_name = f"{name_parts[0]}_{timestamp}.{name_parts[1]}"
            else:
                new_name = f"{sanitized_name}_{timestamp}"
            target_file = trash_dir / new_name
            
        log_message(f"[Delete] Sanitized filename: {full_file_path.name} → {target_file.name}")
        
        # Move file to trash with retry mechanism for Windows file locks
        import time
        
        def move_file_with_retry(source_path, target_path, max_retries=3, delay=0.5):
            """
            Move file with retry mechanism to handle Windows file locks.
            
            Args:
                source_path: Source file path
                target_path: Target file path  
                max_retries: Maximum number of retry attempts
                delay: Delay between retries in seconds
                
            Returns:
                True if successful, False otherwise
            """
            for attempt in range(max_retries + 1):
                try:
                    if attempt > 0:
                        # Wait before retry
                        log_message(f"[Delete] Retry attempt {attempt}/{max_retries} after {delay}s delay...")
                        time.sleep(delay)
                        
                        # Check if file is still being used
                        try:
                            # Try to open file in exclusive mode to check if it's locked
                            with open(source_path, 'r+b') as test_file:
                                pass  # File is not locked
                            log_message(f"[Delete] File appears to be unlocked, proceeding with move...")
                        except (OSError, IOError) as lock_error:
                            if attempt == max_retries:
                                log_message(f"[Delete] File still locked after {max_retries} retries: {lock_error}")
                                return False
                            else:
                                log_message(f"[Delete] File still locked, will retry: {lock_error}")
                                continue
                    
                    log_message(f"[Delete] Attempting to move file (attempt {attempt + 1}/{max_retries + 1})")
                    log_message(f"[Delete] Moving file: {source_path} → {target_path}")
                    
                    shutil.move(source_path, target_path)
                    log_message(f"[Delete] SUCCESS: File moved successfully on attempt {attempt + 1}")
                    return True
                    
                except OSError as e:
                    # Check if this is a Windows file lock error
                    if "being used by another process" in str(e) or "WinError 32" in str(e):
                        log_message(f"[Delete] Attempt {attempt + 1} failed with file lock error: {e}")
                        if attempt == max_retries:
                            log_message(f"[Delete] Final attempt failed - file is locked by another process")
                            return False
                        # Continue to next retry
                        continue
                    else:
                        # Different error, don't retry
                        log_message(f"[Delete] Move failed with non-lock error: {e}")
                        return False
                except Exception as e:
                    log_message(f"[Delete] Move failed with unexpected error: {e}")
                    return False
            
            return False
        
        try:
            # Convert to absolute paths to avoid relative path issues
            source_path = str(full_file_path.resolve())
            target_path = str(target_file.resolve())
            
            log_message(f"[Delete] DEBUG: Preparing to move file:")
            log_message(f"[Delete] DEBUG: - Source path: {source_path}")
            log_message(f"[Delete] DEBUG: - Target path: {target_path}")
            log_message(f"[Delete] DEBUG: - Target directory exists: {target_file.parent.exists()}")
            log_message(f"[Delete] DEBUG: - Source file exists: {full_file_path.exists()}")
            log_message(f"[Delete] DEBUG: - Source file readable: {full_file_path.is_file()}")
            
            # Add small initial delay to give client time to release file
            log_message(f"[Delete] Waiting briefly for client to release file lock...")
            time.sleep(0.3)
            
            # Attempt file move with retry mechanism
            move_success = move_file_with_retry(source_path, target_path)
            
            if not move_success:
                error_msg = "Failed to move file to trash - file may still be in use by media player. Please try again in a moment."
                log_message(f"[Delete] ERROR: {error_msg}")
                return jsonify({"status": "error", "error": error_msg}), 500
            
            # Calculate trash_path relative to ROOT_DIR parent (D:\music\Youtube)
            trash_path = str(target_file.relative_to(root_dir.parent))
            log_message(f"[Delete] SUCCESS: Moved to trash: {track_name} → {trash_path}")
            log_message(f"[Delete] DEBUG: Target file created successfully: {target_file.exists()}")
            
        except Exception as e:
            log_message(f"[Delete] ERROR: Unexpected error during file move: {e}")
            log_message(f"[Delete] ERROR: Exception type: {type(e).__name__}")
            log_message(f"[Delete] ERROR: Source path: {source_path}")
            log_message(f"[Delete] ERROR: Target path: {target_path}")
            return jsonify({"status": "error", "error": f"Failed to move file to trash: {e}"}), 500
        
        # Record deletion in database with full path information
        full_source_path = str(full_file_path)
        full_target_path = str(target_file)
        db.record_track_deletion(
            conn, 
            video_id, 
            track_name, 
            track_relpath, 
            deletion_reason='manual_delete',
            channel_group=channel_folder,
            trash_path=trash_path,
            additional_data=f"deleted_from_playlist_ui,move_from:{full_source_path},move_to:{full_target_path}"
        )
        
        conn.close()
        
        log_message(f"[Delete] Successfully deleted track {video_id} ({track_name}) to trash")
        return jsonify({
            "status": "ok",
            "message": f"Track moved to trash: {channel_folder}/videos/{target_file.name}",
            "video_id": video_id,
            "track_name": track_name,
            "trash_path": trash_path
        })
        
    except Exception as e:
        log_message(f"[Delete] Error deleting track: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

@channels_files_bp.route("/rescan_files", methods=["POST"])
def api_rescan_files():
    """Rescan all files and add missing tracks to database."""
    try:
        root_dir = get_root_dir()
        if not root_dir:
            return jsonify({"status": "error", "error": "ROOT_DIR not initialized"}), 500
        
        log_message(f"[Rescan] Starting file rescan from: {root_dir}")
        
        # Import scan functionality
        from pathlib import Path
        import subprocess
        
        MEDIA_EXTS = {".mp3", ".m4a", ".opus", ".webm", ".flac", ".mp4", ".mkv", ".mov"}
        VIDEO_ID_RE = re.compile(r"\[([A-Za-z0-9_-]{11})\]$")
        
        def get_video_id(stem: str):
            m = VIDEO_ID_RE.search(stem)
            return m.group(1) if m else None
        
        def ffprobe_duration(path: Path):
            try:
                res = subprocess.run([
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration:stream=bit_rate,width,height",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    str(path)
                ], capture_output=True, text=True, check=True, timeout=10)
                lines = res.stdout.strip().split("\n")
                duration = float(lines[0]) if lines else None
                bitrate = None
                resolution = None
                for line in lines[1:]:
                    if not bitrate and line.isdigit():
                        bitrate = int(line)
                    elif "x" in line and line.replace("x", "").replace("N/A", "").isdigit():
                        resolution = line
                return duration, bitrate, resolution
            except Exception:
                return None, None, None
        
        # Scan all directories
        conn = get_connection()
        total_added = 0
        total_playlists = 0
        
        for playlist_dir in root_dir.iterdir():
            if not playlist_dir.is_dir():
                continue
            
            # Check if has media files
            has_media = any(p.suffix.lower() in MEDIA_EXTS for p in playlist_dir.rglob("*.*"))
            if not has_media:
                continue
            
            playlist_rel = str(playlist_dir.relative_to(root_dir))
            log_message(f"[Rescan] Processing playlist: {playlist_dir.name}")
            
            # Upsert playlist
            playlist_id = db.upsert_playlist(conn, playlist_dir.name, playlist_rel)
            total_playlists += 1
            
            count = 0
            processed_track_ids = set()
            
            for file in playlist_dir.rglob("*.*"):
                if file.suffix.lower() not in MEDIA_EXTS or not file.is_file():
                    continue
                
                video_id = get_video_id(file.stem)
                if not video_id:
                    continue  # Skip files without recognized ID
                
                # Check if track already exists
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM tracks WHERE video_id = ?", (video_id,))
                existing = cursor.fetchone()
                
                if existing:
                    track_id = existing[0]
                    log_message(f"[Rescan] Track exists: {video_id}")
                else:
                    # Add new track
                    duration, bitrate, resolution = ffprobe_duration(file)
                    size_bytes = file.stat().st_size
                    track_id = db.upsert_track(
                        conn,
                        video_id=video_id,
                        name=file.stem,
                        relpath=str(file.relative_to(root_dir)),
                        duration=duration,
                        size_bytes=size_bytes,
                        bitrate=bitrate,
                        resolution=resolution,
                        filetype=file.suffix.lstrip(".").lower(),
                    )
                    total_added += 1
                    log_message(f"[Rescan] Added track: {video_id} - {file.stem}")
                
                # Link to playlist
                db.link_track_playlist(conn, track_id, playlist_id)
                processed_track_ids.add(track_id)
                count += 1
            
            # Remove stale links
            cursor = conn.cursor()
            cursor.execute("SELECT track_id FROM track_playlists WHERE playlist_id=?", (playlist_id,))
            existing_links = {row[0] for row in cursor.fetchall()}
            to_remove = existing_links - processed_track_ids
            if to_remove:
                cursor.executemany(
                    "DELETE FROM track_playlists WHERE playlist_id=? AND track_id=?",
                    [(playlist_id, tid) for tid in to_remove],
                )
                conn.commit()
            
            # Update playlist stats
            db.update_playlist_stats(conn, playlist_id, count)
            log_message(f"[Rescan] Playlist {playlist_dir.name}: {count} tracks")
        
        conn.close()
        
        log_message(f"[Rescan] Completed: {total_added} new tracks added to {total_playlists} playlists")
        return jsonify({
            "status": "ok", 
            "message": f"Rescan completed: {total_added} new tracks added to {total_playlists} playlists",
            "tracks_added": total_added,
            "playlists_processed": total_playlists
        })
        
    except Exception as e:
        log_message(f"[Rescan] Error during file rescan: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500 
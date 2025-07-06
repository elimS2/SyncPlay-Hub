"""Service for playlist operations and file scanning."""

import re
from pathlib import Path
from typing import List, Dict, Optional
from flask import url_for

# Media file extensions are hardcoded in functions to match original web_player.py

# Global ROOT_DIR variable
ROOT_DIR = None

def set_root_dir(root_dir: Path):
    """Set the global ROOT_DIR variable."""
    global ROOT_DIR
    ROOT_DIR = root_dir

def _get_last_play_ts(video_id: str) -> Optional[str]:
    """Get the last play timestamp for a video."""
    if not video_id:
        return None
    from database import get_connection
    try:
        conn = get_connection()
        row = conn.execute("SELECT last_start_ts, last_finish_ts FROM tracks WHERE video_id=?", (video_id,)).fetchone()
        conn.close()
        if not row:
            return None
        ts1 = row["last_start_ts"]
        ts2 = row["last_finish_ts"]
        # return latest
        if ts1 and ts2:
            return ts1 if ts1 > ts2 else ts2
        return ts1 or ts2
    except Exception:
        return None

def _get_track_stats(video_id: str) -> dict:
    """Get track statistics for a video."""
    if not video_id:
        return {}
    from database import get_connection
    try:
        conn = get_connection()
        # Get basic stats from tracks table
        row = conn.execute(
            "SELECT play_starts, play_finishes, play_nexts, play_prevs, play_likes FROM tracks WHERE video_id=?", 
            (video_id,)
        ).fetchone()
        
        # Get dislike count from play_history table
        dislike_count = conn.execute(
            "SELECT COUNT(*) FROM play_history WHERE video_id=? AND event='dislike'", 
            (video_id,)
        ).fetchone()[0]
        
        conn.close()
        if not row:
            return {"play_dislikes": dislike_count or 0}
        return {
            "play_starts": row["play_starts"] or 0,
            "play_finishes": row["play_finishes"] or 0,
            "play_nexts": row["play_nexts"] or 0,
            "play_prevs": row["play_prevs"] or 0,
            "play_likes": row["play_likes"] or 0,
            "play_dislikes": dislike_count or 0
        }
    except Exception:
        return {}

def scan_tracks(scan_root: Path) -> List[dict]:
    """Scan a directory for media files and return track information, using YouTube metadata if available."""
    from database import get_connection, get_youtube_metadata_by_id
    
    # Get ROOT_DIR from global scope (set by init function)
    root_dir = globals().get('ROOT_DIR')
    if not root_dir:
        raise RuntimeError("ROOT_DIR not set. Call set_root_dir() first.")
    
    conn = get_connection()
    tracks = []
    
    for file in scan_root.rglob("*.*"):
        if file.suffix.lower() in {".mp3", ".m4a", ".opus", ".webm", ".flac", ".mp4", ".mkv", ".mov"} and file.is_file():
            # Extract video ID from filename pattern: Title [VIDEO_ID].ext (must be at end)
            video_id_match = re.search(r"\[([A-Za-z0-9_-]{11})\]$", file.stem)
            video_id = video_id_match.group(1) if video_id_match else None
            
            # Calculate path relative to ROOT_DIR (not scan_root)
            rel_to_root = file.relative_to(root_dir)
            
            # Try to get YouTube metadata if video_id exists
            display_name = file.stem  # Default to filename
            youtube_metadata = None
            if video_id:
                try:
                    metadata_row = get_youtube_metadata_by_id(conn, video_id)
                    if metadata_row:
                        title = metadata_row['title'] if 'title' in metadata_row.keys() else None
                        if title:
                            display_name = title
                            youtube_metadata = metadata_row
                except Exception as e:
                    # If metadata lookup fails, keep using filename
                    print(f"Warning: Failed to get YouTube metadata for {video_id}: {e}")
                    pass
            
            track_data = {
                "name": display_name,
                "relpath": str(rel_to_root).replace("\\", "/"),
                "url": url_for("media", filename=str(rel_to_root).replace("\\", "/")),
                "video_id": video_id,
                "last_play": _get_last_play_ts(video_id) if video_id else None,
            }
            
            # Add track statistics if video_id exists
            if video_id:
                track_stats = _get_track_stats(video_id)
                track_data.update(track_stats)
            
            # Add YouTube metadata if available
            if youtube_metadata:
                try:
                    keys = youtube_metadata.keys()
                    if 'title' in keys:
                        track_data["youtube_title"] = youtube_metadata['title']
                    if 'channel' in keys:
                        track_data["youtube_channel"] = youtube_metadata['channel']
                    if 'duration' in keys:
                        track_data["youtube_duration"] = youtube_metadata['duration']
                    if 'duration_string' in keys:
                        track_data["youtube_duration_string"] = youtube_metadata['duration_string']
                    if 'view_count' in keys:
                        track_data["youtube_view_count"] = youtube_metadata['view_count']
                    if 'uploader' in keys:
                        track_data["youtube_uploader"] = youtube_metadata['uploader']
                    # Add date fields for tooltip
                    if 'timestamp' in keys:
                        track_data["youtube_timestamp"] = youtube_metadata['timestamp']
                    if 'release_timestamp' in keys:
                        track_data["youtube_release_timestamp"] = youtube_metadata['release_timestamp']
                    if 'release_year' in keys:
                        track_data["youtube_release_year"] = youtube_metadata['release_year']
                    # Add metadata sync information for tooltip
                    if 'updated_at' in keys:
                        track_data["youtube_metadata_updated"] = youtube_metadata['updated_at']
                except Exception as e:
                    print(f"Warning: Error processing YouTube metadata for {video_id}: {e}")
            
            tracks.append(track_data)
    
    conn.close()
    return tracks

def _ensure_subdir(requested: Path) -> Path:
    """Return absolute path under ROOT_DIR or abort 404 if traversal is attempted."""
    from flask import abort
    try:
        if not ROOT_DIR:
            raise ValueError("ROOT_DIR not set")
        
        # Ensure the resolved path is inside ROOT_DIR (prevent path traversal)
        requested_abs = (ROOT_DIR / requested).resolve()
        if ROOT_DIR not in requested_abs.parents and requested_abs != ROOT_DIR:
            raise ValueError
        return requested_abs
    except Exception:
        abort(404)

def list_playlists(root: Path) -> List[dict]:
    """Return first-level sub-directories that contain at least one media file."""
    from database import get_connection
    
    # Fetch meta from DB once
    meta = {}
    try:
        conn = get_connection()
        for row in conn.execute(
            """
            SELECT p.id, p.relpath, p.track_count, p.last_sync_ts, p.source_url,
                   COALESCE(SUM(t.play_starts + t.play_nexts + t.play_prevs + t.play_finishes),0) AS play_total,
                   COALESCE(SUM(t.play_likes),0) AS like_total,
                   COALESCE(SUM(CASE WHEN (t.last_start_ts IS NULL AND t.last_finish_ts IS NULL) OR 
                                         COALESCE(t.last_finish_ts, t.last_start_ts) < datetime('now','-30 days') THEN 1 ELSE 0 END),0) AS forgotten_total
            FROM playlists p
            LEFT JOIN track_playlists tp ON tp.playlist_id = p.id
            LEFT JOIN tracks t ON t.id = tp.track_id
            GROUP BY p.id
            """):
            meta[row[1]] = {
                "track_count": row[2],
                "last_sync_ts": row[3],
                "source_url": row[4],
                "play_total": row[5],
                "like_total": row[6],
                "forgotten_total": row[7],
            }
        conn.close()
    except Exception:
        pass

    playlists = []
    # root is now PLAYLISTS_DIR directly (like original)
    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        # does this dir contain at least one media file (recursively)?
        has_media = any(p.suffix.lower() in {".mp3", ".m4a", ".opus", ".webm", ".flac", ".mp4", ".mkv", ".mov"} for p in d.rglob("*.*"))
        if has_media:
            # Since ROOT_DIR now points to Playlists/, rel should be just the folder name
            rel = d.name  # Just the folder name, like "TopMusic6"
            # In the original structure, playlists in DB are stored as folder name only
            dbinfo = meta.get(d.name)  # Look up by folder name only
            count = dbinfo["track_count"] if dbinfo and dbinfo["track_count"] is not None else "?"
            last_sync_str = dbinfo["last_sync_ts"][:16].replace("T", " ") if dbinfo and dbinfo["last_sync_ts"] else "-"
            has_source = bool(dbinfo and dbinfo["source_url"])
            playlists.append({
                "name": d.name,
                "relpath": rel,
                "url": url_for("playlist_page", playlist_path=rel),
                "count": count,
                "last_sync": last_sync_str,
                "has_source": has_source,
                "plays": dbinfo.get("play_total", 0) if dbinfo else 0,
                "likes": dbinfo.get("like_total", 0) if dbinfo else 0,
                "forgotten": dbinfo.get("forgotten_total", 0) if dbinfo else 0,
            })
    
    # Sort by forgotten count (descending) by default
    playlists.sort(key=lambda x: x["forgotten"], reverse=True)
    
    return playlists 
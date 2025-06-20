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

def scan_tracks(scan_root: Path) -> List[dict]:
    """Scan a directory for media files and return track information."""
    from database import get_connection
    
    # Get ROOT_DIR from global scope (set by init function)
    root_dir = globals().get('ROOT_DIR')
    if not root_dir:
        raise RuntimeError("ROOT_DIR not set. Call set_root_dir() first.")
    
    tracks = []
    for file in scan_root.rglob("*.*"):
        if file.suffix.lower() in {".mp3", ".m4a", ".opus", ".webm", ".flac", ".mp4", ".mkv", ".mov"} and file.is_file():
            # Extract video ID from filename pattern: Title [VIDEO_ID].ext (must be at end)
            video_id_match = re.search(r"\[([A-Za-z0-9_-]{11})\]$", file.stem)
            video_id = video_id_match.group(1) if video_id_match else None
            
            # Calculate path relative to ROOT_DIR (not scan_root)
            rel_to_root = file.relative_to(root_dir)
            
            tracks.append({
                "name": file.stem,
                "relpath": str(rel_to_root).replace("\\", "/"),
                "url": url_for("media", filename=str(rel_to_root).replace("\\", "/")),
                "video_id": video_id,
                "last_play": _get_last_play_ts(video_id) if video_id else None,
            })
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
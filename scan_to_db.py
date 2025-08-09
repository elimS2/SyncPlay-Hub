#!/usr/bin/env python3
"""Scan media folder and populate SQLite database with track & playlist metadata.

Usage:
    python scan_to_db.py --root downloads

The script relies on file naming scheme 'Title [VIDEO_ID].ext' to obtain the
unique YouTube video ID. It uses ffprobe (bundled with ffmpeg) to read duration
and stream info.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import time
from pathlib import Path
from typing import Optional

import database as db
from database import get_connection, upsert_playlist, upsert_track, link_track_playlist, update_playlist_stats
from utils.logging_utils import log_message  # Unified logging system

MEDIA_EXTS = {".mp3", ".m4a", ".opus", ".webm", ".flac", ".mp4", ".mkv", ".mov"}
VIDEO_ID_RE = re.compile(r"\[([A-Za-z0-9_-]{11})\]$")


def get_video_id(stem: str) -> Optional[str]:
    m = VIDEO_ID_RE.search(stem)
    if m:
        return m.group(1)
    return None


def ffprobe_duration(path: Path) -> Optional[float]:
    """Deprecated: use utils.media_probe.ffprobe_media_properties instead.

    Kept for backward compatibility. Returns (duration, bitrate, resolution)
    like before, now by delegating to the shared utility.
    """
    try:
        from utils.media_probe import ffprobe_media_properties
        duration, bitrate, resolution = ffprobe_media_properties(path)
        return duration, bitrate, resolution
    except Exception:
        return None, None, None


def scan(playlists_dir: Path):
    scan_start = time.time()
    print(f"[SCAN] Starting scan of: {playlists_dir} - {time.strftime('%H:%M:%S')}")
    
    # Count total directories first for progress tracking
    all_dirs = [d for d in playlists_dir.iterdir() if d.is_dir()]
    print(f"[SCAN] Found {len(all_dirs)} directories to check")
    
    conn = get_connection()
    
    # OPTIMIZATION: Load all existing tracks into memory
    load_start = time.time()
    print(f"[SCAN] Loading existing tracks from database... - {time.strftime('%H:%M:%S')}")
    cur = conn.cursor()
    cur.execute("SELECT id, video_id, relpath, duration FROM tracks")
    existing_tracks = {row[1]: {'id': row[0], 'relpath': row[2], 'duration': row[3]} for row in cur.fetchall()}
    load_time = time.time() - load_start
    print(f"[SCAN] Loaded {len(existing_tracks)} existing tracks in {load_time:.2f}s - {time.strftime('%H:%M:%S')}")
    
    # OPTIMIZATION: Use autocommit for faster individual operations
    # With most files being skipped, autocommit is more efficient than batch transactions
    
    total_playlists = 0
    total_tracks = 0
    total_ffprobe_calls = 0
    total_ffprobe_skipped = 0
    total_files_skipped = 0
    total_files_no_id = 0
    
    for i, playlist_dir in enumerate(all_dirs, 1):
        playlist_start = time.time()
        print(f"\n[SCAN] [{i}/{len(all_dirs)}] Checking: {playlist_dir.name} - {time.strftime('%H:%M:%S')}")
        
        # Check has media
        media_files = [p for p in playlist_dir.rglob("*.*") if p.suffix.lower() in MEDIA_EXTS and p.is_file()]
        if not media_files:
            print(f"[SCAN]   No media files found, skipping")
            continue
            
        print(f"[SCAN]   Found {len(media_files)} media files")
        
        playlist_rel = str(playlist_dir.relative_to(playlists_dir))
        playlist_id = upsert_playlist(conn, playlist_dir.name, playlist_rel)
        total_playlists += 1

        count = 0
        new_tracks = 0
        processed_track_ids = set()
        files_no_id = 0
        
        for j, file in enumerate(media_files, 1):
            if j % 50 == 0 or j == len(media_files):  # Progress every 50 files or at end
                print(f"[SCAN]   Processing files: {j}/{len(media_files)} - {time.strftime('%H:%M:%S')}")
                
            video_id = get_video_id(file.stem)
            if not video_id:
                total_files_no_id += 1
                files_no_id += 1
                continue  # skip files without recognised ID
                
            # OPTIMIZATION: Use in-memory data instead of SQL queries
            current_relpath = str(file.relative_to(playlists_dir))
            
            # Check if track exists in memory
            existing_track = existing_tracks.get(video_id)
            
            # OPTIMIZATION: If file exists in DB with same path, skip ALL processing
            if existing_track and existing_track['relpath'] == current_relpath:
                # File unchanged, just ensure playlist link exists
                track_id = existing_track['id']
                link_track_playlist(conn, track_id, playlist_id)
                processed_track_ids.add(track_id)
                total_ffprobe_skipped += 1
                total_files_skipped += 1
                count += 1  # Count this file!
                continue
            
            # File is new or path changed, need full processing
            size_bytes = file.stat().st_size
            
            # Determine if we need to probe metadata
            needs_metadata = True
            if existing_track:
                has_duration = existing_track['duration'] is not None
                # Skip ffprobe if we have duration (even if path changed)
                if has_duration:
                    needs_metadata = False
            
            if needs_metadata:
                duration, bitrate, resolution = ffprobe_duration(file)
                total_ffprobe_calls += 1
            else:
                # Use existing metadata (will be preserved by upsert_track)
                duration, bitrate, resolution = None, None, None
                total_ffprobe_skipped += 1
            
            track_id = upsert_track(
                conn,
                video_id=video_id,
                name=file.stem,
                relpath=current_relpath,
                duration=duration,
                size_bytes=size_bytes,
                bitrate=bitrate,
                resolution=resolution,
                filetype=file.suffix.lstrip(".").lower(),
            )
            
            # Count as new only if it didn't exist before
            if not existing_track:
                new_tracks += 1
                
            link_track_playlist(conn, track_id, playlist_id)
            processed_track_ids.add(track_id)
            count += 1

        # Remove stale track→playlist links that no longer have a corresponding file
        cur = conn.cursor()
        cur.execute("SELECT track_id FROM track_playlists WHERE playlist_id=?", (playlist_id,))
        existing_links = {row[0] for row in cur.fetchall()}
        to_remove = existing_links - processed_track_ids
        if to_remove:
            print(f"[SCAN]   Removing {len(to_remove)} stale playlist links")
            cur.executemany(
                "DELETE FROM track_playlists WHERE playlist_id=? AND track_id=?",
                [(playlist_id, tid) for tid in to_remove],
            )

        # update stats
        update_playlist_stats(conn, playlist_id, count)
        playlist_time = time.time() - playlist_start
        print(f"[SCAN]   Playlist '{playlist_dir.name}': {count} tracks total, {new_tracks} new, {files_no_id} without video_id - {playlist_time:.2f}s")
        total_tracks += count
        
    # OPTIMIZATION: All changes auto-committed during processing
    print(f"[SCAN] All changes auto-committed during processing - {time.strftime('%H:%M:%S')}")
    
    conn.close()
    
    total_time = time.time() - scan_start
    print(f"\n[SCAN] Scan completed! Total time: {total_time:.2f}s - {time.strftime('%H:%M:%S')}")
    print(f"[SCAN] Summary: {total_playlists} playlists processed, {total_tracks} total tracks")
    print(f"[SCAN] Files: {total_files_skipped} skipped (unchanged), {total_tracks - total_files_skipped} processed, {total_files_no_id} without video_id")
    print(f"[SCAN] ffprobe calls: {total_ffprobe_calls} executed, {total_ffprobe_skipped} skipped")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scan media folder into SQLite database")
    parser.add_argument("--root", default="downloads", help="Base folder containing Playlists/ and DB/ (legacy mode)")
    parser.add_argument("--playlists-dir", help="Direct path to Playlists folder")
    parser.add_argument("--db-path", help="Direct path to database file")
    args = parser.parse_args()

    # New flexible mode: use direct paths if provided
    if args.playlists_dir and args.db_path:
        playlists_dir = Path(args.playlists_dir).resolve()
        db_path = Path(args.db_path).resolve()
        
        if not playlists_dir.exists():
            raise SystemExit("Playlists folder not found: " + str(playlists_dir))
        
        # Ensure database directory exists
        db_dir = db_path.parent
        db_dir.mkdir(parents=True, exist_ok=True)
        db.set_db_path(str(db_path))
        
        print(f"[CONFIG] Using direct paths:")
        print(f"[CONFIG] Playlists: {playlists_dir}")
        print(f"[CONFIG] Database: {db_path}")
        
    # Legacy mode: use --root parameter
    else:
        base = Path(args.root).resolve()
        playlists_dir = base / "Playlists"
        db_dir = base / "DB"

        if not playlists_dir.exists():
            raise SystemExit("Playlists folder not found: " + str(playlists_dir))

        db_dir.mkdir(parents=True, exist_ok=True)
        db.set_db_path(db_dir / "tracks.db")
        
        print(f"[CONFIG] Using legacy mode with root: {base}")

    scan(playlists_dir) 
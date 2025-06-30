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
    try:
        res = subprocess.run([
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=bit_rate,width,height",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ], capture_output=True, text=True, check=True, timeout=10)
        lines = res.stdout.strip().split("\n")
        # ffprobe prints duration then per-stream values; we only need duration & maybe first stream values
        duration = float(lines[0]) if lines else None
        # try to parse bitrate/resolution from subsequent lines if they exist
        bitrate = None
        resolution = None
        for line in lines[1:]:
            if not bitrate and line.isdigit():
                bitrate = int(line)
            elif "x" in line and line.replace("x", "").isdigit():
                resolution = line
        return duration, bitrate, resolution
    except Exception:
        return None, None, None


def scan(playlists_dir: Path):
    print(f"[SCAN] Starting scan of: {playlists_dir}")
    
    # Count total directories first for progress tracking
    all_dirs = [d for d in playlists_dir.iterdir() if d.is_dir()]
    print(f"[SCAN] Found {len(all_dirs)} directories to check")
    
    conn = get_connection()
    total_playlists = 0
    total_tracks = 0
    
    for i, playlist_dir in enumerate(all_dirs, 1):
        print(f"\n[SCAN] [{i}/{len(all_dirs)}] Checking: {playlist_dir.name}")
        
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
        
        for j, file in enumerate(media_files, 1):
            if j % 50 == 0 or j == len(media_files):  # Progress every 50 files or at end
                print(f"[SCAN]   Processing files: {j}/{len(media_files)}")
                
            video_id = get_video_id(file.stem)
            if not video_id:
                continue  # skip files without recognised ID
                
            # Check if track already exists
            cur = conn.cursor()
            cur.execute("SELECT id FROM tracks WHERE video_id = ?", (video_id,))
            existing = cur.fetchone()
            
            if existing:
                track_id = existing[0]
            else:
                duration, bitrate, resolution = ffprobe_duration(file)
                size_bytes = file.stat().st_size
                track_id = upsert_track(
                    conn,
                    video_id=video_id,
                    name=file.stem,
                    relpath=str(file.relative_to(playlists_dir)),
                    duration=duration,
                    size_bytes=size_bytes,
                    bitrate=bitrate,
                    resolution=resolution,
                    filetype=file.suffix.lstrip(".").lower(),
                )
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
            conn.commit()

        # update stats
        update_playlist_stats(conn, playlist_id, count)
        print(f"[SCAN]   Playlist '{playlist_dir.name}': {count} tracks total, {new_tracks} new")
        total_tracks += count
        
    conn.close()
    print(f"\n[SCAN] Scan completed!")
    print(f"[SCAN] Summary: {total_playlists} playlists processed, {total_tracks} total tracks")


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
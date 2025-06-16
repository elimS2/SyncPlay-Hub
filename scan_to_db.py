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
import log_utils  # noqa: F401 – applies timestamp+PID prefix to all print() calls

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
    conn = get_connection()
    for playlist_dir in playlists_dir.iterdir():
        if not playlist_dir.is_dir():
            continue
        # Check has media
        has_media = any(p.suffix.lower() in MEDIA_EXTS for p in playlist_dir.rglob("*.*"))
        if not has_media:
            continue
        playlist_rel = str(playlist_dir.relative_to(playlists_dir))
        playlist_id = upsert_playlist(conn, playlist_dir.name, playlist_rel)

        count = 0
        processed_track_ids = set()
        for file in playlist_dir.rglob("*.*"):
            if file.suffix.lower() not in MEDIA_EXTS or not file.is_file():
                continue
            video_id = get_video_id(file.stem)
            if not video_id:
                continue  # skip files without recognised ID
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
            link_track_playlist(conn, track_id, playlist_id)
            processed_track_ids.add(track_id)
            count += 1

        # Remove stale track→playlist links that no longer have a corresponding file
        cur = conn.cursor()
        cur.execute("SELECT track_id FROM track_playlists WHERE playlist_id=?", (playlist_id,))
        existing_links = {row[0] for row in cur.fetchall()}
        to_remove = existing_links - processed_track_ids
        if to_remove:
            cur.executemany(
                "DELETE FROM track_playlists WHERE playlist_id=? AND track_id=?",
                [(playlist_id, tid) for tid in to_remove],
            )
            conn.commit()

        # update stats
        update_playlist_stats(conn, playlist_id, count)
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scan media folder into SQLite database")
    parser.add_argument("--root", default="downloads", help="Base folder containing Playlists/ and DB/")
    args = parser.parse_args()

    base = Path(args.root).resolve()
    playlists_dir = base / "Playlists"
    db_dir = base / "DB"

    if not playlists_dir.exists():
        raise SystemExit("Playlists folder not found: " + str(playlists_dir))

    db_dir.mkdir(parents=True, exist_ok=True)
    db.set_db_path(db_dir / "tracks.db")

    scan(playlists_dir)
    print("Scan completed.") 
#!/usr/bin/env python3
"""Simple web player for downloaded YouTube playlist tracks.

Usage:
    python web_player.py --root downloads --host 0.0.0.0 --port 8000

Open in browser: http://localhost:8000/
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import List
import socket
import re

from flask import Flask, jsonify, render_template, send_from_directory, url_for, abort

import database as db
from database import get_connection, iter_tracks_with_playlists, increment_play

# We'll reuse scan function from scan_to_db.py
from scan_to_db import scan as scan_library

app = Flask(
    __name__,
    static_folder="static",
    template_folder="templates",
)

# ROOT_DIR will point to the Playlists directory (BASE_DIR / "Playlists")
ROOT_DIR: Path  # set in main()

# Where the database file lives (BASE_DIR / "DB" / tracks.db)
DB_FILE: Path  # set in main()

VIDEO_ID_RE = re.compile(r"\[([A-Za-z0-9_-]{11})\]$")


def scan_tracks(scan_root: Path) -> List[dict]:
    """Return list of media files under scan_root (recursive).

    The returned URLs/relpaths are always relative to the global ROOT_DIR so that
    they can be served correctly by the /media endpoint.
    """
    files = []
    for p in scan_root.rglob("*.*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in {".mp3", ".m4a", ".opus", ".webm", ".flac", ".mp4", ".mkv", ".mov"}:
            continue
        rel_to_root = p.relative_to(ROOT_DIR)
        m = VIDEO_ID_RE.search(p.stem)
        vid = m.group(1) if m else ""
        files.append({
            "name": p.stem,
            "relpath": str(rel_to_root).replace("\\", "/"),
            "url": url_for("media", filename=str(rel_to_root).replace("\\", "/")),
            "video_id": vid,
        })
    return files


# ------------------------
# Helper functions
# ------------------------


def _ensure_subdir(requested: Path) -> Path:
    """Return absolute path under ROOT_DIR or abort 404 if traversal is attempted."""
    try:
        # Ensure the resolved path is inside ROOT_DIR (prevent path traversal)
        requested_abs = (ROOT_DIR / requested).resolve()
        if ROOT_DIR not in requested_abs.parents and requested_abs != ROOT_DIR:
            raise ValueError
        return requested_abs
    except Exception:
        abort(404)


def list_playlists(root: Path) -> List[dict]:
    """Return first-level sub-directories that contain at least one media file."""
    playlists = []
    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        # does this dir contain at least one media file (recursively)?
        has_media = any(p.suffix.lower() in {".mp3", ".m4a", ".opus", ".webm", ".flac", ".mp4", ".mkv", ".mov"}
                       for p in d.rglob("*.*"))
        if has_media:
            playlists.append({
                "name": d.name,
                "relpath": str(d.relative_to(root)).replace("\\", "/"),
                "url": url_for("playlist_page", playlist_path=str(d.relative_to(root)).replace("\\", "/")),
            })
    return playlists


# -------- API ROUTES --------


@app.route("/api/tracks", defaults={"subpath": ""})
@app.route("/api/tracks/<path:subpath>")
def api_tracks(subpath: str):
    base_dir = _ensure_subdir(Path(subpath)) if subpath else ROOT_DIR
    tracks = scan_tracks(base_dir)
    return jsonify(tracks)


@app.route("/api/playlists")
def api_playlists():
    return jsonify(list_playlists(ROOT_DIR))


@app.route("/media/<path:filename>")
def media(filename: str):
    return send_from_directory(ROOT_DIR, filename, as_attachment=False)


# Helper to determine local LAN IP (for Chromecast)


def _get_local_ip() -> str:
    """Return this machine's LAN IP address (best effort)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Whether the address is reachable is irrelevant; we just need to select the interface
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


# -------- PAGE ROUTES --------


@app.route("/")
def playlists_page():
    """Homepage – list all playlists (sub-folders)."""
    playlists = list_playlists(ROOT_DIR)
    return render_template("playlists.html", playlists=playlists, server_ip=_get_local_ip())


@app.route("/playlist/<path:playlist_path>")
def playlist_page(playlist_path: str):
    """Playlist view – identical to previous homepage."""
    # validate path
    _ensure_subdir(Path(playlist_path))
    from pathlib import Path as _Path
    return render_template("index.html", server_ip=_get_local_ip(), playlist_rel=playlist_path, playlist_name=_Path(playlist_path).name)


# -------- DB Tracks Page --------


@app.route("/tracks")
def tracks_page():
    conn = get_connection()
    tracks = list(iter_tracks_with_playlists(conn))
    conn.close()
    return render_template("tracks.html", tracks=tracks)


# -------- Scan API --------


@app.route("/api/scan", methods=["POST"])
def api_scan():
    """Scan Playlists directory and update database."""
    try:
        scan_library(ROOT_DIR)
        return jsonify({"status": "ok"})
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500


# -------- Event API --------


@app.route("/api/event", methods=["POST"])
def api_event():
    data = {}  # fallback
    try:
        data = app.request_json_cache if hasattr(app, 'request_json_cache') else None
    except Exception:
        pass
    if not data:
        data = getattr(__import__('flask'), 'request').get_json(force=True, silent=True) or {}
    video_id = data.get("video_id")
    ev = data.get("event")
    if not video_id or ev not in {"start", "finish"}:
        return jsonify({"status": "error", "message": "bad payload"}), 400
    conn = get_connection()
    increment_play(conn, video_id, started=(ev == "start"), finished=(ev == "finish"))
    conn.close()
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Local web player for downloaded tracks")
    parser.add_argument("--root", default="downloads", help="Base folder containing Playlists/ and DB/")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    BASE_DIR = Path(args.root).resolve()
    PLAYLISTS_DIR = BASE_DIR / "Playlists"
    DB_DIR = BASE_DIR / "DB"

    if not PLAYLISTS_DIR.exists():
        raise SystemExit(f"Playlists folder '{PLAYLISTS_DIR}' not found (expected inside base dir)")
    DB_DIR.mkdir(parents=True, exist_ok=True)

    ROOT_DIR = PLAYLISTS_DIR
    DB_FILE = DB_DIR / "tracks.db"

    # configure database path
    db.set_db_path(DB_FILE)

    app.run(host=args.host, port=args.port, debug=False) 
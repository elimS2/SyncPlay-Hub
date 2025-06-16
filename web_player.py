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
import datetime

from flask import Flask, jsonify, render_template, send_from_directory, url_for, abort, request

import database as db
from database import get_connection, iter_tracks_with_playlists, record_event, get_history_page

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
            "last_play": _get_last_play_ts(vid),
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


# -------- History Page --------


@app.route("/history")
def history_page():
    page = int(request.args.get("page", 1))
    conn = get_connection()
    rows, has_next = get_history_page(conn, page=page, per_page=1000)
    rows = [dict(r) for r in rows]
    conn.close()
    return render_template("history.html", history=rows, page=page, has_next=has_next)


# -------- Scan API --------


@app.route("/api/scan", methods=["POST"])
def api_scan():
    """Scan Playlists directory and update database."""
    try:
        scan_library(ROOT_DIR)
        return jsonify({"status": "ok"})
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500


# -------- Add Playlist API --------


@app.route("/api/add_playlist", methods=["POST"])
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

    # Import here to avoid heavy deps on start-up
    from download_playlist import fetch_playlist_metadata, download_playlist as _dl_playlist
    from yt_dlp.utils import sanitize_filename  # type: ignore
    try:
        # Fetch metadata (title needed to know target folder & for duplicate check)
        title, _ids = fetch_playlist_metadata(url, debug=False)
    except Exception as exc:
        return jsonify({"status": "error", "message": f"metadata error: {exc}"}), 500

    folder_name = sanitize_filename(title, restricted=True)
    target_dir = ROOT_DIR / folder_name
    if target_dir.exists():
        return jsonify({"status": "exists", "message": "playlist already downloaded"})

    # Background worker to download and rescan DB
    def _worker():
        import contextlib, datetime, sys
        LOGS_DIR_LOCAL = globals().get("LOGS_DIR", Path.cwd() / "Logs")
        log_path = LOGS_DIR_LOCAL / "download_playlist.log"
        LOGS_DIR_LOCAL.mkdir(parents=True, exist_ok=True)
        # Inform server console where log is being written
        print(f"[AddPlaylist] Logging to {log_path}")
        with open(log_path, "a", encoding="utf-8", buffering=1) as lf, \
             contextlib.redirect_stdout(lf), contextlib.redirect_stderr(lf):
            print("="*60, flush=True)
            print(f"[START] {datetime.datetime.now():%Y-%m-%d %H:%M:%S} | Playlist: {title} | URL: {url}", flush=True)
            try:
                _dl_playlist(url, ROOT_DIR, audio_only=False, sync=True, debug=False)
                # Update DB after download
                scan_library(ROOT_DIR)
                print(f"[DONE]  {datetime.datetime.now():%Y-%m-%d %H:%M:%S}  Successfully downloaded {title}", flush=True)
            except Exception as e:
                print(f"[ERROR] {datetime.datetime.now():%Y-%m-%d %H:%M:%S}  {e}", flush=True)
            finally:
                print("="*60, flush=True)

    import threading

    threading.Thread(target=_worker, daemon=True).start()
    return jsonify({"status": "started"})


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
    pos = data.get("position")
    if not video_id or ev not in {"start", "finish", "next", "prev", "like"}:
        return jsonify({"status": "error", "message": "bad payload"}), 400
    conn = get_connection()
    record_event(conn, video_id, ev, position=pos)
    conn.close()
    return jsonify({"status": "ok"})


# Retrieve last play timestamp helper

def _get_last_play_ts(video_id: str):
    if not video_id:
        return None
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


# -------- Logs routes --------


def _list_log_files() -> List[Path]:
    """Return sorted list of *.log paths inside LOGS_DIR (newest first)."""
    logs_dir = globals().get("LOGS_DIR")
    if not logs_dir:
        return []
    return sorted(logs_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)


@app.route("/logs")
def logs_page():
    logs = [p.name for p in _list_log_files()]
    return render_template("logs.html", logs=logs)


@app.route("/log/<path:log_name>")
def log_view_page(log_name: str):
    # security: ensure no traversal
    if "/" in log_name or ".." in log_name or not log_name.endswith(".log"):
        abort(404)
    logs_dir = globals().get("LOGS_DIR")
    if not (logs_dir / log_name).exists():
        abort(404)
    return render_template("log_view.html", log_name=log_name)


@app.route("/stream_log/<path:log_name>")
def stream_log(log_name: str):
    import time
    from collections import deque
    from flask import Response

    # security checks
    if "/" in log_name or ".." in log_name or not log_name.endswith(".log"):
        abort(404)
    logs_dir = globals().get("LOGS_DIR")
    file_path = logs_dir / log_name
    if not file_path.exists():
        abort(404)

    def generate():
        # Send last 200 lines first
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                last_lines = deque(f, maxlen=200)
                for line in last_lines:
                    yield f"data: {line.rstrip()}\n\n"

                # Follow file
                f.seek(0, 2)  # move to end
                while True:
                    line = f.readline()
                    if line:
                        yield f"data: {line.rstrip()}\n\n"
                    else:
                        time.sleep(1)
        except GeneratorExit:
            return

    return Response(generate(), mimetype="text/event-stream")


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

    LOGS_DIR = BASE_DIR / "Logs"
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    ROOT_DIR = PLAYLISTS_DIR
    DB_FILE = DB_DIR / "tracks.db"

    # Expose LOGS_DIR globally so api_add_playlist can access
    globals()["LOGS_DIR"] = LOGS_DIR

    # configure database path
    db.set_db_path(DB_FILE)

    app.run(host=args.host, port=args.port, debug=False) 
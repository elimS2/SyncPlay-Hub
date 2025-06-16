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

from flask import Flask, jsonify, render_template, send_from_directory, url_for

app = Flask(
    __name__,
    static_folder="static",
    template_folder="templates",
)

ROOT_DIR: Path  # will be set in main()


def scan_tracks(root: Path) -> List[dict]:
    """Return list of audio files under root (recursive)."""
    files = []
    for p in root.rglob("*.*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in {".mp3", ".m4a", ".opus", ".webm", ".flac", ".mp4", ".mkv", ".mov"}:
            continue
        rel = p.relative_to(root)
        files.append({
            "name": p.stem,
            "relpath": str(rel).replace("\\", "/"),
            "url": url_for("media", filename=str(rel).replace("\\", "/")),
        })
    return files


@app.route("/api/tracks")
def api_tracks():
    tracks = scan_tracks(ROOT_DIR)
    return jsonify(tracks)


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


@app.route("/")
def index():
    # Pass IP to template so JS can replace "localhost" for Chromecast streaming
    return render_template("index.html", server_ip=_get_local_ip())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Local web player for downloaded tracks")
    parser.add_argument("--root", default="downloads", help="Root folder with audio files")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    ROOT_DIR = Path(args.root).resolve()
    if not ROOT_DIR.exists():
        raise SystemExit(f"Root folder '{ROOT_DIR}' not found")

    app.run(host=args.host, port=args.port, debug=False) 
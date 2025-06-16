#!/usr/bin/env python3
"""download_playlist.py
Script for downloading an entire YouTube playlist.

Example usage:
    python download_playlist.py https://www.youtube.com/playlist?list=PL.... \
        --output my_music --audio-only

Requirements:
    pip install -r requirements.txt
    FFmpeg must be installed on the system (to convert to mp3).
"""

import argparse
import pathlib
import sys
import re
import urllib.parse as _urlparse
from typing import Dict, Any, Set, Tuple

try:
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import sanitize_filename
except ModuleNotFoundError:
    sys.exit("[Error] Module 'yt_dlp' not found. Install dependencies: pip install -r requirements.txt")


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

VIDEO_ID_RE = re.compile(r"\[([A-Za-z0-9_-]{11})\]")

# File storing IDs known to be unavailable on YouTube (per playlist)
UNAVAILABLE_FILE = "unavailable_ids.txt"


def fetch_playlist_metadata(url: str) -> Tuple[str, Set[str]]:
    """Return (playlist_title, set_of_video_ids) without downloading files."""
    # Normalize URL: if it's a watch URL with &list=, convert to full playlist link
    parsed = _urlparse.urlparse(url)
    qs = _urlparse.parse_qs(parsed.query)
    if "list" in qs and (parsed.path.startswith("/watch") or parsed.path.startswith("/embed")):
        url = f"https://www.youtube.com/playlist?list={qs['list'][0]}"

    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        # Fetch full metadata to ensure all playlist items are counted
        # Alternatively, `extract_flat": "discard_in_playlist"` keeps requests light but traverses all pages.
        "extract_flat": "discard_in_playlist",
        # Safeguard: do not impose default 100-item end limit
        "playlistend": 0,  # 0 means no limit (yt-dlp convention)
    }
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    # Some YouTube responses may be wrapped; ensure we get playlist dict
    if "entries" not in info:
        raise RuntimeError("Provided URL does not appear to be a playlist. Make sure to supply a playlist link.")

    title = info.get("title") or "Playlist"
    ids = {entry["id"] for entry in info["entries"] if entry and entry.get("id")}
    return title, ids


def _video_is_available(video_id: str) -> bool:
    """Return True if video is still available on YouTube."""
    opts = {
        "quiet": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
    }
    try:
        with YoutubeDL(opts) as ydl:
            ydl.extract_info(video_id, download=False)
        return True
    except Exception:
        return False


def cleanup_local_files(playlist_dir: pathlib.Path, current_ids: Set[str]) -> None:
    """Remove local files whose video ID is no longer present in the playlist,
    unless the video itself is no longer available on YouTube (archived)."""
    if not playlist_dir.exists():
        return

    unavailable_path = playlist_dir / UNAVAILABLE_FILE
    remembered_unavailable: Set[str] = set()
    if unavailable_path.exists():
        remembered_unavailable = {
            line.strip() for line in unavailable_path.read_text().splitlines() if line.strip()
        }

    dirty = False  # whether we need to rewrite unavailable list

    for file in playlist_dir.iterdir():
        if not file.is_file():
            continue
        match = VIDEO_ID_RE.search(file.name)
        if not match:
            continue  # skip files without ID pattern
        vid = match.group(1)

        # Skip if still in playlist
        if vid in current_ids:
            continue

        # If previously marked unavailable, check again in case it was restored
        if vid in remembered_unavailable:
            if _video_is_available(vid):
                # Video has returned online; treat as normal "available but not in playlist"
                remembered_unavailable.remove(vid)
                dirty = True  # need to update list on disk
            else:
                # Still unavailable → keep archived file
                continue

        # Check availability
        if _video_is_available(vid):
            try:
                file.unlink()
                print(f"[Removed] {file.name} (not in playlist)")
            except Exception as exc:
                print(f"[Warning] Could not remove {file}: {exc}")
        else:
            print(f"[Archive] Keeping {file.name} (video unavailable online)")
            remembered_unavailable.add(vid)
            dirty = True

    if dirty:
        try:
            unavailable_path.write_text("\n".join(sorted(remembered_unavailable)))
        except Exception as exc:
            print(f"[Warning] Could not update {UNAVAILABLE_FILE}: {exc}")


def build_ydl_opts(output_dir: pathlib.Path, audio_only: bool) -> Dict[str, Any]:
    """Build yt-dlp options dict."""
    # File name template: <playlist>/Title [VIDEO_ID].ext
    output_template = str(output_dir / "%(playlist_title)s" / "%(title)s [%(id)s].%(ext)s")

    postprocessors = []
    if audio_only:
        postprocessors = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            },
            {"key": "FFmpegMetadata"},
        ]

    return {
        "format": "bestaudio/best" if audio_only else "bestvideo+bestaudio/best",
        "outtmpl": output_template,
        "download_archive": str(output_dir / "downloaded.txt"),
        "ignoreerrors": True,
        "postprocessors": postprocessors,
        "noplaylist": False,
        "yesplaylist": True,
        "concurrent_fragments": 4,
        # Pretty progress output in the terminal
        "progress_hooks": [lambda d: print_progress(d)],
    }


def print_progress(status: Dict[str, Any]) -> None:
    """Simple progress hook."""
    if status["status"] == "finished":
        filename = pathlib.Path(status["filename"]).name
        print(f"\n[Downloaded] {filename}")


def _get_local_ids(playlist_dir: pathlib.Path) -> Set[str]:
    """Return set of video IDs extracted from filenames in the playlist directory."""
    if not playlist_dir.exists():
        return set()
    ids: Set[str] = set()
    for f in playlist_dir.iterdir():
        if not f.is_file():
            continue
        m = VIDEO_ID_RE.search(f.name)
        if m:
            ids.add(m.group(1))
    return ids


def download_playlist(playlist_url: str, output_dir: pathlib.Path, audio_only: bool = False, *, sync: bool = True) -> None:
    """Download the entire playlist and optionally sync (delete) removed tracks."""
    # 1. Fetch metadata first to know current IDs and sanitized playlist title
    playlist_title, current_ids = fetch_playlist_metadata(playlist_url)
    sanitized_title = sanitize_filename(playlist_title, restricted=True)

    playlist_dir = output_dir / sanitized_title
    if sync:
        cleanup_local_files(playlist_dir, current_ids)

    # Show counts before downloading new content
    local_before = _get_local_ids(playlist_dir)
    print(f"[Info] Playlist items online: {len(current_ids)} | Local before download: {len(local_before)}")

    # Ensure base output_dir exists (yt-dlp will create subfolders itself)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 2. Download/update files
    ydl_opts = build_ydl_opts(output_dir, audio_only)
    with YoutubeDL(ydl_opts) as ydl:
        ydl.download([playlist_url])

    # Summary after download
    local_after = _get_local_ids(playlist_dir)
    added = len(local_after) - len(local_before)
    print(
        f"[Summary] Playlist items online: {len(current_ids)} | Local files after sync & download: {len(local_after)} (added {added})"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download a full YouTube playlist (video or audio only)")
    parser.add_argument("playlist_url", help="YouTube playlist URL")
    parser.add_argument("--output", "-o", default="downloads", help="Folder to save files", dest="output")
    parser.add_argument("--audio-only", action="store_true", help="Download audio only (mp3)")
    parser.add_argument("--no-sync", action="store_true", help="Do not delete local files that were removed from the playlist")
    args = parser.parse_args()

    try:
        download_playlist(
            args.playlist_url,
            pathlib.Path(args.output),
            args.audio_only,
            sync=not args.no_sync,
        )
    except KeyboardInterrupt:
        print("\n[Aborted by user]")
        sys.exit(130) 
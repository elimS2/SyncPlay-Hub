#!/usr/bin/env python3
from __future__ import annotations
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
import os
import textwrap
import shutil
import datetime
from utils.logging_utils import log_message  # Unified logging system
from utils.cookies_manager import get_cookies_for_download, log_cookies_status

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


def _user_agent_for_client(client: str | None, align: bool) -> str:
    """Return a UA aligned with a given extractor client if requested."""
    if not align:
        return 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
    if client == 'android':
        return 'Mozilla/5.0 (Linux; Android 12; SM-G998B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Mobile Safari/537.36'
    if client == 'ios':
        return 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1'
    # web/default
    return 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'


class _ProgLogger:
    def __init__(self, total=None, progress_callback=None):
        self.count = 0
        self.total = total
        self.last_video_id = None
        self.progress_callback = progress_callback
        import time
        self.start_time = time.time()
    
    def debug(self, msg):
        self._process_message(msg)
    
    def info(self, msg):
        self._process_message(msg)
    
    def warning(self, msg):
        self._process_message(msg)
        
    def error(self, msg):
        self._process_message(msg)
    
    def _process_message(self, msg):
        import time
        
        # Track video parsing progress
        if msg.startswith('[youtube') and 'Downloading webpage' in msg:
            self.count += 1
            elapsed = int(time.time() - self.start_time)
            if self.total:
                percentage = (self.count / self.total) * 100
                avg_time = elapsed / self.count if self.count > 0 else 0
                eta = int((self.total - self.count) * avg_time) if avg_time > 0 else 0
                progress_msg = f"  …parsed {self.count}/{self.total} entries ({percentage:.1f}%, {elapsed}s elapsed, ETA: {eta}s)"
                print(f"\r{progress_msg}", end='', flush=True)
                # Send progress to callback
                if self.progress_callback:
                    try:
                        self.progress_callback(f"[Progress] {progress_msg.strip()}")
                    except Exception:
                        pass
            else:
                progress_msg = f"  …parsed {self.count} entries ({elapsed}s elapsed)"
                print(f"\r{progress_msg}", end='', flush=True)
                # Send progress to callback
                if self.progress_callback:
                    try:
                        self.progress_callback(f"[Progress] {progress_msg.strip()}")
                    except Exception:
                        pass
                
        # Show video IDs being processed (every 10th video to avoid spam)
        elif '[youtube]' in msg and ': Downloading webpage' in msg and self.count % 10 == 0:
            # Extract video ID from message like "[youtube] dQw4w9WgXcQ: Downloading webpage"
            import re
            video_id_match = re.search(r'\[youtube\] ([A-Za-z0-9_-]{11}):', msg)
            if video_id_match:
                video_id = video_id_match.group(1)
                video_msg = f"  Processing video ID: {video_id} (#{self.count})"
                print(f"\n{video_msg}")
                # Send to callback
                if self.progress_callback:
                    try:
                        self.progress_callback(f"[Progress] {video_msg}")
                    except Exception:
                        pass
                
        # Show errors and warnings
        elif 'ERROR:' in msg or 'WARNING:' in msg:
            error_msg = f"  {msg.strip()}"
            print(f"\n{error_msg}")
            # Send to callback
            if self.progress_callback:
                try:
                    self.progress_callback(f"[Progress] {error_msg}")
                except Exception:
                    pass
            
        # Show unavailable videos
        elif 'Video unavailable' in msg or 'Private video' in msg or 'Deleted video' in msg:
            print(f"\n  {msg.strip()}")


def _validate_cookies_file(path: str) -> None:
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Cookies file '{path}' not found")
    with open(path, 'r', encoding='utf-8', errors='ignore') as fh:
        content = fh.read(4096)
    if '.youtube.com' not in content:
        raise ValueError("Provided cookies file does not appear to contain YouTube cookies")


def fetch_playlist_metadata(url: str, *, cookies_path: str | None = None, use_browser: bool = False, debug: bool = False, progress_callback=None, proxy_url: str | None = None) -> Tuple[str, Set[str]]:
    """Return (playlist_title, set_of_video_ids) without downloading files."""
    
    # Helper function to log both to console and callback
    def log_progress(msg):
        print(msg)
        if progress_callback:
            try:
                progress_callback(msg)
            except Exception:
                pass  # Don't let callback errors break the download
    
    # Normalize URL: if it's a watch URL with &list=, convert to full playlist link
    parsed = _urlparse.urlparse(url)
    qs = _urlparse.parse_qs(parsed.query)
    if "list" in qs and (parsed.path.startswith("/watch") or parsed.path.startswith("/embed")):
        url = f"https://www.youtube.com/playlist?list={qs['list'][0]}"

    # Quick first pass to estimate total items fast
    log_progress("[Info] Performing quick playlist scan to estimate size...")
    log_progress("[Info] This initial scan may take several minutes for very large playlists...")
    log_progress("[Info] Note: YouTube doesn't provide progress data for this phase, so updates will be periodic")
    common_cookies = ({"cookiefile": cookies_path} if cookies_path else {})
    if use_browser and not cookies_path:
        common_cookies.setdefault("cookiesfrombrowser", ("chrome",))

    quick_opts = {
        "quiet": True,  # Always quiet for quick scan, we'll use our logger
        "skip_download": True,
        "extract_flat": "discard_in_playlist",
        "playlist_items": "1-",
        "ignoreerrors": True,
        **common_cookies,
        **({"proxy": proxy_url} if proxy_url else {}),
    }
    try:
        import time
        start_time = time.time()
        
        # Add progress tracking for quick scan
        class QuickScanLogger:
            def __init__(self, callback):
                self.callback = callback
                self.last_log_time = time.time()
                self.items_found = 0
                
            def debug(self, msg): self._process_message(msg)
            def info(self, msg): self._process_message(msg)
            def warning(self, msg): self._process_message(msg)
            def error(self, msg): self._process_message(msg)
            
            def _process_message(self, msg):
                current_time = time.time()
                
                # Try to extract real progress information from yt-dlp messages
                if "playlist" in msg.lower() and ("downloading" in msg.lower() or "extracting" in msg.lower()):
                    if self.callback:
                        try:
                            elapsed = int(current_time - start_time)
                            self.callback(f"[Info] Quick scan: {msg.strip()} ({elapsed}s elapsed)")
                        except Exception:
                            pass
                    self.last_log_time = current_time
                
                # Look for item count indicators
                elif "entries" in msg.lower() or "items" in msg.lower():
                    if self.callback:
                        try:
                            elapsed = int(current_time - start_time)
                            self.callback(f"[Info] Quick scan: {msg.strip()} ({elapsed}s elapsed)")
                        except Exception:
                            pass
                    self.last_log_time = current_time
                
                # Fallback: periodic updates without real data
                elif current_time - self.last_log_time >= 30:
                    elapsed = int(current_time - start_time)
                    if self.callback:
                        try:
                            self.callback(f"[Info] Quick scan in progress... ({elapsed}s elapsed, still working)")
                        except Exception:
                            pass
                    self.last_log_time = current_time
        
        # Add progress hook to try to catch more detailed progress
        def quick_progress_hook(d):
            if progress_callback and d.get('status'):
                try:
                    elapsed = int(time.time() - start_time)
                    status = d.get('status', 'unknown')
                    if 'total_bytes' in d or 'total_bytes_estimate' in d:
                        progress_callback(f"[Info] Quick scan progress: {status} ({elapsed}s elapsed)")
                    elif status in ['downloading', 'finished']:
                        progress_callback(f"[Info] Quick scan: {status} playlist metadata ({elapsed}s elapsed)")
                except Exception:
                    pass
        
        quick_opts["logger"] = QuickScanLogger(progress_callback)
        quick_opts["progress_hooks"] = [quick_progress_hook]
        
        with YoutubeDL(quick_opts) as ydl:
            quick_info = ydl.extract_info(url, download=False)
        total_est = len(quick_info.get("entries", []))
        elapsed = time.time() - start_time
        log_progress(f"[Info] Quick scan completed in {elapsed:.1f}s - found ~{total_est} items")
    except Exception as e:
        log_progress(f"[Warning] Quick scan failed: {e}")
        total_est = None

    if total_est:
        log_progress(f"[Info] Starting detailed metadata scan for {total_est} items...")
        log_progress("[Info] This may take several minutes for large playlists due to YouTube API rate limits")
        # Estimate time based on typical rate (2-3 items per second)
        estimated_minutes = (total_est * 2.5) / 60  # Conservative estimate
        if estimated_minutes > 1:
            log_progress(f"[Info] Estimated completion time: ~{estimated_minutes:.0f} minutes")
    else:
        log_progress("[Info] Starting detailed metadata scan (unknown size)...")

    # Always use logger to show progress, even in non-debug mode
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "extract_flat": "discard_in_playlist",
        "playlist_items": "1-",  # all items
        "ignoreerrors": True,
        "logger": _ProgLogger(total_est, progress_callback),  # Pass callback to logger
        **common_cookies,
        **({"proxy": proxy_url} if proxy_url else {}),
    }
    
    import time
    detailed_start = time.time()
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    detailed_elapsed = time.time() - detailed_start
    print()  # newline after last carriage-return
    log_progress(f"[Info] Detailed scan completed in {detailed_elapsed:.1f}s")
    log_progress(f"[Info] Playlist metadata loaded: {len(info.get('entries', []))} items detected")

    # Some YouTube responses may be wrapped; ensure we get playlist dict
    if "entries" not in info:
        raise RuntimeError("Provided URL does not appear to be a playlist. Make sure to supply a playlist link.")

    title = info.get("title") or "Playlist"
    ids = {entry["id"] for entry in info["entries"] if entry and entry.get("id")}
    return title, ids


def _video_is_available(video_id: str, proxy_url: str | None = None) -> bool:
    """Return True if video is still available on YouTube."""
    opts = {
        "quiet": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
        **({"proxy": proxy_url} if proxy_url else {}),
    }
    try:
        with YoutubeDL(opts) as ydl:
            ydl.extract_info(video_id, download=False)
        return True
    except Exception:
        return False


def move_to_trash(file_path: pathlib.Path, root_dir: pathlib.Path) -> bool:
    """Move file to trash directory preserving playlist structure.
    
    Args:
        file_path: Full path to file to be moved
        root_dir: Root directory containing Playlists folder
        
    Returns:
        True if successfully moved, False otherwise
    """
    try:
        # Create trash directory structure
        trash_dir = root_dir / "Trash"
        trash_dir.mkdir(exist_ok=True)
        
        # Get playlist name from file path (parent directory)
        playlist_name = file_path.parent.name
        playlist_trash_dir = trash_dir / playlist_name
        playlist_trash_dir.mkdir(exist_ok=True)
        
        # Generate unique filename with timestamp if file already exists in trash
        target_file = playlist_trash_dir / file_path.name
        if target_file.exists():
            # Add timestamp to avoid conflicts
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            name_parts = file_path.name.rsplit('.', 1)
            if len(name_parts) == 2:
                new_name = f"{name_parts[0]}_{timestamp}.{name_parts[1]}"
            else:
                new_name = f"{file_path.name}_{timestamp}"
            target_file = playlist_trash_dir / new_name
        
        # Move file to trash
        shutil.move(str(file_path), str(target_file))
        print(f"[Moved to Trash] {file_path.name} → Trash/{playlist_name}/")
        return True
        
    except Exception as exc:
        print(f"[Warning] Could not move {file_path.name} to trash: {exc}")
        return False


def cleanup_local_files(playlist_dir: pathlib.Path, current_ids: Set[str], root_dir: pathlib.Path = None, proxy_url: str | None = None) -> None:
    """Move local files to trash whose video ID is no longer present in the playlist,
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
            if _video_is_available(vid, proxy_url):
                # Video has returned online; treat as normal "available but not in playlist"
                remembered_unavailable.remove(vid)
                dirty = True  # need to update list on disk
            else:
                # Still unavailable → keep archived file
                continue

        # Check availability
        if _video_is_available(vid, proxy_url):
            try:
                # Try to move to trash first, fall back to deletion if trash fails
                moved_to_trash = False
                if root_dir:
                    moved_to_trash = move_to_trash(file, root_dir)
                
                if not moved_to_trash:
                    # Fallback to deletion if trash move failed
                    file.unlink()
                    print(f"[Removed] {file.name} (not in playlist)")
                
                try:
                    from database import get_connection, record_event  # local import to avoid heavy deps if DB absent
                    conn = get_connection()
                    record_event(conn, vid, "removed")
                    # Unlink association with the current playlist (if present)
                    try:
                        # find playlist id by folder name (unique per library root)
                        cur = conn.cursor()
                        cur.execute("SELECT id FROM playlists WHERE name=?", (playlist_dir.name,))
                        row = cur.fetchone()
                        if row:
                            pl_id = row[0]
                            # remove mapping between this track and playlist
                            cur.execute(
                                "DELETE FROM track_playlists WHERE playlist_id=? AND track_id=(SELECT id FROM tracks WHERE video_id=?)",
                                (pl_id, vid),
                            )
                            conn.commit()
                    except Exception:
                        pass  # ignore any SQL issues, continue
                    conn.close()
                except Exception as _exc:
                    # ignore DB errors (e.g., no DB configured when running standalone CLI)
                    pass
            except Exception as exc:
                print(f"[Warning] Could not process {file}: {exc}")
        else:
            print(f"[Archive] Keeping {file.name} (video unavailable online)")
            remembered_unavailable.add(vid)
            dirty = True

    if dirty:
        try:
            unavailable_path.write_text("\n".join(sorted(remembered_unavailable)))
        except Exception as exc:
            print(f"[Warning] Could not update {UNAVAILABLE_FILE}: {exc}")


def build_ydl_opts(output_dir: pathlib.Path, audio_only: bool, *, cookies_path: str | None = None, use_browser: bool = False, proxy_url: str | None = None, player_client: str | None = None, align_ua: bool = False) -> Dict[str, Any]:
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

    extractor_args: Dict[str, Any] = {}
    if player_client:
        extractor_args = {"youtube": {"player_client": [player_client]}}

    return {
        "format": "bestaudio/best" if audio_only else "137+251/best[height<=1080]/best",
        "outtmpl": output_template,
        "download_archive": str(output_dir / "downloaded.txt"),
        "ignoreerrors": True,
        "postprocessors": postprocessors,
        "noplaylist": False,
        "yesplaylist": True,
        "concurrent_fragments": 4,
        # Pretty progress output in the terminal
        "progress_hooks": [lambda d: print_progress(d)],
        "noprogress": True,
        # Windows filename sanitization - prevents invalid characters like \/:*?"<>|
        "restrictfilenames": True,
        "windowsfilenames": True,
        "extractor_retries": 3,
        "fragment_retries": 10,
        "user_agent": _user_agent_for_client(player_client, align_ua),
        **({"extractor_args": extractor_args} if extractor_args else {}),
        **({"cookiefile": cookies_path} if cookies_path else {}),
        **({"cookiesfrombrowser": ("chrome",)} if use_browser and not cookies_path else {}),
        **({"proxy": proxy_url} if proxy_url else {}),
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


def download_playlist(playlist_url: str, output_dir: pathlib.Path, audio_only: bool = False, *, sync: bool = True,
                     cookies_path: str | None = None, use_browser: bool = False, debug: bool = False, progress_callback=None, proxy_url: str | None = None) -> None:
    """Download the entire playlist and optionally sync (delete) removed tracks."""
    
    # Helper function to log both to console and callback
    def log_progress(msg):
        print(msg)
        if progress_callback:
            try:
                progress_callback(msg)
            except Exception:
                pass  # Don't let callback errors break the download
    
    # Cookies configuration with automatic random selection
    actual_cookies_path, actual_use_browser = get_cookies_for_download(cookies_path, use_browser)
    
    # Show cookies status
    if debug:
        log_cookies_status()
    
    # Validate explicitly provided cookies
    if actual_cookies_path:
        try:
            _validate_cookies_file(actual_cookies_path)
            if actual_cookies_path != cookies_path:
                log_progress(f"[Info] Auto-selected random cookies file: {pathlib.Path(actual_cookies_path).name}")
            else:
                log_progress(f"[Info] Using explicitly provided cookies file: {actual_cookies_path}")
        except Exception as exc:
            log_progress(f"[Error] Cookies validation failed: {exc}")
            sys.exit(1)
    elif actual_use_browser:
        log_progress("[Info] Using browser cookies (Chrome profile by default)")
    else:
        log_progress("[Info] No cookies configured - downloads may fail for age-restricted content")

    # 1. Fetch metadata first to know current IDs and sanitized playlist title
    playlist_title, current_ids = fetch_playlist_metadata(
        playlist_url,
        cookies_path=actual_cookies_path,
        use_browser=actual_use_browser,
        debug=debug,
        progress_callback=progress_callback,
        proxy_url=proxy_url,
    )
    sanitized_title = sanitize_filename(playlist_title, restricted=True)

    playlist_dir = output_dir / sanitized_title
    if sync:
        cleanup_local_files(playlist_dir, current_ids, output_dir, proxy_url)

    # Show counts before downloading new content
    local_before = _get_local_ids(playlist_dir)
    log_progress(f"[Info] Playlist items online: {len(current_ids)} | Local before download: {len(local_before)}")

    # Ensure base output_dir exists (yt-dlp will create subfolders itself)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 2. Download/update files
    # Player client and UA alignment via environment (defaults aligned with roadmap)
    player_client = os.environ.get('YTDLP_PLAYLIST_CLIENT', 'android')
    align_ua = str(os.environ.get('YTDLP_ALIGN_UA_WITH_CLIENT', '0')).strip() in ('1', 'true', 'True')

    # Log yt-dlp version and warn if outdated (simple CLI check)
    try:
        import subprocess
        res = subprocess.run(['yt-dlp', '--version'], capture_output=True, text=True, timeout=10)
        ver = (res.stdout or '').strip()
        if ver:
            print(f"[yt-dlp] Version: {ver}")
    except Exception:
        pass

    ydl_opts = build_ydl_opts(
        output_dir,
        audio_only,
        cookies_path=actual_cookies_path,
        use_browser=actual_use_browser,
        proxy_url=proxy_url,
        player_client=player_client,
        align_ua=align_ua,
    )
    if debug:
        ydl_opts["quiet"] = False
    with YoutubeDL(ydl_opts) as ydl:
        ydl.download([playlist_url])

    # Summary after download
    local_after = _get_local_ids(playlist_dir)
    added = len(local_after) - len(local_before)
    log_progress(
        f"[Summary] Playlist items online: {len(current_ids)} | Local files after sync & download: {len(local_after)} (added {added})"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download a full YouTube playlist (video or audio only)")
    parser.add_argument("playlist_url", help="YouTube playlist URL")
    parser.add_argument("--output", "-o", default="downloads", help="Folder to save files", dest="output")
    parser.add_argument("--audio-only", action="store_true", help="Download audio only (mp3)")
    parser.add_argument("--no-sync", action="store_true", help="Do not delete local files that were removed from the playlist")
    parser.add_argument("--cookies", help="Path to YouTube cookies.txt export")
    parser.add_argument("--use-browser-cookies", action="store_true", help="Import cookies directly from installed browser (Chrome profile by default)")
    parser.add_argument("--debug", action="store_true", help="Verbose yt-dlp output for troubleshooting")
    parser.add_argument("--proxy", help="HTTP/HTTPS/SOCKS proxy URL for YouTube requests (e.g., http://proxy:8080)")
    args = parser.parse_args()

    try:
        download_playlist(
            args.playlist_url,
            pathlib.Path(args.output),
            args.audio_only,
            sync=not args.no_sync,
            cookies_path=args.cookies,
            use_browser=args.use_browser_cookies,
            debug=args.debug,
            proxy_url=args.proxy,
        )
    except KeyboardInterrupt:
        print("\n[Aborted by user]")
        sys.exit(130) 
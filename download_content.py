#!/usr/bin/env python3
from __future__ import annotations
"""download_content.py
Enhanced script for downloading YouTube playlists AND channels.

Example usage:
    # Playlists (original functionality)
    python download_content.py https://www.youtube.com/playlist?list=PL.... \
        --output my_music --audio-only

    # Channels (new functionality)  
    python download_content.py https://www.youtube.com/@WELLBOYmusic/videos \
        --output my_music --audio-only --channel-group "Music" --date-from 2024-01-01

Requirements:
    pip install -r requirements.txt
    FFmpeg must be installed on the system (to convert to mp3).
"""

import argparse
import pathlib
import sys
import re
import urllib.parse as _urlparse
from typing import Dict, Any, Set, Tuple, Optional
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

# File storing IDs known to be unavailable on YouTube (per playlist/channel)
UNAVAILABLE_FILE = "unavailable_ids.txt"

# Channel URL patterns
CHANNEL_PATTERNS = [
    r'youtube\.com/@[\w-]+',
    r'youtube\.com/@[\w-]+/videos',
    r'youtube\.com/c/[\w-]+',
    r'youtube\.com/channel/[\w-]+',
    r'youtube\.com/user/[\w-]+',
]

def is_channel_url(url: str) -> bool:
    """Check if URL is a YouTube channel URL."""
    for pattern in CHANNEL_PATTERNS:
        if re.search(pattern, url, re.IGNORECASE):
            return True
    return False

def normalize_channel_url(url: str) -> str:
    """Normalize channel URL to standard format."""
    # Convert @username/videos to @username for yt-dlp
    url = re.sub(r'/@([\w-]+)/videos', r'/@\1', url)
    return url


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


def fetch_content_metadata(url: str, *, cookies_path: str | None = None, use_browser: bool = False, 
                          debug: bool = False, progress_callback=None, date_from: str = None, 
                          debug_show_all_entries: bool = False) -> Tuple[str, Set[str], bool]:
    """Return (title, set_of_video_ids, is_channel) without downloading files."""
    
    # Helper function to log both to console and callback
    def log_progress(msg):
        print(msg)
        if progress_callback:
            try:
                progress_callback(msg)
            except Exception:
                pass  # Don't let callback errors break the download
    
    is_channel = is_channel_url(url)
    content_type = "channel" if is_channel else "playlist"
    
    # Normalize URL
    if is_channel:
        url = normalize_channel_url(url)
        log_progress(f"[Info] Detected YouTube channel URL: {url}")
    else:
        # Normalize playlist URL: if it's a watch URL with &list=, convert to full playlist link
        parsed = _urlparse.urlparse(url)
        qs = _urlparse.parse_qs(parsed.query)
        if "list" in qs and (parsed.path.startswith("/watch") or parsed.path.startswith("/embed")):
            url = f"https://www.youtube.com/playlist?list={qs['list'][0]}"
        log_progress(f"[Info] Detected YouTube playlist URL: {url}")

    # Quick first pass to estimate total items fast
    log_progress(f"[Info] Performing quick {content_type} scan to estimate size...")
    log_progress(f"[Info] This initial scan may take several minutes for very large {content_type}s...")
    log_progress("[Info] Note: YouTube doesn't provide progress data for this phase, so updates will be periodic")
    
    common_cookies = ({"cookiefile": cookies_path} if cookies_path else {})
    if use_browser and not cookies_path:
        common_cookies.setdefault("cookiesfrombrowser", ("chrome",))

    # Build options for content extraction
    quick_opts = {
        "quiet": True,  # Always quiet for quick scan, we'll use our logger
        "skip_download": True,
        "extract_flat": False,  # Always get full metadata to see all videos
        "ignoreerrors": True,
        **common_cookies,
    }
    
    # Add date filtering for channels
    if is_channel and date_from:
        try:
            # Convert date_from to yt-dlp format
            from datetime import datetime
            date_obj = datetime.strptime(date_from, '%Y-%m-%d')
            quick_opts["dateafter"] = date_obj.strftime('%Y%m%d')
            log_progress(f"[Info] Filtering videos from {date_from} onwards")
        except ValueError:
            log_progress(f"[Warning] Invalid date format '{date_from}', ignoring date filter")
    
    # Add playlist items range (not applicable to channels)
    if not is_channel:
        quick_opts["playlist_items"] = "1-"
    
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
                if (content_type in msg.lower()) and ("downloading" in msg.lower() or "extracting" in msg.lower()):
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
                            self.callback(f"[Info] {msg.strip()}")
                        except Exception:
                            pass
        
        def quick_progress_hook(d):
            if d["status"] == "finished":
                if progress_callback:
                    try:
                        progress_callback(f"[Info] Quick scan completed for: {d.get('filename', 'unknown')}")
                    except Exception:
                        pass

        quick_opts["logger"] = QuickScanLogger(progress_callback)
        quick_opts["progress_hooks"] = [quick_progress_hook]
        
        with YoutubeDL(quick_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if not info:
                raise ValueError(f"Could not extract {content_type} information")
            
            # Debug: Show info structure
            log_progress(f"[Debug] Extracted info structure:")
            log_progress(f"[Debug]   Info type: {info.get('_type', 'unknown')}")
            log_progress(f"[Debug]   Info keys: {list(info.keys())[:10]}...")  # Show first 10 keys
            if 'entries' in info:
                log_progress(f"[Debug]   Entries count: {len(info['entries'])}")
            
            # Extract title and video IDs
            if is_channel:
                title = info.get("channel", info.get("uploader", "Unknown Channel"))
                entries = info.get("entries", [])
                log_progress(f"[Debug] Channel detected: '{title}'")
            else:
                title = info.get("title", f"Unknown Playlist")
                entries = info.get("entries", [])
                log_progress(f"[Debug] Playlist detected: '{title}'")
            
            # Debug: Count different types of entries and list them
            total_entries = len(entries)
            valid_entries = 0
            invalid_entries = 0
            shorts_found = 0
            regular_videos = 0
            
            log_progress(f"[Debug] Analyzing extracted entries:")
            log_progress(f"[Debug] Raw entries structure preview:")
            for i, entry in enumerate(entries[:3]):  # Show first 3 raw entries
                log_progress(f"[Debug] Raw entry #{i+1}: {entry}")
            
            video_ids = set()
            for i, entry in enumerate(entries):
                if entry and entry.get("id"):
                    valid_entries += 1
                    video_id = entry["id"]
                    video_ids.add(video_id)
                    
                    # Get entry details
                    title = entry.get('title', 'No Title')
                    duration = entry.get('duration')
                    is_short = entry.get('is_short', False)
                    webpage_url = entry.get('webpage_url', '')
                    entry_type = entry.get('_type', 'unknown')
                    
                    # Log entries based on debug settings
                    if debug_show_all_entries or i < 20:
                        log_progress(f"[Debug] Entry #{i+1}: '{title}' (ID: {video_id})")
                        log_progress(f"[Debug]   Type: {entry_type}, Duration: {duration}s, is_short: {is_short}")
                        log_progress(f"[Debug]   URL: {webpage_url}")
                    elif i == 20:
                        log_progress(f"[Debug] ... (showing first 20 entries, total: {total_entries})")
                        log_progress(f"[Debug] To see ALL entries, enable debug_show_all_entries=True")
                    
                    # Count Shorts vs regular videos for debugging
                    if is_short or 'shorts' in webpage_url.lower():
                        shorts_found += 1
                    else:
                        if duration is not None and duration < 60:
                            shorts_found += 1
                        else:
                            regular_videos += 1
                else:
                    invalid_entries += 1
                    if i < 10:  # Log first 10 invalid entries
                        log_progress(f"[Debug] Invalid entry #{i+1}: {entry}")
            
            elapsed = int(time.time() - start_time)
            log_progress(f"[Info] Quick scan completed in {elapsed}s")
            log_progress(f"[Info] Found {len(video_ids)} videos in {content_type}: '{title}'")
            
            # Debug statistics
            log_progress(f"[Debug] Entry statistics:")
            log_progress(f"[Debug]   Total entries found: {total_entries}")
            log_progress(f"[Debug]   Valid video entries: {valid_entries}")
            log_progress(f"[Debug]   Invalid/missing entries: {invalid_entries}")
            log_progress(f"[Debug]   Detected Shorts: {shorts_found}")
            log_progress(f"[Debug]   Regular videos (>60s): {regular_videos}")
            log_progress(f"[Debug]   Note: Filtering will happen during download phase")
            
            return title, video_ids, is_channel
            
    except Exception as exc:
        log_progress(f"[Error] Failed to extract {content_type} metadata: {exc}")
        raise


def _video_is_available(video_id: str) -> bool:
    """Check if a video ID is still available on YouTube."""
    try:
        with YoutubeDL({"quiet": True, "skip_download": True}) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
            return info is not None
    except Exception:
        return False


def move_to_trash(file_path: pathlib.Path, root_dir: pathlib.Path) -> bool:
    """Move file to Trash folder within root_dir. Returns True if successful."""
    try:
        if not root_dir:
            return False
        
        trash_dir = root_dir / "Trash"
        trash_dir.mkdir(exist_ok=True)
        
        # Create subdirectory structure in trash to avoid conflicts
        relative_path = file_path.relative_to(root_dir)
        trash_file_path = trash_dir / relative_path
        trash_file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Handle filename conflicts in trash
        counter = 1
        original_trash_path = trash_file_path
        while trash_file_path.exists():
            stem = original_trash_path.stem
            suffix = original_trash_path.suffix
            trash_file_path = original_trash_path.parent / f"{stem}_conflict_{counter}{suffix}"
            counter += 1
        
        shutil.move(str(file_path), str(trash_file_path))
        print(f"[Moved to Trash] {file_path.name} → {trash_file_path.relative_to(root_dir)}")
        return True
        
    except Exception as exc:
        print(f"[Warning] Could not move to trash: {exc}")
        return False


def cleanup_local_files(content_dir: pathlib.Path, current_ids: Set[str], root_dir: pathlib.Path = None) -> None:
    """Remove local files not present in the current content (playlist/channel)."""
    if not content_dir.exists():
        return

    # Load list of video IDs known to be unavailable (don't delete these)
    unavailable_path = content_dir / UNAVAILABLE_FILE
    remembered_unavailable: Set[str] = set()
    dirty = False
    
    if unavailable_path.exists():
        try:
            content = unavailable_path.read_text(encoding="utf-8").strip()
            if content:
                remembered_unavailable = set(line.strip() for line in content.splitlines() if line.strip())
        except Exception as exc:
            print(f"[Warning] Could not read {UNAVAILABLE_FILE}: {exc}")

    print(f"[Info] Cleaning up local files not in current content...")
    print(f"[Info] Current content has {len(current_ids)} videos")
    print(f"[Info] Remembered unavailable: {len(remembered_unavailable)} videos")

    for file in content_dir.iterdir():
        if not file.is_file() or file.name == UNAVAILABLE_FILE:
            continue

        # Extract video ID from filename
        m = VIDEO_ID_RE.search(file.name)
        if not m:
            continue
        vid = m.group(1)

        # Keep files that are still in the current content
        if vid in current_ids:
            continue

        # If previously marked unavailable, check again in case it was restored
        if vid in remembered_unavailable:
            if _video_is_available(vid):
                # Video has returned online; treat as normal "available but not in content"
                remembered_unavailable.remove(vid)
                dirty = True  # need to update list on disk
            else:
                # Still unavailable → keep archived file
                continue

        # Check availability
        if _video_is_available(vid):
            try:
                # Try to move to trash first, fall back to deletion if trash fails
                moved_to_trash = False
                if root_dir:
                    moved_to_trash = move_to_trash(file, root_dir)
                
                if not moved_to_trash:
                    # Fallback to deletion if trash move failed
                    file.unlink()
                    print(f"[Removed] {file.name} (not in content)")
                
                try:
                    from database import get_connection, record_event  # local import to avoid heavy deps if DB absent
                    conn = get_connection()
                    record_event(conn, vid, "removed")
                    # Unlink association with the current content (if present)
                    try:
                        # find content id by folder name (unique per library root)
                        cur = conn.cursor()
                        cur.execute("SELECT id FROM playlists WHERE name=?", (content_dir.name,))
                        row = cur.fetchone()
                        if row:
                            content_id = row[0]
                            # remove mapping between this track and content
                            cur.execute(
                                "DELETE FROM track_playlists WHERE playlist_id=? AND track_id=(SELECT id FROM tracks WHERE video_id=?)",
                                (content_id, vid),
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


def build_ydl_opts(output_dir: pathlib.Path, audio_only: bool, is_channel: bool = False, 
                   channel_group: str = None, date_from: str = None, exclude_shorts: bool = True, *,
                   cookies_path: str | None = None, use_browser: bool = False) -> Dict[str, Any]:
    """Build yt-dlp options dict."""
    
    if is_channel:
        # For channels: Channel-{ChannelName}/Title [VIDEO_ID].ext
        if channel_group:
            # Use channel group folder structure: Music/Channel-Artist/Title [ID].ext
            output_template = str(output_dir / channel_group / "Channel-%(channel)s" / "%(title)s [%(id)s].%(ext)s")
        else:
            # Default channel structure: Channel-{ChannelName}/Title [ID].ext
            output_template = str(output_dir / "Channel-%(channel)s" / "%(title)s [%(id)s].%(ext)s")
    else:
        # For playlists: <playlist>/Title [VIDEO_ID].ext (original behavior)
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

    opts = {
        "format": "bestaudio/best" if audio_only else "bestvideo+bestaudio/best",
        "outtmpl": output_template,
        # "download_archive": str(output_dir / "downloaded.txt"),  # DISABLED for debugging
        "ignoreerrors": True,
        "postprocessors": postprocessors,
        "concurrent_fragments": 4,
        # Progress hooks will be set dynamically in download_content()
        "noprogress": True,
        # Windows filename sanitization - prevents invalid characters like \/:*?"<>|
        "restrictfilenames": True,
        "windowsfilenames": True,
        **({"cookiefile": cookies_path} if cookies_path else {}),
        **({"cookiesfrombrowser": ("chrome",)} if use_browser and not cookies_path else {}),
    }
    
    # Add filter to exclude Shorts (videos shorter than 60 seconds)
    if exclude_shorts and is_channel:
        # Counters for filter statistics
        filter_stats = {'total': 0, 'passed': 0, 'filtered_short': 0, 'filtered_duration': 0}
        
        def match_filter(info):
            video_title = info.get('title', 'Unknown Title')
            video_id = info.get('id', 'Unknown ID')
            webpage_url = info.get('webpage_url', '')
            duration = info.get('duration')
            is_short = info.get('is_short', False)
            
            filter_stats['total'] += 1
            
            # Debug: Log all videos being processed
            print(f"[Filter Debug] Processing #{filter_stats['total']}: '{video_title}' (ID: {video_id})")
            print(f"[Filter Debug]   Duration: {duration}s, is_short: {is_short}")
            print(f"[Filter Debug]   URL: {webpage_url}")
            
            # Skip if it's explicitly marked as a Short
            if is_short or 'shorts' in webpage_url.lower():
                filter_stats['filtered_short'] += 1
                reason = f"Skipping YouTube Short: '{video_title}' (ID: {video_id})"
                print(f"[Filter Debug]   ❌ FILTERED (Short): {reason}")
                return reason
            
            # Skip if duration is less than 60 seconds
            if duration is not None and duration < 60:
                filter_stats['filtered_duration'] += 1
                reason = f"Skipping video shorter than 60s (Shorts): '{video_title}' (ID: {video_id}) ({duration}s)"
                print(f"[Filter Debug]   ❌ FILTERED (Duration): {reason}")
                return reason
            
            # Video passed all filters
            filter_stats['passed'] += 1
            print(f"[Filter Debug]   ✅ PASSED: '{video_title}' (ID: {video_id})")
            
            # Show progress every 10 videos
            if filter_stats['total'] % 10 == 0:
                print(f"[Filter Stats] Processed {filter_stats['total']} videos: {filter_stats['passed']} passed, {filter_stats['filtered_short']} filtered (shorts), {filter_stats['filtered_duration']} filtered (duration)")
            
            return None
        opts["match_filter"] = match_filter
        
        # Additional option to skip shorts at extraction level - DISABLED for now to get all videos
        # opts["extractor_args"] = {
        #     'youtube:tab': {
        #         'skip': ['shorts']
        #     }
        # }
        
        print(f"[Info] Shorts exclusion filter enabled (videos < 60s will be skipped)")
    
    # Channel-specific options
    if is_channel:
        opts["noplaylist"] = False  # Allow processing all videos from channel
        opts["yesplaylist"] = True
        
        # Add date filtering for channels
        if date_from:
            try:
                from datetime import datetime
                date_obj = datetime.strptime(date_from, '%Y-%m-%d')
                opts["dateafter"] = date_obj.strftime('%Y%m%d')
                print(f"[Info] Downloading videos from {date_from} onwards")
            except ValueError:
                print(f"[Warning] Invalid date format '{date_from}', ignoring date filter")
    else:
        # Playlist-specific options (original behavior)
        opts["noplaylist"] = False
        opts["yesplaylist"] = True

    return opts


def create_progress_tracker(total_items: int, content_title: str, progress_callback=None):
    """Create a progress tracking function that shows X/Y progress."""
    
    # Shared state between progress calls
    state = {
        'completed': 0,
        'total': total_items,
        'current_file': None,
        'content_title': content_title,
        'last_update': 0
    }
    
    def progress_hook(status: Dict[str, Any]) -> None:
        """Enhanced progress hook with X/Y tracking."""
        import time
        
        if status["status"] == "finished":
            state['completed'] += 1
            filename = pathlib.Path(status["filename"]).name
            
            # Show progress: X/Y completed
            progress_msg = f"[Progress] Downloaded {state['completed']}/{state['total']}: {filename}"
            print(progress_msg)
            
            # Send to callback for web interface
            if progress_callback:
                try:
                    progress_callback(progress_msg)
                except Exception:
                    pass
                    
            # Show summary every 10 downloads or at completion
            if state['completed'] % 10 == 0 or state['completed'] == state['total']:
                percentage = (state['completed'] / state['total']) * 100
                summary_msg = f"[Progress] {state['content_title']}: {state['completed']}/{state['total']} completed ({percentage:.1f}%)"
                print(summary_msg)
                
                if progress_callback:
                    try:
                        progress_callback(summary_msg)
                    except Exception:
                        pass
        
        elif status["status"] == "downloading":
            # Show current file being downloaded (but not too frequently)
            current_time = time.time()
            if current_time - state['last_update'] > 30:  # Update every 30 seconds
                try:
                    filename = pathlib.Path(status.get("filename", "")).name
                    if filename and filename != state['current_file']:
                        state['current_file'] = filename
                        state['last_update'] = current_time
                        
                        # Show current download status
                        active_msg = f"[Progress] Downloading {state['completed']}/{state['total']}: {filename[:50]}..."
                        print(active_msg)
                        
                        if progress_callback:
                            try:
                                progress_callback(active_msg)
                            except Exception:
                                pass
                except Exception:
                    pass  # Don't break download if progress display fails
    
    return progress_hook


def print_progress(status: Dict[str, Any]) -> None:
    """Legacy simple progress hook - kept for backward compatibility."""
    if status["status"] == "finished":
        filename = pathlib.Path(status["filename"]).name
        print(f"\n[Downloaded] {filename}")


def _get_local_ids(content_dir: pathlib.Path) -> Set[str]:
    """Return set of video IDs extracted from filenames in the content directory."""
    if not content_dir.exists():
        return set()
    ids: Set[str] = set()
    for f in content_dir.iterdir():
        if not f.is_file():
            continue
        m = VIDEO_ID_RE.search(f.name)
        if m:
            ids.add(m.group(1))
    return ids


def download_content(url: str, output_dir: pathlib.Path, audio_only: bool = False, *, sync: bool = True,
                    channel_group: str = None, date_from: str = None, exclude_shorts: bool = True,
                    cookies_path: str | None = None, use_browser: bool = False, debug: bool = False, 
                    progress_callback=None) -> None:
    """Download YouTube content (playlist or channel) and optionally sync (delete) removed tracks."""
    
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

    # 1. Fetch metadata first to know current IDs and sanitized title
    content_title, current_ids, is_channel = fetch_content_metadata(
        url,
        cookies_path=actual_cookies_path,
        use_browser=actual_use_browser,
        debug=debug,
        progress_callback=progress_callback,
        date_from=date_from,
        debug_show_all_entries=debug,  # Show all entries if debug mode is on
    )
    
    # Determine output directory structure
    if is_channel:
        if channel_group:
            # Use channel group structure: Music/Channel-Artist/
            sanitized_title = f"Channel-{sanitize_filename(content_title, restricted=True)}"
            content_dir = output_dir / channel_group / sanitized_title
        else:
            # Default channel structure: Channel-{ChannelName}/
            sanitized_title = f"Channel-{sanitize_filename(content_title, restricted=True)}"
            content_dir = output_dir / sanitized_title
        log_progress(f"[Info] Channel content will be saved to: {content_dir}")
    else:
        # Playlist structure (original): PlaylistName/
        sanitized_title = sanitize_filename(content_title, restricted=True)
        content_dir = output_dir / sanitized_title
        log_progress(f"[Info] Playlist content will be saved to: {content_dir}")

    if sync:
        cleanup_local_files(content_dir, current_ids, output_dir)

    # Show counts before downloading new content
    local_before = _get_local_ids(content_dir)
    content_type = "channel" if is_channel else "playlist"
    log_progress(f"[Info] {content_type.title()} items online: {len(current_ids)} | Local before download: {len(local_before)}")

    # Ensure base output_dir exists (yt-dlp will create subfolders itself)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 2. Download/update files
    ydl_opts = build_ydl_opts(
        output_dir, audio_only, is_channel, channel_group, date_from, exclude_shorts,
        cookies_path=actual_cookies_path, use_browser=actual_use_browser
    )
    if debug:
        ydl_opts["quiet"] = False
    
    # Replace simple progress hook with enhanced tracker
    new_downloads = len(current_ids) - len(local_before)
    if new_downloads > 0:
        # Create enhanced progress tracker that shows X/Y progress
        progress_tracker = create_progress_tracker(
            total_items=new_downloads,
            content_title=content_title,
            progress_callback=progress_callback
        )
        ydl_opts["progress_hooks"] = [progress_tracker]
        
        # Show start message
        start_msg = f"[Progress] Starting download of {new_downloads} new items from {content_title}"
        log_progress(start_msg)
    else:
        # Use simple progress hook for fallback
        ydl_opts["progress_hooks"] = [lambda d: print_progress(d)]
        if len(current_ids) == len(local_before):
            log_progress(f"[Info] All {len(current_ids)} items already downloaded, checking for updates...")
        
    # Debug: Show download configuration
    log_progress(f"[Debug] Download configuration:")
    log_progress(f"[Debug]   URL: {url}")
    log_progress(f"[Debug]   Content directory: {content_dir}")
    log_progress(f"[Debug]   Audio only: {audio_only}")
    log_progress(f"[Debug]   Exclude shorts: {exclude_shorts}")
    log_progress(f"[Debug]   Output template: {ydl_opts.get('outtmpl', 'Not set')}")
    log_progress(f"[Debug]   Download archive: {ydl_opts.get('download_archive', 'Not set')}")
    
    with YoutubeDL(ydl_opts) as ydl:
        log_progress(f"[Debug] Starting yt-dlp download process...")
        ydl.download([url])
        log_progress(f"[Debug] yt-dlp download process completed")

    # Summary after download
    local_after = _get_local_ids(content_dir)
    added = len(local_after) - len(local_before)
    log_progress(
        f"[Summary] {content_type.title()} items online: {len(current_ids)} | Local files after sync & download: {len(local_after)} (added {added})"
    )
    
    # Database integration for channels
    if is_channel:
        try:
            from database import get_connection, record_event
            
            # Record channel download event
            conn = get_connection()
            
            # Log event for each new video
            for video_id in current_ids:
                if video_id not in local_before:  # Only log new downloads
                    import json
                    additional_data = json.dumps({
                        "channel_name": content_title,
                        "channel_group": channel_group,
                        "date_from": date_from
                    })
                    record_event(conn, video_id, "channel_downloaded", additional_data=additional_data)
            
            conn.close()
            log_progress(f"[Info] Recorded {added} new downloads in database")
            
        except Exception as exc:
            log_progress(f"[Warning] Could not update database: {exc}")


# Backward compatibility function
def download_playlist(playlist_url: str, output_dir: pathlib.Path, audio_only: bool = False, *, sync: bool = True,
                     cookies_path: str | None = None, use_browser: bool = False, debug: bool = False, 
                     progress_callback=None) -> None:
    """Backward compatibility wrapper for download_content."""
    return download_content(
        playlist_url, output_dir, audio_only,
        sync=sync, cookies_path=cookies_path, use_browser=use_browser,
        debug=debug, progress_callback=progress_callback
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download YouTube playlists or channels (video or audio only)")
    parser.add_argument("url", help="YouTube playlist or channel URL")
    parser.add_argument("--output", "-o", default="downloads", help="Folder to save files", dest="output")
    parser.add_argument("--audio-only", action="store_true", help="Download audio only (mp3)")
    parser.add_argument("--no-sync", action="store_true", help="Do not delete local files that were removed from the playlist/channel")
    parser.add_argument("--channel-group", help="Channel group folder (e.g., 'Music', 'News', 'Education')")
    parser.add_argument("--date-from", help="Download videos from this date onwards (YYYY-MM-DD format, channels only)")
    parser.add_argument("--cookies", help="Path to YouTube cookies.txt export")
    parser.add_argument("--use-browser-cookies", action="store_true", help="Import cookies directly from installed browser (Chrome profile by default)")
    parser.add_argument("--debug", action="store_true", help="Verbose yt-dlp output for troubleshooting")
    args = parser.parse_args()

    try:
        download_content(
            args.url,
            pathlib.Path(args.output),
            args.audio_only,
            sync=not args.no_sync,
            channel_group=args.channel_group,
            date_from=args.date_from,
            cookies_path=args.cookies,
            use_browser=args.use_browser_cookies,
            debug=args.debug,
        )
    except KeyboardInterrupt:
        print("\n[Aborted by user]")
        sys.exit(130) 
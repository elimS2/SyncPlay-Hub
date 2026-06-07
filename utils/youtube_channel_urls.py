"""Helpers for YouTube channel tab URLs (videos, releases, etc.)."""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional

YOUTUBE_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

VIDEO_URL_PATTERNS = [
    re.compile(r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/v/)([A-Za-z0-9_-]{11})"),
    re.compile(r"youtube\.com/shorts/([A-Za-z0-9_-]{11})"),
]

CHANNEL_TAB_SUFFIXES = ("videos", "releases", "streams", "shorts", "playlists", "community", "channels", "about")

CHANNEL_URL_PATTERNS = [
    r"youtube\.com/@[\w-]+(?:/(?:" + "|".join(CHANNEL_TAB_SUFFIXES) + r"))?",
    r"youtube\.com/c/[\w-]+(?:/(?:videos|releases))?",
    r"youtube\.com/channel/[\w-]+(?:/(?:videos|releases))?",
    r"youtube\.com/user/[\w-]+(?:/(?:videos|releases))?",
]


def is_youtube_video_id(video_id: Optional[str]) -> bool:
    return bool(video_id and YOUTUBE_VIDEO_ID_RE.match(video_id))


def extract_video_id_from_url(url: str) -> Optional[str]:
    """Extract an 11-character YouTube video ID from a watch/shorts/youtu.be URL."""
    for pattern in VIDEO_URL_PATTERNS:
        match = pattern.search((url or "").strip())
        if match:
            video_id = match.group(1)
            if is_youtube_video_id(video_id):
                return video_id
    return None


def is_video_url(url: str) -> bool:
    return extract_video_id_from_url(url) is not None


def is_releases_url(url: str) -> bool:
    return "/releases" in (url or "").lower()


def is_channel_url(url: str) -> bool:
    for pattern in CHANNEL_URL_PATTERNS:
        if re.search(pattern, url, re.IGNORECASE):
            return True
    return False


def normalize_channel_url(url: str) -> str:
    """Normalize channel URL while preserving explicit tab suffixes like /releases."""
    if is_releases_url(url):
        return url
    return re.sub(r"/@([\w-]+)/videos", r"/@\1", url)


def is_nested_playlist_entry(entry: Dict[str, Any]) -> bool:
    """True when a flat-playlist entry points to an album/playlist, not a video."""
    entry_id = entry.get("id") or entry.get("video_id") or ""
    if is_youtube_video_id(entry_id):
        return False

    entry_url = entry.get("url") or entry.get("webpage_url") or ""
    if "playlist?list=" in entry_url:
        return True

    if entry_id.startswith(("OLAK", "PL", "UU", "LL", "FLRD", "RD")):
        return True

    ie_key = (entry.get("ie_key") or "").lower()
    if ie_key in {"youtubetab", "youtube:tab"} and not is_youtube_video_id(entry_id):
        return True

    return False


def expand_nested_playlist_entries(
    metadata_list: List[Dict[str, Any]],
    *,
    extract_playlist_fn: Callable[[str], List[Dict[str, Any]]],
    log_fn: Callable[[str], None],
) -> List[Dict[str, Any]]:
    """Expand album/playlist entries from /releases into individual video metadata."""
    videos: List[Dict[str, Any]] = []
    nested: List[Dict[str, Any]] = []

    for entry in metadata_list:
        if is_nested_playlist_entry(entry):
            nested.append(entry)
        elif is_youtube_video_id(entry.get("id") or entry.get("video_id")):
            videos.append(entry)

    if not nested:
        return metadata_list

    log_fn(f"Expanding {len(nested)} nested album/playlist entries into individual tracks...")
    seen_ids = {entry.get("id") or entry.get("video_id") for entry in videos}

    for index, album in enumerate(nested, 1):
        album_url = album.get("url") or album.get("webpage_url")
        album_title = album.get("title") or "Unknown album"
        if not album_url:
            log_fn(f"Warning: Album '{album_title}' has no URL, skipping")
            continue

        log_fn(f"Extracting album {index}/{len(nested)}: {album_title}")
        album_entries = extract_playlist_fn(album_url)

        for track in album_entries:
            track_id = track.get("id") or track.get("video_id")
            if not is_youtube_video_id(track_id) or track_id in seen_ids:
                continue

            track.setdefault("album", album_title)
            track.setdefault("album_playlist_id", album.get("id"))
            videos.append(track)
            seen_ids.add(track_id)

    log_fn(f"Expanded releases tab to {len(videos)} individual videos")
    return videos

#!/usr/bin/env python3
"""
Metadata utilities for YouTube video metadata processing.

Contains common functions for extracting, formatting and saving YouTube video metadata.
"""

from typing import Dict, Any, Optional, List
import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from controllers.api.shared import get_connection, log_message
import database as db


def _normalize_format_entry(fmt: Dict[str, Any]) -> Dict[str, Any]:
    """Return a compact, normalized subset of a yt-dlp format entry.

    Keeps only fields useful for identifying quality ladders while reducing size.
    """
    return {
        'format_id': fmt.get('format_id'),
        'format_note': fmt.get('format_note'),
        'ext': fmt.get('ext'),
        'vcodec': fmt.get('vcodec'),
        'acodec': fmt.get('acodec'),
        'tbr': fmt.get('tbr'),  # total bitrate kbps (if present)
        'abr': fmt.get('abr'),  # audio bitrate kbps (if present)
        'asr': fmt.get('asr'),  # audio sample rate Hz
        'fps': fmt.get('fps'),
        'width': fmt.get('width'),
        'height': fmt.get('height'),
        'filesize': fmt.get('filesize'),
        'filesize_approx': fmt.get('filesize_approx'),
    }


def _build_formats_summary(normalized_formats: List[Dict[str, Any]]) -> str:
    """Build a compact, human-readable summary from normalized formats.

    Example: "video: 2160p, 1440p, 1080p60, 720p | audio: 160kbps opus, 128kbps m4a"
    """
    if not normalized_formats:
        return ""

    video_entries: List[str] = []
    audio_entries: List[str] = []

    # Collect video and audio candidates
    video_formats = [f for f in normalized_formats if (f.get('vcodec') and f.get('vcodec') != 'none')]
    audio_formats = [f for f in normalized_formats if (f.get('acodec') and f.get('acodec') != 'none') and (not f.get('vcodec') or f.get('vcodec') == 'none')]

    # Build unique video descriptors by (height, fps>=50)
    seen_video_keys = set()
    for f in sorted(video_formats, key=lambda x: (x.get('height') or 0, x.get('fps') or 0), reverse=True):
        height = f.get('height')
        if not height:
            continue
        is_60 = (f.get('fps') or 0) >= 50
        key = (height, is_60)
        if key in seen_video_keys:
            continue
        seen_video_keys.add(key)
        label = f"{height}p"
        if is_60:
            label += "60"
        video_entries.append(label)
        if len(video_entries) >= 6:
            break

    # Build top audio descriptors by abr/tbr
    def _audio_bitrate(fmt: Dict[str, Any]) -> float:
        return float(fmt.get('abr') or fmt.get('tbr') or 0)

    seen_audio_keys = set()
    for f in sorted(audio_formats, key=_audio_bitrate, reverse=True):
        abr = int(round(_audio_bitrate(f)))
        if abr <= 0:
            continue
        codec = f.get('acodec') or ''
        ext = f.get('ext') or ''
        # Unique by (abr, codec or ext)
        key = (abr, codec or ext)
        if key in seen_audio_keys:
            continue
        seen_audio_keys.add(key)
        label_codec = (codec or ext).split('.')[-1]
        audio_entries.append(f"{abr}kbps {label_codec}")
        if len(audio_entries) >= 3:
            break

    parts = []
    if video_entries:
        parts.append("video: " + ", ".join(video_entries))
    if audio_entries:
        parts.append("audio: " + ", ".join(audio_entries))
    return " | ".join(parts)


def _compute_max_quality_fields(normalized_formats: List[Dict[str, Any]]) -> tuple[int | None, str | None]:
    """Compute (max_available_height, max_quality_label) from normalized formats.

    Returns (height, label) where height is an integer like 2160 and label is '2160p'.
    When no valid video formats found, returns (None, None).
    """
    if not isinstance(normalized_formats, list):
        return None, None
    max_height = 0
    for f in normalized_formats:
        if not isinstance(f, dict):
            continue
        vcodec = str(f.get('vcodec') or '').lower()
        if not vcodec or vcodec == 'none':
            continue
        height = f.get('height')
        if isinstance(height, (int, float)) and height and height > max_height:
            max_height = int(height)
    if max_height > 0:
        return max_height, f"{max_height}p"
    return None, None


def create_metadata_dict_from_entry(entry: Dict[str, Any], channel_url: str = None) -> Dict[str, Any]:
    """
    Create standardized metadata dictionary from yt-dlp entry.
    
    Args:
        entry: Raw metadata entry from yt-dlp
        channel_url: Original channel URL to preserve in metadata
        
    Returns:
        Dictionary with standardized metadata fields for database storage
    """
    video_id = entry.get('id')
    if not video_id:
        raise ValueError("Entry must contain 'id' field")
    
    # Extract all standard fields with fallbacks
    metadata = {
        'youtube_id': video_id,
        'title': entry.get('title', ''),
        'description': entry.get('description', ''),
        'channel': entry.get('channel', ''),
        'uploader': entry.get('uploader', ''),
        'uploader_id': entry.get('uploader_id', ''),
        'timestamp': entry.get('timestamp'),
        'release_timestamp': entry.get('release_timestamp'),
        'duration': entry.get('duration'),
        'view_count': entry.get('view_count', 0),
        'availability': entry.get('availability', ''),
        'live_status': entry.get('live_status', ''),
        'webpage_url': entry.get('webpage_url', ''),
        'extractor': entry.get('extractor', ''),
        'extractor_key': entry.get('extractor_key', ''),
        'channel_id': entry.get('channel_id', ''),
        'uploader_url': entry.get('uploader_url', ''),
        'channel_is_verified': entry.get('channel_is_verified', False),
        'duration_string': entry.get('duration_string', ''),
        'release_year': entry.get('release_year'),
        
        # Extended fields
        'url': entry.get('url', ''),
        '_type': entry.get('_type', ''),
        'ie_key': entry.get('ie_key', ''),
        'channel_url': channel_url or entry.get('channel_url', ''),
        'original_url': entry.get('original_url', ''),
        'webpage_url_basename': entry.get('webpage_url_basename', ''),
        'webpage_url_domain': entry.get('webpage_url_domain', ''),
        
        # Playlist context
        'playlist_count': entry.get('playlist_count'),
        'playlist': entry.get('playlist', ''),
        'playlist_id': entry.get('playlist_id', ''),
        'playlist_title': entry.get('playlist_title', ''),
        'playlist_uploader': entry.get('playlist_uploader', ''),
        'playlist_uploader_id': entry.get('playlist_uploader_id', ''),
        'playlist_channel': entry.get('playlist_channel', ''),
        'playlist_channel_id': entry.get('playlist_channel_id', ''),
        'playlist_webpage_url': entry.get('playlist_webpage_url', ''),
        'n_entries': entry.get('n_entries'),
        'playlist_index': entry.get('playlist_index'),
        '__last_playlist_index': entry.get('__last_playlist_index'),
        'playlist_autonumber': entry.get('playlist_autonumber'),
        'epoch': entry.get('epoch'),
        
        # Technical details
        '__x_forwarded_for_ip': entry.get('__x_forwarded_for_ip', '')
    }
    
    # Available formats and summary (optional)
    try:
        raw_formats = entry.get('formats') or []
        normalized_formats = [_normalize_format_entry(f) for f in raw_formats if isinstance(f, dict)]
        # Store as JSON string to keep DB column TEXT
        metadata['available_formats'] = json.dumps(normalized_formats, ensure_ascii=False)
        metadata['available_qualities_summary'] = _build_formats_summary(normalized_formats)
        # Denormalized max-quality fields for server-side filtering/pagination
        max_h, max_label = _compute_max_quality_fields(normalized_formats)
        metadata['max_available_height'] = max_h
        metadata['max_quality_label'] = max_label
    except Exception:
        # Fail-safe: do not break metadata creation if formats are unexpected
        metadata['available_formats'] = None
        metadata['available_qualities_summary'] = None
        metadata['max_available_height'] = None
        metadata['max_quality_label'] = None

    return metadata


def save_video_metadata(metadata: Dict[str, Any], video_id: str = None, logger_func=None) -> bool:
    """
    Save video metadata to database using standardized approach.
    
    Args:
        metadata: Metadata dictionary (from create_metadata_dict_from_entry or similar)
        video_id: Video ID for logging (optional, extracted from metadata if not provided)
        logger_func: Optional logging function (uses log_message if not provided)
        
    Returns:
        True if saved successfully, False otherwise
    """
    if logger_func is None:
        logger_func = log_message
    
    if video_id is None:
        video_id = metadata.get('youtube_id', 'unknown')
    
    try:
        conn = get_connection()
        db.upsert_youtube_metadata(conn, metadata)
        conn.close()
        
        logger_func(f"[Metadata] Successfully saved metadata for video {video_id}")
        return True
        
    except Exception as e:
        logger_func(f"[Metadata] Error saving metadata for video {video_id}: {e}")
        return False


def save_video_metadata_from_entry(entry: Dict[str, Any], channel_url: str = None, logger_func=None) -> bool:
    """
    Extract metadata from yt-dlp entry and save to database in one step.
    
    Args:
        entry: Raw metadata entry from yt-dlp
        channel_url: Original channel URL to preserve in metadata
        logger_func: Optional logging function (uses log_message if not provided)
        
    Returns:
        True if saved successfully, False otherwise
    """
    try:
        # Create standardized metadata dictionary
        metadata = create_metadata_dict_from_entry(entry, channel_url)
        
        # Save to database
        return save_video_metadata(metadata, metadata['youtube_id'], logger_func)
        
    except Exception as e:
        video_id = entry.get('id', 'unknown')
        if logger_func is None:
            logger_func = log_message
        logger_func(f"[Metadata] Error processing metadata for video {video_id}: {e}")
        return False 
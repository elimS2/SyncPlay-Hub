#!/usr/bin/env python3
"""
Metadata utilities for YouTube video metadata processing.

Contains common functions for extracting, formatting and saving YouTube video metadata.
"""

from typing import Dict, Any, Optional
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from controllers.api.shared import get_connection, log_message
import database as db


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
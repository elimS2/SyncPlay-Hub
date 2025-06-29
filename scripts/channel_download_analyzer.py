#!/usr/bin/env python3
"""
Channel Download Analyzer

Analyzes channel download status by comparing metadata with locally downloaded files.
Shows detailed information about each video: download status, play statistics, deletion status.
Now includes functionality to detect and auto-queue incomplete downloads (audio-only .f251 files).

Usage:
    python scripts/channel_download_analyzer.py
    python scripts/channel_download_analyzer.py --channel-id 1
    python scripts/channel_download_analyzer.py --group-id 2
    python scripts/channel_download_analyzer.py --days-back 30
    python scripts/channel_download_analyzer.py --auto-queue-metadata
    python scripts/channel_download_analyzer.py --auto-queue-incomplete --channel-id 15
"""

import argparse
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from pathlib import Path
import re

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from database import get_connection, set_db_path
from utils.logging_utils import log_message

# Job Queue imports for automatic metadata extraction and incomplete download fixes
try:
    from services.job_queue_service import get_job_queue_service
    from services.job_types import JobType, JobPriority
    JOB_QUEUE_AVAILABLE = True
except ImportError:
    JOB_QUEUE_AVAILABLE = False
    print("[WARNING] Job Queue system not available. --auto-queue-metadata and --auto-queue-incomplete options will be disabled.")

# Try to load .env file manually
def load_env_file():
    """Load .env file manually and return config dict."""
    env_path = Path(__file__).parent.parent / '.env'
    config = {}
    
    if env_path.exists():
        try:
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        # Remove BOM if present
                        key = key.strip().lstrip('\ufeff')
                        config[key] = value.strip()
            print(f"[INFO] Loaded .env file from: {env_path}")
        except Exception as e:
            print(f"[WARNING] Error reading .env file: {e}")
    
    return config

# Load .env configuration
env_config = load_env_file()

# Global variable to track created jobs
metadata_jobs_created = 0
incomplete_download_jobs_created = 0

def get_channels_to_analyze(conn, channel_id: Optional[int] = None, group_id: Optional[int] = None) -> List[Dict]:
    """Get list of channels to analyze."""
    cur = conn.cursor()
    
    if channel_id:
        # Analyze specific channel
        cur.execute("""
            SELECT c.*, cg.name as group_name, cg.behavior_type
            FROM channels c
            JOIN channel_groups cg ON cg.id = c.channel_group_id
            WHERE c.id = ? AND c.enabled = 1
        """, (channel_id,))
    elif group_id:
        # Analyze all channels in group
        cur.execute("""
            SELECT c.*, cg.name as group_name, cg.behavior_type
            FROM channels c
            JOIN channel_groups cg ON cg.id = c.channel_group_id
            WHERE c.channel_group_id = ? AND c.enabled = 1
            ORDER BY c.name
        """, (group_id,))
    else:
        # Analyze all active channels
        cur.execute("""
            SELECT c.*, cg.name as group_name, cg.behavior_type
            FROM channels c
            JOIN channel_groups cg ON cg.id = c.channel_group_id
            WHERE c.enabled = 1
            ORDER BY cg.name, c.name
        """)
    
    return [dict(row) for row in cur.fetchall()]


def get_channel_metadata(conn, channel_url: str, date_from: Optional[str] = None) -> List[Dict]:
    """Get YouTube metadata for channel videos from specified date."""
    cur = conn.cursor()
    
    # Extract channel identifier from URL
    channel_id = None
    if '@' in channel_url:
        # @ChannelName format
        channel_name = channel_url.split('@')[1].split('/')[0]
        search_pattern = f'%@{channel_name}%'
    elif '/channel/' in channel_url:
        # /channel/UC... format
        channel_id = channel_url.split('/channel/')[1].split('/')[0]
        search_pattern = f'%{channel_id}%'
    elif '/c/' in channel_url:
        # /c/ChannelName format
        channel_name = channel_url.split('/c/')[1].split('/')[0]
        search_pattern = f'%{channel_name}%'
    else:
        search_pattern = f'%{channel_url}%'
    
    query = """
        SELECT * FROM youtube_video_metadata 
        WHERE (channel_url LIKE ? OR channel LIKE ?)
    """
    params = [search_pattern, search_pattern]
    
    # Add date filter if specified
    if date_from:
        # Convert date to timestamp for comparison
        try:
            date_obj = datetime.strptime(date_from, '%Y-%m-%d')
            timestamp = int(date_obj.timestamp())
            query += " AND (timestamp >= ? OR release_timestamp >= ?)"
            params.extend([timestamp, timestamp])
        except ValueError:
            print(f"Warning: Invalid date format '{date_from}', ignoring date filter")
    
    query += " ORDER BY timestamp DESC, release_timestamp DESC"
    
    cur.execute(query, params)
    return [dict(row) for row in cur.fetchall()]


def get_download_status(conn, youtube_id: str) -> Dict[str, Any]:
    """Get download and play status for a video."""
    cur = conn.cursor()
    
    status = {
        'downloaded': False,
        'deleted': False,
        'track_info': None,
        'play_stats': {
            'starts': 0,
            'finishes': 0,
            'nexts': 0,
            'prevs': 0,
            'likes': 0,
            'last_played': None
        },
        'deletion_info': None
    }
    
    # Check if downloaded (in tracks table)
    cur.execute("SELECT * FROM tracks WHERE video_id = ?", (youtube_id,))
    track = cur.fetchone()
    if track:
        status['downloaded'] = True
        status['track_info'] = dict(track)
        status['play_stats'].update({
            'starts': track['play_starts'] or 0,
            'finishes': track['play_finishes'] or 0,
            'nexts': track['play_nexts'] or 0,
            'prevs': track['play_prevs'] or 0,
            'likes': track['play_likes'] or 0,
            'last_played': track['last_start_ts'] or track['last_finish_ts']
        })
    
    # Check if deleted (in deleted_tracks table)
    cur.execute("""
        SELECT * FROM deleted_tracks 
        WHERE video_id = ? 
        ORDER BY deleted_at DESC 
        LIMIT 1
    """, (youtube_id,))
    deleted = cur.fetchone()
    if deleted:
        status['deleted'] = True
        status['deletion_info'] = dict(deleted)
    
    return status


def get_metadata_info(conn, channel_url: str) -> Dict[str, Any]:
    """Get metadata information for a channel."""
    cur = conn.cursor()
    
    # Count total metadata records for this channel
    # Use same pattern matching as get_channel_metadata
    if '@' in channel_url:
        # @ChannelName format
        channel_name = channel_url.split('@')[1].split('/')[0]
        search_pattern = f'%@{channel_name}%'
    elif '/channel/' in channel_url:
        # /channel/UC... format
        channel_id = channel_url.split('/channel/')[1].split('/')[0]
        search_pattern = f'%{channel_id}%'
    elif '/c/' in channel_url:
        # /c/ChannelName format
        channel_name = channel_url.split('/c/')[1].split('/')[0]
        search_pattern = f'%{channel_name}%'
    else:
        search_pattern = f'%{channel_url}%'
    
    cur.execute("""
        SELECT COUNT(*) as total_count,
               MAX(timestamp) as latest_video_timestamp,
               MIN(timestamp) as earliest_video_timestamp
        FROM youtube_video_metadata 
        WHERE (channel_url LIKE ? OR channel LIKE ?)
    """, (search_pattern, search_pattern))
    
    result = cur.fetchone()
    total_count = result[0] if result else 0
    latest_timestamp = result[1] if result else None
    earliest_timestamp = result[2] if result else None
    
    # Get metadata update info from channel table
    cur.execute("""
        SELECT metadata_last_updated 
        FROM channels 
        WHERE url = ?
    """, (channel_url,))
    
    result = cur.fetchone()
    last_updated = result[0] if result else None
    
    # Convert timestamps to readable dates
    latest_video_date = None
    earliest_video_date = None
    if latest_timestamp:
        try:
            latest_video_date = datetime.fromtimestamp(latest_timestamp).strftime('%Y-%m-%d')
        except (ValueError, OSError):
            latest_video_date = "Invalid date"
    
    if earliest_timestamp:
        try:
            earliest_video_date = datetime.fromtimestamp(earliest_timestamp).strftime('%Y-%m-%d')
        except (ValueError, OSError):
            earliest_video_date = "Invalid date"
    
    return {
        'has_metadata': total_count > 0,
        'total_count': total_count,
        'last_updated': last_updated,
        'latest_video_date': latest_video_date,
        'earliest_video_date': earliest_video_date
    }


def format_duration(seconds: Optional[float]) -> str:
    """Format duration in human readable format."""
    if seconds is None:
        return "Unknown"
    
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    if minutes >= 60:
        hours = int(minutes // 60)
        minutes = int(minutes % 60)
        return f"{hours}h {minutes}m {secs}s"
    else:
        return f"{minutes}m {secs}s"


def format_date(timestamp: Optional[int]) -> str:
    """Format timestamp to readable date."""
    if timestamp is None:
        return "Unknown"
    
    try:
        dt = datetime.fromtimestamp(timestamp)
        return dt.strftime('%Y-%m-%d %H:%M')
    except (ValueError, OSError):
        return "Invalid date"


def format_file_size(size_bytes: Optional[int]) -> str:
    """Format file size in human readable format."""
    if size_bytes is None:
        return "Unknown"
    
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def get_channel_folder_info(channel: Dict, root_dir: str) -> Dict[str, Any]:
    """Get information about channel folder and files."""
    from pathlib import Path
    
    channel_name = channel['name']
    group_name = channel.get('group_name', 'Unknown')
    
    # Try different possible folder structures
    possible_paths = []
    
    # Standard structure: ROOT_DIR/GROUP/Channel-NAME/
    if group_name and group_name != 'Unknown':
        standard_path = Path(root_dir) / group_name / f"Channel-{channel_name}"
        possible_paths.append(standard_path)
    
    # Legacy structure: ROOT_DIR/Channel-NAME/
    legacy_path = Path(root_dir) / f"Channel-{channel_name}"
    possible_paths.append(legacy_path)
    
    # Also try with spaces in channel name (fallback)
    for base_path in [Path(root_dir) / group_name if group_name and group_name != 'Unknown' else None, Path(root_dir)]:
        if base_path:
            # Find folder that starts with "Channel-" and contains the channel name
            if base_path.exists():
                for folder in base_path.iterdir():
                    if folder.is_dir() and folder.name.startswith("Channel-"):
                        # Simple name matching (could be improved)
                        if channel_name.lower() in folder.name.lower() or folder.name.lower() in channel_name.lower():
                            possible_paths.append(folder)
    
    # Check which folder exists and has content
    for folder_path in possible_paths:
        if folder_path.exists() and folder_path.is_dir():
            # Count media files
            media_extensions = ['.mp3', '.m4a', '.opus', '.webm', '.flac', '.mp4', '.mkv', '.mov']
            files = [f for f in folder_path.iterdir() if f.is_file() and f.suffix.lower() in media_extensions]
            
            return {
                'exists': True,
                'actual_path': str(folder_path),
                'expected_path': str(possible_paths[0]),
                'possible_paths': [str(p) for p in possible_paths],
                'file_count': len(files),
                'files': files
            }
    
    # No folder found
    return {
        'exists': False,
        'actual_path': None,
        'expected_path': str(possible_paths[0]) if possible_paths else 'Unknown',
        'possible_paths': [str(p) for p in possible_paths],
        'file_count': 0,
        'files': []
    }


def detect_incomplete_downloads(channel_folder_path: Path) -> List[Dict[str, Any]]:
    """
    Detect videos that have only audio (.f251) files without video component.
    
    Returns:
        List of incomplete download info dictionaries
    """
    incomplete_downloads = []
    
    if not channel_folder_path.exists():
        return incomplete_downloads
    
    # Pattern for extracting video ID from filename: Title [VIDEO_ID].ext
    video_id_pattern = re.compile(r'\[([A-Za-z0-9_-]{11})\]\.f251\.(webm|mp3|m4a)$')
    video_component_pattern = re.compile(r'\[([A-Za-z0-9_-]{11})\]\.(f\d+|mp4|webm|mkv|mov)$')
    
    # Find all .f251 audio files (these indicate audio-only downloads)
    audio_only_files = {}
    video_files = set()
    
    for file_path in channel_folder_path.iterdir():
        if file_path.is_file():
            filename = file_path.name
            
            # Check for .f251 audio files
            audio_match = video_id_pattern.search(filename)
            if audio_match:
                video_id = audio_match.group(1)
                audio_only_files[video_id] = {
                    'video_id': video_id,
                    'audio_file': file_path,
                    'filename': filename
                }
            
            # Check for video component files
            video_match = video_component_pattern.search(filename)
            if video_match:
                video_id = video_match.group(1)
                format_code = video_match.group(2)
                # Skip .f251 files as they are audio-only
                if format_code != 'f251':
                    video_files.add(video_id)
    
    # Find videos that have only audio (.f251) but no video component
    for video_id, audio_info in audio_only_files.items():
        if video_id not in video_files:
            incomplete_downloads.append({
                'video_id': video_id,
                'audio_file_path': audio_info['audio_file'],
                'audio_filename': audio_info['filename'],
                'missing_video': True,
                'file_size': audio_info['audio_file'].stat().st_size if audio_info['audio_file'].exists() else 0
            })
    
    return incomplete_downloads


def get_video_url_from_metadata(conn, video_id: str) -> Optional[str]:
    """Get YouTube URL for a video from metadata."""
    cur = conn.cursor()
    cur.execute("""
        SELECT url, webpage_url 
        FROM youtube_video_metadata 
        WHERE youtube_id = ?
    """, (video_id,))
    
    result = cur.fetchone()
    if result:
        # Try webpage_url first, then url
        return result['webpage_url'] or result['url'] or f"https://www.youtube.com/watch?v={video_id}"
    
    # Fallback to standard YouTube URL format
    return f"https://www.youtube.com/watch?v={video_id}"


def queue_incomplete_download_fixes(conn, channel: Dict, incomplete_downloads: List[Dict[str, Any]]) -> int:
    """
    Queue jobs to fix incomplete downloads.
    
    Checks for existing jobs to avoid duplicates. Will skip videos that already have
    jobs in pending, running, completed, or retrying status.
    
    Returns:
        Number of jobs created
    """
    if not JOB_QUEUE_AVAILABLE or not incomplete_downloads:
        return 0
    
    try:
        job_service = get_job_queue_service(max_workers=1)
        jobs_created = 0
        jobs_skipped = 0
        
        # Get channel folder info for target folder
        root_dir = env_config.get('ROOT_DIR', 'D:/music/Youtube')
        playlists_dir = env_config.get('PLAYLISTS_DIR', root_dir + '/Playlists')
        folder_info = get_channel_folder_info(channel, playlists_dir)
        
        if not folder_info['exists']:
            print(f"   [WARNING] Channel folder not found, cannot queue incomplete download fixes")
            return 0
        
        # Extract target folder from actual path
        channel_folder_path = Path(folder_info['actual_path'])
        
        # Determine target folder structure for job
        # e.g., "New Music/Channel-Artist" or just "Channel-Artist"
        root_path = Path(playlists_dir)
        print(f"   [DEBUG] Channel folder path: {channel_folder_path}")
        print(f"   [DEBUG] Root path: {root_path}")
        
        try:
            relative_path = channel_folder_path.relative_to(root_path)
            target_folder = str(relative_path)
            print(f"   [DEBUG] Relative path: {relative_path}")
            print(f"   [DEBUG] Target folder calculated: '{target_folder}'")
        except ValueError as e:
            # Fallback if path calculation fails - try to get relative path manually
            print(f"   [DEBUG] Path calculation failed ({e}) - attempting manual calculation")
            try:
                # Try to extract the relative part manually
                actual_path_str = str(channel_folder_path).replace('\\', '/')
                root_path_str = str(root_path).replace('\\', '/')
                
                if actual_path_str.startswith(root_path_str):
                    relative_part = actual_path_str[len(root_path_str):].strip('/')
                    target_folder = relative_part
                    print(f"   [DEBUG] Manual calculation successful: '{target_folder}'")
                else:
                    # Ultimate fallback - just use channel name
                    target_folder = channel_folder_path.name
                    print(f"   [DEBUG] Using ultimate fallback: '{target_folder}'")
            except Exception as e2:
                target_folder = channel_folder_path.name
                print(f"   [DEBUG] Manual calculation failed ({e2}) - using channel name: '{target_folder}'")
        
        print(f"   [INFO] Final target folder for jobs: '{target_folder}'")
        
        # Get existing jobs to check for duplicates
        # We check jobs with these statuses to avoid duplicates:
        # - pending: waiting to be executed
        # - running: currently executing
        # - retrying: waiting to retry
        # NOTE: 'completed' is excluded so we can re-download files that were saved to wrong location
        existing_video_jobs = set()
        
        for status in ['pending', 'running', 'retrying']:
            try:
                from services.job_types import JobStatus
                status_enum = JobStatus(status)
                existing_jobs = job_service.get_jobs(
                    status=status_enum,
                    job_type=JobType.SINGLE_VIDEO_DOWNLOAD,
                    limit=1000  # Get enough to check all possible duplicates
                )
                
                for job in existing_jobs:
                    job_data = job.job_data._data
                    playlist_url = job_data.get('playlist_url', '')
                    
                    # Extract video ID from playlist_url
                    # Handle various YouTube URL formats
                    video_id = None
                    if 'youtube.com/watch?v=' in playlist_url:
                        video_id = playlist_url.split('youtube.com/watch?v=')[1].split('&')[0]
                    elif 'youtu.be/' in playlist_url:
                        video_id = playlist_url.split('youtu.be/')[1].split('?')[0]
                    
                    if video_id:
                        existing_video_jobs.add(video_id)
                        
            except Exception as e:
                print(f"   [WARNING] Error checking existing jobs for status {status}: {e}")
                continue
        
        print(f"   [INFO] Found {len(existing_video_jobs)} existing video download jobs to avoid duplicating")
        
        for incomplete_download in incomplete_downloads:
            video_id = incomplete_download['video_id']
            
            # Check if job already exists for this video
            if video_id in existing_video_jobs:
                jobs_skipped += 1
                print(f"   [SKIPPED] Video {video_id} already has existing job (avoiding duplicate)")
                continue
            
            video_url = get_video_url_from_metadata(conn, video_id)
            
            if not video_url:
                print(f"   [WARNING] Could not find URL for video {video_id}, skipping")
                continue
            
            # Create single video download job
            job_id = job_service.create_and_add_job(
                JobType.SINGLE_VIDEO_DOWNLOAD,
                priority=JobPriority.NORMAL,
                playlist_url=video_url,
                target_folder=target_folder,
                format_selector='bestvideo+bestaudio/best',  # Ensure we get both video and audio
                extract_audio=False,  # We want video, not just audio
                download_archive=True,
                ignore_archive=True,  # Ignore archive entries to force re-download
                force_overwrites=True  # Force overwrite existing files
            )
            
            jobs_created += 1
            print(f"   [QUEUED] Incomplete download fix job #{job_id} for video {video_id}")
            
            # Log the action
            log_message(f"[Incomplete Download Fix] Queued job {job_id} for video {video_id} in channel {channel['name']}")
        
        if jobs_skipped > 0:
            print(f"   [INFO] Skipped {jobs_skipped} videos that already have existing jobs")
        
        return jobs_created
        
    except Exception as e:
        print(f"   [ERROR] Failed to queue incomplete download fixes: {e}")
        return 0


def print_channel_summary(conn, channel: Dict, video_count: int, downloaded_count: int, deleted_count: int, auto_queue_metadata: bool = False):
    """Print channel summary information."""
    global metadata_jobs_created
    
    print(f"\n{'='*80}")
    print(f"[CHANNEL] {channel['name']}")
    print(f"{'='*80}")
    print(f"URL: {channel['url']}")
    print(f"Group: {channel['group_name']} ({channel['behavior_type']})")
    print(f"Download from: {channel['date_from'] or 'All time'}")
    print(f"Last sync: {channel['last_sync_ts'] or 'Never'}")
    print(f"Database track count: {channel['track_count'] or 0}")
    
    # Show folder information
    root_dir = env_config.get('ROOT_DIR', 'D:/music/Youtube')
    playlists_dir = env_config.get('PLAYLISTS_DIR', root_dir + '/Playlists')
    folder_info = get_channel_folder_info(channel, playlists_dir)
    
    print(f"")
    print(f"[FOLDER INFORMATION]")
    if folder_info['exists']:
        print(f"   Local folder: {folder_info['actual_path']}")
        print(f"   Files in folder: {folder_info['file_count']}")
        
        # Check for incomplete downloads
        channel_folder_path = Path(folder_info['actual_path'])
        incomplete_downloads = detect_incomplete_downloads(channel_folder_path)
        
        if incomplete_downloads:
            print(f"   ⚠️  Incomplete downloads found: {len(incomplete_downloads)} (audio-only .f251 files)")
            if len(incomplete_downloads) <= 5:
                for incomplete in incomplete_downloads:
                    file_size_mb = incomplete['file_size'] / (1024 * 1024) if incomplete['file_size'] > 0 else 0
                    print(f"      - {incomplete['video_id']}: {incomplete['audio_filename']} ({file_size_mb:.1f} MB)")
            else:
                print(f"      First 5 incomplete downloads:")
                for incomplete in incomplete_downloads[:5]:
                    file_size_mb = incomplete['file_size'] / (1024 * 1024) if incomplete['file_size'] > 0 else 0
                    print(f"      - {incomplete['video_id']}: {incomplete['audio_filename']} ({file_size_mb:.1f} MB)")
                print(f"      ... and {len(incomplete_downloads) - 5} more")
        else:
            print(f"   ✅ All downloads appear complete (no audio-only .f251 files found)")
    else:
        print(f"   Expected folder: {folder_info['expected_path']}")
        print(f"   [ERROR] Folder does not exist")
        if len(folder_info['possible_paths']) > 1:
            print(f"   [INFO] Also checked: {', '.join(folder_info['possible_paths'][1:])}")
    
    # Show metadata information
    metadata_info = get_metadata_info(conn, channel['url'])
    
    print(f"")
    print(f"[METADATA INFORMATION]")
    if metadata_info['has_metadata']:
        print(f"   [OK] YouTube metadata: {metadata_info['total_count']} videos")
        if metadata_info['earliest_video_date'] and metadata_info['latest_video_date']:
            print(f"   Video range: {metadata_info['earliest_video_date']} to {metadata_info['latest_video_date']}")
        if metadata_info['last_updated']:
            print(f"   Metadata updated: {metadata_info['last_updated']}")
        else:
            print(f"   Metadata updated: Unknown (update database schema)")
    else:
        print(f"   [ERROR] No YouTube metadata found")
        
        # Auto-queue metadata extraction if enabled
        if auto_queue_metadata and JOB_QUEUE_AVAILABLE:
            try:
                job_service = get_job_queue_service(max_workers=1)
                job_id = job_service.create_and_add_job(
                    JobType.METADATA_EXTRACTION,
                    priority=JobPriority.HIGH,
                    channel_url=channel['url'],
                    channel_id=channel['id'],
                    force_update=False
                )
                metadata_jobs_created += 1
                print(f"   [QUEUED] Auto-queued metadata extraction job #{job_id}")
                print(f"   [INFO] Job will start automatically when workers are available")
            except Exception as e:
                print(f"   [WARNING] Failed to queue metadata extraction: {e}")
        else:
            print(f"   [HINT] Run: python scripts/extract_channel_metadata.py \"{channel['url']}\"")
            if auto_queue_metadata and not JOB_QUEUE_AVAILABLE:
                print(f"   [WARNING] Auto-queueing disabled: Job Queue system not available")
    
    print(f"")
    print(f"[ANALYSIS RESULTS]")
    print(f"   Total videos in metadata: {video_count}")
    print(f"   Downloaded locally: {downloaded_count}")
    print(f"   Previously deleted: {deleted_count}")
    if video_count > 0:
        download_rate = (downloaded_count / video_count) * 100
        print(f"   Download rate: {download_rate:.1f}%")
    
        undownloaded = video_count - downloaded_count
        if undownloaded > 0:
            print(f"   Still to download: {undownloaded}")


def print_video_status(video: Dict, status: Dict, show_details: bool = True):
    """Print detailed video status information."""
    youtube_id = video['youtube_id']
    title = video['title'] or 'Unknown Title'
    
    # Truncate long titles
    if len(title) > 60:
        title = title[:57] + "..."
    
    # Status icon
    if status['downloaded']:
        if status['deleted']:
            icon = "[REDOWNLOAD]"  # Downloaded but later deleted
            status_text = "Downloaded → Deleted"
        else:
            icon = "[OK]"  # Currently downloaded
            status_text = "Downloaded"
    elif status['deleted']:
        icon = "[DELETED]"   # Deleted (never downloaded or deleted without download)
        status_text = "Deleted"
    else:
        icon = "[MISSING]"   # Not downloaded
        status_text = "Not Downloaded"
    
    # Basic info line
    duration_str = format_duration(video.get('duration'))
    published = format_date(video.get('timestamp') or video.get('release_timestamp'))
    views = video.get('view_count') or 0
    
    print(f"{icon} [{youtube_id}] {title}")
    print(f"   Published: {published} | Duration: {duration_str} | Views: {views:,}")
    
    if show_details:
        # Download details
        if status['downloaded']:
            track = status['track_info']
            file_size = format_file_size(track.get('size_bytes'))
            file_path = track.get('relpath', 'Unknown path')
            print(f"   File: {file_path} ({file_size})")
            
            # Play statistics
            stats = status['play_stats']
            if any(stats[k] > 0 for k in ['starts', 'finishes', 'nexts', 'prevs', 'likes']):
                print(f"   Played: {stats['starts']} starts, {stats['finishes']} finishes, {stats['likes']} likes")
                if stats['last_played']:
                    print(f"   Last played: {stats['last_played']}")
        
        # Deletion details
        if status['deleted']:
            deletion = status['deletion_info']
            deleted_at = deletion.get('deleted_at', 'Unknown')
            reason = deletion.get('deletion_reason', 'Unknown')
            print(f"   Deleted: {deleted_at} (reason: {reason})")
            if deletion.get('can_restore'):
                print(f"   Can be restored from: {deletion.get('trash_path', 'Unknown')}")
    
    print()


def analyze_channel(conn, channel: Dict, days_back: Optional[int] = None, show_details: bool = True, auto_queue_metadata: bool = False, auto_queue_incomplete: bool = False) -> Dict[str, int]:
    """Analyze a single channel and return statistics."""
    global incomplete_download_jobs_created
    
    # Get date filter
    date_from = channel['date_from']
    if days_back:
        cutoff_date = datetime.now() - timedelta(days=days_back)
        filter_date = cutoff_date.strftime('%Y-%m-%d')
        # Use the more restrictive date
        if date_from:
            date_from = max(date_from, filter_date)
        else:
            date_from = filter_date
    
    # Get metadata for this channel
    videos = get_channel_metadata(conn, channel['url'], date_from)
    
    # Analyze each video
    downloaded_count = 0
    deleted_count = 0
    
    for video in videos:
        status = get_download_status(conn, video['youtube_id'])
        
        if status['downloaded']:
            downloaded_count += 1
        if status['deleted']:
            deleted_count += 1
        
        if show_details:
            print_video_status(video, status, show_details=True)
    
    # Check for incomplete downloads and auto-queue fixes if enabled
    incomplete_count = 0
    if auto_queue_incomplete:
        root_dir = env_config.get('ROOT_DIR', 'D:/music/Youtube')
        playlists_dir = env_config.get('PLAYLISTS_DIR', root_dir + '/Playlists')
        folder_info = get_channel_folder_info(channel, playlists_dir)
        
        if folder_info['exists']:
            channel_folder_path = Path(folder_info['actual_path'])
            incomplete_downloads = detect_incomplete_downloads(channel_folder_path)
            incomplete_count = len(incomplete_downloads)
            
            if incomplete_downloads:
                print(f"\n[INCOMPLETE DOWNLOAD FIXES]")
                print(f"Found {len(incomplete_downloads)} incomplete downloads (audio-only .f251 files)")
                
                # Queue jobs to fix incomplete downloads
                jobs_created = queue_incomplete_download_fixes(conn, channel, incomplete_downloads)
                incomplete_download_jobs_created += jobs_created
                
                if jobs_created > 0:
                    print(f"Created {jobs_created} jobs to fix incomplete downloads")
                else:
                    print(f"Failed to create jobs for incomplete download fixes")
    
    # Print summary
    print_channel_summary(conn, channel, len(videos), downloaded_count, deleted_count, auto_queue_metadata)
    
    return {
        'total_videos': len(videos),
        'downloaded': downloaded_count,
        'deleted': deleted_count,
        'not_downloaded': len(videos) - downloaded_count,
        'incomplete_downloads': incomplete_count
    }


def main():
    """Main function with command line argument parsing."""
    parser = argparse.ArgumentParser(
        description="Analyze channel download status and detect incomplete downloads",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python scripts/channel_download_analyzer.py                                # Analyze all channels
    python scripts/channel_download_analyzer.py --channel-id 1                 # Specific channel
    python scripts/channel_download_analyzer.py --group-id 2                   # All channels in group
    python scripts/channel_download_analyzer.py --days-back 30                 # Last 30 days only
    python scripts/channel_download_analyzer.py --summary-only                 # Just summaries
    python scripts/channel_download_analyzer.py --auto-queue-metadata          # Auto-queue metadata extraction
    python scripts/channel_download_analyzer.py --auto-queue-incomplete --channel-id 15  # Fix incomplete downloads
    python scripts/channel_download_analyzer.py --db-path "D:/music/Youtube/DB/tracks.db"  # Use specific database

Incomplete Download Detection:
    The script can detect videos that were downloaded incompletely (audio-only .f251 files without video component).
    Use --auto-queue-incomplete to automatically create jobs to re-download these videos with proper video quality.
    
    Example for fixing incomplete downloads in channel 15:
    python scripts/channel_download_analyzer.py --channel-id 15 --auto-queue-incomplete

.env file variables:
    DB_PATH         Path to the database file (e.g., D:/music/Youtube/DB/tracks.db)
    ROOT_DIR        Path to the media files root directory (e.g., D:/music/Youtube)
        """
    )
    
    parser.add_argument(
        "--channel-id",
        type=int,
        help="Analyze specific channel by ID"
    )
    
    parser.add_argument(
        "--group-id", 
        type=int,
        help="Analyze all channels in specific group"
    )
    
    parser.add_argument(
        "--days-back",
        type=int,
        help="Only analyze videos from last N days"
    )
    
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Show only summary without individual video details"
    )
    
    parser.add_argument(
        "--db-path",
        type=str,
        help="Path to the database file (overrides .env file)"
    )
    
    parser.add_argument(
        "--auto-queue-metadata",
        action="store_true",
        help="Automatically queue metadata extraction for channels without metadata"
    )
    
    parser.add_argument(
        "--auto-queue-incomplete",
        action="store_true",
        help="Automatically queue incomplete download fixes for channels without complete downloads"
    )
    
    args = parser.parse_args()
    
    # Set database path from command line argument or .env file
    db_path = args.db_path
    if not db_path:
        db_path = env_config.get('DB_PATH')
    
    if db_path:
        # Check if path exists
        db_file = Path(db_path)
        if db_file.exists():
            set_db_path(db_path)
            print(f"[INFO] Using database: {db_path}")
        else:
            print(f"[WARNING] Database file not found: {db_path}")
            print(f"[INFO] Using default database: tracks.db (current directory)")
    else:
        print(f"[INFO] Using default database: tracks.db (current directory)")
        print(f"[HINT] Set DB_PATH in .env file or use --db-path to specify database location")
    
    try:
        conn = get_connection()
        
        # Get channels to analyze
        channels = get_channels_to_analyze(conn, args.channel_id, args.group_id)
        
        if not channels:
            print("[ERROR] No active channels found matching the criteria.")
            return
        
        print(f"[ANALYZING] {len(channels)} CHANNEL(S)")
        if args.days_back:
            print(f"Filtering videos from last {args.days_back} days")
        
        # Show brief channel overview with folder info
        if len(channels) > 1:
            print(f"\n[CHANNELS OVERVIEW]")
            root_dir = env_config.get('ROOT_DIR', 'D:/music/Youtube')
            playlists_dir = env_config.get('PLAYLISTS_DIR', root_dir + '/Playlists')
            
            for channel in channels:
                folder_info = get_channel_folder_info(channel, playlists_dir)
                folder_icon = "[FOLDER]" if folder_info['exists'] else "[NO_FOLDER]"
                folder_text = f"({folder_info['file_count']} files)" if folder_info['exists'] else "(no folder)"
                
                print(f"   {channel['name']:25} | Group: {channel['group_name']:15} | {folder_icon} {folder_text}")
        
        # Show metadata auto-queueing status
        if args.auto_queue_metadata:
            if JOB_QUEUE_AVAILABLE:
                print(f"[AUTO-QUEUE] Metadata extraction enabled")
                print(f"[INFO] Will create jobs for channels missing metadata")
            else:
                print(f"[WARNING] Auto-queueing disabled: Job Queue system not available")
        
        # Show incomplete download auto-queueing status
        if args.auto_queue_incomplete:
            if JOB_QUEUE_AVAILABLE:
                print(f"[AUTO-QUEUE] Incomplete download fixes enabled")
                print(f"[INFO] Will create jobs for channels missing complete downloads")
            else:
                print(f"[WARNING] Auto-queueing disabled: Job Queue system not available")
        
        # Analyze each channel
        total_stats = {
            'total_videos': 0,
            'downloaded': 0,
            'deleted': 0,
            'not_downloaded': 0,
            'incomplete_downloads': 0
        }
        
        for i, channel in enumerate(channels, 1):
            print(f"\n[{i}/{len(channels)}]")
            
            stats = analyze_channel(
                conn, 
                channel, 
                days_back=args.days_back, 
                show_details=not args.summary_only,
                auto_queue_metadata=args.auto_queue_metadata,
                auto_queue_incomplete=args.auto_queue_incomplete
            )
            
            # Add to totals
            for key in total_stats:
                total_stats[key] += stats[key]
        
        # Print overall summary
        if len(channels) > 1:
            print(f"\n{'='*80}")
            print(f"[OVERALL SUMMARY] ({len(channels)} channels)")
            print(f"{'='*80}")
            print(f"Total videos in metadata: {total_stats['total_videos']}")
            print(f"Downloaded locally: {total_stats['downloaded']}")
            print(f"Previously deleted: {total_stats['deleted']}")
            print(f"Not downloaded: {total_stats['not_downloaded']}")
            print(f"Incomplete downloads found: {total_stats['incomplete_downloads']}")
            
            if total_stats['total_videos'] > 0:
                download_rate = (total_stats['downloaded'] / total_stats['total_videos']) * 100
                print(f"Overall download rate: {download_rate:.1f}%")
            
            # Show incomplete download rate if any found
            if total_stats['downloaded'] > 0 and total_stats['incomplete_downloads'] > 0:
                incomplete_rate = (total_stats['incomplete_downloads'] / total_stats['downloaded']) * 100
                print(f"Incomplete download rate: {incomplete_rate:.1f}% ({total_stats['incomplete_downloads']} of {total_stats['downloaded']} downloaded)")
            
            # Folder summary
            print(f"\n[FOLDER SUMMARY]")
            root_dir = env_config.get('ROOT_DIR', 'D:/music/Youtube')
            playlists_dir = env_config.get('PLAYLISTS_DIR', root_dir + '/Playlists')
            folders_exist = 0
            total_files = 0
            
            for channel in channels:
                folder_info = get_channel_folder_info(channel, playlists_dir)
                if folder_info['exists']:
                    folders_exist += 1
                    total_files += folder_info['file_count']
            
            print(f"Folders exist: {folders_exist}/{len(channels)}")
            print(f"Total files in folders: {total_files}")
            print(f"Root directory: {root_dir}")
        
        # Show metadata job creation summary
        if args.auto_queue_metadata and metadata_jobs_created > 0:
            print(f"\n[METADATA EXTRACTION JOBS CREATED]")
            print(f"Jobs queued: {metadata_jobs_created}")
            print(f"Jobs will be processed automatically by job queue workers")
            print(f"Monitor job progress at: /jobs (web interface)")
        elif args.auto_queue_metadata and metadata_jobs_created == 0:
            print(f"\n[INFO] All channels already have metadata - no jobs needed")
        
        # Show incomplete download job creation summary
        if args.auto_queue_incomplete and incomplete_download_jobs_created > 0:
            print(f"\n[INCOMPLETE DOWNLOAD FIXES CREATED]")
            print(f"Jobs queued: {incomplete_download_jobs_created}")
            print(f"Jobs will be processed automatically by job queue workers")
            print(f"Monitor job progress at: /jobs (web interface)")
            print(f"[INFO] These jobs will re-download videos to get the missing video components")
        elif args.auto_queue_incomplete and incomplete_download_jobs_created == 0:
            if args.auto_queue_incomplete:
                print(f"\n[INFO] All downloaded videos appear complete - no incomplete download fixes needed")
        
        conn.close()
        
    except KeyboardInterrupt:
        print("\n[CANCELLED] Analysis cancelled by user")
    except Exception as e:
        print(f"[ERROR] Error during analysis: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main() 
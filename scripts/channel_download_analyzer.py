#!/usr/bin/env python3
"""
Channel Download Analyzer

Analyzes channel download status by comparing metadata with locally downloaded files.
Shows detailed information about each video: download status, play statistics, deletion status.

Usage:
    python scripts/channel_download_analyzer.py
    python scripts/channel_download_analyzer.py --channel-id 1
    python scripts/channel_download_analyzer.py --group-id 2
    python scripts/channel_download_analyzer.py --days-back 30
"""

import argparse
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from database import get_connection, set_db_path
from utils.logging_utils import log_message

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
            print(f"📄 Loaded .env file from: {env_path}")
        except Exception as e:
            print(f"⚠️  Error reading .env file: {e}")
    
    return config

# Load .env configuration
env_config = load_env_file()


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
    """Determine channel folder path and check if it exists."""
    from pathlib import Path
    
    root_path = Path(root_dir)
    group_name = channel['group_name']
    channel_name = channel['name']
    channel_url = channel['url']
    
    # Try multiple possible folder names (expanded logic for real-world folders)
    possible_folders = []
    
    # 1. Full channel name
    possible_folders.append(root_path / group_name / f"Channel-{channel_name}")
    
    # 2. Extract channel name from URL (@username)
    if '@' in channel_url:
        url_channel_name = channel_url.split('@')[1].split('/')[0]
        possible_folders.append(root_path / group_name / f"Channel-{url_channel_name}")
    
    # 3. Short name (remove common suffixes)
    short_name = channel_name.replace('enjoy', '').replace('music', '').replace('official', '').strip()
    if short_name != channel_name:
        possible_folders.append(root_path / group_name / f"Channel-{short_name}")
    
    # 4. Uppercase short name
    possible_folders.append(root_path / group_name / f"Channel-{short_name.upper()}")
    
    # 5. Channel name with spaces (for names like "Ann in Black")
    spaced_name = channel_name.replace('InBlack', ' in Black').replace('BAND', '').strip()
    if spaced_name != channel_name:
        possible_folders.append(root_path / group_name / f"Channel-{spaced_name}")
    
    # 6. Capitalized short names (Wellboy vs WELLBOYmusic)
    capitalized_short = short_name.capitalize()
    if capitalized_short != short_name:
        possible_folders.append(root_path / group_name / f"Channel-{capitalized_short}")
    
    # 7. Try searching in group folder for any Channel-* folders (brute force)
    group_folder = root_path / group_name
    if group_folder.exists():
        for item in group_folder.iterdir():
            if item.is_dir() and item.name.startswith('Channel-'):
                folder_channel_name = item.name[8:]  # Remove "Channel-" prefix
                # Check if this could be our channel (contains part of our name)
                if (folder_channel_name.upper() in channel_name.upper() or 
                    channel_name.upper() in folder_channel_name.upper() or
                    any(part in folder_channel_name.upper() for part in channel_name.upper().split()) or
                    any(part in channel_name.upper() for part in folder_channel_name.upper().split())):
                    possible_folders.append(item)
    
    # Check which folder exists and count files
    result = {
        'expected_path': str(possible_folders[0]),  # Primary expected path
        'actual_path': None,
        'exists': False,
        'file_count': 0,
        'possible_paths': [str(p) for p in possible_folders]
    }
    
    # Find existing folder
    for folder_path in possible_folders:
        if folder_path.exists():
            result['actual_path'] = str(folder_path)
            result['exists'] = True
            
            # Count media files
            video_extensions = ['.mp4', '.webm', '.mkv', '.avi', '.mp3', '.m4a']
            media_files = [f for f in folder_path.iterdir() 
                          if f.is_file() and f.suffix.lower() in video_extensions]
            result['file_count'] = len(media_files)
            break
    
    return result


def print_channel_summary(channel: Dict, video_count: int, downloaded_count: int, deleted_count: int):
    """Print channel summary information."""
    print(f"\n{'='*80}")
    print(f"📺 CHANNEL: {channel['name']}")
    print(f"{'='*80}")
    print(f"🔗 URL: {channel['url']}")
    print(f"📁 Group: {channel['group_name']} ({channel['behavior_type']})")
    print(f"📅 Download from: {channel['date_from'] or 'All time'}")
    print(f"🔄 Last sync: {channel['last_sync_ts'] or 'Never'}")
    print(f"📊 Database track count: {channel['track_count'] or 0}")
    
    # Show folder information
    root_dir = env_config.get('ROOT_DIR', 'D:/music/Youtube')
    folder_info = get_channel_folder_info(channel, root_dir)
    
    print(f"")
    print(f"📂 FOLDER INFORMATION:")
    if folder_info['exists']:
        print(f"   📁 Local folder: {folder_info['actual_path']}")
        print(f"   📄 Files in folder: {folder_info['file_count']}")
    else:
        print(f"   📁 Expected folder: {folder_info['expected_path']}")
        print(f"   ❌ Folder does not exist")
        if len(folder_info['possible_paths']) > 1:
            print(f"   💡 Also checked: {', '.join(folder_info['possible_paths'][1:])}")
    
    print(f"")
    print(f"📈 ANALYSIS RESULTS:")
    print(f"   📺 Total videos in metadata: {video_count}")
    print(f"   ✅ Downloaded locally: {downloaded_count}")
    print(f"   🗑️  Previously deleted: {deleted_count}")
    print(f"   ❌ Not downloaded: {video_count - downloaded_count}")
    
    if video_count > 0:
        download_rate = (downloaded_count / video_count) * 100
        print(f"   📊 Download rate: {download_rate:.1f}%")
    
    print(f"\n{'─'*80}")


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
            icon = "🔄"  # Downloaded but later deleted
            status_text = "Downloaded → Deleted"
        else:
            icon = "✅"  # Currently downloaded
            status_text = "Downloaded"
    elif status['deleted']:
        icon = "🗑️"   # Deleted (never downloaded or deleted without download)
        status_text = "Deleted"
    else:
        icon = "❌"   # Not downloaded
        status_text = "Not Downloaded"
    
    # Basic info line
    duration_str = format_duration(video.get('duration'))
    published = format_date(video.get('timestamp') or video.get('release_timestamp'))
    views = video.get('view_count') or 0
    
    print(f"{icon} [{youtube_id}] {title}")
    print(f"   📅 Published: {published} | ⏱️  Duration: {duration_str} | 👁️  Views: {views:,}")
    
    if show_details:
        # Download details
        if status['downloaded']:
            track = status['track_info']
            file_size = format_file_size(track.get('size_bytes'))
            file_path = track.get('relpath', 'Unknown path')
            print(f"   💾 File: {file_path} ({file_size})")
            
            # Play statistics
            stats = status['play_stats']
            if any(stats[k] > 0 for k in ['starts', 'finishes', 'nexts', 'prevs', 'likes']):
                print(f"   🎵 Played: {stats['starts']} starts, {stats['finishes']} finishes, {stats['likes']} likes")
                if stats['last_played']:
                    print(f"   🕒 Last played: {stats['last_played']}")
        
        # Deletion details
        if status['deleted']:
            deletion = status['deletion_info']
            deleted_at = deletion.get('deleted_at', 'Unknown')
            reason = deletion.get('deletion_reason', 'Unknown')
            print(f"   🗑️  Deleted: {deleted_at} (reason: {reason})")
            if deletion.get('can_restore'):
                print(f"   ♻️  Can be restored from: {deletion.get('trash_path', 'Unknown')}")
    
    print()


def analyze_channel(conn, channel: Dict, days_back: Optional[int] = None, show_details: bool = True) -> Dict[str, int]:
    """Analyze a single channel and return statistics."""
    
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
    
    # Print summary
    print_channel_summary(channel, len(videos), downloaded_count, deleted_count)
    
    return {
        'total_videos': len(videos),
        'downloaded': downloaded_count,
        'deleted': deleted_count,
        'not_downloaded': len(videos) - downloaded_count
    }


def main():
    """Main function with command line argument parsing."""
    parser = argparse.ArgumentParser(
        description="Analyze channel download status and statistics",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python scripts/channel_download_analyzer.py                                # Analyze all channels
    python scripts/channel_download_analyzer.py --channel-id 1                 # Specific channel
    python scripts/channel_download_analyzer.py --group-id 2                   # All channels in group
    python scripts/channel_download_analyzer.py --days-back 30                 # Last 30 days only
    python scripts/channel_download_analyzer.py --summary-only                 # Just summaries
    python scripts/channel_download_analyzer.py --db-path "D:/music/Youtube/DB/tracks.db"  # Use specific database

.env file variables:
    DB_PATH         Path to the database file (e.g., D:/music/Youtube/DB/tracks.db)
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
            print(f"🔗 Using database: {db_path}")
        else:
            print(f"⚠️  Database file not found: {db_path}")
            print(f"🔗 Using default database: tracks.db (current directory)")
    else:
        print(f"🔗 Using default database: tracks.db (current directory)")
        print(f"💡 Set DB_PATH in .env file or use --db-path to specify database location")
    
    try:
        conn = get_connection()
        
        # Get channels to analyze
        channels = get_channels_to_analyze(conn, args.channel_id, args.group_id)
        
        if not channels:
            print("❌ No active channels found matching the criteria.")
            return
        
        print(f"🎯 ANALYZING {len(channels)} CHANNEL(S)")
        if args.days_back:
            print(f"📅 Filtering videos from last {args.days_back} days")
        
        # Show brief channel overview with folder info
        if len(channels) > 1:
            print(f"\n📋 CHANNELS OVERVIEW:")
            root_dir = env_config.get('ROOT_DIR', 'D:/music/Youtube')
            
            for channel in channels:
                folder_info = get_channel_folder_info(channel, root_dir)
                folder_icon = "📁" if folder_info['exists'] else "❌"
                folder_text = f"({folder_info['file_count']} files)" if folder_info['exists'] else "(no folder)"
                
                print(f"   📺 {channel['name']:25} | Group: {channel['group_name']:15} | {folder_icon} {folder_text}")
        
        # Analyze each channel
        total_stats = {
            'total_videos': 0,
            'downloaded': 0,
            'deleted': 0,
            'not_downloaded': 0
        }
        
        for i, channel in enumerate(channels, 1):
            print(f"\n[{i}/{len(channels)}]")
            
            stats = analyze_channel(
                conn, 
                channel, 
                days_back=args.days_back, 
                show_details=not args.summary_only
            )
            
            # Add to totals
            for key in total_stats:
                total_stats[key] += stats[key]
        
        # Print overall summary
        if len(channels) > 1:
            print(f"\n{'='*80}")
            print(f"📊 OVERALL SUMMARY ({len(channels)} channels)")
            print(f"{'='*80}")
            print(f"📺 Total videos in metadata: {total_stats['total_videos']}")
            print(f"✅ Downloaded locally: {total_stats['downloaded']}")
            print(f"🗑️  Previously deleted: {total_stats['deleted']}")
            print(f"❌ Not downloaded: {total_stats['not_downloaded']}")
            
            if total_stats['total_videos'] > 0:
                download_rate = (total_stats['downloaded'] / total_stats['total_videos']) * 100
                print(f"📊 Overall download rate: {download_rate:.1f}%")
            
            # Folder summary
            print(f"\n📂 FOLDER SUMMARY:")
            root_dir = env_config.get('ROOT_DIR', 'D:/music/Youtube')
            folders_exist = 0
            total_files = 0
            
            for channel in channels:
                folder_info = get_channel_folder_info(channel, root_dir)
                if folder_info['exists']:
                    folders_exist += 1
                    total_files += folder_info['file_count']
            
            print(f"📁 Folders exist: {folders_exist}/{len(channels)}")
            print(f"📄 Total files in folders: {total_files}")
            print(f"📍 Root directory: {root_dir}")
        
        conn.close()
        
    except KeyboardInterrupt:
        print("\n❌ Analysis cancelled by user")
    except Exception as e:
        print(f"❌ Error during analysis: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main() 
#!/usr/bin/env python3
"""
YouTube Channel Metadata Extractor

This script extracts metadata from YouTube channel videos using yt-dlp
and stores/updates the data in the youtube_video_metadata database table.

Usage:
    python extract_channel_metadata.py "https://www.youtube.com/@SomeChannel/videos"
    python extract_channel_metadata.py "https://www.youtube.com/c/SomeChannel/videos"
    python extract_channel_metadata.py "https://www.youtube.com/channel/UC.../videos"

Requirements:
    - yt-dlp installed (pip install yt-dlp)
    - Database with youtube_video_metadata table
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from typing import Dict, List, Any, Optional
import os
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

# Load .env file manually
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
                        config[key] = value.strip()  # Remove trailing/leading spaces
            print(f"[INFO] Loaded .env file from: {env_path}")
        except Exception as e:
            print(f"[WARNING] Error reading .env file: {e}")
    
    return config

# Load .env configuration
env_config = load_env_file()

from utils.logging_utils import log_message
from utils.cookies_manager import get_random_cookie_file
from database import (
    get_connection, 
    set_db_path,
    upsert_youtube_metadata, 
    get_youtube_metadata_by_id,
    get_channel_by_url
)

def get_channel_date_from(channel_url: str) -> Optional[str]:
    """Get date_from setting for channel from database"""
    try:
        conn = get_connection()
        channel = get_channel_by_url(conn, channel_url)
        conn.close()
        
        if channel and channel['date_from']:
            log_message(f"Found channel date_from setting: {channel['date_from']}")
            return channel['date_from']
        else:
            log_message("No date_from setting found for channel")
            return None
    except Exception as e:
        log_message(f"Error getting channel date_from: {e}")
        return None

def parse_upload_date(date_str: str) -> Optional[datetime]:
    """Parse upload date from yt-dlp metadata"""
    if not date_str:
        return None
    
    try:
        # Try YYYYMMDD format first
        if len(date_str) == 8 and date_str.isdigit():
            return datetime.strptime(date_str, '%Y%m%d')
        
        # Try other common formats
        for fmt in ['%Y-%m-%d', '%Y/%m/%d', '%d.%m.%Y']:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        
        log_message(f"Could not parse date: {date_str}")
        return None
    except Exception as e:
        log_message(f"Error parsing date '{date_str}': {e}")
        return None

def check_videos_newer_than_date(metadata_list: List[Dict], date_from: str) -> bool:
    """Check if any videos in metadata list are newer than date_from"""
    try:
        target_date = datetime.strptime(date_from, '%Y-%m-%d')
        
        for video in metadata_list:
            # Check upload_date field
            upload_date_str = video.get('upload_date')
            if upload_date_str:
                upload_date = parse_upload_date(upload_date_str)
                if upload_date and upload_date >= target_date:
                    return True
            
            # Check timestamp field (Unix timestamp)
            timestamp = video.get('timestamp')
            if timestamp:
                try:
                    video_date = datetime.fromtimestamp(timestamp)
                    if video_date >= target_date:
                        return True
                except (ValueError, OSError):
                    pass
            
            # Check release_timestamp field
            release_timestamp = video.get('release_timestamp')
            if release_timestamp:
                try:
                    video_date = datetime.fromtimestamp(release_timestamp)
                    if video_date >= target_date:
                        return True
                except (ValueError, OSError):
                    pass
        
        return False
    except Exception as e:
        log_message(f"Error checking video dates: {e}")
        return True  # Continue on error to be safe

def run_ytdlp_extract_batch(url: str, start_index: int, batch_size: int = 50, 
                           cookies_path: str = None) -> List[Dict[str, Any]]:
    """
    Run yt-dlp to extract a batch of metadata from YouTube channel
    
    Args:
        url: YouTube channel URL
        start_index: Starting index (1-based)
        batch_size: Number of videos to extract
        cookies_path: Path to cookies file (optional)
        
    Returns:
        List of video metadata dictionaries
        
    Raises:
        RuntimeError: If yt-dlp command fails
    """
    # Build playlist-items range
    end_index = start_index + batch_size - 1
    playlist_items = f"{start_index}:{end_index}"
    
    # Build yt-dlp command
    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--dump-json",
        url,
        "--playlist-items", playlist_items
    ]
    
    # Add cookies if provided
    if cookies_path:
        cmd.extend(["--cookies", cookies_path])
        log_message(f"Using cookies file: {cookies_path}")
    
    log_message(f"Executing yt-dlp command: {' '.join(cmd)}")
    log_message(f"Extracting videos {start_index}-{end_index} (batch of {batch_size})")
    
    try:
        # Run yt-dlp command
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout per batch
        )
        
        if result.returncode != 0:
            error_msg = f"yt-dlp failed with exit code {result.returncode}"
            if result.stderr:
                error_msg += f"\nError output: {result.stderr}"
            raise RuntimeError(error_msg)
        
        # Parse JSON output
        metadata_list = []
        for line in result.stdout.strip().split('\n'):
            if line.strip():
                try:
                    metadata = json.loads(line)
                    metadata_list.append(metadata)
                except json.JSONDecodeError as e:
                    log_message(f"Warning: Failed to parse JSON line: {e}")
                    continue
        
        log_message(f"Successfully extracted {len(metadata_list)} videos")
        return metadata_list
        
    except subprocess.TimeoutExpired:
        raise RuntimeError("yt-dlp command timed out (5 minutes)")
    except Exception as e:
        raise RuntimeError(f"Error running yt-dlp: {e}")

def get_video_date(video_id: str, cookies_path: str = None) -> Optional[str]:
    """Get upload date for a specific video ID"""
    try:
        cmd = ["yt-dlp", "--dump-json", f"https://www.youtube.com/watch?v={video_id}"]
        
        if cookies_path:
            cmd.extend(["--cookies", cookies_path])
        
        log_message(f"Getting date for video {video_id}: {' '.join(cmd)}")
        
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        video_data = json.loads(result.stdout)
        
        upload_date = video_data.get('upload_date')
        if upload_date:
            log_message(f"Video {video_id} upload date: {upload_date}")
            return upload_date
        else:
            log_message(f"Warning: No upload_date found for video {video_id}")
            return None
            
    except subprocess.CalledProcessError as e:
        log_message(f"Error getting date for video {video_id}: {e}")
        return None
    except json.JSONDecodeError as e:
        log_message(f"Error parsing JSON for video {video_id}: {e}")
        return None
    except Exception as e:
        log_message(f"Unexpected error getting date for video {video_id}: {e}")
        return None

def find_date_boundary_in_batch(metadata_list: List[Dict[str, Any]], date_from: str) -> int:
    """Find the exact position where videos become too old"""
    boundary_position = len(metadata_list)  # Default: all videos are new enough
    
    # Convert date_from to datetime for comparison
    try:
        target_date = datetime.strptime(date_from, '%Y-%m-%d')
    except ValueError:
        log_message(f"Invalid date_from format: {date_from}")
        return 0
    
    for i, video in enumerate(metadata_list):
        video_date = None
        
        # Try different date fields
        upload_date = video.get('upload_date')
        if upload_date:
            video_date = parse_upload_date(upload_date)
        elif video.get('timestamp'):
            try:
                video_date = datetime.fromtimestamp(video['timestamp'])
            except:
                pass
        elif video.get('release_timestamp'):
            try:
                video_date = datetime.fromtimestamp(video['release_timestamp'])
            except:
                pass
        
        if video_date and video_date <= target_date:
            boundary_position = i
            log_message(f"Found date boundary at position {i}: video date {video_date.strftime('%Y-%m-%d')} <= {date_from}")
            break
    
    return boundary_position

def smart_extract_with_date_check(url: str, date_from: str, cookies_path: str = None, 
                                batch_size: int = 50) -> List[Dict[str, Any]]:
    """
    Smart extraction with date filtering using hybrid approach:
    1. Use --flat-playlist to get batches quickly
    2. Check last video date in each batch 
    3. Find exact boundary in final batch
    4. Get full metadata for all videos from start to boundary
    """
    log_message(f"Starting smart extraction with date filter: {date_from}")
    log_message(f"Batch size: {batch_size}")
    
    all_results = []
    batch_start = 1
    final_boundary = None
    
    # Phase 1: Find the batch containing the date boundary
    while True:
        batch_end = batch_start + batch_size - 1
        log_message(f"Checking batch {batch_start}:{batch_end}")
        
        # Get flat playlist for current batch
        try:
            cmd = ["yt-dlp", "--flat-playlist", "--dump-json", url, 
                   "--playlist-items", f"{batch_start}:{batch_end}"]
            
            if cookies_path:
                cmd.extend(["--cookies", cookies_path])
            
            log_message(f"Executing batch command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            if not result.stdout.strip():
                log_message(f"No more videos found, stopping at batch {batch_start}:{batch_end}")
                break
                
            # Parse batch results
            batch_videos = []
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    try:
                        video_data = json.loads(line)
                        batch_videos.append(video_data)
                    except json.JSONDecodeError:
                        continue
            
            if not batch_videos:
                log_message(f"No valid videos in batch {batch_start}:{batch_end}")
                break
            
            log_message(f"Found {len(batch_videos)} videos in batch")
            
            # Check date of last video in batch
            last_video = batch_videos[-1]
            last_video_id = last_video.get('id')
            
            if not last_video_id:
                log_message(f"Warning: No ID for last video in batch, stopping")
                break
            
            last_video_date = get_video_date(last_video_id, cookies_path)
            
            if not last_video_date:
                log_message(f"Warning: Could not get date for last video {last_video_id}, stopping")
                break
            
            # Convert dates to same format for comparison (YYYYMMDD)
            date_from_formatted = date_from.replace('-', '')  # "2025-06-29" -> "20250629"
            
            if last_video_date <= date_from_formatted:
                # Found the batch with boundary!
                log_message(f"Found boundary batch {batch_start}:{batch_end}: last video date {last_video_date} <= {date_from}")
                
                # Phase 2: Find exact boundary within this batch
                log_message(f"Getting full metadata for boundary batch {batch_start}:{batch_end}")
                
                boundary_cmd = ["yt-dlp", "--dump-json", url, 
                               "--playlist-items", f"{batch_start}:{batch_end}"]
                
                if cookies_path:
                    boundary_cmd.extend(["--cookies", cookies_path])
                
                boundary_result = subprocess.run(boundary_cmd, capture_output=True, text=True, check=True)
                
                boundary_videos = []
                for line in boundary_result.stdout.strip().split('\n'):
                    if line.strip():
                        try:
                            video_data = json.loads(line)
                            boundary_videos.append(video_data)
                        except json.JSONDecodeError:
                            continue
                
                # Find exact boundary position within batch
                boundary_offset = find_date_boundary_in_batch(boundary_videos, date_from)
                final_boundary = batch_start + boundary_offset - 1
                
                log_message(f"Exact boundary found at video position: {final_boundary}")
                break
            else:
                log_message(f"Batch {batch_start}:{batch_end} still has new videos (last date: {last_video_date}), continuing")
                batch_start = batch_end + 1
                
        except subprocess.CalledProcessError as e:
            log_message(f"Error processing batch {batch_start}:{batch_end}: {e}")
            break
        except Exception as e:
            log_message(f"Unexpected error in batch {batch_start}:{batch_end}: {e}")
            break
    
    # Phase 3: Get full metadata for all videos from start to boundary
    if final_boundary and final_boundary > 0:
        log_message(f"Extracting full metadata for videos 1:{final_boundary}")
        
        final_cmd = ["yt-dlp", "--dump-json", url, "--playlist-items", f"1:{final_boundary}"]
        
        if cookies_path:
            final_cmd.extend(["--cookies", cookies_path])
        
        log_message(f"Executing final extraction: {' '.join(final_cmd)}")
        
        try:
            final_result = subprocess.run(final_cmd, capture_output=True, text=True, check=True)
            
            for line in final_result.stdout.strip().split('\n'):
                if line.strip():
                    try:
                        video_data = json.loads(line)
                        all_results.append(video_data)
                    except json.JSONDecodeError:
                        continue
                        
            log_message(f"Successfully extracted {len(all_results)} videos")
            
        except subprocess.CalledProcessError as e:
            log_message(f"Error in final extraction: {e}")
            raise RuntimeError(f"Final extraction failed: {e}")
    
    elif final_boundary == 0:
        log_message("No videos newer than date_from found")
    else:
        log_message("Could not determine boundary, extracting first batch as fallback")
        # Fallback: extract first batch
        return run_ytdlp_extract(url, batch_size, cookies_path, f"1:{batch_size}")
    
    return all_results

def run_ytdlp_extract(url: str, max_entries: int = None, cookies_path: str = None, 
                      playlist_items: str = None) -> List[Dict[str, Any]]:
    """
    Run yt-dlp to extract metadata from YouTube channel
    
    Args:
        url: YouTube channel URL
        max_entries: Maximum number of videos to extract (optional)
        cookies_path: Path to cookies file (optional)
        playlist_items: Specific video indices to process (optional)
        
    Returns:
        List of video metadata dictionaries
        
    Raises:
        RuntimeError: If yt-dlp command fails
    """
    # Check if we should use smart extraction
    date_from = get_channel_date_from(url)
    
    if date_from and not playlist_items:
        # Use smart batching with date filtering
        return smart_extract_with_date_check(url, date_from, cookies_path)
    
    # Use original single-command approach
    cmd = [
        "yt-dlp", 
        "--flat-playlist", 
        "--dump-json", 
        url
    ]
    
    # Add cookies if provided
    if cookies_path:
        cmd.extend(["--cookies", cookies_path])
        log_message(f"Using cookies file: {cookies_path}")
    
    # Add max entries limit if specified
    if max_entries:
        cmd.extend(["--max-downloads", str(max_entries)])
    
    # Add playlist items filter if specified
    if playlist_items:
        cmd.extend(["--playlist-items", playlist_items])
        log_message(f"Processing playlist items: {playlist_items}")
    
    log_message(f"Executing yt-dlp command: {' '.join(cmd)}")
    
    try:
        # Run yt-dlp command
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            timeout=600  # 10 minute timeout
        )
        
        if result.returncode != 0:
            error_msg = f"yt-dlp failed with exit code {result.returncode}"
            if result.stderr:
                error_msg += f"\nError output: {result.stderr}"
            raise RuntimeError(error_msg)
        
        # Parse JSON output
        metadata_list = []
        for line in result.stdout.strip().split('\n'):
            if line.strip():
                try:
                    metadata = json.loads(line)
                    metadata_list.append(metadata)
                except json.JSONDecodeError as e:
                    log_message(f"Warning: Failed to parse JSON line: {e}")
                    continue
        
        log_message(f"Successfully extracted {len(metadata_list)} videos")
        return metadata_list
        
    except subprocess.TimeoutExpired:
        raise RuntimeError("yt-dlp command timed out (10 minutes)")
    except Exception as e:
        raise RuntimeError(f"Error running yt-dlp: {e}")


def compare_metadata(existing: Dict[str, Any], new: Dict[str, Any]) -> bool:
    """
    Compare two metadata dictionaries to check if update is needed
    
    Args:
        existing: Existing metadata from database
        new: New metadata from yt-dlp
        
    Returns:
        True if metadata differs and update is needed, False otherwise
    """
    # Fields to compare for changes (skip timestamps and IDs)
    compare_fields = [
        'title', 'description', 'duration', 'view_count', 'availability',
        'live_status', 'channel', 'channel_url', 'playlist_title',
        'playlist_count', 'n_entries', 'playlist_index'
    ]
    
    for field in compare_fields:
        existing_val = existing.get(field)
        new_val = new.get(field)
        
        # Handle None values and type mismatches
        if existing_val != new_val:
            # Special handling for numeric fields that might be None vs 0
            if field in ['view_count', 'duration', 'playlist_count', 'n_entries', 'playlist_index']:
                existing_num = existing_val if existing_val is not None else 0
                new_num = new_val if new_val is not None else 0
                if existing_num != new_num:
                    return True
            else:
                return True
    
    return False


def process_channel_metadata(url: str, force_update: bool = False, max_entries: int = None, 
                             cookies_path: str = None, playlist_items: str = None) -> Dict[str, int]:
    """
    Process YouTube channel metadata extraction and database storage
    
    Args:
        url: YouTube channel URL
        force_update: Force update existing metadata even if unchanged
        max_entries: Maximum number of videos to process
        cookies_path: Path to cookies file (optional)
        dateafter: Download only videos after this date (optional)
        datebefore: Download only videos before this date (optional)
        
    Returns:
        Dictionary with statistics: total, inserted, updated, errors
    """
    start_time = datetime.utcnow()
    log_message(f"=== Channel Metadata Extraction Started ===")
    log_message(f"Target URL: {url}")
    log_message(f"Start time: {start_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    
    # Get date filter for debugging
    date_from = get_channel_date_from(url)
    if date_from:
        log_message(f"Date filter active: only videos newer than {date_from}")
    else:
        log_message(f"No date filter found for channel")
    
    stats = {
        'total': 0,
        'inserted': 0,
        'updated': 0,
        'errors': 0
    }
    
    try:
        # Step 1: Extract metadata using yt-dlp
        metadata_list = run_ytdlp_extract(url, max_entries, cookies_path, playlist_items)
        stats['total'] = len(metadata_list)
        
        if not metadata_list:
            log_message("Warning: No metadata extracted from channel")
            return stats
        
        log_message(f"Processing {stats['total']} video metadata records...")
        
        # Step 2: Process each metadata record
        conn = get_connection()
        
        try:
            for i, metadata in enumerate(metadata_list, 1):
                try:
                    # Extract video ID (could be 'id' or 'video_id' depending on format)
                    video_id = metadata.get('id') or metadata.get('video_id')
                    if not video_id:
                        log_message(f"Warning: Video {i} missing ID, skipping")
                        stats['errors'] += 1
                        continue
                    
                    # === DEBUG: Log video details and date filtering ===
                    video_title = metadata.get('title', 'Unknown Title')[:50]
                    
                    # Safely encode title for logging to avoid charmap errors
                    try:
                        safe_title = video_title.encode('ascii', 'replace').decode('ascii')
                    except:
                        safe_title = 'Non-ASCII Title'
                    
                    # Extract video date for debugging
                    video_date_str = "Unknown"
                    video_timestamp = None
                    
                    # Try to get date from various fields
                    if metadata.get('upload_date'):
                        video_date_str = metadata['upload_date']
                        try:
                            video_timestamp = datetime.strptime(video_date_str, '%Y%m%d').timestamp()
                        except:
                            pass
                    elif metadata.get('timestamp'):
                        video_timestamp = metadata['timestamp']
                        try:
                            video_date_str = datetime.fromtimestamp(video_timestamp).strftime('%Y-%m-%d')
                        except:
                            pass
                    elif metadata.get('release_timestamp'):
                        video_timestamp = metadata['release_timestamp']
                        try:
                            video_date_str = datetime.fromtimestamp(video_timestamp).strftime('%Y-%m-%d')
                        except:
                            pass
                    
                    # Check if video passes date filter
                    passes_date_filter = "YES"
                    if date_from and video_timestamp:
                        try:
                            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
                            video_date_obj = datetime.fromtimestamp(video_timestamp)
                            passes_date_filter = "YES" if video_date_obj >= date_from_obj else "NO"
                        except:
                            passes_date_filter = "UNKNOWN"
                    elif date_from:
                        passes_date_filter = "NO_TIMESTAMP"
                    
                    log_message(f"Video {i}/{stats['total']}: {video_id} '{safe_title}...'")
                    log_message(f"  Publication date: {video_date_str}")
                    log_message(f"  Date filter: {date_from or 'None'}")
                    log_message(f"  Passes filter: {passes_date_filter}")
                    
                    # === END DEBUG ===
                    
                    # Ensure youtube_id field is set correctly
                    metadata['youtube_id'] = video_id
                    
                    # Always set channel_url to the original human-readable URL passed to function
                    # This fixes URL mismatch issue where smart extraction returns technical URLs
                    # but callback searches for human-readable URLs  
                    metadata['channel_url'] = url
                    
                    # Check if record already exists
                    existing = get_youtube_metadata_by_id(conn, video_id)
                    
                    if existing:
                        # Check if update is needed
                        if force_update or compare_metadata(dict(existing), metadata):
                            # Update existing record
                            upsert_youtube_metadata(conn, metadata)
                            stats['updated'] += 1
                            if force_update:
                                log_message(f"Force updated metadata for video {video_id} ({i}/{stats['total']})")
                            else:
                                log_message(f"Updated metadata for video {video_id} ({i}/{stats['total']})")
                        else:
                            # No changes needed
                            log_message(f"No changes for video {video_id} ({i}/{stats['total']})")
                    else:
                        # Insert new record
                        upsert_youtube_metadata(conn, metadata)
                        stats['inserted'] += 1
                        log_message(f"Inserted new metadata for video {video_id} ({i}/{stats['total']})")
                    
                    # Progress reporting every 50 videos
                    if i % 50 == 0 or i == stats['total']:
                        progress = (i / stats['total']) * 100
                        log_message(f"Progress: {i}/{stats['total']} ({progress:.1f}%) - "
                                  f"Inserted: {stats['inserted']}, Updated: {stats['updated']}, "
                                  f"Errors: {stats['errors']}")
                
                except Exception as e:
                    log_message(f"Error processing video {i}: {e}")
                    stats['errors'] += 1
                    continue
        
        finally:
            # Update metadata_last_updated field in channels table
            try:
                cur = conn.cursor()
                current_time = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
                cur.execute("""
                    UPDATE channels 
                    SET metadata_last_updated = ? 
                    WHERE url = ?
                """, (current_time, url))
                
                if cur.rowcount > 0:
                    log_message(f"Updated metadata_last_updated for channel: {current_time}")
                else:
                    log_message(f"Warning: Channel not found in database, metadata_last_updated not set")
                
                conn.commit()
            except Exception as e:
                log_message(f"Warning: Failed to update metadata_last_updated: {e}")
            
            conn.close()
    
    except Exception as e:
        log_message(f"Fatal error during processing: {e}")
        stats['errors'] += 1
        return stats
    
    # Final statistics
    end_time = datetime.utcnow()
    duration = end_time - start_time
    
    log_message("=== Channel Metadata Extraction Completed ===")
    log_message(f"End time: {end_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    log_message(f"Duration: {duration.total_seconds():.1f} seconds")
    log_message(f"Results Summary:")
    log_message(f"  - Total videos processed: {stats['total']}")
    log_message(f"  - New records inserted: {stats['inserted']}")
    log_message(f"  - Existing records updated: {stats['updated']}")
    log_message(f"  - Errors encountered: {stats['errors']}")
    log_message(f"  - Success rate: {((stats['total'] - stats['errors']) / max(stats['total'], 1) * 100):.1f}%")
    
    return stats


def main():
    """Main function with command line argument parsing"""
    parser = argparse.ArgumentParser(
        description="Extract YouTube channel metadata and store in database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python extract_channel_metadata.py "https://www.youtube.com/@SomeChannel/videos"
    python extract_channel_metadata.py "https://www.youtube.com/c/SomeChannel/videos" --max-entries 100
    python extract_channel_metadata.py "https://www.youtube.com/channel/UC.../videos" --playlist-items "1:50"
    python extract_channel_metadata.py "https://www.youtube.com/@SomeChannel/videos" --playlist-items "1,5,10"
        """
    )
    
    parser.add_argument(
        "url",
        help="YouTube channel URL (e.g., https://www.youtube.com/@ChannelName/videos)"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Extract metadata but don't save to database (for testing)"
    )
    
    parser.add_argument(
        "--db-path",
        type=str,
        help="Path to the database file (overrides .env file)"
    )
    
    parser.add_argument(
        "--force-update",
        action="store_true",
        help="Force update existing metadata even if unchanged"
    )
    
    parser.add_argument(
        "--max-entries",
        type=int,
        help="Maximum number of videos to process"
    )
    
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging output"
    )
    
    parser.add_argument(
        "--cookies",
        type=str,
        help="Path to cookies file for YouTube authentication"
    )
    
    parser.add_argument(
        "--playlist-items",
        type=str,
        help="Specific video indices to process (e.g., '1:50' for first 50 videos, '1,3,5' for specific videos)"
    )
    
    args = parser.parse_args()
    
    # Set database path from command line argument or .env file
    db_path = args.db_path
    if not db_path:
        db_path = env_config.get('DB_PATH')
    
    if db_path:
        from pathlib import Path
        db_file = Path(db_path)
        if db_file.exists():
            set_db_path(db_path)
            if args.verbose:
                print(f"[INFO] Using database: {db_path}")
        else:
            print(f"[WARNING] Database file not found: {db_path}")
            print(f"[INFO] Using default database: tracks.db (current directory)")
    else:
        if args.verbose:
            print(f"[INFO] Using default database: tracks.db (current directory)")
    
    # Validate URL format
    if not any(domain in args.url.lower() for domain in ['youtube.com', 'youtu.be']):
        print("Error: URL must be a valid YouTube channel URL")
        sys.exit(1)
    
    try:
        if args.dry_run:
            log_message("DRY RUN MODE: Metadata will be extracted but not saved to database")
            # Run extraction only
            metadata_list = run_ytdlp_extract(args.url, args.max_entries, args.cookies, args.playlist_items)
            log_message(f"DRY RUN: Would process {len(metadata_list)} videos")
            
            # Show sample metadata
            if metadata_list:
                sample = metadata_list[0]
                log_message("Sample metadata fields:")
                for key, value in list(sample.items())[:10]:
                    log_message(f"  {key}: {value}")
        else:
            # Full processing
            stats = process_channel_metadata(args.url, args.force_update, args.max_entries, args.cookies, args.playlist_items)
            
            # Exit with error code if there were issues
            if stats['errors'] > 0 and stats['total'] == stats['errors']:
                sys.exit(1)
    
    except KeyboardInterrupt:
        log_message("Operation cancelled by user")
        sys.exit(130)
    except Exception as e:
        log_message(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main() 
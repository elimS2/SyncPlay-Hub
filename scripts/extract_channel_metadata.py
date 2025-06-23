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
from typing import Dict, List, Any
import os

from utils.logging_utils import log_message
from database import (
    get_connection, 
    upsert_youtube_metadata, 
    get_youtube_metadata_by_id
)


def run_ytdlp_extract(url: str) -> List[Dict[str, Any]]:
    """
    Run yt-dlp to extract metadata from YouTube channel
    
    Args:
        url: YouTube channel URL
        
    Returns:
        List of video metadata dictionaries
        
    Raises:
        RuntimeError: If yt-dlp command fails
    """
    log_message(f"Starting yt-dlp extraction for URL: {url}")
    
    # Build yt-dlp command
    cmd = [
        "yt-dlp", 
        "--flat-playlist", 
        "--dump-json", 
        url
    ]
    
    try:
        # Run yt-dlp and capture output
        log_message("Executing yt-dlp command...")
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            encoding='utf-8',
            timeout=300  # 5 minute timeout
        )
        
        if result.returncode != 0:
            error_msg = f"yt-dlp failed with return code {result.returncode}"
            if result.stderr:
                error_msg += f"\nError output: {result.stderr}"
            raise RuntimeError(error_msg)
        
        # Parse JSON output line by line
        metadata_list = []
        for line in result.stdout.strip().split('\n'):
            if line.strip():
                try:
                    metadata = json.loads(line)
                    metadata_list.append(metadata)
                except json.JSONDecodeError as e:
                    log_message(f"Warning: Failed to parse JSON line: {e}")
                    continue
        
        log_message(f"Successfully extracted {len(metadata_list)} video metadata records")
        return metadata_list
        
    except subprocess.TimeoutExpired:
        raise RuntimeError("yt-dlp command timed out after 5 minutes")
    except Exception as e:
        raise RuntimeError(f"Failed to run yt-dlp: {e}")


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


def process_channel_metadata(url: str) -> Dict[str, int]:
    """
    Process YouTube channel metadata extraction and database storage
    
    Args:
        url: YouTube channel URL
        
    Returns:
        Dictionary with statistics: total, inserted, updated, errors
    """
    start_time = datetime.utcnow()
    log_message(f"=== Channel Metadata Extraction Started ===")
    log_message(f"Target URL: {url}")
    log_message(f"Start time: {start_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    
    stats = {
        'total': 0,
        'inserted': 0,
        'updated': 0,
        'errors': 0
    }
    
    try:
        # Step 1: Extract metadata using yt-dlp
        metadata_list = run_ytdlp_extract(url)
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
                    
                    # Ensure youtube_id field is set correctly
                    metadata['youtube_id'] = video_id
                    
                    # Check if record already exists
                    existing = get_youtube_metadata_by_id(conn, video_id)
                    
                    if existing:
                        # Check if update is needed
                        if compare_metadata(dict(existing), metadata):
                            # Update existing record
                            upsert_youtube_metadata(conn, metadata)
                            stats['updated'] += 1
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
    python extract_channel_metadata.py "https://www.youtube.com/c/SomeChannel/videos" 
    python extract_channel_metadata.py "https://www.youtube.com/channel/UC.../videos"
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
    
    args = parser.parse_args()
    
    # Validate URL format
    if not any(domain in args.url.lower() for domain in ['youtube.com', 'youtu.be']):
        print("Error: URL must be a valid YouTube channel URL")
        sys.exit(1)
    
    try:
        if args.dry_run:
            log_message("DRY RUN MODE: Metadata will be extracted but not saved to database")
            # Run extraction only
            metadata_list = run_ytdlp_extract(args.url)
            log_message(f"DRY RUN: Would process {len(metadata_list)} videos")
            
            # Show sample metadata
            if metadata_list:
                sample = metadata_list[0]
                log_message("Sample metadata fields:")
                for key, value in list(sample.items())[:10]:
                    log_message(f"  {key}: {value}")
        else:
            # Full processing
            stats = process_channel_metadata(args.url)
            
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
#!/usr/bin/env python3
"""
Script for cleaning up metadata files in YouTube channel folders

Removes files created by yt-dlp that are not needed for playback:
- .json (video metadata)
- .info.json (detailed information)
- .description (video descriptions) 
- .thumbnail (thumbnails)
- .webp (images)
- .part (incomplete downloads)
- .temp (temporary files)

Usage:
    python scripts/cleanup_channel_metadata.py --channel "Channel-kalush.official"
    python scripts/cleanup_channel_metadata.py --all-channels
    python scripts/cleanup_channel_metadata.py --dry-run --all-channels
"""

import argparse
import sys
from pathlib import Path
from typing import List, Tuple

# Add root folder to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from utils.logging_utils import log_message


def load_config() -> dict:
    """Load configuration from .env file."""
    config = {}
    env_path = Path(__file__).parent.parent / '.env'
    
    if env_path.exists():
        try:
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip().lstrip('\ufeff')  # Remove BOM
                    if line and '=' in line and not line.startswith('#'):
                        key, value = line.split('=', 1)
                        config[key.strip()] = value.strip()
        except Exception as e:
            print(f"Warning: Failed to load .env file: {e}")
    
    return config


def get_metadata_patterns() -> List[str]:
    """Return list of patterns for metadata files that should be removed."""
    return [
        '*.info.json',      # Detailed video information (yt-dlp metadata)
        '*.description',    # Video descriptions
        '*.thumbnail',      # Video thumbnails
        '*.webp',          # WebP images (thumbnails)
        '*.jpg',           # JPEG images (thumbnails) 
        '*.png',           # PNG images (thumbnails)
        '*.part',          # Incomplete download files
        '*.temp',          # Temporary files
        '*.tmp',           # Temporary files
        '*.ytdl',          # yt-dlp files
        '*.download',      # Files being downloaded
    ]


def get_channel_folders(base_dir: Path, channel_name: str = None) -> List[Path]:
    """
    Get list of channel folders for cleanup.
    
    Args:
        base_dir: Base directory with playlists
        channel_name: Specific channel name (without Channel- prefix) or None for all
        
    Returns:
        List of paths to channel folders
    """
    channel_folders = []
    
    if not base_dir.exists():
        print(f"[Error] Base directory does not exist: {base_dir}")
        return channel_folders
    
    # If specific channel is specified
    if channel_name:
        # If channel doesn't start with "Channel-", add prefix
        if not channel_name.startswith("Channel-"):
            channel_name = f"Channel-{channel_name}"
            
        # Search for channel folder in various groups
        for group_folder in base_dir.iterdir():
            if group_folder.is_dir():
                channel_folder = group_folder / channel_name
                if channel_folder.exists() and channel_folder.is_dir():
                    channel_folders.append(channel_folder)
                    
        # Also check root folder
        channel_folder = base_dir / channel_name
        if channel_folder.exists() and channel_folder.is_dir():
            channel_folders.append(channel_folder)
    else:
        # Search for all channel folders
        for item in base_dir.rglob("Channel-*"):
            if item.is_dir():
                channel_folders.append(item)
    
    return channel_folders


def cleanup_metadata_files(channel_folder: Path, dry_run: bool = False) -> Tuple[int, int]:
    """
    Clean up metadata files in channel folder.
    
    Args:
        channel_folder: Path to channel folder
        dry_run: If True, only show what would be removed
        
    Returns:
        Tuple[removed_files, size_in_bytes]
    """
    removed_count = 0
    total_size = 0
    patterns = get_metadata_patterns()
    processed_files = set()  # Track processed files to avoid duplicates
    
    print(f"\n[Cleanup] Processing: {channel_folder}")
    
    for pattern in patterns:
        for file_path in channel_folder.glob(pattern):
            if file_path.is_file() and file_path not in processed_files:
                processed_files.add(file_path)
                file_size = file_path.stat().st_size
                
                if dry_run:
                    print(f"  [Dry Run] Would remove: {file_path.name} ({file_size:,} bytes)")
                else:
                    try:
                        file_path.unlink()
                        print(f"  [Removed] {file_path.name} ({file_size:,} bytes)")
                    except Exception as e:
                        print(f"  [Error] Failed to remove {file_path.name}: {e}")
                        continue
                
                removed_count += 1
                total_size += file_size
    
    return removed_count, total_size


def main():
    parser = argparse.ArgumentParser(description='Clean up metadata files from YouTube channel folders')
    parser.add_argument('--channel', '-c', 
                       help='Specific channel name to clean (e.g., "kalush.official" or "Channel-kalush.official")')
    parser.add_argument('--all-channels', '-a', action='store_true',
                       help='Clean all channel folders')
    parser.add_argument('--dry-run', '-d', action='store_true',
                       help='Show what would be removed without actually deleting')
    parser.add_argument('--base-dir', '-b',
                       help='Base directory containing playlists (overrides config)')
    
    args = parser.parse_args()
    
    # Check arguments
    if not args.channel and not args.all_channels:
        print("[Error] Please specify either --channel <name> or --all-channels")
        return 1
    
    if args.channel and args.all_channels:
        print("[Error] Please specify either --channel or --all-channels, not both")
        return 1
    
    # Load configuration
    config = load_config()
    
    # Determine base directory
    if args.base_dir:
        base_dir = Path(args.base_dir)
    else:
        root_dir = config.get('ROOT_DIR', 'D:/music/Youtube')
        base_dir = Path(config.get('PLAYLISTS_DIR', f'{root_dir}/Playlists'))
    
    print(f"[Config] Base directory: {base_dir}")
    
    if args.dry_run:
        print("[Mode] DRY RUN - no files will actually be deleted")
    
    # Get list of channel folders
    channel_folders = get_channel_folders(base_dir, args.channel)
    
    if not channel_folders:
        if args.channel:
            print(f"[Error] Channel folder not found: {args.channel}")
        else:
            print("[Error] No channel folders found")
        return 1
    
    print(f"[Found] {len(channel_folders)} channel folder(s) to process")
    
    # Clean each channel folder
    total_removed = 0
    total_size = 0
    
    for channel_folder in channel_folders:
        try:
            removed, size = cleanup_metadata_files(channel_folder, args.dry_run)
            total_removed += removed
            total_size += size
            
            if removed > 0:
                size_mb = size / (1024 * 1024)
                print(f"  [Summary] {removed} files, {size_mb:.1f} MB")
            else:
                print(f"  [Summary] No metadata files found")
                
        except Exception as e:
            print(f"[Error] Failed to process {channel_folder}: {e}")
    
    # Final report
    print(f"\n[Final Summary]")
    print(f"Processed channels: {len(channel_folders)}")
    print(f"Total files {'that would be' if args.dry_run else ''} removed: {total_removed}")
    if total_size > 0:
        size_mb = total_size / (1024 * 1024)
        print(f"Total size {'that would be' if args.dry_run else ''} freed: {size_mb:.1f} MB")
    
    if args.dry_run and total_removed > 0:
        print(f"\n[Hint] Run without --dry-run to actually delete these files")
    
    return 0


if __name__ == "__main__":
    sys.exit(main()) 
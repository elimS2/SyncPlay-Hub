#!/usr/bin/env python3
"""
Restore Missing Tracks Script - Automatically restore tracks missing from disk

Directory Structure: PLAYLISTS_DIR/YouTube_Channel_ID/video_file
This ensures stability against channel and folder renaming.
"""

import sqlite3
import sys
import argparse
import subprocess
import json
from pathlib import Path
from typing import List, Dict, Optional
import re

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from database import get_connection, set_db_path
from utils.logging_utils import log_message

# Job Queue imports for automatic download
try:
    from services.job_queue_service import get_job_queue_service
    from services.job_types import JobType, JobPriority
    JOB_QUEUE_AVAILABLE = True
except ImportError:
    JOB_QUEUE_AVAILABLE = False
    print("[WARNING] Job Queue system not available. Cannot create download jobs.")

def load_env_config() -> Dict[str, str]:
    """Load configuration from .env file."""
    config = {}
    
    current_dir = Path(__file__).parent.parent
    env_path = current_dir / '.env'
    
    if env_path.exists():
        try:
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip().lstrip('\ufeff')
                    if line and '=' in line and not line.startswith('#'):
                        key, value = line.split('=', 1)
                        config[key.strip()] = value.strip()
        except Exception as e:
            print(f"Warning: Failed to load .env file: {e}")
    
    return config

def find_missing_tracks(db_path: str, playlists_dir: str) -> List[Dict]:
    """Find tracks that exist in database but have missing files on disk."""
    missing_tracks = []
    
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        
        # Find tracks that are not marked as deleted
        query = """
        SELECT t.id, t.video_id, t.name, t.relpath, t.play_likes, t.play_starts
        FROM tracks t
        WHERE t.video_id NOT IN (
            SELECT dt.video_id FROM deleted_tracks dt
        )
        ORDER BY t.play_likes DESC, t.play_starts DESC
        """
        
        cur.execute(query)
        tracks = cur.fetchall()
        
        for track in tracks:
            track_id, video_id, name, relpath, play_likes, play_starts = track
            
            # Check if file exists on disk
            file_path = Path(playlists_dir) / relpath
            if not file_path.exists():
                missing_tracks.append({
                    'track_id': track_id,
                    'video_id': video_id,
                    'name': name,
                    'relpath': relpath,
                    'play_likes': play_likes or 0,
                    'play_starts': play_starts or 0
                })
        
        conn.close()
        
    except Exception as e:
        print(f"[ERROR] Database error: {e}")
        return []
    
    return missing_tracks

def get_video_metadata_from_db(video_id: str) -> Optional[Dict]:
    """Get video metadata from database."""
    try:
        import sqlite3
        from pathlib import Path
        
        # Load config to get DB path
        env_config = load_env_config()
        db_path = env_config.get('DB_PATH')
        if not db_path:
            print(f"[DEBUG] No DB_PATH in config for {video_id}")
            return None
        
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        print(f"[DEBUG] Checking metadata for {video_id} in database...")
        
        cur.execute("""
            SELECT channel_id, channel, title, duration, uploader, uploader_id
            FROM youtube_video_metadata 
            WHERE youtube_id = ?
        """, (video_id,))
        
        row = cur.fetchone()
        
        if row:
            # Try to get channel_id, fallback to uploader_id
            channel_id = row['channel_id']
            if not channel_id and row['uploader_id']:
                # Convert @HalseyVEVO to HalseyVEVO, or use as-is
                channel_id = row['uploader_id'].lstrip('@') if row['uploader_id'].startswith('@') else row['uploader_id']
            
            print(f"[DEBUG] Found metadata for {video_id}: channel_id={row['channel_id']}, uploader_id={row['uploader_id']}")
            
            if channel_id:
                result = {
                    'channel_id': channel_id,
                    'channel': row['channel'] or row['uploader'],
                    'title': row['title'],
                    'duration': row['duration']
                }
                conn.close()
                return result
            else:
                print(f"[DEBUG] No usable channel_id or uploader_id for {video_id}")
                conn.close()
                return None
        else:
            print(f"[DEBUG] No metadata found for {video_id} in youtube_video_metadata table")
            
            # Check if there are any metadata records at all
            cur.execute("SELECT COUNT(*) as total FROM youtube_video_metadata")
            total_count = cur.fetchone()['total']
            print(f"[DEBUG] Total metadata records in database: {total_count}")
            
            # Check recent metadata records
            cur.execute("""
                SELECT youtube_id, channel_id, title, created_at 
                FROM youtube_video_metadata 
                ORDER BY created_at DESC 
                LIMIT 5
            """)
            recent = cur.fetchall()
            if recent:
                print(f"[DEBUG] Recent metadata records:")
                for r in recent:
                    print(f"[DEBUG]   {r['youtube_id']} - {r['title'][:50]}... - {r['created_at']}")
            else:
                print(f"[DEBUG] No metadata records found in database")
        
        conn.close()
        return None
        
    except Exception as e:
        print(f"[WARNING] Failed to get metadata from DB for {video_id}: {e}")
        import traceback
        print(f"[DEBUG] Traceback: {traceback.format_exc()}")
        return None

def check_existing_metadata_jobs(video_id: str) -> Optional[Dict]:
    """Check if there are existing metadata extraction jobs for this video."""
    if not JOB_QUEUE_AVAILABLE:
        return None
    
    try:
        import sqlite3
        
        # Load config to get DB path
        env_config = load_env_config()
        db_path = env_config.get('DB_PATH')
        if not db_path:
            return None
        
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        # Check for existing metadata extraction jobs for this video
        cur.execute("""
            SELECT id, status, created_at, completed_at, job_data
            FROM job_queue 
            WHERE job_type = 'single_video_metadata_extraction' 
            AND json_extract(job_data, '$.video_id') = ?
            ORDER BY created_at DESC
            LIMIT 5
        """, (video_id,))
        
        jobs = cur.fetchall()
        conn.close()
        
        if jobs:
            latest_job = jobs[0]
            return {
                'job_id': latest_job['id'],
                'status': latest_job['status'], 
                'created_at': latest_job['created_at'],
                'completed_at': latest_job['completed_at'],
                'total_jobs': len(jobs)
            }
        
        return None
        
    except Exception as e:
        print(f"[DEBUG] Failed to check existing jobs for {video_id}: {e}")
        return None

def create_metadata_extraction_job(video_id: str) -> Optional[int]:
    """Create a metadata extraction job for a video."""
    if not JOB_QUEUE_AVAILABLE:
        print("[ERROR] Job queue system not available")
        return None
    
    try:
        from services.job_types import JobType, JobPriority
        
        # Get job service
        job_service = get_job_queue_service()
        
        # Create metadata extraction job
        job_id = job_service.create_and_add_job(
            JobType.SINGLE_VIDEO_METADATA_EXTRACTION,
            priority=JobPriority.NORMAL,
            video_id=video_id,
            force_update=False
        )
        
        return job_id
        
    except Exception as e:
        print(f"[ERROR] Failed to create metadata extraction job for {video_id}: {e}")
        return None

def create_download_job(video_id: str, channel_id: str, playlists_dir: str) -> Optional[int]:
    """Create a single video download job using the job queue system."""
    if not JOB_QUEUE_AVAILABLE:
        print("[ERROR] Job queue system not available")
        return None
    
    try:
        # Get job service
        job_service = get_job_queue_service()
        
        # Create target folder path based on channel ID
        target_folder = channel_id  # This will create PLAYLISTS_DIR/channel_id/
        
        # Video URL
        video_url = f'https://www.youtube.com/watch?v={video_id}'
        
        # Create single video download job
        job_id = job_service.create_and_add_job(
            JobType.SINGLE_VIDEO_DOWNLOAD,
            priority=JobPriority.NORMAL,
            playlist_url=video_url,
            target_folder=target_folder,
            format_selector='bestvideo+bestaudio/best',
            extract_audio=False,
            download_archive=True,
            ignore_archive=True,  # Force download even if in archive
            force_overwrites=True  # Overwrite existing files
        )
        
        return job_id
        
    except Exception as e:
        print(f"[ERROR] Failed to create download job for {video_id}: {e}")
        return None

def update_track_path(db_path: str, track_id: int, new_relpath: str):
    """Update track path in database after successful download."""
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        
        cur.execute(
            "UPDATE tracks SET relpath = ? WHERE id = ?",
            (new_relpath, track_id)
        )
        
        conn.commit()
        conn.close()
        
        print(f"[UPDATE] Updated path for track_id {track_id}: {new_relpath}")
        
    except Exception as e:
        print(f"[ERROR] Database update error: {e}")

def find_downloaded_file(playlists_dir: str, channel_id: str, video_id: str) -> Optional[str]:
    """Find the downloaded file for a video in the channel directory."""
    try:
        channel_dir = Path(playlists_dir) / channel_id
        
        if not channel_dir.exists():
            return None
        
        # Look for files with the video ID in the filename
        for file in channel_dir.glob(f'*[{video_id}].*'):
            if file.is_file() and file.suffix.lower() in {'.mp4', '.mkv', '.webm', '.mp3', '.m4a', '.opus'}:
                # Return path relative to playlists_dir
                return str(file.relative_to(playlists_dir))
        
        return None
        
    except Exception as e:
        print(f"[ERROR] Failed to find downloaded file for {video_id}: {e}")
        return None

def restore_missing_tracks(db_path: str, playlists_dir: str, 
                          max_tracks: int = None, priority_liked: bool = True,
                          dry_run: bool = False):
    """Restore missing tracks by creating appropriate jobs."""
    
    print(f"[INFO] Searching for missing tracks...")
    missing_tracks = find_missing_tracks(db_path, playlists_dir)
    
    if not missing_tracks:
        print("✅ All tracks found on disk!")
        return
    
    print(f"[INFO] Found {len(missing_tracks)} missing tracks")
    
    # Priority for liked tracks
    if priority_liked:
        missing_tracks.sort(key=lambda x: (x['play_likes'], x['play_starts']), reverse=True)
    
    # Limit number if specified
    if max_tracks:
        missing_tracks = missing_tracks[:max_tracks]
        print(f"[INFO] Limiting to {max_tracks} tracks")
    
    if dry_run:
        print(f"[DRY RUN] Would process {len(missing_tracks)} tracks:")
        print(f"[DRY RUN] Checking metadata availability...")
        
        for i, track in enumerate(missing_tracks[:10]):  # Show first 10
            print(f"\n  {i+1}. {track['name']}")
            print(f"     Video ID: {track['video_id']}")
            print(f"     Current path: {track['relpath']} ❌")
            print(f"     Likes: {track['play_likes']}, Plays: {track['play_starts']}")
            
            # Check metadata in database
            metadata = get_video_metadata_from_db(track['video_id'])
            if metadata and metadata.get('channel_id'):
                channel_id = metadata['channel_id']
                title = metadata.get('title', 'Unknown Title')
                
                # Create safe filename
                safe_title = title.replace('/', '_').replace('\\', '_').replace(':', '_').replace('*', '_').replace('?', '_').replace('"', '_').replace('<', '_').replace('>', '_').replace('|', '_')
                expected_filename = f"{safe_title} [{track['video_id']}].mp4"
                expected_path = f"{channel_id}/{expected_filename}"
                full_path = f"{playlists_dir}/{expected_path}"
                
                print(f"     ✅ Metadata available")
                print(f"     Channel ID: {channel_id}")
                print(f"     New path: {expected_path}")
                print(f"     Full path: {full_path}")
                print(f"     → Would create DOWNLOAD job")
            else:
                print(f"     ❌ No usable metadata in database (missing channel_id)")
                print(f"     → Would create METADATA EXTRACTION job first")
                print(f"     → Then create DOWNLOAD job after metadata is ready")
        
        if len(missing_tracks) > 10:
            print(f"\n  ... and {len(missing_tracks) - 10} more tracks")
            
        print(f"\n[DRY RUN] Final structure: {playlists_dir}/CHANNEL_ID/Song Title [video_id].ext")
        print(f"[DRY RUN] Process: Metadata Extraction → Download → Database Update")
        return
    
    metadata_jobs_created = 0
    download_jobs_created = 0
    jobs_failed = 0
    
    for i, track in enumerate(missing_tracks):
        print(f"\n[{i+1}/{len(missing_tracks)}] {track['name']}")
        print(f"  Video ID: {track['video_id']}")
        print(f"  Likes: {track['play_likes']}, Plays: {track['play_starts']}")
        
        # Check if we have metadata in database
        metadata = get_video_metadata_from_db(track['video_id'])
        
        if metadata and metadata.get('channel_id'):
            # We have usable metadata with channel_id
            channel_id = metadata['channel_id']
            title = metadata.get('title', track['name'])
            
            # Show expected file path
            safe_title = title.replace('/', '_').replace('\\', '_').replace(':', '_').replace('*', '_').replace('?', '_').replace('"', '_').replace('<', '_').replace('>', '_').replace('|', '_')
            expected_filename = f"{safe_title} [{track['video_id']}].mp4"
            expected_path = f"{channel_id}/{expected_filename}"
            full_path = f"{playlists_dir}/{expected_path}"
            
            print(f"  ✅ Metadata available, Channel ID: {channel_id}")
            print(f"  📁 Expected path: {expected_path}")
            print(f"  📍 Full path: {full_path}")
            
            job_id = create_download_job(track['video_id'], channel_id, playlists_dir)
            if job_id:
                download_jobs_created += 1
                print(f"  ✅ Created download job #{job_id}")
                log_message(f"[Missing Track Restore] Created download job {job_id} for {track['name']} (ID: {track['video_id']})")
            else:
                jobs_failed += 1
                print(f"  ❌ Failed to create download job")
        else:
            # No usable metadata (missing channel_id), check for existing metadata extraction jobs
            print(f"  ⚠️ No usable metadata in database (missing channel_id)")
            
            existing_job = check_existing_metadata_jobs(track['video_id'])
            if existing_job:
                print(f"  ℹ️ Found existing metadata job #{existing_job['job_id']} (status: {existing_job['status']})")
                print(f"  ℹ️ Created: {existing_job['created_at']}, Completed: {existing_job['completed_at']}")
                
                if existing_job['status'] in ['completed', 'failed']:
                    print(f"  ⚠️ Job {existing_job['status']}, but metadata not in database - job may have failed")
                    print(f"  ➡️ Creating new metadata extraction job")
                    
                    job_id = create_metadata_extraction_job(track['video_id'])
                    if job_id:
                        metadata_jobs_created += 1
                        print(f"  ✅ Created new metadata extraction job #{job_id}")
                        log_message(f"[Missing Track Restore] Created retry metadata job {job_id} for {track['name']} (ID: {track['video_id']})")
                    else:
                        jobs_failed += 1
                        print(f"  ❌ Failed to create metadata extraction job")
                elif existing_job['status'] in ['pending', 'in_progress']:
                    print(f"  ⏳ Metadata extraction job is {existing_job['status']}, skipping creation")
                    print(f"  ℹ️ Wait for job completion, then run script again")
                else:
                    print(f"  ❓ Unknown job status: {existing_job['status']}")
                    jobs_failed += 1
            else:
                print(f"  ➡️ Creating metadata extraction job")
                
                job_id = create_metadata_extraction_job(track['video_id'])
                if job_id:
                    metadata_jobs_created += 1
                    print(f"  ✅ Created metadata extraction job #{job_id}")
                    print(f"  ℹ️ Download job will need to be created after metadata is extracted")
                    log_message(f"[Missing Track Restore] Created metadata job {job_id} for {track['name']} (ID: {track['video_id']})")
                else:
                    jobs_failed += 1
                    print(f"  ❌ Failed to create metadata extraction job")
    
    print(f"\n{'='*60}")
    print(f"[RESTORATION SUMMARY]")
    print(f"{'='*60}")
    print(f"📊 Metadata extraction jobs: {metadata_jobs_created}")
    print(f"⬇️ Download jobs created: {download_jobs_created}")
    print(f"❌ Failed: {jobs_failed}")
    print(f"📁 Final structure: PLAYLISTS_DIR/YouTube_Channel_ID/video_file")
    print(f"🔄 Jobs will be processed by the job queue system")
    
    if metadata_jobs_created > 0:
        print(f"\n[INFO] {metadata_jobs_created} tracks need metadata extraction first")
        print(f"[INFO] You'll need to run this script again after metadata jobs complete")
        print(f"[INFO] Or manually create download jobs from the web interface")
    
    if download_jobs_created > 0:
        print(f"\n[INFO] {download_jobs_created} tracks ready for download")
        print(f"[INFO] Track paths will be updated automatically after downloads complete")
        print(f"[INFO] Monitor job progress in the web interface or logs")

def main():
    parser = argparse.ArgumentParser(description="Restore missing tracks using job queue system")
    parser.add_argument("--db-path", help="Path to database file")
    parser.add_argument("--playlists-dir", help="Playlists directory path")
    parser.add_argument("--max-tracks", type=int, help="Maximum number of tracks to restore")
    parser.add_argument("--no-priority", action="store_true", help="Don't prioritize liked tracks")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be restored without creating jobs")
    
    args = parser.parse_args()
    
    # Load configuration
    env_config = load_env_config()
    
    # Determine paths
    db_path = args.db_path or env_config.get('DB_PATH')
    if not db_path or not Path(db_path).exists():
        print("[ERROR] Database not found")
        sys.exit(1)
    
    playlists_dir = args.playlists_dir or env_config.get('PLAYLISTS_DIR')
    if not playlists_dir:
        root_dir = env_config.get('ROOT_DIR')
        if root_dir:
            playlists_dir = str(Path(root_dir) / 'Playlists')
    
    if not playlists_dir:
        print("[ERROR] Could not determine playlists directory")
        sys.exit(1)
    
    print(f"[INFO] Database: {db_path}")
    print(f"[INFO] Playlists directory: {playlists_dir}")
    
    if not JOB_QUEUE_AVAILABLE and not args.dry_run:
        print("[ERROR] Job queue system not available")
        sys.exit(1)
    
    # Check yt-dlp availability
    try:
        subprocess.run(['yt-dlp', '--version'], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("[ERROR] yt-dlp not found. Install with: pip install yt-dlp")
        sys.exit(1)
    
    # Restore tracks
    restore_missing_tracks(
        db_path=db_path,
        playlists_dir=playlists_dir,
        max_tracks=args.max_tracks,
        priority_liked=not args.no_priority,
        dry_run=args.dry_run
    )

if __name__ == "__main__":
    main() 
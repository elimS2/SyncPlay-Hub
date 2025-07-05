#!/usr/bin/env python3
"""
Metadata Scanner

Scans for tracks missing YouTube metadata and creates extraction jobs.
Part of Extended Metadata Extraction System (Phase 4).

Usage:
    python scripts/scan_missing_metadata.py
    python scripts/scan_missing_metadata.py --limit 100
    python scripts/scan_missing_metadata.py --dry-run
    python scripts/scan_missing_metadata.py --force-update
"""

import argparse
import sys
from pathlib import Path
from typing import List, Dict, Optional

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from database import get_connection, set_db_path
from services.job_queue_service import get_job_queue_service
from services.job_types import JobType, JobPriority
from utils.logging_utils import log_message


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


def find_tracks_missing_metadata(conn, limit: Optional[int] = None, force_update: bool = False) -> List[Dict]:
    """Find tracks that are missing YouTube metadata."""
    try:
        cur = conn.cursor()
        
        if force_update:
            # Force update mode: get all non-deleted tracks
            query = """
            SELECT t.id, t.video_id, t.name, t.published_date
            FROM tracks t
            WHERE t.video_id NOT IN (
                SELECT dt.video_id FROM deleted_tracks dt
            )
            ORDER BY t.id ASC
            """
            params = []
        else:
            # Normal mode: find tracks without metadata or with incomplete metadata
            query = """
            SELECT t.id, t.video_id, t.name, t.published_date
            FROM tracks t
            LEFT JOIN youtube_video_metadata yvm ON t.video_id = yvm.video_id
            WHERE t.video_id NOT IN (
                SELECT dt.video_id FROM deleted_tracks dt
            )
            AND (
                yvm.video_id IS NULL 
                OR (yvm.timestamp IS NULL AND yvm.release_timestamp IS NULL)
            )
            ORDER BY t.id ASC
            """
            params = []
        
        # Add limit if specified
        if limit:
            query += " LIMIT ?"
            params.append(limit)
        
        cur.execute(query, params)
        results = cur.fetchall()
        
        # Convert to list of dictionaries
        tracks = []
        for row in results:
            track = {
                'id': row[0],
                'video_id': row[1],
                'name': row[2],
                'published_date': row[3]
            }
            tracks.append(track)
        
        return tracks
        
    except Exception as e:
        print(f"[ERROR] Failed to find tracks missing metadata: {e}")
        return []


def get_metadata_statistics(conn) -> Dict:
    """Get statistics about metadata coverage."""
    try:
        cur = conn.cursor()
        
        # Total non-deleted tracks
        cur.execute("""
            SELECT COUNT(*) FROM tracks t
            WHERE t.video_id NOT IN (
                SELECT dt.video_id FROM deleted_tracks dt
            )
        """)
        total_tracks = cur.fetchone()[0]
        
        # Tracks with metadata
        cur.execute("""
            SELECT COUNT(*) FROM tracks t
            JOIN youtube_video_metadata yvm ON t.video_id = yvm.video_id
            WHERE t.video_id NOT IN (
                SELECT dt.video_id FROM deleted_tracks dt
            )
            AND (yvm.timestamp IS NOT NULL OR yvm.release_timestamp IS NOT NULL)
        """)
        tracks_with_metadata = cur.fetchone()[0]
        
        # Tracks without metadata
        tracks_without_metadata = total_tracks - tracks_with_metadata
        
        # Coverage percentage
        coverage_percent = (tracks_with_metadata / total_tracks * 100) if total_tracks > 0 else 0
        
        return {
            'total_tracks': total_tracks,
            'tracks_with_metadata': tracks_with_metadata,
            'tracks_without_metadata': tracks_without_metadata,
            'coverage_percent': coverage_percent
        }
        
    except Exception as e:
        print(f"[ERROR] Failed to get metadata statistics: {e}")
        return {
            'total_tracks': 0,
            'tracks_with_metadata': 0,
            'tracks_without_metadata': 0,
            'coverage_percent': 0
        }


def create_metadata_extraction_jobs(tracks: List[Dict], force_update: bool = False, 
                                   dry_run: bool = False) -> int:
    """Create metadata extraction jobs for the given tracks."""
    if not tracks:
        print("[INFO] No tracks to process")
        return 0
    
    if dry_run:
        print(f"[DRY RUN] Would create {len(tracks)} metadata extraction jobs")
        return 0
    
    try:
        # Get job queue service
        job_service = get_job_queue_service(max_workers=1)
        
        jobs_created = 0
        jobs_failed = 0
        
        print(f"[INFO] Creating {len(tracks)} metadata extraction jobs...")
        
        for track in tracks:
            try:
                # Create job for this track
                job_id = job_service.create_and_add_job(
                    JobType.SINGLE_VIDEO_METADATA_EXTRACTION,
                    priority=JobPriority.LOW,  # Priority 10 (low priority)
                    video_id=track['video_id'],
                    force_update=force_update
                )
                
                jobs_created += 1
                
                # Log progress every 10 jobs
                if jobs_created % 10 == 0:
                    print(f"[PROGRESS] Created {jobs_created}/{len(tracks)} jobs...")
                
            except Exception as e:
                jobs_failed += 1
                print(f"[ERROR] Failed to create job for track {track['video_id']}: {e}")
        
        print(f"[SUCCESS] Created {jobs_created} metadata extraction jobs")
        if jobs_failed > 0:
            print(f"[WARNING] Failed to create {jobs_failed} jobs")
        
        # Log the scanning operation
        log_message(f"[Metadata Scanner] Created {jobs_created} extraction jobs for tracks missing metadata")
        
        return jobs_created
        
    except Exception as e:
        print(f"[ERROR] Failed to create metadata extraction jobs: {e}")
        return 0


def print_scan_results(tracks: List[Dict], stats: Dict, limit: Optional[int] = None):
    """Print scan results summary."""
    print(f"\n{'='*80}")
    print(f"[METADATA SCAN RESULTS]")
    print(f"{'='*80}")
    
    # Overall statistics
    print(f"Total tracks in database: {stats['total_tracks']:,}")
    print(f"Tracks with metadata: {stats['tracks_with_metadata']:,}")
    print(f"Tracks without metadata: {stats['tracks_without_metadata']:,}")
    print(f"Metadata coverage: {stats['coverage_percent']:.1f}%")
    
    # Scan results
    print(f"\nFound {len(tracks)} tracks missing metadata")
    if limit and len(tracks) >= limit:
        print(f"(Limited to first {limit} tracks)")
    
    # Show examples
    if tracks:
        print(f"\nFirst 5 tracks missing metadata:")
        for i, track in enumerate(tracks[:5]):
            name = track['name'][:50] + "..." if len(track['name']) > 50 else track['name']
            published = track['published_date'] or 'Unknown'
            print(f"  {i+1}. {track['video_id']} - {name} (Published: {published})")
        
        if len(tracks) > 5:
            print(f"  ... and {len(tracks) - 5} more tracks")


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Scan for tracks missing YouTube metadata and create extraction jobs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python scripts/scan_missing_metadata.py                           # Scan all tracks, create jobs
    python scripts/scan_missing_metadata.py --limit 100              # Limit to first 100 tracks
    python scripts/scan_missing_metadata.py --dry-run                # Show what would be done
    python scripts/scan_missing_metadata.py --force-update           # Force update existing metadata
    python scripts/scan_missing_metadata.py --limit 50 --dry-run     # Dry run with limit
    
Job Queue Integration:
    Created jobs will be processed by the job queue system with configurable delays.
    Check job progress at: /jobs page in the web interface.
    
Settings:
    Configure job execution delays at: /settings page in the web interface.
    Recommended delay: 6 seconds = ~10 videos per minute (respects YouTube limits).
        """
    )
    
    parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of tracks to scan (default: no limit)"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without creating jobs"
    )
    
    parser.add_argument(
        "--force-update",
        action="store_true",
        help="Force update existing metadata (create jobs for all tracks)"
    )
    
    parser.add_argument(
        "--db-path",
        type=str,
        help="Path to the database file (overrides .env file)"
    )
    
    args = parser.parse_args()
    
    # Load environment configuration
    env_config = load_env_file()
    
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
            print(f"[ERROR] Database file not found: {db_path}")
            sys.exit(1)
    else:
        print(f"[INFO] Using default database: tracks.db (current directory)")
        print(f"[HINT] Set DB_PATH in .env file or use --db-path to specify database location")
    
    try:
        # Connect to database
        conn = get_connection()
        
        # Get overall statistics
        stats = get_metadata_statistics(conn)
        
        # Find tracks missing metadata
        print(f"[INFO] Scanning for tracks missing metadata...")
        if args.force_update:
            print(f"[INFO] Force update mode: will create jobs for all tracks")
        if args.limit:
            print(f"[INFO] Limiting scan to first {args.limit} tracks")
        
        tracks = find_tracks_missing_metadata(conn, args.limit, args.force_update)
        
        # Print scan results
        print_scan_results(tracks, stats, args.limit)
        
        # Create jobs if not dry run
        if tracks:
            if args.dry_run:
                print(f"\n[DRY RUN] Would create {len(tracks)} metadata extraction jobs")
                print(f"[DRY RUN] Jobs would be created with priority 10 (low priority)")
                print(f"[DRY RUN] Use job queue delays to control processing speed")
            else:
                print(f"\n[INFO] Creating metadata extraction jobs...")
                jobs_created = create_metadata_extraction_jobs(tracks, args.force_update, args.dry_run)
                
                if jobs_created > 0:
                    print(f"\n[SUCCESS] Created {jobs_created} metadata extraction jobs")
                    print(f"[INFO] Jobs will be processed with configured delays")
                    print(f"[INFO] Monitor progress at: /jobs page in web interface")
                    print(f"[INFO] Configure delays at: /settings page in web interface")
                else:
                    print(f"\n[ERROR] Failed to create jobs")
                    sys.exit(1)
        else:
            print(f"\n[INFO] No tracks found missing metadata")
            if not args.force_update:
                print(f"[INFO] All tracks already have metadata!")
        
        conn.close()
        
    except Exception as e:
        print(f"[ERROR] Scanner failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main() 
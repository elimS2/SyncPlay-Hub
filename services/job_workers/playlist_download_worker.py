#!/usr/bin/env python3
"""
Playlist Download Worker

Worker for downloading individual YouTube playlists through Job Queue system.
Integrates with existing download_content.py.
"""

import sys
import subprocess
import sqlite3
from pathlib import Path
from typing import List
from datetime import datetime
import os
import shutil

# Add root folder to path for imports
sys.path.append(str(Path(__file__).parent.parent.parent))

from services.job_types import JobWorker, Job, JobType
from utils.cookies_manager import get_random_cookie_file


class PlaylistDownloadWorker(JobWorker):
    """Worker for downloading individual YouTube playlists."""
    
    def __init__(self):
        super().__init__("playlist_download_worker")
        self.supported_types = [
            JobType.PLAYLIST_DOWNLOAD,
            JobType.PLAYLIST_SYNC,
            JobType.SINGLE_VIDEO_DOWNLOAD
        ]
    
    def get_supported_job_types(self) -> List[JobType]:
        """Returns supported job types."""
        return self.supported_types
    
    def execute_job(self, job: Job) -> bool:
        """
        Executes playlist or single video download.
        
        Expected parameters in job.job_data:
        - playlist_url: Playlist or video URL to download
        - target_folder: Target folder name for saving (optional)
        - download_archive: Whether to use archive (default: True)
        - max_downloads: Maximum number of downloads (optional)
        - playlist_start: Video number to start from (optional)
        - playlist_end: Video number to stop at (optional)
        - format_selector: Format for download (optional, default: best)
        - extract_audio: Extract audio only (default: False)
        
        Returns:
            True if download successful, False if not
        """
        try:
            # Extract parameters from job data
            playlist_url = job.job_data.get('playlist_url')
            target_folder = job.job_data.get('target_folder')
            download_archive = job.job_data.get('download_archive', True)
            max_downloads = job.job_data.get('max_downloads')
            playlist_start = job.job_data.get('playlist_start')
            playlist_end = job.job_data.get('playlist_end')
            format_selector = job.job_data.get('format_selector', 'best')
            extract_audio = job.job_data.get('extract_audio', False)
            
            if not playlist_url:
                raise ValueError("playlist_url is required")
            
            print(f"Starting playlist download: {playlist_url}")
            print(f"Target folder: {target_folder}")
            print(f"Download archive: {download_archive}, Max downloads: {max_downloads}")
            print(f"Playlist range: {playlist_start}-{playlist_end}")
            print(f"Format: {format_selector}, Extract audio: {extract_audio}")
            
            # Determine working directory (project root)
            project_root = Path(__file__).parent.parent.parent
            
            # Load configuration from .env
            config = self._load_config(project_root)
            
            # Determine paths
            if 'ROOT_DIR' in config:
                root_dir = Path(config['ROOT_DIR'])
                # If ROOT_DIR already contains path to Playlists, use it directly
                if root_dir.name == 'Playlists':
                    playlists_dir = root_dir
                else:
                    playlists_dir = root_dir / 'Playlists'
            else:
                root_dir = project_root  # fallback
            playlists_dir = root_dir / 'Playlists'
            
            # Create target folder if specified
            if target_folder:
                target_path = playlists_dir / target_folder
                target_path.mkdir(parents=True, exist_ok=True)
                print(f"Target directory: {target_path}")
            
            print(f"Using playlists directory: {playlists_dir}")
            
            # Determine download type
            if job.job_type == JobType.SINGLE_VIDEO_DOWNLOAD:
                success = self._download_single_video(
                    playlist_url, config, project_root, target_folder,
                    download_archive, format_selector, extract_audio, job.job_data
                )
            else:
                success = self._download_playlist(
                    playlist_url, config, project_root, target_folder,
                    download_archive, max_downloads, playlist_start, 
                    playlist_end, format_selector, extract_audio
                )
            
            return success
            
        except Exception as e:
            print(f"Exception during playlist download: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _download_playlist(self, playlist_url: str, config: dict, project_root: Path,
                          target_folder: str, download_archive: bool, max_downloads: int,
                          playlist_start: int, playlist_end: int, format_selector: str,
                          extract_audio: bool) -> bool:
        """Downloads playlist."""
        try:
            # Use download_playlist.py for playlists
            script_path = project_root / 'download_playlist.py'
            if not script_path.exists():
                # Fallback to download_content.py
                script_path = project_root / 'download_content.py'
            
            cmd = [
                sys.executable,
                str(script_path),
                playlist_url
            ]
            
            # Add root directory
            if config.get('ROOT_DIR'):
                cmd.extend(['--root', config['ROOT_DIR']])
            
            # Add proxy support
            if config.get('PROXY_URL'):
                cmd.extend(['--proxy', config['PROXY_URL']])
                print(f"Using proxy for playlist: {config['PROXY_URL']}")
            
            # Add target folder
            if target_folder:
                cmd.extend(['--folder', target_folder])
            
            # Add optional parameters
            if not download_archive:
                cmd.append('--no-archive')
            
            if max_downloads:
                cmd.extend(['--max-downloads', str(max_downloads)])
            
            if playlist_start:
                cmd.extend(['--playlist-start', str(playlist_start)])
            
            if playlist_end:
                cmd.extend(['--playlist-end', str(playlist_end)])
            
            if extract_audio:
                cmd.append('--extract-audio')
            
            if format_selector != 'best':
                cmd.extend(['--format', format_selector])
            
            print(f"Executing command: {' '.join(cmd)}")
            
            # Run download with output capture
            result = subprocess.run(
                cmd,
                cwd=str(project_root),
                capture_output=True,
                text=True,
                timeout=7200  # 2 hours timeout for large playlists
            )
            
            # Output result for logging
            if result.stdout:
                print("=== STDOUT ===")
                print(result.stdout)
            
            if result.stderr:
                print("=== STDERR ===")
                print(result.stderr)
            
            print(f"Process exit code: {result.returncode}")
            
            # Check result
            if result.returncode == 0:
                print("Playlist download completed successfully")
                
                # Update database with scan
                self._update_database_scan(config.get('DB_PATH'))
                
                # Cleanup temporary files in playlists directory  
                if target_folder and config.get('ROOT_DIR'):
                    root_dir = Path(config['ROOT_DIR'])
                    playlists_dir = root_dir / 'Playlists' if root_dir.name != 'Playlists' else root_dir
                    target_path = playlists_dir / target_folder
                    self._cleanup_folder_temp_files(target_path)
                
                return True
            else:
                print(f"Playlist download failed with exit code {result.returncode}")
                if result.stderr:
                    print(f"Error output: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            print("Playlist download timed out (2 hours)")
            return False
        except Exception as e:
            print(f"Exception during playlist download: {e}")
            return False
    
    def _download_single_video(self, video_url: str, config: dict, project_root: Path,
                              target_folder: str, download_archive: bool, 
                              format_selector: str, extract_audio: bool, job_data: dict) -> bool:
        """Downloads single video."""
        try:
            # Use yt-dlp directly for single videos
            cmd = ['yt-dlp']
            
            # Determine save path
            if config.get('ROOT_DIR'):
                root_dir = Path(config['ROOT_DIR'])
                # If ROOT_DIR already contains path to Playlists, use it directly
                if root_dir.name == 'Playlists':
                    playlists_dir = root_dir
                else:
                    playlists_dir = root_dir / 'Playlists'
            else:
                playlists_dir = project_root / 'Playlists'
            
            if target_folder:
                output_dir = playlists_dir / target_folder
            else:
                output_dir = playlists_dir / 'SingleVideos'
            
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Output configuration
            output_template = str(output_dir / '%(title)s [%(id)s].%(ext)s')
            cmd.extend(['-o', output_template])
            
            # Format with fallback to bypass HTTP 403
            if extract_audio:
                cmd.extend(['-f', 'bestaudio', '--extract-audio', '--audio-format', 'mp3'])
            else:
                # Use proven solution: f137+f251 instead of f616+f251 to bypass HTTP 403
                if format_selector == 'bestvideo+bestaudio/best':
                    cmd.extend(['-f', '137+251/best[height<=1080]/best'])
                else:
                    cmd.extend(['-f', format_selector])
            
            # Archive
            if download_archive:
                archive_file = output_dir / 'archive.txt'
                cmd.extend(['--download-archive', str(archive_file)])
            
            # Main options + encoding fix
            cmd.extend([
                '--write-info-json',
                '--write-thumbnail', 
                '--embed-thumbnail',
                '--add-metadata',
                '--restrict-filenames',  # KEY fix for Unicode in Windows
                '--user-agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                '--extractor-retries', '3',
                '--fragment-retries', '10'
            ])
            
            # Proxy support for bypassing YouTube blocks
            if config.get('PROXY_URL'):
                cmd.extend(['--proxy', config['PROXY_URL']])
                print(f"Using proxy: {config['PROXY_URL']}")
            
            # Cookies support for bypassing YouTube age restrictions and bot detection
            random_cookie = get_random_cookie_file()
            if random_cookie:
                cmd.extend(['--cookies', random_cookie])
                print(f"Using cookies file: {Path(random_cookie).name}")
            else:
                print("No cookies available - download may fail for age-restricted content")
            
            # Additional parameters for download fixes
            if job_data.get('ignore_archive'):
                cmd.append('--no-download-archive')
            if job_data.get('force_overwrites'):
                cmd.append('--force-overwrites')
            
            # Video URL
            cmd.append(video_url)
            
            print(f"Executing command: {' '.join(cmd)}")
            
            # Run download with correct encoding for Windows
            env = os.environ.copy()
            env['PYTHONIOENCODING'] = 'utf-8'
            
            result = subprocess.run(
                cmd,
                cwd=str(project_root),
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=3600,  # 1 hour timeout for single video
                env=env
            )
            
            # Output result for logging
            if result.stdout:
                print("=== STDOUT ===")
                print(result.stdout)
            
            if result.stderr:
                print("=== STDERR ===")
                print(result.stderr)
            
            print(f"Process exit code: {result.returncode}")
            
            # Check result
            if result.returncode == 0:
                print("Single video download completed successfully")
                
                # Update database with scan
                self._update_database_scan(config.get('DB_PATH'))
                
                # Cleanup temporary files in the download folder
                self._cleanup_folder_temp_files(output_dir)
                
                return True
            else:
                print(f"Single video download failed with exit code {result.returncode}")
                if result.stderr:
                    print(f"Error output: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            print("Single video download timed out (1 hour)")
            return False
        except Exception as e:
            print(f"Exception during single video download: {e}")
            return False
    
    def _update_database_scan(self, db_path: str = None):
        """Updates database by scanning new files."""
        try:
            if not db_path:
                # Fallback to default path
                project_root = Path(__file__).parent.parent.parent
                db_path = str(project_root / 'tracks.db')
            
            # Call scan_to_db.py to update database
            project_root = Path(__file__).parent.parent.parent
            scan_script = project_root / 'scan_to_db.py'
            
            if scan_script.exists():
                cmd = [
                    sys.executable,
                    str(scan_script)
                ]
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=300  # 5 minutes timeout for scanning
                )
                
                if result.returncode == 0:
                    print("Database scan completed successfully")
                    if result.stdout:
                        print(result.stdout.strip())
                else:
                    print(f"Database scan failed: {result.stderr}")
            else:
                print("Warning: scan_to_db.py not found, skipping database update")
                
        except Exception as e:
            print(f"Warning: Failed to update database: {e}")
    
    def _load_config(self, project_root: Path) -> dict:
        """Loads configuration from .env file."""
        config = {}
        env_path = project_root / '.env'
        
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
    
    def get_worker_info(self) -> dict:
        """Worker information for monitoring."""
        info = super().get_worker_info()
        info.update({
            'description': 'Downloads YouTube playlists and single videos using yt-dlp',
            'max_concurrent_jobs': 2,  # Can download 2 playlists in parallel
            'average_duration': '15-60 minutes',
            'supported_features': [
                'playlist_download',
                'single_video_download',
                'audio_extraction',
                'format_selection',
                'playlist_range',
                'download_archive',
                'database_update'
            ]
        })
        return info 
    
    def _cleanup_folder_temp_files(self, folder_path: Path):
        """
        Clean up temporary files in the specified folder after download.
        
        Args:
            folder_path: Path to folder to clean up
        """
        try:
            if not folder_path.exists():
                return
                
            print(f"Cleaning up temporary files in: {folder_path}")
            
            # Temporary files and YouTube metadata files patterns
            temp_patterns = [
                '*.tmp',
                '*.temp',
                '*.part',
                '*.download',
                '*.ytdl',
                '*.pyc',
                # YouTube metadata files (yt-dlp creates these)
                '*.info.json',      # Detailed video information
                '*.description',    # Video descriptions
                '*.thumbnail',      # Video thumbnails
                '*.webp',          # WebP images (thumbnails)
                '*.jpg',           # JPEG images (thumbnails) 
                '*.png',           # PNG images (thumbnails)
            ]
            
            removed_count = 0
            total_size = 0
            
            for pattern in temp_patterns:
                for file_path in folder_path.glob(pattern):
                    if file_path.is_file():
                        try:
                            file_size = file_path.stat().st_size
                            file_path.unlink()
                            print(f"  [Cleanup] Removed: {file_path.name} ({file_size:,} bytes)")
                            removed_count += 1
                            total_size += file_size
                        except Exception as e:
                            print(f"  [Cleanup] Failed to remove {file_path.name}: {e}")
                
                # Handle __pycache__ directories
                if pattern == '__pycache__':
                    for cache_dir in folder_path.glob('__pycache__'):
                        if cache_dir.is_dir():
                            try:
                                shutil.rmtree(cache_dir)
                                print(f"  [Cleanup] Removed directory: {cache_dir.name}")
                                removed_count += 1
                            except Exception as e:
                                print(f"  [Cleanup] Failed to remove directory {cache_dir.name}: {e}")
            
            if removed_count > 0:
                print(f"[Cleanup] Completed: {removed_count} files removed, {total_size / (1024*1024):.1f} MB freed")
            else:
                print("[Cleanup] No temporary files found to remove")
                
        except Exception as e:
            print(f"[Cleanup] Warning: Failed to cleanup temporary files: {e}") 
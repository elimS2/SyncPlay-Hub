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
from utils.cookies_manager import get_random_cookie_file, get_cookie_file, record_cookie_outcome


class PlaylistDownloadWorker(JobWorker):
    """Worker for downloading individual YouTube playlists."""
    
    def __init__(self):
        super().__init__("playlist_download_worker")
        self.supported_types = [
            JobType.PLAYLIST_DOWNLOAD,
            JobType.PLAYLIST_SYNC,
            JobType.SINGLE_VIDEO_DOWNLOAD
        ]
        self._yt_dlp_version_checked = False
    
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
            # Check yt-dlp version once per worker lifecycle
            self._check_yt_dlp_version(config)
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
            # Check yt-dlp version once per worker lifecycle
            self._check_yt_dlp_version(config)
            import time
            import random
            
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

            # Feature flags / configuration
            retry_ladder_enabled = str(config.get('YTDLP_RETRY_LADDER', '1')).strip() not in ('0', 'false', 'False')
            max_attempts = int(config.get('YTDLP_MAX_ATTEMPTS', '4'))
            backoff_min_ms = int(config.get('YTDLP_BACKOFF_MIN_MS', '1000'))
            backoff_max_ms = int(config.get('YTDLP_BACKOFF_MAX_MS', '5000'))
            align_ua_with_client = str(config.get('YTDLP_ALIGN_UA_WITH_CLIENT', '0')).strip() in ('1', 'true', 'True')

            # Helper to construct UA per client if alignment is enabled
            def user_agent_for_client(client: str | None) -> str:
                if not align_ua_with_client:
                    return 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
                if client == 'android':
                    return 'Mozilla/5.0 (Linux; Android 12; SM-G998B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Mobile Safari/537.36'
                if client == 'ios':
                    return 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1'
                # web/default
                return 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'

            # Prepare attempt configurations (ladder)
            # We avoid TV client based on observed SABR correlation.
            attempt_plan = [
                { 'name': 'web-default', 'player_client': None, 'rotate_cookie': False, 'rotate_proxy': False, 'extra_flags': [] },
                { 'name': 'android',     'player_client': 'android', 'rotate_cookie': False, 'rotate_proxy': False, 'extra_flags': [] },
                { 'name': 'web-rotated', 'player_client': None, 'rotate_cookie': True,  'rotate_proxy': True,  'extra_flags': [] },
                { 'name': 'ios-final',   'player_client': 'ios', 'rotate_cookie': True,  'rotate_proxy': True,  'extra_flags': ['--force-ipv4', '--http-chunk-size', '10M'] },
            ]

            if not retry_ladder_enabled:
                attempt_plan = attempt_plan[:1]
                max_attempts = 1

            # Build command per attempt
            def build_cmd(player_client: str | None, cookies_path: str | None, extra_flags: list[str], proxy_url: str | None) -> list[str]:
                cmd = ['yt-dlp']
                cmd.extend(['-o', output_template])

                # Format selection
                if extract_audio:
                    cmd.extend(['-f', 'bestaudio', '--extract-audio', '--audio-format', 'mp3'])
                else:
                    if format_selector == 'bestvideo+bestaudio/best':
                        cmd.extend(['-f', '137+251/best[height<=1080]/best'])
                    else:
                        cmd.extend(['-f', format_selector])

                # Archive: only add if enabled and not explicitly ignored
                ignore_archive = bool(job_data.get('ignore_archive'))
                if download_archive and not ignore_archive:
                    archive_file = output_dir / 'archive.txt'
                    cmd.extend(['--download-archive', str(archive_file)])

                # Common options
                cmd.extend([
                    '--write-info-json',
                    '--write-thumbnail', 
                    '--embed-thumbnail',
                    '--add-metadata',
                    '--restrict-filenames',
                    '--user-agent', user_agent_for_client(player_client),
                    '--extractor-retries', '3',
                    '--fragment-retries', '10'
                ])

                # Extractor args for client switching
                if player_client:
                    cmd.extend(['--extractor-args', f'youtube:player_client={player_client}'])

                # Proxy support (attempt-specific)
                if proxy_url:
                    cmd.extend(['--proxy', proxy_url])

                # Cookies
                if cookies_path:
                    cmd.extend(['--cookies', cookies_path])

                # Extra flags for certain attempts
                if extra_flags:
                    cmd.extend(extra_flags)

                # Additional parameters
                if job_data.get('force_overwrites'):
                    cmd.append('--force-overwrites')

                # URL
                cmd.append(video_url)
                return cmd

            # Select initial cookie
            base_cookie = get_cookie_file(prefer_healthy=True)
            if base_cookie:
                print(f"Using cookies file: {Path(base_cookie).name}")
            else:
                print("No cookies available - download may fail for age-restricted content")

            # Proxy configuration: support PROXY_URLS (comma-separated) and fallback PROXY_URL
            proxy_urls_raw = str(config.get('PROXY_URLS', '')).strip()
            proxy_list = [p.strip() for p in proxy_urls_raw.split(',') if p.strip()] if proxy_urls_raw else []
            if not proxy_list and config.get('PROXY_URL'):
                proxy_list = [config.get('PROXY_URL')]
            proxy_index = 0

            # Environment
            env = os.environ.copy()
            env['PYTHONIOENCODING'] = 'utf-8'

            # Attempt loop
            attempt_index = 0
            seen_sabr_or_403 = False
            for plan in attempt_plan:
                attempt_index += 1

                # Decide cookie for this attempt
                cookies_for_attempt = base_cookie
                if plan['rotate_cookie']:
                    # Prefer a different healthy cookie when rotating
                    rotated = get_cookie_file(prefer_healthy=True)
                    # Avoid picking the same cookie if possible
                    if rotated == base_cookie:
                        try_alt = get_cookie_file(prefer_healthy=True)
                        if try_alt:
                            rotated = try_alt
                    if rotated and rotated != base_cookie:
                        cookies_for_attempt = rotated

                # Decide proxy for this attempt
                proxy_for_attempt = None
                if proxy_list:
                    proxy_for_attempt = proxy_list[proxy_index % len(proxy_list)]
                # Rotate proxy if the plan indicates so
                if plan.get('rotate_proxy'):
                    proxy_index += 1
                    if proxy_list:
                        proxy_for_attempt = proxy_list[proxy_index % len(proxy_list)]

                cmd = build_cmd(plan['player_client'], cookies_for_attempt, plan['extra_flags'], proxy_for_attempt)

                # One-line attempt log
                attempt_log = (
                    f"attempt={attempt_index}/{min(max_attempts, len(attempt_plan))} "
                    f"client={plan['player_client'] or 'web'} "
                    f"cookie={(Path(cookies_for_attempt).name if cookies_for_attempt else 'none')} "
                    f"proxy={(proxy_for_attempt or 'none')} "
                    f"format={'137+251' if (not extract_audio and format_selector=='bestvideo+bestaudio/best') else format_selector}"
                )
                print(attempt_log)
                print(f"Executing command: {' '.join(cmd)}")

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

                # Success?
                if result.returncode == 0:
                    print("Single video download completed successfully")
                    if cookies_for_attempt:
                        try:
                            record_cookie_outcome(cookies_for_attempt, success=True)
                        except Exception:
                            pass
                    self._update_database_scan(config.get('DB_PATH'))
                    self._cleanup_folder_temp_files(output_dir)
                    return True

                # Decide if we should retry based on stderr markers
                stderr_lower = (result.stderr or '').lower()
                sabr_marker = 'sabr' in stderr_lower or 'missing a url' in stderr_lower
                forbidden_403 = 'http error 403' in stderr_lower or 'forbidden' in stderr_lower
                permanent_markers = ['this video is private', 'video unavailable', 'copyright']
                is_permanent = any(m in stderr_lower for m in permanent_markers)
                if sabr_marker or forbidden_403:
                    seen_sabr_or_403 = True

                if is_permanent or attempt_index >= max_attempts:
                    if cookies_for_attempt:
                        try:
                            record_cookie_outcome(cookies_for_attempt, success=False)
                        except Exception:
                            pass
                    # Stop retrying
                    break

                # Retry only if SABR/403-like
                if sabr_marker or forbidden_403:
                    if cookies_for_attempt:
                        try:
                            record_cookie_outcome(cookies_for_attempt, success=False)
                        except Exception:
                            pass
                    # backoff with jitter
                    delay_ms = random.randint(backoff_min_ms, backoff_max_ms)
                    time.sleep(delay_ms / 1000.0)
                    continue
                else:
                    if cookies_for_attempt:
                        try:
                            record_cookie_outcome(cookies_for_attempt, success=False)
                        except Exception:
                            pass
                    # Unknown error kind; do not spin endlessly
                    break

            # If reached here, not successful
            print("Single video download failed after attempts")
            if seen_sabr_or_403:
                # Raise exception to classify as network error for queue retry policy
                raise RuntimeError("network: SABR/403 encountered across attempts")
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
            # Load configuration to get direct paths  
            project_root = Path(__file__).parent.parent.parent
            config = self._load_config(project_root)
            playlists_dir = config.get('PLAYLISTS_DIR', 'D:/music/Youtube/Playlists')
            config_db_path = config.get('DB_PATH', 'D:/music/Youtube/DB/tracks.db')
            
            # Use provided db_path or fall back to config or default
            if not db_path:
                db_path = config_db_path
            
            # Call scan_to_db.py to update database
            scan_script = project_root / 'scan_to_db.py'
            
            if scan_script.exists():
                cmd = [
                    sys.executable,
                    str(scan_script),
                    '--playlists-dir', playlists_dir,
                    '--db-path', db_path
                ]
                
                print(f"Running database scan with playlists: {playlists_dir}")
                print(f"Running database scan with database: {db_path}")
                
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

    def _check_yt_dlp_version(self, config: dict) -> None:
        """Log yt-dlp version and warn if older than minimum configured version."""
        try:
            if self._yt_dlp_version_checked:
                return
            self._yt_dlp_version_checked = True

            import subprocess
            result = subprocess.run(['yt-dlp', '--version'], capture_output=True, text=True, timeout=10)
            version_str = (result.stdout or '').strip()
            if not version_str:
                print("[yt-dlp] Unable to determine yt-dlp version")
                return

            print(f"[yt-dlp] Detected yt-dlp version: {version_str}")

            min_required = str(config.get('YTDLP_MIN_VERSION', '2024.12.01')).strip()

            def parse_v(s: str):
                try:
                    parts = s.split('.')
                    return tuple(int(p) for p in parts[:3])
                except Exception:
                    return None

            cur = parse_v(version_str)
            req = parse_v(min_required)
            if cur and req and cur < req:
                print(f"[yt-dlp] Warning: yt-dlp {version_str} is older than recommended minimum {min_required}. Consider upgrading: pip install -U yt-dlp")
        except Exception as e:
            print(f"[yt-dlp] Version check skipped due to error: {e}")
    
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
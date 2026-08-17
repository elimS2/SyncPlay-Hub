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
from utils.yt_dlp_js import extend_ytdlp_cli_cmd, ytdlp_js_runtime_bin_dir


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
            
        except RuntimeError:
            raise
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
                self._sync_published_dates_after_scan()
                
                # Persist sidecar metadata before cleanup deletes *.info.json
                if target_folder and config.get('ROOT_DIR'):
                    root_dir = Path(config['ROOT_DIR'])
                    playlists_dir = root_dir / 'Playlists' if root_dir.name != 'Playlists' else root_dir
                    target_path = playlists_dir / target_folder
                    self._persist_download_metadata(target_path)
                    self._sync_published_dates_after_scan()
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
                library_dir = playlists_dir / target_folder
            else:
                library_dir = playlists_dir / 'SingleVideos'

            safe_quality_upgrade = bool(job_data.get('safe_quality_upgrade'))
            if safe_quality_upgrade:
                from utils.quality_upgrade import staging_dir_for_video
                video_id = self._resolve_job_video_id(job_data)
                if not video_id:
                    raise ValueError("safe_quality_upgrade requires video_id")
                output_dir = staging_dir_for_video(playlists_dir, video_id)
                raw_job_data = job_data._data if hasattr(job_data, "_data") else job_data
                job_data = dict(raw_job_data)
                job_data['force_overwrites'] = False
                job_data['cleanup_old_variants'] = False
                print(f"[QualityUpgrade] Staging download for {video_id} at {output_dir}")
            else:
                output_dir = library_dir

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
                if client == 'mweb':
                    return 'Mozilla/5.0 (Linux; Android 12; SM-G998B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Mobile Safari/537.36'
                if client == 'tv_embedded':
                    return 'Mozilla/5.0 (ChromiumStylePlatform) Cobalt/Version'
                # web/default
                return 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'

            # Prepare attempt configurations (ladder).
            # android_vr/android/ios skip cookies in yt-dlp; stale cookies often break web client.
            attempt_plan = [
                {'name': 'web-default', 'player_client': None, 'rotate_cookie': False, 'rotate_proxy': False, 'extra_flags': [], 'skip_cookies': False},
                {'name': 'android-vr-no-cookie', 'player_client': 'android_vr', 'rotate_cookie': False, 'rotate_proxy': False, 'extra_flags': [], 'skip_cookies': True},
                {'name': 'mweb', 'player_client': 'mweb', 'rotate_cookie': False, 'rotate_proxy': False, 'extra_flags': [], 'skip_cookies': False},
                {'name': 'web-rotated', 'player_client': None, 'rotate_cookie': True, 'rotate_proxy': True, 'extra_flags': ['--force-ipv4'], 'skip_cookies': False},
            ]

            if not retry_ladder_enabled:
                attempt_plan = attempt_plan[:1]
                max_attempts = 1

            # Build command per attempt
            def build_cmd(player_client: str | None, cookies_path: str | None, extra_flags: list[str], proxy_url: str | None, current_format_selector: str) -> list[str]:
                cmd = ['yt-dlp']
                extend_ytdlp_cli_cmd(cmd)
                cmd.extend(['-o', output_template])

                # Format selection
                if extract_audio:
                    cmd.extend(['-f', 'bestaudio', '--extract-audio', '--audio-format', 'mp3'])
                else:
                    cmd.extend(['-f', current_format_selector])
                    # Prefer MP4 container merge when possible (no re-encode)
                    if job_data.get('prefer_mp4', True):
                        cmd.extend(['--merge-output-format', 'mp4'])

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

                # Extractor args for client switching / optional PO token (mweb high-quality HTTPS)
                extractor_args: list[str] = []
                if player_client:
                    extractor_args.append(f'player_client={player_client}')
                po_token = str(config.get('YOUTUBE_PO_TOKEN', '') or '').strip()
                if po_token:
                    extractor_args.append(f'po_token={po_token}')
                if extractor_args:
                    cmd.extend(['--extractor-args', 'youtube:' + ':'.join(extractor_args)])

                # Proxy support (attempt-specific)
                if proxy_url:
                    cmd.extend(['--proxy', proxy_url])

                # Cookies (android/ios/android_vr clients ignore cookies in yt-dlp)
                cookie_incompatible_clients = {'android', 'android_vr', 'ios'}
                if cookies_path and player_client not in cookie_incompatible_clients:
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
            
            # Ensure the selected JS runtime (Deno preferred) is on PATH for yt-dlp EJS.
            js_runtime_dir = ytdlp_js_runtime_bin_dir()
            if js_runtime_dir:
                env['PATH'] = js_runtime_dir + os.pathsep + env.get('PATH', '')

            # Attempt loop
            attempt_index = 0
            seen_sabr_or_403 = False
            for plan in attempt_plan:
                attempt_index += 1

                # Decide cookie for this attempt
                cookies_for_attempt = None if plan.get('skip_cookies') else base_cookie
                if plan['rotate_cookie'] and not plan.get('skip_cookies'):
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

                # Initial command with requested format
                cmd = build_cmd(plan['player_client'], cookies_for_attempt, plan['extra_flags'], proxy_for_attempt, format_selector)

                # One-line attempt log
                attempt_log = (
                    f"attempt={attempt_index}/{min(max_attempts, len(attempt_plan))} "
                    f"client={plan['player_client'] or 'web'} "
                    f"cookie={(Path(cookies_for_attempt).name if cookies_for_attempt else 'none')} "
                    f"proxy={(proxy_for_attempt or 'none')} "
                    f"skip_cookies={bool(plan.get('skip_cookies'))} "
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
                    if safe_quality_upgrade:
                        return self._finalize_safe_quality_upgrade(
                            config, playlists_dir, output_dir, job_data
                        )
                    self._finalize_single_video_download(config, output_dir, job_data)
                    return True

                # If requested format is not available, try safe format fallbacks within the same attempt
                stderr_lower = (result.stderr or '').lower()
                format_unavailable = ('requested format is not available' in stderr_lower) or ('requested formats are incompatible' in stderr_lower) or ('format not available' in stderr_lower)

                if (not extract_audio) and format_unavailable:
                    try:
                        target_height = int(job_data.get('target_height', 1080))
                    except Exception:
                        target_height = 1080
                    # Construct ordered fallback selectors (most strict to most lenient)
                    fallback_selectors: list[str] = [
                        f"bestvideo[ext=mp4][vcodec*=avc1][height<={target_height}]+bestaudio[ext=m4a]",
                        f"bestvideo[height<={target_height}]+bestaudio/best",
                        "bestvideo[height<=2160]+bestaudio/best",
                        "bestvideo+bestaudio/best",
                        "137+140",
                        "136+140",
                        # Progressive / single-file formats are last resort (often 360p-720p).
                        "22/best[ext=mp4]",
                    ]
                    # Remove duplicates and the already tried selector
                    fallback_selectors = [s for s in fallback_selectors if s and s != format_selector]

                    for idx, fb_selector in enumerate(fallback_selectors, start=1):
                        print(f"[FormatFallback] Trying fallback #{idx}: -f {fb_selector}")
                        fb_cmd = build_cmd(plan['player_client'], cookies_for_attempt, plan['extra_flags'], proxy_for_attempt, fb_selector)
                        print(f"Executing command: {' '.join(fb_cmd)}")
                        fb_result = subprocess.run(
                            fb_cmd,
                            cwd=str(project_root),
                            capture_output=True,
                            text=True,
                            encoding='utf-8',
                            errors='replace',
                            timeout=3600,
                            env=env
                        )
                        if fb_result.stdout:
                            print("=== STDOUT ===")
                            print(fb_result.stdout)
                        if fb_result.stderr:
                            print("=== STDERR ===")
                            print(fb_result.stderr)
                        print(f"Process exit code: {fb_result.returncode}")

                        if fb_result.returncode == 0:
                            print("Single video download completed successfully (via format fallback)")
                            if cookies_for_attempt:
                                try:
                                    record_cookie_outcome(cookies_for_attempt, success=True)
                                except Exception:
                                    pass
                            if safe_quality_upgrade:
                                return self._finalize_safe_quality_upgrade(
                                    config, playlists_dir, output_dir, job_data
                                )
                            self._finalize_single_video_download(config, output_dir, job_data)
                            return True

                        # Prepare for next decision loop by replacing result with the last fallback result
                        result = fb_result
                        stderr_lower = (result.stderr or '').lower()

                # Decide if we should retry based on stderr markers
                sabr_marker = 'sabr' in stderr_lower or 'missing a url' in stderr_lower
                forbidden_403 = 'http error 403' in stderr_lower or 'forbidden' in stderr_lower
                reload_marker = 'page needs to be reloaded' in stderr_lower or 'needs to be reloaded' in stderr_lower
                images_only_marker = 'only images are available' in stderr_lower
                retryable_marker = sabr_marker or forbidden_403 or reload_marker or images_only_marker
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
                    if safe_quality_upgrade and is_permanent:
                        from utils.quality_upgrade import cleanup_staging
                        cleanup_staging(output_dir)
                        raise ValueError(
                            "YouTube video unavailable; original library file was not modified"
                        )
                    # Stop retrying
                    break

                # Retry on transient YouTube client/cookie issues (incl. stale cookies).
                if retryable_marker:
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
            if safe_quality_upgrade:
                from utils.quality_upgrade import cleanup_staging
                cleanup_staging(output_dir)
            if seen_sabr_or_403:
                # Raise exception to classify as network error for queue retry policy
                raise RuntimeError("network: SABR/403 encountered across attempts")
            return False
                
        except subprocess.TimeoutExpired:
            print("Single video download timed out (1 hour)")
            if bool(job_data.get('safe_quality_upgrade')):
                try:
                    from utils.quality_upgrade import cleanup_staging
                    cleanup_staging(output_dir)
                except Exception:
                    pass
            return False
        except RuntimeError:
            raise
        except ValueError:
            raise
        except Exception as e:
            print(f"Exception during single video download: {e}")
            if bool(job_data.get('safe_quality_upgrade')):
                try:
                    from utils.quality_upgrade import cleanup_staging
                    cleanup_staging(output_dir)
                except Exception:
                    pass
            return False

    def _resolve_job_video_id(self, job_data: dict) -> str:
        """Return video_id from job data or parse it from the download URL."""
        video_id = (job_data.get('video_id') or '').strip()
        if video_id:
            return video_id
        try:
            from utils.youtube_channel_urls import extract_video_id_from_url
            return extract_video_id_from_url(job_data.get('playlist_url') or '') or ''
        except Exception:
            return ''

    def _persist_download_metadata(self, output_dir: Path, video_id: str | None = None) -> None:
        """Save youtube_video_metadata from yt-dlp info.json before sidecar cleanup."""
        try:
            from utils.metadata_utils import persist_download_metadata_from_directory
            persist_download_metadata_from_directory(
                output_dir,
                video_id=video_id or None,
                logger_func=print,
            )
        except Exception as e:
            print(f"[PostProcess] Warning: failed to persist download metadata: {e}")

    def _sync_published_dates_after_scan(self, video_id: str | None = None) -> None:
        """Copy publication dates onto track rows created by the library scan."""
        try:
            from utils.metadata_utils import sync_missing_published_dates_from_metadata
            sync_missing_published_dates_from_metadata(video_id=video_id or None, logger_func=print)
        except Exception as e:
            print(f"[PostProcess] Warning: failed to sync published_date: {e}")

    def _finalize_safe_quality_upgrade(
        self, config: dict, playlists_dir: Path, staging_dir: Path, job_data: dict
    ) -> bool:
        """Persist metadata, rotate only if better, never delete the original on failure."""
        from utils.quality_compare import parse_local_height
        from utils.quality_upgrade import cleanup_staging, find_downloaded_video, rotate_if_better

        video_id = self._resolve_job_video_id(job_data)
        print(f"[QualityUpgrade] Finalizing {video_id} from {staging_dir}")
        self._persist_download_metadata(staging_dir, video_id or None)

        new_file = find_downloaded_video(staging_dir, video_id) if video_id else None
        if not new_file:
            print("[QualityUpgrade] No staging media found; original file left untouched")
            cleanup_staging(staging_dir)
            return False

        from database import get_connection

        original_path = None
        old_height = None
        max_height = job_data.get('target_height')
        conn = get_connection()
        try:
            row = conn.execute(
                """
                SELECT t.relpath, t.resolution, yvm.max_available_height
                FROM tracks t
                LEFT JOIN youtube_video_metadata yvm ON yvm.youtube_id = t.video_id
                WHERE t.video_id = ?
                LIMIT 1
                """,
                (video_id,),
            ).fetchone()
            if row:
                relpath, resolution, db_max_height = row
                old_height = parse_local_height(resolution)
                if db_max_height:
                    try:
                        max_height = max(int(max_height or 0), int(db_max_height))
                    except (TypeError, ValueError):
                        max_height = db_max_height
                if relpath:
                    original_path = (playlists_dir / relpath).resolve()
        finally:
            conn.close()

        if original_path is None:
            print("[QualityUpgrade] Track path missing in DB; leaving original untouched")
            cleanup_staging(staging_dir)
            return False

        rotate = rotate_if_better(
            original_path=original_path,
            new_path=new_file,
            playlists_root=playlists_dir,
            old_height=old_height,
            max_height=int(max_height) if max_height else None,
        )
        surviving_path = original_path if original_path.exists() else None
        if rotate.get("rotated"):
            dest = Path(rotate["destination"])
            relpath = str(dest.resolve().relative_to(playlists_dir)).replace("\\", "/")
            conn = get_connection()
            try:
                conn.execute(
                    "UPDATE tracks SET relpath = ?, filetype = ? WHERE video_id = ?",
                    (relpath, dest.suffix.lstrip(".").lower(), video_id),
                )
                conn.commit()
            finally:
                conn.close()
            print(f"[QualityUpgrade] Updated track {video_id} -> {relpath}")
            surviving_path = dest
        else:
            print(f"[QualityUpgrade] No rotation ({rotate.get('reason')}); original kept")

        if video_id and surviving_path:
            try:
                from utils.media_probe import rescan_track_media_properties

                result = rescan_track_media_properties(
                    video_id=video_id,
                    file_path=surviving_path,
                    refresh_duration=True,
                    refresh_size=True,
                )
                if result.get("success"):
                    print(
                        f"[QualityUpgrade] Probed {video_id}: "
                        f"resolution={result.get('resolution')} bitrate={result.get('bitrate')}"
                    )
                else:
                    print(f"[QualityUpgrade] Probe warning: {result.get('error')}")
            except Exception as exc:
                print(f"[QualityUpgrade] Surviving-file probe failed: {exc}")

        if not rotate.get("rotated"):
            cleanup_staging(staging_dir)
            return rotate.get("reason") == "new_file_not_better"

        self._sync_published_dates_after_scan(video_id or None)
        cleanup_staging(staging_dir)
        return True

    def _finalize_single_video_download(self, config: dict, output_dir: Path, job_data: dict) -> None:
        """Persist metadata, update the track row, then remove yt-dlp sidecars."""
        video_id = self._resolve_job_video_id(job_data)
        skip_full_scan = bool(job_data.get('skip_full_scan'))
        print(f"[PostProcess] Debug: video_id='{video_id}', skip_full_scan={skip_full_scan}")
        print(f"[PostProcess] Debug: job_data keys: {list(job_data.keys())}")

        # Persist before cleanup deletes *.info.json
        self._persist_download_metadata(output_dir, video_id or None)

        try:
            if video_id and skip_full_scan:
                print(f"[PostProcess] Using optimized single-track update for {video_id}")
                print(f"[PostProcess] Running full scan first to ensure track {video_id} is in DB")
                self._update_database_scan(config.get('DB_PATH'))
                print(f"[PostProcess] Now updating media properties for {video_id}")
                self._update_single_track_path_and_probe(config, output_dir, video_id)
                try:
                    self._cleanup_old_variants_if_safe(config, video_id)
                except Exception as ce:
                    print(f"[PostProcess] Cleanup skipped due to error: {ce}")
            else:
                print(f"[PostProcess] Using fallback full database scan (video_id={bool(video_id)}, skip_full_scan={skip_full_scan})")
                self._update_database_scan(config.get('DB_PATH'))
        except Exception as e:
            print(f"[PostProcess] Warning: failed to update DB optimally: {e}")
            self._update_database_scan(config.get('DB_PATH'))

        self._sync_published_dates_after_scan(video_id or None)
        self._cleanup_folder_temp_files(output_dir)

    def _update_single_track_path_and_probe(self, config: dict, output_dir: Path, video_id: str) -> None:
        """Update a single track's relpath based on the freshly downloaded file and rescan media properties.

        Looks for a file named '* [<video_id>].<ext>' in output_dir with latest mtime.
        Updates tracks.relpath if changed and triggers media probe to refresh bitrate/resolution/size.
        """
        print(f"[PostProcess] Starting _update_single_track_path_and_probe for {video_id} in {output_dir}")
        try:
            from database import get_connection
            # Resolve ROOT_DIR for relpath computation
            root_dir = None
            if config.get('ROOT_DIR'):
                r = Path(config['ROOT_DIR'])
                root_dir = r if r.name == 'Playlists' else r / 'Playlists'
            if not root_dir:
                # attempt to infer from output_dir's parents
                candidates = [p for p in output_dir.parents]
                for p in candidates:
                    if p.name == 'Playlists':
                        root_dir = p
                        break
            if not root_dir:
                print('[PostProcess] ROOT_DIR not resolved, skipping optimized update')
                return

            # Find newly downloaded playable file matching the video_id
            import re
            pattern = re.compile(rf"\[(?:{re.escape(video_id)})\]\.[^.]+$")
            allowed_exts = {'.mp4', '.mkv', '.webm', '.mov', '.m4a', '.mp3', '.opus', '.flac'}
            candidates = [
                f for f in output_dir.glob('*')
                if f.is_file() and pattern.search(f.name) and f.suffix.lower() in allowed_exts
            ]
            if not candidates:
                print(f"[PostProcess] No file found for video {video_id} in {output_dir}")
                return
            # Pick latest by mtime
            target_file = max(candidates, key=lambda p: p.stat().st_mtime)

            # Compute relpath and update if changed (also update filetype)
            relpath = str(target_file.resolve().relative_to(root_dir)).replace('\\', '/')
            conn = get_connection()
            cur = conn.cursor()
            row = cur.execute("SELECT relpath FROM tracks WHERE video_id = ? LIMIT 1", (video_id,)).fetchone()
            current_rel = row[0] if row else None
            if not current_rel:
                # Track may not be in DB yet; run full scan to add it properly
                conn.close()
                print(f"[PostProcess] Track {video_id} not found in DB; running full scan to add it")
                self._update_database_scan(config.get('DB_PATH'))
                return

            if current_rel != relpath:
                filetype = target_file.suffix.lstrip('.').lower()
                cur.execute("UPDATE tracks SET relpath = ?, filetype = ? WHERE video_id = ?", (relpath, filetype, video_id))
                conn.commit()
                print(f"[PostProcess] Updated relpath for {video_id}: {current_rel} -> {relpath}")

            # Use common utility method for media probing and database update
            from utils.media_probe import rescan_track_media_properties
            
            result = rescan_track_media_properties(
                video_id=video_id,
                file_path=target_file,
                refresh_duration=True,  # Always refresh duration for new downloads
                refresh_size=True       # Always refresh size for new downloads
            )
            
            if result["success"]:
                print(f"[PostProcess] Probed media for {video_id}: bitrate={result['bitrate']}, resolution={result['resolution']}, fps={result['video_fps']}, codec={result['video_codec']}")
                print(f"[PostProcess] Updated fields: {result['fields_updated']}")
            else:
                print(f"[PostProcess] Warning: Media probe failed for {video_id}: {result['error']}")
            
            conn.close()
        except Exception as e:
            print(f"[PostProcess] Error updating single track: {e}")

    def _cleanup_old_variants_if_safe(self, config: dict, video_id: str) -> None:
        """Remove other files with the same [video_id] when DB already points to the new file.

        Preconditions:
        - tracks.relpath exists and points to an existing file
        - Only files in the same directory with '*[video_id].*' will be considered
        """
        import re
        from database import get_connection
        root_dir = None
        if config.get('ROOT_DIR'):
            r = Path(config['ROOT_DIR'])
            root_dir = r if r.name == 'Playlists' else r / 'Playlists'
        if not root_dir or not root_dir.exists():
            return
        conn = get_connection()
        try:
            cur = conn.cursor()
            row = cur.execute("SELECT relpath FROM tracks WHERE video_id = ? LIMIT 1", (video_id,)).fetchone()
            if not row or not row[0]:
                return
            relpath = row[0]
            current_file = (root_dir / relpath).resolve()
            if not current_file.exists():
                return
            start_dir = current_file.parent
            pattern = re.compile(r"\[" + re.escape(video_id) + r"\]")
            allowed_exts = {'.mp4', '.mkv', '.webm', '.mov', '.m4a', '.mp3', '.opus', '.flac'}
            removed = 0
            for candidate in start_dir.glob('*'):
                try:
                    if not candidate.is_file():
                        continue
                    if candidate.resolve() == current_file:
                        continue
                    if not pattern.search(candidate.stem):
                        continue
                    if candidate.suffix.lower() not in allowed_exts:
                        # keep thumbnails and json sidecars
                        continue
                    # Safe remove other variant
                    candidate.unlink(missing_ok=True)
                    removed += 1
                    print(f"[Cleanup] Removed old variant: {candidate.name}")
                except Exception as e:
                    print(f"[Cleanup] Failed to remove {candidate}: {e}")
            if removed:
                print(f"[Cleanup] Old variants removed: {removed}")
        finally:
            conn.close()
    
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

            min_required = str(config.get('YTDLP_MIN_VERSION', '2026.3.17')).strip()

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
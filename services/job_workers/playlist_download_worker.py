#!/usr/bin/env python3
"""
Playlist Download Worker

Воркер для загрузки отдельных плейлистов YouTube через систему Job Queue.
Интегрируется с существующим download_content.py.
"""

import sys
import subprocess
import sqlite3
from pathlib import Path
from typing import List
from datetime import datetime

# Добавляем корневую папку в путь для импортов
sys.path.append(str(Path(__file__).parent.parent.parent))

from services.job_types import JobWorker, Job, JobType


class PlaylistDownloadWorker(JobWorker):
    """Воркер для загрузки отдельных плейлистов YouTube."""
    
    def __init__(self):
        super().__init__("playlist_download_worker")
        self.supported_types = [
            JobType.PLAYLIST_DOWNLOAD,
            JobType.PLAYLIST_SYNC,
            JobType.SINGLE_VIDEO_DOWNLOAD
        ]
    
    def get_supported_job_types(self) -> List[JobType]:
        """Возвращает поддерживаемые типы задач."""
        return self.supported_types
    
    def execute_job(self, job: Job) -> bool:
        """
        Выполняет загрузку плейлиста или отдельного видео.
        
        Ожидаемые параметры в job.job_data:
        - playlist_url: URL плейлиста или видео для загрузки
        - target_folder: название папки для сохранения (optional)
        - download_archive: использовать ли archive (default: True)
        - max_downloads: максимальное количество загрузок (optional)
        - playlist_start: номер видео с которого начать (optional)
        - playlist_end: номер видео на котором остановиться (optional)
        - format_selector: формат для загрузки (optional, default: best)
        - extract_audio: извлекать только аудио (default: False)
        
        Returns:
            True если загрузка успешна, False если нет
        """
        try:
            # Извлекаем параметры из job data
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
            
            # Определяем рабочую директорию (корень проекта)
            project_root = Path(__file__).parent.parent.parent
            
            # Загружаем конфигурацию из .env
            config = self._load_config(project_root)
            
            # Определяем пути
            if 'ROOT_DIR' in config:
                root_dir = Path(config['ROOT_DIR'])
            else:
                root_dir = project_root  # fallback
            
            playlists_dir = root_dir / 'Playlists'
            
            # Создаем целевую папку если указана
            if target_folder:
                target_path = playlists_dir / target_folder
                target_path.mkdir(parents=True, exist_ok=True)
                print(f"Target directory: {target_path}")
            
            print(f"Using playlists directory: {playlists_dir}")
            
            # Определяем тип загрузки
            if job.job_type == JobType.SINGLE_VIDEO_DOWNLOAD:
                success = self._download_single_video(
                    playlist_url, config, project_root, target_folder,
                    download_archive, format_selector, extract_audio
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
        """Загружает плейлист."""
        try:
            # Используем download_playlist.py для плейлистов
            script_path = project_root / 'download_playlist.py'
            if not script_path.exists():
                # Fallback к download_content.py
                script_path = project_root / 'download_content.py'
            
            cmd = [
                sys.executable,
                str(script_path),
                playlist_url
            ]
            
            # Добавляем root директорию
            if config.get('ROOT_DIR'):
                cmd.extend(['--root', config['ROOT_DIR']])
            
            # Добавляем целевую папку
            if target_folder:
                cmd.extend(['--folder', target_folder])
            
            # Добавляем опциональные параметры
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
            
            # Запускаем загрузку с захватом вывода
            result = subprocess.run(
                cmd,
                cwd=str(project_root),
                capture_output=True,
                text=True,
                timeout=7200  # 2 часа timeout для больших плейлистов
            )
            
            # Выводим результат для логирования
            if result.stdout:
                print("=== STDOUT ===")
                print(result.stdout)
            
            if result.stderr:
                print("=== STDERR ===")
                print(result.stderr)
            
            print(f"Process exit code: {result.returncode}")
            
            # Проверяем результат
            if result.returncode == 0:
                print("Playlist download completed successfully")
                
                # Обновляем базу данных сканированием
                self._update_database_scan(config.get('DB_PATH'))
                
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
                              format_selector: str, extract_audio: bool) -> bool:
        """Загружает отдельное видео."""
        try:
            # Используем yt-dlp напрямую для отдельных видео
            cmd = ['yt-dlp']
            
            # Определяем путь для сохранения
            if config.get('ROOT_DIR'):
                playlists_dir = Path(config['ROOT_DIR']) / 'Playlists'
            else:
                playlists_dir = project_root / 'Playlists'
            
            if target_folder:
                output_dir = playlists_dir / target_folder
            else:
                output_dir = playlists_dir / 'SingleVideos'
            
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Настройка вывода
            output_template = str(output_dir / '%(title)s [%(id)s].%(ext)s')
            cmd.extend(['-o', output_template])
            
            # Формат
            if extract_audio:
                cmd.extend(['-f', 'bestaudio', '--extract-audio', '--audio-format', 'mp3'])
            else:
                cmd.extend(['-f', format_selector])
            
            # Archive
            if download_archive:
                archive_file = output_dir / 'archive.txt'
                cmd.extend(['--download-archive', str(archive_file)])
            
            # Дополнительные опции
            cmd.extend([
                '--write-info-json',
                '--write-thumbnail',
                '--embed-thumbnail',
                '--add-metadata'
            ])
            
            # URL видео
            cmd.append(video_url)
            
            print(f"Executing command: {' '.join(cmd)}")
            
            # Запускаем загрузку с захватом вывода
            result = subprocess.run(
                cmd,
                cwd=str(project_root),
                capture_output=True,
                text=True,
                timeout=3600  # 1 час timeout для отдельного видео
            )
            
            # Выводим результат для логирования
            if result.stdout:
                print("=== STDOUT ===")
                print(result.stdout)
            
            if result.stderr:
                print("=== STDERR ===")
                print(result.stderr)
            
            print(f"Process exit code: {result.returncode}")
            
            # Проверяем результат
            if result.returncode == 0:
                print("Single video download completed successfully")
                
                # Обновляем базу данных сканированием
                self._update_database_scan(config.get('DB_PATH'))
                
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
        """Обновляет базу данных сканированием новых файлов."""
        try:
            if not db_path:
                # Fallback к default пути
                project_root = Path(__file__).parent.parent.parent
                db_path = str(project_root / 'tracks.db')
            
            # Вызываем scan_to_db.py для обновления базы
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
                    timeout=300  # 5 минут timeout для сканирования
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
        """Загружает конфигурацию из .env файла."""
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
        """Информация о воркере для мониторинга."""
        info = super().get_worker_info()
        info.update({
            'description': 'Downloads YouTube playlists and single videos using yt-dlp',
            'max_concurrent_jobs': 2,  # Можем загружать 2 плейлиста параллельно
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
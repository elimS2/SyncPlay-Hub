#!/usr/bin/env python3
"""
Channel Download Worker

Воркер для загрузки YouTube каналов через систему Job Queue.
Интегрируется с существующим download_content.py.
"""

import os
import sys
import subprocess
import sqlite3
from pathlib import Path
from typing import List
from datetime import datetime

# Добавляем корневую папку в путь для импортов
sys.path.append(str(Path(__file__).parent.parent.parent))

from services.job_types import JobWorker, Job, JobType
import download_content  # Используем существующую логику загрузки


class ChannelDownloadWorker(JobWorker):
    """Воркер для загрузки YouTube каналов."""
    
    def __init__(self):
        super().__init__("channel_download_worker")
        self.supported_types = [
            JobType.CHANNEL_DOWNLOAD,
            JobType.CHANNEL_SYNC
        ]
    
    def get_supported_job_types(self) -> List[JobType]:
        """Возвращает поддерживаемые типы задач."""
        return self.supported_types
    
    def execute_job(self, job: Job) -> bool:
        """
        Выполняет загрузку канала.
        
        Ожидаемые параметры в job.job_data:
        - channel_url: URL канала для загрузки
        - channel_id: ID канала в базе данных
        - group_name: Название группы каналов
        - download_archive: использовать ли archive (default: True)
        - max_downloads: максимальное количество загрузок (optional)
        
        Returns:
            True если загрузка успешна, False если нет
        """
        try:
            # Извлекаем параметры из job data
            channel_url = job.job_data.get('channel_url')
            channel_id = job.job_data.get('channel_id')
            group_name = job.job_data.get('group_name', 'Default')
            download_archive = job.job_data.get('download_archive', True)
            max_downloads = job.job_data.get('max_downloads')
            
            if not channel_url:
                raise ValueError("channel_url is required")
            
            if not channel_id:
                raise ValueError("channel_id is required")
            
            print(f"Starting channel download: {channel_url}")
            print(f"Channel ID: {channel_id}, Group: {group_name}")
            print(f"Download archive: {download_archive}, Max downloads: {max_downloads}")
            
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
            
            # Создаем папку для группы если нужно
            group_folder = playlists_dir / group_name
            group_folder.mkdir(parents=True, exist_ok=True)
            
            print(f"Using playlists directory: {playlists_dir}")
            print(f"Group folder: {group_folder}")
            
            # Вызываем download_content.py через subprocess для изоляции
            # Это позволяет захватить весь вывод и логи
            cmd = [
                sys.executable,
                str(project_root / 'download_content.py'),
                channel_url,
                '--root', str(root_dir)
            ]
            
            # Добавляем опциональные параметры
            if not download_archive:
                cmd.append('--no-archive')
            
            if max_downloads:
                cmd.extend(['--max-downloads', str(max_downloads)])
            
            print(f"Executing command: {' '.join(cmd)}")
            
            # Запускаем загрузку с захватом вывода
            result = subprocess.run(
                cmd,
                cwd=str(project_root),
                capture_output=True,
                text=True,
                timeout=7200  # 2 часа timeout для больших каналов
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
                print("Channel download completed successfully")
                
                # Обновляем статистику канала в базе данных
                self._update_channel_stats(channel_id, config.get('DB_PATH'))
                
                return True
            else:
                print(f"Channel download failed with exit code {result.returncode}")
                if result.stderr:
                    print(f"Error output: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            print("Channel download timed out (2 hours)")
            return False
        except Exception as e:
            print(f"Exception during channel download: {e}")
            import traceback
            traceback.print_exc()
            return False
    
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
    
    def _update_channel_stats(self, channel_id: int, db_path: str = None):
        """Обновляет статистику канала после загрузки."""
        try:
            if not db_path:
                # Fallback к default пути
                project_root = Path(__file__).parent.parent.parent
                db_path = str(project_root / 'tracks.db')
            
            # Вызываем update_channel_sync через subprocess
            # Это обновит track_count и другую статистику
            cmd = [
                sys.executable,
                '-c',
                f"""
import sys
sys.path.append('{Path(__file__).parent.parent.parent}')
from controllers.api_controller import update_channel_sync
update_channel_sync({channel_id})
print('Channel stats updated successfully')
"""
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                print(f"Channel {channel_id} stats updated successfully")
                if result.stdout:
                    print(result.stdout.strip())
            else:
                print(f"Failed to update channel stats: {result.stderr}")
                
        except Exception as e:
            print(f"Warning: Failed to update channel stats: {e}")
    
    def get_worker_info(self) -> dict:
        """Информация о воркере для мониторинга."""
        info = super().get_worker_info()
        info.update({
            'description': 'Downloads YouTube channels using yt-dlp',
            'max_concurrent_jobs': 1,  # Каналы загружаем по одному
            'average_duration': '30-60 minutes',
            'supported_features': [
                'download_archive',
                'max_downloads_limit',
                'channel_statistics_update',
                'progress_tracking'
            ]
        })
        return info 
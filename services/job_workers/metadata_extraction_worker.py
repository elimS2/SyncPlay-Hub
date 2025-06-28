#!/usr/bin/env python3
"""
Metadata Extraction Worker

Воркер для извлечения метаданных YouTube каналов через систему Job Queue.
Интегрируется с существующим extract_channel_metadata.py.
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


class MetadataExtractionWorker(JobWorker):
    """Воркер для извлечения метаданных YouTube каналов."""
    
    def __init__(self):
        super().__init__("metadata_extraction_worker")
        self.supported_types = [
            JobType.METADATA_EXTRACTION,
            JobType.CHANNEL_METADATA_UPDATE,
            JobType.PLAYLIST_METADATA_UPDATE
        ]
    
    def get_supported_job_types(self) -> List[JobType]:
        """Возвращает поддерживаемые типы задач."""
        return self.supported_types
    
    def execute_job(self, job: Job) -> bool:
        """
        Выполняет извлечение метаданных.
        
        Ожидаемые параметры в job.job_data:
        - channel_url: URL канала для анализа
        - channel_id: ID канала в базе данных (optional, для обновления)
        - extract_type: 'channel' или 'playlist' (default: 'channel')
        - force_update: принудительное обновление существующих метаданных
        - max_entries: максимальное количество видео для анализа (optional)
        
        Returns:
            True если извлечение успешно, False если нет
        """
        try:
            # Извлекаем параметры из job data
            channel_url = job.job_data.get('channel_url')
            channel_id = job.job_data.get('channel_id')
            extract_type = job.job_data.get('extract_type', 'channel')
            force_update = job.job_data.get('force_update', False)
            max_entries = job.job_data.get('max_entries')
            
            if not channel_url:
                raise ValueError("channel_url is required")
            
            print(f"Starting metadata extraction for: {channel_url}")
            print(f"Channel ID: {channel_id}, Type: {extract_type}")
            print(f"Force update: {force_update}, Max entries: {max_entries}")
            
            # Определяем рабочую директорию (корень проекта)
            project_root = Path(__file__).parent.parent.parent
            
            # Загружаем конфигурацию из .env
            config = self._load_config(project_root)
            
            # Определяем путь к скрипту
            script_path = project_root / 'scripts' / 'extract_channel_metadata.py'
            if not script_path.exists():
                # Fallback к корневой папке
                script_path = project_root / 'extract_channel_metadata.py'
            
            if not script_path.exists():
                raise FileNotFoundError("extract_channel_metadata.py not found")
            
            # Строим команду
            cmd = [
                sys.executable,
                str(script_path),
                channel_url
            ]
            
            # Добавляем опциональные параметры
            if config.get('DB_PATH'):
                cmd.extend(['--db-path', config['DB_PATH']])
            
            if force_update:
                cmd.append('--force-update')
            
            if max_entries:
                cmd.extend(['--max-entries', str(max_entries)])
            
            # Добавляем verbose для детального логирования
            cmd.append('--verbose')
            
            print(f"Executing command: {' '.join(cmd)}")
            
            # Запускаем извлечение метаданных с захватом вывода
            result = subprocess.run(
                cmd,
                cwd=str(project_root),
                capture_output=True,
                text=True,
                timeout=1800  # 30 минут timeout для метаданных
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
                print("Metadata extraction completed successfully")
                
                # Обновляем timestamp последнего обновления метаданных
                if channel_id:
                    self._update_metadata_timestamp(channel_id, config.get('DB_PATH'))
                
                # Парсим количество обработанных видео из вывода
                videos_processed = self._parse_videos_count(result.stdout)
                if videos_processed:
                    print(f"Processed {videos_processed} videos")
                
                return True
            else:
                print(f"Metadata extraction failed with exit code {result.returncode}")
                if result.stderr:
                    print(f"Error output: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            print("Metadata extraction timed out (30 minutes)")
            return False
        except Exception as e:
            print(f"Exception during metadata extraction: {e}")
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
    
    def _update_metadata_timestamp(self, channel_id: int, db_path: str = None):
        """Обновляет timestamp последнего обновления метаданных канала."""
        try:
            if not db_path:
                # Fallback к default пути
                project_root = Path(__file__).parent.parent.parent
                db_path = str(project_root / 'tracks.db')
            
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                
                # Обновляем metadata_last_updated поле
                cursor.execute("""
                    UPDATE channels 
                    SET metadata_last_updated = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (channel_id,))
                
                if cursor.rowcount > 0:
                    print(f"Updated metadata timestamp for channel {channel_id}")
                else:
                    print(f"Warning: Channel {channel_id} not found for timestamp update")
                
                conn.commit()
                
        except Exception as e:
            print(f"Warning: Failed to update metadata timestamp: {e}")
    
    def _parse_videos_count(self, output: str) -> int:
        """Парсит количество обработанных видео из вывода скрипта."""
        try:
            for line in output.split('\n'):
                # Ищем строки типа "Loaded X videos metadata for channel"
                if 'videos metadata for channel' in line:
                    words = line.split()
                    for i, word in enumerate(words):
                        if word == 'Loaded' and i + 1 < len(words):
                            try:
                                return int(words[i + 1])
                            except ValueError:
                                continue
                
                # Или "Processing X entries"
                if 'Processing' in line and 'entries' in line:
                    words = line.split()
                    for i, word in enumerate(words):
                        if word == 'Processing' and i + 1 < len(words):
                            try:
                                return int(words[i + 1])
                            except ValueError:
                                continue
            
            return 0
            
        except Exception:
            return 0
    
    def get_worker_info(self) -> dict:
        """Информация о воркере для мониторинга."""
        info = super().get_worker_info()
        info.update({
            'description': 'Extracts YouTube channel/playlist metadata using yt-dlp',
            'max_concurrent_jobs': 2,  # Метаданные можем извлекать параллельно
            'average_duration': '5-15 minutes',
            'supported_features': [
                'channel_metadata',
                'playlist_metadata',
                'force_update',
                'max_entries_limit',
                'database_timestamp_update'
            ]
        })
        return info 
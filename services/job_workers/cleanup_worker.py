#!/usr/bin/env python3
"""
Cleanup Worker

Воркер для очистки старых файлов, логов и базы данных через систему Job Queue.
Выполняет различные типы очистки в зависимости от типа задачи.
"""

import os
import sys
import shutil
import sqlite3
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime, timedelta
import glob

# Добавляем корневую папку в путь для импортов
sys.path.append(str(Path(__file__).parent.parent.parent))

from services.job_types import JobWorker, Job, JobType


class CleanupWorker(JobWorker):
    """Воркер для различных задач очистки."""
    
    def __init__(self):
        super().__init__("cleanup_worker")
        self.supported_types = [
            JobType.FILE_CLEANUP,
            JobType.DATABASE_CLEANUP,
            JobType.LOG_CLEANUP
        ]
    
    def get_supported_job_types(self) -> List[JobType]:
        """Возвращает поддерживаемые типы задач."""
        return self.supported_types
    
    def execute_job(self, job: Job) -> bool:
        """
        Выполняет задачу очистки.
        
        Ожидаемые параметры в job.job_data зависят от типа задачи:
        
        FILE_CLEANUP:
        - cleanup_type: 'orphaned_files', 'old_downloads', 'temp_files'
        - days_old: количество дней для определения старых файлов (default: 30)
        - dry_run: только показать что будет удалено (default: False)
        - target_directories: список директорий для очистки (optional)
        
        DATABASE_CLEANUP:
        - cleanup_type: 'old_history', 'orphaned_records', 'temp_data'
        - days_old: количество дней для очистки истории (default: 90)
        - dry_run: только показать что будет удалено (default: False)
        
        LOG_CLEANUP:
        - cleanup_type: 'old_logs', 'job_logs', 'archive_logs'
        - days_old: количество дней для сохранения логов (default: 30)
        - dry_run: только показать что будет удалено (default: False)
        
        Returns:
            True если очистка успешна, False если нет
        """
        try:
            cleanup_type = job.job_data.get('cleanup_type')
            days_old = job.job_data.get('days_old', 30)
            dry_run = job.job_data.get('dry_run', False)
            
            if not cleanup_type:
                raise ValueError("cleanup_type is required")
            
            print(f"Starting cleanup: {job.job_type.value}")
            print(f"Cleanup type: {cleanup_type}")
            print(f"Days old: {days_old}, Dry run: {dry_run}")
            
            # Определяем рабочую директорию (корень проекта)
            project_root = Path(__file__).parent.parent.parent
            
            # Загружаем конфигурацию из .env
            config = self._load_config(project_root)
            
            # Выполняем соответствующий тип очистки
            if job.job_type == JobType.FILE_CLEANUP:
                success = self._cleanup_files(cleanup_type, days_old, dry_run, config, job.job_data)
            elif job.job_type == JobType.DATABASE_CLEANUP:
                success = self._cleanup_database(cleanup_type, days_old, dry_run, config)
            elif job.job_type == JobType.LOG_CLEANUP:
                success = self._cleanup_logs(cleanup_type, days_old, dry_run, config)
            else:
                raise ValueError(f"Unsupported job type: {job.job_type}")
            
            if success:
                print("Cleanup completed successfully")
            else:
                print("Cleanup completed with errors")
            
            return success
            
        except Exception as e:
            print(f"Exception during cleanup: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _cleanup_files(self, cleanup_type: str, days_old: int, dry_run: bool, 
                      config: Dict[str, str], job_data: Dict[str, Any]) -> bool:
        """Выполняет очистку файлов."""
        try:
            cutoff_time = datetime.now() - timedelta(days=days_old)
            removed_count = 0
            total_size = 0
            
            if cleanup_type == 'orphaned_files':
                # Удаляем файлы которых нет в базе данных
                removed_count, total_size = self._cleanup_orphaned_files(
                    config, cutoff_time, dry_run
                )
            
            elif cleanup_type == 'old_downloads':
                # Удаляем старые загруженные файлы
                target_dirs = job_data.get('target_directories', [])
                removed_count, total_size = self._cleanup_old_downloads(
                    config, cutoff_time, dry_run, target_dirs
                )
            
            elif cleanup_type == 'temp_files':
                # Удаляем временные файлы
                removed_count, total_size = self._cleanup_temp_files(
                    config, cutoff_time, dry_run
                )
            
            else:
                raise ValueError(f"Unknown file cleanup type: {cleanup_type}")
            
            print(f"File cleanup results: {removed_count} files, {total_size / (1024*1024):.1f} MB")
            return True
            
        except Exception as e:
            print(f"File cleanup error: {e}")
            return False
    
    def _cleanup_database(self, cleanup_type: str, days_old: int, dry_run: bool,
                         config: Dict[str, str]) -> bool:
        """Выполняет очистку базы данных."""
        try:
            db_path = config.get('DB_PATH')
            if not db_path:
                project_root = Path(__file__).parent.parent.parent
                db_path = str(project_root / 'tracks.db')
            
            cutoff_date = datetime.now() - timedelta(days=days_old)
            removed_count = 0
            
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                
                if cleanup_type == 'old_history':
                    # Удаляем старую историю воспроизведения
                    if dry_run:
                        cursor.execute("""
                            SELECT COUNT(*) FROM play_history 
                            WHERE timestamp < ?
                        """, (cutoff_date.isoformat(),))
                        removed_count = cursor.fetchone()[0]
                    else:
                        cursor.execute("""
                            DELETE FROM play_history 
                            WHERE timestamp < ?
                        """, (cutoff_date.isoformat(),))
                        removed_count = cursor.rowcount
                        conn.commit()
                
                elif cleanup_type == 'orphaned_records':
                    # Удаляем записи треков которых нет на диске
                    removed_count = self._cleanup_orphaned_db_records(cursor, config, dry_run)
                    if not dry_run:
                        conn.commit()
                
                elif cleanup_type == 'temp_data':
                    # Удаляем временные данные и кэши
                    removed_count = self._cleanup_temp_db_data(cursor, cutoff_date, dry_run)
                    if not dry_run:
                        conn.commit()
                
                else:
                    raise ValueError(f"Unknown database cleanup type: {cleanup_type}")
            
            print(f"Database cleanup results: {removed_count} records removed")
            return True
            
        except Exception as e:
            print(f"Database cleanup error: {e}")
            return False
    
    def _cleanup_logs(self, cleanup_type: str, days_old: int, dry_run: bool,
                     config: Dict[str, str]) -> bool:
        """Выполняет очистку логов."""
        try:
            # Определяем директорию логов
            log_dir = config.get('LOG_DIR')
            if not log_dir:
                project_root = Path(__file__).parent.parent.parent
                log_dir = str(project_root / 'logs')
            
            log_path = Path(log_dir)
            cutoff_time = datetime.now() - timedelta(days=days_old)
            removed_count = 0
            total_size = 0
            
            if cleanup_type == 'old_logs':
                # Удаляем старые основные логи
                removed_count, total_size = self._cleanup_old_log_files(
                    log_path, cutoff_time, dry_run, ['*.log', '*.log.*']
                )
            
            elif cleanup_type == 'job_logs':
                # Удаляем старые логи задач
                job_logs_dir = log_path / 'jobs'
                if job_logs_dir.exists():
                    removed_count, total_size = self._cleanup_job_log_dirs(
                        job_logs_dir, cutoff_time, dry_run
                    )
            
            elif cleanup_type == 'archive_logs':
                # Удаляем архивные логи
                removed_count, total_size = self._cleanup_old_log_files(
                    log_path, cutoff_time, dry_run, ['*.log.gz', '*.log.bz2', 'archive_*']
                )
            
            else:
                raise ValueError(f"Unknown log cleanup type: {cleanup_type}")
            
            print(f"Log cleanup results: {removed_count} files, {total_size / (1024*1024):.1f} MB")
            return True
            
        except Exception as e:
            print(f"Log cleanup error: {e}")
            return False
    
    def _cleanup_orphaned_files(self, config: Dict[str, str], cutoff_time: datetime, 
                               dry_run: bool) -> tuple[int, int]:
        """Удаляет файлы медиа которых нет в базе данных."""
        # TODO: Реализовать логику сравнения файлов с базой данных
        # Пока возвращаем заглушку
        print("Orphaned files cleanup not yet implemented")
        return 0, 0
    
    def _cleanup_old_downloads(self, config: Dict[str, str], cutoff_time: datetime,
                              dry_run: bool, target_dirs: List[str]) -> tuple[int, int]:
        """Удаляет старые загруженные файлы."""
        removed_count = 0
        total_size = 0
        
        # Определяем директории для проверки
        if not target_dirs:
            root_dir = config.get('ROOT_DIR')
            if root_dir:
                playlists_dir = Path(root_dir) / 'Playlists'
                if playlists_dir.exists():
                    target_dirs = [str(playlists_dir)]
        
        for dir_path in target_dirs:
            dir_path = Path(dir_path)
            if not dir_path.exists():
                continue
                
            for file_path in dir_path.rglob('*'):
                if file_path.is_file():
                    file_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                    if file_time < cutoff_time:
                        file_size = file_path.stat().st_size
                        
                        if dry_run:
                            print(f"Would remove: {file_path} ({file_size} bytes)")
                        else:
                            try:
                                file_path.unlink()
                                print(f"Removed: {file_path}")
                            except Exception as e:
                                print(f"Failed to remove {file_path}: {e}")
                                continue
                        
                        removed_count += 1
                        total_size += file_size
        
        return removed_count, total_size
    
    def _cleanup_temp_files(self, config: Dict[str, str], cutoff_time: datetime,
                           dry_run: bool) -> tuple[int, int]:
        """Удаляет временные файлы."""
        removed_count = 0
        total_size = 0
        
        # Обычные места для временных файлов
        temp_patterns = [
            '*.tmp',
            '*.temp',
            '*.part',
            '*.download',
            '*.ytdl',
            '__pycache__',
            '*.pyc'
        ]
        
        # Ищем во всех папках проекта
        project_root = Path(__file__).parent.parent.parent
        
        for pattern in temp_patterns:
            for file_path in project_root.rglob(pattern):
                if file_path.is_file():
                    file_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                    if file_time < cutoff_time:
                        file_size = file_path.stat().st_size
                        
                        if dry_run:
                            print(f"Would remove: {file_path} ({file_size} bytes)")
                        else:
                            try:
                                file_path.unlink()
                                print(f"Removed: {file_path}")
                            except Exception as e:
                                print(f"Failed to remove {file_path}: {e}")
                                continue
                        
                        removed_count += 1
                        total_size += file_size
                
                elif file_path.is_dir() and pattern == '__pycache__':
                    if dry_run:
                        print(f"Would remove directory: {file_path}")
                    else:
                        try:
                            shutil.rmtree(file_path)
                            print(f"Removed directory: {file_path}")
                        except Exception as e:
                            print(f"Failed to remove directory {file_path}: {e}")
                            continue
                    
                    removed_count += 1
        
        return removed_count, total_size
    
    def _cleanup_orphaned_db_records(self, cursor, config: Dict[str, str], dry_run: bool) -> int:
        """Удаляет записи треков которых нет на диске."""
        # TODO: Реализовать проверку существования файлов для записей в tracks
        print("Orphaned database records cleanup not yet implemented")
        return 0
    
    def _cleanup_temp_db_data(self, cursor, cutoff_date: datetime, dry_run: bool) -> int:
        """Удаляет временные данные из базы."""
        removed_count = 0
        
        # Примеры временных данных для очистки
        # (здесь можно добавить специфичные для проекта таблицы)
        
        # Очистка старых логов ошибок если есть такая таблица
        try:
            if dry_run:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='error_logs'")
                if cursor.fetchone():
                    cursor.execute("SELECT COUNT(*) FROM error_logs WHERE timestamp < ?", (cutoff_date.isoformat(),))
                    count = cursor.fetchone()[0]
                    removed_count += count
            else:
                cursor.execute("DELETE FROM error_logs WHERE timestamp < ?", (cutoff_date.isoformat(),))
                removed_count += cursor.rowcount
        except sqlite3.OperationalError:
            pass  # Таблица не существует
        
        return removed_count
    
    def _cleanup_old_log_files(self, log_path: Path, cutoff_time: datetime,
                              dry_run: bool, patterns: List[str]) -> tuple[int, int]:
        """Удаляет старые лог файлы по паттернам."""
        removed_count = 0
        total_size = 0
        
        for pattern in patterns:
            for file_path in log_path.glob(pattern):
                if file_path.is_file():
                    file_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                    if file_time < cutoff_time:
                        file_size = file_path.stat().st_size
                        
                        if dry_run:
                            print(f"Would remove: {file_path} ({file_size} bytes)")
                        else:
                            try:
                                file_path.unlink()
                                print(f"Removed: {file_path}")
                            except Exception as e:
                                print(f"Failed to remove {file_path}: {e}")
                                continue
                        
                        removed_count += 1
                        total_size += file_size
        
        return removed_count, total_size
    
    def _cleanup_job_log_dirs(self, jobs_dir: Path, cutoff_time: datetime,
                             dry_run: bool) -> tuple[int, int]:
        """Удаляет старые директории логов задач."""
        removed_count = 0
        total_size = 0
        
        for job_dir in jobs_dir.iterdir():
            if job_dir.is_dir() and job_dir.name.startswith('job_'):
                dir_time = datetime.fromtimestamp(job_dir.stat().st_mtime)
                if dir_time < cutoff_time:
                    # Считаем размер директории
                    dir_size = sum(f.stat().st_size for f in job_dir.rglob('*') if f.is_file())
                    
                    if dry_run:
                        print(f"Would remove directory: {job_dir} ({dir_size} bytes)")
                    else:
                        try:
                            shutil.rmtree(job_dir)
                            print(f"Removed directory: {job_dir}")
                        except Exception as e:
                            print(f"Failed to remove directory {job_dir}: {e}")
                            continue
                    
                    removed_count += 1
                    total_size += dir_size
        
        return removed_count, total_size
    
    def _load_config(self, project_root: Path) -> Dict[str, str]:
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
    
    def get_worker_info(self) -> Dict[str, Any]:
        """Информация о воркере для мониторинга."""
        info = super().get_worker_info()
        info.update({
            'description': 'Performs various cleanup tasks (files, database, logs)',
            'max_concurrent_jobs': 1,  # Cleanup задачи выполняем последовательно
            'average_duration': '5-30 minutes',
            'supported_features': [
                'file_cleanup',
                'database_cleanup',
                'log_cleanup',
                'dry_run_mode',
                'orphaned_detection',
                'size_reporting'
            ]
        })
        return info 
#!/usr/bin/env python3
"""
Job Queue Service

Основной сервис для управления очередью задач в YouTube Downloader.
Обеспечивает создание, планирование, выполнение и мониторинг задач.
"""

import sqlite3
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Any
from pathlib import Path
import json
import queue
import traceback

from .job_types import (
    Job, JobType, JobStatus, JobPriority, JobData, JobWorker, JobFailureType,
    create_job_with_defaults
)


class JobQueueService:
    """Основной сервис управления очередью задач."""
    
    def __init__(self, db_path: str = None, max_workers: int = 3):
        # Database setup
        if db_path is None:
            # Используем .env файл для определения пути к базе
            project_root = Path(__file__).parent.parent
            env_path = project_root / '.env'
            
            if env_path.exists():
                try:
                    with open(env_path, 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip().lstrip('\ufeff')
                            if line.startswith('DB_PATH='):
                                db_path = line.split('=', 1)[1].strip()
                                break
                except Exception:
                    pass
            
            if not db_path:
                db_path = str(project_root / 'tracks.db')
        
        self.db_path = db_path
        self.max_workers = max_workers
        
        # Threading
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._worker_threads: List[threading.Thread] = []
        
        # Worker management
        self._workers: Dict[str, JobWorker] = {}
        self._worker_queue = queue.Queue()
        
        # Job monitoring
        self._running_jobs: Dict[int, Job] = {}
        self._job_callbacks: Dict[int, List[Callable]] = {}
        
        # Statistics
        self._stats = {
            'total_jobs': 0,
            'completed_jobs': 0,
            'failed_jobs': 0,
            'start_time': datetime.utcnow()
        }
        
        # Инициализация
        self._init_database()
        self._start_worker_threads()
    
    def _init_database(self):
        """Инициализация базы данных для работы с очередью."""
        with sqlite3.connect(self.db_path) as conn:
            # Проверяем что таблица job_queue существует
            cursor = conn.cursor()
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='job_queue'
            """)
            
            if not cursor.fetchone():
                # Создаем таблицу если она не существует
                cursor.execute("""
                    CREATE TABLE job_queue (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        job_type TEXT NOT NULL,
                        job_data TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'pending',
                        priority INTEGER NOT NULL DEFAULT 5,
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        started_at TIMESTAMP,
                        completed_at TIMESTAMP,
                        log_file_path TEXT,
                        error_message TEXT,
                        retry_count INTEGER NOT NULL DEFAULT 0,
                        max_retries INTEGER NOT NULL DEFAULT 3,
                        worker_id TEXT,
                        timeout_seconds INTEGER,
                        parent_job_id INTEGER,
                        FOREIGN KEY (parent_job_id) REFERENCES job_queue(id)
                    )
                """)
                
                # Создаем индексы для производительности
                cursor.execute("CREATE INDEX idx_job_queue_status ON job_queue(status)")
                cursor.execute("CREATE INDEX idx_job_queue_priority ON job_queue(priority DESC)")
                cursor.execute("CREATE INDEX idx_job_queue_created_at ON job_queue(created_at)")
                cursor.execute("CREATE INDEX idx_job_queue_type ON job_queue(job_type)")
                
                conn.commit()
    
    def _start_worker_threads(self):
        """Запуск рабочих потоков."""
        for i in range(self.max_workers):
            worker_thread = threading.Thread(
                target=self._worker_loop,
                name=f"JobWorker-{i+1}",
                daemon=True
            )
            worker_thread.start()
            self._worker_threads.append(worker_thread)
    
    def _worker_loop(self):
        """Основной цикл рабочего потока с zombie detection."""
        worker_name = threading.current_thread().name
        last_zombie_check = time.time()
        zombie_check_interval = 300  # Проверяем zombie каждые 5 минут
        
        while not self._stop_event.is_set():
            try:
                # Периодическая проверка zombie задач
                current_time = time.time()
                if current_time - last_zombie_check > zombie_check_interval:
                    self._cleanup_zombie_jobs()
                    last_zombie_check = current_time
                
                # Получаем следующую задачу из очереди
                job = self._get_next_job()
                
                if job is None:
                    # Нет задач, ждем немного
                    time.sleep(1)
                    continue
                
                # Выполняем задачу
                self._execute_job(job, worker_name)
                
            except Exception as e:
                print(f"Worker {worker_name} error: {e}")
                traceback.print_exc()
                time.sleep(5)  # Пауза при ошибке
    
    def _get_next_job(self) -> Optional[Job]:
        """Получает следующую задачу для выполнения."""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Ищем задачи готовые к выполнению с учетом retry timing
                current_time = datetime.utcnow().isoformat()
                cursor.execute("""
                    SELECT id, job_type, job_data, status, priority, created_at,
                           log_file_path, error_message, retry_count, max_retries,
                           timeout_seconds, parent_job_id, next_retry_at, failure_type
                    FROM job_queue 
                    WHERE (
                        status = 'pending' OR 
                        (status = 'retrying' AND (next_retry_at IS NULL OR next_retry_at <= ?))
                    )
                    ORDER BY priority DESC, created_at ASC
                    LIMIT 1
                """, (current_time,))
                
                row = cursor.fetchone()
                if not row:
                    return None
                
                # Создаем объект Job
                job = Job(
                    job_type=JobType(row[1]),
                    job_data=JobData.from_json(row[2]),
                    priority=JobPriority(row[4])
                )
                
                job.id = row[0]
                job.status = JobStatus(row[3])
                job.created_at = datetime.fromisoformat(row[5])
                job.log_file_path = row[6]
                job.error_message = row[7]
                job.retry_count = row[8]
                job.max_retries = row[9]
                job.timeout_seconds = row[10]
                job.parent_job_id = row[11]
                
                # Новые поля для enhanced error handling
                if row[12]:  # next_retry_at
                    job.next_retry_at = datetime.fromisoformat(row[12])
                if row[13]:  # failure_type
                    job.failure_type = JobFailureType(row[13])
                
                # Помечаем задачу как выполняющуюся
                cursor.execute("""
                    UPDATE job_queue 
                    SET status = 'running', started_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (job.id,))
                conn.commit()
                
                job.status = JobStatus.RUNNING
                job.started_at = datetime.utcnow()
                
                return job
    
    def _execute_job(self, job: Job, worker_name: str):
        """Выполняет задачу."""
        job.worker_id = worker_name
        
        success = False
        error_message = None
        
        try:
            with self._lock:
                self._running_jobs[job.id] = job
            
            # Найдем подходящего воркера
            worker = self._find_worker_for_job(job)
            
            if worker is None:
                raise Exception(f"No worker available for job type {job.job_type.value}")
            
            # Выполняем задачу с встроенным логированием
            success = worker.execute_job_with_logging(job)
                
        except Exception as e:
            success = False
            error_message = str(e)
            # Если у job есть логгер, используем его, иначе печатаем в консоль
            if job.get_logger():
                job.log_exception(e, "job execution in JobQueueService")
            else:
                print(f"Job {job.id} execution error: {e}")
                
        finally:
            # Обновляем статус в базе
            with self._lock:
                if job.id in self._running_jobs:
                    del self._running_jobs[job.id]
                
                self._update_job_completion(job, success, error_message)
            
            # Вызываем callbacks
            self._call_job_callbacks(job.id, success, error_message)
    
    def _find_worker_for_job(self, job: Job) -> Optional[JobWorker]:
        """Находит воркера способного выполнить задачу."""
        for worker in self._workers.values():
            if worker.can_handle_job(job):
                return worker
        return None
    
    def _update_job_completion(self, job: Job, success: bool, error_message: Optional[str]):
        """Обновляет статус завершенной задачи с enhanced retry logic."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            if success:
                new_status = JobStatus.COMPLETED
                self._stats['completed_jobs'] += 1
                
                cursor.execute("""
                    UPDATE job_queue 
                    SET status = ?, completed_at = CURRENT_TIMESTAMP, 
                        log_file_path = ?
                    WHERE id = ?
                """, (new_status.value, job.log_file_path, job.id))
                
            else:
                # Enhanced retry logic с exponential backoff
                if job.can_retry():
                    # Планируем retry с exponential backoff
                    if job.schedule_retry():
                        new_status = JobStatus.RETRYING
                        
                        cursor.execute("""
                            UPDATE job_queue 
                            SET status = ?, retry_count = ?, error_message = ?, 
                                failure_type = ?, next_retry_at = ?, log_file_path = ?
                            WHERE id = ?
                        """, (
                            new_status.value, 
                            job.retry_count, 
                            error_message,
                            job.failure_type.value if job.failure_type else None,
                            job.next_retry_at.isoformat() if job.next_retry_at else None,
                            job.log_file_path,
                            job.id
                        ))
                    else:
                        # Если schedule_retry вернул False, перемещаем в dead letter
                        job.move_to_dead_letter("Failed to schedule retry")
                        new_status = JobStatus.DEAD_LETTER
                        self._stats['failed_jobs'] += 1
                        
                        cursor.execute("""
                            UPDATE job_queue 
                            SET status = ?, completed_at = CURRENT_TIMESTAMP, 
                                error_message = ?, failure_type = ?, log_file_path = ?,
                                dead_letter_reason = ?, moved_to_dead_letter_at = ?
                            WHERE id = ?
                        """, (
                            new_status.value, 
                            error_message, 
                            job.failure_type.value if job.failure_type else None,
                            job.log_file_path,
                            job.dead_letter_reason,
                            job.moved_to_dead_letter_at.isoformat() if job.moved_to_dead_letter_at else None,
                            job.id
                        ))
                else:
                    # Максимальное количество попыток исчерпано
                    if job.retry_count >= job.max_retries:
                        job.move_to_dead_letter(f"Max retries ({job.max_retries}) exceeded")
                        new_status = JobStatus.DEAD_LETTER
                    else:
                        new_status = JobStatus.FAILED
                    
                    self._stats['failed_jobs'] += 1
                    
                    cursor.execute("""
                        UPDATE job_queue 
                        SET status = ?, completed_at = CURRENT_TIMESTAMP, 
                            error_message = ?, failure_type = ?, log_file_path = ?,
                            dead_letter_reason = ?, moved_to_dead_letter_at = ?
                        WHERE id = ?
                    """, (
                        new_status.value, 
                        error_message, 
                        job.failure_type.value if job.failure_type else None,
                        job.log_file_path,
                        job.dead_letter_reason,
                        job.moved_to_dead_letter_at.isoformat() if job.moved_to_dead_letter_at else None,
                        job.id
                    ))
            
            conn.commit()
            job.status = new_status
    
    def _call_job_callbacks(self, job_id: int, success: bool, error_message: Optional[str]):
        """Вызывает зарегистрированные callbacks для задачи."""
        callbacks = self._job_callbacks.get(job_id, [])
        
        for callback in callbacks:
            try:
                callback(job_id, success, error_message)
            except Exception as e:
                print(f"Callback error for job {job_id}: {e}")
        
        # Очищаем callbacks после выполнения
        if job_id in self._job_callbacks:
            del self._job_callbacks[job_id]
    
    def _cleanup_zombie_jobs(self):
        """Очищает zombie задачи."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Находим все running задачи
            cursor.execute("""
                SELECT id, job_type, job_data, status, priority, created_at,
                       started_at, log_file_path, error_message, retry_count, 
                       max_retries, timeout_seconds, parent_job_id,
                       failure_type, next_retry_at, dead_letter_reason, moved_to_dead_letter_at
                FROM job_queue 
                WHERE status = 'running'
            """)
            
            zombie_count = 0
            for row in cursor.fetchall():
                job = Job(
                    job_type=JobType(row[1]),
                    job_data=JobData.from_json(row[2]),
                    priority=JobPriority(row[4])
                )
                
                job.id = row[0]
                job.status = JobStatus(row[3])
                job.created_at = datetime.fromisoformat(row[5]) if row[5] else None
                job.started_at = datetime.fromisoformat(row[6]) if row[6] else None
                job.log_file_path = row[7]
                job.error_message = row[8]
                job.retry_count = row[9]
                job.max_retries = row[10]
                job.timeout_seconds = row[11]
                job.parent_job_id = row[12]
                
                # Новые поля Phase 6
                if row[13]:  # failure_type
                    job.failure_type = JobFailureType(row[13])
                if row[14]:  # next_retry_at
                    job.next_retry_at = datetime.fromisoformat(row[14])
                job.dead_letter_reason = row[15]  # dead_letter_reason
                if row[16]:  # moved_to_dead_letter_at
                    job.moved_to_dead_letter_at = datetime.fromisoformat(row[16])
                
                # Проверяем является ли задача zombie
                if job.is_zombie():
                    job.mark_as_zombie(f"Zombie detected during cleanup after {job.get_elapsed_time():.0f}s")
                    
                    # Обновляем в базе
                    cursor.execute("""
                        UPDATE job_queue 
                        SET status = ?, error_message = ?, failure_type = ?
                        WHERE id = ?
                    """, (
                        JobStatus.ZOMBIE.value,
                        job.error_message,
                        JobFailureType.TIMEOUT_ERROR.value,
                        job.id
                    ))
                    
                    zombie_count += 1
            
            if zombie_count > 0:
                conn.commit()
                print(f"Marked {zombie_count} zombie jobs during cleanup")
    
    def force_kill_zombie_jobs(self):
        """Принудительно завершает все zombie задачи."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Находим все zombie задачи
            cursor.execute("""
                SELECT id FROM job_queue WHERE status = 'zombie'
            """)
            
            zombie_ids = [row[0] for row in cursor.fetchall()]
            
            if zombie_ids:
                cursor.execute("""
                    UPDATE job_queue 
                    SET status = 'failed', completed_at = CURRENT_TIMESTAMP,
                        error_message = 'Zombie job forcefully terminated'
                    WHERE status = 'zombie'
                """)
                
                conn.commit()
                print(f"Force killed {len(zombie_ids)} zombie jobs")
                return len(zombie_ids)
            
            return 0
    
    # Public API методы
    
    def register_worker(self, worker: JobWorker):
        """Регистрирует воркера для выполнения задач."""
        with self._lock:
            self._workers[worker.worker_id] = worker
    
    def unregister_worker(self, worker_id: str):
        """Удаляет воркера из системы."""
        with self._lock:
            if worker_id in self._workers:
                del self._workers[worker_id]
    
    def add_job(self, job: Job, callback: Optional[Callable] = None) -> int:
        """
        Добавляет задачу в очередь.
        
        Returns:
            ID созданной задачи
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO job_queue (
                    job_type, job_data, status, priority, 
                    max_retries, timeout_seconds, parent_job_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                job.job_type.value,
                job.job_data.to_json(),
                job.status.value,
                job.priority.value,
                job.max_retries,
                job.timeout_seconds,
                job.parent_job_id
            ))
            
            job_id = cursor.lastrowid
            conn.commit()
            
            job.id = job_id
            
            # Регистрируем callback если передан
            if callback:
                with self._lock:
                    if job_id not in self._job_callbacks:
                        self._job_callbacks[job_id] = []
                    self._job_callbacks[job_id].append(callback)
            
            self._stats['total_jobs'] += 1
            
            return job_id
    
    def create_and_add_job(self, job_type: JobType, callback: Optional[Callable] = None, **kwargs) -> int:
        """Создает и добавляет задачу с дефолтными настройками."""
        job = create_job_with_defaults(job_type, **kwargs)
        return self.add_job(job, callback)
    
    def get_job(self, job_id: int) -> Optional[Job]:
        """Получает информацию о задаче."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id, job_type, job_data, status, priority, created_at,
                       started_at, completed_at, log_file_path, error_message,
                       retry_count, max_retries, worker_id, timeout_seconds, parent_job_id,
                       failure_type, next_retry_at, dead_letter_reason, moved_to_dead_letter_at
                FROM job_queue WHERE id = ?
            """, (job_id,))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            job = Job(
                job_type=JobType(row[1]),
                job_data=JobData.from_json(row[2]),
                priority=JobPriority(row[4])
            )
            
            job.id = row[0]
            job.status = JobStatus(row[3])
            job.created_at = datetime.fromisoformat(row[5]) if row[5] else None
            job.started_at = datetime.fromisoformat(row[6]) if row[6] else None
            job.completed_at = datetime.fromisoformat(row[7]) if row[7] else None
            job.log_file_path = row[8]
            job.error_message = row[9]
            job.retry_count = row[10]
            job.max_retries = row[11]
            job.worker_id = row[12]
            job.timeout_seconds = row[13]
            job.parent_job_id = row[14]
            
            # Новые поля Phase 6
            if row[15]:  # failure_type
                job.failure_type = JobFailureType(row[15])
            if row[16]:  # next_retry_at
                job.next_retry_at = datetime.fromisoformat(row[16])
            job.dead_letter_reason = row[17]  # dead_letter_reason
            if row[18]:  # moved_to_dead_letter_at
                job.moved_to_dead_letter_at = datetime.fromisoformat(row[18])
            
            return job
    
    def get_jobs(self, status: Optional[JobStatus] = None, job_type: Optional[JobType] = None, 
                 limit: int = 100) -> List[Job]:
        """Получает список задач с фильтрацией."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            query = """
                SELECT id, job_type, job_data, status, priority, created_at,
                       started_at, completed_at, log_file_path, error_message,
                       retry_count, max_retries, worker_id, timeout_seconds, parent_job_id,
                       failure_type, next_retry_at, dead_letter_reason, moved_to_dead_letter_at
                FROM job_queue
            """
            params = []
            conditions = []
            
            if status:
                conditions.append("status = ?")
                params.append(status.value)
            
            if job_type:
                conditions.append("job_type = ?")
                params.append(job_type.value)
            
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            
            jobs = []
            for row in cursor.fetchall():
                job = Job(
                    job_type=JobType(row[1]),
                    job_data=JobData.from_json(row[2]),
                    priority=JobPriority(row[4])
                )
                
                job.id = row[0]
                job.status = JobStatus(row[3])
                job.created_at = datetime.fromisoformat(row[5]) if row[5] else None
                job.started_at = datetime.fromisoformat(row[6]) if row[6] else None
                job.completed_at = datetime.fromisoformat(row[7]) if row[7] else None
                job.log_file_path = row[8]
                job.error_message = row[9]
                job.retry_count = row[10]
                job.max_retries = row[11]
                job.worker_id = row[12]
                job.timeout_seconds = row[13]
                job.parent_job_id = row[14]
                
                # Новые поля Phase 6
                if row[15]:  # failure_type
                    job.failure_type = JobFailureType(row[15])
                if row[16]:  # next_retry_at
                    job.next_retry_at = datetime.fromisoformat(row[16])
                job.dead_letter_reason = row[17]  # dead_letter_reason
                if row[18]:  # moved_to_dead_letter_at
                    job.moved_to_dead_letter_at = datetime.fromisoformat(row[18])
                
                jobs.append(job)
            
            return jobs
    
    def cancel_job(self, job_id: int) -> bool:
        """Отменяет задачу."""
        with self._lock:
            # Проверяем не выполняется ли задача сейчас
            if job_id in self._running_jobs:
                # TODO: Реализовать механизм остановки выполняющихся задач
                return False
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    UPDATE job_queue 
                    SET status = 'cancelled', completed_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND status IN ('pending', 'retrying')
                """, (job_id,))
                
                conn.commit()
                
                return cursor.rowcount > 0
    
    def get_queue_stats(self) -> Dict[str, Any]:
        """Получает статистику очереди."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Считаем задачи по статусам
            cursor.execute("""
                SELECT status, COUNT(*) 
                FROM job_queue 
                GROUP BY status
            """)
            
            status_counts = dict(cursor.fetchall())
            
            # Считаем задачи по типам
            cursor.execute("""
                SELECT job_type, COUNT(*) 
                FROM job_queue 
                GROUP BY job_type
            """)
            
            type_counts = dict(cursor.fetchall())
            
            # Информация о воркерах
            with self._lock:
                worker_info = [
                    worker.get_worker_info() 
                    for worker in self._workers.values()
                ]
                running_jobs_count = len(self._running_jobs)
        
        uptime = (datetime.utcnow() - self._stats['start_time']).total_seconds()
        
        return {
            'status_counts': status_counts,
            'type_counts': type_counts,
            'workers': {
                'total': len(self._workers),
                'busy': sum(1 for w in worker_info if w['status'] == 'busy'),
                'idle': sum(1 for w in worker_info if w['status'] == 'idle'),
                'info': worker_info
            },
            'running_jobs': running_jobs_count,
            'total_jobs': self._stats['total_jobs'],
            'completed_jobs': self._stats['completed_jobs'],
            'failed_jobs': self._stats['failed_jobs'],
            'uptime_seconds': uptime
        }
    
    def shutdown(self, graceful_timeout: int = 30):
        """Graceful shutdown сервиса с ожиданием завершения текущих задач."""
        print("Initiating graceful shutdown of Job Queue Service...")
        
        # Проверяем текущие выполняющиеся задачи
        running_jobs = list(self._running_jobs.values())
        if running_jobs:
            print(f"Waiting for {len(running_jobs)} running jobs to complete (timeout: {graceful_timeout}s)...")
            
            # Ждем завершения текущих задач с timeout
            start_time = time.time()
            while running_jobs and (time.time() - start_time) < graceful_timeout:
                time.sleep(1)
                # Обновляем список активных задач
                with self._lock:
                    running_jobs = list(self._running_jobs.values())
            
            # Если остались незавершенные задачи, помечаем их как cancelled
            if running_jobs:
                print(f"Force cancelling {len(running_jobs)} remaining jobs...")
                for job in running_jobs:
                    job.status = JobStatus.CANCELLED
                    job.error_message = "Cancelled due to service shutdown"
                    job.completed_at = datetime.utcnow()
                    
                    # Обновляем в базе
                    try:
                        with sqlite3.connect(self.db_path) as conn:
                            cursor = conn.cursor()
                            cursor.execute("""
                                UPDATE job_queue 
                                SET status = ?, completed_at = CURRENT_TIMESTAMP, 
                                    error_message = ?
                                WHERE id = ?
                            """, (JobStatus.CANCELLED.value, job.error_message, job.id))
                            conn.commit()
                    except Exception as e:
                        print(f"Error updating cancelled job {job.id}: {e}")
        
        # Финальная очистка zombie задач
        print("Performing final zombie cleanup...")
        self._cleanup_zombie_jobs()
        
        # Сигнализируем потокам о завершении
        self._stop_event.set()
        
        # Ждем завершения всех worker потоков
        print("Stopping worker threads...")
        for thread in self._worker_threads:
            thread.join(timeout=10)  # Увеличенный timeout для graceful shutdown
            if thread.is_alive():
                print(f"Warning: Worker thread {thread.name} did not shut down gracefully")
        
        # Очищаем данные
        with self._lock:
            self._workers.clear()
            self._running_jobs.clear()
            self._job_callbacks.clear()
        
        print("Job Queue Service shut down gracefully")


# Singleton instance
_job_queue_service: Optional[JobQueueService] = None


def get_job_queue_service(db_path: str = None, max_workers: int = 3) -> JobQueueService:
    """Получает singleton instance сервиса очереди."""
    global _job_queue_service
    
    if _job_queue_service is None:
        _job_queue_service = JobQueueService(db_path, max_workers)
    
    return _job_queue_service


def shutdown_job_queue_service():
    """Завершает работу singleton сервиса."""
    global _job_queue_service
    
    if _job_queue_service is not None:
        _job_queue_service.shutdown()
        _job_queue_service = None 
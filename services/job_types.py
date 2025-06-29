#!/usr/bin/env python3
"""
Job Types and Base Classes for Job Queue System

Определяет типы задач и базовую архитектуру для системы очереди задач.
"""

from enum import Enum
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from abc import ABC, abstractmethod
import json
import time
import random


# Delayed import to avoid circular dependencies
def _get_job_logger_class():
    """Lazy import of JobLogger to avoid circular dependencies."""
    try:
        from utils.job_logging import JobLogger
        return JobLogger
    except ImportError:
        return None


class JobType(Enum):
    """Типы задач в системе очереди."""
    
    # Задачи загрузки
    CHANNEL_DOWNLOAD = "channel_download"
    PLAYLIST_DOWNLOAD = "playlist_download" 
    SINGLE_VIDEO_DOWNLOAD = "single_video_download"
    
    # Задачи метаданных
    METADATA_EXTRACTION = "metadata_extraction"
    CHANNEL_METADATA_UPDATE = "channel_metadata_update"
    PLAYLIST_METADATA_UPDATE = "playlist_metadata_update"
    
    # Задачи обслуживания
    FILE_CLEANUP = "file_cleanup"
    DATABASE_CLEANUP = "database_cleanup"
    LOG_CLEANUP = "log_cleanup"
    METADATA_CLEANUP = "metadata_cleanup"
    
    # Задачи синхронизации
    CHANNEL_SYNC = "channel_sync"
    PLAYLIST_SYNC = "playlist_sync"
    LIBRARY_SCAN = "library_scan"
    
    # Системные задачи
    DATABASE_BACKUP = "database_backup"
    SYSTEM_MAINTENANCE = "system_maintenance"


class JobStatus(Enum):
    """Статусы выполнения задач."""
    
    PENDING = "pending"        # Ожидает выполнения
    RUNNING = "running"        # Выполняется
    COMPLETED = "completed"    # Успешно завершена
    FAILED = "failed"          # Завершена с ошибкой
    CANCELLED = "cancelled"    # Отменена пользователем
    TIMEOUT = "timeout"        # Превышено время ожидания
    RETRYING = "retrying"      # Ожидает повторной попытки
    DEAD_LETTER = "dead_letter"  # Перемещена в dead letter queue
    ZOMBIE = "zombie"          # Зависшая задача (требует принудительного завершения)


class JobPriority(Enum):
    """Приоритеты задач."""
    
    LOW = 0
    NORMAL = 5
    HIGH = 10
    URGENT = 15
    CRITICAL = 20


class JobFailureType(Enum):
    """Типы ошибок задач для определения retry стратегии."""
    
    UNKNOWN = "unknown"                    # Неизвестная ошибка
    NETWORK_ERROR = "network_error"        # Сетевая ошибка (retry с backoff)
    TIMEOUT_ERROR = "timeout_error"        # Превышение времени выполнения
    RESOURCE_ERROR = "resource_error"      # Недостаток ресурсов (память, диск)
    PERMISSION_ERROR = "permission_error"  # Ошибки прав доступа
    CONFIGURATION_ERROR = "config_error"   # Ошибки конфигурации (не retry)
    VALIDATION_ERROR = "validation_error"  # Ошибки валидации данных (не retry)
    SYSTEM_ERROR = "system_error"          # Системные ошибки
    WORKER_ERROR = "worker_error"          # Ошибки в логике воркера


class RetryConfig:
    """Конфигурация retry механизма."""
    
    def __init__(
        self,
        initial_delay: float = 1.0,        # Начальная задержка в секундах
        max_delay: float = 300.0,          # Максимальная задержка (5 минут)
        backoff_multiplier: float = 2.0,   # Множитель для exponential backoff
        jitter: bool = True,               # Добавлять случайную задержку
        max_jitter: float = 0.1            # Максимальный jitter (10% от delay)
    ):
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_multiplier = backoff_multiplier
        self.jitter = jitter
        self.max_jitter = max_jitter
    
    def calculate_delay(self, retry_count: int) -> float:
        """Вычисляет задержку для retry с exponential backoff."""
        if retry_count <= 0:
            return self.initial_delay
        
        # Exponential backoff
        delay = self.initial_delay * (self.backoff_multiplier ** (retry_count - 1))
        
        # Ограничиваем максимальной задержкой
        delay = min(delay, self.max_delay)
        
        # Добавляем jitter для предотвращения thundering herd
        if self.jitter and delay > 0:
            jitter_amount = delay * self.max_jitter
            delay += random.uniform(-jitter_amount, jitter_amount)
        
        return max(0, delay)
    
    def get_next_retry_time(self, retry_count: int) -> datetime:
        """Возвращает время следующей попытки retry."""
        delay = self.calculate_delay(retry_count)
        return datetime.utcnow() + timedelta(seconds=delay)


class JobData:
    """Контейнер для данных задачи с типизацией."""
    
    def __init__(self, **kwargs):
        self._data = kwargs
    
    def to_json(self) -> str:
        """Сериализация в JSON для хранения в базе."""
        return json.dumps(self._data, ensure_ascii=False, default=str)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'JobData':
        """Десериализация из JSON."""
        data = json.loads(json_str)
        return cls(**data)
    
    def get(self, key: str, default=None):
        """Получить значение по ключу."""
        return self._data.get(key, default)
    
    def set(self, key: str, value):
        """Установить значение."""
        self._data[key] = value
    
    def __getitem__(self, key):
        return self._data[key]
    
    def __setitem__(self, key, value):
        self._data[key] = value
    
    def __contains__(self, key):
        return key in self._data
    
    def keys(self):
        return self._data.keys()
    
    def items(self):
        return self._data.items()
    
    def __repr__(self):
        return f"JobData({self._data})"


class Job:
    """Представление задачи в системе очереди."""
    
    def __init__(
        self,
        job_type: JobType,
        job_data: JobData,
        priority: JobPriority = JobPriority.NORMAL,
        max_retries: int = 3,
        timeout_seconds: Optional[int] = None,
        parent_job_id: Optional[int] = None
    ):
        # Основные поля
        self.id: Optional[int] = None
        self.job_type = job_type
        self.job_data = job_data
        self.status = JobStatus.PENDING
        self.priority = priority
        
        # Временные метки
        self.created_at: Optional[datetime] = None
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        
        # Логирование и ошибки
        self.log_file_path: Optional[str] = None
        self.error_message: Optional[str] = None
        self.failure_type: Optional[JobFailureType] = None
        self.last_error_traceback: Optional[str] = None
        
        # Retry логика
        self.retry_count: int = 0
        self.max_retries = max_retries
        self.next_retry_at: Optional[datetime] = None
        self.retry_config = RetryConfig()
        
        # Dead letter queue
        self.dead_letter_reason: Optional[str] = None
        self.moved_to_dead_letter_at: Optional[datetime] = None
        
        # Выполнение
        self.worker_id: Optional[str] = None
        self.timeout_seconds = timeout_seconds
        
        # Зависимости
        self.parent_job_id = parent_job_id
        
        # Логгер задачи (создается при начале выполнения)
        self._job_logger: Optional['JobLogger'] = None
    
    def create_logger(self) -> Optional['JobLogger']:
        """Создает логгер для задачи."""
        if self.id is None:
            return None
            
        JobLoggerClass = _get_job_logger_class()
        if JobLoggerClass is None:
            return None
            
        try:
            self._job_logger = JobLoggerClass(self.id, self.job_type.value)
            self.log_file_path = self._job_logger.get_log_files()['directory']
            return self._job_logger
        except Exception as e:
            print(f"Failed to create job logger for job {self.id}: {e}")
            return None
    
    def get_logger(self) -> Optional['JobLogger']:
        """Возвращает логгер задачи."""
        return self._job_logger
    
    def log_info(self, message: str):
        """Логирует информационное сообщение."""
        if self._job_logger:
            self._job_logger.info(message)
    
    def log_error(self, message: str):
        """Логирует ошибку."""
        if self._job_logger:
            self._job_logger.error(message)
    
    def log_progress(self, message: str, percentage: Optional[float] = None):
        """Логирует прогресс выполнения."""
        if self._job_logger:
            self._job_logger.progress(message, percentage)
    
    def log_exception(self, exc: Exception, context: str = ""):
        """Логирует исключение."""
        if self._job_logger:
            self._job_logger.log_exception(exc, context)
    
    def finalize_logging(self, success: bool, error_message: Optional[str] = None):
        """Завершает логирование задачи."""
        if self._job_logger:
            self._job_logger.finalize(success, error_message)
            self._job_logger = None
    
    @classmethod
    def create(
        cls,
        job_type: JobType,
        priority: JobPriority = JobPriority.NORMAL,
        timeout_seconds: Optional[int] = None,
        parent_job_id: Optional[int] = None,
        **job_data_kwargs
    ) -> 'Job':
        """Удобный метод создания задачи."""
        job_data = JobData(**job_data_kwargs)
        return cls(
            job_type=job_type,
            job_data=job_data,
            priority=priority,
            timeout_seconds=timeout_seconds,
            parent_job_id=parent_job_id
        )
    
    def can_retry(self) -> bool:
        """Можно ли повторить задачу."""
        # Не retry задачи в dead letter queue или zombie
        if self.status in [JobStatus.DEAD_LETTER, JobStatus.ZOMBIE, JobStatus.CANCELLED]:
            return False
        
        # Проверяем базовые условия
        if not (self.status in [JobStatus.FAILED, JobStatus.TIMEOUT] and 
                self.retry_count < self.max_retries):
            return False
        
        # Некоторые типы ошибок не должны retry
        non_retryable_failures = [
            JobFailureType.CONFIGURATION_ERROR,
            JobFailureType.VALIDATION_ERROR,
            JobFailureType.PERMISSION_ERROR
        ]
        
        if self.failure_type in non_retryable_failures:
            return False
        
        return True
    
    def is_ready_for_retry(self) -> bool:
        """Готова ли задача для retry (с учетом времени)."""
        if not self.can_retry():
            return False
        
        if self.next_retry_at is None:
            return True
        
        return datetime.utcnow() >= self.next_retry_at
    
    def schedule_retry(self) -> bool:
        """Планирует следующую попытку retry."""
        if not self.can_retry():
            return False
        
        self.retry_count += 1
        self.next_retry_at = self.retry_config.get_next_retry_time(self.retry_count)
        self.status = JobStatus.RETRYING
        
        self.log_info(f"Retry #{self.retry_count} scheduled for {self.next_retry_at.isoformat()}")
        return True
    
    def move_to_dead_letter(self, reason: str = None) -> bool:
        """Перемещает задачу в dead letter queue."""
        if self.status == JobStatus.DEAD_LETTER:
            return False
        
        self.status = JobStatus.DEAD_LETTER
        self.dead_letter_reason = reason or f"Max retries ({self.max_retries}) exceeded"
        self.moved_to_dead_letter_at = datetime.utcnow()
        self.completed_at = datetime.utcnow()
        
        self.log_error(f"Job moved to dead letter queue: {self.dead_letter_reason}")
        return True
    
    def classify_failure(self, exception: Exception) -> JobFailureType:
        """Классифицирует ошибку для определения retry стратегии."""
        import traceback
        
        # Сохраняем полный traceback
        self.last_error_traceback = traceback.format_exc()
        
        # Классификация по типу исключения
        exc_type = type(exception).__name__.lower()
        exc_message = str(exception).lower()
        
        # Сетевые ошибки
        if any(keyword in exc_type for keyword in ['connection', 'network', 'timeout', 'socket']):
            return JobFailureType.NETWORK_ERROR
        
        if any(keyword in exc_message for keyword in ['connection', 'network', 'timeout']):
            return JobFailureType.NETWORK_ERROR
        
        # Ошибки ресурсов
        if any(keyword in exc_type for keyword in ['memory', 'disk', 'space']):
            return JobFailureType.RESOURCE_ERROR
        
        if any(keyword in exc_message for keyword in ['no space', 'memory', 'disk full']):
            return JobFailureType.RESOURCE_ERROR
        
        # Ошибки прав доступа
        if any(keyword in exc_type for keyword in ['permission', 'access', 'forbidden']):
            return JobFailureType.PERMISSION_ERROR
        
        # Ошибки валидации
        if any(keyword in exc_type for keyword in ['validation', 'value', 'assertion']):
            return JobFailureType.VALIDATION_ERROR
        
        # Timeout ошибки - приоритет перед network errors
        if exc_type == 'timeouterror' or ('timeout' in exc_type and 'error' in exc_type):
            return JobFailureType.TIMEOUT_ERROR
        
        # По умолчанию - неизвестная ошибка
        return JobFailureType.UNKNOWN
    
    def should_timeout(self) -> bool:
        """Превышено ли время выполнения."""
        if not self.timeout_seconds or not self.started_at:
            return False
        
        elapsed = (datetime.utcnow() - self.started_at).total_seconds()
        return elapsed > self.timeout_seconds
    
    def is_zombie(self, zombie_threshold_minutes: int = 60) -> bool:
        """Проверяет является ли задача zombie (зависшая)."""
        if self.status != JobStatus.RUNNING:
            return False
        
        if not self.started_at:
            return False
        
        # Задача считается zombie если выполняется слишком долго без обновлений
        elapsed_minutes = (datetime.utcnow() - self.started_at).total_seconds() / 60
        
        # Если есть timeout, используем его как базу для zombie detection
        if self.timeout_seconds:
            timeout_minutes = self.timeout_seconds / 60
            zombie_threshold = max(zombie_threshold_minutes, timeout_minutes * 2)
        else:
            zombie_threshold = zombie_threshold_minutes
        
        return elapsed_minutes > zombie_threshold
    
    def mark_as_zombie(self, reason: str = None):
        """Помечает задачу как zombie."""
        if self.status == JobStatus.RUNNING:
            self.status = JobStatus.ZOMBIE
            self.error_message = reason or f"Task became zombie after {self.get_elapsed_time():.0f} seconds"
            self.failure_type = JobFailureType.TIMEOUT_ERROR
            
            self.log_error(f"Job marked as zombie: {self.error_message}")
    
    def force_kill(self, reason: str = None):
        """Принудительно завершает zombie задачу."""
        if self.status == JobStatus.ZOMBIE:
            self.status = JobStatus.FAILED
            self.completed_at = datetime.utcnow()
            self.error_message = reason or "Zombie job forcefully terminated"
            
            self.log_error(f"Zombie job killed: {self.error_message}")
    
    def get_elapsed_time(self) -> Optional[float]:
        """Время выполнения в секундах."""
        if not self.started_at:
            return None
        
        end_time = self.completed_at or datetime.utcnow()
        return (end_time - self.started_at).total_seconds()
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразование в словарь для API."""
        return {
            'id': self.id,
            'job_type': self.job_type.value,
            'job_data': self.job_data._data,
            'status': self.status.value,
            'priority': self.priority.value,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'log_file_path': self.log_file_path,
            'error_message': self.error_message,
            'failure_type': self.failure_type.value if self.failure_type else None,
            'retry_count': self.retry_count,
            'max_retries': self.max_retries,
            'next_retry_at': self.next_retry_at.isoformat() if self.next_retry_at else None,
            'worker_id': self.worker_id,
            'timeout_seconds': self.timeout_seconds,
            'parent_job_id': self.parent_job_id,
            'elapsed_time': self.get_elapsed_time(),
            'dead_letter_reason': self.dead_letter_reason,
            'moved_to_dead_letter_at': self.moved_to_dead_letter_at.isoformat() if self.moved_to_dead_letter_at else None,
            'can_retry': self.can_retry(),
            'is_ready_for_retry': self.is_ready_for_retry(),
            'is_zombie': self.is_zombie()
        }
    
    def __repr__(self):
        return f"Job(id={self.id}, type={self.job_type.value}, status={self.status.value})"


class JobWorker(ABC):
    """Базовый класс для исполнителей задач."""
    
    def __init__(self, worker_id: str):
        self.worker_id = worker_id
        self.current_job: Optional[Job] = None
    
    @abstractmethod
    def get_supported_job_types(self) -> list[JobType]:
        """Возвращает список поддерживаемых типов задач."""
        pass
    
    def execute_job_with_logging(self, job: Job) -> bool:
        """
        Выполняет задачу с полным логированием и enhanced error handling.
        
        Args:
            job: Задача для выполнения
            
        Returns:
            True если задача выполнена успешно, False если провалилась
        """
        # Создаем логгер для задачи
        logger = job.create_logger()
        
        success = False
        error_message = None
        failure_type = None
        
        # Отмечаем начало выполнения
        self.current_job = job
        
        try:
            job.log_info(f"Starting job execution with worker {self.worker_id}")
            job.log_info(f"Job data: {job.job_data._data}")
            job.log_info(f"Retry attempt: {job.retry_count + 1}/{job.max_retries + 1}")
            
            # Проверяем timeout перед выполнением
            if job.should_timeout():
                raise TimeoutError(f"Job timeout ({job.timeout_seconds}s) exceeded before execution")
            
            # Используем захват вывода если логгер доступен
            if logger:
                with logger.capture_output():
                    success = self.execute_job(job)
            else:
                success = self.execute_job(job)
                
            if success:
                job.log_info("Job completed successfully")
            else:
                error_message = "Job execution returned False"
                failure_type = JobFailureType.WORKER_ERROR
                job.log_error(error_message)
                
        except TimeoutError as e:
            success = False
            error_message = str(e)
            failure_type = JobFailureType.TIMEOUT_ERROR
            job.log_exception(e, f"timeout in {self.worker_id}")
            
        except PermissionError as e:
            success = False
            error_message = str(e)
            failure_type = JobFailureType.PERMISSION_ERROR
            job.log_exception(e, f"permission error in {self.worker_id}")
            
        except ValueError as e:
            success = False
            error_message = str(e)
            failure_type = JobFailureType.VALIDATION_ERROR
            job.log_exception(e, f"validation error in {self.worker_id}")
            
        except Exception as e:
            success = False
            error_message = str(e)
            # Автоматическая классификация ошибки
            failure_type = job.classify_failure(e)
            job.log_exception(e, f"execute_job in {self.worker_id}")
            
        finally:
            # Обновляем информацию об ошибке
            if not success and error_message:
                job.error_message = error_message
                job.failure_type = failure_type
            
            # Очищаем current_job
            self.current_job = None
            
            # Завершаем логирование
            job.finalize_logging(success, error_message)
            
        return success

    @abstractmethod
    def execute_job(self, job: Job) -> bool:
        """
        Выполняет задачу.
        
        Args:
            job: Задача для выполнения
            
        Returns:
            True если задача выполнена успешно, False если провалилась
            
        Raises:
            Exception: При критических ошибках выполнения
        """
        pass
    
    def can_handle_job(self, job: Job) -> bool:
        """Может ли воркер обработать данную задачу."""
        return job.job_type in self.get_supported_job_types()
    
    def get_worker_info(self) -> Dict[str, Any]:
        """Информация о воркере для мониторинга."""
        return {
            'worker_id': self.worker_id,
            'supported_job_types': [jt.value for jt in self.get_supported_job_types()],
            'current_job_id': self.current_job.id if self.current_job else None,
            'status': 'busy' if self.current_job else 'idle'
        }


# Предопределенные конфигурации для разных типов задач
JOB_TYPE_CONFIGS = {
    JobType.CHANNEL_DOWNLOAD: {
        'timeout_seconds': 3600,  # 1 час
        'max_retries': 3,
        'priority': JobPriority.HIGH
    },
    JobType.PLAYLIST_DOWNLOAD: {
        'timeout_seconds': 1800,  # 30 минут
        'max_retries': 3,
        'priority': JobPriority.HIGH
    },
    JobType.METADATA_EXTRACTION: {
        'timeout_seconds': 300,   # 5 минут
        'max_retries': 2,
        'priority': JobPriority.NORMAL
    },
    JobType.FILE_CLEANUP: {
        'timeout_seconds': 600,   # 10 минут
        'max_retries': 1,
        'priority': JobPriority.LOW
    },
    JobType.DATABASE_BACKUP: {
        'timeout_seconds': 1200,  # 20 минут
        'max_retries': 2,
        'priority': JobPriority.URGENT
    }
}


def create_job_with_defaults(job_type: JobType, **kwargs) -> Job:
    """Создает задачу с предустановленными параметрами для типа."""
    config = JOB_TYPE_CONFIGS.get(job_type, {})
    
    # Применяем дефолтные значения, если они не переданы
    for key, default_value in config.items():
        if key not in kwargs:
            kwargs[key] = default_value
    
    return Job.create(job_type=job_type, **kwargs) 
#!/usr/bin/env python3
"""
Job Types and Base Classes for Job Queue System

Определяет типы задач и базовую архитектуру для системы очереди задач.
"""

from enum import Enum
from typing import Dict, Any, Optional
from datetime import datetime
from abc import ABC, abstractmethod
import json


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


class JobPriority(Enum):
    """Приоритеты задач."""
    
    LOW = 0
    NORMAL = 5
    HIGH = 10
    URGENT = 15
    CRITICAL = 20


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
        
        # Retry логика
        self.retry_count: int = 0
        self.max_retries = max_retries
        
        # Выполнение
        self.worker_id: Optional[str] = None
        self.timeout_seconds = timeout_seconds
        
        # Зависимости
        self.parent_job_id = parent_job_id
    
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
        return (
            self.status in [JobStatus.FAILED, JobStatus.TIMEOUT] and
            self.retry_count < self.max_retries
        )
    
    def should_timeout(self) -> bool:
        """Превышено ли время выполнения."""
        if not self.timeout_seconds or not self.started_at:
            return False
        
        elapsed = (datetime.utcnow() - self.started_at).total_seconds()
        return elapsed > self.timeout_seconds
    
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
            'retry_count': self.retry_count,
            'max_retries': self.max_retries,
            'worker_id': self.worker_id,
            'timeout_seconds': self.timeout_seconds,
            'parent_job_id': self.parent_job_id,
            'elapsed_time': self.get_elapsed_time()
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
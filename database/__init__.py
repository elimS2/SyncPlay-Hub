"""
Database package for YouTube downloader project.

Contains migration system and database management utilities.
"""

# Экспортируем основные классы для удобства использования
from .migration_manager import MigrationManager, Migration

__all__ = ['MigrationManager', 'Migration'] 
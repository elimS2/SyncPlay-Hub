"""
Production Configuration for YouTube Playlist Downloader & Job Queue System

This module provides production-ready configuration with security settings,
performance optimizations, and environment-specific parameters.
"""

import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class ProductionSettings:
    """Main production configuration settings."""
    
    # Security
    secret_key: str = os.environ.get('SECRET_KEY', 'change-this-in-production')
    session_timeout: int = 3600  # 1 hour
    max_content_length: int = 16 * 1024 * 1024  # 16MB
    
    # Database
    connection_pool_size: int = 10
    connection_timeout: int = 30
    journal_mode: str = 'WAL'
    cache_size: int = -64000  # 64MB
    
    # Job Queue
    max_concurrent_workers: int = 5
    worker_timeout_seconds: int = 3600
    max_retry_attempts: int = 3
    max_queue_size: int = 1000
    
    # Performance
    max_concurrent_downloads: int = 3
    download_timeout: int = 1800  # 30 minutes
    send_file_max_age: int = 86400  # 24 hours
    
    # Logging
    log_level: str = 'INFO'
    max_log_size_mb: int = 100
    backup_count: int = 5
    
    # Monitoring
    health_check_enabled: bool = True
    metrics_collection_enabled: bool = True
    metrics_retention_hours: int = 168  # 7 days


class ProductionConfig:
    """Production configuration manager."""
    
    def __init__(self):
        """Initialize production configuration."""
        self.base_dir = Path(__file__).parent.parent
        self._load_environment()
        
        # Core settings
        self.secret_key = os.environ.get('SECRET_KEY', 'change-this-in-production')
        self.connection_pool_size = int(os.environ.get('DB_CONNECTION_POOL_SIZE', '10'))
        self.max_concurrent_workers = int(os.environ.get('MAX_CONCURRENT_WORKERS', '5'))
        self.log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
        self.max_concurrent_downloads = int(os.environ.get('MAX_CONCURRENT_DOWNLOADS', '3'))
        
        self._validate_config()
    
    def _load_environment(self):
        """Load environment variables from .env file."""
        env_file = self.base_dir / '.env'
        if env_file.exists():
            try:
                with open(env_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, value = line.split('=', 1)
                            os.environ.setdefault(key.strip(), value.strip())
            except Exception as e:
                print(f"Warning: Failed to load .env file: {e}")
    
    def _validate_config(self):
        """Validate configuration settings."""
        if self.secret_key == 'change-this-in-production':
            print("WARNING: Using default secret key in production!")
        
        if self.connection_pool_size < 1:
            raise ValueError("Database connection pool size must be at least 1")
    
    def get_flask_config(self) -> Dict[str, Any]:
        """Get Flask-specific configuration."""
        return {
            'SECRET_KEY': self.secret_key,
            'MAX_CONTENT_LENGTH': 16 * 1024 * 1024,  # 16MB
            'SEND_FILE_MAX_AGE_DEFAULT': 86400,  # 24 hours
            'JSON_SORT_KEYS': False,
        }
    
    def get_database_config(self) -> Dict[str, Any]:
        """Get database configuration."""
        return {
            'pool_size': self.connection_pool_size,
            'timeout': 30,
            'sqlite_settings': {
                'journal_mode': 'WAL',
                'cache_size': -64000,  # 64MB
            }
        }
    
    def get_job_queue_config(self) -> Dict[str, Any]:
        """Get job queue configuration."""
        return {
            'max_concurrent_workers': self.max_concurrent_workers,
            'worker_timeout_seconds': 3600,
            'max_retry_attempts': 3,
            'max_queue_size': 1000,
        }
    
    def export_summary(self) -> Dict[str, Any]:
        """Export configuration summary."""
        return {
            'database_pool_size': self.connection_pool_size,
            'max_workers': self.max_concurrent_workers,
            'max_downloads': self.max_concurrent_downloads,
            'log_level': self.log_level,
            'security_configured': self.secret_key != 'change-this-in-production',
        }


# Global configuration instance
production_config = ProductionConfig()


def get_config() -> ProductionConfig:
    """Get the global production configuration instance."""
    return production_config


def configure_app(app, config: Optional[ProductionConfig] = None):
    """Configure Flask application with production settings."""
    if config is None:
        config = get_config()
    
    # Apply Flask configuration
    app.config.update(config.get_flask_config())
    
    # Configure logging
    import logging.config
    logging.config.dictConfig(config.get_logging_config())
    
    return app


if __name__ == "__main__":
    # Configuration testing and validation
    config = ProductionConfig()
    
    print("🔧 Production Configuration Summary:")
    print(f"  📊 Database Pool Size: {config.connection_pool_size}")
    print(f"  👥 Max Concurrent Workers: {config.max_concurrent_workers}")
    print(f"  📥 Max Concurrent Downloads: {config.max_concurrent_downloads}")
    print(f"  📋 Log Level: {config.log_level}")
    print(f"  🔐 Security: {'Configured' if config.secret_key != 'change-this-in-production' else 'Default (WARNING)'}")
    
    print("\n✅ Configuration validation completed successfully!") 
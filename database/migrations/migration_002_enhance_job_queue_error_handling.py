#!/usr/bin/env python3
"""
Migration 002: Enhanced Job Queue Error Handling

Добавляет новые поля в таблицу job_queue для Phase 6 - Error Handling & Retry Logic:
- failure_type: Тип ошибки для классификации
- next_retry_at: Время следующей попытки retry
- last_error_traceback: Полный traceback последней ошибки
- dead_letter_reason: Причина перемещения в dead letter queue
- moved_to_dead_letter_at: Время перемещения в dead letter queue
"""

import sqlite3
from datetime import datetime
from pathlib import Path


MIGRATION_ID = "002_enhance_job_queue_error_handling"
MIGRATION_DESCRIPTION = "Enhanced Job Queue Error Handling for Phase 6"


def upgrade(db_path: str):
    """Применяет миграцию - добавляет новые поля для error handling."""
    print(f"🔄 Applying migration {MIGRATION_ID}...")
    
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        
        # Добавляем новые поля для enhanced error handling
        new_columns = [
            ("failure_type", "TEXT"),  # Тип ошибки (JobFailureType enum)
            ("next_retry_at", "TIMESTAMP"),  # Время следующей попытки retry
            ("last_error_traceback", "TEXT"),  # Полный traceback ошибки
            ("dead_letter_reason", "TEXT"),  # Причина dead letter
            ("moved_to_dead_letter_at", "TIMESTAMP")  # Время перемещения в dead letter
        ]
        
        # Проверяем какие колонки уже существуют
        cursor.execute("PRAGMA table_info(job_queue)")
        existing_columns = {row[1] for row in cursor.fetchall()}
        
        added_columns = []
        for column_name, column_type in new_columns:
            if column_name not in existing_columns:
                cursor.execute(f"ALTER TABLE job_queue ADD COLUMN {column_name} {column_type}")
                added_columns.append(column_name)
                print(f"  ✅ Added column: {column_name} ({column_type})")
            else:
                print(f"  ⚠️  Column already exists: {column_name}")
        
        # Создаем индексы для новых полей
        indexes_to_create = [
            ("idx_job_queue_next_retry", "next_retry_at"),
            ("idx_job_queue_failure_type", "failure_type"),
            ("idx_job_queue_dead_letter", "moved_to_dead_letter_at")
        ]
        
        for index_name, column_name in indexes_to_create:
            if column_name in added_columns or column_name in existing_columns:
                try:
                    cursor.execute(f"CREATE INDEX IF NOT EXISTS {index_name} ON job_queue({column_name})")
                    print(f"  🔍 Created index: {index_name}")
                except sqlite3.OperationalError as e:
                    print(f"  ⚠️  Index creation skipped: {index_name} - {e}")
        
        conn.commit()
        print(f"✅ Migration {MIGRATION_ID} applied successfully!")


def downgrade(db_path: str):
    """Откатывает миграцию (SQLite не поддерживает DROP COLUMN до версии 3.35)."""
    print(f"⚠️  Migration {MIGRATION_ID} downgrade not supported by SQLite")
    print("   New columns will remain in the table but won't be used")


def get_migration_info():
    """Возвращает информацию о миграции."""
    return {
        "id": MIGRATION_ID,
        "description": MIGRATION_DESCRIPTION,
        "upgrade": upgrade,
        "downgrade": downgrade,
        "applied_at": None
    }


if __name__ == "__main__":
    # Тестирование миграции
    import os
    import tempfile
    
    # Создаем временную базу для тестирования
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp_db:
        test_db_path = tmp_db.name
    
    try:
        print("🧪 Testing migration on temporary database...")
        
        # Создаем базовую таблицу job_queue (как в migration_001)
        with sqlite3.connect(test_db_path) as conn:
            cursor = conn.cursor()
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
            conn.commit()
            print("  📋 Created base job_queue table")
        
        # Применяем миграцию
        upgrade(test_db_path)
        
        # Проверяем результат
        with sqlite3.connect(test_db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(job_queue)")
            columns = [row[1] for row in cursor.fetchall()]
            
            print("\n📊 Final table structure:")
            for col in columns:
                print(f"  - {col}")
            
            # Проверяем новые колонки
            expected_new_columns = [
                'failure_type', 'next_retry_at', 'last_error_traceback',
                'dead_letter_reason', 'moved_to_dead_letter_at'
            ]
            
            missing_columns = [col for col in expected_new_columns if col not in columns]
            if missing_columns:
                print(f"❌ Missing columns: {missing_columns}")
            else:
                print("✅ All expected columns present!")
        
        print("\n🎉 Migration test completed successfully!")
        
    finally:
        # Удаляем временную базу
        os.unlink(test_db_path)
        print(f"🧹 Cleaned up temporary database") 
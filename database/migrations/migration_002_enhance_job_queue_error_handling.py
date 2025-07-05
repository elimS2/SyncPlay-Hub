#!/usr/bin/env python3
"""
Migration 002: Enhanced Job Queue Error Handling

Adds new fields to job_queue table for Phase 6 - Error Handling & Retry Logic:
- failure_type: Error type for classification
- next_retry_at: Time of next retry attempt
- last_error_traceback: Full traceback of last error
- dead_letter_reason: Reason for moving to dead letter queue
- moved_to_dead_letter_at: Time of moving to dead letter queue
"""

from database.migration_manager import Migration
import sqlite3


class Migration002(Migration):
    """Enhanced error handling for job queue system."""
    
    def up(self, conn: sqlite3.Connection) -> None:
        """Adds new fields for error handling."""
        cursor = conn.cursor()
        
        # Add new fields for enhanced error handling
        new_columns = [
            ("failure_type", "TEXT"),  # Error type (JobFailureType enum)
            ("next_retry_at", "TIMESTAMP"),  # Time of next retry attempt
            ("last_error_traceback", "TEXT"),  # Full error traceback
            ("dead_letter_reason", "TEXT"),  # Dead letter reason
            ("moved_to_dead_letter_at", "TIMESTAMP")  # Time moved to dead letter
        ]
        
        # Check which columns already exist
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
        
        # Create indexes for new fields
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
        
        print("✅ Enhanced error handling fields added to job_queue")
    
    def down(self, conn: sqlite3.Connection) -> None:
        """Rolls back migration (SQLite doesn't support DROP COLUMN before version 3.35)."""
        print("⚠️  Migration 002 downgrade not supported by SQLite")
        print("   New columns will remain in the table but won't be used")
    
    def description(self) -> str:
        """Migration description."""
        return "Enhanced Job Queue Error Handling - adds failure_type, retry timing, and dead letter fields"


# Legacy functions for backward compatibility (can be removed later)
MIGRATION_ID = "002_enhance_job_queue_error_handling"
MIGRATION_DESCRIPTION = "Enhanced Job Queue Error Handling for Phase 6"


def upgrade(db_path: str):
    """Legacy function - use Migration002 class instead."""
    print(f"⚠️  Using legacy upgrade function. Please use Migration002 class instead.")
    with sqlite3.connect(db_path) as conn:
        migration = Migration002()
        migration.up(conn)


def downgrade(db_path: str):
    """Legacy function - use Migration002 class instead."""
    print(f"⚠️  Using legacy downgrade function. Please use Migration002 class instead.")
    with sqlite3.connect(db_path) as conn:
        migration = Migration002()
        migration.down(conn)


def get_migration_info():
    """Legacy function - use Migration002 class instead."""
    return {
        "id": MIGRATION_ID,
        "description": MIGRATION_DESCRIPTION,
        "upgrade": upgrade,
        "downgrade": downgrade,
        "applied_at": None
    }


if __name__ == "__main__":
    # Migration testing
    import os
    import tempfile
    
    # Create temporary database for testing
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp_db:
        test_db_path = tmp_db.name
    
    try:
        print("🧪 Testing migration on temporary database...")
        
        # Create base job_queue table (as in migration_001)
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
        
        # Apply migration through new class
        with sqlite3.connect(test_db_path) as conn:
            migration = Migration002()
            migration.up(conn)
            conn.commit()
        
        # Check result
        with sqlite3.connect(test_db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(job_queue)")
            columns = [row[1] for row in cursor.fetchall()]
            
            print("\n📊 Final table structure:")
            for col in columns:
                print(f"  - {col}")
            
            # Check new columns
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
        # Delete temporary database
        os.unlink(test_db_path)
        print(f"🧹 Cleaned up temporary database") 
"""
Migration 003: Add missing job statuses to CHECK constraint

Adds 'timeout', 'retrying', 'dead_letter', 'zombie' statuses to job_queue table
CHECK constraint to fix "CHECK constraint failed" errors.
"""

import sqlite3
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))
from migration_manager import Migration


def migrate_up(conn: sqlite3.Connection):
    """Add missing job statuses to CHECK constraint."""
    cursor = conn.cursor()
    
    # First, check if job_queue table exists and get its current schema
    cursor.execute("""
        SELECT sql FROM sqlite_master 
        WHERE type='table' AND name='job_queue'
    """)
    
    result = cursor.fetchone()
    if not result:
        print("job_queue table not found, skipping migration")
        return
    
    current_schema = result[0]
    print(f"Current job_queue schema: {current_schema}")
    
    # Check if CHECK constraint already includes all needed statuses
    if all(status in current_schema for status in ['timeout', 'retrying', 'dead_letter', 'zombie']):
        print("All required statuses already present in CHECK constraint")
        return
    
    print("Updating job_queue CHECK constraint to include missing statuses...")
    
    # SQLite doesn't support ALTER TABLE to modify CHECK constraints
    # We need to recreate the table with updated constraint
    
    # 1. Create new table with updated CHECK constraint
    cursor.execute("""
        CREATE TABLE job_queue_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_type TEXT NOT NULL,
            job_data TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            priority INTEGER NOT NULL DEFAULT 5,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            log_file_path TEXT,
            error_message TEXT,
            failure_type TEXT,
            last_error_traceback TEXT,
            retry_count INTEGER DEFAULT 0,
            max_retries INTEGER DEFAULT 3,
            next_retry_at TIMESTAMP,
            dead_letter_reason TEXT,
            moved_to_dead_letter_at TIMESTAMP,
            worker_id TEXT,
            timeout_seconds INTEGER,
            parent_job_id INTEGER,
            CHECK (status IN (
                'pending', 'running', 'completed', 'failed', 'cancelled',
                'timeout', 'retrying', 'dead_letter', 'zombie'
            )),
            CHECK (priority >= 0 AND priority <= 20),
            FOREIGN KEY (parent_job_id) REFERENCES job_queue(id)
        )
    """)
    
    # 2. Copy data from old table to new table
    cursor.execute("""
        INSERT INTO job_queue_new 
        SELECT * FROM job_queue
    """)
    
    # 3. Drop old table
    cursor.execute("DROP TABLE job_queue")
    
    # 4. Rename new table to original name
    cursor.execute("ALTER TABLE job_queue_new RENAME TO job_queue")
    
    # 5. Recreate indexes
    cursor.execute("CREATE INDEX idx_job_queue_status ON job_queue(status)")
    cursor.execute("CREATE INDEX idx_job_queue_priority ON job_queue(priority DESC)")
    cursor.execute("CREATE INDEX idx_job_queue_created_at ON job_queue(created_at)")
    cursor.execute("CREATE INDEX idx_job_queue_type ON job_queue(job_type)")
    
    conn.commit()
    print("Successfully updated job_queue CHECK constraint with all statuses")


def migrate_down(conn: sqlite3.Connection):
    """Revert CHECK constraint to original state (not recommended)."""
    cursor = conn.cursor()
    
    print("WARNING: Reverting CHECK constraint will prevent using extended statuses")
    print("This migration down is not recommended as it may cause data loss")
    
    # Create table with original constraint
    cursor.execute("""
        CREATE TABLE job_queue_original (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_type TEXT NOT NULL,
            job_data TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            priority INTEGER NOT NULL DEFAULT 5,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            log_file_path TEXT,
            error_message TEXT,
            failure_type TEXT,
            last_error_traceback TEXT,
            retry_count INTEGER DEFAULT 0,
            max_retries INTEGER DEFAULT 3,
            next_retry_at TIMESTAMP,
            dead_letter_reason TEXT,
            moved_to_dead_letter_at TIMESTAMP,
            worker_id TEXT,
            timeout_seconds INTEGER,
            parent_job_id INTEGER,
            CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled')),
            CHECK (priority >= 0 AND priority <= 20),
            FOREIGN KEY (parent_job_id) REFERENCES job_queue(id)
        )
    """)
    
    # Copy only jobs with allowed statuses
    cursor.execute("""
        INSERT INTO job_queue_original 
        SELECT * FROM job_queue
        WHERE status IN ('pending', 'running', 'completed', 'failed', 'cancelled')
    """)
    
    # Drop and rename
    cursor.execute("DROP TABLE job_queue")
    cursor.execute("ALTER TABLE job_queue_original RENAME TO job_queue")
    
    # Recreate indexes
    cursor.execute("CREATE INDEX idx_job_queue_status ON job_queue(status)")
    cursor.execute("CREATE INDEX idx_job_queue_priority ON job_queue(priority DESC)")
    cursor.execute("CREATE INDEX idx_job_queue_created_at ON job_queue(created_at)")
    cursor.execute("CREATE INDEX idx_job_queue_type ON job_queue(job_type)")
    
    conn.commit()
    print("Reverted to original CHECK constraint (extended status jobs removed)")


class Migration003(Migration):
    """Migration to add missing job statuses to CHECK constraint."""
    
    def up(self, conn: sqlite3.Connection) -> None:
        """Apply migration - add missing statuses to CHECK constraint."""
        migrate_up(conn)
    
    def down(self, conn: sqlite3.Connection) -> None:
        """Rollback migration - revert to original CHECK constraint."""
        migrate_down(conn)
    
    def description(self) -> str:
        """Description of what this migration does."""
        return "Add missing job statuses (timeout, retrying, dead_letter, zombie) to CHECK constraint"


if __name__ == "__main__":
    # Test migration
    from database import get_connection, get_db_path
    
    print(f"Testing migration on database: {get_db_path()}")
    
    with get_connection() as conn:
        migrate_up(conn)
        print("Migration completed successfully") 
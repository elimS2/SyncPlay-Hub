#!/usr/bin/env python3
"""
Database Migration Manager

Database migration management system for the project.
Allows versioning schema changes and applying them automatically.
"""

import sqlite3
import importlib
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any
from abc import ABC, abstractmethod


class Migration(ABC):
    """Base class for migrations."""
    
    def __init__(self):
        # Extract migration number from class name (e.g. Migration001 -> 1)
        class_name = self.__class__.__name__
        if class_name.startswith('Migration') and class_name[9:].isdigit():
            self.number = int(class_name[9:])
        else:
            raise ValueError(f"Migration class name must be in format Migration001, got {class_name}")
    
    @abstractmethod
    def up(self, conn: sqlite3.Connection) -> None:
        """Apply migration (create changes)."""
        pass
    
    @abstractmethod
    def down(self, conn: sqlite3.Connection) -> None:
        """Rollback migration (undo changes).""" 
        pass
    
    @abstractmethod
    def description(self) -> str:
        """Description of what the migration does."""
        pass


class MigrationManager:
    """Manager for database migrations."""
    
    def __init__(self, db_path: str, migrations_dir: str = None):
        self.db_path = db_path
        if migrations_dir is None:
            self.migrations_dir = Path(__file__).parent / 'migrations'
        else:
            self.migrations_dir = Path(migrations_dir)
        
        # Add migrations folder to Python path
        sys.path.insert(0, str(self.migrations_dir.parent))
        
        self._ensure_migration_table()
    
    def _ensure_migration_table(self):
        """Creates migration tracking table if it doesn't exist."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    migration_number INTEGER UNIQUE NOT NULL,
                    migration_name TEXT NOT NULL,
                    applied_at TEXT DEFAULT (datetime('now')),
                    rollback_at TEXT NULL
                )
            ''')
            conn.commit()
        finally:
            conn.close()
    
    def get_applied_migrations(self) -> List[int]:
        """Returns list of applied migration numbers."""
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.cursor()
            cur.execute('''
                SELECT migration_number 
                FROM schema_migrations 
                WHERE rollback_at IS NULL
                ORDER BY migration_number
            ''')
            return [row[0] for row in cur.fetchall()]
        finally:
            conn.close()
    
    def get_available_migrations(self) -> List[Migration]:
        """Loads all available migrations from migrations folder."""
        migrations = []
        
        # Look for all .py files in migrations folder
        if not self.migrations_dir.exists():
            return migrations
        
        for file_path in self.migrations_dir.glob('*.py'):
            if file_path.name.startswith('migration_') and file_path.name.endswith('.py'):
                # Load migration module
                module_name = f"migrations.{file_path.stem}"
                try:
                    module = importlib.import_module(module_name)
                    
                    # Look for Migration classes in module
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if (isinstance(attr, type) and 
                            issubclass(attr, Migration) and 
                            attr != Migration):
                            migrations.append(attr())
                            break
                    
                except Exception as e:
                    print(f"Warning: Failed to load migration {file_path}: {e}")
        
        # Sort by migration number
        migrations.sort(key=lambda m: m.number)
        return migrations
    
    def get_pending_migrations(self) -> List[Migration]:
        """Returns migrations that haven't been applied yet."""
        applied = set(self.get_applied_migrations())
        available = self.get_available_migrations()
        
        return [m for m in available if m.number not in applied]
    
    def apply_migration(self, migration: Migration) -> bool:
        """Applies one migration."""
        conn = sqlite3.connect(self.db_path)
        try:
            print(f"Applying migration {migration.number:03d}: {migration.description()}")
            
            # Apply migration
            migration.up(conn)
            
            # Record in migrations table
            conn.execute('''
                INSERT INTO schema_migrations (migration_number, migration_name, applied_at)
                VALUES (?, ?, datetime('now'))
            ''', (migration.number, migration.__class__.__name__))
            
            conn.commit()
            print(f"✅ Migration {migration.number:03d} applied successfully")
            return True
            
        except Exception as e:
            conn.rollback()
            print(f"❌ Failed to apply migration {migration.number:03d}: {e}")
            return False
        finally:
            conn.close()
    
    def rollback_migration(self, migration: Migration) -> bool:
        """Rolls back one migration."""
        conn = sqlite3.connect(self.db_path)
        try:
            print(f"Rolling back migration {migration.number:03d}: {migration.description()}")
            
            # Rollback migration
            migration.down(conn)
            
            # Mark migration as rolled back
            conn.execute('''
                UPDATE schema_migrations 
                SET rollback_at = datetime('now')
                WHERE migration_number = ? AND rollback_at IS NULL
            ''', (migration.number,))
            
            conn.commit()
            print(f"✅ Migration {migration.number:03d} rolled back successfully")
            return True
            
        except Exception as e:
            conn.rollback()
            print(f"❌ Failed to rollback migration {migration.number:03d}: {e}")
            return False
        finally:
            conn.close()
    
    def migrate(self) -> int:
        """Applies all unapplied migrations."""
        pending = self.get_pending_migrations()
        
        if not pending:
            print("✅ Database is up to date")
            return 0
        
        print(f"📋 Found {len(pending)} pending migration(s)")
        
        applied_count = 0
        for migration in pending:
            if self.apply_migration(migration):
                applied_count += 1
            else:
                print(f"❌ Stopped at migration {migration.number:03d}")
                break
        
        if applied_count == len(pending):
            print(f"✅ Successfully applied {applied_count} migration(s)")
        else:
            print(f"⚠️  Applied {applied_count}/{len(pending)} migration(s)")
        
        return applied_count
    
    def migrate_json(self) -> int:
        """Applies all unapplied migrations (silent mode for JSON)."""
        pending = self.get_pending_migrations()
        
        if not pending:
            return 0
        
        applied_count = 0
        for migration in pending:
            if self.apply_migration_silent(migration):
                applied_count += 1
            else:
                break
        
        return applied_count
    
    def apply_migration_silent(self, migration: Migration) -> bool:
        """Applies one migration without output to console."""
        conn = sqlite3.connect(self.db_path)
        try:
            # Apply migration
            migration.up(conn)
            
            # Record in migrations table
            conn.execute('''
                INSERT INTO schema_migrations (migration_number, migration_name, applied_at)
                VALUES (?, ?, datetime('now'))
            ''', (migration.number, migration.__class__.__name__))
            
            conn.commit()
            return True
            
        except Exception:
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def rollback_migration_json(self, migration: Migration) -> bool:
        """Rolls back one migration (silent mode for JSON)."""
        conn = sqlite3.connect(self.db_path)
        try:
            # Rollback migration
            migration.down(conn)
            
            # Mark migration as rolled back
            conn.execute('''
                UPDATE schema_migrations 
                SET rollback_at = datetime('now')
                WHERE migration_number = ? AND rollback_at IS NULL
            ''', (migration.number,))
            
            conn.commit()
            return True
            
        except Exception:
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def mark_migration_as_applied(self, migration_number: int, migration_name: str = None) -> bool:
        """
        Marks migration as applied without actually applying changes.
        Useful when changes have already been applied manually.
        """
        conn = sqlite3.connect(self.db_path)
        try:
            # Check if already applied
            cursor = conn.cursor()
            cursor.execute('''
                SELECT COUNT(*) FROM schema_migrations 
                WHERE migration_number = ? AND rollback_at IS NULL
            ''', (migration_number,))
            
            if cursor.fetchone()[0] > 0:
                print(f"⚠️  Migration {migration_number:03d} is already marked as applied")
                return False
            
            # Mark as applied
            migration_name = migration_name or f"Migration{migration_number:03d}"
            cursor.execute('''
                INSERT INTO schema_migrations (migration_number, migration_name, applied_at)
                VALUES (?, ?, datetime('now'))
            ''', (migration_number, migration_name))
            
            conn.commit()
            print(f"✅ Migration {migration_number:03d} marked as applied")
            return True
            
        except Exception as e:
            print(f"❌ Failed to mark migration {migration_number:03d} as applied: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def status(self) -> Dict[str, Any]:
        """Shows migration status."""
        applied = self.get_applied_migrations()
        available = self.get_available_migrations()
        pending = self.get_pending_migrations()
        
        print(f"📊 MIGRATION STATUS")
        print(f"={'='*50}")
        print(f"Database: {self.db_path}")
        print(f"Applied migrations: {len(applied)}")
        print(f"Available migrations: {len(available)}")
        print(f"Pending migrations: {len(pending)}")
        
        if available:
            print(f"\n📋 AVAILABLE MIGRATIONS:")
            for migration in available:
                status_icon = "✅" if migration.number in applied else "⏳"
                print(f"   {status_icon} {migration.number:03d}: {migration.description()}")
        
        return {
            'applied_count': len(applied),
            'available_count': len(available),
            'pending_count': len(pending),
            'applied_migrations': applied,
            'pending_migrations': [m.number for m in pending]
        }
    
    def status_json(self) -> Dict[str, Any]:
        """Returns migration status in JSON format."""
        applied = self.get_applied_migrations()
        available = self.get_available_migrations()
        pending = self.get_pending_migrations()
        
        migrations_info = []
        for migration in available:
            migrations_info.append({
                'number': migration.number,
                'description': migration.description(),
                'applied': migration.number in applied,
                'status': 'applied' if migration.number in applied else 'pending'
            })
        
        return {
            'success': True,
            'command': 'status',
            'database_path': self.db_path,
            'applied_count': len(applied),
            'available_count': len(available),
            'pending_count': len(pending),
            'applied_migrations': applied,
            'pending_migrations': [m.number for m in pending],
            'migrations': migrations_info
        }


def main():
    """CLI for managing migrations."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Database Migration Manager")
    parser.add_argument('--db-path', help="Path to database file")
    parser.add_argument('command', choices=['migrate', 'status', 'rollback'], 
                       help="Command to execute")
    parser.add_argument('--migration', type=int, help="Specific migration number for rollback")
    
    args = parser.parse_args()
    
    # Define database path
    db_path = args.db_path
    if not db_path:
        # Try to load from .env
        env_path = Path(__file__).parent.parent / '.env'
        if env_path.exists():
            try:
                with open(env_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith('DB_PATH='):
                            db_path = line.split('=', 1)[1].strip().lstrip('\ufeff')
                            break
            except Exception:
                pass
    
    if not db_path:
        db_path = "tracks.db"
    
    print(f"🔗 Using database: {db_path}")
    
    manager = MigrationManager(db_path)
    
    if args.command == 'migrate':
        manager.migrate()
    elif args.command == 'status':
        manager.status()
    elif args.command == 'rollback':
        if not args.migration:
            print("❌ --migration parameter required for rollback")
            sys.exit(1)
        
        available = manager.get_available_migrations()
        migration_to_rollback = None
        for m in available:
            if m.number == args.migration:
                migration_to_rollback = m
                break
        
        if not migration_to_rollback:
            print(f"❌ Migration {args.migration} not found")
            sys.exit(1)
        
        manager.rollback_migration(migration_to_rollback)


if __name__ == "__main__":
    main() 
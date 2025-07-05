#!/usr/bin/env python3
"""
Database Migrations CLI

Convenient interface for managing database migrations.
Automatically loads configuration from .env file.
"""

import sys
import json
from pathlib import Path

# Add project root folder to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from database.migration_manager import MigrationManager


def load_env_file():
    """Loads variables from .env file."""
    env_path = project_root / '.env'
    if not env_path.exists():
        return {}
    
    env_vars = {}
    try:
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip().lstrip('\ufeff')  # Remove BOM
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env_vars[key.strip()] = value.strip()
    except Exception as e:
        print(f"Warning: Failed to load .env file: {e}")
    
    return env_vars


def main():
    """Main CLI function."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Database Migration Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python migrate.py status          # Show migration status
  python migrate.py migrate         # Apply all pending migrations
  python migrate.py rollback --migration 1  # Rollback specific migration
  python migrate.py mark-applied --migration 1  # Mark migration as applied without running
        """
    )
    
    parser.add_argument('--db-path', help="Path to database file")
    parser.add_argument('--json', action='store_true', 
                       help="Output results in JSON format (for automation)")
    parser.add_argument('command', choices=['migrate', 'status', 'rollback', 'mark-applied'], 
                       help="Command to execute")
    parser.add_argument('--migration', type=int, 
                       help="Specific migration number (for rollback or mark-applied)")
    
    args = parser.parse_args()
    
    # Determine database path
    db_path = args.db_path
    if not db_path:
        env_vars = load_env_file()
        db_path = env_vars.get('DB_PATH')
    
    if not db_path:
        db_path = "tracks.db"
    
    if not args.json:
        print(f"🔗 Using database: {db_path}")
    
    # Check database existence
    if not Path(db_path).exists():
        if args.json:
            error_result = {
                'success': False,
                'error': 'Database file not found',
                'database_path': db_path,
                'message': 'Make sure DB_PATH in .env file is correct or use --db-path parameter'
            }
            print(json.dumps(error_result, indent=2, ensure_ascii=False))
        else:
            print(f"❌ Database file not found: {db_path}")
            print("💡 Make sure DB_PATH in .env file is correct or use --db-path parameter")
        sys.exit(1)
    
    try:
        manager = MigrationManager(db_path)
        
        if args.command == 'migrate':
            if args.json:
                count = manager.migrate_json()
                result = {
                    'success': True,
                    'command': 'migrate',
                    'database_path': db_path,
                    'migrations_applied': count,
                    'message': f'Successfully applied {count} migration(s)' if count > 0 else 'Database is up to date'
                }
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print(f"🚀 Starting database migration...")
                count = manager.migrate()
                if count > 0:
                    print(f"🎉 Migration completed successfully!")
            
        elif args.command == 'status':
            if args.json:
                status_data = manager.status_json()
                print(json.dumps(status_data, indent=2, ensure_ascii=False))
            else:
                manager.status()
            
        elif args.command == 'rollback':
            if not args.migration:
                if args.json:
                    error_result = {
                        'success': False,
                        'error': 'Migration parameter required',
                        'message': '--migration parameter required for rollback'
                    }
                    print(json.dumps(error_result, indent=2, ensure_ascii=False))
                else:
                    print("❌ --migration parameter required for rollback")
                    print("Example: python migrate.py rollback --migration 1")
                sys.exit(1)
            
            available = manager.get_available_migrations()
            migration_to_rollback = None
            
            for m in available:
                if m.number == args.migration:
                    migration_to_rollback = m
                    break
            
            if not migration_to_rollback:
                if args.json:
                    error_result = {
                        'success': False,
                        'error': 'Migration not found',
                        'migration_number': args.migration,
                        'message': f'Migration {args.migration} not found'
                    }
                    print(json.dumps(error_result, indent=2, ensure_ascii=False))
                else:
                    print(f"❌ Migration {args.migration} not found")
                sys.exit(1)
            
            if args.json:
                success = manager.rollback_migration_json(migration_to_rollback)
                result = {
                    'success': success,
                    'command': 'rollback',
                    'database_path': db_path,
                    'migration_number': args.migration,
                    'migration_description': migration_to_rollback.description(),
                    'message': f'Migration {args.migration} rolled back successfully' if success else f'Failed to rollback migration {args.migration}'
                }
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print(f"⚠️  Rolling back migration {args.migration}...")
                if manager.rollback_migration(migration_to_rollback):
                    print(f"🎉 Rollback completed successfully!")
                    
        elif args.command == 'mark-applied':
            if not args.migration:
                if args.json:
                    error_result = {
                        'success': False,
                        'error': 'Migration parameter required',
                        'message': '--migration parameter required for mark-applied'
                    }
                    print(json.dumps(error_result, indent=2, ensure_ascii=False))
                else:
                    print("❌ --migration parameter required for mark-applied")
                    print("Example: python migrate.py mark-applied --migration 1")
                sys.exit(1)
            
            if args.json:
                success = manager.mark_migration_as_applied(args.migration)
                result = {
                    'success': success,
                    'command': 'mark-applied',
                    'database_path': db_path,
                    'migration_number': args.migration,
                    'message': f'Migration {args.migration} marked as applied' if success else f'Failed to mark migration {args.migration} as applied'
                }
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print(f"📝 Marking migration {args.migration} as applied...")
                if manager.mark_migration_as_applied(args.migration):
                    print(f"🎉 Migration {args.migration} marked as applied successfully!")
    
    except Exception as e:
        if args.json:
            error_result = {
                'success': False,
                'error': 'Unexpected error',
                'message': str(e),
                'database_path': db_path
            }
            print(json.dumps(error_result, indent=2, ensure_ascii=False))
        else:
            print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main() 
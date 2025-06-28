# Database Migrations System

Система управления миграциями базы данных для YouTube downloader проекта.

## 🎯 **Назначение**

Миграции позволяют:
- **Версионировать** изменения схемы базы данных
- **Отслеживать** какие изменения применены
- **Откатывать** изменения при необходимости
- **Синхронизировать** схему между разными средами
- **Автоматизировать** обновления базы данных

## 🚀 **Быстрый старт**

### Проверить статус миграций
```bash
python migrate.py status
```

### Применить все неприменённые миграции
```bash
python migrate.py migrate
```

### Откатить конкретную миграцию
```bash
python migrate.py rollback --migration 1
```

### JSON формат для автоматизации
```bash
# Статус в JSON формате
python migrate.py status --json

# Миграция с JSON выводом
python migrate.py migrate --json

# Откат с JSON выводом
python migrate.py rollback --migration 1 --json
```

## 📁 **Структура файлов**

```
database/
├── migration_manager.py          # Ядро системы миграций
├── migrations/                   # Папка с миграциями
│   ├── __init__.py
│   └── migration_001_create_job_queue.py
└── README.md                     # Этот файл

migrate.py                        # CLI интерфейс для запуска
```

## 📋 **Создание новой миграции**

### 1. Создайте файл миграции
```bash
# Формат: migration_XXX_description.py
touch database/migrations/migration_002_add_user_settings.py
```

### 2. Реализуйте класс миграции
```python
#!/usr/bin/env python3
from database.migration_manager import Migration
import sqlite3

class Migration002(Migration):
    """Описание миграции."""
    
    def up(self, conn: sqlite3.Connection) -> None:
        """Применить изменения."""
        conn.execute('''
            CREATE TABLE user_settings (
                id INTEGER PRIMARY KEY,
                setting_key TEXT UNIQUE NOT NULL,
                setting_value TEXT
            )
        ''')
        print("✅ Created user_settings table")
    
    def down(self, conn: sqlite3.Connection) -> None:
        """Откатить изменения."""
        conn.execute('DROP TABLE IF EXISTS user_settings')
        print("✅ Dropped user_settings table")
    
    def description(self) -> str:
        return "Add user settings table"
```

### 3. Примените миграцию
```bash
python migrate.py migrate
```

## 🔧 **Конфигурация**

### Путь к базе данных
Система автоматически определяет путь к базе данных:

1. **Параметр командной строки** (высший приоритет):
   ```bash
   python migrate.py status --db-path "D:/music/Youtube/DB/tracks.db"
   ```

2. **Файл .env** (создайте в корне проекта):
   ```
   DB_PATH=D:/music/Youtube/DB/tracks.db
   ```

3. **По умолчанию**: `tracks.db` в текущей папке

## 📊 **Команды CLI**

### Обычный режим (с эмодзи и форматированием)

### `python migrate.py status`
Показывает текущий статус миграций:
```
📊 MIGRATION STATUS
==================================================
Database: D:/music/Youtube/DB/tracks.db
Applied migrations: 1
Available migrations: 1
Pending migrations: 0

📋 AVAILABLE MIGRATIONS:
   ✅ 001: Create job_queue table with status tracking
```

### `python migrate.py migrate`
Применяет все неприменённые миграции:
```
🚀 Starting database migration...
📋 Found 1 pending migration(s)
Applying migration 001: Create job_queue table...
✅ Migration 001 applied successfully
✅ Successfully applied 1 migration(s)
🎉 Migration completed successfully!
```

### `python migrate.py rollback --migration N`
Откатывает конкретную миграцию:
```
⚠️  Rolling back migration 1...
Rolling back migration 001: Create job_queue table...
✅ Migration 001 rolled back successfully
🎉 Rollback completed successfully!
```

### JSON режим (для автоматизации)

### `python migrate.py status --json`
Возвращает статус в структурированном JSON:
```json
{
  "success": true,
  "command": "status",
  "database_path": "D:/music/Youtube/DB/tracks.db",
  "applied_count": 0,
  "available_count": 1,
  "pending_count": 1,
  "applied_migrations": [],
  "pending_migrations": [1],
  "migrations": [
    {
      "number": 1,
      "description": "Create job_queue table with status tracking",
      "applied": false,
      "status": "pending"
    }
  ]
}
```

### `python migrate.py migrate --json`
Применяет миграции и возвращает результат:
```json
{
  "success": true,
  "command": "migrate",
  "database_path": "D:/music/Youtube/DB/tracks.db",
  "migrations_applied": 1,
  "message": "Successfully applied 1 migration(s)"
}
```

### `python migrate.py rollback --migration 1 --json`
Откатывает миграцию и возвращает результат:
```json
{
  "success": true,
  "command": "rollback",
  "database_path": "D:/music/Youtube/DB/tracks.db",
  "migration_number": 1,
  "migration_description": "Create job_queue table with status tracking",
  "message": "Migration 1 rolled back successfully"
}
```

## 🏗️ **Архитектура системы**

### MigrationManager
Основной класс для управления миграциями:
- Отслеживает применённые миграции в таблице `schema_migrations`
- Загружает миграции из папки `migrations/`
- Применяет и откатывает изменения

### Migration (базовый класс)
Абстрактный класс для всех миграций:
- `up()` - применить изменения
- `down()` - откатить изменения  
- `description()` - описание миграции

### Таблица schema_migrations
Отслеживает статус миграций:
```sql
CREATE TABLE schema_migrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    migration_number INTEGER UNIQUE NOT NULL,
    migration_name TEXT NOT NULL,
    applied_at TEXT DEFAULT (datetime('now')),
    rollback_at TEXT NULL
);
```

## ✅ **Лучшие практики**

### 1. Именование миграций
```
migration_001_create_job_queue.py
migration_002_add_user_settings.py
migration_003_add_indexes_to_tracks.py
```

### 2. Структура миграции
- Всегда реализуйте `up()` и `down()`
- Используйте транзакции (автоматически)
- Добавляйте подробные сообщения
- Проверяйте существование объектов

### 3. Тестирование
```bash
# Применить миграцию
python migrate.py migrate

# Проверить результат
python migrate.py status

# Откатить для тестирования
python migrate.py rollback --migration 1

# Применить снова
python migrate.py migrate
```

### 4. Безопасность
- Всегда делайте бэкап базы перед миграцией
- Тестируйте миграции на копии данных
- Не изменяйте уже применённые миграции

## 🚨 **Важные особенности**

### Нумерация миграций
- Номер миграции извлекается из имени класса: `Migration001` → `1`
- Миграции применяются в порядке номеров
- Пропуски в нумерации допустимы

### Обработка ошибок
- При ошибке миграция откатывается автоматически
- Последующие миграции не применяются
- Подробная информация об ошибках в консоли

### Поддержка Python Path
- Автоматическое добавление папки миграций в `sys.path`
- Динамическая загрузка модулей миграций
- Кроссплатформенная совместимость

## 🤖 **JSON режим для автоматизации**

JSON режим (`--json`) идеален для:
- **CI/CD пайплайнов** - проверка и применение миграций в автоматическом режиме
- **Мониторинга** - скрипты для отслеживания состояния базы данных  
- **Интеграции** с другими системами и инструментами
- **Парсинга результатов** в скриптах на любом языке программирования

### Структура JSON ответа
Все JSON ответы содержат:
- `success` - булевый флаг успешности операции
- `command` - выполненная команда (`status`, `migrate`, `rollback`)
- `database_path` - путь к используемой базе данных
- `message` - человеко-читаемое сообщение
- При ошибках: `error` - тип ошибки

## 📈 **Развитие системы**

В будущем можно добавить:
- Генератор шаблонов миграций
- Подтверждение перед применением
- Сухой прогон (`--dry-run`)
- Миграции данных (не только схемы)
- Интеграция с системой бэкапов
- Веб-интерфейс для управления миграциями 
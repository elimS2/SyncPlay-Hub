import sqlite3
from pathlib import Path
from typing import Iterator, Optional, Union

DB_PATH = Path(__file__).with_name("tracks.db")

# ---------- Connection helpers ----------

def set_db_path(path: Union[str, Path]):
    """Override default DB path (should be done before get_connection())."""
    global DB_PATH
    DB_PATH = Path(path)

def get_connection():
    """Return sqlite3 connection (creates file/tables if needed)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS playlists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            relpath TEXT NOT NULL UNIQUE,
            track_count INTEGER,
            last_sync_ts TEXT,
            source_url TEXT
        );

        CREATE TABLE IF NOT EXISTS tracks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            relpath TEXT NOT NULL,
            duration REAL,
            size_bytes INTEGER,
            bitrate INTEGER,
            resolution TEXT,
            filetype TEXT,
            play_starts INTEGER DEFAULT 0,
            play_finishes INTEGER DEFAULT 0,
            play_nexts INTEGER DEFAULT 0,
            play_prevs INTEGER DEFAULT 0,
            play_likes INTEGER DEFAULT 0,
            last_start_ts TEXT,
            last_finish_ts TEXT
        );

        CREATE TABLE IF NOT EXISTS track_playlists (
            track_id INTEGER NOT NULL,
            playlist_id INTEGER NOT NULL,
            PRIMARY KEY (track_id, playlist_id),
            FOREIGN KEY (track_id) REFERENCES tracks(id) ON DELETE CASCADE,
            FOREIGN KEY (playlist_id) REFERENCES playlists(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS play_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT NOT NULL,
            event TEXT NOT NULL,
            ts TEXT DEFAULT (datetime('now')),
            position REAL,
            volume_from REAL,
            volume_to REAL,
            seek_from REAL,
            seek_to REAL,
            additional_data TEXT
        );

        CREATE TABLE IF NOT EXISTS user_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            setting_key TEXT NOT NULL UNIQUE,
            setting_value TEXT NOT NULL,
            updated_at TEXT DEFAULT (datetime('now'))
        );
        """
    )
    conn.commit()

    # ---- ensure new columns exist when upgrading older DB ----
    cur.execute("PRAGMA table_info(tracks)")
    cols = {row[1] for row in cur.fetchall()}
    for col in ("play_starts", "play_finishes", "play_nexts", "play_prevs", "play_likes", "last_start_ts", "last_finish_ts"):
        if col not in cols:
            if col.startswith('play_'):
                cur.execute(f"ALTER TABLE tracks ADD COLUMN {col} INTEGER DEFAULT 0")
            else:
                cur.execute(f"ALTER TABLE tracks ADD COLUMN {col} TEXT")
    conn.commit()

    # ensure history table exists (for upgrades before)
    cur.execute("CREATE TABLE IF NOT EXISTS play_history (id INTEGER PRIMARY KEY AUTOINCREMENT, video_id TEXT NOT NULL, event TEXT NOT NULL, ts TEXT DEFAULT (datetime('now')), position REAL)")
    conn.commit()

    cur.execute("PRAGMA table_info(play_history)")
    hcols = {row[1] for row in cur.fetchall()}
    if 'position' not in hcols:
        cur.execute("ALTER TABLE play_history ADD COLUMN position REAL")
    if 'volume_from' not in hcols:
        cur.execute("ALTER TABLE play_history ADD COLUMN volume_from REAL")
    if 'volume_to' not in hcols:
        cur.execute("ALTER TABLE play_history ADD COLUMN volume_to REAL")
    if 'seek_from' not in hcols:
        cur.execute("ALTER TABLE play_history ADD COLUMN seek_from REAL")
    if 'seek_to' not in hcols:
        cur.execute("ALTER TABLE play_history ADD COLUMN seek_to REAL")
    if 'additional_data' not in hcols:
        cur.execute("ALTER TABLE play_history ADD COLUMN additional_data TEXT")
    conn.commit()

    cur.execute("PRAGMA table_info(playlists)")
    cols = {row[1] for row in cur.fetchall()}
    if "track_count" not in cols:
        cur.execute("ALTER TABLE playlists ADD COLUMN track_count INTEGER")
    if "last_sync_ts" not in cols:
        cur.execute("ALTER TABLE playlists ADD COLUMN last_sync_ts TEXT")
    if "source_url" not in cols:
        cur.execute("ALTER TABLE playlists ADD COLUMN source_url TEXT")
    conn.commit()


# ---------- Convenience queries ----------


def upsert_playlist(conn: sqlite3.Connection, name: str, relpath: str, *, track_count: int | None = None, last_sync_ts: str | None = None, source_url: str | None = None) -> int:
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO playlists (name, relpath, track_count, last_sync_ts, source_url)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(relpath) DO UPDATE SET
            name=excluded.name,
            track_count=COALESCE(excluded.track_count, playlists.track_count),
            last_sync_ts=COALESCE(excluded.last_sync_ts, playlists.last_sync_ts),
            source_url=COALESCE(excluded.source_url, playlists.source_url)
        RETURNING id
        """,
        (name, relpath, track_count, last_sync_ts, source_url),
    )
    return cur.fetchone()[0]


def update_playlist_stats(conn: sqlite3.Connection, playlist_id: int, track_count: int):
    conn.execute("UPDATE playlists SET track_count=?, last_sync_ts=datetime('now') WHERE id=?", (track_count, playlist_id))
    conn.commit()


def upsert_track(
    conn: sqlite3.Connection,
    video_id: str,
    name: str,
    relpath: str,
    duration: Optional[float],
    size_bytes: int,
    bitrate: Optional[int],
    resolution: Optional[str],
    filetype: str,
) -> int:
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO tracks (video_id, name, relpath, duration, size_bytes, bitrate, resolution, filetype)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(video_id) DO UPDATE SET
            name=excluded.name,
            relpath=excluded.relpath,
            duration=excluded.duration,
            size_bytes=excluded.size_bytes,
            bitrate=excluded.bitrate,
            resolution=excluded.resolution,
            filetype=excluded.filetype
        RETURNING id
        """,
        (video_id, name, relpath, duration, size_bytes, bitrate, resolution, filetype),
    )
    return cur.fetchone()[0]


def link_track_playlist(conn: sqlite3.Connection, track_id: int, playlist_id: int):
    conn.execute(
        "INSERT OR IGNORE INTO track_playlists (track_id, playlist_id) VALUES (?, ?)",
        (track_id, playlist_id),
    )
    conn.commit()


def iter_tracks_with_playlists(conn: sqlite3.Connection) -> Iterator[sqlite3.Row]:
    """Yield tracks with aggregated playlist names."""
    for row in conn.execute(
        """
        SELECT t.*, GROUP_CONCAT(p.name, ', ') AS playlists
        FROM tracks t
        LEFT JOIN track_playlists tp ON tp.track_id = t.id
        LEFT JOIN playlists p ON p.id = tp.playlist_id
        GROUP BY t.id
        ORDER BY t.name COLLATE NOCASE
        """
    ):
        yield row 


# ---------- Play counts ----------


def record_event(conn: sqlite3.Connection, video_id: str, event: str, position: Optional[float] = None, 
                 volume_from: Optional[float] = None, volume_to: Optional[float] = None, 
                 seek_from: Optional[float] = None, seek_to: Optional[float] = None, additional_data: Optional[str] = None):
    """Record playback or library event and update counters/history.

    Supported events:
        - start, finish, next, prev, like, play, pause  –  coming from the web player
        - volume_change                                 –  volume change events
        - seek                                          –  seek/scrub events (position changes)
        - removed                                       –  file deletion during library sync
        - backup_created                                –  database backup creation
    """
    valid = {"start", "finish", "next", "prev", "like", "play", "pause", "volume_change", "seek", "removed", "backup_created"}
    if event not in valid:
        return
    cur = conn.cursor()
    set_parts = []
    if event == "start":
        set_parts.append("play_starts = play_starts + 1")
        set_parts.append("last_start_ts = datetime('now')")
    elif event == "finish":
        set_parts.append("play_finishes = play_finishes + 1")
        set_parts.append("last_finish_ts = datetime('now')")
    elif event == "next":
        set_parts.append("play_nexts = play_nexts + 1")
    elif event == "prev":
        set_parts.append("play_prevs = play_prevs + 1")
    elif event == "like":
        # check last like within 12h
        like_recent = cur.execute("SELECT 1 FROM play_history WHERE video_id=? AND event='like' AND ts >= datetime('now','-12 hours') LIMIT 1", (video_id,)).fetchone()
        if like_recent:
            # skip counting duplicate like
            return
        set_parts.append("play_likes = play_likes + 1")
    elif event == "removed":
        # no per-track counters, only history log
        pass
    elif event == "backup_created":
        # no per-track counters, only history log
        pass
    if set_parts:
        cur.execute(f"UPDATE tracks SET {', '.join(set_parts)} WHERE video_id = ?", (video_id,))
        conn.commit()

    # log history
    try:
        cur.execute(
            "INSERT INTO play_history (video_id, event, position, volume_from, volume_to, seek_from, seek_to, additional_data) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", 
            (video_id, event, position, volume_from, volume_to, seek_from, seek_to, additional_data)
        )
        conn.commit()
    except sqlite3.IntegrityError as e:
        # Likely due to old CHECK constraint only allowing start/finish
        if "CHECK" in str(e):
            _migrate_history_table(conn)
            cur.execute(
                "INSERT INTO play_history (video_id, event, position, volume_from, volume_to, seek_from, seek_to, additional_data) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", 
                (video_id, event, position, volume_from, volume_to, seek_from, seek_to, additional_data)
            )
            conn.commit()
        else:
            raise


def _migrate_history_table(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("PRAGMA legacy_alter_table=ON")
    cur.execute("ALTER TABLE play_history RENAME TO play_history_old")
    cur.executescript(
        """
        CREATE TABLE play_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT NOT NULL,
            event TEXT NOT NULL,
            ts TEXT DEFAULT (datetime('now')),
            position REAL,
            volume_from REAL,
            volume_to REAL,
            seek_from REAL,
            seek_to REAL,
            additional_data TEXT
        );
        INSERT INTO play_history (video_id, event, ts, position, volume_from, volume_to, seek_from, seek_to, additional_data)
        SELECT video_id, event, ts, position, NULL, NULL, NULL, NULL, NULL FROM play_history_old;
        DROP TABLE play_history_old;
        """
    )
    conn.commit()


# For backward compatibility
def increment_play(conn: sqlite3.Connection, video_id: str, *, started=False, finished=False):
    if started:
        record_event(conn, video_id, "start")
    if finished:
        record_event(conn, video_id, "finish")


def iter_history(conn: sqlite3.Connection, limit: int = 500):
    for row in conn.execute("SELECT * FROM play_history ORDER BY id DESC LIMIT ?", (limit,)):
        yield row


# Pagination


def get_history_page(conn: sqlite3.Connection, page: int = 1, per_page: int = 1000):
    if page < 1:
        page = 1
    offset = (page - 1) * per_page
    cur = conn.cursor()
    cur.execute(
        "SELECT ph.*, t.name FROM play_history ph LEFT JOIN tracks t ON t.video_id = ph.video_id ORDER BY ph.id DESC LIMIT ? OFFSET ?",
        (per_page + 1, offset),
    )
    rows = cur.fetchall()
    has_next = len(rows) > per_page
    return rows[:per_page], has_next 


# ---------- Extra helpers ----------


def get_playlist_by_relpath(conn: sqlite3.Connection, relpath: str):
    return conn.execute("SELECT * FROM playlists WHERE relpath=?", (relpath,)).fetchone()


# ---------- Database Backup Functions ----------

import shutil
import datetime
import os


def create_backup(root_dir: Path) -> dict:
    """Create a backup of the database with timestamp.
    
    Args:
        root_dir: Root directory containing DB folder
        
    Returns:
        dict with backup info: {'success': bool, 'backup_path': str, 'error': str}
    """
    try:
        # Determine base directory - handle both root_dir patterns
        # If root_dir ends with 'Playlists', go up one level to find DB
        if root_dir.name == "Playlists":
            base_dir = root_dir.parent
        else:
            base_dir = root_dir
        
        # Create backup directory structure
        backups_dir = base_dir / "Backups" / "DB"
        backups_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate timestamp folder name (UTC)
        timestamp = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S_UTC")
        backup_folder = backups_dir / timestamp
        backup_folder.mkdir(exist_ok=True)
        
        # Source database path
        db_dir = base_dir / "DB"
        source_db = db_dir / "tracks.db"
        
        if not source_db.exists():
            return {
                'success': False,
                'backup_path': '',
                'error': f'Database not found at {source_db}'
            }
        
        # Backup file path
        backup_db = backup_folder / "tracks.db"
        
        # Create backup using SQLite backup API (safer than file copy)
        source_conn = sqlite3.connect(str(source_db))
        backup_conn = sqlite3.connect(str(backup_db))
        
        # Perform backup
        source_conn.backup(backup_conn)
        
        # Close connections
        backup_conn.close()
        source_conn.close()
        
        # Get backup file size
        backup_size = backup_db.stat().st_size
        
        # Record backup event in history
        try:
            conn = get_connection()
            record_event(conn, "system", "backup_created", position=float(backup_size))
            conn.close()
        except Exception:
            pass  # Don't fail backup if history recording fails
        
        return {
            'success': True,
            'backup_path': str(backup_db),
            'backup_folder': str(backup_folder),
            'timestamp': timestamp,
            'size_bytes': backup_size,
            'error': ''
        }
        
    except Exception as e:
        return {
            'success': False,
            'backup_path': '',
            'error': str(e)
        }


def list_backups(root_dir: Path) -> list:
    """List all database backups with metadata.
    
    Args:
        root_dir: Root directory containing Backups folder
        
    Returns:
        list of backup info dicts sorted by date (newest first)
    """
    try:
        # Handle both root_dir patterns - same logic as create_backup
        if root_dir.name == "Playlists":
            base_dir = root_dir.parent
        else:
            base_dir = root_dir
            
        backups_dir = base_dir / "Backups" / "DB"
        if not backups_dir.exists():
            return []
        
        backups = []
        
        for backup_folder in backups_dir.iterdir():
            if backup_folder.is_dir():
                backup_db = backup_folder / "tracks.db"
                if backup_db.exists():
                    stat = backup_db.stat()
                    
                    # Parse timestamp from folder name
                    try:
                        timestamp_str = backup_folder.name.replace("_UTC", "")
                        backup_datetime = datetime.datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                        backup_datetime = backup_datetime.replace(tzinfo=datetime.timezone.utc)
                    except ValueError:
                        # Fallback to file modification time
                        backup_datetime = datetime.datetime.fromtimestamp(stat.st_mtime, tz=datetime.timezone.utc)
                    
                    backups.append({
                        'folder_name': backup_folder.name,
                        'backup_path': str(backup_db),
                        'timestamp': backup_datetime.isoformat(),
                        'timestamp_display': backup_datetime.strftime("%Y-%m-%d %H:%M:%S UTC"),
                        'size_bytes': stat.st_size,
                        'size_display': _format_file_size(stat.st_size)
                    })
        
        # Sort by timestamp (newest first)
        backups.sort(key=lambda x: x['timestamp'], reverse=True)
        return backups
        
    except Exception:
        return []


def _format_file_size(size_bytes: int) -> str:
    """Format file size in human readable format."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


# ---------- User Settings Functions ----------


def get_user_setting(conn: sqlite3.Connection, setting_key: str, default_value: str = None):
    """Get user setting value by key.
    
    Args:
        conn: Database connection
        setting_key: Setting key to retrieve
        default_value: Default value if setting doesn't exist
        
    Returns:
        Setting value as string or default_value if not found
    """
    cur = conn.cursor()
    result = cur.execute(
        "SELECT setting_value FROM user_settings WHERE setting_key = ?",
        (setting_key,)
    ).fetchone()
    
    if result:
        return result[0]
    return default_value


def set_user_setting(conn: sqlite3.Connection, setting_key: str, setting_value: str):
    """Set or update user setting.
    
    Args:
        conn: Database connection
        setting_key: Setting key to store
        setting_value: Setting value to store
    """
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO user_settings (setting_key, setting_value, updated_at)
        VALUES (?, ?, datetime('now'))
        ON CONFLICT(setting_key) DO UPDATE SET
            setting_value = excluded.setting_value,
            updated_at = datetime('now')
        """,
        (setting_key, setting_value)
    )
    conn.commit()


def get_user_volume(conn: sqlite3.Connection) -> float:
    """Get saved user volume (0.0 to 1.0).
    
    Returns:
        Volume level as float, defaults to 1.0 if not set
    """
    volume_str = get_user_setting(conn, 'volume', '1.0')
    try:
        volume = float(volume_str)
        # Clamp between 0.0 and 1.0
        return max(0.0, min(1.0, volume))
    except (ValueError, TypeError):
        return 1.0


def set_user_volume(conn: sqlite3.Connection, volume: float):
    """Save user volume setting.
    
    Args:
        conn: Database connection
        volume: Volume level (0.0 to 1.0)
    """
    # Clamp between 0.0 and 1.0
    volume = max(0.0, min(1.0, float(volume)))
    set_user_setting(conn, 'volume', str(volume))


def record_volume_change(conn: sqlite3.Connection, video_id: str, volume_from: float, volume_to: float, 
                        position: Optional[float] = None, additional_data: Optional[str] = None):
    """Record volume change event with detailed information.
    
    Args:
        conn: Database connection
        video_id: ID of the track being played (or 'system' for global volume)
        volume_from: Previous volume level (0.0 to 1.0)
        volume_to: New volume level (0.0 to 1.0)
        position: Current playback position in seconds
        additional_data: Additional information (e.g., 'slider', 'remote', 'gesture')
    """
    record_event(
        conn, 
        video_id, 
        'volume_change', 
        position=position,
        volume_from=volume_from,
        volume_to=volume_to,
        additional_data=additional_data
    )


def record_seek_event(conn: sqlite3.Connection, video_id: str, seek_from: float, seek_to: float, 
                     additional_data: Optional[str] = None):
    """Record seek/scrub event with detailed information.
    
    Args:
        conn: Database connection
        video_id: ID of the track being played
        seek_from: Previous playback position in seconds
        seek_to: New playback position in seconds
        additional_data: Additional information (e.g., 'progress_bar', 'remote', 'keyboard')
    """
    record_event(
        conn, 
        video_id, 
        'seek', 
        position=seek_to,  # Store final position in main position field
        seek_from=seek_from,
        seek_to=seek_to,
        additional_data=additional_data
    ) 
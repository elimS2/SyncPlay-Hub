import sqlite3
import time
from pathlib import Path
from typing import Iterator, Optional, Union, List, Dict, Callable, TypeVar

def _load_env_config() -> dict:
    """Load configuration from .env file."""
    config = {}
    project_root = Path(__file__).parent
    env_path = project_root / '.env'
    
    if env_path.exists():
        try:
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip().lstrip('\ufeff')  # Remove BOM
                    if line and '=' in line and not line.startswith('#'):
                        key, value = line.split('=', 1)
                        config[key.strip()] = value.strip()
        except Exception as e:
            print(f"Warning: Failed to load .env file: {e}")
    
    return config

# Initialize DB_PATH from .env file
_env_config = _load_env_config()
DB_PATH = Path(_env_config.get('DB_PATH', 'tracks.db'))

# ---------- Connection helpers ----------

def set_db_path(path: Union[str, Path]):
    """Override default DB path (should be done before get_connection())."""
    global DB_PATH
    DB_PATH = Path(path)

def get_connection(timeout: float = 30.0):
    """Return sqlite3 connection (creates file/tables if needed).

    Applies connection-level PRAGMAs for better concurrency and stability.
    """
    # Create connection with busy timeout
    conn = sqlite3.connect(DB_PATH, timeout=timeout)
    # Enable autocommit to minimize transaction lifetimes and reduce lock contention
    try:
        conn.isolation_level = None
    except Exception:
        pass
    conn.row_factory = sqlite3.Row

    # Apply recommended PRAGMAs per-connection (low risk defaults)
    try:
        cur = conn.cursor()
        # Enable foreign keys
        cur.execute("PRAGMA foreign_keys = ON")
        # Prefer WAL for concurrent readers/writers
        cur.execute("PRAGMA journal_mode = WAL")
        # Balance durability and performance
        cur.execute("PRAGMA synchronous = NORMAL")
        # Ensure SQLite waits before raising SQLITE_BUSY
        cur.execute(f"PRAGMA busy_timeout = {int(timeout * 1000)}")
        # Optional performance tweaks (safe on modern SQLite)
        cur.execute("PRAGMA temp_store = MEMORY")
        cur.execute("PRAGMA cache_size = -64000")  # 64MB
        cur.execute("PRAGMA mmap_size = 268435456")  # 256MB
        # Let SQLite auto-optimize
        cur.execute("PRAGMA optimize")
    except Exception:
        # Don't fail connection creation if PRAGMAs are not supported
        pass
    finally:
        try:
            cur.close()
        except Exception:
            pass

    _ensure_schema(conn)
    return conn


# ---------- Retry helpers ----------

T = TypeVar("T")


def execute_with_retry(
    operation: Callable[[], T],
    *,
    max_attempts: int = 5,
    base_delay_ms: int = 100,
) -> T:
    """Execute callable with retries on transient SQLite lock errors.

    Retries sqlite3.OperationalError when error message indicates a lock/busy state.
    Uses exponential backoff with a small initial delay.

    Args:
        operation: Callable that performs the database operation and returns a value.
        max_attempts: Maximum number of attempts (including the first try).
        base_delay_ms: Initial delay between retries in milliseconds.

    Returns:
        The result of the operation if successful.

    Raises:
        Re-raises the last exception if not considered transient or attempts exhausted.
    """
    attempt_number = 1
    delay_seconds = max(0.0, base_delay_ms / 1000.0)

    while True:
        try:
            return operation()
        except sqlite3.OperationalError as error:
            message = str(error).lower()
            is_transient = any(
                token in message
                for token in (
                    "database is locked",
                    "database is busy",
                    "schema is locked",
                    "table is locked",
                )
            )

            if not is_transient or attempt_number >= max_attempts:
                raise

            time.sleep(delay_seconds)
            attempt_number += 1
            delay_seconds = min(delay_seconds * 2.0, 1.0)


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

        -- New tables for channel system --
        CREATE TABLE IF NOT EXISTS channel_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            behavior_type TEXT NOT NULL DEFAULT 'music',
            play_order TEXT NOT NULL DEFAULT 'random',
            auto_delete_enabled BOOLEAN DEFAULT 0,
            include_in_likes BOOLEAN DEFAULT 1,
            folder_path TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            url TEXT NOT NULL UNIQUE,
            channel_group_id INTEGER,
            date_from TEXT,
            enabled BOOLEAN DEFAULT 1,
            last_sync_ts TEXT,
            track_count INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (channel_group_id) REFERENCES channel_groups(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS deleted_tracks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT NOT NULL,
            original_name TEXT NOT NULL,
            original_relpath TEXT NOT NULL,
            deleted_at TEXT DEFAULT (datetime('now')),
            deletion_reason TEXT DEFAULT 'manual',
            channel_group TEXT,
            trash_path TEXT,
            can_restore BOOLEAN DEFAULT 1,
            restored_at TEXT,
            additional_data TEXT
        );

        -- YouTube Video Metadata Table --
        CREATE TABLE IF NOT EXISTS youtube_video_metadata (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            _type TEXT,
            ie_key TEXT,
            youtube_id TEXT NOT NULL UNIQUE,
            url TEXT,
            title TEXT,
            description TEXT,
            duration REAL,
            channel_id TEXT,
            channel TEXT,
            channel_url TEXT,
            uploader TEXT,
            uploader_id TEXT,
            uploader_url TEXT,
            timestamp INTEGER,
            release_timestamp INTEGER,
            availability TEXT,
            view_count INTEGER,
            live_status TEXT,
            channel_is_verified BOOLEAN,
            __x_forwarded_for_ip TEXT,
            webpage_url TEXT,
            original_url TEXT,
            webpage_url_basename TEXT,
            webpage_url_domain TEXT,
            extractor TEXT,
            extractor_key TEXT,
            playlist_count INTEGER,
            playlist TEXT,
            playlist_id TEXT,
            playlist_title TEXT,
            playlist_uploader TEXT,
            playlist_uploader_id TEXT,
            playlist_channel TEXT,
            playlist_channel_id TEXT,
            playlist_webpage_url TEXT,
            n_entries INTEGER,
            playlist_index INTEGER,
            __last_playlist_index INTEGER,
            playlist_autonumber INTEGER,
            epoch INTEGER,
            duration_string TEXT,
            release_year INTEGER,
            -- New fields for YouTube available formats
            available_formats TEXT,
            available_qualities_summary TEXT,
            created_at TEXT DEFAULT (datetime('now')),
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
    
    # Add new channel-related columns to tracks table
    for col in ("published_date", "duration_seconds", "channel_group", "auto_delete_after_finish"):
        if col not in cols:
            if col == "duration_seconds":
                cur.execute(f"ALTER TABLE tracks ADD COLUMN {col} INTEGER")
            elif col == "auto_delete_after_finish":
                cur.execute(f"ALTER TABLE tracks ADD COLUMN {col} BOOLEAN DEFAULT 0")
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

    # Add new include_in_likes column to channel_groups table
    cur.execute("PRAGMA table_info(channel_groups)")
    channel_groups_cols = {row[1] for row in cur.fetchall()}
    if "include_in_likes" not in channel_groups_cols:
        cur.execute("ALTER TABLE channel_groups ADD COLUMN include_in_likes BOOLEAN DEFAULT 1")
    conn.commit()

    # Add new columns for youtube_video_metadata if missing (upgrades)
    cur.execute("PRAGMA table_info(youtube_video_metadata)")
    ycols = {row[1] for row in cur.fetchall()}
    if "available_formats" not in ycols:
        cur.execute("ALTER TABLE youtube_video_metadata ADD COLUMN available_formats TEXT")
    if "available_qualities_summary" not in ycols:
        cur.execute("ALTER TABLE youtube_video_metadata ADD COLUMN available_qualities_summary TEXT")
    conn.commit()

    # Ensure valid event types include new channel events
    _add_valid_event_types()


def _add_valid_event_types():
    """Add new event types for channel system"""
    # This will be used in record_event validation
    pass


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


def update_track_media_properties(
    conn: sqlite3.Connection,
    video_id: str,
    *,
    bitrate: Optional[int] = None,
    resolution: Optional[str] = None,
    duration: Optional[float] = None,
    size_bytes: Optional[int] = None,
) -> bool:
    """
    Partially update media-related properties for a track identified by video_id.

    Only provided keyword arguments will be updated. If no fields are provided,
    the function is a no-op and returns False.

    Returns True when an UPDATE was executed (rows may still be 0 if video_id
    does not exist), False when nothing to update.
    """
    set_parts = []
    params: list = []

    if duration is not None:
        set_parts.append("duration = ?")
        params.append(duration)
    if size_bytes is not None:
        set_parts.append("size_bytes = ?")
        params.append(size_bytes)
    if bitrate is not None:
        set_parts.append("bitrate = ?")
        params.append(bitrate)
    if resolution is not None:
        set_parts.append("resolution = ?")
        params.append(resolution)

    if not set_parts:
        return False

    sql = f"UPDATE tracks SET {', '.join(set_parts)} WHERE video_id = ?"
    params.append(video_id)

    cur = conn.cursor()
    cur.execute(sql, tuple(params))
    conn.commit()
    return True

def link_track_playlist(conn: sqlite3.Connection, track_id: int, playlist_id: int):
    """Link track to playlist and log the event if it's a new association."""
    cur = conn.cursor()
    
    # Check if this track-playlist link already exists
    existing = cur.execute(
        "SELECT 1 FROM track_playlists WHERE track_id = ? AND playlist_id = ?",
        (track_id, playlist_id)
    ).fetchone()
    
    if not existing:
        # This is a new association - insert and log it
        cur.execute(
            "INSERT INTO track_playlists (track_id, playlist_id) VALUES (?, ?)",
            (track_id, playlist_id),
        )
        
        # Get track video_id and playlist name for logging
        track_info = cur.execute(
            "SELECT video_id FROM tracks WHERE id = ?", (track_id,)
        ).fetchone()
        
        playlist_info = cur.execute(
            "SELECT name FROM playlists WHERE id = ?", (playlist_id,)
        ).fetchone()
        
        if track_info and playlist_info:
            video_id = track_info[0]
            playlist_name = playlist_info[0]
            
            # Log the playlist addition event
            record_playlist_addition(conn, video_id, playlist_id, playlist_name, source="scan")
        
        conn.commit()


def iter_tracks_with_playlists(conn: sqlite3.Connection, search_query: str = None, include_deleted: bool = False) -> Iterator[sqlite3.Row]:
    """Yield tracks with aggregated playlist names, using YouTube metadata title if available.
    
    Args:
        conn: Database connection
        search_query: Optional search query to filter tracks by title (case-insensitive)
        include_deleted: Whether to include deleted tracks in results (default: False)
    """
    base_query = """
        SELECT t.*, 
               GROUP_CONCAT(p.name, ', ') AS playlists,
               COALESCE(ym.title, t.name) AS display_name,
               CASE 
                   WHEN dt.video_id IS NOT NULL THEN 1 
                   ELSE 0 
               END AS is_deleted,
               dt.deleted_at AS deletion_date,
               dt.deletion_reason AS deletion_reason
        FROM tracks t
        LEFT JOIN track_playlists tp ON tp.track_id = t.id
        LEFT JOIN playlists p ON p.id = tp.playlist_id
        LEFT JOIN youtube_video_metadata ym ON ym.youtube_id = t.video_id
        LEFT JOIN deleted_tracks dt ON dt.video_id = t.video_id
        GROUP BY t.id
        ORDER BY COALESCE(ym.title, t.name) COLLATE NOCASE
    """
    
    # Get all tracks first
    for row in conn.execute(base_query):
        # Apply deleted filter
        if not include_deleted and row['is_deleted']:
            continue
            
        # If no search query, yield matching tracks
        if not search_query:
            yield row
        else:
            # Perform case-insensitive search in Python for proper Unicode support
            display_name = row['display_name'] or ''
            search_term = search_query.strip().lower()
            if search_term in display_name.lower():
                yield row


# ---------- Single track fetcher ----------

def get_track_with_playlists(conn: sqlite3.Connection, video_id: str) -> Optional[Dict]:
    """Return a single track with aggregated playlist information.

    Combines core track fields from `tracks` with:
    - playlist_count: number of associated playlists
    - playlists: comma-separated playlist names for display
    - playlists_list: list of playlist names (stable separator)
    - playlist_relpaths_list: list of playlist relpaths for linking
    - is_deleted, deletion_date, deletion_reason from deleted_tracks

    Args:
        conn: Database connection
        video_id: YouTube video ID

    Returns:
        dict with track and aggregation fields, or None if not found
    """
    cur = conn.cursor()
    # Use custom separators that are unlikely to appear in names/paths
    name_sep = '|||'
    path_sep = '||/'
    row = cur.execute(
        f"""
        SELECT 
            t.*,
            COUNT(DISTINCT p.id) AS playlist_count,
            GROUP_CONCAT(p.name, '{name_sep}') AS playlist_names_concat,
            GROUP_CONCAT(p.relpath, '{path_sep}') AS playlist_relpaths_concat,
            CASE WHEN dt.video_id IS NOT NULL THEN 1 ELSE 0 END AS is_deleted,
            dt.deleted_at AS deletion_date,
            dt.deletion_reason AS deletion_reason
        FROM tracks t
        LEFT JOIN track_playlists tp ON tp.track_id = t.id
        LEFT JOIN playlists p ON p.id = tp.playlist_id
        LEFT JOIN deleted_tracks dt ON dt.video_id = t.video_id
        WHERE t.video_id = ?
        GROUP BY t.id
        LIMIT 1
        """,
        (video_id,),
    ).fetchone()

    if not row:
        return None

    result: Dict = dict(row)

    # Build readable playlists string and lists
    names_concat = result.pop('playlist_names_concat', None)
    relpaths_concat = result.pop('playlist_relpaths_concat', None)

    if names_concat:
        names_list = names_concat.split(name_sep)
        result['playlists_list'] = names_list
        # Human-readable comma+space separated string
        result['playlists'] = ', '.join(names_list)
    else:
        result['playlists_list'] = []
        result['playlists'] = ''

    if relpaths_concat:
        result['playlist_relpaths_list'] = relpaths_concat.split(path_sep)
    else:
        result['playlist_relpaths_list'] = []

    # Normalize boolean-ish field
    result['is_deleted'] = bool(result.get('is_deleted'))

    return result

# ---------- Play counts ----------


def record_event(conn: sqlite3.Connection, video_id: str, event: str, position: Optional[float] = None, 
                 volume_from: Optional[float] = None, volume_to: Optional[float] = None, 
                 seek_from: Optional[float] = None, seek_to: Optional[float] = None, additional_data: Optional[str] = None):
    """Record playback or library event and update counters/history.

    Supported events:
        - start, finish, next, prev, like, dislike, play, pause  –  coming from the web player
        - volume_change                                          –  volume change events
        - seek                                                   –  seek/scrub events (position changes)
        - playlist_added                                         –  track added/discovered in playlist
        - removed                                                –  file deletion during library sync
        - backup_created                                         –  database backup creation
        - channel_downloaded                                     –  channel content downloaded
        - track_restored                                         –  track restoration from deleted tracks
        - bulk_track_restore                                     –  bulk track restoration operation
    """
    valid = {"start", "finish", "next", "prev", "like", "dislike", "play", "pause", "volume_change", "seek", "playlist_added", "removed", "backup_created", "channel_downloaded", "track_restored", "bulk_track_restore"}
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
    elif event == "dislike":
        # check last dislike within 12h
        dislike_recent = cur.execute("SELECT 1 FROM play_history WHERE video_id=? AND event='dislike' AND ts >= datetime('now','-12 hours') LIMIT 1", (video_id,)).fetchone()
        if dislike_recent:
            # skip counting duplicate dislike
            return
        # Note: dislike doesn't increment a counter like likes do, just records the event
    elif event == "playlist_added":
        # no per-track counters, only history log
        pass
    elif event == "removed":
        # no per-track counters, only history log
        pass
    elif event == "backup_created":
        # no per-track counters, only history log
        pass
    elif event == "track_restored":
        # no per-track counters, only history log
        pass
    elif event == "bulk_track_restore":
        # no per-track counters, only history log
        pass
    if set_parts:
        def _update_track_counters() -> bool:
            cur.execute(
                f"UPDATE tracks SET {', '.join(set_parts)} WHERE video_id = ?",
                (video_id,)
            )
            conn.commit()
            return True

        execute_with_retry(_update_track_counters)

    # log history
    try:
        def _insert_history() -> bool:
            cur.execute(
                "INSERT INTO play_history (video_id, event, position, volume_from, volume_to, seek_from, seek_to, additional_data) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", 
                (video_id, event, position, volume_from, volume_to, seek_from, seek_to, additional_data)
            )
            conn.commit()
            return True

        execute_with_retry(_insert_history)
    except sqlite3.IntegrityError as e:
        # Likely due to old CHECK constraint only allowing start/finish
        if "CHECK" in str(e):
            _migrate_history_table(conn)
            def _reinsert_history() -> bool:
                cur.execute(
                    "INSERT INTO play_history (video_id, event, position, volume_from, volume_to, seek_from, seek_to, additional_data) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", 
                    (video_id, event, position, volume_from, volume_to, seek_from, seek_to, additional_data)
                )
                conn.commit()
                return True

            execute_with_retry(_reinsert_history)
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


def get_history_page(conn: sqlite3.Connection, page: int = 1, per_page: int = 1000, 
                     event_types: list = None, track_filter: str = None, video_id_filter: str = None):
    """Get paginated history with optional server-side filtering.
    
    Args:
        conn: Database connection
        page: Page number (1-based)
        per_page: Items per page
        event_types: List of event types to include (e.g. ['like', 'start'])
        track_filter: Filter by track name (partial match)
        video_id_filter: Filter by video ID (partial match)
        
    Returns:
        tuple: (rows, has_next)
    """
    if page < 1:
        page = 1
    offset = (page - 1) * per_page
    
    # Build WHERE clause based on filters
    where_conditions = []
    params = []
    
    # Event type filter
    if event_types is not None:  # Filter was specified
        if event_types:  # Non-empty list
            placeholders = ','.join('?' * len(event_types))
            where_conditions.append(f"ph.event IN ({placeholders})")
            params.extend(event_types)
        else:  # Empty list - show no events
            where_conditions.append("1 = 0")  # Always false condition
    
    # Track name filter
    if track_filter:
        where_conditions.append("t.name LIKE ?")
        params.append(f"%{track_filter}%")
    
    # Video ID filter
    if video_id_filter:
        where_conditions.append("ph.video_id LIKE ?")
        params.append(f"%{video_id_filter}%")
    
    # Construct SQL query with YouTube metadata
    base_query = """SELECT ph.*, 
                           COALESCE(ym.title, t.name) as name,
                           ym.duration as youtube_duration,
                           ym.duration_string as youtube_duration_string,
                           ym.channel as youtube_channel,
                           ym.view_count as youtube_view_count
                    FROM play_history ph 
                    LEFT JOIN tracks t ON t.video_id = ph.video_id
                    LEFT JOIN youtube_video_metadata ym ON ym.youtube_id = ph.video_id"""
    
    if where_conditions:
        base_query += " WHERE " + " AND ".join(where_conditions)
    
    base_query += " ORDER BY ph.id DESC LIMIT ? OFFSET ?"
    params.extend([per_page + 1, offset])
    
    cur = conn.cursor()
    cur.execute(base_query, params)
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

    def _upsert_setting() -> bool:
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
        return True

    execute_with_retry(_upsert_setting)


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


def record_playlist_addition(conn: sqlite3.Connection, video_id: str, playlist_id: int, playlist_name: str, 
                           source: Optional[str] = None):
    """Record playlist addition event with detailed information.
    
    Args:
        conn: Database connection
        video_id: ID of the track being added
        playlist_id: ID of the playlist
        playlist_name: Name of the playlist
        source: Source of addition (e.g., 'scan', 'download', 'manual')
    """
    additional_data = f"playlist_id:{playlist_id},playlist_name:{playlist_name}"
    if source:
        additional_data += f",source:{source}"
    
    record_event(
        conn, 
        video_id, 
        'playlist_added', 
        additional_data=additional_data
    )


def migrate_existing_playlist_associations(conn: sqlite3.Connection, dry_run: bool = False):
    """Migrate existing track-playlist associations to playlist_added events.
    
    This function creates playlist_added events for all existing track-playlist
    links that don't already have corresponding events in the history.
    
    Args:
        conn: Database connection
        dry_run: If True, only count what would be migrated without actually doing it
        
    Returns:
        dict with migration statistics
    """
    cur = conn.cursor()
    
    # Get all existing track-playlist associations with track and playlist info
    cur.execute("""
        SELECT tp.track_id, tp.playlist_id, t.video_id, p.name as playlist_name
        FROM track_playlists tp
        JOIN tracks t ON t.id = tp.track_id
        JOIN playlists p ON p.id = tp.playlist_id
        ORDER BY tp.track_id, tp.playlist_id
    """)
    
    associations = cur.fetchall()
    total_associations = len(associations)
    
    if dry_run:
        return {
            'total_associations': total_associations,
            'would_migrate': total_associations,
            'dry_run': True
        }
    
    # Create playlist_added events for all associations
    migrated_count = 0
    for track_id, playlist_id, video_id, playlist_name in associations:
        try:
            record_playlist_addition(
                conn, 
                video_id, 
                playlist_id, 
                playlist_name, 
                source="migration"
            )
            migrated_count += 1
        except Exception as e:
            print(f"Error migrating track {video_id} to playlist {playlist_name}: {e}")
            continue
    
    return {
        'total_associations': total_associations,
        'migrated': migrated_count,
        'dry_run': False
    } 


# ---------- Channel System Functions ----------


def create_channel_group(conn: sqlite3.Connection, name: str, behavior_type: str = 'music', 
                        play_order: str = 'random', auto_delete_enabled: bool = False, 
                        include_in_likes: bool = True, folder_path: str = None) -> int:
    """Create a new channel group.
    
    Args:
        conn: Database connection
        name: Group name (e.g., 'Music', 'News', 'Education')
        behavior_type: Type of behavior ('music', 'news', 'education', 'podcasts')
        play_order: Play order ('random', 'chronological_newest', 'chronological_oldest')
        auto_delete_enabled: Whether to auto-delete tracks after finish
        include_in_likes: Whether to include tracks from this group in likes playlists
        folder_path: Path to the group folder
        
    Returns:
        ID of created channel group
    """
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO channel_groups (name, behavior_type, play_order, auto_delete_enabled, include_in_likes, folder_path)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (name, behavior_type, play_order, auto_delete_enabled, include_in_likes, folder_path)
    )
    conn.commit()
    return cur.lastrowid


def get_channel_groups(conn: sqlite3.Connection):
    """Get all channel groups with channel counts."""
    cur = conn.cursor()
    cur.execute("""
        SELECT 
            cg.id, cg.name, cg.behavior_type, cg.play_order, 
            cg.auto_delete_enabled, cg.include_in_likes, cg.folder_path, cg.created_at,
            COUNT(c.id) as channel_count,
            COALESCE(SUM(c.track_count), 0) as total_tracks
        FROM channel_groups cg
        LEFT JOIN channels c ON c.channel_group_id = cg.id AND c.enabled = 1
        GROUP BY cg.id, cg.name, cg.behavior_type, cg.play_order, 
                 cg.auto_delete_enabled, cg.include_in_likes, cg.folder_path, cg.created_at
        ORDER BY cg.name
    """)
    rows = cur.fetchall()
    
    # Convert rows to dictionaries for JSON serialization
    groups = []
    for row in rows:
        groups.append({
            'id': row[0],
            'name': row[1],
            'behavior_type': row[2],
            'play_order': row[3],
            'auto_delete_enabled': bool(row[4]),
            'include_in_likes': bool(row[5]),
            'folder_path': row[6],
            'created_at': row[7],
            'channel_count': row[8],
            'total_tracks': row[9]
        })
    return groups


def get_channel_group_by_id(conn: sqlite3.Connection, group_id: int):
    """Get channel group by ID."""
    cur = conn.cursor()
    cur.execute("SELECT * FROM channel_groups WHERE id = ?", (group_id,))
    return cur.fetchone()


def update_channel_group(conn: sqlite3.Connection, group_id: int, **kwargs):
    """Update channel group settings.
    
    Args:
        conn: Database connection
        group_id: ID of the group to update
        **kwargs: Fields to update (name, behavior_type, play_order, auto_delete_enabled, include_in_likes, folder_path)
    
    Returns:
        True if group was updated, False if not found
    """
    cur = conn.cursor()
    
    # Check if group exists
    if not get_channel_group_by_id(conn, group_id):
        return False
    
    # Build update query dynamically
    valid_fields = {'name', 'behavior_type', 'play_order', 'auto_delete_enabled', 'include_in_likes', 'folder_path'}
    update_fields = {k: v for k, v in kwargs.items() if k in valid_fields}
    
    if not update_fields:
        return False
    
    # Add updated_at timestamp
    update_fields['updated_at'] = 'datetime("now")'
    
    set_clause = ', '.join([f'{k} = ?' if k != 'updated_at' else f'{k} = {v}' for k, v in update_fields.items()])
    values = [v for k, v in update_fields.items() if k != 'updated_at']
    values.append(group_id)
    
    cur.execute(f"UPDATE channel_groups SET {set_clause} WHERE id = ?", values)
    conn.commit()
    
    return cur.rowcount > 0


def delete_channel_group(conn: sqlite3.Connection, group_id: int) -> bool:
    """Delete a channel group (only if it has no channels).
    
    Args:
        conn: Database connection
        group_id: ID of the group to delete
        
    Returns:
        True if group was deleted, False if it has channels or doesn't exist
    """
    cur = conn.cursor()
    
    # Check if group exists and has no channels
    cur.execute("""
        SELECT cg.id, COUNT(c.id) as channel_count
        FROM channel_groups cg
        LEFT JOIN channels c ON c.channel_group_id = cg.id AND c.enabled = 1
        WHERE cg.id = ?
        GROUP BY cg.id
    """, (group_id,))
    
    result = cur.fetchone()
    if not result:
        return False  # Group doesn't exist
    
    _, channel_count = result
    if channel_count > 0:
        return False  # Group has channels, cannot delete
    
    # Delete the group
    cur.execute("DELETE FROM channel_groups WHERE id = ?", (group_id,))
    conn.commit()
    
    return cur.rowcount > 0


def create_channel(conn: sqlite3.Connection, name: str, url: str, channel_group_id: int,
                  date_from: str = None, enabled: bool = True) -> int:
    """Create a new channel.
    
    Args:
        conn: Database connection
        name: Channel name (extracted from URL or custom)
        url: YouTube channel URL
        channel_group_id: ID of the channel group
        date_from: Download videos from this date (YYYY-MM-DD format)
        enabled: Whether channel is enabled for syncing
        
    Returns:
        ID of created channel
    """
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO channels (name, url, channel_group_id, date_from, enabled)
        VALUES (?, ?, ?, ?, ?)
        """,
        (name, url, channel_group_id, date_from, enabled)
    )
    conn.commit()
    return cur.lastrowid


def get_channels_by_group(conn: sqlite3.Connection, group_id: int):
    """Get all channels in a group."""
    cur = conn.cursor()
    cur.execute("""
        SELECT 
            c.*, 
            cg.name as group_name,
            cg.behavior_type,
            cg.auto_delete_enabled
        FROM channels c
        JOIN channel_groups cg ON cg.id = c.channel_group_id
        WHERE c.channel_group_id = ?
        ORDER BY c.last_sync_ts ASC NULLS FIRST, c.name
    """, (group_id,))
    return cur.fetchall()


def get_channel_by_url(conn: sqlite3.Connection, url: str):
    """Get channel by URL with group information."""
    cur = conn.cursor()
    cur.execute("""
        SELECT c.*, cg.name as group_name 
        FROM channels c
        LEFT JOIN channel_groups cg ON c.channel_group_id = cg.id
        WHERE c.url = ?
    """, (url,))
    return cur.fetchone()


def get_channel_by_id(conn: sqlite3.Connection, channel_id: int):
    """Get channel by ID with group information."""
    cur = conn.cursor()
    cur.execute("""
        SELECT c.*, cg.name as group_name 
        FROM channels c
        LEFT JOIN channel_groups cg ON c.channel_group_id = cg.id
        WHERE c.id = ?
    """, (channel_id,))
    return cur.fetchone()


def update_channel_sync(conn: sqlite3.Connection, channel_id: int, track_count: int):
    """Update channel sync timestamp and track count."""
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE channels 
        SET last_sync_ts = datetime('now'), track_count = ? 
        WHERE id = ?
        """,
        (track_count, channel_id)
    )
    conn.commit()


def record_track_deletion(conn: sqlite3.Connection, video_id: str, original_name: str,
                         original_relpath: str, deletion_reason: str = 'auto_delete',
                         channel_group: str = None, trash_path: str = None,
                         additional_data: str = None):
    """Record a track deletion for potential restoration.
    
    Args:
        conn: Database connection
        video_id: Video ID of deleted track
        original_name: Original track name
        original_relpath: Original file path
        deletion_reason: Reason for deletion ('auto_delete', 'manual_delete', 'sync_removal')
        channel_group: Name of channel group (for organization)
        trash_path: Path in trash folder
        additional_data: Additional context data
    """
    cur = conn.cursor()

    def _insert_deleted() -> bool:
        cur.execute(
            """
            INSERT INTO deleted_tracks 
            (video_id, original_name, original_relpath, deletion_reason, 
             channel_group, trash_path, additional_data)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (video_id, original_name, original_relpath, deletion_reason,
             channel_group, trash_path, additional_data)
        )
        conn.commit()
        return True

    execute_with_retry(_insert_deleted)
    
    # Also record as event in play_history
    record_event(conn, video_id, 'auto_deleted' if deletion_reason == 'auto_delete' else 'removed',
                additional_data=f"reason:{deletion_reason},trash_path:{trash_path}")


def get_deleted_tracks(conn: sqlite3.Connection, channel_group: str = None, 
                      days_back: int = None, page: int = 1, per_page: int = 50):
    """Get deleted tracks for restoration interface with pagination.
    
    Args:
        conn: Database connection
        channel_group: Filter by channel group name
        days_back: How many days back to search (None = all time)
        page: Page number (1-based)
        per_page: Number of results per page
        
    Returns:
        Tuple of (tracks_list, total_count)
    """
    cur = conn.cursor()
    
    # Base query for counting total results
    count_query = """
        SELECT COUNT(*) 
        FROM deleted_tracks dt
        WHERE 1=1
    """
    
    # Base query for getting results
    query = """
        SELECT 
            dt.*,
            CASE 
                WHEN dt.trash_path IS NOT NULL AND dt.can_restore = 1 
                THEN 'file_restore'
                ELSE 're_download'
            END as restoration_method,
            COALESCE(ym.title, dt.original_name) AS display_name
        FROM deleted_tracks dt
        LEFT JOIN youtube_video_metadata ym ON ym.youtube_id = dt.video_id
        WHERE 1=1
    """
    
    params = []
    count_params = []
    
    # Add date filter if specified
    if days_back is not None:
        date_filter = " AND dt.deleted_at >= datetime('now', '-{} days')".format(days_back)
        query += date_filter
        count_query += date_filter
    
    # Add channel group filter if specified
    if channel_group:
        group_filter = " AND dt.channel_group = ?"
        query += group_filter
        count_query += group_filter
        params.append(channel_group)
        count_params.append(channel_group)
    
    # Get total count
    cur.execute(count_query, count_params)
    total_count = cur.fetchone()[0]
    
    # Add ordering and pagination
    offset = (page - 1) * per_page
    query += " ORDER BY dt.deleted_at DESC LIMIT ? OFFSET ?"
    params.extend([per_page, offset])
    
    cur.execute(query, params)
    tracks = cur.fetchall()
    
    return tracks, total_count


def restore_deleted_track(conn: sqlite3.Connection, deleted_track_id: int):
    """Mark a deleted track as restored.
    
    Args:
        conn: Database connection
        deleted_track_id: ID of the deleted track record
    """
    cur = conn.cursor()

    def _mark_restored() -> bool:
        cur.execute(
            """
            UPDATE deleted_tracks 
            SET restored_at = datetime('now'), can_restore = 0
            WHERE id = ?
            """,
            (deleted_track_id,)
        )
        conn.commit()
        return True

    execute_with_retry(_mark_restored)


def should_auto_delete_track(conn: sqlite3.Connection, video_id: str) -> bool:
    """Check if track should be auto-deleted based on its channel group settings.
    
    Args:
        conn: Database connection
        video_id: Video ID to check
        
    Returns:
        True if track should be auto-deleted, False otherwise
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT t.auto_delete_after_finish, cg.auto_delete_enabled
        FROM tracks t
        LEFT JOIN channels c ON c.url LIKE '%' || SUBSTR(t.relpath, 1, INSTR(t.relpath, '/') - 1) || '%'
        LEFT JOIN channel_groups cg ON cg.id = c.channel_group_id
        WHERE t.video_id = ?
    """, (video_id,))
    
    result = cur.fetchone()
    if result:
        track_setting = result[0]  # Individual track setting
        group_setting = result[1]  # Channel group setting
        
        # Individual track setting overrides group setting
        if track_setting is not None:
            return bool(track_setting)
        
        # Fall back to group setting
        return bool(group_setting) if group_setting is not None else False
    
    return False


def record_channel_added(conn: sqlite3.Connection, channel_url: str, channel_name: str, 
                        group_name: str, additional_data: str = None):
    """Record channel addition event."""
    event_data = f"channel_name:{channel_name},group:{group_name}"
    if additional_data:
        event_data += f",{additional_data}"
    
    record_event(conn, 'system', 'channel_added', additional_data=event_data)


def record_channel_synced(conn: sqlite3.Connection, channel_url: str, channel_name: str, 
                         tracks_added: int, tracks_total: int, additional_data: str = None):
    """Record channel sync event."""
    event_data = f"channel_name:{channel_name},tracks_added:{tracks_added},tracks_total:{tracks_total}"
    if additional_data:
        event_data += f",{additional_data}"
    
    record_event(conn, 'system', 'channel_synced', additional_data=event_data) 


# ---------- YouTube Video Metadata Functions ----------

def upsert_youtube_metadata(conn: sqlite3.Connection, metadata: dict) -> int:
    """Insert or update YouTube video metadata"""
    cur = conn.cursor()
    
    # Extract all fields from metadata dict
    fields = [
        '_type', 'ie_key', 'youtube_id', 'url', 'title', 'description', 'duration',
        'channel_id', 'channel', 'channel_url', 'uploader', 'uploader_id', 'uploader_url',
        'timestamp', 'release_timestamp', 'availability', 'view_count', 'live_status',
        'channel_is_verified', '__x_forwarded_for_ip', 'webpage_url', 'original_url',
        'webpage_url_basename', 'webpage_url_domain', 'extractor', 'extractor_key',
        'playlist_count', 'playlist', 'playlist_id', 'playlist_title', 'playlist_uploader',
        'playlist_uploader_id', 'playlist_channel', 'playlist_channel_id', 'playlist_webpage_url',
        'n_entries', 'playlist_index', '__last_playlist_index', 'playlist_autonumber',
        'epoch', 'duration_string', 'release_year',
        # New available qualities fields
        'available_formats', 'available_qualities_summary'
    ]
    
    # Build column list and value placeholders
    columns = ', '.join(fields)
    placeholders = ', '.join(['?' for _ in fields])
    update_clause = ', '.join([f'{field}=excluded.{field}' for field in fields if field != 'youtube_id'])
    
    values = [metadata.get(field) for field in fields]
    
    cur.execute(f"""
        INSERT INTO youtube_video_metadata ({columns}, updated_at)
        VALUES ({placeholders}, datetime('now'))
        ON CONFLICT(youtube_id) DO UPDATE SET
            {update_clause},
            updated_at=datetime('now')
        RETURNING id
    """, values)
    
    result = cur.fetchone()
    conn.commit()
    return result[0] if result else None


def get_youtube_metadata_by_id(conn: sqlite3.Connection, youtube_id: str) -> Optional[sqlite3.Row]:
    """Get YouTube video metadata by video ID"""
    cur = conn.cursor()
    cur.execute("SELECT * FROM youtube_video_metadata WHERE youtube_id = ?", (youtube_id,))
    return cur.fetchone()


def get_youtube_metadata_batch(conn: sqlite3.Connection, video_ids: List[str]) -> Dict[str, sqlite3.Row]:
    """Get YouTube metadata for multiple video IDs in single query for performance optimization"""
    if not video_ids:
        return {}
    
    # Remove duplicates while preserving order
    unique_ids = list(dict.fromkeys(video_ids))
    
    placeholders = ','.join(['?' for _ in unique_ids])
    query = f"SELECT * FROM youtube_video_metadata WHERE youtube_id IN ({placeholders})"
    
    cur = conn.cursor()
    cur.execute(query, unique_ids)
    
    result = {}
    for row in cur.fetchall():
        result[row['youtube_id']] = row
    
    return result


def get_track_stats_batch(conn: sqlite3.Connection, video_ids: List[str]) -> Dict[str, dict]:
    """Get track statistics for multiple video IDs in single query for performance optimization"""
    if not video_ids:
        return {}
    
    # Remove duplicates while preserving order
    unique_ids = list(dict.fromkeys(video_ids))
    
    # Get basic stats from tracks table
    placeholders = ','.join(['?' for _ in unique_ids])
    tracks_query = f"""
        SELECT video_id, play_starts, play_finishes, play_nexts, play_prevs, play_likes 
        FROM tracks 
        WHERE video_id IN ({placeholders})
    """
    
    cur = conn.cursor()
    cur.execute(tracks_query, unique_ids)
    
    result = {}
    for row in cur.fetchall():
        result[row['video_id']] = {
            "play_starts": row['play_starts'] or 0,
            "play_finishes": row['play_finishes'] or 0,
            "play_nexts": row['play_nexts'] or 0,
            "play_prevs": row['play_prevs'] or 0,
            "play_likes": row['play_likes'] or 0,
            "play_dislikes": 0  # Will be updated below
        }
    
    # Get dislike counts from play_history table
    dislikes_query = f"""
        SELECT video_id, COUNT(*) as dislike_count 
        FROM play_history 
        WHERE video_id IN ({placeholders}) AND event='dislike'
        GROUP BY video_id
    """
    
    cur.execute(dislikes_query, unique_ids)
    
    for row in cur.fetchall():
        video_id = row['video_id']
        if video_id in result:
            result[video_id]["play_dislikes"] = row['dislike_count'] or 0
        else:
            # Track exists in play_history but not in tracks table
            result[video_id] = {
                "play_starts": 0,
                "play_finishes": 0,
                "play_nexts": 0,
                "play_prevs": 0,
                "play_likes": 0,
                "play_dislikes": row['dislike_count'] or 0
            }
    
    # Add default stats for video_ids not found in database
    for video_id in unique_ids:
        if video_id not in result:
            result[video_id] = {
                "play_starts": 0,
                "play_finishes": 0,
                "play_nexts": 0,
                "play_prevs": 0,
                "play_likes": 0,
                "play_dislikes": 0
            }
    
    return result


def get_last_play_timestamps_batch(conn: sqlite3.Connection, video_ids: List[str]) -> Dict[str, Optional[str]]:
    """Get last play timestamps for multiple video IDs in single query for performance optimization"""
    if not video_ids:
        return {}
    
    # Remove duplicates while preserving order
    unique_ids = list(dict.fromkeys(video_ids))
    
    placeholders = ','.join(['?' for _ in unique_ids])
    query = f"""
        SELECT video_id, last_start_ts, last_finish_ts 
        FROM tracks 
        WHERE video_id IN ({placeholders})
    """
    
    cur = conn.cursor()
    cur.execute(query, unique_ids)
    
    result = {}
    for row in cur.fetchall():
        video_id = row['video_id']
        ts1 = row['last_start_ts']
        ts2 = row['last_finish_ts']
        
        # Return latest timestamp
        if ts1 and ts2:
            result[video_id] = ts1 if ts1 > ts2 else ts2
        else:
            result[video_id] = ts1 or ts2
    
    # Add None for video_ids not found in database
    for video_id in unique_ids:
        if video_id not in result:
            result[video_id] = None
    
    return result


def get_dislike_counts_batch(conn: sqlite3.Connection, video_ids: List[str]) -> Dict[str, int]:
    """Get dislike counts for multiple video IDs in single query for performance optimization"""
    if not video_ids:
        return {}
    
    # Remove duplicates while preserving order
    unique_ids = list(dict.fromkeys(video_ids))
    
    placeholders = ','.join(['?' for _ in unique_ids])
    query = f"""
        SELECT video_id, COUNT(*) as dislike_count 
        FROM play_history 
        WHERE video_id IN ({placeholders}) AND event='dislike'
        GROUP BY video_id
    """
    
    cur = conn.cursor()
    cur.execute(query, unique_ids)
    
    result = {}
    for row in cur.fetchall():
        result[row['video_id']] = row['dislike_count'] or 0
    
    # Add 0 for video_ids not found in database
    for video_id in unique_ids:
        if video_id not in result:
            result[video_id] = 0
    
    return result


def get_youtube_metadata_by_playlist(conn: sqlite3.Connection, playlist_id: str) -> Iterator[sqlite3.Row]:
    """Get all YouTube video metadata for a specific playlist"""
    cur = conn.cursor()
    cur.execute("SELECT * FROM youtube_video_metadata WHERE playlist_id = ? ORDER BY playlist_index", (playlist_id,))
    return cur.fetchall()


def delete_youtube_metadata(conn: sqlite3.Connection, youtube_id: str) -> bool:
    """Delete YouTube video metadata by video ID"""
    cur = conn.cursor()
    cur.execute("DELETE FROM youtube_video_metadata WHERE youtube_id = ?", (youtube_id,))
    conn.commit()
    return cur.rowcount > 0


def search_youtube_metadata(conn: sqlite3.Connection, query: str, limit: int = 100) -> Iterator[sqlite3.Row]:
    """Search YouTube video metadata by title or description"""
    cur = conn.cursor()
    search_query = f"%{query}%"
    cur.execute("""
        SELECT * FROM youtube_video_metadata 
        WHERE title LIKE ? OR description LIKE ? OR channel LIKE ?
        ORDER BY created_at DESC
        LIMIT ?
    """, (search_query, search_query, search_query, limit))
    return cur.fetchall()


def get_youtube_metadata_stats(conn: sqlite3.Connection) -> dict:
    """Get statistics about YouTube metadata in database"""
    cur = conn.cursor()
    
    # Total count
    cur.execute("SELECT COUNT(*) FROM youtube_video_metadata")
    total_count = cur.fetchone()[0]
    
    # Count by playlist
    cur.execute("""
        SELECT playlist_title, COUNT(*) as count 
        FROM youtube_video_metadata 
        WHERE playlist_title IS NOT NULL 
        GROUP BY playlist_title 
        ORDER BY count DESC 
        LIMIT 10
    """)
    top_playlists = cur.fetchall()
    
    # Count by channel
    cur.execute("""
        SELECT channel, COUNT(*) as count 
        FROM youtube_video_metadata 
        WHERE channel IS NOT NULL 
        GROUP BY channel 
        ORDER BY count DESC 
        LIMIT 10
    """)
    top_channels = cur.fetchall()
    
    # Recent additions
    cur.execute("""
        SELECT COUNT(*) FROM youtube_video_metadata 
        WHERE created_at >= datetime('now', '-7 days')
    """)
    recent_count = cur.fetchone()[0]
    
    return {
        'total_count': total_count,
        'top_playlists': [dict(row) for row in top_playlists],
        'top_channels': [dict(row) for row in top_channels],
        'recent_additions': recent_count
    } 


# ---------- Quick Sync Functions ----------

def get_latest_downloaded_track_date(conn: sqlite3.Connection, channel_id: int) -> Optional[str]:
    """Get the publication date of the latest downloaded track for a channel.
    
    Args:
        conn: Database connection
        channel_id: Channel ID
        
    Returns:
        Publication date string (YYYY-MM-DD) or None if no tracks found
    """
    cur = conn.cursor()
    
    # Get channel info to match tracks
    cur.execute("SELECT name, url, channel_group_id FROM channels WHERE id = ?", (channel_id,))
    channel_info = cur.fetchone()
    if not channel_info:
        return None
    
    channel_name, channel_url, group_id = channel_info
    
    # Get group name
    cur.execute("SELECT name FROM channel_groups WHERE id = ?", (group_id,))
    group_info = cur.fetchone()
    group_name = group_info[0] if group_info else None
    
    # Find tracks belonging to this channel by checking relpath pattern
    # Channel tracks are stored in: GroupName/Channel-ChannelName/
    channel_path_pattern = f"{group_name}/Channel-{channel_name}/%" if group_name else f"Channel-{channel_name}/%"
    
    cur.execute("""
        SELECT published_date 
        FROM tracks 
        WHERE relpath LIKE ? 
        AND published_date IS NOT NULL 
        ORDER BY published_date DESC 
        LIMIT 1
    """, (channel_path_pattern,))
    
    result = cur.fetchone()
    return result[0] if result else None


def get_channel_latest_video_metadata(conn: sqlite3.Connection, channel_url: str, limit: int = 50) -> List[Dict]:
    """Get latest video metadata for a channel from YouTube metadata table.
    
    Args:
        conn: Database connection
        channel_url: YouTube channel URL
        limit: Maximum number of videos to return
        
    Returns:
        List of video metadata dictionaries sorted by publication date (newest first)
    """
    cur = conn.cursor()
    
    # Extract channel identifier from URL for metadata search
    if '@' in channel_url:
        channel_name_search = channel_url.split('@')[1].split('/')[0]
        search_pattern = f'%@{channel_name_search}%'
    elif '/channel/' in channel_url:
        channel_id_search = channel_url.split('/channel/')[1].split('/')[0]
        search_pattern = f'%{channel_id_search}%'
    elif '/c/' in channel_url:
        channel_name_search = channel_url.split('/c/')[1].split('/')[0]
        search_pattern = f'%{channel_name_search}%'
    else:
        search_pattern = f'%{channel_url}%'
    
    cur.execute("""
        SELECT youtube_id, title, timestamp, release_timestamp, duration, availability, live_status
        FROM youtube_video_metadata 
        WHERE (channel_url LIKE ? OR channel LIKE ?)
        AND availability != 'private'
        AND availability != 'premium_only'
        AND availability != 'subscriber_only'
        ORDER BY COALESCE(release_timestamp, timestamp) DESC
        LIMIT ?
    """, (search_pattern, search_pattern, limit))
    
    results = cur.fetchall()
    
    # Convert to list of dictionaries
    videos = []
    for row in results:
        videos.append({
            'youtube_id': row[0],
            'title': row[1],
            'timestamp': row[2],
            'release_timestamp': row[3],
            'duration': row[4],
            'availability': row[5],
            'live_status': row[6]
        })
    
    return videos


def is_track_already_downloaded(conn: sqlite3.Connection, video_id: str) -> bool:
    """Check if a track with given video ID is already downloaded.
    
    Args:
        conn: Database connection
        video_id: YouTube video ID
        
    Returns:
        True if track is already downloaded, False otherwise
    """
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM tracks WHERE video_id = ? LIMIT 1", (video_id,))
    return cur.fetchone() is not None


def get_video_publication_date(conn: sqlite3.Connection, video_id: str) -> Optional[str]:
    """Get publication date for a video from YouTube metadata.
    
    Args:
        conn: Database connection
        video_id: YouTube video ID
        
    Returns:
        Publication date string (YYYY-MM-DD) or None if not found
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT release_timestamp, timestamp 
        FROM youtube_video_metadata 
        WHERE youtube_id = ?
    """, (video_id,))
    
    result = cur.fetchone()
    if not result:
        return None
    
    release_timestamp, timestamp = result
    
    # Use release_timestamp if available, otherwise use timestamp
    video_timestamp = release_timestamp if release_timestamp else timestamp
    
    if video_timestamp:
        try:
            from datetime import datetime
            # Convert timestamp to date string
            date_obj = datetime.fromtimestamp(video_timestamp)
            return date_obj.strftime('%Y-%m-%d')
        except (ValueError, OSError):
            return None
    
    return None 
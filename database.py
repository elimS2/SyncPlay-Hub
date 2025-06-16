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
            relpath TEXT NOT NULL UNIQUE
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
            position REAL
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
    conn.commit()


# ---------- Convenience queries ----------


def upsert_playlist(conn: sqlite3.Connection, name: str, relpath: str) -> int:
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO playlists (name, relpath) VALUES (?, ?) ON CONFLICT(relpath) DO UPDATE SET name=excluded.name RETURNING id",
        (name, relpath),
    )
    return cur.fetchone()[0]


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


def record_event(conn: sqlite3.Connection, video_id: str, event: str, position: Optional[float] = None):
    """Record playback event and update counters."""
    valid = {"start", "finish", "next", "prev", "like"}
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
    if set_parts:
        cur.execute(f"UPDATE tracks SET {', '.join(set_parts)} WHERE video_id = ?", (video_id,))
        conn.commit()

    # log history
    try:
        cur.execute("INSERT INTO play_history (video_id, event, position) VALUES (?, ?, ?)", (video_id, event, position))
        conn.commit()
    except sqlite3.IntegrityError as e:
        # Likely due to old CHECK constraint only allowing start/finish
        if "CHECK" in str(e):
            _migrate_history_table(conn)
            cur.execute("INSERT INTO play_history (video_id, event, position) VALUES (?, ?, ?)", (video_id, event, position))
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
            position REAL
        );
        INSERT INTO play_history (video_id, event, ts, position)
        SELECT video_id, event, ts, NULL FROM play_history_old;
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
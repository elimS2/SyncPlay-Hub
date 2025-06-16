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
            play_finishes INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS track_playlists (
            track_id INTEGER NOT NULL,
            playlist_id INTEGER NOT NULL,
            PRIMARY KEY (track_id, playlist_id),
            FOREIGN KEY (track_id) REFERENCES tracks(id) ON DELETE CASCADE,
            FOREIGN KEY (playlist_id) REFERENCES playlists(id) ON DELETE CASCADE
        );
        """
    )
    conn.commit()

    # ---- ensure new columns exist when upgrading older DB ----
    cur.execute("PRAGMA table_info(tracks)")
    cols = {row[1] for row in cur.fetchall()}
    for col in ("play_starts", "play_finishes"):
        if col not in cols:
            cur.execute(f"ALTER TABLE tracks ADD COLUMN {col} INTEGER DEFAULT 0")
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


def increment_play(conn: sqlite3.Connection, video_id: str, *, started: bool = False, finished: bool = False):
    cur = conn.cursor()
    set_parts = []
    if started:
        set_parts.append("play_starts = play_starts + 1")
    if finished:
        set_parts.append("play_finishes = play_finishes + 1")
    if not set_parts:
        return
    cur.execute(f"UPDATE tracks SET {', '.join(set_parts)} WHERE video_id = ?", (video_id,))
    conn.commit() 
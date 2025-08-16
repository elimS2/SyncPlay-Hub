#!/usr/bin/env python3
"""
One-time backfill of max_available_height / max_quality_label in youtube_video_metadata

Reads existing normalized available_formats (JSON TEXT) and computes:
- max_available_height (INTEGER)
- max_quality_label (TEXT, e.g., '2160p')

No network calls. Safe to run multiple times.
"""

import argparse
import json
import sqlite3
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

import database as db


def compute_max_height_and_label(formats_json: str) -> tuple[int | None, str | None]:
    try:
        formats = json.loads(formats_json) if formats_json else None
    except Exception:
        return None, None
    if not isinstance(formats, list):
        return None, None
    max_height = 0
    for f in formats:
        if not isinstance(f, dict):
            continue
        vcodec = str(f.get('vcodec') or '').lower()
        if not vcodec or vcodec == 'none':
            continue
        h = f.get('height')
        if isinstance(h, (int, float)) and h and h > max_height:
            max_height = int(h)
    if max_height > 0:
        return max_height, f"{max_height}p"
    return None, None


def backfill(conn: sqlite3.Connection, batch_size: int = 1000, limit: int | None = None) -> dict:
    cur = conn.cursor()
    total = 0
    updated = 0
    skipped = 0

    # Count candidates
    cnt_sql = (
        "SELECT COUNT(*) FROM youtube_video_metadata "
        "WHERE available_formats IS NOT NULL AND TRIM(available_formats) != '' "
        "AND (max_available_height IS NULL OR max_quality_label IS NULL)"
    )
    try:
        total = cur.execute(cnt_sql).fetchone()[0]
    except Exception:
        total = 0

    processed = 0
    offset = 0
    while True:
        if limit is not None and processed >= limit:
            break
        fetch = batch_size
        if limit is not None:
            fetch = min(fetch, max(0, limit - processed))
        rows = cur.execute(
            """
            SELECT youtube_id, available_formats
            FROM youtube_video_metadata
            WHERE available_formats IS NOT NULL AND TRIM(available_formats) != ''
              AND (max_available_height IS NULL OR max_quality_label IS NULL)
            LIMIT ? OFFSET ?
            """,
            (fetch, offset),
        ).fetchall()
        if not rows:
            break
        for youtube_id, af_json in rows:
            h, label = compute_max_height_and_label(af_json)
            if h is None:
                skipped += 1
                continue
            try:
                cur.execute(
                    """
                    UPDATE youtube_video_metadata
                    SET max_available_height = ?, max_quality_label = ?, updated_at = datetime('now')
                    WHERE youtube_id = ?
                    """,
                    (h, label, youtube_id),
                )
                updated += 1
            except Exception:
                skipped += 1
        conn.commit()
        processed += len(rows)
        offset += len(rows)
        if len(rows) < fetch:
            break
    return {"total_candidates": total, "updated": updated, "skipped": skipped}


def main():
    parser = argparse.ArgumentParser(description="Backfill max YouTube quality fields")
    parser.add_argument("--db-path", help="Path to database file (optional; defaults to DB_PATH from .env)")
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    # Resolve DB path via database module, unless overridden
    if args.db_path:
        db.set_db_path(Path(args.db_path))
    conn = db.get_connection()
    try:
        stats = backfill(conn, batch_size=max(1, int(args.batch_size)), limit=args.limit)
        print(
            f"Backfill complete: candidates={stats['total_candidates']}, "
            f"updated={stats['updated']}, skipped={stats['skipped']}"
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()



#!/usr/bin/env python3
import sys
from pathlib import Path

# Ensure project root on sys.path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from database import get_connection

SQL = """
SELECT 
  t.video_id,
  t.relpath,
  ym.title AS youtube_title,
  ym.channel AS ym_channel,
  ym.channel_url AS ym_channel_url,
  ym.uploader AS ym_uploader,
  ym.uploader_id AS ym_uploader_id,
  ym.uploader_url AS ym_uploader_url,
  ch.id AS channel_id,
  ch.name AS channel_name,
  ch.url AS channel_url,
  cg.id AS group_id,
  cg.name AS group_name,
  cg.include_in_likes AS group_include_in_likes
FROM tracks t
LEFT JOIN youtube_video_metadata ym ON ym.youtube_id = t.video_id
LEFT JOIN channels ch ON (
  ch.url = ym.channel_url OR 
  ch.url LIKE '%' || ym.channel || '%' OR 
  ym.channel_url LIKE '%' || ch.url || '%' OR
  (ym.uploader_id IS NOT NULL AND (
    ch.url LIKE '%' || ym.uploader_id || '%' OR
    ch.url LIKE '%' || REPLACE(ym.uploader_id, '@', '') || '%'
  )) OR
  (ym.uploader_url IS NOT NULL AND (
    ch.url LIKE '%' || REPLACE(REPLACE(ym.uploader_url, 'https://www.youtube.com/', ''), '/videos', '') || '%'
  ))
)
LEFT JOIN channel_groups cg ON cg.id = ch.channel_group_id
WHERE t.video_id = ?
LIMIT 1
"""

SQL_DELETED = """
SELECT 1 FROM deleted_tracks WHERE video_id = ? AND restored_at IS NULL LIMIT 1
"""

SQL_LIKES = """
SELECT 
  t.play_likes AS likes,
  COALESCE((SELECT COUNT(*) FROM play_history ph WHERE ph.video_id=t.video_id AND ph.event='dislike'), 0) AS dislikes,
  t.play_likes - COALESCE((SELECT COUNT(*) FROM play_history ph WHERE ph.video_id=t.video_id AND ph.event='dislike'), 0) AS net_likes
FROM tracks t WHERE t.video_id = ?
"""

def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/diagnostics/check_channel_group_mapping.py <video_id>")
        sys.exit(1)

    video_id = sys.argv[1]

    conn = get_connection()
    try:
        row = conn.execute(SQL, (video_id,)).fetchone()
        deleted = bool(conn.execute(SQL_DELETED, (video_id,)).fetchone())
        likes = conn.execute(SQL_LIKES, (video_id,)).fetchone()

        print("=== Channel Group Mapping Diagnostic ===")
        print(f"video_id: {video_id}")
        if row:
            print(f"relpath: {row['relpath']}")
            print(f"youtube_title: {row['youtube_title']}")
            print("-- YouTube metadata used for matching --")
            print(f"ym.channel: {row['ym_channel']}")
            print(f"ym.channel_url: {row['ym_channel_url']}")
            print(f"ym.uploader: {row['ym_uploader']}")
            print(f"ym.uploader_id: {row['ym_uploader_id']}")
            print(f"ym.uploader_url: {row['ym_uploader_url']}")
            print("-- Matched channel --")
            print(f"channel_id: {row['channel_id']}")
            print(f"channel_name: {row['channel_name']}")
            print(f"channel_url: {row['channel_url']}")
            print("-- Channel group --")
            print(f"group_id: {row['group_id']}")
            print(f"group_name: {row['group_name']}")
            print(f"group_include_in_likes: {row['group_include_in_likes']}")
        else:
            print("No track found or no metadata available for join.")

        print("-- Deleted state --")
        print(f"is_deleted_and_not_restored: {deleted}")

        if likes:
            print("-- Likes summary --")
            print(f"likes: {likes['likes']}")
            print(f"dislikes: {likes['dislikes']}")
            print(f"net_likes: {likes['net_likes']}")
    finally:
        try:
            conn.close()
        except Exception:
            pass

if __name__ == "__main__":
    main()

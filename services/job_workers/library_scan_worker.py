#!/usr/bin/env python3
"""
Library Scan Worker

Rescans media properties (bitrate, resolution, optionally duration and size)
for all non-deleted tracks in the database.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List

# Ensure project root in path
sys.path.append(str(Path(__file__).parent.parent.parent))

from services.job_types import JobWorker, Job, JobType
from utils.media_probe import ffprobe_media_properties


class LibraryScanWorker(JobWorker):
    """Worker to rescan media properties for non-deleted tracks."""

    def __init__(self, worker_id: str = "library_scan_worker"):
        super().__init__(worker_id)

    def get_supported_job_types(self) -> List[JobType]:
        return [JobType.LIBRARY_SCAN]

    def execute_job(self, job: Job) -> bool:
        """
        Execute library-wide media properties rescan.

        Job data options:
          - refresh_duration: bool (default True)
          - refresh_size: bool (default True)
        """
        try:
            from controllers.api.shared import get_root_dir
            import database as db
            import sqlite3

            refresh_duration: bool = bool(job.job_data.get("refresh_duration", True))
            refresh_size: bool = bool(job.job_data.get("refresh_size", True))

            root_dir = get_root_dir()
            if not root_dir:
                job.log_error("ROOT_DIR not initialized")
                return False

            processed = 0
            updated = 0
            skipped_missing = 0

            conn = db.get_connection()
            try:
                cursor = conn.cursor()
                # Non-deleted: exclude those present in deleted_tracks without restore
                cursor.execute(
                    """
                    SELECT t.video_id, t.relpath
                    FROM tracks t
                    WHERE t.video_id NOT IN (
                        SELECT dt.video_id FROM deleted_tracks dt
                        WHERE dt.restored_at IS NULL
                    )
                    ORDER BY t.id ASC
                    """
                )
                rows = cursor.fetchall()
            finally:
                conn.close()

            total = len(rows)
            job.log_info(f"Starting LibraryScanWorker for {total} tracks (refresh_duration={refresh_duration}, refresh_size={refresh_size})")

            # Iterate and update
            conn2 = db.get_connection()
            try:
                for idx, (video_id, relpath) in enumerate(rows, start=1):
                    processed += 1
                    abs_path = (root_dir / relpath).resolve()
                    if not abs_path.exists() or not abs_path.is_file():
                        skipped_missing += 1
                        if skipped_missing <= 5:
                            job.log_info(f"Missing file for {video_id}: {abs_path}")
                        continue

                    duration, bitrate, resolution = ffprobe_media_properties(abs_path)
                    size_bytes = abs_path.stat().st_size

                    update_kwargs = {"bitrate": bitrate, "resolution": resolution}
                    if refresh_duration:
                        update_kwargs["duration"] = duration
                    if refresh_size:
                        update_kwargs["size_bytes"] = size_bytes
                    # Avoid overwriting with None
                    update_kwargs = {k: v for k, v in update_kwargs.items() if v is not None}

                    if update_kwargs:
                        db.update_track_media_properties(conn2, video_id, **update_kwargs)
                        updated += 1

                    if idx % 100 == 0 or idx == total:
                        job.log_info(f"Progress: {idx}/{total} processed; updated={updated}; missing={skipped_missing}")

                job.log_info(f"Library scan finished: processed={processed}, updated={updated}, missing={skipped_missing}")
                return True
            finally:
                conn2.close()

        except Exception as e:
            job.log_exception(e, "execute_job in LibraryScanWorker")
            return False



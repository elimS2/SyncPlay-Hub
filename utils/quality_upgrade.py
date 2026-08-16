#!/usr/bin/env python3
"""Safe max-quality upgrade: download to staging, rotate only if better."""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from utils.quality_compare import HEIGHT_SLACK_PX, is_below_max_by_height, parse_local_height

ALLOWED_MEDIA_EXTS = {".mp4", ".mkv", ".webm", ".mov", ".m4a", ".mp3", ".opus", ".flac"}
STAGING_DIR_NAME = "QualityUpgradeStaging"
MIN_NEW_FILE_BYTES = 1_000_000


def staging_dir_for_video(playlists_root: Path, video_id: str) -> Path:
    """Keep staging outside Playlists so library scan cannot pick up drafts."""
    return playlists_root.parent / STAGING_DIR_NAME / video_id


def find_downloaded_video(directory: Path, video_id: str) -> Optional[Path]:
    if not directory.exists():
        return None
    pattern = re.compile(rf"\[{re.escape(video_id)}\]\.[^.]+$")
    candidates = [
        path
        for path in directory.glob("*")
        if path.is_file() and pattern.search(path.name) and path.suffix.lower() in ALLOWED_MEDIA_EXTS
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def should_replace_with_upgrade(
    *,
    old_height: Optional[int],
    new_height: Optional[int],
    old_size: Optional[int],
    new_size: Optional[int],
    max_height: Optional[int],
) -> bool:
    """True only when the new file is clearly better. Equal or worse keeps the original.

    A successful yt-dlp run is not enough: format fallbacks can still land on
    360p. Height must be known and must beat the current file.
    """
    if new_height is None or new_height <= 0:
        return False
    try:
        new_bytes = int(new_size or 0)
    except (TypeError, ValueError):
        new_bytes = 0
    if new_bytes < MIN_NEW_FILE_BYTES:
        return False

    if old_height is not None and old_height > 0:
        return new_height > old_height + HEIGHT_SLACK_PX

    if max_height and not is_below_max_by_height(new_height, max_height):
        return True
    try:
        old_bytes = int(old_size or 0)
    except (TypeError, ValueError):
        old_bytes = 0
    return bool(old_bytes > 0 and new_bytes > int(old_bytes * 1.25))


def _unique_sidecar(path: Path, suffix: str) -> Path:
    candidate = path.with_name(f"{path.stem}{suffix}{path.suffix}")
    counter = 1
    while candidate.exists():
        candidate = path.with_name(f"{path.stem}{suffix}_{counter}{path.suffix}")
        counter += 1
    return candidate


def probe_height(path: Path) -> Optional[int]:
    try:
        from utils.media_probe import ffprobe_media_properties

        _duration, _bitrate, resolution = ffprobe_media_properties(path)
        return parse_local_height(resolution)
    except Exception:
        return None


def rotate_if_better(
    *,
    original_path: Path,
    new_path: Path,
    playlists_root: Path,
    old_height: Optional[int] = None,
    new_height: Optional[int] = None,
    max_height: Optional[int] = None,
    logger: Callable[[str], None] = print,
) -> Dict[str, Any]:
    """Replace the library file only after the new file is verified as better.

    Order:
    1) Decide using heights/sizes (original stays in place).
    2) Move original to a sibling backup.
    3) Move new file into the original directory.
    4) On any failure after step 2, restore the backup to the original path.
    5) After success, try to move the backup to Trash. If trash fails, keep the backup.
    """
    result: Dict[str, Any] = {
        "rotated": False,
        "kept_original": True,
        "reason": "",
        "destination": None,
        "backup_path": None,
    }

    if not new_path.exists() or not new_path.is_file():
        result["reason"] = "new_file_missing"
        return result

    original_exists = original_path.exists() and original_path.is_file()
    old_size = original_path.stat().st_size if original_exists else 0
    new_size = new_path.stat().st_size

    if new_height is None:
        new_height = probe_height(new_path)
    if old_height is None and original_exists:
        old_height = probe_height(original_path)

    logger(
        f"[QualityUpgrade] Compare old_height={old_height} new_height={new_height} "
        f"old_size={old_size} new_size={new_size} max={max_height}"
    )
    if original_exists and not should_replace_with_upgrade(
        old_height=old_height,
        new_height=new_height,
        old_size=old_size,
        new_size=new_size,
        max_height=max_height,
    ):
        result["reason"] = "new_file_not_better"
        logger(
            f"[QualityUpgrade] Keeping original {original_path.name}: "
            f"old_height={old_height} new_height={new_height} max={max_height}"
        )
        return result

    dest_dir = original_path.parent if original_exists else new_path.parent
    dest_dir.mkdir(parents=True, exist_ok=True)
    destination = dest_dir / new_path.name
    backup_path: Optional[Path] = None

    try:
        if original_exists:
            backup_path = _unique_sidecar(original_path, ".pre_upgrade")
            shutil.move(str(original_path), str(backup_path))
            result["backup_path"] = str(backup_path)
            logger(f"[QualityUpgrade] Parked original at {backup_path.name}")

        if destination.exists() and backup_path and destination.resolve() == backup_path.resolve():
            destination = dest_dir / new_path.name

        if destination.exists() and (not backup_path or destination.resolve() != Path(backup_path).resolve()):
            destination = _unique_sidecar(destination, ".upgraded")

        shutil.move(str(new_path), str(destination))
        dest_height = probe_height(destination)
        if dest_height is not None and original_exists and not should_replace_with_upgrade(
            old_height=old_height,
            new_height=dest_height,
            old_size=old_size,
            new_size=destination.stat().st_size if destination.exists() else new_size,
            max_height=max_height,
        ):
            raise RuntimeError(
                f"post-rotate probe rejected dest_height={dest_height} "
                f"(old_height={old_height}, max={max_height})"
            )
        result["destination"] = str(destination)
        result["rotated"] = True
        result["kept_original"] = False
        result["reason"] = "rotated"
        logger(f"[QualityUpgrade] Installed upgrade at {destination.name} dest_height={dest_height}")
    except Exception as exc:
        result["reason"] = f"rotate_failed:{exc}"
        result["rotated"] = False
        result["kept_original"] = True
        logger(f"[QualityUpgrade] Rotate failed, restoring original: {exc}")
        if backup_path and backup_path.exists() and not original_path.exists():
            try:
                shutil.move(str(backup_path), str(original_path))
                logger("[QualityUpgrade] Original restored from backup")
            except Exception as restore_exc:
                result["reason"] = f"restore_failed:{restore_exc}"
                logger(f"[QualityUpgrade] CRITICAL: failed to restore original: {restore_exc}")
        if destination.exists() and destination != original_path:
            try:
                destination.unlink()
            except Exception:
                pass
        return result

    if backup_path and backup_path.exists():
        try:
            from download_content import move_to_trash

            if move_to_trash(backup_path, playlists_root):
                logger("[QualityUpgrade] Old file moved to Trash")
            else:
                logger(f"[QualityUpgrade] Trash move failed; backup kept at {backup_path}")
        except Exception as trash_exc:
            logger(f"[QualityUpgrade] Trash move failed; backup kept at {backup_path}: {trash_exc}")

    return result


def cleanup_staging(staging_dir: Path, logger: Callable[[str], None] = print) -> None:
    if not staging_dir.exists():
        return
    try:
        shutil.rmtree(staging_dir, ignore_errors=False)
        logger(f"[QualityUpgrade] Removed staging {staging_dir}")
    except Exception as exc:
        logger(f"[QualityUpgrade] Failed to remove staging {staging_dir}: {exc}")

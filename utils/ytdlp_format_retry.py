#!/usr/bin/env python3
"""yt-dlp format selectors and 403/short-download retry helpers.

YouTube often advertises 1080p DASH (399/400/248) and then 403s the bytes.
Classic AVC itags (137+140 / 137+251) and a later client switch usually work.
A successful 720p download after that 403 is not the goal — keep trying.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.quality_compare import (
    SUCCESS_HEIGHT_PX,
    effective_success_target_height,
    is_below_max_by_height,
)
from utils.quality_upgrade import ALLOWED_MEDIA_EXTS

BELOW_TARGET_MARK = ".below_target"
_PARKED_NAME_RE = re.compile(r"\.below_target(?:_\d+)?(?=\.[^.]+$)")
_SELECTED_FORMAT_RE = re.compile(
    r"Downloading 1 format\(s\):\s*(\S+)",
    re.IGNORECASE,
)


def extract_selected_format(stdout: str = "", stderr: str = "") -> str:
    """Parse the itag pair yt-dlp actually chose, e.g. ``137+140``."""
    match = _SELECTED_FORMAT_RE.search(f"{stdout or ''}\n{stderr or ''}")
    return match.group(1) if match else ""


def output_has_403(stdout: str = "", stderr: str = "") -> bool:
    text = f"{stdout or ''}\n{stderr or ''}".lower()
    return "http error 403" in text or "forbidden" in text


def format_ytdlp_attempt_line(
    *,
    client: Optional[str],
    format_req: str,
    selected: str,
    exit_code: int,
    saw_403: bool,
) -> str:
    return (
        f"[QualityRetry] ytdlp client={client or 'web'} "
        f"format_req={format_req} selected={selected or 'unknown'} "
        f"exit={exit_code} 403={'yes' if saw_403 else 'no'}"
    )


def format_quality_retry_summary(
    *,
    video_id: Optional[str],
    target_height: Any,
    seen_403: bool,
    clients: List[str],
    final_height: Any,
    outcome: str,
) -> str:
    """One grep-friendly line per job for batch diagnosis."""
    return (
        f"[QualityRetry] summary video={video_id or '?'} "
        f"target={target_height} seen_403={'yes' if seen_403 else 'no'} "
        f"clients={','.join(clients) if clients else 'none'} "
        f"final_height={final_height if final_height is not None else 'none'} "
        f"outcome={outcome}"
    )


def max_quality_format_selector(target_height: int) -> str:
    """Prefer classic 1080p AVC itags before SABR-gated DASH ``bestvideo``."""
    height = max(int(target_height), 144)
    return (
        "137+140/137+251/299+140/"
        f"bestvideo[ext=mp4][vcodec*=avc1][height<={height}]+bestaudio[ext=m4a]/"
        f"bestvideo[height<={height}]+bestaudio/"
        f"best[height<={height}]/best"
    )


def height_locked_format_selectors(target_height: int) -> List[str]:
    """1080-capable selectors only — no progressive 22/18 last-resorts."""
    try:
        raw_height = int(target_height)
    except (TypeError, ValueError):
        raw_height = SUCCESS_HEIGHT_PX
    height = min(max(raw_height, 144), SUCCESS_HEIGHT_PX)
    return [
        "137+140",
        "137+251",
        "299+140",
        f"bestvideo[height={height}][ext=mp4][vcodec*=avc1]+bestaudio[ext=m4a]",
        f"bestvideo[height={height}]+bestaudio",
        f"bestvideo[ext=mp4][vcodec*=avc1][height<={height}]+bestaudio[ext=m4a]",
    ]


def format_unavailable_fallback_selectors(
    target_height: int, already_tried: str
) -> List[str]:
    """Used when the manifest lacks the requested format (not on HTTP 403)."""
    try:
        height = max(int(target_height), 144)
    except (TypeError, ValueError):
        height = SUCCESS_HEIGHT_PX
    selectors = [
        f"bestvideo[ext=mp4][vcodec*=avc1][height<={height}]+bestaudio[ext=m4a]",
        f"bestvideo[height<={height}]+bestaudio/best",
        "137+140",
        "136+140",
        "22/best[ext=mp4]",
    ]
    return [item for item in selectors if item and item != already_tried]


def should_keep_trying_for_target_height(
    probed_height: Any,
    target_height: Any,
    attempts_remaining: int,
) -> bool:
    """True when this file is below the 1080 success cap and more tries remain."""
    try:
        remaining = int(attempts_remaining)
    except (TypeError, ValueError):
        remaining = 0
    if remaining <= 0:
        return False
    success_target = effective_success_target_height(target_height)
    if success_target is None:
        return False
    if probed_height is None:
        return False
    return is_below_max_by_height(probed_height, success_target)


def park_below_target_file(path: Path) -> Path:
    """Rename a too-short download so the next yt-dlp run can write 1080p."""
    dest = path.with_name(f"{path.stem}{BELOW_TARGET_MARK}{path.suffix}")
    counter = 1
    while dest.exists():
        dest = path.with_name(f"{path.stem}{BELOW_TARGET_MARK}_{counter}{path.suffix}")
        counter += 1
    path.replace(dest)
    return dest


def list_parked_below_target(directory: Path, video_id: str) -> List[Path]:
    if not directory.exists() or not video_id:
        return []
    return [
        path
        for path in directory.glob("*")
        if path.is_file()
        and video_id in path.name
        and BELOW_TARGET_MARK in path.name
        and path.suffix.lower() in ALLOWED_MEDIA_EXTS
    ]


def delete_parked_below_target(directory: Path, video_id: str) -> None:
    for path in list_parked_below_target(directory, video_id):
        try:
            path.unlink()
        except OSError:
            pass


def unpark_best_below_target(directory: Path, video_id: str) -> Optional[Path]:
    """Restore the largest parked file to a normal ``[id].ext`` name."""
    parked = list_parked_below_target(directory, video_id)
    if not parked:
        return None
    best = max(parked, key=lambda path: path.stat().st_size)
    restored_name = _PARKED_NAME_RE.sub("", best.name)
    restored = best.with_name(restored_name)
    if restored.exists() and restored != best:
        return restored
    if restored != best:
        best.replace(restored)
    for leftover in list_parked_below_target(directory, video_id):
        if leftover != restored:
            try:
                leftover.unlink()
            except OSError:
                pass
    return restored


def default_403_attempt_plan() -> List[Dict[str, Any]]:
    """Client ladder: try 1080-capable clients before android_vr (often 720/360)."""
    return [
        {
            "name": "web-default",
            "player_client": None,
            "rotate_cookie": False,
            "rotate_proxy": False,
            "extra_flags": [],
            "skip_cookies": False,
        },
        {
            "name": "android-no-cookie",
            "player_client": "android",
            "rotate_cookie": False,
            "rotate_proxy": False,
            "extra_flags": [],
            "skip_cookies": True,
        },
        {
            "name": "ios-no-cookie",
            "player_client": "ios",
            "rotate_cookie": False,
            "rotate_proxy": False,
            "extra_flags": [],
            "skip_cookies": True,
        },
        {
            "name": "mweb",
            "player_client": "mweb",
            "rotate_cookie": False,
            "rotate_proxy": False,
            "extra_flags": [],
            "skip_cookies": False,
        },
        {
            "name": "web-rotated",
            "player_client": None,
            "rotate_cookie": True,
            "rotate_proxy": True,
            "extra_flags": ["--force-ipv4", "--http-chunk-size", "10M"],
            "skip_cookies": False,
        },
        {
            "name": "android-vr-no-cookie",
            "player_client": "android_vr",
            "rotate_cookie": False,
            "rotate_proxy": False,
            "extra_flags": [],
            "skip_cookies": True,
        },
    ]

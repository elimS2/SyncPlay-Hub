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
from utils.quality_upgrade import ALLOWED_MEDIA_EXTS, find_downloaded_video

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


def output_has_format_gate(stdout: str = "", stderr: str = "") -> bool:
    """True when yt-dlp skipped formats (often a silent 403 via --check-formats)."""
    text = f"{stdout or ''}\n{stderr or ''}".lower()
    return (
        "unable to download format" in text
        or "requested format is not available" in text
        or "requested formats are incompatible" in text
    )


def _combined_download_text(stdout: str = "", stderr: str = "") -> str:
    text = f"{stdout or ''}\n{stderr or ''}"
    return (
        text.replace("\u2019", "'")
        .replace("\u2018", "'")
        .replace("`", "'")
        .lower()
    )


def output_has_archive_skip(stdout: str = "", stderr: str = "") -> bool:
    return "has already been recorded in the archive" in _combined_download_text(
        stdout, stderr
    )


def output_has_bot_check(stdout: str = "", stderr: str = "") -> bool:
    text = _combined_download_text(stdout, stderr)
    return "confirm you're not a bot" in text or "confirm youre not a bot" in text


def is_permanent_download_error(stdout: str = "", stderr: str = "") -> bool:
    text = _combined_download_text(stdout, stderr)
    return (
        "this video is private" in text
        or "video unavailable" in text
        or "copyright" in text
    )


def is_retryable_download_error(stdout: str = "", stderr: str = "") -> bool:
    if is_permanent_download_error(stdout, stderr):
        return False
    text = _combined_download_text(stdout, stderr)
    return (
        output_has_403(stdout, stderr)
        or output_has_format_gate(stdout, stderr)
        or output_has_bot_check(stdout, stderr)
        or "sabr" in text
        or "missing a url" in text
        or "page needs to be reloaded" in text
        or "needs to be reloaded" in text
        or "only images are available" in text
        or "format not available" in text
    )


def single_video_metadata_attempts(cookies_path: Optional[str]) -> List[Dict[str, Any]]:
    """Ordered dump-json attempts for one watch URL.

    Cookies make yt-dlp prefer ``tv_downgraded``. YouTube often answers that
    client with "The page needs to be reloaded." Public videos still return
    full metadata from ``android_vr`` without cookies.
    """
    cookie = (cookies_path or "").strip() or None
    attempts: List[Dict[str, Any]] = [{
        "name": "default",
        "cookies": cookie,
        "player_client": None,
    }]
    if cookie:
        attempts.append({
            "name": "android_vr-no-cookie",
            "cookies": None,
            "player_client": "android_vr",
        })
    return attempts


def should_retry_metadata_without_cookies(stdout: str = "", stderr: str = "") -> bool:
    """Skip the cookieless client when the video itself is unreachable."""
    if is_permanent_download_error(stdout, stderr):
        return False
    text = _combined_download_text(stdout, stderr)
    if "members-only" in text or "join this channel" in text:
        return False
    return True


def build_single_video_metadata_cmd(
    video_url: str,
    *,
    cookies_path: Optional[str] = None,
    player_client: Optional[str] = None,
) -> List[str]:
    """CLI for one metadata attempt. ``android_vr`` must not receive cookies."""
    from utils.yt_dlp_js import extend_ytdlp_cli_cmd

    cmd = ["yt-dlp"]
    extend_ytdlp_cli_cmd(cmd)
    if player_client:
        cmd.extend(["--extractor-args", f"youtube:player_client={player_client}"])
    cmd.extend(["--dump-json", video_url])
    if cookies_path:
        cmd.extend(["--cookies", cookies_path])
    return cmd


def archive_entry_line(video_id: str) -> str:
    return f"youtube {video_id}"


def record_id_in_archive(archive_path: Path, video_id: str) -> None:
    """Append ``youtube <id>`` once. Used at finalize, not during the 1080 chase."""
    if not video_id:
        return
    line = archive_entry_line(video_id)
    if archive_path.exists():
        existing = {
            row.strip()
            for row in archive_path.read_text(encoding="utf-8", errors="replace").splitlines()
        }
        if line in existing or any(video_id == row.split()[-1] for row in existing if row):
            return
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with archive_path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def remove_id_from_archive(archive_path: Path, video_id: str) -> bool:
    """Drop a lying archive row when yt-dlp skipped but no file exists."""
    if not video_id or not archive_path.exists():
        return False
    lines = archive_path.read_text(encoding="utf-8", errors="replace").splitlines()
    kept = [row for row in lines if video_id not in row.split()]
    if len(kept) == len(lines):
        return False
    text = "\n".join(kept)
    archive_path.write_text(text + ("\n" if text else ""), encoding="utf-8")
    return True


def resolve_archive_skip_action(directory: Path, video_id: str) -> str:
    """How to treat an archive skip: keepable | unpark | missing."""
    if find_downloaded_video(directory, video_id):
        return "keepable"
    if list_parked_below_target(directory, video_id):
        return "unpark"
    return "missing"


def find_keepable_or_parked_video(directory: Path, video_id: str) -> Optional[Path]:
    """Finalize-mode resolver: unpark if the only copy is ``.below_target``."""
    found = find_downloaded_video(directory, video_id)
    if found:
        return found
    return unpark_best_below_target(directory, video_id)


def delete_parked_if_keepable_exists(directory: Path, video_id: str) -> bool:
    """Delete parked leftovers only after a normal ``[id].ext`` file exists."""
    if not find_downloaded_video(directory, video_id):
        return False
    delete_parked_below_target(directory, video_id)
    return True


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

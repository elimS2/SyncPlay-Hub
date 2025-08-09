from __future__ import annotations

"""
Media probing utilities with multi-platform Python-first strategy.

This module exposes a function to extract media properties
(duration, bitrate, resolution) from a local file using Python libraries
when possible, and falling back to ffprobe only if needed.

Priority order (to maximize portability):
1) Audio: mutagen (duration, bitrate when available)
2) Video: moviepy (duration, width, height) via imageio-ffmpeg (auto-bundled)
3) Fallback: call ffprobe CLI if present

Bitrate fallback: if library does not expose bitrate, compute average container
bitrate as: bitrate_bps = (size_bytes * 8) / duration_seconds

All identifiers, comments, and strings are in English as per project policy.
"""

from pathlib import Path
from typing import Optional, Tuple
import json
import subprocess
import os

_AUDIO_EXTS = {".mp3", ".m4a", ".aac", ".flac", ".opus", ".ogg", ".wav"}
_VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".mov", ".avi"}


def ffprobe_media_properties(path: Path, timeout: int = 10) -> Tuple[Optional[float], Optional[int], Optional[str]]:
    """
    Probe media file properties using Python-first strategy, fallback to ffprobe.

    Returns (duration_seconds, bitrate_bps, resolution_string).
    """

    if not isinstance(path, Path):
        path = Path(path)
    if not path.exists() or not path.is_file():
        return None, None, None

    size_bytes: int = path.stat().st_size
    suffix = path.suffix.lower()

    # 1) Audio via mutagen
    if suffix in _AUDIO_EXTS:
        try:
            from mutagen import File as MutagenFile  # type: ignore
            m = MutagenFile(str(path))
            duration_seconds = float(m.info.length) if getattr(m, "info", None) and getattr(m.info, "length", None) else None
            bitrate_bps = int(getattr(m.info, "bitrate", 0)) or None
            if (not bitrate_bps) and duration_seconds and duration_seconds > 0:
                bitrate_bps = int(size_bytes * 8 / duration_seconds)
            # Audio has no resolution
            return duration_seconds, bitrate_bps, None
        except Exception:
            pass

    # 2) Video via ffprobe if available (prefer to reduce noisy warnings)
    if suffix in _VIDEO_EXTS:
        try:
            from shutil import which
            if which("ffprobe") is not None:
                # Use the ffprobe path first for videos to avoid moviepy warnings
                cmd = [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration,bit_rate:stream=index,codec_type,bit_rate,width,height",
                    "-of",
                    "json",
                    str(path),
                ]
                res = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=timeout,
                )
                data = json.loads(res.stdout or "{}")

                duration_seconds: Optional[float] = None
                bitrate_bps: Optional[int] = None
                resolution: Optional[str] = None

                fmt = (data or {}).get("format") or {}
                if isinstance(fmt, dict):
                    dur_raw = fmt.get("duration")
                    if dur_raw not in (None, "N/A", ""):
                        try:
                            duration_seconds = float(dur_raw)
                        except (TypeError, ValueError):
                            duration_seconds = None
                    fmt_bitrate = fmt.get("bit_rate")
                    if fmt_bitrate not in (None, "N/A", ""):
                        try:
                            bitrate_bps = int(fmt_bitrate)
                        except (TypeError, ValueError):
                            bitrate_bps = None

                streams = (data or {}).get("streams") or []
                if isinstance(streams, list):
                    for s in streams:
                        if not isinstance(s, dict):
                            continue
                        if s.get("codec_type") == "video":
                            w = s.get("width")
                            h = s.get("height")
                            try:
                                if w and h and int(w) > 0 and int(h) > 0:
                                    resolution = f"{int(w)}x{int(h)}"
                                    break
                            except (TypeError, ValueError):
                                continue
                    if bitrate_bps is None:
                        stream_bitrates = []
                        for s in streams:
                            if not isinstance(s, dict):
                                continue
                            br = s.get("bit_rate")
                            if br in (None, "N/A", ""):
                                continue
                            try:
                                stream_bitrates.append(int(br))
                            except (TypeError, ValueError):
                                continue
                        if stream_bitrates:
                            bitrate_bps = max(stream_bitrates)

                if (not bitrate_bps) and (duration_seconds and duration_seconds > 0):
                    bitrate_bps = int(size_bytes * 8 / duration_seconds)

                return duration_seconds, bitrate_bps, resolution
        except Exception:
            # Fall back to moviepy path below
            pass

    # 3) Video via moviepy (uses imageio-ffmpeg internally, which auto-bundles ffmpeg)
    if suffix in _VIDEO_EXTS:
        try:
            import warnings as _warnings
            from moviepy.video.io.VideoFileClip import VideoFileClip  # type: ignore
            clip = None
            try:
                # Suppress noisy UserWarning messages from moviepy about attachment streams
                with _warnings.catch_warnings():
                    _warnings.simplefilter("ignore", category=UserWarning)
                    clip = VideoFileClip(str(path), audio=False)
                duration_seconds = float(clip.duration) if getattr(clip, "duration", None) else None
                width = int(clip.w) if getattr(clip, "w", None) else None
                height = int(clip.h) if getattr(clip, "h", None) else None
                resolution = f"{width}x{height}" if width and height else None
                bitrate_bps = None
                if duration_seconds and duration_seconds > 0:
                    bitrate_bps = int(size_bytes * 8 / duration_seconds)
                return duration_seconds, bitrate_bps, resolution
            finally:
                try:
                    if clip is not None:
                        clip.close()
                except Exception:
                    pass
        except Exception:
            pass

    # 4) Fallback: ffprobe CLI if available (generic for any suffix)
    try:
        # Check availability first
        from shutil import which
        if which("ffprobe") is None:
            raise FileNotFoundError("ffprobe not available")

        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration,bit_rate:stream=index,codec_type,bit_rate,width,height",
            "-of",
            "json",
            str(path),
        ]
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            timeout=timeout,
        )
        data = json.loads(res.stdout or "{}")

        duration_seconds: Optional[float] = None
        bitrate_bps: Optional[int] = None
        resolution: Optional[str] = None

        fmt = (data or {}).get("format") or {}
        if isinstance(fmt, dict):
            dur_raw = fmt.get("duration")
            if dur_raw not in (None, "N/A", ""):
                try:
                    duration_seconds = float(dur_raw)
                except (TypeError, ValueError):
                    duration_seconds = None
            fmt_bitrate = fmt.get("bit_rate")
            if fmt_bitrate not in (None, "N/A", ""):
                try:
                    bitrate_bps = int(fmt_bitrate)
                except (TypeError, ValueError):
                    bitrate_bps = None

        streams = (data or {}).get("streams") or []
        if isinstance(streams, list):
            for s in streams:
                if not isinstance(s, dict):
                    continue
                if s.get("codec_type") == "video":
                    w = s.get("width")
                    h = s.get("height")
                    try:
                        if w and h and int(w) > 0 and int(h) > 0:
                            resolution = f"{int(w)}x{int(h)}"
                            break
                    except (TypeError, ValueError):
                        continue
            if bitrate_bps is None:
                stream_bitrates = []
                for s in streams:
                    if not isinstance(s, dict):
                        continue
                    br = s.get("bit_rate")
                    if br in (None, "N/A", ""):
                        continue
                    try:
                        stream_bitrates.append(int(br))
                    except (TypeError, ValueError):
                        continue
                if stream_bitrates:
                    bitrate_bps = max(stream_bitrates)

        # As last resort for bitrate: compute from size and duration
        if (not bitrate_bps) and (duration_seconds and duration_seconds > 0):
            bitrate_bps = int(size_bytes * 8 / duration_seconds)

        return duration_seconds, bitrate_bps, resolution
    except Exception:
        pass

    # Could not determine via any method
    return None, None, None



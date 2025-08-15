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
from typing import Optional, Tuple, Dict, Any, List
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
                    "format=duration,bit_rate:stream=index,codec_type,bit_rate,width,height,disposition",
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
                    # Prefer non-attached picture streams (ignore cover images)
                    def _is_attached(stream: Dict[str, Any]) -> bool:
                        try:
                            disp = stream.get("disposition") or {}
                            flag = disp.get("attached_pic")
                            if isinstance(flag, str):
                                flag = int(flag)
                            return bool(flag)
                        except Exception:
                            return False
                    video_streams: List[Dict[str, Any]] = [s for s in streams if isinstance(s, dict) and s.get("codec_type") == "video"]
                    preferred = [s for s in video_streams if not _is_attached(s)] or video_streams
                    # Choose the stream with the largest area
                    def _area(s: Dict[str, Any]) -> int:
                        try:
                            return int(s.get("width") or 0) * int(s.get("height") or 0)
                        except Exception:
                            return 0
                    preferred.sort(key=_area, reverse=True)
                    main_v = preferred[0] if preferred else None
                    if main_v:
                        w = main_v.get("width")
                        h = main_v.get("height")
                        try:
                            if w and h and int(w) > 0 and int(h) > 0:
                                resolution = f"{int(w)}x{int(h)}"
                        except (TypeError, ValueError):
                            pass
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
            "format=duration,bit_rate:stream=index,codec_type,bit_rate,width,height,disposition",
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
            def _is_attached(stream: Dict[str, Any]) -> bool:
                try:
                    disp = stream.get("disposition") or {}
                    flag = disp.get("attached_pic")
                    if isinstance(flag, str):
                        flag = int(flag)
                    return bool(flag)
                except Exception:
                    return False
            video_streams: List[Dict[str, Any]] = [s for s in streams if isinstance(s, dict) and s.get("codec_type") == "video"]
            preferred = [s for s in video_streams if not _is_attached(s)] or video_streams
            def _area(s: Dict[str, Any]) -> int:
                try:
                    return int(s.get("width") or 0) * int(s.get("height") or 0)
                except Exception:
                    return 0
            preferred.sort(key=_area, reverse=True)
            main_v = preferred[0] if preferred else None
            if main_v:
                try:
                    w = main_v.get("width")
                    h = main_v.get("height")
                    if w and h and int(w) > 0 and int(h) > 0:
                        resolution = f"{int(w)}x{int(h)}"
                except (TypeError, ValueError):
                    pass
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


def _parse_fractional_rate(value: Any) -> Optional[float]:
    """
    Parse ffprobe frame rate value that may be a fraction string like "30000/1001".
    Returns float rounded to two decimals, or None if cannot parse.
    """
    if value in (None, "N/A", "", 0):
        return None
    try:
        # Already numeric
        if isinstance(value, (int, float)):
            return round(float(value), 2)
        text = str(value)
        if "/" in text:
            num, den = text.split("/", 1)
            num_f = float(num)
            den_f = float(den) if float(den) != 0 else 1.0
            return round(num_f / den_f, 2)
        # Plain string number
        return round(float(text), 2)
    except Exception:
        return None


def ffprobe_media_properties_ex(path: Path, timeout: int = 10) -> Dict[str, Optional[Any]]:
    """
    Extended media probing that returns a dictionary with the following keys:
      - duration: float | None (seconds)
      - bitrate: int | None (bits per second)
      - resolution: str | None (e.g., "1920x1080")
      - video_fps: float | None (e.g., 29.97)
      - video_codec: str | None (e.g., "h264")
      - audio_codec: str | None (e.g., "aac", "opus")
      - audio_bitrate: int | None (bps)
      - audio_sample_rate: int | None (Hz)
      - audio_bitrate_estimated: bool (True when bitrate is derived/approximate)

    Strategy mirrors ffprobe_media_properties but also extracts fps and codec
    for video streams when available.
    """
    if not isinstance(path, Path):
        path = Path(path)
    if not path.exists() or not path.is_file():
        return {
            "duration": None,
            "bitrate": None,
            "resolution": None,
            "video_fps": None,
            "video_codec": None,
            "audio_codec": None,
            "audio_bitrate": None,
            "audio_sample_rate": None,
            "audio_bitrate_estimated": False,
        }

    size_bytes: int = path.stat().st_size
    suffix = path.suffix.lower()

    # Audio via mutagen
    if suffix in _AUDIO_EXTS:
        try:
            from mutagen import File as MutagenFile  # type: ignore
            m = MutagenFile(str(path))
            duration_seconds = float(m.info.length) if getattr(m, "info", None) and getattr(m.info, "length", None) else None
            bitrate_bps = int(getattr(m.info, "bitrate", 0)) or None
            if (not bitrate_bps) and duration_seconds and duration_seconds > 0:
                bitrate_bps = int(size_bytes * 8 / duration_seconds)
            return {
                "duration": duration_seconds,
                "bitrate": bitrate_bps,
                "resolution": None,
                "video_fps": None,
                "video_codec": None,
                "audio_codec": (getattr(m.info, 'codec', None) or None),
                "audio_bitrate": bitrate_bps,
                "audio_sample_rate": int(getattr(m.info, 'sample_rate', 0)) or None,
                "audio_bitrate_estimated": bool(not getattr(m.info, 'bitrate', None)),
            }
        except Exception:
            pass

    # Prefer ffprobe for video, if available
    if suffix in _VIDEO_EXTS:
        try:
            from shutil import which
            if which("ffprobe") is not None:
                cmd = [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    # Request additional fields; include format.sample_rate and audio stream sample_rate/channels
                    # Add disposition to detect attached pictures (cover images)
                    "format=duration,bit_rate,sample_rate:stream=index,codec_type,codec_name,bit_rate,width,height,avg_frame_rate,r_frame_rate,sample_rate,channels,channel_layout,tags,disposition",
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
                video_fps: Optional[float] = None
                video_codec: Optional[str] = None
                audio_codec: Optional[str] = None
                audio_bitrate: Optional[int] = None
                audio_sample_rate: Optional[int] = None
                audio_bitrate_estimated: bool = False

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
                    # Fallback for audio sample rate at container level
                    fmt_asr = fmt.get("sample_rate")
                    if audio_sample_rate is None and fmt_asr not in (None, "N/A", ""):
                        try:
                            audio_sample_rate = int(fmt_asr)
                        except Exception:
                            pass

                streams = (data or {}).get("streams") or []
                if isinstance(streams, list):
                    video_stream_bitrate_sum = 0
                    video_streams: list[dict] = []
                    for s in streams:
                        if not isinstance(s, dict):
                            continue
                        ctype = s.get("codec_type")
                        if ctype == "video":
                            video_streams.append(s)
                            # Do not break; keep scanning others to collect stream bitrates below
                            br_v = s.get("bit_rate")
                            try:
                                if br_v not in (None, "N/A", ""):
                                    video_stream_bitrate_sum += int(br_v)
                            except Exception:
                                pass
                        elif ctype == "audio":
                            c = s.get("codec_name")
                            if isinstance(c, str) and c and c != "N/A":
                                audio_codec = c.lower()
                            # Prefer stream audio bitrate if present
                            br = s.get("bit_rate")
                            try:
                                if br not in (None, "N/A", ""):
                                    audio_bitrate = int(br)
                            except Exception:
                                pass
                            asr = s.get("sample_rate")
                            try:
                                if asr not in (None, "N/A", ""):
                                    audio_sample_rate = int(asr)
                            except Exception:
                                pass
                            # Try tags for audio bitrate (e.g., BPS, BPS-eng)
                            if audio_bitrate is None:
                                tags = s.get("tags") or {}
                                if isinstance(tags, dict):
                                    for key in ("BPS", "BPS-eng"):
                                        val = tags.get(key)
                                        if val not in (None, "N/A", ""):
                                            try:
                                                audio_bitrate = int(val)
                                                break
                                            except Exception:
                                                continue
                    # Choose preferred video stream: ignore attached pictures and still-image codecs, then max area
                    def _is_attached(stream: dict) -> bool:
                        try:
                            disp = stream.get("disposition") or {}
                            flag = disp.get("attached_pic")
                            if isinstance(flag, str):
                                flag = int(flag)
                            return bool(flag)
                        except Exception:
                            return False
                    STILL_IMAGE_CODECS = {"png", "mjpeg", "mjpg", "bmp", "gif", "webp", "tiff"}
                    def _is_still_codec(stream: dict) -> bool:
                        c = stream.get("codec_name")
                        return isinstance(c, str) and c.lower() in STILL_IMAGE_CODECS
                    candidates = [s for s in video_streams if (not _is_attached(s)) and (not _is_still_codec(s))] or \
                                 [s for s in video_streams if not _is_attached(s)] or video_streams
                    def _area(s: dict) -> int:
                        try:
                            return int(s.get("width") or 0) * int(s.get("height") or 0)
                        except Exception:
                            return 0
                    main_v = sorted(candidates, key=_area, reverse=True)[0] if candidates else None
                    if main_v:
                        try:
                            w = main_v.get("width")
                            h = main_v.get("height")
                            if w and h and int(w) > 0 and int(h) > 0:
                                resolution = f"{int(w)}x{int(h)}"
                        except Exception:
                            pass
                        c = main_v.get("codec_name")
                        if isinstance(c, str) and c and c != "N/A":
                            video_codec = c.lower()
                        video_fps = _parse_fractional_rate(main_v.get("avg_frame_rate")) or _parse_fractional_rate(main_v.get("r_frame_rate"))
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

                    # Derive audio_bitrate if missing and we have a container/derived bitrate
                    if audio_bitrate is None and (duration_seconds and duration_seconds > 0):
                        container_bps = None
                        # Prefer format bit_rate if present
                        if isinstance(fmt, dict) and fmt.get("bit_rate") not in (None, "N/A", ""):
                            try:
                                container_bps = int(fmt.get("bit_rate"))
                            except Exception:
                                container_bps = None
                        # Fallback to size/duration
                        if container_bps is None:
                            try:
                                container_bps = int(size_bytes * 8 / duration_seconds)
                            except Exception:
                                container_bps = None
                        if container_bps is not None and video_stream_bitrate_sum > 0:
                            candidate = container_bps - video_stream_bitrate_sum
                            if candidate > 0:
                                audio_bitrate = candidate
                                audio_bitrate_estimated = True

                if (not bitrate_bps) and (duration_seconds and duration_seconds > 0):
                    bitrate_bps = int(size_bytes * 8 / duration_seconds)

                return {
                    "duration": duration_seconds,
                    "bitrate": bitrate_bps,
                    "resolution": resolution,
                    "video_fps": video_fps,
                    "video_codec": video_codec,
                    "audio_codec": audio_codec,
                    "audio_bitrate": audio_bitrate,
                    "audio_sample_rate": audio_sample_rate,
                    "audio_bitrate_estimated": audio_bitrate_estimated,
                }
        except Exception:
            # Fall back to moviepy path below
            pass

    # MoviePy fallback for video
    if suffix in _VIDEO_EXTS:
        try:
            import warnings as _warnings
            from moviepy.video.io.VideoFileClip import VideoFileClip  # type: ignore
            clip = None
            try:
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
                fps_val = getattr(clip, "fps", None)
                video_fps = round(float(fps_val), 2) if fps_val else None
                return {
                    "duration": duration_seconds,
                    "bitrate": bitrate_bps,
                    "resolution": resolution,
                    "video_fps": video_fps,
                    "video_codec": None,  # codec not available via moviepy reliably
                    "audio_codec": None,
                    "audio_bitrate": None,
                    "audio_sample_rate": None,
                    "audio_bitrate_estimated": False,
                }
            finally:
                try:
                    if clip is not None:
                        clip.close()
                except Exception:
                    pass
        except Exception:
            pass

    # Generic ffprobe fallback (any suffix)
    try:
        from shutil import which
        if which("ffprobe") is None:
            raise FileNotFoundError("ffprobe not available")

        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            # Add disposition to detect attached pictures
            "format=duration,bit_rate,sample_rate:stream=index,codec_type,codec_name,bit_rate,width,height,avg_frame_rate,r_frame_rate,sample_rate,channels,channel_layout,tags,disposition",
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
        video_fps: Optional[float] = None
        video_codec: Optional[str] = None
        audio_codec: Optional[str] = None
        audio_bitrate: Optional[int] = None
        audio_sample_rate: Optional[int] = None
        audio_bitrate_estimated: bool = False

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
            fmt_asr = fmt.get("sample_rate")
            if fmt_asr not in (None, "N/A", "") and audio_sample_rate is None:
                try:
                    audio_sample_rate = int(fmt_asr)
                except Exception:
                    pass

        streams = (data or {}).get("streams") or []
        if isinstance(streams, list):
            video_stream_bitrate_sum = 0
            video_streams: list[dict] = []
            for s in streams:
                if not isinstance(s, dict):
                    continue
                ctype = s.get("codec_type")
                if ctype == "video":
                    video_streams.append(s)
                    br_v = s.get("bit_rate")
                    try:
                        if br_v not in (None, "N/A", ""):
                            video_stream_bitrate_sum += int(br_v)
                    except Exception:
                        pass
                elif ctype == "audio":
                    c = s.get("codec_name")
                    if isinstance(c, str) and c and c != "N/A":
                        audio_codec = c.lower()
                    br = s.get("bit_rate")
                    try:
                        if br not in (None, "N/A", ""):
                            audio_bitrate = int(br)
                    except Exception:
                        pass
                    asr = s.get("sample_rate")
                    try:
                        if asr not in (None, "N/A", ""):
                            audio_sample_rate = int(asr)
                    except Exception:
                        pass
                    if audio_bitrate is None:
                        tags = s.get("tags") or {}
                        if isinstance(tags, dict):
                            for key in ("BPS", "BPS-eng"):
                                val = tags.get(key)
                                if val not in (None, "N/A", ""):
                                    try:
                                        audio_bitrate = int(val)
                                        break
                                    except Exception:
                                        continue
            # Choose preferred video stream (ignore attached pictures and still-image codecs)
            def _is_attached(stream: dict) -> bool:
                try:
                    disp = stream.get("disposition") or {}
                    flag = disp.get("attached_pic")
                    if isinstance(flag, str):
                        flag = int(flag)
                    return bool(flag)
                except Exception:
                    return False
            STILL_IMAGE_CODECS = {"png", "mjpeg", "mjpg", "bmp", "gif", "webp", "tiff"}
            def _is_still_codec(stream: dict) -> bool:
                c = stream.get("codec_name")
                return isinstance(c, str) and c.lower() in STILL_IMAGE_CODECS
            candidates = [s for s in video_streams if (not _is_attached(s)) and (not _is_still_codec(s))] or \
                         [s for s in video_streams if not _is_attached(s)] or video_streams
            def _area(s: dict) -> int:
                try:
                    return int(s.get("width") or 0) * int(s.get("height") or 0)
                except Exception:
                    return 0
            main_v = sorted(candidates, key=_area, reverse=True)[0] if candidates else None
            if main_v:
                try:
                    w = main_v.get("width")
                    h = main_v.get("height")
                    if w and h and int(w) > 0 and int(h) > 0:
                        resolution = f"{int(w)}x{int(h)}"
                except Exception:
                    pass
                c = main_v.get("codec_name")
                if isinstance(c, str) and c and c != "N/A":
                    video_codec = c.lower()
                video_fps = _parse_fractional_rate(main_v.get("avg_frame_rate")) or _parse_fractional_rate(main_v.get("r_frame_rate"))
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

            # Derive audio_bitrate if missing and possible
            if audio_bitrate is None and (duration_seconds and duration_seconds > 0):
                container_bps = None
                if isinstance(fmt, dict) and fmt.get("bit_rate") not in (None, "N/A", ""):
                    try:
                        container_bps = int(fmt.get("bit_rate"))
                    except Exception:
                        container_bps = None
                if container_bps is None:
                    try:
                        container_bps = int(size_bytes * 8 / duration_seconds)
                    except Exception:
                        container_bps = None
                if container_bps is not None and video_stream_bitrate_sum > 0:
                    candidate = container_bps - video_stream_bitrate_sum
                    if candidate > 0:
                        audio_bitrate = candidate
                        audio_bitrate_estimated = True

        if (not bitrate_bps) and (duration_seconds and duration_seconds > 0):
            bitrate_bps = int(size_bytes * 8 / duration_seconds)

        return {
            "duration": duration_seconds,
            "bitrate": bitrate_bps,
            "resolution": resolution,
            "video_fps": video_fps,
            "video_codec": video_codec,
            "audio_codec": audio_codec,
            "audio_bitrate": audio_bitrate,
            "audio_sample_rate": audio_sample_rate,
            "audio_bitrate_estimated": audio_bitrate_estimated,
        }
    except Exception:
        pass

    return {
        "duration": None,
        "bitrate": None,
        "resolution": None,
        "video_fps": None,
        "video_codec": None,
        "audio_codec": None,
        "audio_bitrate": None,
        "audio_sample_rate": None,
        "audio_bitrate_estimated": False,
    }


def rescan_track_media_properties(video_id: str, file_path: Path, refresh_duration: bool = False, refresh_size: bool = False) -> dict:
    """
    Rescan media properties for a track and update database.
    
    This is a common utility method that can be reused by different parts of the system
    (Rescan API, download workers, etc.) to avoid code duplication.
    
    Args:
        video_id: YouTube video ID of the track
        file_path: Path to the media file to probe
        refresh_duration: Whether to refresh duration in database
        refresh_size: Whether to refresh file size in database
        
    Returns:
        Dict with probe results and update status:
        {
            "success": bool,
            "bitrate": int | None,
            "resolution": str | None,
            "duration": float | None,
            "size_bytes": int | None,
            "video_fps": float | None,
            "video_codec": str | None,
            "audio_codec": str | None,
            "audio_bitrate": int | None,
            "audio_sample_rate": int | None,
            "fields_updated": list[str],
            "error": str | None
        }
    """
    print(f"[MediaProbe] Starting rescan for {video_id}, file: {file_path}")
    print(f"[MediaProbe] Parameters: refresh_duration={refresh_duration}, refresh_size={refresh_size}")
    try:
        from database import get_connection, update_track_media_properties
        from controllers.api.shared import log_message
        
        # Ensure file exists
        if not file_path.exists() or not file_path.is_file():
            return {
                "success": False,
                "error": f"File not found: {file_path}"
            }
        
        # Probe media (extended)
        probe = ffprobe_media_properties_ex(file_path)
        duration = probe.get("duration")
        bitrate = probe.get("bitrate")
        resolution = probe.get("resolution")
        video_fps = probe.get("video_fps")
        video_codec = probe.get("video_codec")
        size_bytes = file_path.stat().st_size
        
        # Determine which fields to update
        fields_updated = []
        update_kwargs = {
            "bitrate": bitrate,
            "resolution": resolution,
            "video_fps": video_fps,
            "video_codec": video_codec,
            "audio_codec": probe.get("audio_codec"),
            "audio_bitrate": probe.get("audio_bitrate"),
            "audio_sample_rate": probe.get("audio_sample_rate"),
        }
        if refresh_duration:
            update_kwargs["duration"] = duration
        if refresh_size:
            update_kwargs["size_bytes"] = size_bytes
        
        # Filter out None so we do not overwrite with NULL unintentionally
        update_kwargs = {k: v for k, v in update_kwargs.items() if v is not None}
        
        # Update database if we have fields to update
        if update_kwargs:
            conn = get_connection()
            try:
                update_track_media_properties(conn, video_id, **update_kwargs)
                fields_updated = list(update_kwargs.keys())
                conn.close()
            except Exception as e:
                conn.close()
                return {
                    "success": False,
                    "error": f"Database update failed: {e}"
                }
        
        # Log the operation
        log_message(
            f"[MediaProbe] {video_id} -> updated: {fields_updated or 'none'}; "
            f"bitrate={bitrate}, resolution={resolution}, fps={video_fps}, vcodec={video_codec}, "
            f"acodec={probe.get('audio_codec')}, abitrate={probe.get('audio_bitrate')}, asr={probe.get('audio_sample_rate')}, "
            f"duration={duration}, size={size_bytes}"
        )
        
        return {
            "success": True,
            "bitrate": bitrate,
            "resolution": resolution,
            "duration": duration,
            "size_bytes": size_bytes,
            "video_fps": video_fps,
            "video_codec": video_codec,
            "audio_codec": probe.get("audio_codec"),
            "audio_bitrate": probe.get("audio_bitrate"),
            "audio_sample_rate": probe.get("audio_sample_rate"),
            "fields_updated": fields_updated,
            "error": None
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": f"Probe failed: {e}"
        }


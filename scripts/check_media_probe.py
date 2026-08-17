#!/usr/bin/env python3
"""Smoke checks for video-stream selection used by quality-upgrade height probes."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.media_probe import (
    resolution_from_stream,
    select_main_video_stream,
)
from utils.quality_compare import parse_local_height
from utils.quality_upgrade import probe_height


def _h264(width: int, height: int) -> dict:
    return {
        "codec_type": "video",
        "codec_name": "h264",
        "width": width,
        "height": height,
        "disposition": {"attached_pic": 0},
    }


def _cover_png(width: int = 1280, height: int = 720, attached: bool = False) -> dict:
    return {
        "codec_type": "video",
        "codec_name": "png",
        "width": width,
        "height": height,
        "disposition": {"attached_pic": 1 if attached else 0},
    }


def test_select_ignores_larger_png_cover() -> None:
    streams = [
        _h264(640, 360),
        {"codec_type": "audio", "codec_name": "aac"},
        _cover_png(1280, 720, attached=False),
    ]
    main = select_main_video_stream(streams)
    assert resolution_from_stream(main) == "640x360"
    assert parse_local_height(resolution_from_stream(main)) == 360


def test_select_ignores_attached_pic_flag() -> None:
    streams = [
        _cover_png(1920, 1080, attached=True),
        _h264(1280, 720),
    ]
    assert resolution_from_stream(select_main_video_stream(streams)) == "1280x720"


def test_select_falls_back_to_still_when_only_cover() -> None:
    streams = [_cover_png(1280, 720, attached=False)]
    assert resolution_from_stream(select_main_video_stream(streams)) == "1280x720"


def test_select_without_codec_name_cannot_drop_png() -> None:
    """ffprobe must request codec_name; without it a larger cover still wins."""
    streams = [
        {
            "codec_type": "video",
            "width": 640,
            "height": 360,
            "disposition": {"attached_pic": 0},
        },
        {
            "codec_type": "video",
            "width": 1280,
            "height": 720,
            "disposition": {"attached_pic": 0},
        },
    ]
    assert resolution_from_stream(select_main_video_stream(streams)) == "1280x720"


def test_select_empty() -> None:
    assert select_main_video_stream([]) is None
    assert select_main_video_stream(None) is None
    assert resolution_from_stream(None) is None


def test_probe_height_skips_embedded_cover_when_library_file_exists() -> None:
    path = Path(
        r"D:/music/Youtube/Playlists/New Music/Channel-eminem"
        r"/Eminem_-_The_Monster_ft._Rihanna_Audio [ZDXXi19_7iE].mp4"
    )
    if not path.is_file():
        print("[SKIP] test_probe_height_skips_embedded_cover_when_library_file_exists (file missing)")
        return
    height = probe_height(path)
    assert height == 360, height
    print("[PASS] test_probe_height_skips_embedded_cover_when_library_file_exists")


def main() -> int:
    test_select_ignores_larger_png_cover()
    print("[PASS] test_select_ignores_larger_png_cover")
    test_select_ignores_attached_pic_flag()
    print("[PASS] test_select_ignores_attached_pic_flag")
    test_select_falls_back_to_still_when_only_cover()
    print("[PASS] test_select_falls_back_to_still_when_only_cover")
    test_select_without_codec_name_cannot_drop_png()
    print("[PASS] test_select_without_codec_name_cannot_drop_png")
    test_select_empty()
    print("[PASS] test_select_empty")
    test_probe_height_skips_embedded_cover_when_library_file_exists()
    print("[OK] media probe checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())

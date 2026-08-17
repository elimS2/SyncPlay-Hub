#!/usr/bin/env python3
"""Smoke checks for 403/1080 format retry helpers."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.quality_upgrade import find_downloaded_video
from utils.ytdlp_format_retry import (
    default_403_attempt_plan,
    delete_parked_below_target,
    extract_selected_format,
    format_quality_retry_summary,
    format_unavailable_fallback_selectors,
    format_ytdlp_attempt_line,
    height_locked_format_selectors,
    max_quality_format_selector,
    output_has_403,
    park_below_target_file,
    should_keep_trying_for_target_height,
    unpark_best_below_target,
)


def test_selector_prefers_classic_1080_itags() -> None:
    selector = max_quality_format_selector(2160)
    assert selector.startswith("137+140/137+251/299+140/")
    assert "bestvideo[height<=2160]+bestaudio" in selector
    assert not selector.startswith("bestvideo[height<=")


def test_height_locked_has_no_progressive_last_resort() -> None:
    locked = height_locked_format_selectors(2160)
    joined = " ".join(locked)
    assert "137+140" in locked
    assert "137+251" in locked
    assert "22" not in joined
    assert "best[ext=mp4]" not in joined
    assert "height=1080" in joined


def test_format_unavailable_keeps_progressive_last() -> None:
    fallbacks = format_unavailable_fallback_selectors(1080, "137+140")
    assert fallbacks[-1] == "22/best[ext=mp4]"
    assert "137+140" not in fallbacks


def test_should_keep_trying() -> None:
    assert should_keep_trying_for_target_height(720, 1080, 3) is True
    assert should_keep_trying_for_target_height(720, 2160, 2) is True
    assert should_keep_trying_for_target_height(1080, 2160, 3) is False
    assert should_keep_trying_for_target_height(720, 1080, 0) is False
    assert should_keep_trying_for_target_height(720, 720, 3) is False
    assert should_keep_trying_for_target_height(None, 1080, 3) is False


def test_android_vr_is_last_client() -> None:
    plan = default_403_attempt_plan()
    assert plan[0]["name"] == "web-default"
    assert plan[1]["player_client"] == "android"
    assert plan[2]["player_client"] == "ios"
    assert plan[-1]["player_client"] == "android_vr"
    assert any(item["player_client"] == "mweb" for item in plan)


def test_park_hides_from_finder_and_unpark_restores(tmp_path: Path) -> None:
    video_id = "k9DFtTySOnQ"
    media = tmp_path / f"Sample [{video_id}].mp4"
    media.write_bytes(b"x" * 2_000_000)
    parked = park_below_target_file(media)
    assert parked.exists()
    assert not media.exists()
    assert find_downloaded_video(tmp_path, video_id) is None
    restored = unpark_best_below_target(tmp_path, video_id)
    assert restored is not None
    assert restored.exists()
    assert restored.name == f"Sample [{video_id}].mp4"
    assert find_downloaded_video(tmp_path, video_id) == restored


def test_log_line_helpers() -> None:
    selected = extract_selected_format(
        "",
        "[info] k9DFtTySOnQ: Downloading 1 format(s): 137+140\nERROR: HTTP Error 403: Forbidden",
    )
    assert selected == "137+140"
    assert output_has_403("", "unable to download video data: HTTP Error 403: Forbidden")
    assert output_has_403("ok", "") is False
    line = format_ytdlp_attempt_line(
        client="android",
        format_req="137+140",
        selected="137+140",
        exit_code=1,
        saw_403=True,
    )
    assert "client=android" in line
    assert "403=yes" in line
    summary = format_quality_retry_summary(
        video_id="k9DFtTySOnQ",
        target_height=1080,
        seen_403=True,
        clients=["web", "android"],
        final_height=720,
        outcome="last_resort",
    )
    assert summary.startswith("[QualityRetry] summary video=k9DFtTySOnQ")
    assert "outcome=last_resort" in summary
    assert "seen_403=yes" in summary


def test_delete_parked(tmp_path: Path) -> None:
    video_id = "abc123xyzAB"
    media = tmp_path / f"Clip [{video_id}].mp4"
    media.write_bytes(b"y" * 1_000_000)
    park_below_target_file(media)
    delete_parked_below_target(tmp_path, video_id)
    assert list(tmp_path.glob("*")) == []


def main() -> int:
    test_selector_prefers_classic_1080_itags()
    print("[PASS] test_selector_prefers_classic_1080_itags")
    test_height_locked_has_no_progressive_last_resort()
    print("[PASS] test_height_locked_has_no_progressive_last_resort")
    test_format_unavailable_keeps_progressive_last()
    print("[PASS] test_format_unavailable_keeps_progressive_last")
    test_should_keep_trying()
    print("[PASS] test_should_keep_trying")
    test_android_vr_is_last_client()
    print("[PASS] test_android_vr_is_last_client")
    with tempfile.TemporaryDirectory() as tmp:
        test_park_hides_from_finder_and_unpark_restores(Path(tmp))
    print("[PASS] test_park_hides_from_finder_and_unpark_restores")
    test_log_line_helpers()
    print("[PASS] test_log_line_helpers")
    with tempfile.TemporaryDirectory() as tmp:
        test_delete_parked(Path(tmp))
    print("[PASS] test_delete_parked")
    print("[OK] ytdlp format retry checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())

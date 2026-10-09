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
    BELOW_TARGET_MARK,
    default_403_attempt_plan,
    delete_parked_below_target,
    delete_parked_if_keepable_exists,
    extract_selected_format,
    find_keepable_or_parked_video,
    format_quality_retry_summary,
    format_unavailable_fallback_selectors,
    format_ytdlp_attempt_line,
    height_locked_format_selectors,
    build_single_video_metadata_cmd,
    is_permanent_download_error,
    is_retryable_download_error,
    should_retry_metadata_without_cookies,
    single_video_metadata_attempts,
    max_quality_format_selector,
    output_has_403,
    output_has_archive_skip,
    output_has_bot_check,
    output_has_format_gate,
    park_below_target_file,
    record_id_in_archive,
    remove_id_from_archive,
    resolve_archive_skip_action,
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
    assert output_has_format_gate("", "WARNING: Unable to download format 137. Skipping...")
    assert output_has_format_gate("", "ERROR: Requested format is not available")
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


def test_archive_skip_unpark_does_not_delete(tmp_path: Path) -> None:
    """Bug 2: archive skip + parked file must unpark, not unlink."""
    video_id = "vidA0000001"
    media = tmp_path / f"_ [{video_id}].mp4"
    media.write_bytes(b"z" * 2_000_000)
    parked = park_below_target_file(media)
    stdout = f"[download] {video_id}: has already been recorded in the archive\n"
    assert output_has_archive_skip(stdout, "")
    assert find_downloaded_video(tmp_path, video_id) is None
    assert resolve_archive_skip_action(tmp_path, video_id) == "unpark"
    assert delete_parked_if_keepable_exists(tmp_path, video_id) is False
    assert parked.exists()
    restored = find_keepable_or_parked_video(tmp_path, video_id)
    assert restored is not None
    assert restored.exists()
    assert BELOW_TARGET_MARK not in restored.name
    assert delete_parked_if_keepable_exists(tmp_path, video_id) is True
    assert not parked.exists()
    assert restored.exists()


def test_finish_success_deletes_parked_only_after_keepable(tmp_path: Path) -> None:
    video_id = "vidB0000002"
    keepable = tmp_path / f"Title [{video_id}].mp4"
    keepable.write_bytes(b"k" * 1_500_000)
    leftover = tmp_path / f"Old [{video_id}].below_target.mp4"
    leftover.write_bytes(b"p" * 800_000)
    assert delete_parked_if_keepable_exists(tmp_path, video_id) is True
    assert keepable.exists()
    assert not leftover.exists()


def test_archive_record_only_on_accept(tmp_path: Path) -> None:
    video_id = "vidC0000003"
    archive = tmp_path / "archive.txt"
    record_id_in_archive(archive, video_id)
    record_id_in_archive(archive, video_id)
    text = archive.read_text(encoding="utf-8")
    assert text.count(f"youtube {video_id}") == 1
    assert remove_id_from_archive(archive, video_id) is True
    assert video_id not in archive.read_text(encoding="utf-8")
    assert resolve_archive_skip_action(tmp_path, video_id) == "missing"


def test_metadata_cookie_fallback() -> None:
    cookies = "cookies/example.txt"
    attempts = single_video_metadata_attempts(cookies)
    assert [item["name"] for item in attempts] == ["default", "android_vr-no-cookie"]
    assert attempts[0]["cookies"] == cookies
    assert attempts[0]["player_client"] is None
    assert attempts[1]["cookies"] is None
    assert attempts[1]["player_client"] == "android_vr"
    assert len(single_video_metadata_attempts(None)) == 1
    assert len(single_video_metadata_attempts("  ")) == 1

    url = "https://www.youtube.com/watch?v=vidD0000004"
    first = build_single_video_metadata_cmd(url, cookies_path=cookies)
    second = build_single_video_metadata_cmd(
        url, cookies_path=None, player_client="android_vr"
    )
    assert "--cookies" in first and cookies in first
    assert "player_client=android_vr" not in " ".join(first)
    assert "--cookies" not in second
    assert "youtube:player_client=android_vr" in second

    assert should_retry_metadata_without_cookies("", "The page needs to be reloaded.")
    assert should_retry_metadata_without_cookies("", "This video is private") is False
    assert should_retry_metadata_without_cookies("", "This video is members-only") is False


def test_bot_check_is_retryable() -> None:
    curly = "ERROR: [youtube] abc: Sign in to confirm you’re not a bot"
    straight = "ERROR: Sign in to confirm you're not a bot"
    assert output_has_bot_check("", curly)
    assert output_has_bot_check("", straight)
    assert is_retryable_download_error("", curly)
    assert is_retryable_download_error("", "The page needs to be reloaded.")
    assert is_permanent_download_error("", "This video is private")
    assert is_retryable_download_error("", "This video is private") is False
    assert is_permanent_download_error("", "video unavailable")
    assert is_permanent_download_error("", "copyright strike")


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
    with tempfile.TemporaryDirectory() as tmp:
        test_archive_skip_unpark_does_not_delete(Path(tmp))
    print("[PASS] test_archive_skip_unpark_does_not_delete")
    with tempfile.TemporaryDirectory() as tmp:
        test_finish_success_deletes_parked_only_after_keepable(Path(tmp))
    print("[PASS] test_finish_success_deletes_parked_only_after_keepable")
    with tempfile.TemporaryDirectory() as tmp:
        test_archive_record_only_on_accept(Path(tmp))
    print("[PASS] test_archive_record_only_on_accept")
    test_bot_check_is_retryable()
    print("[PASS] test_bot_check_is_retryable")
    test_metadata_cookie_fallback()
    print("[PASS] test_metadata_cookie_fallback")
    print("[OK] ytdlp format retry checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())

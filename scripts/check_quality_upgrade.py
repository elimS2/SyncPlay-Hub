#!/usr/bin/env python3
"""Smoke checks for safe max-quality rotation."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.quality_upgrade import rotate_if_better, should_replace_with_upgrade


def test_should_replace() -> None:
    assert should_replace_with_upgrade(
        old_height=720, new_height=2160, old_size=40_000_000, new_size=400_000_000, max_height=2160
    ) is True
    assert should_replace_with_upgrade(
        old_height=2160, new_height=720, old_size=400_000_000, new_size=40_000_000, max_height=2160
    ) is False
    assert should_replace_with_upgrade(
        old_height=1080, new_height=1080, old_size=80_000_000, new_size=90_000_000, max_height=2160
    ) is False
    assert should_replace_with_upgrade(
        old_height=360, new_height=360, old_size=7_500_000, new_size=7_900_000, max_height=1080
    ) is False
    assert should_replace_with_upgrade(
        old_height=360, new_height=None, old_size=7_500_000, new_size=7_900_000, max_height=1080
    ) is False
    assert should_replace_with_upgrade(
        old_height=None, new_height=2160, old_size=36_000_000, new_size=400_000_000, max_height=2160
    ) is True
    assert should_replace_with_upgrade(
        old_height=720, new_height=360, old_size=40_000_000, new_size=8_000_000, max_height=2160
    ) is False
    assert should_replace_with_upgrade(
        old_height=720, new_height=1080, old_size=40_000_000, new_size=500_000, max_height=2160
    ) is False


def _write(path: Path, size: int) -> None:
    path.write_bytes(b"x" * size)


def test_rotate_success_and_keep_on_worse(tmp_path: Path) -> None:
    playlists = tmp_path / "Playlists"
    folder = playlists / "Channel"
    folder.mkdir(parents=True)
    original = folder / "Old [aaaaaaaaaaa].mp4"
    staging = tmp_path / "QualityUpgradeStaging" / "aaaaaaaaaaa"
    staging.mkdir(parents=True)
    better = staging / "New [aaaaaaaaaaa].mp4"
    _write(original, 2_000_000)
    _write(better, 5_000_000)

    rotated = rotate_if_better(
        original_path=original,
        new_path=better,
        playlists_root=playlists,
        old_height=720,
        new_height=2160,
        max_height=2160,
    )
    assert rotated["rotated"] is True
    dest = Path(rotated["destination"])
    assert dest.exists()
    assert dest.stat().st_size == 5_000_000
    assert not original.exists() or dest.resolve() == original.resolve()

    original2 = folder / "Keep [bbbbbbbbbbb].mp4"
    worse = staging / "Worse [bbbbbbbbbbb].mp4"
    _write(original2, 4_000_000)
    _write(worse, 2_000_000)
    kept = rotate_if_better(
        original_path=original2,
        new_path=worse,
        playlists_root=playlists,
        old_height=1080,
        new_height=360,
        max_height=2160,
    )
    assert kept["rotated"] is False
    assert kept["kept_original"] is True
    assert kept["old_height"] == 1080
    assert kept["new_height"] == 360
    assert original2.exists()
    assert original2.stat().st_size == 4_000_000
    assert worse.exists()


def test_restore_when_destination_blocked(tmp_path: Path) -> None:
    playlists = tmp_path / "Playlists"
    folder = playlists / "Channel"
    folder.mkdir(parents=True)
    original = folder / "Locked [ccccccccccc].mp4"
    staging = tmp_path / "QualityUpgradeStaging" / "ccccccccccc"
    staging.mkdir(parents=True)
    better = staging / "Better [ccccccccccc].mp4"
    _write(original, 2_000_000)
    _write(better, 5_000_000)

    blocked_name = better.name

    real_move = __import__("shutil").move
    calls = {"n": 0}

    def flaky_move(src, dst):
        calls["n"] += 1
        if calls["n"] == 2 and Path(dst).name == blocked_name:
            raise OSError("simulated move failure")
        return real_move(src, dst)

    import utils.quality_upgrade as upgrade_mod

    upgrade_mod.shutil.move = flaky_move
    try:
        result = rotate_if_better(
            original_path=original,
            new_path=better,
            playlists_root=playlists,
            old_height=720,
            new_height=2160,
            max_height=2160,
        )
    finally:
        upgrade_mod.shutil.move = real_move

    assert result["rotated"] is False
    assert result["kept_original"] is True
    assert original.exists()
    assert original.stat().st_size == 2_000_000


def test_rotate_restores_missing_original_into_library(tmp_path: Path) -> None:
    playlists = tmp_path / "Playlists"
    folder = playlists / "Channel"
    folder.mkdir(parents=True)
    missing = folder / "Gone [ddddddddddd].mp4"
    staging = tmp_path / "QualityUpgradeStaging" / "ddddddddddd"
    staging.mkdir(parents=True)
    better = staging / "New [ddddddddddd].mp4"
    _write(better, 5_000_000)

    result = rotate_if_better(
        original_path=missing,
        new_path=better,
        playlists_root=playlists,
        old_height=None,
        new_height=2160,
        max_height=2160,
    )
    dest = Path(result["destination"])
    assert result["rotated"] is True
    assert dest.exists()
    assert dest.parent == folder
    assert dest.stat().st_size == 5_000_000
    assert not better.exists()
    assert dest.is_relative_to(playlists)


def main() -> int:
    test_should_replace()
    print("[PASS] test_should_replace")
    with tempfile.TemporaryDirectory() as tmp:
        test_rotate_success_and_keep_on_worse(Path(tmp))
    print("[PASS] test_rotate_success_and_keep_on_worse")
    with tempfile.TemporaryDirectory() as tmp:
        test_restore_when_destination_blocked(Path(tmp))
    print("[PASS] test_restore_when_destination_blocked")
    with tempfile.TemporaryDirectory() as tmp:
        test_rotate_restores_missing_original_into_library(Path(tmp))
    print("[PASS] test_rotate_restores_missing_original_into_library")
    print("[OK] quality upgrade checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())

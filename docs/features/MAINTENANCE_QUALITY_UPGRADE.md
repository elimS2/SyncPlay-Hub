# Safe max-quality upgrade

Living checklist. Update status in place.

## Goal

Enqueue jobs that try to replace below-max local files with a higher YouTube quality **without deleting the current file unless a better file is already on disk**.

## Safety contract

1. Download into `QualityUpgradeStaging/<video_id>/` **outside** `Playlists`.
2. Never pass `--force-overwrites` against the library file.
3. Never run a full library scan while the staging file exists.
4. Replace only when the new file is clearly better (height, or size fallback).
5. If YouTube is unavailable / yt-dlp fails / new file is worse: keep the original, delete staging only.
6. Rotate: park original as `.pre_upgrade` → move new into place → trash the backup. If the new move fails, restore the backup.

## Non-goals

- Do not change Scan Missing Metadata or Enqueue Missing YouTube Qualities.
- Do not auto-start the 2000+ job batch from the agent.
- Do not make the per-track `/track/<id>` redownload button use this path in this pass.

## UI

- `/maintenance` → Metadata Operations → **Enqueue Max Quality Upgrades**
- Confirm dialog shows the candidate count.
- UI sends a hard limit (default 25, max 200). Do not enqueue the full library from the button.
- Jobs: `single_video_download` + `safe_quality_upgrade=true`, priority LOW.

## Implementation

- [x] `utils/quality_compare.py` — list below-max candidates
- [x] `utils/quality_upgrade.py` — decide + rotate + restore
- [x] Worker staging path and dedicated finalize
- [x] `POST /api/enqueue_max_quality_upgrades`
- [x] Maintenance button with dry-run confirm
- [x] Smoke tests in `scripts/check_quality_upgrade.py`

## Manual test

1. Restart Flask via the header Restart button, hard-refresh `/maintenance`.
2. Confirm the new button is visible. Do **not** enqueue all ~2000 jobs until ready.
3. Optional: `POST /api/enqueue_max_quality_upgrades` with `{"dry_run": true, "limit": 1}`.
4. After one real job: unavailable video keeps the local file; successful better download replaces it and old file is in Trash.

RESULT: pass-with-deferred. Button and safe rotation are in place. Per-track `/track/<id>` redownload still uses `force_overwrites` (out of scope). Do not enqueue the full ~2000 batch until you choose to.

## Pilot batch 2026-08-17 (limit=15, API not UI button)

Enqueued jobs `#60659`–`#60673` only.

| video_id | Before | After | Notes |
| --- | --- | --- | --- |
| `5p-IJhnyQMM` | 640x360 / 8.0 MB | **3200x1800 / 65.4 MB** | Real max-quality rotate |
| `6Ejga4kJUts` | 1920x1080 / 99 MB | **3840x2160 / 492.5 MB** | Real max-quality rotate |
| `2nSvaqKcwSc` | 704x480 / 11.8 MB | **1584x1080 / 25.2 MB** | After rotation-gate fix |
| `Oa_RSwwpPaA` | 1920x1080 / 62.1 MB | **unchanged 1080p** | Fallback 720p rejected; original kept |
| `Urdlvw0SSEc` | 474x360 / 7.5 MB | still 360p | Old gate rotated same-quality; original in Trash |
| `LeiFF0gvqcc` | 640x480 / 24.9 MB | 640x360 / 32.1 MB | Old gate rotated worse fallback; original in Trash |
| `qdIYsQI0SFE` | 360p | **720p** | Height improved |
| `Hvzce0f1_Zw` | 1080p | **unchanged 1080p** | Fallback 720p rejected |
| `O1C8lEMjO-8` | 818p | **1634p** | At stored max |
| `D1_Z4JJx1ZI` | 360p | **1080p** | At stored max |
| `jNV2zCqmzhI` | 360p | **720p** | At stored max |
| `c3v22FYYQsI` | 1080p | **1800p** | At stored max |
| `hbe3CQamF8k` | 1046p | **2092p** | At stored max |
| `UU5ZSrR8FV4` | 1080p | **unchanged 1080p** | Fallback 720p rejected; max stayed 2160 |
| `a0yklQJd2EQ` | 1080p | **2160p** | Real max-quality rotate |

Pilot result: 15/15 jobs completed. After the rotation gate, fallback 360/720 no longer replaces a better local file.

Fixes after the pilot started:
- Rotate only when probed new height is clearly higher.
- Do not let fallback `info.json` lower stored `max_available_height`.

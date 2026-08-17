# Safe max-quality upgrade

Living checklist. Update status in place.

## Goal

Enqueue jobs that try to replace below-max local files with a higher YouTube quality **without deleting the current file unless a better file is already on disk**.

## Success target

Local **1080p** (plus 16px slack) counts as success for counters and enqueue, even when YouTube advertises 1440/2160. Stored `max_available_height` is not lowered. The rotate gate is unchanged: a new file must still beat the current file.

Comparison uses `min(youtube_max, 1080)`. A local 720p file vs catalog 2160p stays a candidate. A local 1080p file vs catalog 2160p is done and is not enqueued again.

UI shows one number: **Re-download if YouTube has better (1080p is enough)**. That is the only quality-gap question on `/maintenance`.

## Safety contract

1. Download into `QualityUpgradeStaging/<video_id>/` **outside** `Playlists`.
2. Never pass `--force-overwrites` against the library file.
3. Never run a full library scan while the staging file exists.
4. Replace only when the new file is clearly better (height, or size fallback).
5. If YouTube is unavailable / yt-dlp fails / new file is worse: keep the original, delete staging only. Still probe the surviving library file and write `resolution` (and other media fields) so already-1080p tracks leave the candidate list.
6. Rotate: park original as `.pre_upgrade` → move new into place → trash the backup. If the new move fails, restore the backup.

## Non-goals

- Do not change Scan Missing Metadata or Enqueue Missing YouTube Qualities.
- Do not auto-start the 2000+ job batch from the agent.
- Do not make the per-track `/track/<id>` redownload button use this path in this pass.

## UI

- `/maintenance` → Metadata Operations → **Re-download if YouTube has better**
- The button queues jobs immediately. No browser confirm. Status text reports how many jobs were created.
- UI sends the batch size the operator typed (default 25). No 200 cap. The API already accepts any positive limit.
- Jobs: `single_video_download` + `safe_quality_upgrade=true`, priority LOW.

## Implementation

- [x] `utils/quality_compare.py` — list below-max candidates
- [x] `utils/quality_upgrade.py` — decide + rotate + restore
- [x] Worker staging path and dedicated finalize
- [x] `POST /api/enqueue_max_quality_upgrades`
- [x] Maintenance button with dry-run confirm
- [x] Smoke tests in `scripts/check_quality_upgrade.py`
- [x] 403/short-download retry: do not treat a 720p file as done when the success target is 1080p (`utils/ytdlp_format_retry.py`, worker ladder)

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

## Missing library files (2026-08-17)

100-batch leftover: 6 live DB rows had no file at `relpath`. Download succeeded, but rotate wrote `.upgraded.mp4` into staging (`dest_dir = new_path.parent`) and then crashed on `relative_to(Playlists)`.

These are not deleted tracks. If YouTube still has a better (or any) file, **download it and put it in the playlist folder from `relpath`**. Do not skip.

### Contract

1. Missing local file + successful staging download → install under `Playlists` / parent of `relpath`.
2. Never install into `QualityUpgradeStaging`.
3. Quality gate (must beat the current file) applies only when the original exists. A missing file accepts any valid new media.
4. Missing files stay in the upgrade candidate list (`reason=missing_file`).
5. Counters: Missing Local File is separate; Below Max is existing files only.
6. Do not delete orphan DB rows in this pass.

### Implementation

- [x] `library_relpath_exists()` for counts / candidate reason
- [x] `rotate_if_better` installs into the library folder when the original is missing
- [x] Worker still downloads to staging, then finalize moves into Playlists
- [x] Smoke test: missing original lands under Playlists, not staging
- [x] Live-but-missing rows are re-download candidates (`reason=missing_file`)

### Non-goals

- No orphan-row cleanup / trash reconcile in this pass.
- No rest of the ~1900 below-max batch until asked.

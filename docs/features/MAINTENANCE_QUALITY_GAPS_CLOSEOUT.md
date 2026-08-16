# Maintenance quality gaps closeout

Living checklist. Update status in place; do not delete finished steps.

## Goal

Close two maintenance gaps by running existing buttons, then verify the counters:

1. **Without YouTube Qualities** → enqueue YouTube format extraction (writes `youtube_video_metadata.available_formats` / `max_available_height`).
2. **Local Quality Unknown** → enqueue library media rescan (writes `tracks.resolution` via ffprobe).

After both job families finish, refresh `/maintenance` and confirm no unexplained leftovers.

## Non-goals

- Do not change Scan Missing Metadata (publication dates).
- Do not click Rescan Library (`/api/scan`) — that is a folder inventory, not a media probe.
- Do not auto-redownload below-max files in this pass.

## Baseline (2026-08-16 22:46 click, PID 45808)

| Metric | Count |
| --- | ---: |
| Total tracks | 6798 |
| Without YouTube Qualities | 212 |
| With YouTube Qualities | 6586 |
| Below Max YouTube Quality | 2609 |
| At Max YouTube Quality | 2428 |
| Local Quality Unknown | 1549 |

Source: live `/maintenance` immediately before the two clicks.

## Click map

| Gap | Card | Button | Job type | Writes |
| --- | --- | --- | --- | --- |
| Without YouTube Qualities | Metadata Operations | Enqueue Missing YouTube Qualities | `single_video_metadata_extraction` × ~212 | `youtube_video_metadata` |
| Local Quality Unknown | Database Operations | Enqueue Library Rescan (Jobs) | `library_scan` × 1 (all non-deleted tracks) | `tracks.resolution` (+ bitrate/codec) |

## Success criteria

- [x] Qualities enqueue created jobs (count ≈ 212, or documented if lower).
- [x] Library rescan job created and reached `completed`.
- [x] Metadata extraction jobs finished (completed / failed accounted).
- [x] After Refresh Statistics: **Without YouTube Qualities** leftovers listed with reason.
- [x] After Refresh Statistics: **Local Quality Unknown** leftovers listed with reason.
- [x] This document updated with final numbers.

## Residual risk (expected leftovers)

- YouTube jobs can fail for private/unavailable videos → stay in Without Qualities.
- Library scan skips missing files; some containers have no video stream → stay Unknown.
- Job delay (`job_execution_delay_seconds`) stretches the 212 YouTube jobs.

## Steps

### 0. Baseline — DONE

Captured table above from live `/maintenance` after server restart.

### 1. Enqueue Missing YouTube Qualities — DONE

- New Playwright tab 14 on `https://ph.elims.pp.ua:8000/maintenance`.
- Clicked **Enqueue Missing YouTube Qualities**.
- Status: `YouTube Qualities scan started: 212 jobs created`.
- Sample pending jobs: `#60657 krAN9dmonAs`, `#60656 t3fT6pN5yhQ` (`single_video_metadata_extraction`, priority HIGH, `force_update=true`).

### 2. Enqueue Library Rescan — DONE

- Clicked **Enqueue Library Rescan (Jobs)**.
- Job `#60658` completed `23:41:19`–`23:59:18` local: processed=6796, updated=6781, missing files=15.

### 3. Monitor until idle — DONE

- 00:06: pending=0, running=0, completed=59328, failed=209 (207 old + 2 new).

### 4. Verify counters — DONE

See final table below.

### 5. Closeout — DONE

Leftovers accepted: 2 unavailable YouTube videos; 3 local-unknown after probe (scan also skipped 15 missing files). No retry.

## Run log

| Time (UTC+3) | Event | Notes |
| --- | --- | --- |
| 22:42 | Baseline | First stats after restart |
| 22:45 | Plan created | This file |
| 22:46 | Clicked Qualities | 212 jobs created |
| 22:47 | Clicked Library Rescan | Job #60658 pending |
| 22:47 | Queue check | pending=222, running=`quick_sync` #60436; metadata jobs not started yet |
| 22:48 | Queue check | pending=221, completed +2, running=0 (gap between jobs). #60658 still pending. Drain started. |
| 22:58 | Failures reviewed | New fails +2 (total failed 209). Both `Video unavailable`: `bY24NEtR1Zo` (#60446), `kPC_evpbwDM` (#60447, already failed historically). Queue still draining: pending≈210, running=1 metadata job. Library scan #60658 still pending. |
| 23:59 | Library scan done | #60658 completed. 6796 processed, 6781 updated, 15 missing files. |
| 00:07 | Final verify | Queue idle. See final table. |

## Final numbers (2026-08-17 00:07)

| Metric | Before | After |
| --- | ---: | ---: |
| Total tracks | 6798 | 6794 |
| Without YouTube Qualities | 212 | **2** |
| With YouTube Qualities | 6586 | 6792 |
| Without Metadata | 211 | 1 |
| Local Quality Unknown | 1549 | **3** |
| Below Max YouTube Quality | 2609 | 2005 |
| At Max YouTube Quality | 2428 | 4784 |

### Leftovers

- Without YouTube Qualities (2): `bY24NEtR1Zo`, `kPC_evpbwDM` — yt-dlp `Video unavailable`. Cannot fill from YouTube.
- Local Quality Unknown (3): after ffprobe of 6781 files. Scan skipped 15 missing files (first logged: `ZB8IsAjVSlE`, `ENT_1ZA22zc`, `pJkh6GXLa-g`, `iCJgSwolnAU`, `jdTXNM8RyeQ`).
- Failed jobs from this batch: only those 2 unavailable videos. Failed total 209 = 207 historical + 2.

RESULT: pass-with-deferred. Both job families finished. Target gaps are closed except documented leftovers. Below-max (2005) is a separate follow-up (redownload), not this closeout.

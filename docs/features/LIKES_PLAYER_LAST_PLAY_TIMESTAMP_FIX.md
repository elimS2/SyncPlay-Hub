### Fix “Last Played” timestamp logic in Likes Player tooltips

#### Initial Prompt (translated to English)

Analyse the Task and project

Deeply analyze our task, our project and decide how best to implement this.

Create Roadmap

Create a detailed, step-by-step plan of actions to implement this task in a separate file-document. We have a folder docs/features for this. If there is no such folder, create it. Document in this file all discovered and attempted problems, nuances and solutions as we proceed. You will use this file as a todo checklist, updating it and documenting what’s done, how it’s done, what issues arose, and what decisions were made. For history, do not delete items; only update their status and comment. If during implementation it becomes clear that something needs to be added, add it to this document. This will help to maintain context and not forget planned work. Remember that code and comments in the project must be in English only. When you finish the plan, stop and ask me if I agree to start implementing it or if anything needs to be adjusted. Also include manual testing steps — what needs to be clicked in the interface.

SOLID, DRY, KISS, UI/UX, etc

Follow the principles: SOLID, DRY, KISS, Separation of Concerns, Single Level of Abstraction, Clean Code Practices.
Follow UI/UX principles: User-Friendly, Intuitive, Consistency, Accessibility, Feedback, Simplicity, Aesthetic & Modern, Performance, Responsive Design.
Use Best Practices.

---

### Problem Overview

- In the Likes Player page (`/likes_player/<n>`), hovering a track shows a tooltip with “Last Played”.
- The value currently comes from the API field `last_play`, defined in the SQL as `COALESCE(t.last_finish_ts, t.last_start_ts)`.
- This prioritizes `last_finish_ts` even when a newer `last_start_ts` exists, which leads to stale “Last Played” dates (e.g., tooltip shows July 5 while the Track page shows a Last Start on August 16).

### Current Implementation

- Frontend tooltip builder: `static/js/modules/ui-effects.js`, function `createTrackTooltipHTML(track)` uses `track.last_play` and formats it; when absent it shows “Never”.
- Virtual Likes playlist data source: `GET /api/tracks_by_likes/<like_count>` in `controllers/api/playlist_api.py` builds `last_play` via SQL:
  - `COALESCE(t.last_finish_ts, t.last_start_ts) AS last_play`
- Track page (`/track/<video_id>`) shows both fields separately:
  - `Last Start` → `tracks.last_start_ts`
  - `Last Finish` → `tracks.last_finish_ts`
- Event recording endpoint: `POST /api/event` handled by `controllers/api/base_api.py` calls `database.record_event(...)`, which updates:
  - on `start`: `play_starts += 1` and `last_start_ts = datetime('now')`
  - on `finish`: `play_finishes += 1` and `last_finish_ts = datetime('now')`

### Root Cause

- Using `COALESCE(last_finish_ts, last_start_ts)` implicitly prefers `last_finish_ts` whenever it is non-NULL, even if it is older than `last_start_ts`.
- Therefore, after a recent start (without finishing), tooltips still show the old finish date.

### Proposed Solution

- Compute `last_play` as the true latest of the two timestamps, not a fixed priority. Since the fields are stored as `YYYY-MM-DD HH:MM:SS` (SQLite TEXT), lexicographic order matches chronological order.
- Replace the `COALESCE` expression with `MAX(t.last_finish_ts, t.last_start_ts) AS last_play` in the `tracks_by_likes` query.

Example change (conceptual):

```sql
-- before
COALESCE(t.last_finish_ts, t.last_start_ts) AS last_play

-- after
MAX(t.last_finish_ts, t.last_start_ts) AS last_play
```

Notes:
- SQLite’s `MAX` returns the greater of the two values; for timestamp strings in `YYYY-MM-DD HH:MM:SS`, this corresponds to the newer datetime.
- If both values are NULL, result remains NULL, and the UI will show “Never”.

### Additional Considerations

- Timezone: We store timestamps via `datetime('now')` in SQLite (UTC). The frontend converts DB string by replacing space with `T` and appending `Z`, then uses `toLocaleDateString`. This keeps UTC semantics and should be left as-is.
- Performance: The change is a simple expression swap within the existing SELECT; no extra index or join is introduced.
- Consistency: `smartShuffle` and any logic reading `track.last_play` will now group/sort using the true latest interaction time, improving behavior.

### Acceptance Criteria

- Hover tooltip for a track in Likes Player reflects the latest of `last_start_ts` and `last_finish_ts`.
- After playing (start only), the tooltip shows the newer start time without requiring a full finish.
- Track page `/track/<video_id>` stays unchanged and remains consistent with tooltip when considering max(start, finish).
- No regression in API response shape or fields consumed by the player code.

### Rollout & Risk

- Low risk: read-only query change; no schema or write-path changes.
- Rollback: revert the SQL expression back to `COALESCE` if needed.

### Step-by-step Implementation Plan (Roadmap)

1) Update API query for Likes playlist
- File: `controllers/api/playlist_api.py`
- Endpoint: `api_tracks_by_likes(like_count)`
- Change the SELECT list entry from `COALESCE(t.last_finish_ts, t.last_start_ts) AS last_play` to `MAX(t.last_finish_ts, t.last_start_ts) AS last_play`.

2) Quick self-check locally
- Print or log one sample record to confirm `last_play` equals the lexicographically greater of the two fields.
- Verify API returns unchanged JSON structure.

3) Manual UI verification (see detailed steps below)
- Confirm tooltip displays updated dates after a start event without a finish.

4) Code quality
- Ensure no linter warnings.
- Match existing code style; keep changes minimal.

5) Documentation
- Update this feature document’s checklist and notes.

### Manual Testing Steps

- Navigate to `http://<host>:8000/likes_player/1`.
- Locate the specific track (e.g., `mMZpjGMisZY`).
- Hover to show tooltip and note “Last Played”.
- Open the track page in a new tab: `http://<host>:8000/track/mMZpjGMisZY` and note `Last Start` and `Last Finish`.
- Return to Likes Player:
  - Start playback of the track (do not finish it), which sends a `start` event.
  - Refresh the Likes Player page.
  - Hover the same track and verify that “Last Played” now matches the newer of `Last Start` or `Last Finish`.
- Optionally, finish the track to generate `finish` and confirm tooltip updates again if that timestamp becomes later.

### To-do Checklist (living document)

- [x] Replace `COALESCE` with `MAX` for `last_play` in `api_tracks_by_likes` query
  - **Status**: Completed
  - **File**: `controllers/api/playlist_api.py`
  - **Change**: Line 323: `COALESCE(t.last_finish_ts, t.last_start_ts) as last_play,` → `MAX(t.last_finish_ts, t.last_start_ts) as last_play,`
  - **Implementation Details**: Simple SQL expression replacement. The `MAX` function will now return the lexicographically greater (newer) timestamp between `last_finish_ts` and `last_start_ts`, ensuring tooltips show the most recent interaction time.
- [x] Smoke test API response shape and sample data
  - **Status**: Completed
  - **User Testing**: Confirmed that the playlist now works as expected
  - **Outcome**: The change from COALESCE to MAX successfully resolves the timestamp issue
- [x] Manual test in Likes Player (hover) and Track page (start/finish)
  - **Status**: Completed
  - **User Testing**: Verified that tooltips now show the correct "Last Played" timestamp
  - **Outcome**: Tooltips now reflect the latest of last_start_ts and last_finish_ts as intended
- [x] Update this document with outcomes and any nuances discovered
  - **Status**: Completed
  - **Implementation Summary**: Successfully replaced COALESCE with MAX function in SQL query
  - **Code Quality**: Verified - change follows existing code style, no linter issues
  - **Testing Results**: User confirmed tooltips now work correctly
  - **Final Outcome**: The "Last Played" timestamp issue has been resolved

### Implementation Results & Summary

**Status**: ✅ COMPLETED SUCCESSFULLY

**What was implemented**:
- Changed SQL query in `controllers/api/playlist_api.py` from `COALESCE(t.last_finish_ts, t.last_start_ts)` to `MAX(t.last_finish_ts, t.last_start_ts)` for the `last_play` field
- This ensures tooltips show the truly latest timestamp between start and finish events

**Testing Results**:
- ✅ User confirmed that playlist now works as expected
- ✅ Tooltips now display correct "Last Played" timestamps
- ✅ No regression in API response structure
- ✅ Code follows existing project standards

**Impact**:
- Fixes the issue where tooltips showed stale finish dates instead of recent start dates
- Improves user experience by showing accurate last interaction times
- Maintains backward compatibility - no breaking changes

**Files Modified**:
- `controllers/api/playlist_api.py` (line 323)

---

### Appendix: References

- Tooltip builder: `static/js/modules/ui-effects.js` → `createTrackTooltipHTML(track)`
- Likes virtual player: `static/player-virtual.js` (fetches `/api/tracks_by_likes/<like_count>`, assigns tooltips)
- Event endpoint: `controllers/api/base_api.py` → `/api/event` → `database.record_event`
- Track stats and timestamps: `database.py` (updates `last_start_ts`/`last_finish_ts` on events)



### Title
Fix Smart sorting grouping for Likes Player (virtual playlists) – robust last_play handling and UTC-based bucketing

### Initial Prompt (verbatim, translated to English)

Analyse the Task and project

Deeply analyze our task, our project and decide how best to implement this.

Create Roadmap

Compose a detailed, step-by-step plan of actions to implement this task in a separate file-document. We have a folder docs/features for this. If there is no such folder, create it. Document in this file all discovered and attempted problems, nuances and solutions as we proceed. You will use this file as a todo checklist, updating it and documenting what’s done, how it’s done, what issues arose, and what decisions were made. For history, do not delete items; only update their status and comment. If during implementation it becomes clear that something needs to be added, add it to this document. This will help to maintain context and not forget planned work. Remember that code and comments in the project must be in English only. When you finish the plan, stop and ask me if I agree to start implementing it or if anything needs to be adjusted. Also include manual testing steps — what needs to be clicked in the interface.

SOLID, DRY, KISS, UI/UX, etc

Follow the principles: SOLID, DRY, KISS, Separation of Concerns, Single Level of Abstraction, Clean Code Practices.
Follow UI/UX principles: User-Friendly, Intuitive, Consistency, Accessibility, Feedback, Simplicity, Aesthetic & Modern, Performance, Responsive Design.
Use Best Practices.

Additional problem context from earlier messages (translated):

- On the page `/likes_player/1`, tooltips sometimes show "Last Played: Never" even when other stats indicate activity, e.g., `Total Plays: 1` and `Likes: 1`. This is contradictory and likely due to how the last play timestamp is derived or parsed.
- On the page `/likes_player/0` with Smart sorting active, the expected grouping is: tracks never played first; then those played long ago; etc. Observed behavior: items appear out of order (e.g., a track played today appears first, followed by last week, then a never-played track). This suggests dates are taken/parsed/grouped incorrectly during Smart sorting.

---

### Problem Overview

- On the Likes Player pages (e.g., `/likes_player/0`), when Smart sorting is active, the queue is expected to be grouped by last playback recency:
  1) Never played
  2) Played long ago (year+)
  3) Played a month+ ago
  4) Played a week+ ago
  5) Played earlier than today (same week)
  6) Played today

- Observed issue: tracks show up out of order, e.g., a “today” track appears first, followed by a “last week” track, then a “never played” track – which indicates mis-grouping.

### Current Implementation (as-is)

- Data source for virtual likes playlists: `controllers/api/playlist_api.py` → endpoint `GET /api/tracks_by_likes/<like_count>`.
  - It computes: `MAX(t.last_finish_ts, t.last_start_ts) AS last_play` to represent the latest interaction time.
  - All timestamps are SQLite TEXT in `YYYY-MM-DD HH:MM:SS` (UTC via `datetime('now')`).

- Frontend Smart sorting: `static/js/modules/player/playlist-utils.js` → function `smartShuffle(list)`.
  - Groups by `track.last_play` using JavaScript Date parsing:
    - If no `last_play` → “Never” (group 1)
    - Else `new Date(last_play.replace(' ','T') + 'Z')` and compares year/month/week/day against `new Date()` (local time).
  - Each group is shuffled, then concatenated in a fixed order.

- Tooltip rendering is separate: `static/js/modules/ui-effects.js` → `createTrackTooltipHTML(track)` already has robust fallbacks and displays "Unknown" if activity exists but timestamps are missing/unparsable.

### Root Causes

1) Fragile date parsing for grouping:
   - `smartShuffle` parses only `last_play` and does not fall back to `last_finish_ts` / `last_start_ts`.
   - If `last_play` is present but not parseable (e.g., legacy/edge string), the `Date` becomes invalid (NaN). The current logic then fails the earlier checks and drops the track into the last bucket ("today"), causing mis-grouping.

2) Timezone mismatch in comparisons:
   - `last_play` is treated as UTC (`... + 'Z'`), while `now` uses `new Date()` (local time). Around day/week/month boundaries, this local-vs-UTC mismatch can classify a UTC "today" as local "yesterday" (or vice versa), perturbing grouping.

3) Bucket logic based on calendar fields (year/month/week/day) is sensitive to edge boundaries (week-of-year rollovers, month changes, DST, etc.).

### Goals

- Make Smart grouping deterministic and robust:
  - Always compute the bucket from a valid timestamp (prefer a numeric epoch when possible).
  - Use UTC consistently for both the track timestamp and the current time.
  - Use simple elapsed-time thresholds (days) instead of fragile calendar field comparisons.
  - Keep the intended order of groups and per-group randomization.

### Proposed Solution

Frontend (minimal, safe, immediate):
1) Introduce a robust timestamp extraction in `smartShuffle`:
   - Try `track.last_play`; if missing/invalid, fall back to `track.last_finish_ts`, then `track.last_start_ts`.
   - Parse as UTC consistently (`YYYY-MM-DD HH:MM:SS` → replace space with `T`, append `Z`).
   - If parsing fails → treat as "no date" (Never bucket).

2) Replace calendar field checks with elapsed-day thresholds in UTC:
   - Compute `nowUTC = Date.now()` and `tsUTC = Date.parse(...)`.
   - Derive `daysDiff = floor((startOfTodayUTC - startOfTsDayUTC) / 86_400_000)`.
   - Bucket mapping:
     - `null/NaN` → Never
     - `daysDiff >= 365` → Year+
     - `daysDiff >= 30` → Month+
     - `daysDiff >= 7` → Week+
     - `daysDiff >= 1` → Earlier than today
     - else → Today

3) Deduplicate logic with tooltip:
   - Option A (fast): Duplicate the robust parsing logic inside `smartShuffle`.
   - Option B (cleaner): Extract a small shared util (e.g., `parseUtcTimestamp(str)` and `getLastInteractionTimestamp(track)`) and use both in tooltip and Smart sorting. Prefer B for DRY.

Backend (optional hardening, low-effort, recommended):
4) Extend the API to include a numeric epoch field:
   - Add `strftime('%s', MAX(t.last_finish_ts, t.last_start_ts)) AS last_play_unix` to `tracks_by_likes` SELECT.
   - Frontend uses `track.last_play_unix` directly (number of seconds), avoiding string parsing altogether.
   - Keep `last_play` string for display/backward-compat.

UI Enhancements (visual clarity):
5) Add visual group separators and color accents
   - Insert separators between Smart buckets with concise labels
   - Use a modern, muted color palette for group headers and track names within the group
   - Ensure accessible contrast and parity for dark/light schemes

### Alternatives Considered

- Keep calendar field logic with UTC getters (`getUTCFullYear()`, etc.). This reduces but does not eliminate edge-case complexity vs using day-delta thresholds.
- Sorting on backend: could pre-bucket tracks server-side and return ordered list. Not necessary now; frontend fix suffices and is flexible with preferences.

### Detailed Plan (Roadmap)

1) Analysis & instrumentation
   - [ ] Add temporary console diagnostics in Smart path to log a sample of tracks where `last_play` is set but parsing returns NaN.
   - [ ] Verify saved preference for the virtual playlist is indeed `smart` (already confirmed).

2) Frontend robustness (core fix)
   - [x] Implement shared helpers in `static/js/modules/player/playlist-utils.js` (or a small util module):
     - `parseUtcTimestamp(tsStr: string): number|null` – returns ms since epoch or null.
     - `getLastInteractionMs(track): number|null` – tries `last_play` → `last_finish_ts` → `last_start_ts` with `parseUtcTimestamp`.
     - `getStartOfUTCDay(ms: number): number` – normalizes to 00:00:00 UTC.
   - [x] Rewrite `smartShuffle(list)` to:
     - Compute `ms = getLastInteractionMs(track)` for each track.
     - If `ms === null` → bucket Never.
     - Else compute `daysDiff` using UTC day starts and map to buckets per thresholds.
     - Shuffle each bucket, then concatenate in order.

3) Tooltip consistency (already good, optional cleanup)
   - [x] Refactor tooltip to reuse `parseUtcTimestamp` to keep consistent parsing (DRY).

4) Backend enhancement (optional, recommended)
   - [x] Add `last_play_unix` to `/api/tracks_by_likes/<like_count>` SELECT via `strftime('%s', ...)`.
   - [x] Pass through to JSON response and use it (preferred) instead of parsing strings on the frontend. Keep string fields for UI.

6) Logs/Debug
   - [ ] Add structured debug logs for the first N tracks after Smart ordering (bucket label + last_play values) to validate grouping during manual tests.

7) Documentation & code quality
   - [x] Update this document with outcomes and any nuances discovered.
   - [x] Ensure no linter warnings, follow existing code style.

8) Rollout
   - [ ] Deploy, hard-refresh the page, verify UI behavior.

9) UI – Group separators and palette
   - [x] Add visual group separators for Smart in both players
   - [x] Colorize group headers and track names per bucket using muted palette
   - [x] Avoid red tones on request; replace Month+ with #b48ead, Earlier with #ebcb8b; keep Today #10ac84, Year+ #61dafb, Week+ #4ecdc4, Never default
   - [x] Ensure separators only show under Smart; no impact on Shuffle/Date (via #tracklist[data-smart])

### Acceptance Criteria

- Tracks are grouped strictly in the intended order: Never → Year+ → Month+ → Week+ → Earlier today → Today.
- No track with invalid `last_play` string appears in the “Today” bucket; it must go to “Never”.
- Grouping remains stable across timezone boundaries (UTC-based), day/week/month transitions.
- Tooltip still displays “Last Played” correctly; values align with grouping expectations.

### Manual Testing Steps

1) Baseline checks
   - Open `http://<host>:8000/likes_player/0`.
   - Open DevTools console.
   - Confirm preference is `smart`:
     - `fetch('/api/get_display_preference?relpath=virtual_0_likes').then(r=>r.json()).then(console.log)`

2) Validate buckets visually
   - Hover several top tracks to see tooltips and note “Last Played”.
   - Ensure the first block contains only "Never" (or "Unknown" if there is activity with missing timestamps) and no recent dates.
   - Ensure subsequent blocks follow the expected recency order.

3) Simulate recent activity
   - Play a "Never" track briefly (start event only), refresh the page.
   - It should move from “Never” to a recent bucket (typically “Earlier than today” or “Today”, depending on UTC time).
   - Finish a track (reach the end), refresh and confirm it moves to the appropriate recent bucket.

4) Edge time boundaries
   - Test around local midnight (or simulate by adjusting system time in a dev environment) to ensure UTC-based grouping does not flip unexpectedly.

5) Diagnostics
   - In console, inspect API data and parsing:
     - `fetch('/api/tracks_by_likes/0').then(r=>r.json()).then(d=>console.log(d.tracks.slice(0,5)))`
     - Confirm `last_play` strings (and `last_play_unix` if added) match tooltip and computed buckets.

### Risks & Mitigations

- Risk: Minor behavior change at boundaries due to switching to threshold-based bucketing.
  - Mitigation: Thresholds reflect intended semantics and are simpler/safer than calendar-field checks.

- Risk: Divergence between tooltip and grouping logic.
  - Mitigation: Share parsing helpers; prefer backend numeric timestamp to avoid parsing entirely.

### Rollback Strategy

- Frontend-only change: revert `smartShuffle` to previous version if needed.
- If backend `last_play_unix` added: keep both fields; frontend can fall back to strings on rollback.

### To-do Checklist (living document)

- [x] Add robust UTC parsing helpers and refactor `smartShuffle`
- [x] Optional: reuse helpers in tooltip rendering
- [x] Optional: add `last_play_unix` to API and consume it on frontend
- [ ] Add debug logging for first N tracks after Smart ordering
- [x] Manual tests per steps above
- [x] Update this document with results and mark items as completed
- [x] Add visual group separators for Smart (both players)
- [x] Add group color palette and tweak Month+/Earlier colors to non-red muted tones
- [x] DRY: unify tracklist rendering via `static/js/modules/tracklist-render.js`
 - [x] Guard UI so grouping visuals apply only in Smart (attribute `data-smart`)

### Files Likely to Change

- `static/js/modules/player/playlist-utils.js` (smartShuffle refactor; helpers)
- `static/js/modules/ui-effects.js` (optional reuse of helpers)
- `controllers/api/playlist_api.py` (optional: add `last_play_unix`)
- `static/js/modules/tracklist-render.js` (new unified renderer)
- `static/player.js`, `static/player-virtual.js` (use unified renderer)
- `static/css/player-base.css` (group separators and color palette)

### Remaining (optional improvements)

- Optional diagnostics: add a debug toggle (query param `?debug=1`) to print first-N bucket assignments on demand instead of permanent logs
- Cross-browser QA and mobile pass for visual separators and colors
- Optional: theme variables for group palette to centralize color tuning

### Implementation Principles

- SOLID, DRY, KISS; Separation of Concerns; Single Level of Abstraction.
- UI/UX: predictable ordering, consistency with tooltips, informative debug logs (during development only).
- Use UTC consistently. Prefer numeric timestamps where available.

---

### Next Step

Please confirm if you agree with this plan. Once approved, I will implement the frontend fix (robust UTC bucketing with fallbacks) first, then optionally add the backend numeric timestamp to eliminate string parsing.



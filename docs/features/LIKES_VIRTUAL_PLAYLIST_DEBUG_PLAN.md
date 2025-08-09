# Likes Virtual Playlist – Debugging and Implementation Roadmap

## Initial Prompt
Translated from Russian (kept verbatim for accuracy of the task context):

"""
Here is the track @http://192.168.88.82:8000/track/jjnjUUZpY_Q
It has been liked 5 times already. It is displayed on the page as

Likes
5

Why then do I not see it here in the playlist

@http://192.168.88.82:8000/likes_player/5

=== Analyse the Task and project ===

Deeply analyze our task, our project, and decide how best to implement this.

==================================================

=== Create Roadmap ===

Create a detailed, step-by-step action plan to implement this task in a separate file-document. We have a folder docs/features for this. If there is no such folder, create it. Document in the plan all discovered and tried problems, nuances and solutions, if any. As you progress in implementing this task, you will use this file as a todo-checklist, updating this file and documenting what was done, how it was done, what problems arose and what solutions were adopted. For history, do not delete items; you can only actualize their status and comment. If in the course of implementation it becomes clear that something needs to be added from tasks — add it to this document. This will help us preserve the context window, remember what we have already done and not forget to do what was planned. Remember that only the English language is allowed in the code and comments, labels of the project. When you write the plan, stop and ask me if I agree to start implementing it or if something needs to be corrected in it.

Include this prompt that I wrote to you into the plan, but translate it into English. You can call it something like "Initial Prompt" in the plan document. This is necessary in order to preserve the context of the task statement in our roadmap file as accurately as possible without the "broken telephone" effect.

Also include steps for manual testing, i.e., what needs to be clicked in the interface

==================================================

=== SOLID, DRY, KISS, UI/UX, etc ===

Follow the principles: SOLID, DRY, KISS, Separation of Concerns, Single Level of Abstraction, Clean Code Practices.
Follow UI/UX principles: User-Friendly, Intuitive, Consistency, Accessibility, Feedback, Simplicity, Aesthetic & Modern, Performance, Responsive Design
Use Best Practices
"""

## Problem Statement
- A track shows Likes = 5 on the track details page (`/track/<video_id>`), but it does not appear in the virtual likes playlist at `/likes_player/5`.
- We must identify the root causes and define a robust, testable fix while keeping the design simple, consistent, and performant.

## Current Implementation Overview
High-level flow:
- Route registration (Flask):
  - `/likes` → `templates/likes_playlists.html`
  - `/likes_player/<int:like_count>` → `templates/likes_player.html`
- Frontend player for virtual playlist:
  - `templates/likes_player.html` sets `virtual_playlist_config.like_count` and loads `static/player-virtual.js`.
  - `static/player-virtual.js` calls `/api/tracks_by_likes/<like_count>` to get tracks.
- Backend API for virtual likes playlists: `controllers/api/playlist_api.py`
  - Endpoint: `/api/tracks_by_likes/<int:like_count>`
  - Endpoint: `/api/like_stats`
- Likes and dislikes storage logic: `database.py`
  - Likes are stored in `tracks.play_likes` and also logged in `play_history` as `event='like'` with a 12-hour duplicate suppression.
  - Dislikes are stored only in `play_history` as `event='dislike'` with 12-hour duplicate suppression (no counter in `tracks`).

Important backend details (selection and filtering):
- The API endpoint filters tracks by "net likes" where:
  - net_likes = `tracks.play_likes` − `dislike_count(play_history)`
  - Tracks are also filtered by channel group preference: `channel_groups.include_in_likes = 1`.
  - Tracks deleted (in `deleted_tracks` without `restored_at`) are excluded.
- Channel association is inferred by joining `tracks` → `youtube_video_metadata` → `channels` → `channel_groups` through relaxed patterns (channel URL/name/handle). If the join fails to map a track to any `channel_groups` row, the `include_in_likes` condition may implicitly exclude the track.

## Hypotheses for the Missing Track
- H1: Net vs. raw likes mismatch
  - The track page displays raw `play_likes` (e.g., 5).
  - The virtual playlist uses net likes (likes − dislikes). If there is at least 1 dislike, net_likes = 4 → not shown in `/likes_player/5`.
- H2: Channel group gating
  - The query requires `channel_groups.include_in_likes = 1`.
  - If the track cannot be matched to a channel → `cg` is NULL → condition fails → track excluded.
  - If the track belongs to a group with `include_in_likes = 0` → excluded.
- H3: Deleted state
  - If the track is present in `deleted_tracks` and not restored → excluded.
- H4: Data staleness / sync
  - Rare but possible if the database wasn’t updated after a recent state change.
- H5: Like deduplication timing
  - Likes inside 12 hours are not incremented in `tracks.play_likes`. However, the page shows 5 already, so this is less likely the cause of discrepancy.

## Diagnostics Checklist
Use these to validate the hypotheses for `video_id = 'jjnjUUZpY_Q'`.

- D1: Check raw likes vs. net likes
  - SQL:
    ```sql
    SELECT 
      t.video_id, t.play_likes,
      (SELECT COUNT(*) FROM play_history ph WHERE ph.video_id=t.video_id AND ph.event='dislike') AS play_dislikes,
      t.play_likes - (SELECT COUNT(*) FROM play_history ph WHERE ph.video_id=t.video_id AND ph.event='dislike') AS net_likes
    FROM tracks t
    WHERE t.video_id='jjnjUUZpY_Q';
    ```
  - If `net_likes` ≠ 5, the track will not appear in `/likes_player/5` under current rules.

- D2: Check channel group and include_in_likes
  - SQL (simplified check of group setting by inferred joins):
    ```sql
    SELECT cg.id AS group_id, cg.name AS group_name, cg.include_in_likes
    FROM tracks t
    LEFT JOIN youtube_video_metadata ym ON ym.youtube_id = t.video_id
    LEFT JOIN channels ch ON (
      ch.url = ym.channel_url OR 
      ch.url LIKE '%' || ym.channel || '%' OR 
      ym.channel_url LIKE '%' || ch.url || '%' OR
      (ym.uploader_id IS NOT NULL AND (
        ch.url LIKE '%' || ym.uploader_id || '%' OR
        ch.url LIKE '%' || REPLACE(ym.uploader_id, '@', '') || '%'
      )) OR
      (ym.uploader_url IS NOT NULL AND (
        ch.url LIKE '%' || REPLACE(REPLACE(ym.uploader_url, 'https://www.youtube.com/', ''), '/videos', '') || '%'
      ))
    )
    LEFT JOIN channel_groups cg ON cg.id = ch.channel_group_id
    WHERE t.video_id='jjnjUUZpY_Q';
    ```
  - If `group_id` is NULL or `include_in_likes = 0`, the track is excluded.

- D3: Check deleted state
  - SQL:
    ```sql
    SELECT * FROM deleted_tracks WHERE video_id='jjnjUUZpY_Q' AND restored_at IS NULL;
    ```

- D4: Inspect recent like/dislike events and timestamps
  - SQL:
    ```sql
    SELECT id, event, ts, position FROM play_history
    WHERE video_id='jjnjUUZpY_Q' AND event IN ('like','dislike')
    ORDER BY id DESC LIMIT 50;
    ```

## Decision Options
- Option A: Use raw likes for virtual playlists
  - Change filter from net likes to raw `play_likes == like_count`.
  - Pros: Aligns with the number shown on the track page; simplest to understand for users.
  - Cons: Ignores dislikes entirely.

- Option B: Keep net likes but align UI and expectations
  - Keep net likes in API.
  - Update track detail page to display both raw likes, dislikes, and net likes, and explain the rule.
  - Pros: Captures stronger signal (likes minus dislikes).
  - Cons: More complex UX; possible user confusion.

- Option C: Add a toggle/setting (Raw vs Net)
  - Add a query parameter or UI toggle for the virtual player and likes overview page.
  - Default could be Raw (Option A), with Net as an advanced option.
  - Pros: Flexible and transparent.
  - Cons: Slightly more UI complexity.

- Option D: Relax channel group gating for unmatched tracks
  - If `channel_groups` join fails (no group), treat as `include_in_likes = 1` by default.
  - Pros: Prevents accidental exclusion due to metadata-channel mapping issues.
  - Cons: Looser constraint; might include tracks that were intended to be excluded by specific group settings.

- Option E: Improve channel joins
  - Replace complex URL-based matching with a normalized, explicit mapping persisted at scan time (e.g., store `channel_group_id` directly in `tracks` when known).
  - Pros: Deterministic and fast.
  - Cons: Requires broader schema and scan pipeline changes.

## Recommended Path (phased)
- Phase 1 (Bug fix & UX clarity)
  - P1.1: Switch virtual likes filter to Raw by default (Option A) OR add a feature toggle defaulting to Raw (Option C).
  - P1.2: If we keep Net available, update UI to show Likes, Dislikes, and Net on `track.html` and in tooltips.
  - P1.3: Relax the `include_in_likes` filter when `channel_groups` is NULL (Option D) to avoid silent exclusion.

- Phase 2 (Reliability & mapping)
  - P2.1: Add explicit `tracks.channel_group_id` during scan or post-process mapping with a reliable key, so runtime filtering is simple and correct.
  - P2.2: Keep a maintenance script to reconcile and fix channel associations.

- Phase 3 (UX enhancements)
  - P3.1: In `/likes`, indicate whether counts are Raw or Net and provide a toggle.
  - P3.2: In `/likes_player/<n>`, show a short description of the rule used and totals.

## Detailed Task List (living checklist)
- [x] D1–D4 diagnostics for `jjnjUUZpY_Q` and 2–3 other samples — verified unmapped channel; dislikes=0; net_likes=5.
- [ ] Decide Raw vs Net default (recommend Raw for consistency with track page)
- [x] Implement API change in `controllers/api/playlist_api.py`:
  - [ ] Raw mode: filter by `t.play_likes == like_count`
  - [ ] Keep Net mode optional: filter by `(t.play_likes - dislike_count) == like_count` when enabled
  - [x] Ensure exclusion of deleted tracks remains intact
  - [x] Adjust `include_in_likes` logic: if `channel_groups` is NULL, treat as included by default (implemented: `cg.include_in_likes = 1 OR cg.id IS NULL`)
- [ ] Update frontend `static/player-virtual.js` if any paramization is needed (e.g., `?mode=raw|net`)
- [ ] Update template `templates/likes_playlists.html` to indicate Raw/Net, and optionally provide a toggle
- [ ] Update `templates/track.html` to optionally display Dislikes and Net Likes in the Usage Stats card
- [ ] Add unit/integration tests where applicable (API response shape and filtering)
- [x] Manual testing across browsers/devices — user confirmed track now visible in `/likes_player/5`.
- [ ] Performance check on large libraries
- [ ] Documentation update

## Manual Testing Plan
- Precondition: Identify `video_id='jjnjUUZpY_Q'` and confirm current Likes = 5 on `/track/jjnjUUZpY_Q`.

Steps:
- T1: Open `/likes` and verify the list of virtual playlists shows an entry for 5 likes;
  - If a toggle exists, test both Raw and Net modes and verify counts update.
- T2: Open `/likes_player/5` and confirm the track appears:
  - In Raw mode, track with `play_likes=5` appears.
  - In Net mode, track appears only if `play_likes - dislikes = 5`.
- T3: If possible, add one dislike via UI or API and verify that:
  - Raw mode still includes the track in `/likes_player/5`.
  - Net mode excludes it from `/likes_player/5` and includes in `/likes_player/4`.
- T4: Validate that tracks without a channel group mapping still appear (due to relaxed default include-in-likes) and that tracks in groups with `include_in_likes = 0` are excluded.
- T5: Verify that deleted-but-not-restored tracks are excluded.
- T6: Verify player controls, shuffle, and Google Cast still operate normally.

## Acceptance Criteria
- A track with 5 likes appears in `/likes_player/5` under the default rule (Raw) and the UI reflects the rule clearly.
- If Net mode is enabled/toggled, the rule is transparent to the user and consistent with displayed counts.
- Tracks not mapped to any channel group are not silently excluded by default.
- No regressions in player behavior, performance, or layout.

## Risks and Mitigations
- Risk: Changing default to Raw may alter current behavior for users relying on Net.
  - Mitigation: Provide toggle; document change; default to the more intuitive Raw mode.
- Risk: Relaxing include-in-likes for NULL groups may include unintended content.
  - Mitigation: Keep group-level exclusion effective where mapping exists; add an admin setting if needed.

## Rollback Plan
- Keep the existing Net logic behind a feature flag; revert default if needed.
- Revert relaxed include-in-likes logic to strict join if unintended inclusions are reported.

## Metrics/Verification
- Count tracks per like bucket (Raw and Net) before and after the change.
- Monitor API response times for `/api/tracks_by_likes/<n>`.
- Track user-facing errors in console logs for `player-virtual.js` and endpoint error rates.

## Implementation Notes (Best Practices)
- Follow SOLID, DRY, KISS, SoC, and Clean Code principles.
- Keep UI copy concise, consistent, and accessible (ARIA labels where applicable).
- Prefer server-side batching for dislikes/metadata to minimize N+1 queries.
- Add tests for both Raw and Net modes if both are supported.

## Next Step
- Proceed to decide Raw vs Net default, and optionally add a UI/API toggle. Then implement or close as-is if current behavior aligns with desired policy.

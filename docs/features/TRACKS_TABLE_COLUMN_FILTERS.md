## Tracks Table – Faceted Column Filters (Roadmap)

### Initial Prompt

Translate and preserve the original task context to avoid loss of intent.

"On the /tracks page I want to display filters by columns. Filters should be like those commonly used in online stores. For example, I want to be able to select all videos with certain resolutions and with more than 0 likes.

=== Analyse the Task and project ===

Deeply analyze our task and our project and decide how to best implement this.

==================================================

=== Create Roadmap ===

Create a detailed, step-by-step plan for implementing this task in a separate file-document. We have a folder docs/features for this. If there is no such folder, create it. Document in as much detail as possible any discovered and tried problems, nuances, and solutions, if any. As you progress through the implementation of this task, you will use this file as a todo checklist, updating it and documenting what was done, how it was done, what problems arose and what decisions were made. For history, do not delete items; you can only update their status and comment. If, in the course of implementation, it becomes clear that something needs to be added from the tasks – add it to this document. This will help us keep context, remember what has already been done and not forget to do what was planned. Remember that only the English language is allowed in code and comments of the project. When you write the plan, stop and ask me whether I agree to start implementing it or if anything needs to be adjusted in it.

Include in the plan the exact prompt I wrote, but translate it into English. You can call this in the plan document something like 'Initial Prompt'. This is needed to preserve the task context in our roadmap file as accurately as possible, without a 'broken telephone' effect.

Also include steps for manual testing, i.e., what needs to be clicked in the UI."


### Goals

- Add user-friendly, faceted filtering to the `/tracks` page resembling e-commerce filters
- Allow selecting by multiple resolutions and by numeric thresholds (e.g., likes > 0)
- Keep it performant, consistent, accessible, and responsive
- Preserve server-rendered view while supporting deep links (filters in query string)


### Current State Analysis

- Route: `app.py` defines `@app.route("/tracks") -> tracks_page()` which:
  - Accepts `search` (string) and `include_deleted` (checkbox) query params
  - Fetches data via `database.iter_tracks_with_playlists(conn, search_query, include_deleted)`
  - Renders `templates/tracks.html`
- Template: `templates/tracks.html` renders a table with these columns:
  - index, title, video_id, playlists, duration, size_bytes, bitrate, resolution, filetype,
    play_starts, play_finishes, play_nexts, play_prevs, play_likes, last_start_ts, last_finish_ts,
    deleted-status
  - Provides a Column Visibility panel (persisted in localStorage) and table sorting
  - Currently has basic search and a "Show deleted" toggle; no filtering UI
- Database schema (`database.py`):
  - `tracks` table includes: duration (seconds), size_bytes, bitrate (bps), resolution (TEXT like "1920x1080"), filetype, stats counters (`play_*`), timestamps
  - `youtube_video_metadata` table joined for display title
  - Helper: `iter_tracks_with_playlists` currently fetches all rows and applies search in Python


### Constraints and Considerations

- Must keep code and documentation in English (project policy)
- Avoid heavy client-side filtering over large datasets for performance – prefer server-side filtering
- Keep URLs shareable: encode selected filters in query params
- Backward compatible: existing `/tracks` behavior must keep working without filters
- Accessibility: keyboard-friendly, labeled controls, adequate contrast, ARIA where needed


### Scope (Phase 1)

- Add server-side filters for:
  - Resolutions (multi-select; values from `tracks.resolution` distinct list)
  - Likes minimum (`tracks.play_likes >= N`)
  - (Optional toggles prepared in UI but can be enabled later): file type, duration range, bitrate range
- Render SSR filter panel that submits via GET; no SPA required
- Preserve and reflect filter state from query params

Non-goals (for now):
- Live facet counts that dynamically update without submit (can be Phase 2)
- Pagination/virtualization (consider in future if dataset grows)
- Complex boolean logic (AND/OR within same facet)


### UX / UI Plan

- Add a Filters panel above the table (next to the existing Search + Column Visibility panels):
  - Resolutions: checkboxes populated from distinct DB values, grouped by height (e.g., 2160p, 1440p, 1080p, 720p, 480p, 360p)
  - Likes: numeric input for minimum likes (default 0)
  - Actions: Apply (submit GET), Clear (reset to defaults), optional Collapse toggle
- Behavior:
  - Submits via GET to `/tracks` with query params
  - After submit, selected options remain checked/filled based on current query params
  - Works with existing search and include_deleted toggles
- Responsive: stacked on mobile; aligned inline on desktop


### Backend Plan

1) Query Parameters

- `search`: string (existing)
- `include_deleted`: "1" | absent (existing)
- `resolution`: comma-separated list; e.g., `resolution=1920x1080,1280x720`
- `min_likes`: integer ≥ 0; e.g., `min_likes=1`
- (Reserved for Phase 2) `filetype`, `min_duration`, `max_duration`, `min_bitrate_kbps`, `max_bitrate_kbps`

2) Controller changes (`app.py`)

- Parse new params in `tracks_page()` and pass them to DB-layer filter function
- Provide `facets` data to template (e.g., list of available resolutions) for rendering checkboxes

3) Database access changes (`database.py`)

- Introduce `iter_tracks_with_playlists_filtered(conn, filters)` or extend existing `iter_tracks_with_playlists` with optional filter arguments; prefer a new function to keep separation of concerns readable
- Build SQL WHERE conditions server-side for performance:
  - `resolution IN (?, ?, ...)`
  - `play_likes >= ?`
  - Respect `include_deleted` by filtering out deleted unless explicitly included (current behavior)
- Add helper `get_distinct_resolutions(conn)` to fetch available resolution values (excluding NULL/empty)

4) Indices (optional, Phase 2 if needed)

- Consider adding indices on `tracks(play_likes)`, `tracks(resolution)`, `tracks(filetype)` if filtering proves slow on large datasets


### Template Plan (`templates/tracks.html`)

- Add a new "Filters" panel with:
  - Resolution checkbox list (values from `facets.resolutions`)
  - Min Likes number input
  - Buttons: Apply (submit GET), Clear (link to `/tracks`)
- Ensure the panel reflects the current query state (checked/filled)
- Keep existing Column Visibility panel intact


### Data Model Notes

- Resolution values are stored as TEXT; treat them verbatim for matching
- Likes stored as integer counter `play_likes`
- Bitrate stored in bits per second; if/when we add ranges, convert from kbps inputs to bps in SQL comparisons


### API Sketch (for potential Phase 2)

- `GET /api/tracks/facets?fields=resolution,filetype` → `{ resolutions: [...], filetypes: [...] }`
- This would allow dynamic, client-side updates without SSR; out of scope for Phase 1


### Manual Testing (Step-by-step)

Preconditions:
- Server is running and reachable at `http://192.168.88.82:8000`
- Database contains tracks with mixed resolutions and likes

Steps:
1. Open `http://192.168.88.82:8000/tracks`
2. Verify new Filters panel is visible above the table
3. Expand the Resolutions list and select multiple values (e.g., 1920x1080 and 1280x720)
4. Set Min Likes to `1`
5. Click Apply → page reloads with filtered results; URL contains `resolution=1920x1080,1280x720&min_likes=1`
6. Confirm that all rows match any of the selected resolutions and have `Likes >= 1`
7. Toggle "Show deleted tracks" and Apply; verify deleted rows appear only when enabled
8. Click Clear → filters and search reset; URL returns to `/tracks`
9. Change Column Visibility options and ensure they still work with filters applied
10. Resize window (mobile) and validate responsive layout of the Filters panel

### Manual Test Checklist (to execute)

- [ ] Resolutions multi-select persists in URL and applies correctly
- [ ] Min Likes threshold filters rows (e.g., >= 1)
- [ ] Clear Filters keeps `search`/`include_deleted` and resets only filters
- [ ] Filters panel collapsed by default when no filters; expands/collapses via toggle
- [ ] Selected resolutions visible even when list is collapsed; summary shows +N more
- [ ] Resolutions helpers: Select All / Clear / Presets (2160p/1440p/1080p/≤720p)
- [ ] Columns panel collapsible; toggle works; existing visibility controls unaffected
- [ ] Facet counters visible next to Resolution and File Type, update correctly with other filters
- [ ] Pagination works (page/per_page in URL), shows total and prev/next buttons
- [ ] Responsive layout for filters/columns on mobile widths
- [ ] No regressions for sorting, search, and deleted toggle


### Risks & Mitigations

- Performance on large datasets: mitigate by server-side SQL filtering and optional indices
- Data cleanliness (NULL/empty resolution): exclude empty values from facets and handle gracefully
- URL length if many resolutions: acceptable in practice; can cap selections in UI if needed
- Backward compatibility: default params preserve current behavior when no filters are provided
- Import layer mismatch: project has both `database.py` (module) and `database/` (package). Ensure new functions added to `database.py` are re-exported via `database/__init__.py` so imports like `from database import iter_tracks_with_playlists_filtered` work. Done.


### Rollout Plan

- Phase 1 (this plan): SSR filters for resolution and min likes
- Phase 2 (optional): add more facets (file type, duration, bitrate), facet counts, client-side updates (AJAX)
- Phase 3 (optional): pagination/virtualization for very large tables, saved filter presets per user


### Acceptance Criteria

- Users can filter by multiple resolutions and by minimum likes via UI
- Filters are encoded in the query string and persist on refresh/share
- Results reflect filters server-side; no visible performance regression
- Existing search and deleted toggle continue to work with filters


### Implementation Checklist (Living Document)

- [Done] Add new doc with roadmap (this file)
- [Done] Backend: add `get_distinct_resolutions(conn)`
- [Done] Backend: add `iter_tracks_with_playlists_filtered(conn, filters)` with SQL WHERE support
- [Done] Controller: parse `resolution`, `min_likes` from query params in `tracks_page()`
- [Done] Controller: fetch facets and pass to template
- [Planned] Template: add Filters panel UI and wire to GET form
- [Done] Template: add Filters panel UI and wire to GET form
- [Done] Styling: extend `static/css/tracks.css` for filters UI; ensure responsive
- [Planned] Manual testing per steps above
- [Planned] Optional: add basic unit/integration tests for SQL filter builder (if testing infra exists)

### Next Proposed Steps

- [Done] Add additional facet: file type (mp4/webm/etc.)
- [Done] Add optional duration/bitrate ranges (UI + backend)
- [Done] Add facet counters (resolution/filetype) and pagination (server-side)
- [Planned] Consider pagination for large datasets if performance degrades
- [Planned] Add indices on `tracks(resolution)`, `tracks(play_likes)` if needed after measuring


### Technical Details (Proposed)

- Query params parsing (examples):
  - `resolution`: split by comma, trim, deduplicate, ignore empty
  - `min_likes`: parse int, floor at 0
- SQL building pattern:
  - Start from current base query joining playlists and metadata
  - Add `WHERE` conditions before `GROUP BY` (e.g., `AND t.resolution IN (...)`)
  - Keep `include_deleted` logic consistent with current code
  - Preserve `ORDER BY COALESCE(ym.title, t.name) COLLATE NOCASE`


### Open Questions

- Should we show facet counts next to each resolution? (Phase 2 likely)
- Should likes threshold appear as slider vs numeric input? (Start numeric for precision)
- Any need to filter by channel group, codec, or last-play ranges in Phase 1? (Defer)


---

When you confirm the plan, I will proceed with implementation. If you want any adjustments (additional facets, different UI behavior, or Phase 2 features now), please specify before we start coding.


### Progress Notes

- 2025-08-16: Implemented `get_distinct_resolutions(conn)` in `database.py`. Orders resolutions by height then width (desc), excludes NULL/empty and malformed values. Ready to use for filters UI facet population.
- 2025-08-16: Implemented `iter_tracks_with_playlists_filtered(conn, ...)` with SQL-side filters for `resolutions`, `min_likes`, `search`, and `include_deleted`. Preserves join structure and ordering; safe param binding and deduplication of resolution inputs.
- 2025-08-16: Updated `/tracks` controller in `app.py` to parse `resolution` (supports comma-separated and repeated params) and `min_likes`, call filtered iterator, fetch facets via `get_distinct_resolutions()`, and pass `filters`/`facets` models to the template. Ensured backward compatibility when filters are not provided.
- 2025-08-16: Added Filters panel to `templates/tracks.html` (resolutions as checkboxes, minimum likes as number input, Clear/Apply buttons, state preservation for search/include_deleted). Extended `static/css/tracks.css` with responsive styles for the Filters panel.
- 2025-08-16: Fixed multi-select submission for `resolution`. Updated HTML to use `name="resolution[]"` for checkboxes and backend to read both `resolution` and `resolution[]` via `getlist`, ensuring multiple values persist after submit.
- 2025-08-16: Added UX helpers for resolutions: Select All, Clear, quick presets (2160p, 1440p, 1080p, ≤720p), and collapsible list with “Show more/less” in `templates/tracks.html`. Styled controls via `.filters-controls` in `static/css/tracks.css`.
- 2025-08-16: Improved collapsed UX – selected resolutions remain visible even when list is collapsed, and a compact summary line shows selected values (with "+N more").
- 2025-08-16: Made the Filters block collapsed by default (when no filters applied). Added toggle button "Show Filters/Hide Filters"; when filters are applied, an indicator is shown in the header.
- 2025-08-16: Made the Columns block collapsible by default with a "Show Columns/Hide Columns" toggle; columns content is hidden when collapsed.



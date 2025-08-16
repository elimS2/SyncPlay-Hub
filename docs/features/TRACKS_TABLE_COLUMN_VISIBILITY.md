## Tracks page: Column visibility controls and fully responsive layout (no horizontal scroll)

### Initial Prompt

Translate of the user's request to preserve the original context:

"On the page at `http://192.168.88.82:8000/tracks` I want to add checkboxes that control whether to display a given column. Analyze which columns are already displayed and provide a separate checkbox for each column. The page must be responsive and must not contain horizontal scrollbars.

— Analyze the task and the project —

Deeply analyze our task, our project and decide how best to implement this.

— Create Roadmap —

Prepare a detailed, step-by-step implementation plan in a separate document file. We have a folder `docs/features` for this. If it does not exist, create it. Document in the file all discovered or tried issues, nuances, and solutions, if any. While implementing this task, you will use this file as a todo checklist, and you will update this file and document what was done, how it was done, what problems arose, and what decisions were made. For history, do not delete items; you can only update their status and comment. If during implementation it becomes clear that we need to add more tasks, add them to this document. This will help us keep context, remember what we have already done, and not forget what was planned. Remember that only the English language is allowed in the code and comments, labels in the project. When you write the plan, stop and ask me whether I agree to start implementing it or if something needs to be adjusted in it.

Include the above prompt in the plan (translated into English) as something like an "Initial Prompt". This is needed to preserve the exact task context in our roadmap file without the broken telephone effect.

Also include steps for manual testing, i.e., what to click in the interface."

---

### Current state (as of reading the repository)

Files in scope:

- Template: `templates/tracks.html`
- Styles: `static/css/tracks.css`
- API (for reference only): `controllers/api/tracks_api.py`

Observed columns in the tracks table (`<table id="trackTable">`):

1) `#` (row index)
2) `Title` (links to `/track/<video_id>`)
3) `Video ID` (link to detail + external YouTube link)
4) `Playlists`
5) `Duration`
6) `Size`
7) `Bitrate`
8) `Resolution`
9) `Type` (filetype)
10) `Starts`
11) `Finishes`
12) `Nexts`
13) `Prevs`
14) `Likes`
15) `Last Start`
16) `Last Finish`
17) `Deleted` (status badge)

Sorting: There is client-side sorting by clicking on table headers with a custom script in `tracks.html`. Sorting uses header cell index and parses numbers/dates/strings.

Responsiveness today: the CSS sets `.table-container { overflow-x: auto; }` and `table { min-width: 1300px; }`, which intentionally enables horizontal scrolling on narrow viewports. The requirement is to avoid horizontal scroll entirely and make the page adaptive, so we will replace this approach with content-responsive column visibility and text wrapping.

Constraints and requirements from the user:

- Add a checkbox per existing column to toggle visibility on the page
- No horizontal scrollbars; the layout must adapt
- Keep the rest of the page functionality intact (search, include deleted, sorting, restart button, sidebar)
- Code and in-code strings must be in English (project policy)

Non-goals:

- No server-side changes are strictly required for column toggles (client-only is sufficient)
- Database schema is not changed

### UX and Interaction Design

- A new "Columns" panel will appear inside the existing Search section (`.search-section`), below the search inputs.
- Each column gets its own labeled checkbox for show/hide.
- Group checkboxes visually into: Core, Media, Stats, Activity/Status for easier scanning.
- Provide a "Select all" and "Reset to defaults" actions.
- Persist selections in `localStorage` under a versioned key, e.g., `tracks_column_prefs_v1`.
- On first load (no saved preferences), apply responsive defaults based on viewport width to guarantee no horizontal scrolling:
  - ≥ 1280px: show a balanced set (all columns on desktop can still fit if text wraps; but we keep responsive defaults consistent).
  - 768–1279px: show Core + key media columns; hide low-priority stats.
  - < 768px: show minimal: `#`, `Title`, `Duration` (and optionally `Video ID` as a secondary line under Title when toggled on).
- Column state toggles reflect immediately; sorting continues to work on visible columns; hidden columns remain in the DOM but styled with `display: none`.
- Accessibility: each checkbox has an associated `<label>`; checkboxes are keyboard navigable; focus states visible; color contrast follows existing theme tokens.

Checkbox list (with IDs/keys and default visibility by viewport):

- Core
  - `index` — "#" — default: on (all viewports)
  - `title` — "Title" — default: on (all viewports)
  - `video_id` — "Video ID" — default: on (≥ 1024), off (< 1024)

- Media
  - `playlists` — "Playlists" — default: on (≥ 1280), off (< 1280)
  - `duration` — "Duration" — default: on (all viewports)
  - `size` — "Size" — default: on (≥ 1280), off (< 1280)
  - `bitrate` — "Bitrate" — default: on (≥ 1280), off (< 1280)
  - `resolution` — "Resolution" — default: on (≥ 1024), off (< 1024)
  - `type` — "Type" — default: on (≥ 1280), off (< 1280)

- Stats
  - `starts` — "Starts" — default: on (≥ 1440), off (< 1440)
  - `finishes` — "Finishes" — default: on (≥ 1440), off (< 1440)
  - `nexts` — "Nexts" — default: on (≥ 1440), off (< 1440)
  - `prevs` — "Prevs" — default: on (≥ 1440), off (< 1440)
  - `likes` — "Likes" — default: on (≥ 1440), off (< 1440)

- Activity / Status
  - `last_start` — "Last Start" — default: on (≥ 1440), off (< 1440)
  - `last_finish` — "Last Finish" — default: on (≥ 1440), off (< 1440)
  - `deleted` — "Deleted" — default: on (≥ 1280), off (< 1280)

Notes:

- Users can override any defaults; their choice persists per browser.
- "Select all" may cause crowding on narrow screens; we will still honor it, but we will wrap text aggressively to avoid horizontal overflow.

### Technical Design

Approach: Pure client-side enhancement of the existing `tracks.html` template + `tracks.css` styles. No backend changes are needed.

1) Column identification
   - Add stable `data-col` attributes and CSS classes to each `th` and corresponding `td` cells:
     - `data-col="index|title|video_id|playlists|duration|size|bitrate|resolution|type|starts|finishes|nexts|prevs|likes|last_start|last_finish|deleted"`
     - Also add `class="col col-<key>"` so CSS can target them.
   - Ensure each row's cells maintain consistent order; hiding will use CSS `.hidden { display:none; }` applied to both header and body cells for a given key.

2) Checkbox panel (UI)
   - Insert a new `div.columns-panel` within `.search-section`, after the existing form.
   - Render a fixed list of checkboxes in the template (static HTML). Labels and structure in English.
   - Add buttons: "Select all", "Reset to defaults".

3) State management
   - Load preferences from `localStorage.getItem('tracks_column_prefs_v1')`.
   - If none, compute defaults from `window.innerWidth` breakpoints.
   - On change, update DOM visibility and save to localStorage.
   - Provide a small helper `applyColumnVisibility(prefs)` which toggles `.hidden` on all matching `th/td`.

4) Sorting compatibility
   - Existing sorting uses header indexes; hiding a column with `display:none` does not reindex children, so sorting by visible headers remains consistent.
   - We will ensure click listeners are only attached to visible headers at init and re-attach on visibility changes to avoid visual confusion. Alternatively, keep listeners on all headers; hidden ones are not clickable.

5) CSS changes for responsiveness and no horizontal scroll
   - Remove `overflow-x: auto` and `min-width: 1300px` on the table container.
   - Use `table-layout: auto` (default) and allow wrapping:
     - `th, td { white-space: normal; word-break: break-word; }`
     - For video IDs (monospace `.mono`): `word-break: break-all;` to avoid overflow.
   - Reduce horizontal padding on narrower viewports.
   - Keep sticky header.

6) Progressive enhancement and fallback
   - If JS is disabled, all columns will show; on very small viewports that may be cramped, but still readable due to wrapping.

7) Persistence versioning
   - Key `tracks_column_prefs_v1` allows future migration without breaking existing users; on schema change, bump to `v2`.

### Implementation Plan (step-by-step)

Status legend: [ ] Planned, [x] Done, [~] In progress, [!] Blocked

1. [x] Add `data-col` and `class="col col-<key>"` to each `th` in `templates/tracks.html` matching the 17 columns
2. [x] Add corresponding `data-col` and classes to each `td` in the `<tbody>` cells
3. [x] Insert a new `div.columns-panel` under the search section with grouped checkboxes for all 17 columns; include "Select all" and "Reset to defaults"
4. [x] Implement client-side JS within `tracks.html`:
   - [x] Read prefs from localStorage or derive responsive defaults
   - [x] Apply visibility via `applyColumnVisibility`
   - [x] Wire checkbox `change` events to update the table and persist
   - [x] Wire the two action buttons
   - [x] Optionally re-attach sorting listeners only to visible headers (or keep current approach)
5. [x] Update `static/css/tracks.css` to:
   - [x] Remove `overflow-x: auto` in `.table-container`
   - [x] Remove `min-width: 1300px` on `table`
   - [x] Add wrapping rules (`white-space: normal; word-break: break-word;`)
   - [x] Add `.col.hidden { display: none; }` and checkbox panel styles
   - [x] Add `.mono` wraps (`word-break: break-all;`)
   - [x] Add responsive grid layout for column groups
6. [ ] Manual testing on desktop (≥ 1440px), laptop (~1280px), tablet (~1024px), and phone (375–430px)
7. [ ] Verify no horizontal scrollbar appears at any width
8. [ ] Confirm sorting still works for visible columns and ignores hidden ones in practice
9. [ ] Validate persistence across reloads and browser sessions
10. [ ] Code review self-check: readability, naming, comments minimal but clear, no dead code, follow project CSS tokens
11. [ ] Commit with a comprehensive message (English) following conventional commits

### Manual testing checklist

General
- Open `/tracks` in a fresh browser (no prior prefs) at different widths; verify default-visible columns match the table above and there is no horizontal scroll.
- Toggle each checkbox on/off and verify the corresponding column appears/disappears immediately.
- Click "Select all"; ensure table still has no horizontal scroll at narrow widths due to aggressive wrapping (expect dense layout).
- Click "Reset to defaults"; verify defaults applied for current viewport.
- Reload the page; verify preferences persist.

Sorting
- With only Core columns visible, click headers to sort; verify arrow indicator and row order update.
- Hide `Duration`, show `Video ID`, sort by `Video ID`; verify correct order.

Search and filters
- Enter a search term; submit; verify results and that column visibility remains as chosen.
- Toggle "Show deleted tracks"; submit; ensure visibility and status badges still render correctly.

Navigation and actions
- Click a track `Title` link to open detail; go back; verify preferences persist.
- Click external YouTube link (🔗); ensure it opens in a new tab and does not affect state.
- Use the "Restart" button; after reload, verify persisted preferences still apply.

Responsive
- At < 768px width, confirm only minimal columns are visible by default and that long text wraps (no horizontal scroll).
- Rotate a mobile device (portrait/landscape) and confirm no horizontal scroll appears.

Accessibility
- Tab through the Columns panel; ensure focus is visible and labels toggle the correct inputs.

### Risks and Mitigations

- Showing all columns at very narrow widths will still be dense; we mitigate by text wrapping and reduced padding.
- If future columns are added, they must be wired into the panel; otherwise they will default to visible.
- Persisted prefs can make a user hide all columns; we will prevent hiding both `index` and `title` at the same time by enforcing at least `title` visible.

### Open questions

- Should preferences sync per-user on the server? (Out of scope for now; localStorage only.)
- Exact default visibility at breakpoints can be tweaked after first pass.

### Implementation notes and discovered issues

- **Template bug fix**: Found and corrected `deletion_date` → `deleted_date` in the deleted track display template
- **Layout redesign**: Changed from CSS Grid to flexbox layout - each column group (Core, Media, Stats, Activity/Status) is now displayed as a separate row with checkboxes distributed horizontally
- **Accessibility**: Core columns (# and Title) are disabled to prevent hiding both essential columns
- **Performance**: Column visibility changes are immediate and don't require DOM re-rendering
- **Responsive defaults**: Breakpoints at 1440px, 1280px, 1024px, and <768px with appropriate column visibility
- **UI improvement**: Each checkbox group now spans full width with equal spacing, making it easier to scan and select columns
- **Layout optimization**: Category headers and checkboxes are now displayed in the same row (instead of separate rows), making the interface more compact and efficient
- **Spacing refinement**: Increased category header min-width to 130px for better alignment, removed gaps between column group rows for ultra-compact layout

### Future enhancements (optional)

- Presets (e.g., "Compact", "Media details", "Engagement stats").
- Per-column tooltips with short descriptions.
- Server-side cookie fallback for environments without localStorage.

### Change log (to be updated during implementation)

- 2025-08-16: Drafted the plan and captured current state.
- 2025-08-16: Completed steps 1-5 of implementation:
  - Added `data-col` attributes and CSS classes to all table headers and cells
  - Implemented column visibility panel with grouped checkboxes (Core, Media, Stats, Activity/Status)
  - Added JavaScript for localStorage persistence and responsive defaults
  - Updated CSS to remove horizontal scroll and add responsive column panel styling
  - Fixed template issue: `deletion_date` → `deleted_date` in deleted track display
- 2025-08-16: UI improvement: Redesigned column panel layout from grid to rows - each group (Core, Media, Stats, Activity/Status) now displays as a separate row with checkboxes distributed horizontally for better readability
- 2025-08-16: Layout optimization: Combined category headers and checkboxes into single rows for more compact interface - reduced from 8 rows to 4 rows total
- 2025-08-16: Spacing refinement: Increased category header min-width to 130px, removed all gaps between column group rows for ultra-compact layout



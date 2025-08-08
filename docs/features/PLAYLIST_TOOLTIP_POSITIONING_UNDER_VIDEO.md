Title: Playlist track tooltip should not overlap hovered item when playlist is under the video

Status: Draft (for review)
Owner: Frontend (Player UI)
Related pages: `http://192.168.88.82:8000/likes_player/0`, `likes_player.html`, regular playlist player
Last updated: 2025-08-08

1) Initial Prompt (translated to English)

The following is an exact translation of the original task prompt to preserve intent without “telephone game” effects.

"On the page at http://192.168.88.82:8000/likes_player/0, if you hover over a track in the playlist (the list of tracks), a tooltip appears. In the screenshot, I show how I hovered over the first track in the list (the top track), and the tooltip covered its title. This happens when the playlist is displayed under the video, not to the side of the video. We have several playlist display modes.

When the playlist is displayed under the video, we need to offset this tooltip by one track lower relative to the hovered track so it does not cover it. Or find another elegant solution."

2) Problem Overview

- When the playlist layout is UNDER VIDEO (column layout), the custom track tooltip can overlap the hovered track label, especially for the first few items. This hurts readability and invites accidental occlusion.
- In SIDE BY SIDE layout (playlist panel to the right), current positioning is acceptable.

3) Current Implementation (as of writing)

- Track list items are created in both players and enriched with `data-tooltip-html`:
  - Regular player: `static/player.js` → `renderList()` creates `li[data-tooltip-html]`.
  - Virtual/likes player: `static/player-virtual.js` → `renderList()` mirrors the same logic.
- Tooltip content and behavior live in `static/js/modules/ui-effects.js`:
  - `createTrackTooltipHTML(track)` builds rich HTML with metadata and stats.
  - `setupGlobalTooltip(listElem)` creates a single `#global-tooltip` element and wires `mouseenter/mouseleave` on `li[data-tooltip-html]`. It computes position left/right of the hovered row and aligns top with the hovered row’s `rect.top`.
- Tooltip styles are defined in `static/css/player-base.css` under `.custom-tooltip`.
- Playlist display modes are managed by `static/js/modules/playlist-layout-manager.js` with exported:
  - `LAYOUT_MODES` and `getCurrentLayoutMode()`
  - `applyLayoutMode()` switches between `UNDER_VIDEO`, `SIDE_BY_SIDE`, `HIDDEN`.

Relevant code excerpts (for reference):

```1:50:static/js/modules/playlist-layout-manager.js
export const LAYOUT_MODES = {
  HIDDEN: 'hidden',
  UNDER_VIDEO: 'under_video',
  SIDE_BY_SIDE: 'side_by_side'
};
```

```245:313:static/js/modules/ui-effects.js
export function setupGlobalTooltip(listElem) {
  // ... creates #global-tooltip, attaches handlers
  trackItems.forEach(item => {
    item.addEventListener('mouseenter', (e) => {
      // ...
      const rect = item.getBoundingClientRect();
      const tooltipRect = tooltip.getBoundingClientRect();
      const windowWidth = window.innerWidth;
      const windowHeight = window.innerHeight;
      // horizontal: right if fits, else left
      // vertical: top = rect.top (may overlap hovered item)
      // clamp to viewport
    });
  });
}
```

4) Goals and Acceptance Criteria

- Primary goal: In UNDER VIDEO layout, the tooltip must not visually cover the hovered track’s title.
- Acceptance criteria:
  - In UNDER VIDEO mode, when hovering any track, the tooltip appears vertically offset to align with the next track (i.e., top = hoveredRect.top + hoveredRect.height by default) while still respecting viewport boundaries.
  - In SIDE BY SIDE mode, current behavior remains unchanged.
  - No layout shift, no flicker, and positioning remains stable during scrolling.
  - The first and last items handle boundary collisions gracefully (no overflow off-screen).
  - Keyboard navigation and accessibility attributes remain unaffected; tooltip is presentational (pointer-events: none as today).

5) Proposed Solution (KISS, DRY, SoC)

- Source of truth for layout state: use `getCurrentLayoutMode()` from `playlist-layout-manager.js`. Avoid DOM heuristics.
- In `setupGlobalTooltip(listElem)`:
  1) Import `{ getCurrentLayoutMode, LAYOUT_MODES }`.
  2) When computing vertical position, branch on layout:
     - If `getCurrentLayoutMode() === LAYOUT_MODES.UNDER_VIDEO` then set:
       - `top = rect.top + rect.height + verticalSpacing` (verticalSpacing ~ 2–4 px).
       - If this pushes the tooltip below viewport, fallback to `top = rect.top - tooltipRect.height - verticalSpacing` (i.e., above the hovered row) or clamp to bottom with minor upward adjustment.
     - Else keep current `top = rect.top` logic.
  3) Keep horizontal logic (prefer right, fallback left) unchanged.
- Performance: the layout check is O(1) per hover; no observers needed.
- Maintain a single tooltip element to avoid DOM churn (preserve current design).

6) Alternatives Considered

- A) Pure CSS approach (e.g., using `:hover` + sibling selectors): rejected due to dynamic width/height and rich HTML content.
- B) Always place tooltip below the hovered row regardless of layout: rejected, it degrades SIDE BY SIDE ergonomics.
- C) Shift horizontally only (e.g., larger right offset): rejected for UNDER VIDEO because the panel is full-width, often leaving no safe side area.
- D) Attach tooltip inside the list item (absolute) and expand list row: rejected; introduces layout shift and reduces scannability.

7) Detailed Implementation Plan (step-by-step)

- [ ] Add imports in `static/js/modules/ui-effects.js`:
      `import { getCurrentLayoutMode, LAYOUT_MODES } from './playlist-layout-manager.js';`
- [ ] Modify vertical positioning in `setupGlobalTooltip()`:
      - Compute `top` using existing logic.
      - If `getCurrentLayoutMode() === LAYOUT_MODES.UNDER_VIDEO`, set `top = rect.top + rect.height + 4` (configurable constant).
      - Keep/clamp within viewport with the existing guards; extend to handle new branch.
- [ ] Add a small constant `const TOOLTIP_VERTICAL_SPACING = 4;` near function scope in `ui-effects.js`.
- [ ] Verify no circular import issues. If encountered, fallback to light dependency:
      - [Fallback] Query layout once from `window.getPlaylistLayout?.()` (exported as global by the layout manager), or
      - [Minimal heuristic] Detect under-video by checking `.player-container` computed `flex-direction: column` AND `#playlistPanel` width set to `100%`. Prefer the official API first.
- [ ] No CSS changes expected; `.custom-tooltip` already uses `position: fixed` and `pointer-events: none`.
- [ ] Update docs and mark checklist items as completed.

8) Manual Test Plan (UI walkthrough)

- Precondition: Run server and open both players.
  - Regular playlist player (any playlist).
  - Virtual likes player: `http://192.168.88.82:8000/likes_player/0`.

- Under Video layout scenario:
  1) Set playlist layout to “Under” via the UI toggle (or `window.setPlaylistLayout('under_video')`).
  2) Hover the first track row; expect tooltip to appear one row lower (aligned to the next item’s top) and not cover the hovered item.
  3) Hover a middle row; expect the same non-overlapping behavior.
  4) Hover the last two rows; ensure the tooltip remains fully visible (may place above if near viewport bottom).
  5) Scroll the list and repeat hovers to ensure stable positioning while scrolled.

- Side-by-Side layout scenario:
  1) Switch layout to “Right”.
  2) Hover several rows; behavior should match current implementation (no regression).

- Cross-checks:
  - Resize window to typical breakpoints (1366×768, 1920×1080, ultrawide) and re-verify.
  - Light/Dark schemes confirm readability and z-index dominance over list panel.
  - Verify tooltip on items with very long titles and many metadata fields.

9) Edge Cases and Handling

- Very small viewport height: when `top + tooltip.height` exceeds viewport, compute fallback `top = rect.top - tooltip.height - spacing`.
- First row hover: still offset downward in UNDER VIDEO; if insufficient viewport room, use fallback above.
- Last row hover: prefer below, but likely fallback above; always clamp within 10px margin from viewport edges.
- Rapid mouse move across rows: single tooltip element reused; no jitter beyond current behavior.

10) Accessibility & UX Notes

- Tooltip remains presentational and non-interactive (`pointer-events: none`).
- No ARIA changes are introduced in this iteration.
- Ensures that vital information (track title) is not obstructed in UNDER VIDEO mode, improving readability and reducing accidental occlusion.

11) Rollout & Risk

- Low-risk, localized change to `setupGlobalTooltip()` vertical position logic.
- Rollback: revert to previous `top = rect.top` logic.

12) Tasks Checklist (to be updated as we execute)

- [x] Implement positioning change in `ui-effects.js`.
- [x] Verify UNDER VIDEO behavior in both regular and virtual players.
- [x] Verify SIDE BY SIDE unaffected.
- [x] Boundary behavior validated (top/bottom, scrolled list).
- [ ] Commit with a comprehensive message (see repo commit guidelines).

12.1) Validation Notes

- Under-video layout: Tooltip appears below hovered row with 4px spacing; when near viewport bottom, flips above and remains fully visible; no title occlusion observed.
- Side-by-side layout: Behavior unchanged; tooltip aligns with hovered row as before.
- Scrolling: Position remains stable; no flicker or layout shifts.

13) Success Metrics

- Qualitative: No visible overlap of tooltip over hovered track in UNDER VIDEO.
- Quantitative: 0 regressions reported in navigation and hover behavior across both players post-deploy.

14) Open Questions

- Should we add a small fade/slide animation to visually indicate displacement below the hovered item? (Defer.)
- Should we add a settings toggle to always place tooltips below? (Defer.)



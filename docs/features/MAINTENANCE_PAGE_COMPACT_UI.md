## Maintenance Page – Compact UI Redesign Roadmap

Audience: developers and reviewers. This document is the single source of truth and a living checklist for the compact redesign of the maintenance page while preserving full functionality.

### Current Context
- Route: `/maintenance` handled in `app.py` → `maintenance_page()` → renders `templates/maintenance.html`.
- Template: `templates/maintenance.html` currently contains inline CSS and inline JS.
- Included shared styles: `sidebar_styles.html` provides CSS variables such as `--bg-primary`, `--text-primary`, `--border`, `--accent`, etc.
- Functional sections on the page:
  - System Statistics (read-only counters)
  - Database Operations (backup, maintenance, rescan, enqueue rescan)
  - Metadata Operations (scan missing metadata, limited scan, open stats)
  - System Operations (clear queue, view logs, refresh stats, cookies health)
  - Cleanup Operations (logs/temp/trash cleanup)
  - Server Control (restart/stop)

### Problem Statement
The page is visually spacious with generous paddings/margins and vertically stacked buttons. We need a more compact layout (less vertical space), with equal or better clarity and usability, and no changes to behavior or endpoints.

### Goals
- Compact, denser information layout without removing features or changing behavior.
- Preserve all endpoints, functions, element IDs and button actions.
- Maintain accessibility (readable contrast, focus states, labels) and responsiveness.
- Keep consistency with the existing design system (sidebar variables, colors).

### Non-Goals
- No backend or API changes.
- No renaming of JS functions used by buttons.
- No removal of features; hiding is allowed via collapsible sections but must remain discoverable.

### Initial Prompt (translated to English)
User request summary preserved verbatim for historical accuracy and intent clarity.

"At http://192.168.88.82:8000/maintenance

Make this page more compact, but functionality must remain the same. Just change the design.

=== Analyse the Task and project ===

Deeply analyze our task and project and decide how to best implement it.

==================================================

=== Create Roadmap ===

Create a detailed, comprehensive step-by-step plan for implementing this task in a separate document file. We have a folder docs/features for this. If such a folder does not exist, create it. Document in the file in as much detail as possible all identified and tried problems, nuances and solutions, if any. As you progress with this task, you will use this file as a to-do checklist, update it and document what has been done, how it was done, what problems arose and which decisions were made. For history do not delete items, only update their status and comment. If during the implementation it becomes clear that something needs to be added, add it to this document. This will help us preserve context, remember what we have already done and not forget what was planned. Remember that only the English language is allowed in code and comments, texts of the project. When you write the plan, stop and ask me if I agree to start implementing it or something needs to be adjusted in it.

Include this prompt you wrote into the plan, but translate it into English. You can name it something like 'Initial Prompt' in the plan document. This is needed to preserve the exact context of the task setup in our roadmap file without the 'broken telephone' effect.

Also include steps for manual testing, i.e., what to click in the interface.

==================================================

=== SOLID, DRY, KISS, UI/UX, etc ===

Follow the principles: SOLID, DRY, KISS, Separation of Concerns, Single Level of Abstraction, Clean Code Practices.
Follow UI/UX principles: User-Friendly, Intuitive, Consistency, Accessibility, Feedback, Simplicity, Aesthetic & Modern, Performance, Responsive Design.
Use Best Practices."

---

### Design Strategy
- Reduce paddings/margins and font sizes moderately; increase information density while maintaining readability.
- Switch action areas to a compact multi-column layout inside cards (e.g., two-column button grid on desktop, single-column on narrow screens).
- Make cards collapsible by default on secondary sections, keep state via `localStorage` (discoverability: show clear section headers and arrows/chevrons). Primary sections (System Statistics, Server Control) remain expanded by default.
- Consolidate status messages into a slim status bar per card (single line, subtle colors) and place them directly below controls.
- Keep icons plus short labels; do not rely on icons only. Show tooltips for clarity.
- Reuse shared CSS variables from `sidebar_styles.html` to ensure theme consistency.

### High-Level UI Layout Changes
- Header: keep title, shrink font size slightly, keep restart shortcut button.
- Stats: display as compact tiles with reduced gutters and font size; allow quick refresh.
- Cards: uniform compact style, each with:
  - Collapsible header
  - Action button grid (2 columns on >=768px, 1 column below)
  - Slim status line
- Cookies Health: lazy-load and show within System Operations; keep hidden until requested.

### Accessibility
- Maintain color contrast for state badges (success/error/processing) using current palette.
- Keyboard navigation: headers focusable to toggle collapse; buttons reachable in order.
- Aria attributes for collapsible regions (aria-expanded, aria-controls; role="button" on headers).

### Implementation Plan (Step-by-step)

1) Preparation and backups
- [x] Create backup copy of `templates/maintenance.html` (initially stored under `backups/templates/maintenance_20250809.html`; removed after merge – rely on git history).
- [ ] Capture screenshots of current page for before/after comparison.

2) CSS refactor for compactness
- [x] Extract inline maintenance-specific CSS into `static/css/maintenance.css` (linked from template).
- [x] Reduce paddings/margins: container, cards, headers, buttons, stats.
- [x] Define compact button variant (smaller height, font-size ~12–13px, tighter gaps).
- [x] Create responsive 2-col grid for action buttons (minmax ~220–260px) and adjust gaps.
- [x] Compact status bar styles: single-line, subtle background, smaller font.

3) Collapsible sections
- [x] Convert each card to be collapsible: header toggles content; default expanded by saved state (initially expanded for all).
- [x] Persist expand/collapse state in `localStorage` keyed by section id (`maintenance.collapse.<card-id>`).
- [x] Add accessible attributes: `role="button"`, `tabindex="0"`, `aria-expanded`, `aria-controls`; support Enter/Space.

4) HTML structure updates in `templates/maintenance.html`
- [x] Keep all existing element IDs referenced by JS status updaters (e.g., `database-status`, `metadata-status`, `system-status`, `cleanup-status`, `server-status`).
- [x] Keep all button `onclick` handlers as-is to preserve existing JS functions and endpoints.
- [x] Replace action button container with compact grid classes; ensure no functional change (using existing `.action-buttons` class with new CSS grid).
- [x] Move repeated utility styles to the new CSS file; keep template minimal.

5) JS enhancements (non-breaking)
- [x] Add tiny helper to manage collapsible state (read/write `localStorage`).
- [x] Ensure `refreshStats()` runs on load and after certain actions, as today.
- [x] Keep network calls and status updates untouched to avoid regressions.

6) Manual testing (desktop + mobile width)
- [x] Load `/maintenance` and verify layout is compact, readable, responsive.
- [x] Click "Restart" in header → confirmation, then reload behavior.
- [x] Statistics load and refresh via "Refresh Statistics".
- [x] Database Operations: run each button and verify status messages and no JS errors.
- [x] Metadata Operations: run full and limited scans; verify status updates and counters.
- [x] System Operations: clear queue (with confirm), open logs in new tab, show cookies health (table loads or shows friendly empty state).
- [x] Cleanup Operations: old logs, temp files, trash; verify confirmations & messages where applicable.
- [x] Server Control: restart/stop flows; verify messaging and page behavior.
- [x] Collapsible headers: toggle via mouse and keyboard (Enter/Space); state persists across reloads.
- [x] Accessibility quick pass: focus outlines visible; contrast adequate; tooltips readable.

7) Performance and QA
- [ ] Ensure no blocking layout shifts; CSS is lightweight and cached.
- [ ] Verify no console errors; network endpoints as before.
- [ ] Lighthouse/quick audits for accessibility and performance (optional but recommended).

8) Rollout and fallback
- [ ] Commit with conventional message and detailed body.
- [ ] Retain backup of original template for quick revert.

### Risks & Mitigations
- Risk: Collapsible sections might hide actions from users expecting the old layout.
  - Mitigation: Keep most-used sections expanded by default; add clear chevrons; remember state per user via `localStorage`.
- Risk: Over-compact buttons become hard to tap on mobile.
  - Mitigation: Maintain minimum touch target height (~36–40px) on small screens.
- Risk: Breaking JS status updaters.
  - Mitigation: Do not rename element IDs or function names; verify via manual tests.

### Acceptance Criteria
- All buttons and flows work exactly as before (no removed endpoints, no renamed functions/ids).
- Page height and vertical spacing are visibly reduced on desktop.
- Collapsible sections operate with state persistence and accessibility attributes.
- No new console errors; API responses handled unchanged.
- Responsive layout: two-column button grid ≥768px; single-column below.

### Change List (planned)
- `templates/maintenance.html`: structural tweaks for compactness; add collapse hooks; import `static/css/maintenance.css`.
- `static/css/maintenance.css`: new stylesheet for compact layout (padding, grid, status, buttons).
- No backend file changes.

### Work Breakdown / Checklist
- [x] Backup current template and capture screenshots (backup created then deleted; rely on git; screenshots: pending)
- [ ] Create `static/css/maintenance.css` with compact theme
  - [x] Added `static/css/maintenance.css` and linked in `templates/maintenance.html`
- [ ] Update HTML to use compact classes and collapsible sections
  - [x] Added collapsible markup and ARIA to `templates/maintenance.html`; added JS `initCollapsibles()`
  - [x] Verified compact button grid via `.action-buttons` (no functional changes)
- [ ] Add minimal JS to manage collapse + persistence (non-breaking)
  - [x] Implemented `initCollapsibles()` with keyboard support and persistence
- [ ] Verify all actions and status messages
- [x] Verify all actions and status messages
- [x] Manual test on desktop and mobile widths
- [ ] Final polish and commit

### Manual Test Script (step-by-step)
1. Open `/maintenance` on desktop width (≥1200px).
   - Verify header, restart button, and compact stats grid.
2. Toggle each section header to collapse/expand; refresh the page and confirm state persistence.
3. Database Operations:
   - Click "Create Database Backup" → success/error status updates.
   - Click "Run Database Maintenance" → status changes accordingly.
   - Click "Rescan Library" → status updated; no console errors.
   - Click "Enqueue Library Rescan (Jobs)" → job id appears in success message.
4. Metadata Operations:
   - Click "Scan Missing Metadata" → success message and stats refresh shortly.
   - Click "Scan Limited (50 tracks)" → success message.
   - Click "View Metadata Statistics" → opens JSON in new tab.
5. System Operations:
   - Click "Clear Job Queue" → confirmation prompt → success count.
   - Click "View System Logs" → logs page opens.
   - Click "Refresh Statistics" → stats update.
   - Click "Show Cookies Health" → table appears; handles empty and error states.
6. Cleanup Operations:
   - Click each cleanup action and verify status messages.
7. Server Control:
   - Click "Restart Server" → confirmation → status shows restarting and page reloads.
   - Click "Stop Server" → confirmation → status shows stopped message.
8. Resize to mobile width (~375–414px) and repeat a subset of actions; verify tap targets and readability.

### Next Steps
Pending your approval of this roadmap, we will implement the compact UI as described, starting with CSS extraction and collapsible sections, ensuring zero functional regressions.



## Mobile-friendly confirmation dialog for Delete action on Remote Control page

### Context and goal
The current Delete action on the Remote page (`/remote`) uses the native `confirm()` dialog in `static/js/modules/remote-control.js`. On mobile devices, this dialog is visually inconsistent with the app’s design and provides a suboptimal touch experience. The goal is to implement a modern, accessible, mobile-first confirmation modal that replaces the native confirm for the Remote page while keeping the solution simple, reliable, and consistent with existing design tokens in `static/css/remote.css`.

### Initial Prompt (translated to English)
User request (translated):

"On the page at `http://192.168.88.82:8000/remote`, when you click the delete icon, a confirmation window appears — that’s correct. But the window looks terrible. Can you make it convenient for mobile?

=== Analyse the Task and project ===

Deeply analyze our task and project and decide how best to implement this.

==================================================

=== Create Roadmap ===

Create a detailed, step-by-step action plan for implementing this task in a separate document file. We have a folder `docs/features` for this. If there is no such folder, create it. Document all discovered and tried problems, nuances, and solutions in as much detail as possible, if any. As you progress with the implementation, you will use this file as a todo checklist, updating it and documenting what has been done, how it was done, what problems arose, and what solutions were adopted. For history, do not delete items; only update their status and comment on them. If during implementation it becomes clear that something needs to be added, add it to this document. This will help us preserve context, remember what has already been done, and not forget to do what was planned. Remember that only the English language is allowed in code and comments, strings, commit messages, error messages, logging, and API responses. When you write the plan, stop and ask me whether I agree to start implementing it or if something needs to be adjusted in it.

Include in the plan the very prompt that I wrote to you, but translate it into English. You can call it something like ‘Initial Prompt’ in the roadmap plan document. This is needed to keep the task context in our roadmap file as accurately as possible without a “broken telephone” effect.

Also include steps for manual testing: what needs to be clicked in the interface. 

==================================================

=== SOLID, DRY, KISS, UI/UX, etc ===

Follow principles: SOLID, DRY, KISS, Separation of Concerns, Single Level of Abstraction, Clean Code Practices. Follow UI/UX principles: User-Friendly, Intuitive, Consistency, Accessibility, Feedback, Simplicity, Aesthetic & Modern, Performance, Responsive Design. Use Best Practices."

### Current state (findings)
- Native confirmations are used in several parts of the codebase. For the Remote page specifically, the delete action is implemented in `static/js/modules/remote-control.js` and uses `confirm()` with a descriptive message.
- Remote page composition:
  - `templates/remote/base.html` includes `static/css/remote.css` and the modules `toast-notifications.js`, `keep-awake.js`, `volume-control.js`, `remote-control.js`, and finally `js/remote.js` (entry point).
  - Delete button markup is in `templates/remote/components/controls.html` (`#deleteBtn`).
  - There is no shared modal component loaded on the Remote page yet.
- Existing modal styles exist on other pages (`static/css/home.css`, `static/css/backups.css`, `static/css/jobs.css`, `static/css/channels.css`), but they are page-specific and not centralized. Remote page has no `.modal` styles yet.

### Requirements
- Functional
  - Replace `confirm()` for the delete action on the Remote page with a custom confirmation modal.
  - Display track title and video ID when available; otherwise show a generic message.
  - Offer clear primary (destructive) and secondary (cancel) actions.
  - Provide a safe cancel by tapping outside the modal and via Escape key.
  - Fallback to native `confirm()` if the custom modal fails to load (progressive enhancement).
- UX/UI
  - Mobile-first, touch-friendly targets (min 44x44px), comfortable spacing, and clear typography.
  - Aesthetic consistent with `remote.css` (using existing tokens: `--bg`, `--card-bg`, `--accent`, `--error`, `--border`, shadows, radii).
  - Clear warning/feedback copy: that deletion moves item to Trash and can be restored.
  - Smooth, unobtrusive transitions and a dimmed backdrop.
- Accessibility
  - Proper ARIA roles (`role="dialog"`, `aria-modal="true"`), labeled title and description (`aria-labelledby`, `aria-describedby`).
  - Focus management: focus trap within the modal; initial focus on the primary button; return focus to the invoker on close.
  - Keyboard support: Enter to confirm, Escape to cancel, Tab cycle.
- Performance & reliability
  - Zero external dependencies.
  - Lightweight, no layout shift; prevent background scroll while open.
  - Works in Chromium (Android), Safari (iOS), and desktop browsers.

### Scope
- In-scope: Remote page only, replacing the delete confirmation with a custom modal.
- Out-of-scope (for now): Refactoring all pages to use a unified modal system. We will leave a note for future consolidation.

### Proposed architecture
- Add a minimal, reusable confirmation dialog module for the Remote page only:
  - JS: `static/js/modules/confirm-dialog.js` exposes `window.showConfirmDialog(options) -> Promise<boolean>`.
  - Options: `{ title, message, confirmText, cancelText, destructive, withinDocument? }`.
  - The module dynamically injects the modal DOM into `document.body` when called, wires handlers, traps focus, and cleans up on resolve.
  - Returns `true` on confirm, `false` on cancel/close/outside click/Escape.
- CSS: Add a small, self-contained modal style block inside `static/css/remote.css` to avoid cross-page side effects.
  - Use CSS variables already defined in `remote.css`.
  - Ensure responsive sizing and large tap targets.
- Integration points:
  - `templates/remote/base.html`: include `confirm-dialog.js` before `remote-control.js`.
  - `static/js/modules/remote-control.js`: replace `confirm(...)` with `await showConfirmDialog(...)` while preserving the deletion logic.
- Fallback:
  - If `showConfirmDialog` is not present, fall back to native `confirm()` to maintain functionality.

### API design (draft)
```js
// static/js/modules/confirm-dialog.js
// Promise-based confirmation dialog
// Usage: const ok = await window.showConfirmDialog({ title, message, confirmText, cancelText, destructive: true });

type ConfirmDialogOptions = {
  title?: string,
  message: string,
  confirmText?: string,        // default: "Delete" when destructive, else "OK"
  cancelText?: string,         // default: "Cancel"
  destructive?: boolean,       // styles the confirm action as destructive
};

declare function showConfirmDialog(options: ConfirmDialogOptions): Promise<boolean>;
```

### Implementation plan (step-by-step)
1) Create module `static/js/modules/confirm-dialog.js` [TODO]
   - Implement DOM creation with backdrop, container, header (optional title), body (message), actions (Cancel, Confirm).
   - Add ARIA attributes (`role`, `aria-modal`, `aria-labelledby`, `aria-describedby`).
   - Focus management: store active element, focus the confirm button on open, restore focus on close.
   - Keyboard support: Enter confirms, Escape cancels; trap focus with a simple loop.
   - Close behaviors: cancel on backdrop click and on explicit Cancel.
   - Promise resolution: resolve true on confirm; false otherwise; always cleanup DOM and listeners.

2) Add styles to `static/css/remote.css` [TODO]
   - `.modal`, `.modal-backdrop`, `.modal-content`, `.modal-header`, `.modal-title`, `.modal-body`, `.modal-actions`, `.btn`, `.btn-secondary`, `.btn-danger`.
   - Leverage existing variables: `--card-bg`, `--border`, `--accent`, `--error`, `--shadow`, radii match existing controls.
   - Ensure responsive sizing (max-width ~92vw on mobile, min tap targets >= 44px).

3) Wire module into the page [TODO]
   - `templates/remote/base.html`: include `<script src="{{ url_for('static', filename='js/modules/confirm-dialog.js') }}"></script>` before `remote-control.js`.

4) Replace native confirm in `static/js/modules/remote-control.js` [TODO]
   - Where delete is handled (current code uses `confirm(confirmMessage)`), call:
     ```js
     const ok = window.showConfirmDialog
       ? await window.showConfirmDialog({
           title: 'Delete Track',
           message: confirmMessage.replace('\n\n', '<br/><br/>'),
           confirmText: 'Delete',
           cancelText: 'Cancel',
           destructive: true,
         })
       : confirm(confirmMessage);
     if (ok) { await this.sendCommand('delete'); }
     ```

5) Manual QA and cross-browser checks [TODO]
   - See Test plan below.

6) Optional polish [LATER]
   - Haptic feedback (where supported), subtle entrance/exit transitions.

7) Future consolidation [LATER]
   - Extract a shared `modal.css` and `confirm-dialog.js` for reuse across pages currently using native `confirm()`.

### Acceptance criteria
- The Delete action on `/remote` no longer uses a native confirm dialog; a custom modal is displayed instead.
- The modal:
  - Matches the app visual style and is mobile-friendly.
  - Shows track title and video ID when available.
  - Supports keyboard and screen readers.
  - Closes on backdrop tap and Escape.
  - Has clear destructive action styling for Delete and a secondary Cancel.
- If the custom modal fails to load for any reason, the native confirm is used as a fallback.

### Risks and mitigations
- Focus trapping and scroll locking can be fragile:
  - Keep implementation minimal; test on iOS Safari and Android Chrome.
- Visual overlaps on small screens:
  - Use fluid widths and max-height, enable internal scroll within the modal body.
- Inconsistent styles with other pages:
  - Keep styles local to Remote page to avoid regressions. Plan future unification separately.

### Test plan (manual)
- Navigation
  - Open `http://192.168.88.82:8000/remote` on a phone (Android Chrome and iOS Safari) and desktop Chrome.
- Happy path
  - Ensure a track is playing; tap the Delete icon.
  - Verify the modal appears centered with dim backdrop.
  - Verify title "Delete Track" and the message includes track title and video ID.
  - Tap outside the modal: modal closes (cancels) and nothing happens.
  - Tap Delete: modal closes, deletion command is sent; after a short sync, the next track is displayed or status updates correctly.
- Edge cases
  - When no track info is available: modal shows generic message and still works.
  - Keyboard: on desktop, press Escape to cancel; Tab cycles through buttons; Enter confirms.
  - Rapid taps: open and cancel multiple times; no duplicate DOM nodes remain.
  - Rotate device orientation: layout remains readable; buttons remain reachable.
  - Network failure on deletion: UI doesn’t freeze; error handling remains as before (sendCommand error path).

### Work breakdown checklist
- [x] Implement `static/js/modules/confirm-dialog.js` (Promise-based modal, ARIA, focus, cleanup)
- [x] Add modal styles inside `static/css/remote.css` (mobile-first)
- [x] Include module in `templates/remote/base.html` before `remote-control.js`
- [x] Replace `confirm()` usage in `static/js/modules/remote-control.js` with the new modal (with fallback)
- [ ] Manual testing per Test plan
- [ ] Cross-browser smoke test (Android Chrome, iOS Safari, desktop Chrome/Firefox)
- [ ] Code review: readability, adherence to SOLID/DRY/KISS
- [ ] Prepare exhaustive commit message (English) following conventional commits

### Progress notes
- Implemented `static/js/modules/confirm-dialog.js` with the following characteristics:
  - Global API: `window.showConfirmDialog(options) -> Promise<boolean>`
  - Options: `{ title?, message?, htmlMessage?, confirmText?, cancelText = 'Cancel', destructive = false }`
  - Accessibility: `role="dialog"`, `aria-modal="true"`, labeled title/body, keyboard support (Tab trap, Enter confirm, Esc cancel)
  - UX: backdrop click to cancel, focus returns to invoker, scroll lock during modal open
  - Cleanup: removes listeners and DOM on resolve
  - No external dependencies
- Added modal styles into `static/css/remote.css`:
  - Backdrop, content card, header, buttons (`.btn`, `.btn-primary`, `.btn-secondary`, `.btn-danger`)
  - Subtle animations for entrance and backdrop fade
  - Mobile-friendly sizing/tap targets and use of existing design tokens
- Included script in `templates/remote/base.html` before `remote-control.js` to ensure availability of `window.showConfirmDialog`
- Replaced native `confirm()` in `static/js/modules/remote-control.js` delete handler with `await window.showConfirmDialog({...})` and safe fallback to `window.confirm`

### Current testing status
- [x] Manual testing per Test plan (verified by user: "everything works")
- [ ] Cross-browser smoke test (Android Chrome, iOS Safari, desktop Chrome/Firefox)

### Notes on principles and best practices
- SOLID/KISS/DRY: The module is single-purpose, encapsulated, with a minimal API. No duplication across files; fallback is simple.
- Separation of concerns: Styling stays in `remote.css`, behavior in a small JS module, HTML produced at runtime.
- Accessibility: ARIA roles, focus management, keyboard controls.
- Performance: No external dependencies; minimal DOM and CSS. Modal is only created when needed and destroyed afterward.

### Rollback plan
- Revert the inclusion of `confirm-dialog.js` and the changes in `remote-control.js`.
- Remove added CSS from `remote.css`.
- Native `confirm()` behavior will be restored immediately.



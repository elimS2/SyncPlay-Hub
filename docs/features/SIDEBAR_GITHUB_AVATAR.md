## Feature: Sidebar GitHub Avatar Next to Username

### Status
- Planning: done
- Implementation: in progress

### Context
The left sidebar currently shows a status block with server info and a GitHub link:
"GitHub: elimS2" with an Octocat icon at the left. The goal is to display a small GitHub avatar (like a gravatar) right after the username, not larger than the cat icon to maintain visual balance.

### Initial Prompt (Translated to English)
"In the sidebar there is the following block:

PID: 144128 | Uptime: 0:12:24
Started: 2025-08-17 02:27:05
Current: 2025-08-17 02:39:30
GitHub: elimS2

I want that in the line GitHub: elimS2 after elimS2 my small GitHub avatar is shown, like a gravatar, no larger than the cat icon to the left of the word GitHub.

=== Analyse the Task and project ===

Deeply analyze our task, our project and decide how best to implement it.

==================================================

=== Create Roadmap ===

Create a detailed, step-by-step action plan for implementing this task in a separate document file. We have a folder docs/features for this. If there is no such folder, create it. Document all discovered and tested issues, nuances and solutions in as much detail as possible in the document, if any. As you progress with the implementation of this task, you will use this file as a todo checklist, you will update this file and document what has been done, how it was done, what problems arose and what decisions were made. For history, do not delete items; you can only update their status and comment. If during implementation it becomes clear that something needs to be added from the tasks – add it to this document. This will help us maintain the context window, remember what we have already done, and not forget to do what was planned. Remember that only the English language is allowed in the code and comments, captions of the project. When you write the plan, stop and ask me if I agree to start implementing it or if something needs to be adjusted in it.

Include this prompt that I wrote to you in the plan itself, but translate it into English. You can name it something like "Initial Prompt" in the plan document. This is needed to preserve the context of the task setting in our roadmap file as accurately as possible without the “broken telephone” effect.

Also include steps for manual testing, that is, what needs to be clicked through in the interface.

==================================================

=== SOLID, DRY, KISS, UI/UX, etc ===

Follow the principles: SOLID, DRY, KISS, Separation of Concerns, Single Level of Abstraction, Clean Code Practices.
Follow UI/UX principles: User-Friendly, Intuitive, Consistency, Accessibility, Feedback, Simplicity, Aesthetic & Modern, Performance, Responsive Design.
Use Best Practices."

### Requirements and Acceptance Criteria
- Display the GitHub avatar image after the username text inside the existing GitHub link in the sidebar status block.
- Avatar display size: 25x25 as requested. This intentionally exceeds the existing `.nav-icon` (20x20). Ensure alignment and spacing remain visually balanced.
- Preserve the existing left Octocat icon and the text "GitHub: <username>".
- Maintain visual alignment with the link’s flex layout and spacing.
- Do not degrade performance; avoid blocking layout. Use `loading="lazy"` and small image size.
- Accessibility: provide meaningful `alt` text; maintain sufficient color contrast and focus styles.
- Implementation must comply with English-only code/docs policy.
- No breaking changes to other sidebar items or layouts across pages that include `sidebar.html` and `sidebar_styles.html`.

### Design Overview
- Image source: GitHub provides `https://github.com/<username>.png`. We can request a small size (e.g., `?size=32`) and display at 16px to improve sharpness on high-DPI screens.
- Placement: within `templates/sidebar.html`, inside the `<a class="github-link">` right after the username text.
- Styling: extend `templates/sidebar_styles.html` to add `.github-avatar` rules (size, border-radius, subtle border for visibility in light/dark themes, and alignment). The link already uses `display: flex; align-items: center; gap: 5px;` which we will leverage.
- Configurability (optional enhancement): centralize the GitHub username in the server context (e.g., Flask config/env) to avoid duplication and ease future changes.
- Resilience: if the avatar fails to load (offline/404), hide the broken image or fall back to a neutral placeholder while keeping the Octocat icon in place.

### File Inventory (Impacted)
- `templates/sidebar.html` – add the avatar `<img>` after the username. Optionally wrap the text in a span for consistent spacing.
- `templates/sidebar_styles.html` – add `.github-avatar` CSS rules. Keep styles minimal and scoped.
- (Optional) `app.py` – inject `GITHUB_USERNAME` into the template context; otherwise, keep the existing hard-coded username to minimize scope.

### Implementation Plan (Step-by-Step)
1. Add CSS for the avatar in `templates/sidebar_styles.html`:
   - `.github-avatar { width: 16px; height: 16px; border-radius: 50%; object-fit: cover; flex: 0 0 auto; }`
   - Add a subtle 1px border using theme variables to ensure visibility on both dark/light backgrounds.
   - Ensure it inherits the link’s hover color for consistency or remains neutral (validate visually).
2. Update `templates/sidebar.html` within the GitHub link block:
   - Wrap the text `GitHub: elimS2` into `<span class="github-text">GitHub: elimS2</span>`.
   - Append `<img class="github-avatar" src="https://github.com/elimS2.png?size=32" alt="elimS2 avatar" width="16" height="16" loading="lazy" decoding="async" referrerpolicy="no-referrer" onerror="this.style.display='none'" />`.
   - Keep the existing left icon `<span class="nav-icon nav-icon-github"></span>` unchanged.
3. (Optional, DRY) Centralize username:
   - Introduce `GITHUB_USERNAME` via environment variable or config and pass to all templates (e.g., via Flask `app.context_processor`).
   - Replace hard-coded `elimS2` and corresponding URL and `alt` text to use the variable.
4. Verify responsiveness:
   - Ensure the link layout remains intact across breakpoints defined in `sidebar_styles.html` and does not wrap undesirably.
5. Linting/Formatting:
   - Keep indentation, style, and HTML structure consistent with the project.

### Manual Testing Plan
- Open pages that include the sidebar (e.g., `Playlists`, `Tracks`, `Jobs`).
- Verify the GitHub line shows: [Octocat icon] "GitHub: elimS2" [circular avatar].
- Check avatar size is ≤ the Octocat icon height; no vertical misalignment.
- Click the GitHub link; ensure it opens the profile in a new tab.
- Toggle/verify hover state: link color updates, avatar appearance remains acceptable.
- Test on both dark and light schemes (if available) to ensure avatar border/visibility.
- Resize the window to mobile width; ensure layout remains clean and does not overflow.
- Simulate offline or block images (DevTools): verify no broken image icon is shown (image is hidden via `onerror`).

### Edge Cases and Considerations
- Network failures: image may 404 or time out; we hide the avatar to avoid broken UI. The Octocat icon remains as a fallback visual.
- High-DPI screens: request `?size=32` and display at 16px for crisper rendering.
- Privacy/Referrer: add `referrerpolicy="no-referrer"` for external image requests.
- Caching: browsers cache GitHub avatars; no extra work needed.
- Performance: using `loading="lazy"` prevents early blocking; negligible impact given one small image.

### Accessibility
- Provide `alt` as `<username> avatar`.
- Keep focusable element as the link; image is decorative but informative; `alt` suffices.
- Maintain color contrast for hover/focus states.

### Rollback Plan
- Revert changes in `templates/sidebar.html` and remove the `.github-avatar` CSS block from `templates/sidebar_styles.html`. No data migrations or backend changes are involved.

### Decisions Confirmed
- Hardcode username and avatar source (no config variable at this time).
- The entire link remains clickable (including the avatar image).
- Tooltip is not needed for now.
- Single account only (author page), no multi-account support.

### Tasks Checklist (Live Doc)
- [x] Add `.github-avatar` CSS to `templates/sidebar_styles.html`.
- [x] Update `templates/sidebar.html` link content to include the avatar `<img>` after the username.
- [ ] Visual QA on desktop and mobile widths.
- [ ] Accessibility QA (keyboard focus, alt text). 
- [ ] (Optional) Centralize `GITHUB_USERNAME` via Flask context.
- [ ] Update this document with outcomes, screenshots (optional), and any deviations.

### Notes (Current Step)
- Inserted avatar image after username; size updated to 25×25 per request, circular, lazy loading, and `onerror` fallback to hide broken image. Entire link remains clickable as requested.
 - Adjusted `.server-info` font-size to 16px to improve readability of status lines.

### Future Improvements (Optional)
- Add a tooltip on hover showing "Open GitHub profile".
- Fetch and cache the avatar server-side and serve it from the app to avoid third-party requests.
- Make the username and link configurable in Settings UI.



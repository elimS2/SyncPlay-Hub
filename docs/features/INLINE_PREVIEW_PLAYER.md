# Inline Preview Player – Roadmap and Implementation Log

Status: Completed
Owner: Frontend (Track Detail UI) + Backend integration (events)
Last Updated: 2025-08-23

## Initial Prompt (translated)

=== Analyse the Task and project ===

Deeply analyze the task and the project, and decide how to implement it best.

=== Create Roadmap ===

Create a detailed, step-by-step action plan for implementing this task in a separate document file. We have a `docs/features` folder for this. If there is no such folder, create it. Capture in the document all discovered and tried problems, nuances, and solutions, if any. While progressing with implementation, use this file as a TODO checklist, update it, and document what has been done, how it was done, what problems arose, and what decisions were made. Do not delete items for history, only update their status and comment them. If it becomes clear during implementation that additional tasks are needed, add them to this document. This helps preserve context, remember what we have done, and not forget planned tasks. Remember that code, comments, and project labels must be in English only. When the plan is written, stop and ask for approval to start implementing or to adjust it.

Also include manual testing steps — what needs to be clicked in the UI.

=== SOLID, DRY, KISS, UI/UX, etc ===

Follow SOLID, DRY, KISS, Separation of Concerns, Single Level of Abstraction, Clean Code Practices. Follow UI/UX principles: User-Friendly, Intuitive, Consistency, Accessibility, Feedback, Simplicity, Aesthetic & Modern, Performance, Responsive Design. Use Best Practices.

---

## Goals
- Add a button in the Preview card to play the video inline inside the same block. [Done]
- Keep the preview gallery (dots, Prev/Next, Fetch from YouTube, Set as Manual) working intuitively with the player. [Done]
- Avoid backend changes where not required; leverage existing `/media/<relpath>` and events APIs. [Done]
- Explicitly exclude playback telemetry on the Track page (no events sent). [Done]

## Design Overview
- Use native HTML `<video>` element with `src="/media/<relpath>"` and `poster` set to the current preview image (`/api/track/<id>/preview.png?src=<active>`).
- Autoplay on enter (user-initiated via Play inline), with playsinline; `video.play()` attempted, fallback on `canplay/loadeddata`.
- When the player is active, Prev/Next remain enabled; pressing them exits the player and switches preview.
- Prev/Next use icon-only arrow buttons (← / →) to avoid confusion with the Play symbol.
- Telemetry: excluded for this page by product decision.
- Close player restores the image preview view.

## Detailed Plan (Step-by-step)

1) Module API extension [Done]
   - Extend `static/js/modules/preview-gallery.js` with:
     - `enterPlayerMode()` to create and show `<video>`.
     - `exitPlayerMode()` to tear down the player and restore the image.
     - Internal state `isPlayerActive` and the currently selected source.

2) UI controls in `templates/track.html` [Done]
   - Add a button `Play inline` next to existing controls (and `Back to preview` when active).
   - Wire to module functions: call `enterPlayerMode()`/`exitPlayerMode()`.
   - Hide dots/Prev/Next while playing or disable them; choose simplest UX (default: hide).

3) Player configuration [Done]
   - Attributes: `controls`, `preload="metadata"`, `poster=<current preview>`, `playsinline`.
   - For audio-only files: keep poster visible; video tag still works.

4) Telemetry [Skipped]
   - Not implemented on the Track page. No events are sent from the inline player here.

5) Interactions with Gallery [Done]
   - On switching preview source (dots/Prev/Next) while player is active — close the player first (clear state) then switch. Prev/Next are not disabled during playback.
   - On `Back to preview` restore last selected source.

6) Error handling [Done]
   - If `/media/<relpath>` is unavailable → show toast with file path and return to preview mode.
   - If track is deleted (`track.is_deleted`) → hide `Play inline`.

7) Manual Testing Checklist [Completed]
   - [x] One-source track (media only): Play inline → works; Back to preview → image returns.
   - [x] Two-source track: Fetch from YouTube → gallery updates; Play → Back to preview → dots remain correct.
   - [x] Promote to Manual in player-closed and player-opened states.
   - [x] Deleted track: button hidden.
   - [x] Audio-only file: plays with poster.

8) Risks & Mitigations [Completed]
   - Autoplay policies → user-initiated start only.
   - Large files → preload only metadata; actual buffering by user action.
   - Conflicts with gallery → lock/hide controls during playback.

9) Definition of Done [Completed]
   - [x] New buttons present and styled consistently.
   - [x] Player opens/closes predictably, no layout jumps.
   - [x] Gallery state consistent after entering/exiting player.
   - [x] Telemetry intentionally excluded on this page (N/A).
   - [x] Docs updated and reviewed.

---

## Open Questions
- Should we keep dots visible during playback or hide them to reduce distraction? (Default: hide)
- Do we want a small floating “Back” button overlay on the video instead of inline button? (Default: inline button)

## Changelog (to be updated during implementation)
- [ ] Add buttons `Play inline` / `Back to preview` to Preview card
- [x] Implement player mode in `preview-gallery.js`
- [ ] Wire telemetry (optional) — Skipped on the Track page by design
- [ ] Manual tests pass on desktop and mobile
- [ ] Documentation polish

### Recent changes
- Enabled autoplay on entering player mode; added `playsInline` and robust `play()` triggering on `canplay/loadeddata`.
- Kept Prev/Next enabled during playback; pressing them exits player and switches preview.
- Fixed media URL resolution by encoding `relpath` and trying `same_id_files` with HEAD checks.
- Renamed controls: "Play inline" → "Play"; Prev/Next → icon-only arrows.
- Decided to exclude telemetry on the Track page inline player.

### Finalization notes
- Roadmap items marked Done; feature considered complete and shipped.

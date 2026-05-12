# pd-ocr-labeler-spa: Page Actions Bar

> **Status**: Draft
> **Last updated**: 2026-05-12
> **Spec-Issue**: ConcaveTrillion/pd-ocr-labeler-spa#20

## TL;DR

A horizontal row below the project navigation controls: Reload OCR, Reload OCR (Edited),
Save Page, Save Project (202+job), Load Page, Rematch GT, Rotate buttons (M9.1),
Export…, page name label, source badge, and rotation badge. All buttons disabled while
a page mutation or active job is targeting this page.

## Context

The legacy `page_actions.py` wires button callbacks directly to `PageState` methods.
The SPA exposes each action as a distinct REST endpoint, some synchronous (Save Page)
and some long-running returning `202 + job_id` (Save Project, Reload OCR).

The `source badge` (`OCR` / `CACHED` / `LABELED`) communicates to the user which lane
the current page data came from (`PageRecord.page_source`).

## Constraints

- **All buttons disabled during any active page mutation or job.** No concurrent mutations
  on the same page. The SPA checks `useIsMutating` and `useJobProgress`.
- **`has_edited_image` gate.** "Reload OCR (Edited)" is disabled when
  `PagePayload.has_edited_image === false`.
- **Save Project is a long-running job.** Returns `202 + job_id`; SPA must show progress
  via `useJobProgress`.
- **Rotate buttons ship in M9.1.** Present in DOM but hidden via CSS until M9.1 is
  implemented (feature-flagged by milestone, not a feature flag in code).
- **Auto-save is server-side.** The SPA does not implement a client-side autosave timer;
  the server writes to cached lane after every mutation.

## Decision

### Button layout (left to right)

1. **Reload OCR** — POST `.../reload-ocr {use_edited_image: false}` → 202+job.
2. **Reload OCR (Edited)** — same with `use_edited_image: true`. Disabled when
   `!has_edited_image`.
3. **Save Page** — POST `.../save`. Synchronous. Flips source badge to LABELED.
4. **Save Project** — POST `.../save-all` → 202+job. Shows progress in busy overlay.
5. **Load Page** — POST `.../load`. Re-loads from disk, discards in-memory edits.
6. **Rematch GT** — POST `.../rematch-gt`. Re-runs GT alignment synchronously.
7. **Rotate ↺ / ↻** (M9.1, hidden until then).
8. **Export…** — opens `<ExportDialog>` modal.

### Page name + badges

Right side of the bar: `page_001.png` (filename from `PageRecord.image_path`), source
badge (`OCR` / `CACHED` / `LABELED` derived from `page_source`), rotation badge
(angle, hidden until M9.1).

testids: `reload-ocr-button`, `reload-ocr-edited-button`, `save-page-button`,
`save-project-button`, `load-page-button`, `rematch-gt-button`, `export-button`,
`page-source-badge`, `page-name-label`.

### OCR reload flow

POST → 202 `{job_id}`. Open `useJobProgress(job_id)`. Show `<BusyOverlay>` with message.
On `complete`: invalidate page query, toast "OCR complete". On `error`: sticky toast with
error message; page state unchanged.

### OCR failure fallback

If OCR fails, backend returns a fallback `Page` with `page_source = "fallback"` and
`ocr_failed = true`. SPA renders a banner: "OCR failed for this page. Use Reload OCR to
retry." Source badge shows `FALLBACK`.

### Save Project flow

POST `/api/projects/{pid}/save-all` → 202 `{job_id}`. Progress events include per-page
progress. `<BusyOverlay>` with cancel button. On complete: toast "Saved N pages".
Failed pages listed in a dismissible panel.

### Hotkeys (page-action scope)

`Mod+S` — Save Page. `Mod+R` — Reload OCR. `E` — Export (open dialog).
Remaining hotkeys from `specs/12-hotkeys-a11y.md`.

## Contract / Acceptance

- Playwright: Save Page → POST fires → source badge flips to LABELED.
- Playwright: Reload OCR → 202 → BusyOverlay visible → EventSource terminal → OCR Complete
  toast → source badge flips to OCR.
- Playwright: "Reload OCR (Edited)" disabled when `has_edited_image = false`.
- Playwright: Save Project → progress events → "Saved N pages" toast.
- Vitest: SaveStatus indicator renders correct badge class for each `PageSource` value.

## Trade-offs considered

**Synchronous Save Page vs 202+job.** Save Page is fast enough to be synchronous (<200ms
typical). Save Project is slow (one write per page) and benefits from SSE progress.
Mixed approach: Save Page is synchronous; Save Project is 202+job.

**Busy overlay vs inline spinner.** Busy overlay blocks the entire page while a long job
runs, preventing concurrent mutations. Inline spinner would allow concurrent interaction,
risking inconsistent state. Overlay chosen.

**Rotate buttons hidden vs absent.** Keeping rotate buttons in the DOM (hidden) avoids a
layout shift when M9.1 ships. Hidden via CSS (`display: none`) not via conditional render.

## Consequences

- The busy overlay must release (and re-enable all buttons) on both `complete` and
  `error` job terminal events.
- Export dialog is a modal, not a route. Its testid must be registered in
  `specs/13-driver-contract.md`.

## Open questions

None.

## References

- `specs/08-page-actions.md` — legacy feature doc
- `specs/09-persistence.md` — save/load semantics and lane precedence
- `specs/11-notifications.md` — BusyOverlay and toast channel integration
- `specs/12-hotkeys-a11y.md` — page-action-scoped hotkeys
- `specs/19-auto-rotation.md` — Rotate button M9.1 detail

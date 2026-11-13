---
kind: spec
status: active
owner: maintainers
created: 2026-06-01
last_verified: 2026-11-13
---

# Behavior unit spec - Page actions and dialogs

- **Unit type:** component
- **Address:** `PageActionsCompact`, hidden `PageActions`, `OCRConfigModal`,
  `SourceFolderDialog`, `ExportDialog`, `HotkeyHelpModal`
- **UI definition:** none - existing stable UI documented in
  `docs/architecture/06-toolbar-actions.md`, `26-right-panel-detail.md`,
  `08-page-actions.md`, `10-export.md`, `12-hotkeys-a11y.md`,
  `13-driver-contract.md`
- **Parent unit(s):** `screen-project-page.md`, `screen-root.md`
- **Child unit(s):** jobs/SSE, page persistence, OCR config carrier
- **Shared unit:** yes
- **Implementation:** `frontend/src/components/PageActionsCompact.tsx`,
  `PageActions.tsx`, `OCRConfigModal.tsx`, `ExportDialog.tsx`,
  `SourceFolderDialog.tsx`, `HotkeyHelpModal.tsx`,
  `frontend/src/stores/dialog-store.ts`
- **Backend / collaborators touched:** save/reload/rematch/export endpoints,
  OCR config endpoints, filesystem browser endpoints, job runner, notification
  stream

## Behavior records

### B-ACTIONS-001 - OCR config dialog opens from the project toolbar

- **Flow(s):** -
- **Composed by:** B-PROJECT-001
- **Trigger:** User clicks `ocr-config-trigger-button`.
- **Preconditions:** Project route is loaded.
- **Observable output:** `ocr-config-modal` appears; available config fields
  and done/cancel controls are visible; closing returns to the project page.
- **Backend / side-effects:** Modal reads normalize/auto-rotate availability
  and OCR config; apply persists config through the OCR config endpoint and
  refreshes subsequent OCR jobs.
- **Bad-state / error:** Availability endpoints fail -> unavailable messages
  render and the modal remains closable; apply failure shows
  `ocr-config-save-error`.
- **Tier(s):** A
- **Regression:** yes (#405)
- **Test:** `tests/e2e/test_project_page_smoke.py::test_open_ocr_config_dialog`

### B-ACTIONS-002 - Save Page and Save Project flush dirty state to disk

- **Flow(s):** F-LABEL-SAVE-EXPORT-01
- **Composed by:** B-RIGHT-002, B-CANVAS-004
- **Trigger:** User clicks `save-page-button`, `save-project-button`, or uses
  the save hotkey.
- **Preconditions:** Page or project has dirty in-memory state.
- **Observable output:** Save status/progress updates and then returns to idle;
  success notification appears.
- **Backend / side-effects:** Save endpoint persists through the event-backed
  page store when a page id/store is available, then updates
  generation/dirty flags; Save Project runs a job that saves dirty pages.
- **Bad-state / error:** Save failure leaves dirty state visible, shows an
  error notification, and does not partially mark failed pages clean.
- **Tier(s):** A+B
- **Regression:** no
- **Test:** -

### B-ACTIONS-003 - Reload OCR, rematch, and refine actions create tracked jobs

- **Flow(s):** -
- **Composed by:** B-DRAWER-003, B-CANVAS-004
- **Trigger:** User clicks reload/rematch/refine actions from compact page
  actions, bulk actions, or toolbar grid.
- **Preconditions:** Project page is loaded; operation is available.
- **Observable output:** Action disables or shows busy/progress state; SSE/job
  progress updates; page data refreshes on completion.
- **Backend / side-effects:** Operation posts to the matching endpoint, creates
  a JobRunner job, streams/polls job status, and invalidates the page query
  after terminal success.
- **Bad-state / error:** Job failure displays an error toast/inline message and
  keeps previous page data intact.
- **Tier(s):** A+B for OCR/refine, A for deterministic rematch
- **Regression:** no
- **Test:** -

### B-ACTIONS-004 - Export dialog creates an export job and manifest

- **Flow(s):** F-LABEL-SAVE-EXPORT-01
- **Composed by:** B-ACTIONS-002
- **Trigger:** User opens Export dialog and submits export options.
- **Preconditions:** Project is loaded; export options are valid.
- **Observable output:** `export-dialog` closes or shows progress; completion
  notification/manifest path appears where exposed.
- **Backend / side-effects:** `POST /api/projects/{id}/export` creates an
  export job; handler writes XHTML/export artifacts and an export manifest.
- **Bad-state / error:** Invalid path/options produce a visible validation
  error; no export artifact is written outside the allowed project/export root.
- **Tier(s):** A+B
- **Regression:** no
- **Test:** -

### B-ACTIONS-005 - Pencil opens the right-panel word editor

- **Flow(s):** F-DRIVER-OPEN-EDIT-01
- **Composed by:** B-RIGHT-001
- **Trigger:** User clicks `edit-word-button-{l}-{w}`.
- **Preconditions:** The word cell for that word is present.
- **Observable output:** The click selects the word and shows `word-detail`
  inside `right-panel`. No word-edit modal is mounted.
- **Backend / side-effects:** Selection is client state. Later edits use the
  right-panel word routes.
- **Bad-state / error:** A missing word shows the panel's empty state. The
  click does not open a modal.
- **Tier(s):** A
- **Regression:** no
- **Test:** `tests/e2e/test_project_page_smoke.py::test_word_edit_dialog_lifecycle`

### B-ACTIONS-006 - Source folder dialog browses and applies source root

- **Flow(s):** F-SOURCE-ROOT-01
- **Composed by:** B-ROOT-006
- **Trigger:** User opens source folder dialog, browses/enters a path, and
  applies.
- **Preconditions:** Root or project chrome has a source-folder trigger.
- **Observable output:** Dialog initializes from projects config, lists
  filesystem entries, shows typed/current path, and remains open on validation
  failure.
- **Backend / side-effects:** Reads `/api/projects` and `/api/fs/ls`; applying
  posts `/api/projects/source-root` and rescans projects.
- **Bad-state / error:** Invalid/nonexistent path is rejected visibly and does
  not change the configured root.
- **Tier(s):** A+B
- **Regression:** no
- **Test:** -

### B-ACTIONS-007 - Hotkey help lists registry groups and closes safely

- **Flow(s):** F-HOTKEY-HELP-01
- **Composed by:** B-SHELL-004
- **Trigger:** User presses `?` or opens hotkey help through UI/store.
- **Preconditions:** App shell mounted.
- **Observable output:** Modal renders registered shortcuts grouped by scope and
  closes through Escape/Radix close affordances.
- **Backend / side-effects:** Client-only dialog state.
- **Bad-state / error:** Empty registry still renders a closable modal.
- **Tier(s):** A
- **Regression:** no
- **Test:** -

### B-ACTIONS-008 - Full and compact page actions keep parity

- **Flow(s):** F-PAGE-ACTIONS-01
- **Composed by:** B-PROJECT-004
- **Trigger:** User views page action bar or compact header actions.
- **Preconditions:** Project/page data loaded.
- **Observable output:** Busy disabling, edited-image gate, page/source/rotation
  badges, provenance tooltip, save/reload/rematch/export/OCR buttons match the
  available page actions.
- **Backend / side-effects:** Rendering only; button clicks delegate to the
  specific action records.
- **Bad-state / error:** Disabled actions remain visible enough for driver/UI
  contract without posting unavailable mutations.
- **Tier(s):** A
- **Regression:** no
- **Test:** -

### B-ACTIONS-009 - Load Page and Rematch GT confirm destructive changes

- **Flow(s):** F-PAGE-DESTRUCTIVE-01
- **Composed by:** B-ACTIONS-008
- **Trigger:** User clicks/hotkeys Load Page or Rematch GT and confirms.
- **Preconditions:** Project page loaded.
- **Observable output:** Confirmation opens; cancel leaves page unchanged;
  confirm disables action and refreshes page after success.
- **Backend / side-effects:** Load page or rematch endpoint mutates in-memory
  page state; selection resets where applicable.
- **Bad-state / error:** Failure shows recoverable error and keeps previous page
  data.
- **Tier(s):** A+B
- **Regression:** no
- **Test:** -

### B-ACTIONS-010 - Job-backed actions report progress and terminal state

- **Flow(s):** F-JOB-SSE-01
- **Composed by:** B-JOBS-001
- **Trigger:** User starts reload OCR, save project, refine, rotate, or export.
- **Preconditions:** Operation is enabled.
- **Observable output:** Job id/progress/busy overlay or action progress appears;
  terminal success invalidates affected queries and clears busy state.
- **Backend / side-effects:** Endpoint creates a JobRunner job and streams or
  polls progress.
- **Bad-state / error:** Terminal error displays toast/inline error and leaves
  previous page data intact.
- **Tier(s):** A+B
- **Regression:** no
- **Test:** -

### B-ACTIONS-011 - Notification stream maps backend events to visible toasts

- **Flow(s):** F-NOTIFICATIONS-01
- **Composed by:** B-JOBS-002
- **Trigger:** Backend emits notification queue events or client reconnects.
- **Preconditions:** App shell mounted.
- **Observable output:** Toast/test IDs such as `notification-{kind}-{id}`
  appear; replayed ring-buffer notifications are shown without duplicating
  dismissed state.
- **Backend / side-effects:** SSE subscribe/read/dismiss notification routes.
- **Bad-state / error:** Auto-save success can be filtered; failures remain
  visible.
- **Tier(s):** A+B
- **Regression:** no
- **Test:** -

### B-ACTIONS-012 - Toolbar grid maps cells to enabled actions

- **Flow(s):** F-TOOLBAR-GRID-01
- **Composed by:** B-DRIVER-003
- **Trigger:** Toolbar grid renders or user activates a cell.
- **Preconditions:** Project page loaded; selected scope may be empty/line/word.
- **Observable output:** Four-by-fourteen grid, stub cells, enabled states, and
  selected-scope derivation are visible to the driver contract.
- **Backend / side-effects:** Action cells delegate to mapped word/line/page
  endpoints where wired; stubs have no mutation.
- **Bad-state / error:** Delete-style actions require confirmation; disabled
  cells must not post.
- **Tier(s):** A
- **Regression:** no
- **Test:** -

### B-ACTIONS-013 - Toolbar style/component and Add Word rows mutate selection

- **Flow(s):** F-TOOLBAR-STYLE-ADD-01
- **Composed by:** B-ACTIONS-012, B-CANVAS-008
- **Trigger:** User applies style/component/clear or toggles Add Word.
- **Preconditions:** Selected words for style/component; page loaded for Add
  Word.
- **Observable output:** Style/component rows reflect enabled state and Add Word
  mode changes canvas affordance.
- **Backend / side-effects:** Posts word style/component mutations or toggles
  viewport add-word mode for subsequent canvas drag.
- **Bad-state / error:** No selection disables scoped style/component actions.
- **Tier(s):** A+B
- **Regression:** no
- **Test:** -

### B-ACTIONS-014 - Right-panel geometry drafts stay local until apply

- **Flow(s):** F-WORD-DIALOG-IMAGE-01
- **Composed by:** B-ACTIONS-005, B-RIGHT-003
- **Trigger:** User stages bbox, rebox, erase, or char-bbox edits on the
  selected word.
- **Preconditions:** `word-detail` is open for a word that has image data.
- **Observable output:** The section shows the pending draft and enables apply
  only when that draft is dirty.
- **Backend / side-effects:** Staging is local until apply.
- **Bad-state / error:** Reset or discard drops the local draft and posts
  nothing.
- **Tier(s):** A
- **Regression:** no
- **Test:** -

### B-ACTIONS-015 - Right-panel word edits keep a failed draft

- **Flow(s):** F-WORD-DIALOG-MUTATE-01
- **Composed by:** B-ACTIONS-005
- **Trigger:** User applies ground truth, a structural component, merge, split,
  delete, nudge, refine, erase pixels, or char bboxes from the mounted editor.
- **Preconditions:** `word-detail` is open for a selected word.
- **Observable output:** Success updates the detail. Failure leaves the draft
  in the panel.
- **Backend / side-effects:** Posts the right-panel word routes. Typography
  spans replaced character-range mutations, which are not a current write.
  The page query invalidates after success.
- **Bad-state / error:** A failed mutation leaves the pending draft in place.
- **Tier(s):** A+B
- **Regression:** no
- **Test:** -

### B-ACTIONS-016 - OCR config selection persists model and revision choices

- **Flow(s):** F-OCR-CONFIG-01
- **Composed by:** B-ACTIONS-001
- **Trigger:** User changes OCR model, rescans, revision, or related config and
  applies.
- **Preconditions:** OCR config modal open.
- **Observable output:** Current config fields update or save-error banner
  appears.
- **Backend / side-effects:** OCR config endpoint updates live server config;
  sidecar persistence is best-effort and failure tolerant.
- **Bad-state / error:** Sidecar save failure is reported/logged while live
  config can still apply.
- **Tier(s):** A+B
- **Regression:** no
- **Test:** -

### B-ACTIONS-017 - OCR config normalization and auto-rotation settings persist

- **Flow(s):** F-OCR-CONFIG-NORMALIZE-ROTATE-01
- **Composed by:** B-ACTIONS-001
- **Trigger:** User changes normalize/auto-rotate options and applies.
- **Preconditions:** OCR config modal open.
- **Observable output:** Availability probes, disabled/unavailable messaging,
  auto-rotate settings, and save-error banner reflect current state.
- **Backend / side-effects:** Posts OCR/text normalization config used by later
  OCR jobs.
- **Bad-state / error:** Missing rotation/normalization support disables or
  degrades controls without closing the modal.
- **Tier(s):** A+B
- **Regression:** no
- **Test:** -

### B-ACTIONS-018 - Export dialog options validate scope and output mode

- **Flow(s):** F-EXPORT-OPTIONS-01
- **Composed by:** B-ACTIONS-004
- **Trigger:** User edits export scope, style/component filters, output mode,
  or starts/cancels export.
- **Preconditions:** Export dialog open.
- **Observable output:** Mutually exclusive options, run history, and validation
  state update; cancel returns to project page.
- **Backend / side-effects:** Style list fetch and export job creation/cancel.
- **Bad-state / error:** Invalid options block submission and path traversal is
  rejected server-side.
- **Tier(s):** A+B
- **Regression:** no
- **Test:** -

### B-ACTIONS-019 - Save/load roundtrip preserves event-store page state

- **Flow(s):** F-SAVE-LOAD-ROUNDTRIP-01
- **Composed by:** B-ACTIONS-002
- **Trigger:** User saves, reloads page/project, or mutates a loaded page.
- **Preconditions:** Page has generated/current dirty state.
- **Observable output:** Save status and reloaded page data reflect current
  page-store state and page generation.
- **Backend / side-effects:** Save generation conflict detection,
  event-backed `LabelerEdited` persistence where page-store wiring is present,
  and Save Project partial failure handling.
- **Bad-state / error:** Generation conflict or partial save keeps affected page
  dirty and reports failure.
- **Tier(s):** A+B
- **Regression:** no
- **Test:** -

### B-ACTIONS-020 - Manual rotation action creates job and updates rotation badge

**Implementation reconciliation (2026-11-13).** The current source/test scope is recorded below.
The original acceptance fields remain after it; any stronger unimplemented expectation is retained, not waived.

- **Observed trigger:** Run manual rotate or auto-rotate-all from the mounted page actions.
- **Current behavior:** Jobs rotate source pixels, rerun OCR and persist aggregate rotation metadata.
  Auto rotation protects manual pages unless overwrite_manual is requested. Immutable book sources reject
  rotation. These are implemented effects, not plumbing stubs.
- **Additional evidence:** `tests/integration/test_rotate_job.py`, `test_auto_rotate_all_job.py`,
  `tests/e2e/test_rotate_parity.py`.

**Original acceptance fields:**

- **Flow(s):** F-ROTATE-PAGE-01
- **Composed by:** B-ACTIONS-010
- **Trigger:** User rotates clockwise, counter-clockwise, or 180 degrees.
- **Preconditions:** Project page loaded and rotation action enabled.
- **Observable output:** 202/job progress appears and rotation/source badge
  updates according to backend result.
- **Backend / side-effects:** Rotation job runs through job plumbing; image
  rotation/OCR rerun side effects are currently stubbed and tracked as unclear.
- **Bad-state / error:** Failed job leaves previous image/page data intact.
- **Tier(s):** A+B
- **Regression:** no
- **Test:** -

### B-ACTIONS-021 - Image drift recovery reloads instead of overwriting

- **Flow(s):** F-IMAGE-DRIFT-01
- **Composed by:** B-ACTIONS-002
- **Trigger:** Save detects source image drift.
- **Preconditions:** Page source image has changed since load.
- **Observable output:** Client reloads page and shows visible info/error state;
  it does not retry blind overwrite.
- **Backend / side-effects:** Save returns `409 image_drift`; page query reloads.
- **Bad-state / error:** No active implementation evidence was found; keep this
  record specified until product decision or implementation catches up.
- **Tier(s):** B
- **Regression:** no
- **Test:** -

## Known regressions

- B-ACTIONS-001 - OCR config trigger disappeared after HeaderBar controls were
  deprecated; #405 restored a real visible project-route trigger.

## Implementation reconciliation (2026-11-13)

PageActionsCompact is mounted and rotation is implemented. B-ACTIONS-021 remains an unimplemented
save-time `409 image_drift` refusal/recovery requirement. GET drift detection and ImageDriftBanner are
shipped; they do not satisfy that stronger requirement. See architecture 08 section 14.

## Adversarial Review

**Accepted finding:** Persistent right-panel editing superseded the standalone word dialog; current
action contracts must follow the visible replacement.

**Stage:** migration-time current-state review on 2026-07-13.

**Source:** an independent read-only reviewer compared this document with current
code, tests, architecture, and git history.

**Result:** the review accepted the finding above and used it to declare the
metadata status. Residual risks remain explicit here or in
`docs/context/intent-map.md`; deferred or blocked behavior is not claimed as
shipped.

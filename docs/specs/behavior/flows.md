# Cross-unit flows - pdomain-ocr-labeler-spa

## Agent Index

- **Kind:** behavior-flow-spec
- **Use with:** `/workspaces/ocr-container/docs/process/behavior-e2e-capture.md`
- **Purpose:** chain locked unit behavior records into cross-unit scenarios.

## Flows

### F-LABEL-SAVE-EXPORT-01 - Open project, edit a word, save, export

- **Units:** root -> project page -> canvas/drawer -> right panel -> page
  actions/export
- **Steps (record IDs in order):**
  1. B-ROOT-002 - open a project from the root screen.
  2. B-PROJECT-001 - project page loads the full labeling workspace.
  3. B-CANVAS-002 or B-DRAWER-002 - select a word by canvas or hierarchy.
  4. B-RIGHT-002 - edit GT text or tags on the selected word.
  5. B-ACTIONS-002 - save dirty page/project state.
  6. B-ACTIONS-004 - export the project.
- **Expected end state (UI + backend):** Project page remains usable; edited
  word data is persisted through the page store; export artifacts and manifest
  include the saved text/state.
- **Bad-state / error:** Save failure blocks export confidence: dirty state
  remains visible and export should not be used as proof of persisted edits.
- **Tier(s):** A+B
- **Regression:** no
- **Test:** -

### F-DRIVER-OPEN-EDIT-01 - Driver opens legacy route and reaches edit controls

- **Units:** driver contract -> project page -> hidden/visible controls -> word
  edit dialog
- **Steps (record IDs in order):**
  1. B-DRIVER-002 - legacy route resolves to canonical project page.
  2. B-DRIVER-001 - required driver test IDs are present or stubbed.
  3. B-ACTIONS-005 - word edit dialog can be opened for a word.
- **Expected end state (UI + backend):** Driver can still locate its stable
  selectors and open a real editable word workflow.
- **Bad-state / error:** Hidden stubs alone are insufficient: the flow fails if
  no visible or actionable path opens the dialog.
- **Tier(s):** A
- **Regression:** no
- **Test:** -

### F-SOURCE-ROOT-01 - Change source root and reopen project browser

- **Units:** root -> source folder dialog -> projects API -> root browser
- **Steps (record IDs in order):**
  1. B-ROOT-006 - open the source folder dialog.
  2. B-ACTIONS-006 - browse or type a source root and apply.
  3. B-ROOT-001 - project browser rerenders against the new root.
- **Expected end state (UI + backend):** Source root is updated and projects are
  rescanned from the new directory.
- **Bad-state / error:** Invalid root leaves previous root and visible projects
  unchanged.
- **Tier(s):** A+B
- **Regression:** no
- **Test:** -

### F-HOTKEY-HELP-01 - Open and close keyboard help

- **Units:** shell -> dialog store -> hotkey help modal
- **Steps (record IDs in order):**
  1. B-SHELL-004 or B-ACTIONS-007 - trigger hotkey help.
  2. B-ACTIONS-007 - render groups and close safely.
- **Expected end state (UI + backend):** User returns to the prior project
  surface without any backend mutation.
- **Bad-state / error:** Empty registry still yields a closable modal.
- **Tier(s):** A
- **Regression:** no
- **Test:** -

### F-PAGE-ACTIONS-01 - Use visible page action controls

- **Units:** project header/page actions -> dialogs/jobs/persistence
- **Steps (record IDs in order):**
  1. B-PROJECT-004 - header injects compact page actions.
  2. B-ACTIONS-008 - visible actions match availability.
  3. B-ACTIONS-002, B-ACTIONS-003, B-ACTIONS-004, or B-ACTIONS-010 - perform
     selected action.
- **Expected end state (UI + backend):** Action-specific state updates and the
  project page remains usable.
- **Bad-state / error:** Disabled actions do not post mutations.
- **Tier(s):** A+B
- **Regression:** no
- **Test:** -

### F-PAGE-DESTRUCTIVE-01 - Confirm page destructive actions

- **Units:** page actions -> confirm dialog -> mutation endpoint
- **Steps (record IDs in order):**
  1. B-ACTIONS-008 - destructive action is available.
  2. B-ACTIONS-009 - confirm/cancel behavior gates mutation.
- **Expected end state (UI + backend):** Confirmed action refreshes page data;
  canceled action leaves state unchanged.
- **Bad-state / error:** Failure leaves prior page data recoverable.
- **Tier(s):** A+B
- **Regression:** no
- **Test:** -

### F-JOB-SSE-01 - Run and observe a job-backed action

- **Units:** action trigger -> JobRunner -> job progress hook -> busy overlay
- **Steps (record IDs in order):**
  1. B-ACTIONS-010 - job-backed action starts.
  2. B-JOBS-001 - progress stream updates terminal state.
  3. B-JOBS-003 - busy overlay prevents duplicate mutation where applicable.
- **Expected end state (UI + backend):** Terminal success invalidates affected
  data and clears busy state.
- **Bad-state / error:** Terminal failure reports error and keeps previous page
  data intact.
- **Tier(s):** A+B
- **Regression:** no
- **Test:** -

### F-NOTIFICATIONS-01 - Backend notification reaches visible toast

- **Units:** backend notification queue -> SSE -> toast/live region
- **Steps (record IDs in order):**
  1. B-JOBS-002 - notification stream subscribes/replays.
  2. B-ACTIONS-011 - event becomes a visible toast.
- **Expected end state (UI + backend):** User can see/dismiss important
  notifications.
- **Bad-state / error:** Stream failure does not crash the shell.
- **Tier(s):** A+B
- **Regression:** no
- **Test:** -

### F-TOOLBAR-GRID-01 - Exercise toolbar grid contract

- **Units:** driver contract -> toolbar grid -> mapped action
- **Steps (record IDs in order):**
  1. B-ACTIONS-012 - grid renders cells and enabled states.
  2. B-ACTIONS-013 - selection-sensitive rows map to style/add-word behavior.
- **Expected end state (UI + backend):** Visible or stubbed toolbar cells match
  the documented driver/action contract.
- **Bad-state / error:** Stubs do not prove real behavior.
- **Tier(s):** A
- **Regression:** no
- **Test:** -

### F-TOOLBAR-STYLE-ADD-01 - Apply toolbar tags or add a word

- **Units:** toolbar grid -> canvas/right panel -> word mutation endpoints
- **Steps (record IDs in order):**
  1. B-ACTIONS-013 - choose style/component/clear or Add Word.
  2. B-CANVAS-008 or B-RIGHT-007 - mutate word data.
- **Expected end state (UI + backend):** Page payload reflects changed word tags
  or added empty word and remains dirty until save.
- **Bad-state / error:** No selection disables tag mutations.
- **Tier(s):** A+B
- **Regression:** no
- **Test:** -

### F-WORD-DIALOG-IMAGE-01 - Stage image edits in word dialog

- **Units:** word edit dialog -> word image canvas -> local draft
- **Steps (record IDs in order):**
  1. B-ACTIONS-005 - open the word edit dialog.
  2. B-ACTIONS-014 - stage image/geometry edits.
- **Expected end state (UI + backend):** Local draft shows staged edits until
  user applies or discards.
- **Bad-state / error:** Discard resets local draft without posting.
- **Tier(s):** A
- **Regression:** no
- **Test:** -

### F-WORD-DIALOG-MUTATE-01 - Apply word dialog mutation

- **Units:** word edit dialog -> word endpoints -> page query
- **Steps (record IDs in order):**
  1. B-ACTIONS-005 - open the word edit dialog.
  2. B-ACTIONS-015 - apply a mutation.
- **Expected end state (UI + backend):** Page data invalidates/refetches and
  dialog remains recoverable.
- **Bad-state / error:** Failure keeps draft open.
- **Tier(s):** A+B
- **Regression:** no
- **Test:** -

### F-OCR-CONFIG-01 - Change OCR model configuration

- **Units:** OCR config modal -> OCR config endpoint -> later OCR job
- **Steps (record IDs in order):**
  1. B-ACTIONS-001 - open OCR config.
  2. B-ACTIONS-016 - apply model/revision settings.
- **Expected end state (UI + backend):** Live server config changes and later
  OCR jobs read the updated config.
- **Bad-state / error:** Sidecar failure does not silently block live config.
- **Tier(s):** A+B
- **Regression:** no
- **Test:** -

### F-OCR-CONFIG-NORMALIZE-ROTATE-01 - Change normalization and rotation config

- **Units:** OCR config modal -> availability probes -> config endpoint
- **Steps (record IDs in order):**
  1. B-ACTIONS-001 - open OCR config.
  2. B-ACTIONS-017 - apply normalize/auto-rotate settings.
- **Expected end state (UI + backend):** Future OCR jobs use saved settings.
- **Bad-state / error:** Unavailable capability disables controls clearly.
- **Tier(s):** A+B
- **Regression:** no
- **Test:** -

### F-EXPORT-OPTIONS-01 - Configure and run export

- **Units:** export dialog -> export router -> export artifacts
- **Steps (record IDs in order):**
  1. B-ACTIONS-004 - open/start export.
  2. B-ACTIONS-018 - validate options and run/cancel export.
- **Expected end state (UI + backend):** Export artifacts and manifest match
  selected filters and mode.
- **Bad-state / error:** Invalid options or unsafe paths do not write artifacts.
- **Tier(s):** A+B
- **Regression:** no
- **Test:** -

### F-SAVE-LOAD-ROUNDTRIP-01 - Save and reload persisted page state

- **Units:** right panel/canvas -> save/load endpoints -> page store
- **Steps (record IDs in order):**
  1. B-RIGHT-002 or B-CANVAS-008 - create dirty state.
  2. B-ACTIONS-002 - save state.
  3. B-ACTIONS-019 - reload from persisted page-store state.
- **Expected end state (UI + backend):** Reloaded page reflects persisted data
  and generation state.
- **Bad-state / error:** Generation conflicts preserve dirty state.
- **Tier(s):** A+B
- **Regression:** no
- **Test:** -

### F-ROTATE-PAGE-01 - Rotate page through job plumbing

- **Units:** page actions -> rotate job -> page badge/image data
- **Steps (record IDs in order):**
  1. B-ACTIONS-020 - start manual rotation.
  2. B-JOBS-001 - observe terminal state.
- **Expected end state (UI + backend):** Current implementation guarantees job
  plumbing; real image/OCR side effects remain unclear.
- **Bad-state / error:** Failed rotation leaves previous page data intact.
- **Tier(s):** A+B
- **Regression:** no
- **Test:** -

### F-IMAGE-DRIFT-01 - Recover from source image drift

- **Units:** save endpoint -> page query -> notification surface
- **Steps (record IDs in order):**
  1. B-ACTIONS-002 - attempt save.
  2. B-ACTIONS-021 - handle image drift.
- **Expected end state (UI + backend):** Client reloads current page instead of
  overwriting drifted source data.
- **Bad-state / error:** Current implementation evidence is incomplete.
- **Tier(s):** B
- **Regression:** no
- **Test:** -

### F-GLYPH-REVIEW-01 - Review and persist glyph annotations

- **Units:** glyph chips -> glyph panel/bulk dialog -> glyph endpoints
- **Steps (record IDs in order):**
  1. B-GLYPH-001 - glyph state is visible.
  2. B-GLYPH-002, B-GLYPH-003, or B-GLYPH-004 - user reviews glyph data.
  3. B-GLYPH-005 - page-state persistence preserves review state.
- **Expected end state (UI + backend):** Human glyph annotations survive reload
  with null/empty/populated states intact.
- **Bad-state / error:** Production panel mount and frontend POST wiring remain
  unclear.
- **Tier(s):** A+B
- **Regression:** no
- **Test:** -

---
kind: spec
status: active
owner: maintainers
created: 2026-06-01
last_verified: 2026-07-13
---

# Behavior unit spec - Right panel detail views

- **Unit type:** component
- **Address:** `RightPanel`, `WordDetail`, `LineDetail`, `BlockDetail`,
  action sections, palettes, Unicode picker
- **UI definition:** none - existing stable UI documented in
  `docs/architecture/26-right-panel-detail.md`,
  `27-right-panel-sections.md`, and `28-palettes-pickers.md`
- **Parent unit(s):** `screen-project-page.md`, `component-canvas.md`,
  `component-drawer-worklist.md`
- **Child unit(s):** dialog-store confirm dialog, word mutation hooks
- **Shared unit:** yes
- **Implementation:** `frontend/src/components/shell/RightPanel.tsx`,
  `frontend/src/components/right-panel/*.tsx`,
  `frontend/src/components/right-panel/sections/*.tsx`,
  `frontend/src/hooks/useWordMutations.ts`, `useLineMutations.ts`
- **Backend / collaborators touched:** word GT/style/component/validate/delete
  endpoints, line validation/merge endpoints, paragraph patch endpoint, char
  ranges/char bboxes mutation endpoints

## Behavior records

### B-RIGHT-001 - Word selection renders editable word detail

- **Flow(s):** F-LABEL-SAVE-EXPORT-01
- **Composed by:** B-CANVAS-002, B-DRAWER-002
- **Trigger:** Selection store level becomes `word`.
- **Preconditions:** Page payload contains the selected word.
- **Observable output:** `word-detail` renders header, preview, OCR/GT compare,
  style/component palettes, edit sections, and sticky footer for that word.
- **Backend / side-effects:** No write on render; data comes from
  `PagePayload.line_matches`.
- **Bad-state / error:** Missing selected word shows "No word selected." or a
  stable empty state instead of throwing.
- **Tier(s):** A
- **Regression:** no
- **Test:** `tests/e2e/test_image_click_selection.py::test_click_word_bbox_on_image_opens_word_detail`

### B-RIGHT-002 - Word GT/style/component edits update page payload and dirty state

- **Flow(s):** F-LABEL-SAVE-EXPORT-01
- **Composed by:** B-RIGHT-001
- **Trigger:** User edits `ocr-gt-input`, clicks a style chip, or clicks a
  component chip.
- **Preconditions:** A word is selected.
- **Observable output:** Edited GT text or chip state updates after success;
  page dirty/save status indicates unsaved changes.
- **Backend / side-effects:** Corresponding word mutation endpoint updates
  server page state, performs best-effort event-store persistence where wired,
  and returns/refetches `PagePayload`.
- **Bad-state / error:** Backend rejection leaves prior text/chip state visible
  or restores it after optimistic update; user sees an error state/toast.
- **Tier(s):** A
- **Regression:** no
- **Test:** -

### B-RIGHT-003 - Word geometry sections apply explicit bbox/erase/char changes

- **Flow(s):** -
- **Composed by:** B-RIGHT-001
- **Trigger:** User applies BBox, Rebox, Erase Pixels, Char Ranges, or Char
  Fixer changes.
- **Preconditions:** A word is selected; operation-specific draft is dirty.
- **Observable output:** Apply buttons enable only when dirty; successful apply
  updates bbox/readout/canvas/chip display; reset restores current page data.
- **Backend / side-effects:** Mutation posts to rebox, erase-pixels,
  char-ranges, or char-bboxes endpoint; page data is invalidated/refetched;
  page remains dirty until Save Page.
- **Bad-state / error:** Unavailable refine/erase displays the documented
  not-available message; failed mutation keeps the draft recoverable.
- **Tier(s):** A+B for erase/refine paths, A otherwise
- **Regression:** no
- **Test:** -

### B-RIGHT-004 - Line and block detail mutate their own scope

- **Flow(s):** -
- **Composed by:** B-DRAWER-002
- **Trigger:** User selects a line or block/para and clicks detail actions.
- **Preconditions:** Page payload contains the selected line or block/para.
- **Observable output:** `line-detail` or `block-detail` is visible; validate,
  merge, density, layout, and item-view controls update their local state and
  disabled/enabled labels as documented.
- **Backend / side-effects:** Line actions call validate/merge endpoints;
  block layout saves patch paragraph/layout state; page data invalidates and
  durable persistence is handled by Save Page where applicable.
- **Bad-state / error:** First-line merge-prev and last-line merge-next are
  disabled; mutation errors render inline and do not corrupt selection.
- **Tier(s):** A
- **Regression:** no
- **Test:** -

### B-RIGHT-005 - Word header/footer navigate and perform destructive actions

- **Flow(s):** F-LABEL-SAVE-EXPORT-01
- **Composed by:** B-RIGHT-001
- **Trigger:** User clicks prev/next, Validate, Skip, or Delete.
- **Preconditions:** A word is selected.
- **Observable output:** Header identity/pager and sticky footer state update;
  destructive delete opens confirmation where required.
- **Backend / side-effects:** Prev/next walk selection; validate/skip/delete
  post the corresponding word mutation and invalidate page data.
- **Bad-state / error:** Edge navigation is disabled; cancel/failure does not
  remove the word.
- **Tier(s):** A
- **Regression:** no
- **Test:** -

### B-RIGHT-006 - OCR/GT compare supports edit, copy, and Unicode insert

- **Flow(s):** F-LABEL-SAVE-EXPORT-01
- **Composed by:** B-RIGHT-001
- **Trigger:** User blurs/commits GT, clicks copy OCR, or inserts from Unicode
  picker.
- **Preconditions:** A word is selected.
- **Observable output:** GT input changes and picker toggles/inserts at cursor.
- **Backend / side-effects:** GT commit posts `words/{li}/{wi}/gt`.
- **Bad-state / error:** Unchanged blur no-ops; backend rejection keeps input
  recoverable.
- **Tier(s):** A
- **Regression:** no
- **Test:** -

### B-RIGHT-007 - Whole-word style and component palettes persist chips

- **Flow(s):** F-LABEL-SAVE-EXPORT-01
- **Composed by:** B-RIGHT-001
- **Trigger:** User clicks a style or component chip.
- **Preconditions:** A word is selected.
- **Observable output:** Chip state reflects refetched server payload.
- **Backend / side-effects:** Posts style/component word mutation; page remains
  dirty until save.
- **Bad-state / error:** Mixed state is ignored in word context; failed mutation
  leaves persisted state visible.
- **Tier(s):** A
- **Regression:** no
- **Test:** -

### B-RIGHT-008 - BBox typed, nudge, and refine actions update draft bbox

- **Flow(s):** -
- **Composed by:** B-RIGHT-003
- **Trigger:** User edits coordinates, nudges, refines, crops, or resets.
- **Preconditions:** A word is selected.
- **Observable output:** Draft/readout changes; reset restores source bbox.
- **Backend / side-effects:** Apply posts rebox mutation.
- **Bad-state / error:** Invalid input or backend rejection keeps draft
  recoverable.
- **Tier(s):** A
- **Regression:** no
- **Test:** -

### B-RIGHT-009 - Rebox mini-canvas modes apply or reset bbox draft

- **Flow(s):** -
- **Composed by:** B-RIGHT-003
- **Trigger:** User switches Snap/Draw/Pan, zooms, drags, applies, or resets.
- **Preconditions:** A word is selected.
- **Observable output:** Mini-canvas bbox/summary changes; Apply is enabled only
  when dirty.
- **Backend / side-effects:** Apply posts rebox mutation.
- **Bad-state / error:** Apply disabled when clean; zoom is clamped.
- **Tier(s):** A
- **Regression:** no
- **Test:** -

### B-RIGHT-010 - Erase Pixels gates capability and applies queued ops

- **Flow(s):** -
- **Composed by:** B-RIGHT-003
- **Trigger:** User adds brush/lasso/rect erase ops and applies.
- **Preconditions:** A word is selected; erase/refine capability probe has run.
- **Observable output:** Fallback or full UI appears; ops list and apply state
  update.
- **Backend / side-effects:** Apply posts sequential erase-pixels mutations.
- **Bad-state / error:** Unavailable capability shows message; failed apply
  preserves queued ops and reports recoverably.
- **Tier(s):** A+B
- **Regression:** no
- **Test:** -

### B-RIGHT-011 - Structure merge, gap, and split mutate word structure

- **Flow(s):** -
- **Composed by:** B-RIGHT-003
- **Trigger:** User merges previous/next, commits gap, or splits word.
- **Preconditions:** A word is selected and required neighbor/text exists.
- **Observable output:** Neighbor cards, merge confirm, split label, and gap
  readout update.
- **Backend / side-effects:** Posts merge, next-word rebox, or split mutation.
- **Bad-state / error:** Missing neighbor disables relevant controls; cancel is
  a no-op.
- **Tier(s):** A
- **Regression:** no
- **Test:** -

### B-RIGHT-012 - CharRanges add, edit, delete, and persist ranges

- **Flow(s):** -
- **Composed by:** B-RIGHT-003
- **Trigger:** User selects chars, adds range, edits kind/style/component, or
  deletes a range.
- **Preconditions:** A word is selected.
- **Observable output:** Pending range, glyph preview, chips, and overlap badge
  update.
- **Backend / side-effects:** Full replacement posts to char-ranges endpoint.
- **Bad-state / error:** Empty OCR disables pending add; invalid POST keeps UI
  recoverable.
- **Tier(s):** A
- **Regression:** no
- **Test:** -

### B-RIGHT-013 - CharFixer edits GT cells and char bboxes

- **Flow(s):** -
- **Composed by:** B-RIGHT-003
- **Trigger:** User edits per-char GT, inserts Unicode, adjusts char bbox, and
  applies.
- **Preconditions:** A word is selected.
- **Observable output:** Mismatch cells, selected bbox detail, and dirty apply
  state update.
- **Backend / side-effects:** GT posts through word GT mutation; char bbox apply
  posts char-bboxes mutation data that is surfaced on refreshed page payloads.
- **Bad-state / error:** Empty OCR hides canvas; failed char-bbox save keeps
  Apply enabled and shows error.
- **Tier(s):** A
- **Regression:** no
- **Test:** -

### B-RIGHT-014 - LineDetail supports tabs, GT, validation, merge, and bulk bar

- **Flow(s):** -
- **Composed by:** B-DRAWER-004
- **Trigger:** User selects line, switches tabs/density, commits GT, validates,
  merges, or uses word bulk controls.
- **Preconditions:** A line is selected.
- **Observable output:** Line/words tabs, counts, cards/rows, and bulk bar
  reflect state.
- **Backend / side-effects:** Posts line GT, validate-batch, or line merge.
- **Bad-state / error:** Missing line shows stable empty state; first-line
  merge-prev disabled; Escape reverts GT draft.
- **Tier(s):** A
- **Regression:** no
- **Test:** -

### B-RIGHT-015 - Block and paragraph detail support layout and item navigation

- **Flow(s):** -
- **Composed by:** B-DRAWER-002
- **Trigger:** User selects block/paragraph, saves layout, or clicks flat/tree
  items.
- **Preconditions:** Selected block or paragraph exists.
- **Observable output:** Tabs, layout chips, preview, and item groups render;
  item clicks move selection.
- **Backend / side-effects:** Layout save patches paragraph state; item clicks
  mutate selection only.
- **Bad-state / error:** Missing block/paragraph shows empty state; failed patch
  shows inline error.
- **Tier(s):** A
- **Regression:** no
- **Test:** -

## Known regressions

- None captured yet.

## Adversarial Review

**Accepted finding:** The right panel is the shipped editor replacement; mixed-selection and
error-state coverage remain the main residual risks.

**Stage:** migration-time current-state review on 2026-07-13.

**Source:** an independent read-only reviewer compared this document with current
code, tests, architecture, and git history.

**Result:** the review accepted the finding above and used it to declare the
metadata status. Residual risks remain explicit here or in
`docs/context/intent-map.md`; deferred or blocked behavior is not claimed as
shipped.

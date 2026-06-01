# Behavior unit spec - Canvas and image viewport

- **Unit type:** component
- **Address:** `PageImageCanvas`, `BBoxOverlay`, image-viewport controls
- **UI definition:** none - existing stable UI documented in
  `docs/architecture/04-image-viewport.md`, `21-konva-renderer.md`,
  `22-page-surface-wireup.md`
- **Parent unit(s):** `screen-project-page.md`, `component-studio-shell.md`
- **Child unit(s):** right panel, page action toolbar
- **Shared unit:** yes
- **Implementation:** `frontend/src/components/PageImageCanvas.tsx`,
  `frontend/src/components/BBoxOverlay.tsx`,
  `frontend/src/components/ImageTabsHeader.tsx`,
  `frontend/src/stores/viewport-store.ts`,
  `frontend/src/stores/selection-store.ts`
- **Backend / collaborators touched:** page payload image URL, selection state,
  word add/rebox/erase endpoints

## Behavior records

### B-CANVAS-001 - Canvas renders page image and bbox overlays

- **Flow(s):** F-LABEL-SAVE-EXPORT-01
- **Composed by:** B-PROJECT-001
- **Trigger:** Project page receives a successful page payload.
- **Preconditions:** Page image and encoded dimensions are available.
- **Observable output:** `image-viewport` and canvas are visible; overlay
  layers reflect paragraph, line, word, and current selection visibility prefs.
- **Backend / side-effects:** Page image loads from `/image-cache`; no mutation
  occurs.
- **Bad-state / error:** Missing image URL leaves the viewport empty/error
  state but the rest of the project page remains usable.
- **Tier(s):** A
- **Regression:** no
- **Test:** `tests/e2e/test_project_page_smoke.py::test_project_page_loads_with_tiny_fixture`

### B-CANVAS-002 - Clicking a word bbox selects the word and opens detail

- **Flow(s):** F-LABEL-SAVE-EXPORT-01
- **Composed by:** B-RIGHT-001
- **Trigger:** User clicks inside a word bbox on `image-viewport`.
- **Preconditions:** Word overlay is visible and the click hits a word bbox.
- **Observable output:** Word selection highlight appears; `word-detail` shows
  the clicked line/word identity.
- **Backend / side-effects:** Selection store changes client-side; no backend
  write occurs until a detail-panel action is used.
- **Bad-state / error:** Click outside every bbox clears or preserves selection
  according to current mode without navigating away or blanking the page.
- **Tier(s):** A
- **Regression:** no
- **Test:** `tests/e2e/test_image_click_selection.py::test_click_word_bbox_on_image_opens_word_detail`

### B-CANVAS-003 - Zoom, fit, and layer controls change viewport state only

- **Flow(s):** -
- **Composed by:** -
- **Trigger:** User clicks `zoom-fit-button`, `zoom-100-button`, layer
  checkboxes, or selection-mode radios.
- **Preconditions:** Project page is loaded.
- **Observable output:** Zoom/layer/mode visual state updates; hidden layers no
  longer render their bboxes; selection mode controls which level is selected.
- **Backend / side-effects:** Zustand UI prefs/viewport store update; no
  backend write occurs.
- **Bad-state / error:** Repeated 100% or fit clicks are idempotent; invalid
  stored prefs fall back to default visible layers and word selection mode.
- **Tier(s):** A
- **Regression:** no
- **Test:** -

### B-CANVAS-004 - Add word and erase modes expose canvas mutation affordances

- **Flow(s):** -
- **Composed by:** B-DRAWER-003, B-RIGHT-001
- **Trigger:** User toggles add-word or erase mode and drags a rectangle on
  the canvas.
- **Preconditions:** Project page loaded; mode is active; drag rectangle has
  non-zero area.
- **Observable output:** Mode-specific cursor/preview affordance appears. The
  visible project-page wiring for posting these canvas mutations is unresolved;
  component-level and backend behavior are captured in B-CANVAS-008 and
  B-CANVAS-009.
- **Backend / side-effects:** Intended backend mutations are word add and erase
  endpoints; current project-page canvas wiring may not call them directly.
- **Bad-state / error:** Zero-area drag or backend rejection shows no new word,
  no page mutation, and leaves the user in a recoverable mode.
- **Tier(s):** A+B where real image mutation is exercised
- **Regression:** no
- **Test:** -

### B-CANVAS-005 - Drag box selection applies replace, remove, or toggle

- **Flow(s):** F-LABEL-SAVE-EXPORT-01
- **Composed by:** B-RIGHT-001, B-DRAWER-002
- **Trigger:** User drags a rectangle in select mode.
- **Preconditions:** Page loaded; target selection mode is paragraph, line,
  word, or block.
- **Observable output:** A dashed drag rectangle appears during drag; matching
  bboxes become selected or highlighted after mouseup.
- **Backend / side-effects:** Intended call is
  `POST /api/projects/{pid}/pages/{idx}/selection` with replace/remove/toggle;
  selection generation bumps server-side.
- **Bad-state / error:** Tiny drag does nothing; 404/422 leaves existing
  selection and page data usable.
- **Tier(s):** A+B
- **Regression:** no
- **Test:** -

### B-CANVAS-006 - Selection overlays render selected bboxes defensively

- **Flow(s):** F-LABEL-SAVE-EXPORT-01
- **Composed by:** B-CANVAS-002, B-CANVAS-005
- **Trigger:** Page payload or selection store contains selected paragraph,
  line, word, or block indices.
- **Preconditions:** Page payload has bbox data for the selected level.
- **Observable output:** Selection layer renders selected bboxes with emphasis;
  invalid or out-of-range indices are skipped.
- **Backend / side-effects:** None beyond reading page payload and UI store.
- **Bad-state / error:** Empty/null page data renders zero overlays without
  crashing.
- **Tier(s):** A
- **Regression:** no
- **Test:** -

### B-CANVAS-007 - Rebox mode replaces a word bbox from canvas drag

- **Flow(s):** -
- **Composed by:** B-RIGHT-003
- **Trigger:** User starts rebox for a word and drags a new rectangle.
- **Preconditions:** Word selected; viewport mode is `rebox`; pending target
  identifies line and word.
- **Observable output:** Rebox preview appears; successful mutation updates the
  bbox and returns the viewport to select mode.
- **Backend / side-effects:** `POST .../words/{line}/{word}/rebox` bumps page
  generation and writes cached envelope best-effort.
- **Bad-state / error:** Escape/cancel or tiny drag sends no POST; rejected bbox
  leaves prior bbox intact.
- **Tier(s):** A+B
- **Regression:** no
- **Test:** -

### B-CANVAS-008 - Add Word mode creates a new empty word from drag

- **Flow(s):** F-LABEL-SAVE-EXPORT-01
- **Composed by:** B-DRAWER-003, B-RIGHT-001
- **Trigger:** User activates Add Word and drags a rectangle.
- **Preconditions:** Page loaded; viewport mode is `add-word`.
- **Observable output:** New empty word appears in the nearest line/detail data;
  Add Word remains active for repeated additions where the component is wired.
- **Backend / side-effects:** `POST .../words/add` with `{bbox, text: ""}`
  bumps page generation and writes cached envelope best-effort.
- **Bad-state / error:** Tiny drag sends no mutation; backend rejection shows a
  recoverable error and no new word.
- **Tier(s):** A+B
- **Regression:** no
- **Test:** -

### B-CANVAS-009 - Erase mode erases pixels from a drag rectangle

- **Flow(s):** -
- **Composed by:** B-RIGHT-003
- **Trigger:** User activates Erase and drags an erase rectangle.
- **Preconditions:** Page loaded; erase mode active; a word/image target is
  available.
- **Observable output:** Erase preview appears during drag; page image/data
  refreshes after success.
- **Backend / side-effects:** Current backend route is word-anchored
  `POST .../words/{line}/{word}/erase-pixels`; page generation bumps and cached
  envelope is written.
- **Bad-state / error:** Missing image, bad word target, or rejected bbox shows
  a recoverable mutation error.
- **Tier(s):** A+B
- **Regression:** no
- **Test:** -

### B-CANVAS-010 - Viewport hotkeys change canvas state

- **Flow(s):** -
- **Composed by:** -
- **Trigger:** User presses Escape or viewport shortcut keys for target/layer,
  erase, or add mode.
- **Preconditions:** Project page/canvas mounted and no modal/input owns the
  key event.
- **Observable output:** Layers toggle, selection mode changes, erase/add modes
  toggle, and Escape clears transient drag/selection state.
- **Backend / side-effects:** UI stores only; no backend write.
- **Bad-state / error:** Modal/input contexts suppress canvas hotkeys.
- **Tier(s):** A
- **Regression:** no
- **Test:** -

### B-CANVAS-011 - Zoom and fit preserve bbox coordinate correctness

- **Flow(s):** -
- **Composed by:** B-CANVAS-002
- **Trigger:** User uses Fit/100% zoom or clicks bboxes while fit-scaled.
- **Preconditions:** Canvas mounted with encoded dimensions and bbox overlays.
- **Observable output:** Zoom active state changes and bbox clicks still hit the
  correct word under internal scaling.
- **Backend / side-effects:** `viewportStore.canvasZoom` only; no backend write.
- **Bad-state / error:** Empty viewport renders no zoom controls.
- **Tier(s):** A
- **Regression:** yes
- **Test:** -

### B-CANVAS-012 - Layer and mismatch controls alter overlay visibility

- **Flow(s):** -
- **Composed by:** -
- **Trigger:** User toggles layer controls or mismatches-only control.
- **Preconditions:** Page loaded with word match statuses.
- **Observable output:** Hidden layers stop rendering; exact/validated words dim
  when mismatches-only is active.
- **Backend / side-effects:** UI prefs only; no backend write.
- **Bad-state / error:** Repeated toggles are idempotent and recoverable.
- **Tier(s):** A
- **Regression:** no
- **Test:** -

### B-CANVAS-013 - Large overlay pages remain responsive during drag

- **Flow(s):** -
- **Composed by:** B-CANVAS-001, B-CANVAS-005
- **Trigger:** User drags on a page with thousands of bbox rects.
- **Preconditions:** Synthetic or real page has high bbox count.
- **Observable output:** Drag remains responsive within the performance budget.
- **Backend / side-effects:** None.
- **Bad-state / error:** Performance failure is actionable and does not corrupt
  page state.
- **Tier(s):** B/perf
- **Regression:** no
- **Test:** -

## Known regressions

- None captured yet.

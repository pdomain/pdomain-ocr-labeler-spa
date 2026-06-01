# Behavior unit spec - Drawer worklist and hierarchy

- **Unit type:** component
- **Address:** `Worklist`, `Hierarchy`, `BulkActions`
- **UI definition:** none - existing stable UI documented in
  `docs/architecture/25-drawer-worklist.md`
- **Parent unit(s):** `screen-project-page.md`, `component-studio-shell.md`
- **Child unit(s):** right panel, export job
- **Shared unit:** yes
- **Implementation:** `frontend/src/components/drawer/Worklist.tsx`,
  `Hierarchy.tsx`, `BulkActions.tsx`, `frontend/src/stores/worklist-store.ts`,
  `frontend/src/stores/selection-store.ts`
- **Backend / collaborators touched:** line validation endpoint, reload OCR
  job endpoint, export job endpoint, `useJobProgress`

## Behavior records

### B-DRAWER-001 - Worklist filter and sort reshape the visible queue

- **Flow(s):** -
- **Composed by:** B-PROJECT-001
- **Trigger:** User clicks Worklist count chips or changes the sort select.
- **Preconditions:** Page payload has at least one line.
- **Observable output:** `worklist-queue` rows update; active chip has
  `data-active="true"`; empty filtered result shows "No lines match current
  filter".
- **Backend / side-effects:** Filtering/sorting is client-side over
  `PagePayload.line_matches`; no API request or file write occurs.
- **Bad-state / error:** A page with zero lines renders the empty queue state
  without crashing.
- **Tier(s):** A
- **Regression:** no
- **Test:** -

### B-DRAWER-002 - Hierarchy selection opens the matching right-panel detail

- **Flow(s):** F-LABEL-SAVE-EXPORT-01
- **Composed by:** B-PROJECT-001
- **Trigger:** User opens `drawer-tab-hierarchy` and clicks a paragraph, line,
  or word node.
- **Preconditions:** Page payload contains hierarchy data.
- **Observable output:** Clicked node gains `data-selected="true"`; word nodes
  display `word-detail`, line nodes display `line-detail`, and paragraph/block
  nodes display `block-detail`; project page remains mounted.
- **Backend / side-effects:** Selection store mutates in memory; no API request
  occurs until the user performs a mutation in the right panel.
- **Bad-state / error:** Null paragraph nodes are selectable visually but do
  not mutate selection; the page does not go blank.
- **Tier(s):** A
- **Regression:** no
- **Test:** `tests/e2e/test_image_click_selection.py::test_click_word_in_hierarchy_opens_word_detail_without_blank_page`

### B-DRAWER-003 - Bulk actions operate on selected worklist lines

- **Flow(s):** -
- **Composed by:** -
- **Trigger:** User selects multiple worklist lines and clicks a BulkActions
  button.
- **Preconditions:** `worklistStore.selectedIds` is non-empty.
- **Observable output:** `bulk-actions` is present; count/clear appear only
  when lines are selected; mutating actions show job progress or clear selection
  on success.
- **Backend / side-effects:** Mark reviewed posts validate-batch for selected
  line indices; re-run match posts reload OCR and tracks a job; export filtered
  posts export and tracks a job.
- **Bad-state / error:** Backend failure leaves selection intact and shows an
  error toast/inline job error; no unrelated lines are mutated.
- **Tier(s):** A+B for reload/export, A for validate
- **Regression:** no
- **Test:** -

### B-DRAWER-004 - Worklist rows render evidence and open line detail

- **Flow(s):** F-LABEL-SAVE-EXPORT-01
- **Composed by:** B-RIGHT-004
- **Trigger:** User clicks `worklist-row-{lineIndex}`.
- **Preconditions:** A visible row exists.
- **Observable output:** Row gains selected state; right panel/selection changes
  to line detail; OCR/GT diff, confidence, and status evidence are visible.
- **Backend / side-effects:** `worklistStore.selectedLineIndex` and
  `selectionStore.selectLine`; no API.
- **Bad-state / error:** A filtered-out selected row is not shown as selected.
- **Tier(s):** A
- **Regression:** no
- **Test:** -

### B-DRAWER-005 - Worklist checkboxes manage bulk selection only

- **Flow(s):** -
- **Composed by:** B-DRAWER-003
- **Trigger:** User clicks `worklist-row-checkbox-{lineIndex}`.
- **Preconditions:** Visible row exists.
- **Observable output:** Checkbox checked state changes and BulkActions count
  updates.
- **Backend / side-effects:** `worklistStore.toggle(lineIndex)` only.
- **Bad-state / error:** Checkbox click must not navigate to line detail.
- **Tier(s):** A
- **Regression:** no
- **Test:** -

### B-DRAWER-006 - BulkActions supports selection and page-level actions

- **Flow(s):** -
- **Composed by:** B-JOBS-001
- **Trigger:** User clicks clear, mark reviewed, re-run match, or export.
- **Preconditions:** Worklist mounted; selected count may be zero.
- **Observable output:** Mark reviewed is disabled with count 0; page-level
  re-run/export actions remain available; selected count and clear state update.
- **Backend / side-effects:** Validate-batch clears selected rows on success;
  reload/export create or track jobs.
- **Bad-state / error:** Failed fetch shows toast and preserves selection.
- **Tier(s):** A+B
- **Regression:** no
- **Test:** -

### B-DRAWER-007 - Hierarchy filters and node count reshape visible tree

- **Flow(s):** -
- **Composed by:** B-DRAWER-002
- **Trigger:** User clicks `hierarchy-filter-*`.
- **Preconditions:** Hierarchy has page data.
- **Observable output:** Active pill changes, visible nodes are limited by kind,
  and node count reflects the visible flat tree.
- **Backend / side-effects:** Component-local filter state only.
- **Bad-state / error:** No page data renders a stable empty state.
- **Tier(s):** A
- **Regression:** no
- **Test:** -

### B-DRAWER-008 - Hierarchy expand, collapse, and keyboard navigation select nodes

- **Flow(s):** -
- **Composed by:** B-DRAWER-002
- **Trigger:** User clicks a node, presses Enter/Space, or uses Arrow keys.
- **Preconditions:** Hierarchy has visible nodes.
- **Observable output:** Branches reveal/hide children; selected node gets
  selected state; right panel changes to matching detail.
- **Backend / side-effects:** Selection store via canonical select helpers.
- **Bad-state / error:** Boundary ArrowUp/Down is a no-op.
- **Tier(s):** A
- **Regression:** no
- **Test:** -

### B-DRAWER-009 - Hierarchy block layer renders when block index exists

- **Flow(s):** -
- **Composed by:** B-DRAWER-002
- **Trigger:** Page payload includes numeric `block_index`.
- **Preconditions:** Hierarchy mounted.
- **Observable output:** Top-level block nodes and optional block filter appear;
  without blocks, paragraph-root behavior remains.
- **Backend / side-effects:** Selecting block calls `selectBlock`; no API.
- **Bad-state / error:** Mixed/null block lines fall under the synthetic
  unsorted block grouping.
- **Tier(s):** A
- **Regression:** no
- **Test:** -

## Known regressions

- None captured yet.

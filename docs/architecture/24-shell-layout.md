---
kind: architecture
status: built
owner: maintainers
created: 2026-05-16
last_verified: 2026-11-13
---

# 24 — Studio Shell / Layout

The mounted workbench uses AppShell chrome, WorkspaceToolbar and ProjectPage's body grid. StudioShell
remains a tested standalone primitive; its existence does not mean ProjectPage mounts it.

## Shared shell and local ownership

App owns the header, suite integration and shared shell slots. ProjectPage supplies the document canvas,
text/worklist views and local right-panel frame. The previous D-047/D-048 ownership decisions remain in
the ADR log. The 2026-11-11 comparison chose no extraction of that local frame; owner-review caveats in
the roadmap remain unchanged.

## Search, rail and drawer

QuickSearch is editable. It writes worklistStore.searchQuery; Worklist filters OCR or GT by a
case-insensitive substring before sorting. Escape clears and blurs. The search keycap focuses the input;
the rail Hotkeys button opens help.

Rail Bulk opens the Worklist drawer. View/region map to viewport select, annotate to add-word and erase
to erase; region gestures are dispatched by the canvas adapter. Shift shortcut collisions remain owned
by viewport handlers. Drawer tabs are Worklist, Hierarchy, Text, Queue and History. ProjectPage supplies
nonexact-or-unvalidated Worklist counts, total Hierarchy lines and total undecided Queue items.

Optional block hierarchy exists. Breadcrumb still displays the raw block identifier rather than a
1-based Block N label. Drawer state is currently in-memory; browser-local persistence and invalid-tab
fallback expectations remain explicit behavior-contract gaps, not delivered features.

## 6. data-testid contract

| testid | element | description |
|---|---|---|
| `studio-shell` | div | Top-level grid container |
| `studio-shell-header` | div | Header zone (hidden when `headerHeight=0`) |
| `studio-shell-rail` | div | Rail zone |
| `studio-shell-drawer` | div | Drawer zone; `data-collapsed="true"` when collapsed |
| `studio-shell-canvas` | div | Main canvas zone |
| `studio-shell-right` | div | Right panel zone |
| `rail` | div | 64px rail container |
| `rail-mode-view` | button | View mode card |
| `rail-mode-region` | button | Region mode card |
| `rail-mode-annotate` | button | Annotate mode card |
| `rail-mode-erase` | button | Erase mode card |
| `rail-target-block` | button | Block target cell |
| `rail-target-para` | button | Para target cell |
| `rail-target-line` | button | Line target cell |
| `rail-target-word` | button | Word target cell |
| `rail-bulk-button` | button | Opens Worklist drawer |
| `rail-hotkeys-button` | button | Opens hotkey help dialog |
| `breadcrumb` | div | Breadcrumb container |
| `breadcrumb-chip-root` | button | "Project" root chip |
| `breadcrumb-chip-block` | button | Block-level chip (when in path) |
| `breadcrumb-chip-para` | button | Para-level chip (when in path) |
| `breadcrumb-chip-line` | button | Line-level chip (when in path) |
| `breadcrumb-chip-word` | button | Word-level chip (when in path) |
| `quick-search` | div | Quick search container |
| `quick-search-input` | input | Editable Worklist text search |
| `quick-search-keycap` | button | ⌘K keycap button, focuses search input |
| `drawer` | div | Drawer panel; `data-open="true\|false"` |
| `drawer-header` | div | Tab strip + collapse button |
| `drawer-tab-worklist` | button | Worklist tab trigger |
| `drawer-tab-hierarchy` | button | Hierarchy tab trigger |
| `drawer-tab-icon-worklist` | span | Worklist tab icon (List icon) |
| `drawer-tab-icon-hierarchy` | span | Hierarchy tab icon (GitBranch icon) |
| `drawer-tab-count-worklist` | span | Worklist count badge (when count > 0) |
| `drawer-tab-count-hierarchy` | span | Hierarchy count badge (when count > 0) |
| `drawer-collapse-btn` | button | Collapse drawer (ChevronLeft) |
| `drawer-expand-btn` | button | Expand drawer (ChevronRight, shown when collapsed) |

`data-active` representation is component-specific; some controls use an explicit `"false"`.
Use the current component tests rather than a universal absent-attribute promise.

## Project page composition

`ProjectPage` connects the page query to the shared canvas host, text tabs/worklist and local right panel.
Image, selection and mode callbacks stay in the Labeler adapter. Successful page mutations invalidate page
queries and reconcile selection; navigation changes the active route rather than mounting hidden driver stubs.
The source-folder dialog is mounted by App. Word editing opens the right panel, not a word-edit modal.
Cold-page status and image errors stay local to the document pane; the shell remains usable.

The current grid uses 640px detail width for line/block editing and 520px for other detail surfaces. The earlier
Splitter-based assembly plan is superseded by this composition.

### Composition evidence

- Code: `frontend/src/pages/ProjectPage.tsx`, `App.tsx`, `hooks/useToolbarDispatch.ts` and
  `components/PageImageCanvas.tsx`.
- Tests: `frontend/src/pages/ProjectPage.test.tsx`, `ProjectPage.editWord.test.tsx`,
  `ProjectPage.pageLoadProgress.test.tsx`, and `tests/e2e/test_project_page_smoke.py`.
- Commits: `8391cddc` aligns driver/shell ownership; `66d878c8` records history and right-panel wiring.
- Verified: 2026-11-13 by source and test inspection; browser test execution is not claimed here.

# New SPA — Dimension C: Document / Project / System Actions

Audit date: 2026-06-05
Repo: `pdomain-ocr-labeler-spa`
Frontend: `frontend/src/` · Backend: `src/pdomain_ocr_labeler_spa/`

---

## 1. Action Inventory

| # | Action | Surface | Entry point | Backend endpoint | Status |
|---|--------|---------|-------------|------------------|--------|
| C-01 | List available projects | ProjectLoadControls (select mode) | `project-select` dropdown | `GET /api/projects` | Implemented |
| C-02 | Select project from dropdown | ProjectLoadControls | `project-select` onChange | (client-side selection) | Implemented |
| C-03 | Load / open project | ProjectLoadControls | `load-project-button` | `POST /api/projects/load` (body: `project_root`, `initial_page_index=0`) | Implemented |
| C-04 | Discover projects (rescan source root) | ProjectLoadControls | Implicit on GET /api/projects | `POST /api/projects/discover` (called server-side) | Implemented |
| C-05 | Change project (breadcrumb mode) | HeaderBar breadcrumb | `change-project-button` → opens SourceFolderDialog | `dialogStore.open("sourceFolder")` | Implemented |
| C-06 | Browse / change source folder | SourceFolderDialog | `source-folder-button` (select mode) or `change-project-button` (breadcrumb) | `POST /api/projects/source-root` | Implemented |
| C-07 | Navigate filesystem in source folder dialog | SourceFolderDialog | `fs-ls-entry-{name}` (click dir), `source-folder-up-button`, `source-folder-home-button` | `GET /api/fs/ls?path=…` | Implemented |
| C-08 | Apply new source root | SourceFolderDialog | `source-folder-apply-button` (or Mod+Enter) | `POST /api/projects/source-root` | Implemented |
| C-09 | Close / cancel source folder dialog | SourceFolderDialog | `source-folder-cancel-button` (or Escape) | (client-side) | Implemented |
| C-10 | View current project info | ProjectNavigationControls / URL | Breadcrumb label + page count | `GET /api/projects/{id}` | Implemented |
| C-11 | Delete / close project | (no explicit UI button) | — | `DELETE /api/projects/{id}` (backend only) | Backend-only — no UI trigger |
| C-12 | Navigate to previous page | PageNavigation / keyboard | `nav-prev-button` (◀) or `mod+ArrowLeft` | `GET /api/projects/{id}/pages/{idx}` (via page load) | Implemented |
| C-13 | Navigate to next page | PageNavigation / keyboard | `nav-next-button` (▶) or `mod+ArrowRight` | same | Implemented |
| C-14 | Navigate to first page | PageNavigation / keyboard | `mod+Home` | same | Implemented |
| C-15 | Navigate to last page | PageNavigation / keyboard | `mod+End` | same | Implemented |
| C-16 | Jump to specific page by number | PageNavigation | `nav-page-input` + Enter or `nav-goto-button` | React Router push to `/projects/{id}/pages/pageno/{n}` | Implemented |
| C-17 | Jump via Quick Search filter | QuickSearch (header) | `quick-search` input → worklist row click | `worklistStore.setSearchQuery()` → navigate | Implemented |
| C-18 | Walk worklist sibling (prev/next) | Breadcrumb nav | `Alt+ArrowLeft` / `Alt+ArrowRight` (useBreadcrumbHotkeys) | client-side worklist traversal | Implemented |
| C-19 | Walk worklist level up/down | Breadcrumb nav | `Alt+ArrowUp` / `Alt+ArrowDown` (useBreadcrumbHotkeys) | client-side tree walk | Implemented |
| C-20 | Save page (labeled lane) | PageActions / PageActionsCompact | `save-page-button` / `page-actions-compact-save-page` or `mod+s` | `POST /api/projects/{id}/pages/{idx}/save` | Implemented |
| C-21 | Save project / save all pages | PageActions | `save-project-button` / overflow `save-project-button` or `mod+shift+s` | `POST /api/projects/{id}/save-all` | Implemented |
| C-22 | Load page (discard unsaved edits) | PageActions | `load-page-button` / overflow `load-page-button` or `mod+l` | `POST /api/projects/{id}/pages/{idx}/load` | Implemented |
| C-23 | Auto-save (background, on every mutation) | Invisible / notification stream | Triggered server-side on every mutation | Server best-effort → cached lane | Implemented (passive) |
| C-24 | Reload OCR (re-run OCR on current page) | PageActions / PageActionsCompact | `reload-ocr-button` / `page-actions-compact-reload-ocr` or `mod+r` | `POST /api/projects/{id}/pages/{idx}/reload-ocr` → 202+job_id | Implemented |
| C-25 | Reload OCR preserving edits | PageActions | `reload-ocr-edited-button` / overflow `reload-ocr-edited-button` or `mod+shift+r` | `POST /api/projects/{id}/pages/{idx}/reload-ocr` (with `preserve_edits=true`) | Implemented |
| C-26 | Rematch GT | PageActions / PageActionsCompact | `rematch-gt-button` / `page-actions-compact-rematch-gt` or `e` (PageActions hotkey) | `POST /api/projects/{id}/pages/{idx}/rematch-gt` | Implemented |
| C-27 | Refine bboxes on current page | MatchesList / dialog | `r` (matches scope) or `shift+r` (expand+refine) / `r`/`shift+r` in dialog | `POST /api/projects/{id}/pages/{idx}/refine` → 202+job_id | Implemented |
| C-28 | Check refine availability | (behind-scenes on app load) | — | `GET /api/refine/available` | Implemented |
| C-29 | Rotate page CCW | PageActions | `rotate-ccw-button` | `POST /api/projects/{id}/pages/{idx}/rotate` (body: direction) | Implemented (stub — no actual image rotation yet) |
| C-30 | Rotate page CW | PageActions | `rotate-cw-button` | `POST /api/projects/{id}/pages/{idx}/rotate` | Implemented (stub) |
| C-31 | Rotate page 180° | PageActions | `rotate-180-button` (per spec; driver testid present) | `POST /api/projects/{id}/pages/{idx}/rotate` (direction=180) | Spec'd; driver testid present; stub |
| C-32 | Auto-rotate all pages (batch job) | OCRConfigModal | `auto-rotate-checkbox` (enable) → Apply triggers scan | `POST /api/projects/{id}/auto-rotate-all` → 202+job_id | Implemented (stub — rotation applied but re-OCR not run) |
| C-33 | Export current page | ExportDialog | `export-button` (scope=current) via `page-actions-compact-export` or `export-button` in PageActions or `mod+e` | `POST /api/projects/{id}/export` (body: scope, styles, components, output_mode flags) → 202+job_id | Implemented |
| C-34 | Export all validated pages | ExportDialog | `export-scope-all` radio | same endpoint, scope=all_validated | Implemented |
| C-35 | Filter export by text-style labels | ExportDialog | `export-style-all-checkbox` + `export-style-checkbox-{key}` | body: `style_filter` | Implemented |
| C-36 | Filter export by word components | ExportDialog | (component checkboxes in dialog) | body: `component_filter` | Implemented |
| C-37 | Toggle output mode flags (plaintext/doctr/…) | ExportDialog | output mode checkboxes | body: `output_mode` flags | Implemented |
| C-38 | Cancel running export job | ExportDialog | `export-cancel-button` (visible while job running) | `POST /api/projects/{id}/jobs/{id}/cancel` | Implemented |
| C-39 | View export run history | ExportDialog | `export-results` panel | `GET /api/projects/{id}/exports` | Implemented |
| C-40 | Fetch available export style vocab | ExportDialog (on open) | (auto-fetch) | `GET /api/projects/{id}/export/styles` | Implemented |
| C-41 | Open OCR config / settings | PageActionsCompact | `ocr-config-trigger-button` → opens OCRConfigModal | `GET /api/ocr-config` (on modal open) | Implemented |
| C-42 | Select OCR detection model | OCRConfigModal | `ocr-detection-model-select` | `POST /api/ocr-config/models` | Implemented |
| C-43 | Select OCR recognition model | OCRConfigModal | `ocr-recognition-model-select` | `POST /api/ocr-config/models` | Implemented |
| C-44 | Set HuggingFace model revision | OCRConfigModal | `ocr-hf-revision-input` | `POST /api/ocr-config/models` (body: `hf_revision`) | Implemented |
| C-45 | Rescan available OCR models | OCRConfigModal | `ocr-rescan-models-button` | `POST /api/ocr-config/rescan` | Implemented |
| C-46 | Toggle auto-rotate on load | OCRConfigModal | `auto-rotate-checkbox` | `POST /api/ocr-config/auto-rotate` | Implemented |
| C-47 | Select auto-rotate method | OCRConfigModal | `auto-rotate-method-select` | `POST /api/ocr-config/auto-rotate` | Implemented |
| C-48 | Set GT normalization profile | OCRConfigModal | `normalize-profile-select` | (stored in ocr_config.json, applied on next OCR) | Implemented |
| C-49 | Toggle normalize-GT-matching | OCRConfigModal | `normalize-gt-matching-checkbox` | (stored in ocr_config.json) | Implemented |
| C-50 | Toggle normalize-plaintext | OCRConfigModal | `normalize-plaintext-checkbox` | (stored in ocr_config.json) | Implemented |
| C-51 | Apply OCR config changes | OCRConfigModal | `ocr-config-apply-button` | `POST /api/ocr-config/models` + `/auto-rotate` | Implemented |
| C-52 | Close OCR config without applying | OCRConfigModal | `ocr-config-done-button` / `ocr-config-close-button` / Escape | (client-side) | Implemented |
| C-53 | Open hotkey help | HotkeyHelpModal | `?` key (global) or `rail-hotkeys-button` in Rail footer | `dialogStore.open("hotkeyHelp")` | Implemented |
| C-54 | Close hotkey help | HotkeyHelpModal | `hotkey-help-close` or Escape | (client-side) | Implemented |
| C-55 | View notification toasts | Notification stream | Passive — sonner toasts | `GET /api/notifications/stream` (SSE) | Implemented |
| C-56 | View job progress (while job runs) | ExportDialog / inline | Progress bar via `useJobProgress` SSE | `GET /api/jobs/{id}/events` (SSE) | Implemented |
| C-57 | Cancel arbitrary job | (no generic job list UI) | — | `POST /api/jobs/{id}/cancel` (backend + ExportDialog cancel only) | Partial — no job queue UI |
| C-58 | List all jobs | (no UI) | — | `GET /api/jobs` (backend only) | Backend-only — no UI |
| C-59 | Zoom in viewport | Viewport | `+` / `=` keys (global scope, useGlobalHotkeys) | client-side `viewportStore.setCanvasZoom` | Implemented |
| C-60 | Zoom out viewport | Viewport | `-` key (global scope) | client-side `viewportStore.setCanvasZoom` | Implemented |
| C-61 | Fit page to container | Viewport | `0` key (global scope) or `shift+0` | `viewportStore.setCanvasZoom(0)` (0 = fit-to-container) | Implemented |
| C-62 | Zoom to 100% | Viewport | `1` (if no rail conflict — rail uses 1 for block target) | Note: may conflict with rail key `1` | Ambiguous / potential conflict |
| C-63 | Pan viewport | Viewport canvas | Mouse drag (or touchpad) on canvas | client-side Konva stage drag | Implemented |
| C-64 | Open quick search | QuickSearch | `mod+k` (opens hotkeyHelp per keycap hint) or click `quick-search` input | `dialogStore.open("hotkeyHelp")` via keycap button | Partially — search input always visible; ⌘K opens help |
| C-65 | Clear quick search | QuickSearch | Escape in `quick-search-input` | `worklistStore.setSearchQuery("")` | Implemented |
| C-66 | Fetch label vocabulary | (app startup) | Auto-fetched at startup | `GET /api/label-vocabulary` | Implemented (read-only, sourced from pdomain_book_tools) |
| C-67 | Resume last session (cross-restart) | App startup | Auto-applied on server start | `session_state.json` read → last project+page loaded | Implemented |
| C-68 | Glyph bulk mark (current selection) | PageActionsCompact | `bulk-glyph-mark-button` or `mod+g` | `POST /api/projects/{id}/pages/{idx}/glyph-bulk-mark` | Implemented |

---

## 2. Keyboard Shortcuts

All combos use `mod` = Ctrl on Linux/Windows, Cmd on macOS unless noted.

### 2a. Global scope (active everywhere)

| Combo | Action | Source |
|-------|--------|--------|
| `mod+s` | Save page | useGlobalHotkeys.ts |
| `mod+shift+s` | Save project (save all) | useGlobalHotkeys.ts |
| `mod+l` | Load page (discard edits) | useGlobalHotkeys.ts |
| `mod+g` | Glyph bulk mark | useGlobalHotkeys.ts |
| `mod+e` | Open export dialog | useGlobalHotkeys.ts |
| `mod+ArrowLeft` | Previous page | useGlobalHotkeys.ts |
| `mod+ArrowRight` | Next page | useGlobalHotkeys.ts |
| `mod+Home` | First page | useGlobalHotkeys.ts |
| `mod+End` | Last page | useGlobalHotkeys.ts |
| `?` | Open hotkey help | HotkeyHelpModal (useHotkey) |
| `+` / `=` | Zoom in | hotkeyMap.ts / useGlobalHotkeys |
| `-` | Zoom out | hotkeyMap.ts / useGlobalHotkeys |
| `0` | Fit page to container | hotkeyMap.ts / useGlobalHotkeys |

### 2b. Page-actions local hotkeys (PageActions.tsx inline)

| Combo | Action | Source |
|-------|--------|--------|
| `mod+r` | Reload OCR | PageActions.tsx (useHotkey inline) |
| `mod+shift+r` | Reload OCR preserving edits | PageActions.tsx (useHotkey inline) |
| `e` | Rematch GT (PageActions bar) | PageActions.tsx (useHotkey inline, scope: page-actions) |

### 2c. Viewport scope (active when viewport focused)

| Combo | Action | Source |
|-------|--------|--------|
| `shift+p` | Toggle prediction layer | useViewportHotkeys.ts |
| `shift+l` | Toggle label layer | useViewportHotkeys.ts |
| `shift+w` | Toggle word layer | useViewportHotkeys.ts |
| `shift+1` | Selection mode: single | useViewportHotkeys.ts |
| `shift+2` | Selection mode: multi | useViewportHotkeys.ts |
| `shift+3` | Selection mode: lasso | useViewportHotkeys.ts |
| `shift+e` | Erase mode | useViewportHotkeys.ts |
| `shift+a` | Add-word mode | useViewportHotkeys.ts |
| `Escape` | Cancel / exit to select mode | useViewportHotkeys.ts |

### 2d. Matches / worklist scope

| Combo | Action | Source |
|-------|--------|--------|
| `j` | Next line in worklist | useMatchesHotkeys.ts |
| `k` | Previous line in worklist | useMatchesHotkeys.ts |
| `v` | Validate selected line | useMatchesHotkeys.ts |
| `u` | Unvalidate selected line | useMatchesHotkeys.ts |
| `d` | Delete selected line | useMatchesHotkeys.ts |
| `r` | Refine bboxes (current line) | useMatchesHotkeys.ts |
| `shift+r` | Expand + refine bboxes | useMatchesHotkeys.ts |
| `m` | Merge selected lines | useMatchesHotkeys.ts |
| `o` | Copy OCR text → GT field | useMatchesHotkeys.ts |
| `g` | Copy GT text → OCR field | useMatchesHotkeys.ts |

### 2e. Dialog scope (word-edit dialog open)

| Combo | Action | Source |
|-------|--------|--------|
| `ArrowLeft` | Previous word | useDialogHotkeys.ts |
| `ArrowRight` | Next word | useDialogHotkeys.ts |
| `shift+Enter` | Apply edit + close dialog | useDialogHotkeys.ts |
| `Escape` | Close dialog | useDialogHotkeys.ts |
| `r` | Refine bboxes (in dialog) | useDialogHotkeys.ts |
| `shift+r` | Expand + refine bboxes (in dialog) | useDialogHotkeys.ts |
| `Delete` | Delete word | useDialogHotkeys.ts |
| `shift+ArrowLeft` | Nudge bbox left | useDialogHotkeys.ts |
| `shift+ArrowRight` | Nudge bbox right | useDialogHotkeys.ts |
| `shift+ArrowUp` | Nudge bbox up | useDialogHotkeys.ts |
| `shift+ArrowDown` | Nudge bbox down | useDialogHotkeys.ts |
| `ctrl+ArrowLeft` | Resize bbox left edge | useDialogHotkeys.ts |
| `ctrl+ArrowRight` | Resize bbox right edge | useDialogHotkeys.ts |
| `ctrl+ArrowUp` | Resize bbox top edge | useDialogHotkeys.ts |
| `ctrl+ArrowDown` | Resize bbox bottom edge | useDialogHotkeys.ts |

### 2f. Source-folder dialog scope

| Combo | Action | Source |
|-------|--------|--------|
| `Enter` | Open typed path | SourceFolderDialog.tsx (useHotkey, scope: source-folder) |
| `mod+Enter` | Apply source root | SourceFolderDialog.tsx |
| `Escape` | Cancel / close dialog | SourceFolderDialog.tsx |

### 2g. GT-input scope (GT text field focused)

| Combo | Action | Source |
|-------|--------|--------|
| `Enter` | Submit GT text | hotkeyMap.ts / useGtInputHotkeys |
| `Escape` | Cancel GT edit | hotkeyMap.ts / useGtInputHotkeys |
| `mod+z` | Undo GT edit (field-level) | hotkeyMap.ts / useGtInputHotkeys |
| `mod+shift+z` | Redo GT edit (field-level) | hotkeyMap.ts / useGtInputHotkeys |

### 2h. Rail hotkeys (raw keydown listener, not react-hotkeys-hook)

Active when focus is outside any input/textarea:

| Key | Action | Source |
|-----|--------|--------|
| `1` | Rail target: Block | useRailHotkeys.ts |
| `2` | Rail target: Paragraph | useRailHotkeys.ts |
| `3` | Rail target: Line | useRailHotkeys.ts |
| `4` | Rail target: Word | useRailHotkeys.ts |
| `v` | Rail mode: View | useRailHotkeys.ts |
| `V` (shift+v) | Rail mode: View (same) | useRailHotkeys.ts |
| `r` | Rail mode: Region | useRailHotkeys.ts |
| `R` (shift+r) | Rail mode: Region | useRailHotkeys.ts |
| `a` | Rail mode: Annotate | useRailHotkeys.ts |
| `A` (shift+a) | Rail mode: Annotate | useRailHotkeys.ts |
| `e` | Rail mode: Erase | useRailHotkeys.ts |
| `E` (shift+e) | Rail mode: Erase | useRailHotkeys.ts |

### 2i. Breadcrumb navigation (raw keydown listener)

Active when focus is outside inputs, no Alt+Ctrl/Meta:

| Combo | Action | Source |
|-------|--------|--------|
| `Alt+ArrowLeft` | Walk worklist sibling prev | useBreadcrumbHotkeys.ts |
| `Alt+ArrowRight` | Walk worklist sibling next | useBreadcrumbHotkeys.ts |
| `Alt+ArrowUp` | Walk worklist level up | useBreadcrumbHotkeys.ts |
| `Alt+ArrowDown` | Walk worklist level down | useBreadcrumbHotkeys.ts |

---

## 3. User Paths

### UP-C-01: Load a project for the first time
1. Land on `/` (root route) — ProjectLoadControls in select mode.
2. `project-select` dropdown populated by `GET /api/projects`.
3. Select a project from dropdown (`project-select` onChange).
4. Click `load-project-button` → `POST /api/projects/load`.
5. Server sets session_state, returns project metadata.
6. React Router navigates to `/projects/{id}/pages/pageno/1`.

### UP-C-02: Change source folder (no project loaded)
1. Click folder icon (`source-folder-button`) → SourceFolderDialog opens.
2. Browse server filesystem via `fs-ls-entry-{name}` clicks or type path in input.
3. `source-folder-up-button` / `source-folder-home-button` for navigation.
4. Click `source-folder-apply-button` (or Mod+Enter) → `POST /api/projects/source-root`.
5. `GET /api/projects` is re-fetched; dropdown repopulates.

### UP-C-03: Change project while on a page (breadcrumb mode)
1. Click `change-project-button` (FolderOpen icon) → `dialogStore.open("sourceFolder")`.
2. SourceFolderDialog opens. Browse, apply new source root.
3. Project list repopulates; user selects + loads different project.

### UP-C-04: Navigate pages sequentially
- Click `nav-prev-button` / `nav-next-button` OR press `mod+ArrowLeft` / `mod+ArrowRight`.
- React Router pushes `/projects/{id}/pages/pageno/{n±1}`.
- `GET /api/projects/{id}/pages/{idx}` loads page data.
- Background prefetch: adjacent pages preloaded.

### UP-C-05: Jump to page N directly
1. Click `nav-page-input`, type page number, press Enter.
2. React Router pushes `/projects/{id}/pages/pageno/{N}`.

### UP-C-06: Save and navigate away safely
1. Make edits (mutations trigger server-side auto-save to cache lane).
2. Press `mod+s` or click `save-page-button` → `POST .../save` (labeled lane).
3. Optionally press `mod+shift+s` (save-project-button) to flush all pages.
4. Navigate to next page — labeled data persists.

### UP-C-07: Re-run OCR on current page
1. Click `page-actions-compact-reload-ocr` or press `mod+r`.
2. `POST .../reload-ocr` → server returns 202 + job_id.
3. `useJobProgress` opens SSE stream at `/api/jobs/{job_id}/events`.
4. Progress UI updates until "complete" event → TanStack Query invalidates page.

### UP-C-08: Re-run OCR preserving manual edits
1. Click overflow menu (`page-actions-compact-overflow` → `reload-ocr-edited-button`) or press `mod+shift+r`.
2. Same flow as UP-C-07 with `preserve_edits=true`.

### UP-C-09: Export labeled data
1. Click `page-actions-compact-export` or press `mod+e` → ExportDialog opens.
2. Choose scope: `export-scope-current` or `export-scope-all`.
3. Select style filters via `export-style-checkbox-{key}` checkboxes.
4. Select output mode flags.
5. Click `export-button` → `POST /api/projects/{id}/export` → 202+job_id.
6. SSE progress bar updates. On complete, `export-results` panel shows output paths.
7. Optionally click `export-cancel-button` to cancel in-flight job.

### UP-C-10: Configure OCR settings
1. Click `ocr-config-trigger-button` (PageActionsCompact) → OCRConfigModal opens.
2. `GET /api/ocr-config` populates current values.
3. Modify: model selects, auto-rotate toggle/method, normalization options, HF revision.
4. Click `ocr-config-apply-button` → POSTs to `/api/ocr-config/models` and `/api/ocr-config/auto-rotate`.
5. Click `ocr-config-done-button` to close.

### UP-C-11: Rotate a page manually
1. Click `rotate-ccw-button` or `rotate-cw-button` in PageActions.
2. `POST /api/projects/{id}/pages/{idx}/rotate` (direction param).
3. Rotation badge appears on page. (Note: actual image rotation + re-OCR is stubbed.)

### UP-C-12: Auto-rotate all pages
1. Open OCR config (UP-C-10).
2. Check `auto-rotate-checkbox` and select method in `auto-rotate-method-select`.
3. Apply → `POST /api/ocr-config/auto-rotate` saves config.
4. Trigger: `POST /api/projects/{id}/auto-rotate-all` → 202+job_id (runs as background job).
5. SSE progress updates. (Actual rotation is stubbed.)

### UP-C-13: Open keyboard shortcut reference
1. Press `?` anywhere (global hotkey) OR click `rail-hotkeys-button` in Rail footer.
2. HotkeyHelpModal opens, grouped by scope.
3. Escape or `hotkey-help-close` button to dismiss.

### UP-C-14: Find a page using Quick Search
1. Type in `quick-search` input (always visible in header).
2. Worklist filters in real-time via `worklistStore.setSearchQuery`.
3. Click matching row → navigate to that page.
4. Press Escape to clear search.

### UP-C-15: Session resumption on server restart
1. Server starts → reads `session_state.json`.
2. Last active project + page index restored automatically.
3. Browser navigates to `/projects/{id}/pages/pageno/{last_idx}` on load.

---

## 4. Cross-Dimension Spillover

These actions are primarily Dimension C but have significant overlap with other dimensions:

| Action | Primary dim | Overlapping dim | Note |
|--------|-------------|-----------------|------|
| Zoom in/out/fit | C (system/viewport) | A (screen layout) | Viewport zoom changes canvas render state |
| Pan viewport | C (system/viewport) | A (screen layout) | Konva stage drag; no backend call |
| Layer toggles (shift+p/l/w) | A (screen) | C (system) | Toggle display layers, not data; no backend call |
| Refine bboxes | C (OCR action) | B (content) | Modifies word bounding boxes → content dimension |
| Glyph bulk mark | C (system action) | B (content) | Bulk-mutates glyph flags on selected words |
| GT field undo/redo (mod+z/shift+z) | C (keyboard) | B (content) | Field-level text undo only, not page-level |
| Validate / unvalidate line (v/u) | B (content) | C (matches control) | Status mutation; listed in C because it's worklist-driven |
| Export style filter vocab | C (export) | B (content labels) | `GET /api/label-vocabulary` feeds ExportDialog checkboxes |
| Notification toasts | C (system) | A (UI feedback) | SSE-driven sonner toasts appear in shell |

---

## 5. Coverage Self-Check

| Category | Count | Notes |
|----------|-------|-------|
| Total actions enumerated | 68 | C-01 through C-68 |
| Fully implemented | 58 | Working end-to-end |
| Backend-only (no UI trigger) | 3 | C-11 (DELETE project), C-57 (generic job cancel), C-58 (job list) |
| Stubbed / partial | 4 | C-29 (rotate CCW — no image change), C-30 (rotate CW — stub), C-31 (rotate 180 — stub), C-32 (auto-rotate-all — stub) |
| Potential key conflict | 1 | C-62: zoom-to-100% key `1` vs rail target Block `1` |
| Ambiguous / partial | 2 | C-64 (quick search vs help — ⌘K opens help, not search), C-57 (cancel limited to ExportDialog) |
| Total keyboard shortcuts | 72 | Global(13) + PageActions-local(3) + Viewport(9) + Matches(10) + Dialog(15) + SourceFolder(3) + GTInput(4) + Rail(12) + Breadcrumb(4) = 73 combos across 9 scope groups |
| User paths documented | 15 | UP-C-01 through UP-C-15 |
| Cross-dimension spillover items | 9 | See Section 4 |

### Gaps and observations

1. **No vocabulary management UI.** `GET /api/label-vocabulary` is read-only and returns constants from `pdomain_book_tools`. There is no screen to add, edit, or remove vocabulary entries.
2. **No undo/redo (page-level).** Only field-level undo exists in the GT text input (`mod+z`/`mod+shift+z`). There is no page-state undo stack.
3. **No auth/session management.** `NoneAuthAdapter` placeholder; deferred per D-042.
4. **No import/upload.** All projects live on the server filesystem. SourceFolderDialog browses server-side paths only.
5. **No generic job queue UI.** Only ExportDialog shows job progress inline. `GET /api/jobs` is backend-only.
6. **OCR-config trigger (#405 follow-up).** The `ocr-config-trigger-button` was moved and restored per issue #405. Confirmed present in `PageActionsCompact.tsx`.
7. **Rotate stubs (M9.1/M9.2).** The rotate endpoints exist and are called; actual image rotation, re-OCR, and PageRecord update are stubbed. Rotation badge renders but image does not change.
8. **Key conflict risk: `1` key.** Rail hotkeys (raw keydown) bind `1`→Block target; zoom hotkeys might bind `1`→100% zoom. Needs audit to confirm the zoom-to-100% binding is not actually registered (it appears in spec notes but may not be in implemented hotkeyMap).
9. **`mod+k` opens help, not search.** The `quick-search-keycap` button label shows `⌘K` but clicking it calls `dialogStore.open("hotkeyHelp")`. Quick search input is always visible and requires a direct click (not a shortcut) to focus.

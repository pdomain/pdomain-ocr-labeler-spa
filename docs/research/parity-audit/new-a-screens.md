# New labeler SPA — Dimension A: Screens, Navigation & Chrome

Audit date: 2026-06-05. Auditor: Claude Sonnet 4.6.

---

## Screens & panels

| Screen / Panel | Purpose | Route / how reached | Component file:line | data-testid (if any) |
|---|---|---|---|---|
| **RootPage** | Project dashboard — shows project grid or auto-resumes last session | `/` (GET → session-state check → redirect or render) | `frontend/src/pages/RootPage.tsx:451` | `empty-project-state` (legacy stub), `root-hero-band`, `root-search-filter-bar`, `root-projects-grid` |
| — EmptyProjectState (stub) | Centred "no project loaded" placeholder; shown if no projects discovered | Rendered inside RootPage when no project | `frontend/src/pages/RootPage.tsx:81` | `empty-project-state` |
| — HeroBand | Branded header band: logo + tagline | Top of RootPage/ProjectListView | `frontend/src/pages/RootPage.tsx:95` | `root-hero-band`, `root-hero-title` |
| — ProjectListView | Main project browser: search + filter chips + card grid | RootPage fallback (no prior session, load failed, skipRedirect) | `frontend/src/pages/RootPage.tsx:295` | `root-search-filter-bar`, `root-search-input`, `root-filter-chips`, `root-projects-grid`, `root-empty-search`, `root-empty-projects` |
| — ProjectCard | Per-project card: thumbnail + page count + progress bar + action menu | Inside project grid | `frontend/src/pages/RootPage.tsx:147` | `project-card-{id}`, `project-card-thumbnail-{id}`, `project-card-open-{id}`, `project-card-menu-{id}`, `project-card-delete-{id}`, `project-card-archive-{id}`, `project-card-error-{id}` |
| — ProjectCard action menu | Inline drop-down: Delete / Archive per project | Click chevron on a ProjectCard | `frontend/src/pages/RootPage.tsx:249` | (inside `project-card-menu-{id}` toggle) |
| **ProjectPage** | Main OCR-labeling surface | `/projects/:projectId/pages/pageno/:pageNo` | `frontend/src/pages/ProjectPage.tsx:224` | `project-page`, `project-workspace`, `project-canvas-column`, `project-worklist-column`, `project-detail-column` |
| — image-pane (canvas column) | Scrollable Konva page image with bbox overlays | Inside ProjectPage canvas column | `frontend/src/pages/ProjectPage.tsx:836` | `image-pane` |
| — text-pane (hidden stubs) | TextTabs/WordMatchView driver-contract stubs (hidden) | Hidden div inside canvas column | `frontend/src/pages/ProjectPage.tsx:874` | `text-pane` |
| — inline-banners zone | OCR-failed and image-drift banner strip below canvas | Bottom of canvas column | `frontend/src/pages/ProjectPage.tsx:847` | `inline-banners` |
| — project-top-toolbar | 36px bar showing current page / total count | Top of canvas slot (inside image pane column) | `frontend/src/pages/ProjectPage.tsx:749` | `project-top-toolbar`, `project-toolbar-page` |
| **PerfTestPage** | Dev/test Konva viewport benchmark — 200 lines × 20 words | `/__perf-test` (lazy-loaded) | `frontend/src/pages/PerfTestPage.tsx:1` | `perf-test-loading` (Suspense fallback) |
| **Drawer panel** (Worklist column) | 320px collapsible left-side panel with Worklist and Hierarchy tabs | Inside ProjectPage; collapsed/expanded via Rail footer "Bulk" button or collapse chevron | `frontend/src/components/shell/Drawer.tsx:70` | `drawer`, `drawer-header` |
| — Drawer: Worklist tab | Line-match list: filter chips + sort + per-line rows + bulk actions footer | Active by default; click "Worklist" tab | `frontend/src/components/drawer/Worklist.tsx:362` | `worklist`, `worklist-filter-row`, `worklist-queue`, `worklist-filter-all`, `worklist-filter-unvalidated`, `worklist-filter-mismatched`, `worklist-sort-select`, `worklist-row-{idx}`, `worklist-row-checkbox-{idx}`, `worklist-row-{idx}-gt` |
| — Drawer: BulkActions footer | Page-scope and line-scope bulk mutation buttons at Worklist bottom | Always visible inside Worklist | `frontend/src/components/drawer/BulkActions.tsx:1` | (see BulkActions component) |
| — Drawer: Hierarchy tab | Block/Para/Line/Word tree view with kind filter pills and node count | Click "Hierarchy" drawer tab | `frontend/src/components/drawer/Hierarchy.tsx:436` | `hierarchy`, `hierarchy-filter-row`, `hierarchy-filter-all`, `hierarchy-filter-block`, `hierarchy-filter-para`, `hierarchy-filter-line`, `hierarchy-filter-word`, `hierarchy-node-count`, `hierarchy-node-{id}`, `hierarchy-color-{id}` |
| **Right panel** (detail column) | Collapsible context panel: shows word/line/block/para detail by selection level | Opens when user selects a bounding box in canvas; width 520px (word) or 640px (line/block/para) | `frontend/src/components/shell/RightPanel.tsx:66` | `right-panel`, `right-panel-header`, `right-panel-body`, `right-panel-placeholder` |
| — RightPanel: WordDetail | 6-accordion word editor: BBox / Rebox / Erase Pixels / Structure / Char Ranges / Char Fixer; with header, image preview, OCR/GT compare, style/component palettes, sticky footer | When `selection-store.level === "word"` | `frontend/src/components/right-panel/WordDetail.tsx:90` | `word-detail`, `word-detail-accordion` |
| — RightPanel: LineDetail | Line tab (structure box + GT input + line card + validate-all + merge/copy/split) + Words tab (card/row density toggle + bulk bar + per-word cards) | When `selection-store.level === "line"` | `frontend/src/components/right-panel/LineDetail.tsx:76` | `line-detail`, `line-detail-tabs`, `line-detail-tab-line`, `line-detail-tab-words`, `line-detail-structure-box`, `line-detail-gt-input`, `line-detail-validate-all`, `line-detail-merge-prev`, `line-detail-merge-next`, `line-detail-density-toggle`, `line-detail-bulk-bar`, `line-detail-bulk-validate`, `line-detail-bulk-skip` |
| — RightPanel: BlockDetail | Layout tab (glyph cards + model-suggest + preview) + Items tab (flat/tree sub-toggle + line cards) + Para layout tab | When `selection-store.level === "block"` | `frontend/src/components/right-panel/BlockDetail.tsx:1` | `block-detail`, `block-detail-tabs`, `block-detail-tab-layout`, `block-detail-tab-items`, `block-detail-tab-para-layout`, `block-detail-layout-chip-*`, `block-detail-layout-save`, `block-detail-preview`, `block-detail-items-tree` |
| — RightPanel: ParagraphDetail | Paragraph-scope action buttons (merge/delete/split/copy GT-OCR/validate) above BlockDetail items | When `selection-store.level === "para"` | `frontend/src/components/right-panel/ParagraphDetail.tsx:47` | `paragraph-detail`, `para-merge`, `para-delete`, `para-split-after-line`, `para-copy-gt-to-ocr`, `para-copy-ocr-to-gt`, `para-validate`, `para-unvalidate` |
| — RightPanel: placeholder | "Select a block/para/line/word…" centred message | When `selection-store.level === "none"` | `frontend/src/components/shell/RightPanel.tsx:127` | `right-panel-placeholder` |

---

## Global chrome

| Element | Location | Contents | file:line |
|---|---|---|---|
| **AppShell wrapper** (`data-testid="app-shell"`) | Root of every route; full-screen grid | Outer div providing `h-screen w-full`; wraps pdomain-ui AppShell | `frontend/src/App.tsx:187` |
| **pdomain-ui AppShell** | Wraps all content; `launcherSlot="header"` injects suite launcher into header zone | Provides header / rail / main / children slots; AppShell renders children (dialogs) outside the grid | `frontend/src/App.tsx:192` |
| **HeaderBar** | 56px top bar; present on every route | Left: logo badge ("O") + "OCR Labeler" + "Projects" link [+ "/" + project-name chip on project routes]; Center-left: navSlot (ProjectNavigationControls on project routes); Center-right: actionsSlot (PageActionsCompact on project routes); Right: metrics strip (project routes) + theme chips | `frontend/src/components/HeaderBar.tsx:104` |
| — Logo / home link | Left of HeaderBar | Orange "O" badge + "OCR Labeler" text; Link to "/" | `frontend/src/components/HeaderBar.tsx:116` |
| — "Projects" breadcrumb link | Left of HeaderBar (after logo) | Link to "/"; always visible | `frontend/src/components/HeaderBar.tsx:133` |
| — Project-name breadcrumb chip | Left of HeaderBar (project routes only) | Truncated project_id display; renders when `headerProjectName !== null` | `frontend/src/components/HeaderBar.tsx:143` |
| — ProjectNavigationControls (navSlot) | Center-left of HeaderBar; project routes only | ◀ page-input ▶ / total; prev/next/goto navigation | `frontend/src/components/ProjectNavigationControls.tsx:37` |
| — PageActionsCompact (actionsSlot) | Center-right of HeaderBar; project routes only | Reload OCR, Rematch, ✓ Save page, Export ▾, OCR Config, ⋯ overflow menu, Bulk glyphs | `frontend/src/components/PageActionsCompact.tsx:34` |
| — PageActionsCompact overflow menu | Dropdown from "⋯" in actionsSlot | Reload OCR (Edited), Save Project, Load Page | `frontend/src/components/PageActionsCompact.tsx:329` |
| — Metrics strip | Right of HeaderBar; project routes with loaded page only | Word count: exact / fuzzy / mismatch counts, validated/total, optional glyphs reviewed | `frontend/src/components/HeaderBar.tsx:165` |
| — Theme chips | Far-right of HeaderBar; all routes | Dark / Light / System radio group | `frontend/src/components/HeaderBar.tsx:37` |
| — Status announcer (sr-only) | Inside HeaderBar slot; always present | `role="status"` `aria-live="polite"` accessible live region | `frontend/src/App.tsx:217` |
| — Error announcer (sr-only) | Inside HeaderBar slot; always present | `role="alert"` `aria-live="assertive"` accessible live region | `frontend/src/App.tsx:223` |
| — Driver-contract stubs (hidden) | Hidden div inside HeaderBar | Nav stubs (nav-prev-button, nav-next-button, nav-goto-button, nav-page-input, nav-page-total-label); source-folder stubs (current-path-label, path-input, home/up/open-typed/use-current/apply/cancel buttons); OCR config stubs (detection-model-select, recognition-model-select, hf-revision-input, rescan/cancel/apply buttons) | `frontend/src/components/HeaderBar.tsx:213` |
| **Rail** | 64px vertical left strip; project routes only (via AppShell `rail` slot) | MODE section (View/Refine/Annotate/Erase); TARGET section (Block/Para/Line/Word swatches); LAYERS visibility toggles (Block/Para/Line/Word); Footer: Bulk + Hotkeys buttons | `frontend/src/components/shell/Rail.tsx:194` |
| — Rail footer: Bulk button | Bottom of Rail | Opens drawer to worklist tab | `frontend/src/components/shell/Rail.tsx:321` |
| — Rail footer: Hotkeys button | Bottom of Rail | Opens HotkeyHelpModal (`dialogStore.open("hotkeyHelp")`) | `frontend/src/components/shell/Rail.tsx:337` |
| **ImageTabsHeader** | Viewport chrome bar; top of image-pane; project routes only | Para/Line/Word layer checkboxes; Para/Line/Word selection-mode radios; Erase toggle; + Word (add-word) toggle; Mismatches filter toggle; Layer color legend chips; Zoom Fit + 100% buttons | `frontend/src/components/ImageTabsHeader.tsx:66` |
| **BulkWordActions bar** | Narrow horizontal bar below ImageTabsHeader | Page validate-all / unvalidate-all; word multi-select: delete, style-select+apply, component-select+apply | `frontend/src/components/BulkWordActions.tsx:39` |
| **project-top-toolbar** | 36px bar at very top of canvas column (above ImageTabsHeader) | Page N / M indicator (tabular-nums) | `frontend/src/pages/ProjectPage.tsx:749` |
| **TextTabs** (hidden stub) | Hidden inside canvas column; driver-contract testids only | Matches / Ground Truth / OCR tabs; match-filter segmented control | `frontend/src/components/TextTabs.tsx:56` |
| **ToolbarActionGrid** (hidden stub) | Hidden inside canvas column; driver-contract testids only | Scope × action grid for toolbar batch operations | `frontend/src/components/ToolbarActionGrid.tsx:1` |
| **Sonner Toaster** | Fixed position bottom-right; all routes | Toast notifications; theme-aware (dark/light) | `frontend/src/App.tsx:317` |
| **BusyOverlay** | Fixed inset overlay z-40; project routes during mutations | Spinner + progress message + optional Cancel button | `frontend/src/components/BusyOverlay.tsx:35` |
| **ProjectLoadingOverlay** | Fixed inset overlay z-50; project routes during initial page fetch | Spinner + "Loading project…" | `frontend/src/components/BusyOverlay.tsx:117` |
| **Drawer collapse/expand tab** | Left side of project-worklist-column | When open: collapse chevron + Worklist/Hierarchy tab strip; when collapsed: expand chevron | `frontend/src/components/shell/Drawer.tsx:70` |
| **RightPanel header** | Top of right panel column | Breadcrumb path chips (Project › Block › Para › Line › Word) + collapse button | `frontend/src/components/shell/RightPanel.tsx:79` |
| **Breadcrumb** | Inside RightPanel header | Clickable ancestor chips + active terminal chip with kind-color fill | `frontend/src/components/shell/Breadcrumb.tsx:150` |
| **StudioShell** (unused in production render) | CSS grid layout component (defined but ProjectPage uses a raw grid instead) | 5-zone grid: header / rail / drawer / canvas / right | `frontend/src/components/shell/StudioShell.tsx:39` |
| **QuickSearch** (defined but not currently mounted) | Defined header widget; filters worklist by text; wires to worklistStore.searchQuery | Not mounted in App.tsx or HeaderBar as of audit date | `frontend/src/components/shell/QuickSearch.tsx:23` |
| **OcrFailedBanner** | Inline inside `inline-banners` div; project routes | Danger banner when `pageRecord.ocr_failed === true` | `frontend/src/components/InlineBanners.tsx:28` |
| **ImageDriftBanner** | Inline inside `inline-banners` div; project routes | Warning banner after 409 image_drift save | `frontend/src/components/InlineBanners.tsx:62` |
| **ProjectNotFoundBanner** (defined but not mounted inline) | Defined; currently project-not-found triggers a toast + navigate("/") instead of inline banner | Danger banner for missing project | `frontend/src/components/InlineBanners.tsx:48` |

---

## Modals & dialogs

| Dialog | Opened by | Purpose | file:line |
|---|---|---|---|
| **OCRConfigModal** | `dialogStore.open("ocrConfig")` — triggered by `ocr-config-trigger-button` in PageActionsCompact (project routes only); also stub present in HeaderBar; E2E test bridge `window.__DIALOG_STORE_OPEN("ocrConfig")` | Configure OCR: text-normalization toggles (GT matching, plaintext tabs, profile); auto-rotation (on/off, method); OCR model selection (detection + recognition + HF revision; Apply / Rescan). Shows error banner on POST failure. | `frontend/src/components/OCRConfigModal.tsx:170` |
| **ExportDialog** | `dialogStore.open("export")` — triggered by "Export ▾" in PageActionsCompact, Mod+E global hotkey, toolbar export action; only mounts when `projectId` is non-null | Export DocTR training data: scope (current page / all validated), style filter checkboxes, component filter dropdown, output mode radios (both/detection/recognition/classification), progress display, run history (client-only), Cancel while running | `frontend/src/components/ExportDialog.tsx:75` |
| **HotkeyHelpModal** | `dialogStore.open("hotkeyHelp")` — via `?` key anywhere (not in form inputs); Rail footer "Hotkeys" button; QuickSearch "⌘K" keycap button | Keyboard shortcuts reference: grouped sections of key-cap rows, scrollable, close via × or Escape | `frontend/src/components/HotkeyHelpModal.tsx:89` |
| **SourceFolderDialog** | `dialogStore.open("sourceFolder")` — "Open source folder" button in RootPage ProjectListView | File-browser-style folder picker: current-path display, Home/Up navigation, subdirectory listing, typed-path input, Apply (POST /api/projects/source-root) | `frontend/src/components/SourceFolderDialog.tsx:66` |
| **WordEditDialog** | `dialogStore.openWordEdit({lineIdx, wordIdx})` — via per-word pencil click on canvas / WordCell; also openable from legacy hotkey paths | Word-level editor: 3-column preview row (prev/current/next word), GT text input, Konva word-image canvas, action rows (Merge/Split/Delete/Crop), Refine/Nudge/Tag rows, Apply & Close / × Close | `frontend/src/components/WordEditDialog.tsx:117` |
| **ConfirmDialog** | `dialogStore.openConfirm({title, body, onConfirm})` — triggered by destructive keyboard shortcuts (D key via `onDelete`), `handleLoadPage()`, `handleRematchGt()` | Destructive-action confirmation: title + message body; Confirm (red) / Cancel buttons; Escape closes (Radix native) | `frontend/src/components/ConfirmDialog.tsx:55` |
| **BulkGlyphMarkDialog** | `setBulkGlyphOpen(true)` — "Bulk glyphs" button in PageActionsCompact | Bulk glyph annotation: recipe dropdown (ct/st/long-s), skip-annotated checkbox, accept-predictions checkbox, Preview (dry-run) + Apply buttons, preview count | `frontend/src/components/glyph/BulkGlyphMarkDialog.tsx:35` |
| **GlyphAnnotationPanel** (popover/inline section) | Rendered inside WordDetail or anchored to WordCell click (typography annotation sub-panel) | View/edit ligature marks + long-s annotations + swash toggle; accept/reject predictions; mark reviewed | `frontend/src/components/glyph/GlyphAnnotationPanel.tsx:40` |

---

## Navigation map

### Route table

| Route pattern | Handler | Result |
|---|---|---|
| `/` | `RootPage` | Checks session-state; if last project on disk → POST /api/projects/load → redirect to `/projects/:id/pages/pageno/:pageNo`; else → ProjectListView |
| `/projects/:projectId` | `ProjectRootRedirect` | Immediate `<Navigate>` to `/projects/:projectId/pages/pageno/1` |
| `/projects/:projectId/pages/pageno/:pageNo` | `ProjectPage` | Full labeling surface for page N |
| `/projects/:projectId/pages/index/:idx0` | `ProjectPageIndexRedirect` | Converts 0-based idx to 1-based pageNo; `<Navigate>` to pageno URL |
| `/__perf-test` | `PerfTestPage` (lazy) | Dev/test Konva benchmark page |
| `*` (catch-all) | `<Navigate to="/" replace>` | Redirects unknown routes to root |

### Ways to navigate between screens

1. **Root → ProjectPage**: Click "Open" on a ProjectCard (POST /api/projects/load → navigate); or auto-resume from session-state on app load.
2. **ProjectPage → Root**: Click "Projects" link or logo in HeaderBar.
3. **ProjectPage → ProjectPage (different page)**: Prev/Next arrow buttons in `ProjectNavigationControls` (nav-prev-button / nav-next-button); type page number in nav-page-input + Enter (nav-goto-button sr-only); global hotkeys Mod+ArrowLeft/Right (prev/next), Mod+Home/End (first/last); Alt+Arrow breadcrumb hotkeys; WorkList row click selects line (does not navigate pages).
4. **404 → Root**: Any non-existent project route triggers `projectNotFound` effect → toast + navigate("/", skipSessionRedirect).
5. **Breadcrumb chips in RightPanel**: Click ancestor chips to re-select at that level (does not change route/page).
6. **Modal → project context**: All modals are overlaid on the current route; closing them returns to the underlying screen unchanged.
7. **RootPage filter / search**: Filters the project card grid in-place; does not change route.
8. **RootPage → SourceFolderDialog**: "Open source folder" button opens the dialog; Apply closes it and invalidates the projects query, refreshing the grid.
9. **Rail "Bulk" button**: Opens the Drawer to the Worklist tab (state change only; no route change).
10. **Rail "Hotkeys" button / QuickSearch keycap / ? key**: Opens HotkeyHelpModal overlay.
11. **Drawer collapse/expand**: Toggles `useUiPrefs.drawerOpen`; no route change.
12. **RightPanel collapse**: Toggles `useUiPrefs.rightPanelOpen`; no route change.

---

## Cross-dimension spillover

The following items are visible in this dimension's source scan but belong primarily to other dimensions:

- **Dimension B (content-level edit actions)**: All mutation buttons inside ImageTabsHeader (Erase, + Word), BulkWordActions, PageActionsCompact (Reload OCR, Rematch, Save page), ToolbarActionGrid, WordDetail sections (BBox/Rebox/Erase Pixels/Structure/Char Ranges/Char Fixer), WordEditDialog action rows, LineDetail validate/merge/copy/split buttons, ParagraphDetail action buttons, BulkActions in drawer footer, BulkGlyphMarkDialog Apply/Preview buttons.
- **Dimension C (document/system operations + global keyboard shortcuts)**: Global hotkeys wired in `useGlobalHotkeys` (Mod+S, Mod+R, Mod+G, Mod+L, Mod+E, Mod+ArrowLeft/Right, Mod+Home/End, Mod+Comma for OCR config); matches-line hotkeys in `useMatchesHotkeys` (V/U/D/O/G/M/R); Rail mode/target hotkeys in `useRailHotkeys` (1/2/3/4 target; V/R/A/E mode); PageActionsCompact export + OCR-config launchers.
- **QuickSearch** (`frontend/src/components/shell/QuickSearch.tsx`) is defined but not mounted in the current App.tsx or HeaderBar. It filters the worklist `searchQuery` store and opens HotkeyHelpModal from the keycap. Existence noted here; render location is a gap.
- **StudioShell** (`frontend/src/components/shell/StudioShell.tsx`) is defined as the intended 5-zone CSS grid but ProjectPage uses a raw `grid` div directly instead of StudioShell. The component exists and is tested but is not used in the production render tree.

---

## Coverage self-check

### Source files scanned (exhaustive)

**Pages**
- `frontend/src/pages/RootPage.tsx`
- `frontend/src/pages/ProjectPage.tsx`
- `frontend/src/pages/PerfTestPage.tsx`

**App entry / routing**
- `frontend/src/App.tsx`
- `frontend/src/lib/routes.ts`
- `frontend/src/stores/dialog-store.ts`

**Shell / layout components**
- `frontend/src/components/shell/Rail.tsx`
- `frontend/src/components/shell/Drawer.tsx`
- `frontend/src/components/shell/RightPanel.tsx`
- `frontend/src/components/shell/Breadcrumb.tsx`
- `frontend/src/components/shell/StudioShell.tsx`
- `frontend/src/components/shell/QuickSearch.tsx`

**Header / navigation**
- `frontend/src/components/HeaderBar.tsx`
- `frontend/src/components/ProjectNavigationControls.tsx`
- `frontend/src/components/PageActionsCompact.tsx`

**Canvas viewport chrome**
- `frontend/src/components/ImageTabsHeader.tsx`
- `frontend/src/components/BulkWordActions.tsx`
- `frontend/src/components/BusyOverlay.tsx`
- `frontend/src/components/InlineBanners.tsx`
- `frontend/src/components/TextTabs.tsx`

**Drawer contents**
- `frontend/src/components/drawer/Worklist.tsx`
- `frontend/src/components/drawer/Hierarchy.tsx`
- `frontend/src/components/drawer/BulkActions.tsx` (existence confirmed; full content deferred — Dimension B)

**Right panel contents**
- `frontend/src/components/shell/RightPanel.tsx`
- `frontend/src/components/right-panel/WordDetail.tsx`
- `frontend/src/components/right-panel/LineDetail.tsx`
- `frontend/src/components/right-panel/BlockDetail.tsx` (header/testids only — Dimension B for content)
- `frontend/src/components/right-panel/ParagraphDetail.tsx` (header/testids)
- `frontend/src/components/right-panel/WordHeader.tsx` (existence confirmed)
- `frontend/src/components/right-panel/WordImagePreview.tsx` (existence confirmed)
- `frontend/src/components/right-panel/OcrGtCompareRow.tsx` (existence confirmed)
- `frontend/src/components/right-panel/StylePalette.tsx` (existence confirmed)
- `frontend/src/components/right-panel/ComponentPalette.tsx` (existence confirmed)
- `frontend/src/components/right-panel/WordFooter.tsx` (existence confirmed)
- `frontend/src/components/right-panel/LineCard.tsx` (existence confirmed — imported by LineDetail)
- `frontend/src/components/right-panel/LineWordsCard.tsx` (existence confirmed)
- `frontend/src/components/right-panel/sections/BBoxSection.tsx` (existence confirmed)
- `frontend/src/components/right-panel/sections/ReboxSection.tsx` (existence confirmed)
- `frontend/src/components/right-panel/sections/ErasePixelsSection.tsx` (existence confirmed)
- `frontend/src/components/right-panel/sections/StructureSection.tsx` (existence confirmed)
- `frontend/src/components/right-panel/sections/CharRangesSection.tsx` (existence confirmed)
- `frontend/src/components/right-panel/sections/CharFixerSection.tsx` (existence confirmed)

**Dialogs / modals**
- `frontend/src/components/OCRConfigModal.tsx`
- `frontend/src/components/ExportDialog.tsx`
- `frontend/src/components/HotkeyHelpModal.tsx`
- `frontend/src/components/SourceFolderDialog.tsx`
- `frontend/src/components/WordEditDialog.tsx`
- `frontend/src/components/ConfirmDialog.tsx`
- `frontend/src/components/glyph/BulkGlyphMarkDialog.tsx`
- `frontend/src/components/glyph/GlyphAnnotationPanel.tsx`
- `frontend/src/components/glyph/GlyphChip.tsx` (existence confirmed)

**Architecture docs consulted**
- `docs/architecture/00-overview.md` (referenced; not read in full — skim only)
- `docs/architecture/13-driver-contract.md` (testid contract source)
- `docs/architecture/24-shell-layout.md` (referenced)
- `docs/architecture/25-drawer-worklist.md` (referenced)
- `docs/architecture/26-right-panel-detail.md` (referenced)

### Known gaps / items not fully covered in this dimension

- **Right-panel sections interior** (BBoxSection, ReboxSection, ErasePixelsSection, StructureSection, CharRangesSection, CharFixerSection, CharFixerCanvas, ReboxCanvas, EraseCanvas): their individual testids and sub-controls belong to Dimension B. Existence is confirmed; content audit deferred.
- **ToolbarActionGrid interior**: all grid cell testids (`toolbar-{scope}-{action}`, `apply-style-select`, etc.) belong to Dimension B.
- **WordEditDialog interior rows** (WordActionRows, WordRefineNudgeRows, WordTagRow, WordImageCanvas): all Dimension B.
- **BulkActions (drawer footer)**: not fully read — existence confirmed; all buttons are Dimension B.
- **QuickSearch** is defined but not rendered in the current production App.tsx build; its mount location is unresolved.
- **StudioShell** is defined but not used in the actual production render path; ProjectPage uses a raw CSS grid.
- **GlyphAnnotationPanel sub-controls** (ligature kind select, char-span cells, long-s cells, swash checkbox): Dimension B.
- **UnicodePicker**: `frontend/src/components/right-panel/UnicodePicker.tsx` — referenced from right-panel; existence confirmed; content is Dimension B.
- **FilterToggle**: `frontend/src/components/FilterToggle.tsx` — matches-tab line filter toggle; Dimension B.
- **WordMatchView**: `frontend/src/components/WordMatchView.tsx` — per-line/per-word match rows; Dimension B.
- **PageImage, PageImageCanvas, WordImageCanvas**: canvas rendering components; Dimension B/C.
- **WordCell, LineCard**: per-item UI; Dimension B.
- **ProjectLoadControls**: `frontend/src/components/ProjectLoadControls.tsx` — referenced in driver contract §2.1 for project-select / load-project-button / source-folder-button; not opened in this audit but testids are on the root page.

# Legacy pd-ocr-labeler — Dimension C: Document / Project / System Actions

Audit date: 2026-06-05. Source repo: `/workspaces/ocr-container/pd-ocr-labeler`.
Scope: project/book/folder open-load-close; page navigation; save/persist;
export/download; whole-image operations; OCR run/re-OCR; refine-bboxes at page
or batch scope; undo/redo; global search/find; settings/preferences/OCR-config;
vocabulary management screens; jobs/progress; import; all global keyboard
shortcuts; session/auth.

---

## Action inventory

| # | Action name | Screen / context | Trigger | Scope | Handler file:line | Behavior |
|---|---|---|---|---|---|---|
| C-01 | Set source projects root (browse) | Header — project load controls | Click `folder_open` icon button (`source-folder-button`) | Global / app | `project_load_controls.py:205` `_open_source_folder_dialog` | Opens the source-folder picker dialog, pre-filled with the currently configured root. |
| C-02 | Navigate picker — browse into child directory | Source folder dialog | Click a child-directory button in the scrollable list | Dialog | `project_load_controls.py:287` `_open_child_directory` | Descends into the clicked subdirectory and refreshes the list and breadcrumbs. |
| C-03 | Navigate picker — Go Home | Source folder dialog | Click **Home** button (`source-folder-home-button`) | Dialog | `project_load_controls.py:295` `_path_picker_go_home` | Navigates the picker to the user's home directory. |
| C-04 | Navigate picker — Go Up | Source folder dialog | Click **Up** button (`source-folder-up-button`) | Dialog | `project_load_controls.py:303` `_path_picker_go_up` | Navigates the picker one directory level up toward the filesystem root. |
| C-05 | Navigate picker — Open typed path | Source folder dialog | Click **Open Typed Path** button (`source-folder-open-typed-button`) | Dialog | `project_load_controls.py:322` `_open_typed_source_path` | Resolves the path typed in the path input and navigates the picker to it (warns if invalid/missing). |
| C-06 | Navigate picker — copy current to input | Source folder dialog | Click **Use Current** button (`source-folder-use-current-button`) | Dialog | `project_load_controls.py:348` `_use_current_folder` | Copies the currently browsed directory path into the path input without applying. |
| C-07 | Apply source folder root | Source folder dialog | Click **Apply** button (`source-folder-apply-button`) | Global / app | `project_load_controls.py:356` `_apply_source_folder` | Persists the typed path as `source_projects_root` in `config.yaml`, rescans available projects, and closes the dialog. |
| C-08 | Cancel source folder dialog | Source folder dialog | Click **Cancel** button (`source-folder-cancel-button`) | Dialog | `project_load_controls.py:78` `dialog.close` | Closes the dialog without changing the source folder. |
| C-09 | Select project from dropdown | Header — project load controls | Choose from **Project** `ui.select` (`project-select`) | Global | `project_load_controls.py:91` (binding) | Updates `AppStateViewModel.selected_project_key`; does not load yet. |
| C-10 | Load selected project | Header — project load controls | Click **LOAD** button (`load-project-button`) | Global | `project_load_controls.py:180` `_load_selected_project` | Loads the selected project directory into memory (triggers background OCR on first page), updates browser URL to `/project/{key}`. |
| C-11 | Auto-restore session on startup | App startup (no CLI project arg) | Automatic — on app startup | Global | `app.py:419` `_try_restore_session` | Reads `session_state.json`; if the last project path still exists, enqueues a background `load_project` to the last page index. |
| C-12 | Load project from URL — project only | Deep link: `/project/{project_id}` | Browser navigation / direct URL | Global | `app.py:497` `_initialize_from_url` | Resolves project_id to filesystem path, loads it, and navigates to page 1. |
| C-13 | Load project from URL — project + page | Deep link: `/project/{project_id}/page/{page_id}` | Browser navigation / direct URL | Global | `app.py:497` `_initialize_from_url` | Resolves project and navigates to the 1-based page number encoded in the URL. |
| C-14 | Navigate to previous page | Project view — navigation controls | Click **Prev** button (`nav-prev-button`) | Project | `project_view.py:162` `_prev_async` | Navigates to the page before the current one; blocked when already on page 1 or project is loading. Busy spinner shown during navigation. |
| C-15 | Navigate to next page | Project view — navigation controls | Click **Next** button (`nav-next-button`) | Project | `project_view.py:206` `_next_async` | Navigates to the page after the current one; blocked when at last page or project is loading. Busy spinner shown. |
| C-16 | Jump to specific page (button) | Project view — navigation controls | Click **Go To:** button (`nav-goto-button`) after filling page number input (`nav-page-input`) | Project | `project_view.py:265` `_goto_async` | Navigates to the 1-based page number entered in the numeric input; validates the range. |
| C-17 | Save current page | Project view — page actions toolbar | Click **Save Page** button (`save-page-button`) | Page | `page_view.py:233` `_save_page_async` | Serializes the current page OCR + GT data to `pages.json` (sidecar persistence) in the project directory. |
| C-18 | Save all loaded pages in project | Project view — page actions toolbar | Click **Save Project** button (`save-project-button`) | Project | `page_view.py:257` `_save_project_async` | Saves every page that has been loaded into memory to disk; reports per-page success/failure count. |
| C-19 | Load saved page from disk | Project view — page actions toolbar | Click **Load Page** button (`load-page-button`) | Page | `page_view.py:284` `_load_page_async` | Loads the previously saved OCR + GT sidecar data for the current page, replacing the in-memory state. |
| C-20 | Open export dialog | Project view — page actions toolbar | Click **Export…** button | Project | `page_actions.py:104` lambda → `ExportDialog.open()` | Opens the DocTR training export dialog; resets scope radio to "current". |
| C-21 | Export current page (DocTR) | Export dialog | Select scope "Current Page" → click **Export** button | Page | `export_dialog.py:199` `_on_export_clicked` | Exports all validated words on the current page to the DocTR detection + recognition folder structure under `export/{subfolder}/`. |
| C-22 | Export all validated pages (DocTR) | Export dialog | Select scope "All Validated Pages" → click **Export** button | Project | `export_dialog.py:199` `_on_export_clicked` | Loads all saved pages from disk then exports every validated page; skips unvalidated pages (counts them in stats). |
| C-23 | Load all saved pages (lazy, for export) | Export dialog | Scope radio changed to "All Validated Pages" | Project | `export_dialog.py:100` `_on_scope_changed` | Automatically loads all saved pages from disk into memory when "All Validated Pages" scope is selected; one-shot per dialog open. |
| C-24 | Filter export by style | Export dialog | Toggle style checkboxes, then click **Export** | Page / Project | `export_dialog.py:193` `_get_selected_styles` | When specific style checkboxes are checked (not "All"), runs one export per selected style, each into its own subfolder. |
| C-25 | Close export dialog | Export dialog | Click **Close** button | Dialog | `export_dialog.py:79` `dialog.close` | Closes the dialog; any completed export results shown in the results panel remain visible until next open. |
| C-26 | Reload OCR (original image) | Project view — page actions toolbar | Click **Reload OCR** button (`reload-ocr-button`) | Page | `page_view.py:361` `_reload_ocr_async` | Re-runs OCR on the original source page image, replacing all existing OCR results for that page; refreshes both text tabs and image overlay. |
| C-27 | Reload OCR (edited/erased image) | Project view — page actions toolbar | Click **Reload OCR (Edited)** button (`reload-ocr-edited-button`) | Page | `page_view.py:407` `_reload_ocr_edited_async` | Re-runs OCR on the current in-memory edited (erase-ops applied) image rather than the original source file. |
| C-28 | Rematch ground truth | Project view — page actions toolbar | Click **Rematch GT** button (`rematch-gt-button`) | Page | `page_view.py:454` `_rematch_gt_async` | Re-runs the bulk GT text matching algorithm from the source text file, discarding all per-word manual GT edits; notifies if no source text available. |
| C-29 | Refine all bboxes on page | Word match toolbar — Page row | Click `auto_fix_high` icon in Page row (tooltip: "Refine all bounding boxes on this page") (`page-refine-bboxes-button`) | Page | `word_match_toolbar.py:99` → `page_view.py:308` `_refine_bboxes_async` | Runs the bbox-refinement algorithm on every word on the current page; replaces bounding boxes with tighter-fitting ones. |
| C-30 | Expand + refine all bboxes on page | Word match toolbar — Page row | Click `zoom_out_map` icon in Page row (tooltip: "Expand then refine all bounding boxes on this page") (`page-expand-refine-bboxes-button`) | Page | `word_match_toolbar.py:108` → `page_view.py:332` `_expand_refine_bboxes_async` | Expands then tightens every word bbox on the current page; useful when OCR bboxes are slightly too small. |
| C-31 | Open OCR configuration modal | Header | Click `tune` icon button (`ocr-config-trigger-button`) | Global | `ocr_config_modal.py:102` `_open` | Opens the OCR Configuration dialog; rescans available local trainer model directories automatically on open. |
| C-32 | Rescan OCR models | OCR configuration modal | Click **Rescan Models** button (`ocr-rescan-models-button`) | Global | `ocr_config_modal.py:134` `_rescan_models` | Re-scans the pd-ocr-trainer output directory for local fine-tuned model pairs; refreshes the detection and recognition dropdown options. |
| C-33 | Select detection model | OCR configuration modal | Choose from **Detection model** `ui.select` (`ocr-detection-model-select`) | Global | `ocr_config_modal.py:42` (binding) | Picks which detection model weights to use for subsequent OCR runs (HF default or a local fine-tuned model). |
| C-34 | Select recognition model | OCR configuration modal | Choose from **Recognition model** `ui.select` (`ocr-recognition-model-select`) | Global | `ocr_config_modal.py:49` (binding) | Picks which recognition model weights to use for subsequent OCR runs. |
| C-35 | Pin Hugging Face model revision | OCR configuration modal | Type into **Hugging Face revision pin** input (`ocr-hf-revision-input`) and click **Apply** | Global | `ocr_config_modal.py:167` `_apply_selection` | Pins the HF download to a specific revision tag or commit SHA; empty means always-latest. |
| C-36 | Apply OCR model selection | OCR configuration modal | Click **Apply** button (`ocr-config-apply-button`) | Global | `ocr_config_modal.py:167` `_apply_selection` | Persists the chosen detection/recognition model pair and HF revision pin to `AppState`; subsequent OCR runs use the new selection. |
| C-37 | Cancel OCR configuration | OCR configuration modal | Click **Cancel** button (`ocr-config-cancel-button`) | Dialog | `ocr_config_modal.py:127` `_close` | Closes the dialog without persisting changes to model selection. |
| C-38 | Toggle image overlay — paragraphs layer | Image tabs viewport | Click **Show Paragraphs** checkbox | Page | `image_tabs.py:119` `_set_layer_visibility("paragraphs", ...)` | Shows or hides the green paragraph bounding-box overlay on the viewport image. |
| C-39 | Toggle image overlay — lines layer | Image tabs viewport | Click **Show Lines** checkbox | Page | `image_tabs.py:124` `_set_layer_visibility("lines", ...)` | Shows or hides the pink line bounding-box overlay on the viewport image. |
| C-40 | Toggle image overlay — words layer | Image tabs viewport | Click **Show Words** checkbox | Page | `image_tabs.py:129` `_set_layer_visibility("words", ...)` | Shows or hides the blue word bounding-box overlay on the viewport image. |
| C-41 | Set selection mode — Paragraphs | Image tabs viewport | Click **Select Paragraphs** radio option | Page | `image_tabs.py:137` `_set_selection_mode("paragraph")` | Switches drag-to-select to select whole paragraphs rather than individual words. |
| C-42 | Set selection mode — Lines | Image tabs viewport | Click **Select Lines** radio option | Page | `image_tabs.py:137` `_set_selection_mode("line")` | Switches drag-to-select to select entire lines rather than individual words. |
| C-43 | Set selection mode — Words | Image tabs viewport | Click **Select Words** radio option (default) | Page | `image_tabs.py:137` `_set_selection_mode("word")` | Switches drag-to-select to select individual words (the default mode). |
| C-44 | Erase pixels from page image | Image tabs viewport | Click **Erase Pixels** button, then drag a rectangle | Page | `image_tabs.py:147` `enable_erase_mode()` + `_handle_erase_drag` → `_emit_erase_bbox` | Enters erase mode; after user drags a rectangle, that pixel region is blanked in the in-memory edited image (does not alter the source file). |
| C-45 | Drag-select words (box select, replace) | Image tabs viewport — word mode | Mouse drag on viewport (no modifier) | Page | `image_tabs.py:237` `_handle_viewport_mouse` → `_apply_box_selection` | Selects all words whose bboxes intersect the drawn rectangle, replacing any previous selection. |
| C-46 | Drag-select words (add to selection) | Image tabs viewport — word mode | Ctrl + mouse drag on viewport | Page | `image_tabs.py:256` (drag_add_mode via ctrl) | Adds / toggles words inside the drag rect into the existing selection (symmetric difference). |
| C-47 | Drag-select words (remove from selection) | Image tabs viewport — word mode | Shift + mouse drag on viewport | Page | `image_tabs.py:255` (drag_remove_mode via shift) | Removes words inside the drag rect from the existing selection. |
| C-48 | Validate all words on page | Word match toolbar — Page row | Click `check_circle` icon in Page row (`page-validate-button`) | Page | `word_match_toolbar.py:137` `_handle_validate_page` | Marks every word on the current page as validated (prerequisite for export). |
| C-49 | Unvalidate all words on page | Word match toolbar — Page row | Click `unpublished` icon in Page row (`page-unvalidate-button`) | Page | `word_match_toolbar.py:143` `_handle_unvalidate_page` | Removes the "validated" label from every word on the current page. |
| C-50 | Copy page GT → OCR | Word match toolbar — Page row | Click `content_copy` (flipped) in Page row (`page-copy-gt-to-ocr-button`) | Page | `word_match_toolbar.py:124` → `actions._handle_copy_page_gt_to_ocr` | Copies every word's ground truth text into its OCR text field for the entire page. |
| C-51 | Copy page OCR → GT | Word match toolbar — Page row | Click `content_copy` in Page row (`page-copy-ocr-to-gt-button`) | Page | `word_match_toolbar.py:131` → `actions._handle_copy_page_ocr_to_gt` | Copies every word's OCR text into its ground truth text field for the entire page. |
| C-52 | Set word style (Apply Style) | Word match toolbar — style toolbar | Select style from **Style** dropdown (`apply-style-select`), set **Scope** dropdown (`scope-select`), click **Apply Style** (`apply-style-button`) | Selection | `word_match_toolbar.py:516` `_apply_selected_style` | Applies the chosen style label (italic, small-caps, etc.) to all currently selected words. |
| C-53 | Apply scope to selection | Word match toolbar — style toolbar | Select "Whole" or "Part" from **Scope** dropdown (`scope-select`) | Selection | `word_match_toolbar.py:521` `_apply_scope` | Immediately applies the chosen scope (whole/part) to all selected words. |
| C-54 | Apply component to selection | Word match toolbar — style toolbar | Select from **Component** dropdown (`apply-component-select`), click **Apply Component** (`apply-component-button`) | Selection | `word_match_toolbar.py:526` `_apply_selected_component` | Tags selected words with the chosen component label (footnote marker, drop cap, etc.). |
| C-55 | Clear component from selection | Word match toolbar — style toolbar | Select from **Component** dropdown, click **Clear Component** (`clear-component-button`) | Selection | `word_match_toolbar.py:531` `_clear_selected_component` | Removes the chosen component label from all selected words. |
| C-56 | Add word (draw bbox) | Word match toolbar — add-word toolbar | Click **Add Word** button (`word-add-button`), then drag a rectangle on the viewport | Page | `word_match_toolbar.py:488` → `bbox.handle_start_add_word` | Enters add-word mode; the user drags a rectangle on the viewport to define a new word's bounding box, which is then inserted into the nearest line. |
| C-57 | Session state saved automatically | Background / implicit | Automatic — on project load + page navigation | Global | `session_state_operations.py:57` `save_session_state` | Persists the current project path and page index to `session_state.json` so the next app launch can restore the session. |

---

## Keyboard shortcuts

| Key combo | Action | Context | file:line |
|---|---|---|---|
| `Enter` | Jump to page (triggers `_on_goto`) | Page number input (`nav-page-input`) in project navigation controls | `project_navigation_controls.py:55-58` |
| `Enter` | Navigate the picker to the typed path | Path input (`source-folder-path-input`) in source folder dialog | `project_load_controls.py:60` `_on_source_path_enter` |
| `Enter` | Commit per-word GT edit (inline renderer) | Per-word GT text input (`gt-text-input`) in word match renderer | `word_match_gt_editing.py:68-74` |
| `Tab` | Commit current GT and move focus to next word GT input (forward) | Per-word GT text input in word match renderer | `word_match_gt_editing.py:76-78` `_handle_word_gt_keydown` + `_handle_word_gt_tab_navigation:154` |
| `Shift+Tab` | Commit current GT and move focus to previous word GT input (backward) | Per-word GT text input in word match renderer | `word_match_gt_editing.py:148-152` (shiftKey detection) + `_handle_word_gt_tab_navigation:154` |
| `Enter` | Commit per-word GT edit in word edit dialog | GT input inside Word Edit Dialog (`dialog-gt-input`) | `word_edit_dialog.py:1433` |
| `Escape` | Close any open dialog (Quasar default — no custom handler) | Source folder dialog, OCR config modal, export dialog, word edit dialog | (no registration; Quasar `q-dialog` default unless `persistent` prop is set) |

Notes:
- There is **no** `ui.keyboard` global shortcut handler anywhere in the codebase.
- There are **no** modifier-key (Ctrl, Cmd, Alt) global shortcuts wired at the
  application level. Ctrl/Shift on the image viewport affect drag-select mode
  (add/remove), but those are not registered keyboard shortcuts — they are mouse
  modifier checks on the drag event.
- The OCR config modal HF revision input intentionally has no `Enter` handler
  (apply requires the explicit Apply button).

---

## User paths

1. **First launch — configure source folder and load a project**
   1. App opens at `/`; "No Project Loaded" placeholder shown.
   2. Click `folder_open` icon (C-01) → source folder dialog opens.
   3. Browse using breadcrumbs / child-directory buttons (C-02), **Home** (C-03), **Up** (C-04), or type a path and press **Enter** / click **Open Typed Path** (C-05/keyboard shortcut).
   4. Click **Use Current** (C-06) to copy the browsed path into the input.
   5. Click **Apply** (C-07) → config.yaml updated, project dropdown refreshed.
   6. Choose a project from the **Project** dropdown (C-09).
   7. Click **LOAD** (C-10) → project loads, browser URL updated to `/project/{key}`.
   8. First page displayed with OCR run automatically.

2. **Navigate pages and save progress**
   1. With a project loaded, click **Next** (C-15) or **Prev** (C-14) to move between pages.
   2. Type a page number in the page input and press **Enter** or click **Go To:** (C-16, keyboard) to jump.
   3. Review/edit GT text on the current page.
   4. Click **Save Page** (C-17) to persist the current page's edits.
   5. Click **Save Project** (C-18) to batch-save all loaded pages at once.

3. **Re-OCR a page (after erasing noise)**
   1. Navigate to a page with image artifacts.
   2. Click **Erase Pixels** (C-44); drag a rectangle over the noise region on the viewport image — the region is blanked in-memory.
   3. Click **Reload OCR (Edited)** (C-27) → OCR re-runs on the edited image; word list updates.
   4. Alternatively, click **Reload OCR** (C-26) to re-OCR from the original source image, discarding pixel edits.

4. **Select and configure OCR models**
   1. Click the `tune` icon in the header (C-31) → OCR Configuration dialog opens; models rescanned automatically.
   2. Optionally click **Rescan Models** (C-32) to re-scan after trainer output changes.
   3. Choose from **Detection model** (C-33) and **Recognition model** (C-34) dropdowns.
   4. Optionally type a Hugging Face revision tag in the HF revision pin input (C-35).
   5. Click **Apply** (C-36) → model selection persisted; click **Cancel** (C-37) to discard.
   6. Run **Reload OCR** (C-26) on a page to use the newly selected models.

5. **Validate and export DocTR training data**
   1. Navigate to each page and validate all words via the **Validate page** button in the toolbar (C-48), or validate at paragraph/line/word scope.
   2. Click **Export…** in the page actions toolbar (C-20) → export dialog opens.
   3. Select scope: **Current Page** or **All Validated Pages** (C-21/C-22).
      - Selecting "All Validated Pages" triggers an automatic load of all saved pages from disk (C-23).
   4. Optionally filter by style using checkboxes (C-24) — one export run per selected style.
   5. Click **Export** button → DocTR-format detection + recognition directories written to `export/{subfolder}/` in the project directory; stats shown in dialog.
   6. Click **Close** (C-25) to dismiss.

6. **Deep-link to a specific page**
   1. Navigate to `/project/{project_id}` → project loaded at page 1 (C-12).
   2. Navigate to `/project/{project_id}/page/{page_id}` → project loaded and navigated to the 1-based page number (C-13).
   3. After any in-app page navigation the browser URL is updated via `history.replace` to reflect the current project and page, enabling copy-share of deep links.

7. **Session restore on restart**
   1. App launched without a CLI `project_dir` argument.
   2. `session_state.json` is read (C-57/C-11); if the last project directory still contains images, `load_project` runs in background to the last page index.
   3. User lands directly on the previously viewed page without any manual action.

---

## Cross-dimension spillover

The following actions were encountered but are classified under other dimensions:

- **B (per-content edits):** Per-word GT text editing (inline input, Tab/Enter navigation), word merge/split/delete/crop/nudge in the Word Edit Dialog, apply-style/apply-component/validate per word/line/paragraph, bbox fine-tune nudge buttons. These mutate word content rather than system state.
- **A (screen layout / nav chrome):** Show/hide overlay layers checkboxes (paragraphs/lines/words) straddle A and C — they are viewport display controls but also affect the current page's visible selection state. Listed in C because they directly control the image viewport rendering mode. Tab switches (Matches / Ground Truth / OCR text tabs) are dimension A.
- **B/C boundary — Refine bboxes:** Refine/expand-refine at the Paragraph, Line, and Word scope are structural edits on selected elements (dimension B). Refine/expand-refine at the **Page** scope (C-29, C-30) are treated as system/batch operations in this audit because they operate on the entire page without requiring selection.

---

## Coverage self-check

### Source files scanned

| File | Relevant to dim-C? | Notes |
|---|---|---|
| `pd_ocr_labeler/app.py` | Yes | URL routing, session restore, `_initialize_from_url` |
| `pd_ocr_labeler/cli.py` | Marginal | CLI entry point; configures host/port/font — no UI actions |
| `pd_ocr_labeler/routing.py` | Yes | URL path parsing and browser-URL sync |
| `pd_ocr_labeler/views/header/header.py` | Yes | Orchestrates header bar |
| `pd_ocr_labeler/views/header/project_load_controls.py` | Yes | Source folder dialog, project select, LOAD button |
| `pd_ocr_labeler/views/header/ocr_config_modal.py` | Yes | OCR model config dialog |
| `pd_ocr_labeler/views/main_view.py` | Yes | Top-level view orchestration, project-loading overlay |
| `pd_ocr_labeler/views/projects/project_view.py` | Yes | Prev/Next/GoTo navigation, busy spinner, URL sync |
| `pd_ocr_labeler/views/projects/project_navigation_controls.py` | Yes | Navigation buttons and page input |
| `pd_ocr_labeler/views/projects/pages/page_view.py` | Yes | Save/Load/ReloadOCR/RematchGT/Refine-bbox async handlers |
| `pd_ocr_labeler/views/projects/pages/page_actions.py` | Yes | Page action button bar (save, load, export, reload-ocr) |
| `pd_ocr_labeler/views/projects/pages/export_dialog.py` | Yes | DocTR export dialog — scope, style filter, export |
| `pd_ocr_labeler/views/projects/pages/image_tabs.py` | Yes | Layer visibility, selection mode, erase mode, drag-select modifiers |
| `pd_ocr_labeler/views/projects/pages/word_match_toolbar.py` | Yes | Page/paragraph/line/word scope action grid, style/component toolbar, add-word |
| `pd_ocr_labeler/views/projects/pages/word_match_gt_editing.py` | Yes | Tab/Enter keyboard shortcuts on GT inputs |
| `pd_ocr_labeler/views/projects/pages/word_edit_dialog.py` | Partial | Enter keyboard shortcut on dialog GT input only (rest is dim-B) |
| `pd_ocr_labeler/views/projects/pages/text_tabs.py` | Marginal | Text editor tabs — display only; no system actions |
| `pd_ocr_labeler/views/projects/pages/content.py` | Marginal | Layout; no direct system actions |
| `pd_ocr_labeler/views/projects/pages/word_match.py` | Marginal | Per-word view; dim-B content actions |
| `pd_ocr_labeler/views/projects/pages/word_match_actions.py` | Marginal | Per-selection actions; dim-B |
| `pd_ocr_labeler/views/projects/pages/word_match_bbox.py` | Marginal | Per-word bbox editing; dim-B |
| `pd_ocr_labeler/views/projects/pages/word_match_renderer.py` | Marginal | Per-line/word rendering; dim-B |
| `pd_ocr_labeler/views/projects/pages/word_match_selection.py` | Marginal | Selection bookkeeping; dim-B |
| `pd_ocr_labeler/operations/persistence/config_operations.py` | Yes | Config read/write for `source_projects_root` |
| `pd_ocr_labeler/operations/persistence/session_state_operations.py` | Yes | Session save/restore |
| `pd_ocr_labeler/operations/persistence/project_discovery_operations.py` | Yes | Project scanning logic |
| `pd_ocr_labeler/operations/persistence/project_operations.py` | Yes | Save/load/export project mechanics |
| `pd_ocr_labeler/operations/export/doctr_export.py` | Yes | DocTR export format implementation |
| `pd_ocr_labeler/operations/ocr/ocr_service.py` | Marginal | OCR execution backend; no UI |
| `pd_ocr_labeler/state/app_state.py` | Yes | OCR model key state |
| `pd_ocr_labeler/state/project_state.py` | Marginal | Project/page state machine |
| `docs/architecture/ui-action-buttons.md` | Yes | Authoritative existing inventory; used for cross-reference |
| `docs/archive/research/2026-05-06-keyboard-shortcuts-coverage.md` | Yes | Prior keyboard audit; used for cross-reference |

### Confirmed gaps

- **No undo/redo:** There is no undo/redo stack anywhere in the codebase. Bulk operations (validate-page, copy-GT-to-OCR) are irreversible without a page reload from saved data. This is a genuine absence, not a gap in this audit.
- **No global search / find:** No global text search or cross-page search exists. This is a genuine absence.
- **No import:** No UI for importing external data (no `ui.upload`, no file-import dialog). Projects are discovered by filesystem scan only.
- **No vocabulary/dictionary management screen:** No standalone vocab screen exists. Style and component labels are applied inline via the toolbar dropdowns; there is no screen dedicated to managing a dictionary or vocabulary. (The new SPA has this in M4+ — the legacy does not.)
- **No jobs / progress panel:** Long-running operations (OCR, export) surface progress only through `ui.notify` toast notifications and the full-screen busy overlay spinner. There is no dedicated jobs panel or queue view.
- **No session/auth:** The app is a single-user local web server with no authentication. Multi-tab isolation is achieved by per-session Python state objects, not by any auth mechanism.
- **No zoom/pan controls:** The viewport image has no zoom or pan UI. The image is displayed at native resolution (scaled to max 1200 px on the long edge); users scroll the browser window. No zoom buttons, pinch-zoom, or fit-to-window controls exist in the codebase.
- **No rotate/flip:** No page image rotation or flip controls exist in this legacy repo. (These were added in the SPA as M9.1/M9.2.)
- **No auto-rotate-all:** Absent. Confirmed by full grep of `rotate`, `flip` in the source tree — zero matches.

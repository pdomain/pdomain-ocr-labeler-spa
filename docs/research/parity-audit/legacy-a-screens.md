# Legacy pd-ocr-labeler — Dimension A: Screens, Navigation & Chrome

---

## Screens & panels

| Screen/Panel | Purpose | How reached (route / nav / trigger) | Defining file:line |
|---|---|---|---|
| **Root/Index page** | Single-page shell that hosts all UI; shown immediately on any route | HTTP GET `/` (or any path — NiceGUI SPA) | `app.py:366` `@ui.page("/")` |
| **No Project Loaded placeholder** | Full-content area centered message: icon + "No Project Loaded" + instruction text | Shown by default when `show_placeholder=True` (no project loaded); hidden when a project loads | `main_view.py:54–62` |
| **Project-loading overlay** | Full-viewport blur + centered spinner, covers entire UI | Shown automatically via `is_project_loading=True` binding when any project is loading | `main_view.py:65–73` |
| **Project view** | Container for project navigation controls + page view; replaces placeholder when project is loaded | Programmatically built and shown when `show_project_view=True` (project loaded successfully) | `main_view.py:140–148`, `project_view.py:59` |
| **Page-busy overlay** | Full-viewport semi-transparent blur + spinner; covers project view during long operations | Shown via `is_busy=True` binding during OCR/save/navigation actions | `project_view.py:79–87` |
| **Project navigation bar** | Horizontal row: Prev / Next / Go To buttons + page number input + total pages label | Always visible inside project view once project is loaded | `project_navigation_controls.py:36–93` |
| **Page actions toolbar** | Horizontal row of per-page action buttons: Reload OCR, Reload OCR (Edited), Save Page, Save Project, Load Page, Rematch GT, Export…, page name label, page source label | Always visible inside project view; below nav bar | `page_actions.py:56–139` |
| **Content area (splitter)** | 50/50 horizontal splitter: left = ImageTabs viewport, right = TextTabs | Always visible (hidden by page-spinner during loading); built as part of project view | `content.py:197–208` |
| **Page navigation spinner** (inline) | Small centered spinner inside content area; replaces splitter while page is loading | Shown during page-level navigation/OCR start, hidden when content is ready | `content.py:192–195`, `page_view.py:148–155` |
| **ImageTabs / OCR Viewport** | Left pane of splitter: single interactive image with layer toggles (Show Paragraphs / Lines / Words), selection mode radio (Paragraph / Line / Word), legend badges, Erase Pixels button, SVG bbox overlays | Always left half of content splitter; part of loaded project view | `image_tabs.py:113–200` |
| **TextTabs right pane** | Right pane of splitter; contains actions toolbar + 3 named tabs (Matches, Ground Truth, OCR) | Always right half of content splitter | `text_tabs.py:480–543` |
| **Matches tab** | Word-level OCR vs Ground Truth comparison panel; shows paragraph/line/word filter toggle, scrollable line cards | Default active tab in TextTabs; click "Matches" tab to reach | `text_tabs.py:500–508`, `word_match.py:224–249` |
| **Ground Truth tab** | Full-page read-only CodeMirror editor showing GT text | Click "Ground Truth" tab in TextTabs | `text_tabs.py:509–518` |
| **OCR tab** | Full-page read-only CodeMirror editor showing OCR text | Click "OCR" tab in TextTabs | `text_tabs.py:519–528` |
| **Word-match actions toolbar** (inside Matches) | 4-row icon grid (Page / Paragraph / Line / Word operations) + Apply Style row + Add Word row; shown above filter toggle inside the Matches tab right panel | Always rendered inside TextTabs; visible within Matches tab content area | `text_tabs.py:486–488`, `word_match_toolbar.py:86–491` |
| **Stats/export status bar** | Single row: analytics icon + match summary text + optional export status text; above the content splitter | Always visible when project is loaded | `content.py:166–189` |

---

## Global chrome

| Element | Location | Contents | file:line |
|---|---|---|---|
| **Header bar** (`ui.header`) | Top of every page, sticky | Project selector row (see below) | `header.py:30–33` |
| **Project select dropdown** | Left side of header bar | `ui.select` labeled "Project"; lists all discovered project keys | `project_load_controls.py:91–97` |
| **LOAD button** | Header bar, right of project select | Loads selected project; disabled while loading | `project_load_controls.py:100–102` |
| **Source folder button** (folder_open icon) | Header bar, right of LOAD button | Opens the Source Projects Folder dialog | `project_load_controls.py:104–108` |
| **OCR config (tune icon) button** | Header bar, right of source folder button | Opens the OCR Configuration modal | `project_load_controls.py:110`, `ocr_config_modal.py:90–92` |
| **Resolved project path label** | Right-aligned in header bar | Shows fully resolved filesystem path of the currently loaded project | `project_load_controls.py:114–118` |
| **Toast notifications** | Floating overlay, z-index 100000 | Short status messages (positive / negative / warning / info) from all operations | `app.py:214–221`, `main_view.py:167–184` |

---

## Modals & dialogs

| Dialog | Opened by | Purpose | file:line |
|---|---|---|---|
| **Source Projects Folder dialog** | Clicking the `folder_open` header button | Browse and select the root directory that is scanned for project subdirectories; includes path input, breadcrumb nav, subdirectory list scroll area, Home / Up / Open Typed Path / Use Current / Cancel / Apply buttons | `project_load_controls.py:44–83` (build), `project_load_controls.py:205–225` (open trigger) |
| **OCR Configuration modal** | Clicking the `tune` icon header button | Select detection model, recognition model, pin a Hugging Face revision; Rescan Models / Cancel / Apply buttons | `ocr_config_modal.py:29–100` (build), `ocr_config_modal.py:102–126` (open) |
| **Export to DocTR Training Format dialog** | Clicking "Export…" in page actions toolbar | Choose export scope (Current Page / All Validated Pages), style filter checkboxes (All + per-style), Export button, results area, Close button | `export_dialog.py:40–81` (build), `page_actions.py:105` (open trigger) |
| **Word Edit dialog** | Clicking on a word image in the Matches panel | Per-word editing: shows Previous / Current / Next word images at configurable zoom (1×/2×/5×/10×), GT text input, style/scope/component selects, Apply Style + Apply Component buttons, tag chips with clear buttons, horizontal/vertical split tools, bbox nudge controls, erase-pixel controls, Apply+Close / Close buttons | `word_edit_dialog.py:326–1511+` (class `WordEditDialog`), opened via `word_match_renderer.py` word image click handlers |

---

## Navigation map

- **App bootstrap → No Project Loaded placeholder**: On first load (no CLI project, no session restore), the placeholder is shown.
- **Session restore**: If a prior session is saved, the last-used project loads automatically in the background on `GET /`.
- **URL deep-link → Project page**: `GET /project/{project_id}` or `/project/{project_id}/page/{page_id}` loads the named project and navigates to the given page (1-based). The URL is also updated by the client whenever the page changes.
- **Header: select project + click LOAD → Project view**: Choosing a project from the dropdown and clicking LOAD replaces the placeholder with the project view and updates the browser URL.
- **Project view: Prev / Next buttons → adjacent page**: Clicking Prev or Next navigates to the previous or next page within the loaded project.
- **Project view: Go To button + page number input → arbitrary page**: Typing a page number and clicking Go To (or pressing Enter) navigates to that page.
- **TextTabs: click "Matches" / "Ground Truth" / "OCR" tab → tab panel switch**: Tabs in the right pane switch between the word-match panel and the two read-only text editors.
- **Matches tab: filter toggle ("Unvalidated Lines" / "Mismatched Lines" / "All Lines") → filter word-match list**: Changing the toggle filters visible line cards within the Matches panel.
- **Header source folder button → Source Projects Folder dialog → Apply**: Applying a new source root rescans projects and refreshes the project select dropdown.
- **Header OCR config button → OCR Configuration modal → Apply**: Applying new OCR models takes effect for the next Reload OCR operation.
- **Page actions: Export… → Export dialog**: Opens the export modal.
- **ImageTabs: layer checkboxes and selection-mode radio**: Toggles visual overlays and changes drag-select behavior within the same viewport (no screen change).
- **Word image click in Matches → Word Edit dialog**: Opens the per-word editing modal.

---

## Cross-dimension spillover

The following are content-level edit actions (Dimension B) observed in the source, noted here so nothing is lost:

- **Drag-select on viewport**: Box selection of words / lines / paragraphs using mouse drag on the OCR image (Shift = deselect, Ctrl = toggle). (`image_tabs.py`)
- **Erase Pixels mode**: Toggle and drag to erase a rectangular region from the page image. (`image_tabs.py:146–149`, `image_tabs.py:362–404`)
- **Word-level operations (toolbar)**: Merge, delete, split, refine, expand, form line, form paragraph, copy GT↔OCR, validate/unvalidate — all at Page / Paragraph / Line / Word granularity. (`word_match_toolbar.py`)
- **Per-word editing in Word Edit dialog**: GT text edit, style/scope/component apply, bbox nudge, crop-to-marker, erase-to-marker, split word (horizontal and vertical). (`word_edit_dialog.py`)
- **Page actions**: Save Page, Save Project, Load Page, Reload OCR, Reload OCR (Edited), Rematch GT. (`page_actions.py`)
- **Export scope and style filter selection** inside the Export dialog are content-operation configuration (Dimension C area).
- **Global keyboard bindings scoped to specific inputs** (not global app shortcuts):
  - Enter in page number input triggers Go To navigation. (`project_navigation_controls.py:57`)
  - Enter in source path input triggers path open. (`project_load_controls.py:60`)
  - Enter in GT input inside Word Edit dialog commits the edit. (`word_edit_dialog.py:1433`)
  - Tab/Shift-Tab in GT inline inputs navigates between word GT fields. (`word_match_gt_editing.py:69–78`)

---

## Coverage self-check

### Source files scanned

| File | Scanned |
|---|---|
| `pd_ocr_labeler/app.py` | Full |
| `pd_ocr_labeler/routing.py` | Full |
| `pd_ocr_labeler/cli.py` | Not read (entry-point only; no UI construction) |
| `pd_ocr_labeler/constants.py` | Not read (constants only) |
| `pd_ocr_labeler/prefetch.py` | Not read (background prefetch logic, no UI) |
| `pd_ocr_labeler/views/main_view.py` | Full |
| `pd_ocr_labeler/views/header/header.py` | Full |
| `pd_ocr_labeler/views/header/project_load_controls.py` | Full |
| `pd_ocr_labeler/views/header/ocr_config_modal.py` | Full |
| `pd_ocr_labeler/views/projects/project_view.py` | Full |
| `pd_ocr_labeler/views/projects/project_navigation_controls.py` | Full |
| `pd_ocr_labeler/views/projects/pages/page_view.py` | Full |
| `pd_ocr_labeler/views/projects/pages/content.py` | Full |
| `pd_ocr_labeler/views/projects/pages/image_tabs.py` | Full |
| `pd_ocr_labeler/views/projects/pages/text_tabs.py` | Full |
| `pd_ocr_labeler/views/projects/pages/page_actions.py` | Full |
| `pd_ocr_labeler/views/projects/pages/export_dialog.py` | Full |
| `pd_ocr_labeler/views/projects/pages/word_match.py` | Full |
| `pd_ocr_labeler/views/projects/pages/word_match_toolbar.py` | Full |
| `pd_ocr_labeler/views/projects/pages/word_edit_dialog.py` | Lines 1–1511 of 1840; remainder contains further bbox/erase/split controls not changing screen/chrome topology |
| `pd_ocr_labeler/views/projects/pages/word_match_renderer.py` | Referenced; not fully read (renders word cards inline; no new screens/dialogs beyond WordEditDialog already documented) |
| `pd_ocr_labeler/views/projects/pages/word_match_gt_editing.py` | Referenced for keyboard spillover; not fully read |
| `pd_ocr_labeler/views/projects/pages/word_match_bbox.py` | Not read (bbox calculation helpers; no new UI screens) |
| `pd_ocr_labeler/views/projects/pages/word_match_selection.py` | Not read (selection state management; no new screens) |
| `pd_ocr_labeler/views/projects/pages/word_match_actions.py` | Not read (action dispatchers; no new screens) |
| `pd_ocr_labeler/views/projects/pages/word_operations.py` | Not read (word mutation helpers; no new screens) |
| `pd_ocr_labeler/views/callbacks.py` | Not read (callback type definitions only) |
| `pd_ocr_labeler/views/shared/base_view.py` | Not read (base class; no UI construction) |
| `pd_ocr_labeler/views/shared/button_styles.py` | Not read (style helpers only) |
| `pd_ocr_labeler/views/shared/view_helpers.py` | Not read (mixin helpers only) |
| `pd_ocr_labeler/state/app_state.py` | Not read (state layer; no UI) |
| `pd_ocr_labeler/state/page_state.py` | Not read (state layer; no UI) |
| `pd_ocr_labeler/state/project_state.py` | Not read (state layer; no UI) |
| `pd_ocr_labeler/viewmodels/**` | Not read (ViewModel layer; no UI construction) |
| `pd_ocr_labeler/models/**` | Not read (data models; no UI) |
| `pd_ocr_labeler/operations/**` | Not read (business logic; no UI) |
| `pd_ocr_labeler/services/notification_service.py` | Not read (service layer; no UI) |
| `docs/architecture/*.md` | Not read for this audit |

### Possible gaps

- The last ~330 lines of `word_edit_dialog.py` (lines 1512–1840) were not read due to token limits. These contain additional bbox-nudge and erase-pixel UI controls rendered *inside* the already-documented Word Edit dialog. No new top-level screens or modals are expected there, but specific sub-controls (crop buttons, erase-to-marker buttons) may not be fully enumerated under the B/C spillover list.
- `word_match_renderer.py` was not fully read; it builds inline word card UI. No new dialogs beyond `WordEditDialog` are expected, but any additional popovers or inline expansion widgets within word cards are not catalogued here.
- Keyboard shortcut coverage is limited to what surfaced in visible `on("keydown.*")` calls; no `ui.keyboard` global shortcut handlers were found in any file.

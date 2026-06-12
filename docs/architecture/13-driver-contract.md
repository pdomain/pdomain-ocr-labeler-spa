# 13 — Driver-Compatibility Contract

> **Status**: Active
> **Last updated**: 2026-05-11
> **Spec-Issue**: pdomain/pdomain-ocr-labeler-spa#30

The `pd-ocr-labeler-driver` agent operates the labeler UI through
Playwright. It uses **stable `data-testid` attributes** and **stable
URL paths** to find and click things. The SPA must preserve every
testid and URL shape from the legacy labeler.

This document is the canonical list. If the SPA implementation
diverges, **the SPA is wrong**, not this document.

> Cross-refs:
> Legacy testid catalogue —
> `pd-ocr-labeler/docs/architecture/ui-action-buttons.md`
> Legacy URL helpers —
> `pd-ocr-labeler/pd_ocr_labeler/routing.py`
> Driver agent — `.claude/agents/pd-ocr-labeler-driver.md`

---

## 1. URL invariants

**D-030 changed the URL grammar from the legacy form.** The pgdp-prep
plural convention is canonical; legacy paths 301-redirect.

### 1.1 Canonical (new) routes

| Path | When | Behaviour |
|---|---|---|
| `/` | No project loaded | Show `<EmptyProjectState>` + visible header |
| `/` | Last project in `session_state.json` | Redirect to `/projects/{id}/pages/pageno/{n}` (last page) |
| `/projects/{project_id}` | — | Same as `/projects/{project_id}/pages/pageno/1` |
| `/projects/{project_id}/pages/pageno/{n}` | — | Open project, navigate to page (1-based) |
| `/projects/{project_id}/pages/index/{idx0}` | — | Open project, navigate to page (0-based) |
| `/projects/{project_id}/pages/{n}` | — | `301 → pages/pageno/{n}` |

`pageno` and `index` are **explicit sub-routes** to disambiguate. The
canonical URL the SPA emits to the browser bar is the `pageno` form
(human-friendly).

### 1.2 Legacy redirects (compat)

| Legacy path | Status | Target |
|---|---|---|
| `/project/{id}` | `301` | `/projects/{id}` |
| `/project/{id}/page/{n}` | `301` | `/projects/{id}/pages/pageno/{n}` |

All legacy redirects emit `301 Moved Permanently` per
[D-035](../../specs/17-decisions.md) (resolves Q-A4). 308 was on the table but
offers no benefit for the GET-only SPA routes here.

### 1.3 Edge cases

If `{project_id}` doesn't match a discovered project, render an inline
"Project not found" message inside the chrome — **don't** 404 the
route. The driver agent expects the chrome to remain.

Browser history: every navigation from one page to another within a
project replaces the URL via `router.navigate(... , { replace: true })`,
matching the legacy `ui.navigate.history.replace(...)` behaviour.
Cross-project navigation pushes a new history entry.

### 1.4 Driver-agent migration

The driver agent (`pd-ocr-labeler-driver`) currently issues legacy
URLs (`/project/{id}/page/{n}`). After M2 ships, the driver should
update to emit canonical URLs directly (avoid the redirect roundtrip),
but legacy URLs continue to work indefinitely via the 301.

---

## 2. Stable `data-testid` catalogue

Every entry below must exist in the SPA after a project is loaded.
Any testid the legacy has that we want to retire requires
[OPEN_QUESTIONS.md](../../OPEN_QUESTIONS.md) approval before it's dropped.

### 2.1 Header bar / project load

> **D-046 (2026-05-21):** The legacy inline header controls have been
> deprecated and removed (see `specs/17-decisions.md` D-046). The driver
> must reach these controls at their new locations as documented below.

| Control | New location | New testid(s) |
|---|---|---|
| Project dropdown | `ProjectLoadControls.tsx` on RootPage | `project-select` (real) |
| LOAD button | `ProjectLoadControls.tsx` on RootPage | `load-project-button` (real) |
| Source folder button | `ProjectLoadControls.tsx` (breadcrumb mode) | `source-folder-button` (real) |
| OCR config trigger | `PageActionsCompact.tsx` on project routes | `ocr-config-trigger-button` (real); field stubs still in HeaderBar hidden div |
| Export trigger | `PageActionsCompact.tsx` / `PageActions.tsx` | `page-actions-compact-export` / `export-button` |
| Hotkey help trigger | Rail footer (`Rail.tsx`) | `rail-hotkeys-button` |

The project-load trio (`project-select`, `load-project-button`,
`source-folder-button`) are real controls inside `ProjectLoadControls`,
rendered on the RootPage and in breadcrumb mode on project routes. The
source-folder dialog fields (§2.2) and OCR-config modal fields (§2.3)
continue to have stubs in the HeaderBar hidden div.

> **#405 (2026-05-22):** `ocr-config-trigger-button` is restored as a real button
> in `PageActionsCompact.tsx`, available on every project route. It was inadvertently
> left without a user-facing trigger by D-046 / #401.

### 2.2 Source folder dialog

| Testid | What it is |
|---|---|
| `source-folder-current-path-label` | Read-only path label at top |
| `source-folder-path-input` | Text input |
| `source-folder-home-button` | Home button |
| `source-folder-up-button` | Up button |
| `source-folder-open-typed-button` | Open Typed Path button |
| `source-folder-use-current-button` | Use Current button |
| `source-folder-cancel-button` | Cancel |
| `source-folder-apply-button` | Apply |

Hotkey: `Enter` on the path input triggers `source-folder-open-typed-button`.

### 2.3 OCR config modal

> **#405 (2026-05-22):** `ocr-config-trigger-button` is restored as a real visible button
> in `PageActionsCompact.tsx` on project routes (fix for D-046 regression). Click it to
> open the OCR-config modal. The `ocr-config-trigger-button` in the HeaderBar hidden stub
> div is no longer present. The modal field stubs (below) remain in the HeaderBar hidden div.
> The modal itself uses `data-testid="ocr-config-modal"`.

| Testid | What it is |
|---|---|
| `ocr-detection-model-select` | Detection model select (stub in HeaderBar; real when modal open) |
| `ocr-recognition-model-select` | Recognition model select |
| `ocr-hf-revision-input` | HF revision input |
| `ocr-rescan-models-button` | Rescan Models button |
| `ocr-config-cancel-button` | Cancel |
| `ocr-config-apply-button` | Apply |

### 2.4 Project navigation

| Testid | What it is |
|---|---|
| `nav-prev-button` | Prev |
| `nav-next-button` | Next |
| `nav-goto-button` | Go To: button |
| `nav-page-input` | Page number `<input type="number">` |
| `nav-page-total-label` | "/ N" total label |

Hotkey: `Enter` on `nav-page-input` triggers `Go To`.

### 2.5 Page actions

| Testid | What it is |
|---|---|
| `reload-ocr-button` | Reload OCR |
| `reload-ocr-edited-button` | Reload OCR (Edited) |
| `save-page-button` | Save Page |
| `save-project-button` | Save Project |
| `load-page-button` | Load Page |
| `rematch-gt-button` | Rematch GT |
| `export-button` | Export... |
| `page-source-badge` | The badge ("LABELED" / "CACHED OCR" / "RAW OCR" / "LOADING…") |
| `page-name-label` | Filename label |

### 2.6 Image tabs (left pane)

| Testid | What it is |
|---|---|
| `layer-paragraphs-checkbox` | Show Paragraphs |
| `layer-lines-checkbox` | Show Lines |
| `layer-words-checkbox` | Show Words |
| `selection-mode-paragraph` | Radio: Paragraph |
| `selection-mode-line` | Radio: Line |
| `selection-mode-word` | Radio: Word |
| `erase-pixels-button` | Erase Pixels mode toggle |
| `mismatches-only-toggle` | Toggle: dim exact/validated word bboxes (Issue #295) |
| `zoom-fit-button` | Fit page to viewport width |
| `zoom-100-button` | 100% zoom (1:1 pixel) |
| `image-viewport` | The Konva `<Stage>`'s outer wrapper div |

Drag rectangle CSS class: `.ocr-drag-rect` (legacy CSS class
preserved for any external script that might style it).

### 2.7 Text tabs / right pane

These are right-pane `TextTabs.tsx` tab triggers, not image-viewport
overlays. The decision not to add image-viewport text-overlay sub-tabs
is recorded in `specs/17-decisions.md` D-045 (2026-05-16). These
testids are live in the SPA and must be preserved per D-014.

| Testid | What it is |
|---|---|
| `text-tab-matches` | Tabs trigger: Matches (right pane) |
| `text-tab-ground-truth` | Tabs trigger: Ground Truth (right pane) |
| `text-tab-ocr` | Tabs trigger: OCR (right pane) |
| `match-filter-toggle` | The Unvalidated/Mismatched/All toggle |
| `match-filter-unvalidated` | Toggle option: Unvalidated |
| `match-filter-mismatched` | Toggle option: Mismatched |
| `match-filter-all` | Toggle option: All |

### 2.8 Word match view (per-line card)

For line index `n` (0-based):

| Testid | What it is |
|---|---|
| `line-card-{n}` | The whole card |
| `paragraph-checkbox-{p}` | Paragraph checkbox in the line's paragraph header (only on paragraph-first lines) |
| `line-checkbox-{n}` | Line selection checkbox |
| `line-gt-to-ocr-button-{n}` | GT→OCR |
| `line-ocr-to-gt-button-{n}` | OCR→GT |
| `line-validate-button-{n}` | Validate / Unvalidate |
| `line-delete-button-{n}` | Delete (line) |

For each word at `(line_index=l, word_index=w)`:

| Testid | What it is |
|---|---|
| `word-checkbox-{l}-{w}` | Word selection checkbox |
| `edit-word-button-{l}-{w}` | Pencil-icon edit button |
| `word-validate-button-{l}-{w}` | Per-word validate |
| `gt-text-input-{l}-{w}` | GT input field |
| `ocr-text-label-{l}-{w}` | OCR text label |
| `word-status-icon-{l}-{w}` | Status icon (check/warning/cancel/help/info) |
| `word-image-cell-{l}-{w}` | Image cell wrapper (for hover/click handlers) |
| `word-tag-chip-{l}-{w}-{label}` | Style/component chip (one per active label, label is normalised key like `italics`) |
| `word-tag-clear-button-{l}-{w}-{label}` | × on a chip |

The `{l}-{w}` suffix matches the legacy convention. The driver
agent already parses these.

### 2.9 Toolbar action grid

The grid has 14 columns × 4 rows. Cell testid is
`toolbar-{scope}-{action}` where:

- `{scope}` ∈ `page | paragraph | line | word`
- `{action}` ∈ `merge | refine | expand-refine | expand-bboxes |
  split-after | split-selected | word-to-line | to-paragraph |
  gt-to-ocr | ocr-to-gt | validate | unvalidate | delete`

So e.g. `toolbar-page-refine` = "Refine all bboxes on this page".
`toolbar-line-validate` = "Validate selected lines".

Cells the legacy doesn't have (e.g. `toolbar-word-merge` —
word-merge is in the dialog) are `display: none` but the testid
still exists, with `data-testid-stub="true"` so the driver can
distinguish "not present" from "stubbed".

### 2.10 Apply Style toolbar row

| Testid | What it is |
|---|---|
| `apply-style-select` | Style select |
| `scope-select` | Scope select (whole / part) |
| `apply-style-button` | Apply Style |
| `apply-component-select` | Component select |
| `apply-component-button` | Apply Component |
| `clear-component-button` | Clear Component |
| `word-add-button` | Add Word |

### 2.11 Word edit dialog

| Testid | What it is |
|---|---|
| `word-edit-dialog` | Outer Radix Dialog wrapper |
| `dialog-header-label` | "Edit Line N, Word M" |
| `dialog-apply-close-button` | check-icon (top-right) |
| `dialog-close-button` | close-icon (top-right) |
| `dialog-previous-preview-column` | Left preview column |
| `dialog-current-preview-column` | Centre column |
| `dialog-next-preview-column` | Right preview column |
| `dialog-tag-chips-slot` | Container for tag chips |
| `dialog-current-zoom-toggle` | 1x/2x/5x/10x toggle |
| `dialog-gt-input` | GT input inside dialog |
| `dialog-style-select` | Style select |
| `dialog-scope-select` | Scope select |
| `dialog-component-select` | Component select |
| `dialog-apply-style-button` | Apply Style |
| `dialog-apply-component-button` | Apply Component |
| `dialog-clear-component-button` | Clear Component |
| `dialog-merge-prev-button` | Merge Prev |
| `dialog-merge-next-button` | Merge Next |
| `dialog-split-h-button` | H |
| `dialog-split-v-button` | V |
| `dialog-delete-word-button` | Delete |
| `dialog-crop-above-button` | Crop Above |
| `dialog-crop-below-button` | Crop Below |
| `dialog-crop-left-button` | Crop Left |
| `dialog-crop-right-button` | Crop Right |
| `dialog-refine-button` | Refine (preview) |
| `dialog-expand-refine-button` | Expand + Refine (preview) |
| `dialog-nudge-{edge}-{sign}-button` | 8 nudge buttons (edge ∈ left/right/top/bottom, sign ∈ minus/plus) |
| `dialog-reset-button` | Reset |
| `dialog-apply-button` | Apply |
| `dialog-apply-refine-button` | Apply + Refine |

Hotkey: `Enter` on `dialog-gt-input` commits.

### 2.12 Export dialog

| Testid | What it is |
|---|---|
| `export-dialog` | Outer dialog wrapper |
| `export-scope-current` | Scope radio: Current Page |
| `export-scope-all` | Scope radio: All Validated Pages |
| `export-style-all-checkbox` | "All (no style filter)" checkbox |
| `export-style-checkbox-{key}` | One per style discovered, key = normalised style |
| `export-button` | Export (the run button inside the dialog) |
| `export-cancel-button` | Cancel (replaces Export while a job is running; posts `POST /api/jobs/{id}/cancel`) |
| `export-results` | Container for per-export results |
| `export-close-button` | Close |
| `export-send-to-trainer` | Send to Trainer button (only visible when trainer is installed) |

### 2.13 Notifications + busy

| Testid | What it is |
|---|---|
| `busy-overlay` | The blur overlay during long actions |
| `project-loading-overlay` | The blur overlay during project load |
| `notification-{kind}-{id}` | Sonner toast wrapper. `{kind}` ∈ positive/negative/warning/info; `{id}` is the server-issued id |

The driver agent specifically watches for `notification-negative-*` to
detect operation failures.

### 2.14 Rail — mode + target selectors

The Rail is the 64px left column. It has three sections: MODE, TARGET, and LAYERS (legend only).

| Testid | What it is |
|---|---|
| `rail` | Outer rail container |
| `rail-mode-view` | View mode card (Eye icon + "View") |
| `rail-mode-region` | Refine mode card (Square icon + "Refine") |
| `rail-mode-annotate` | Annotate mode card (Plus icon + "Annotate") |
| `rail-mode-erase` | Erase mode card (Eraser icon + "Erase") |
| `rail-target-block` | Block target cell |
| `rail-target-para` | Para target cell (between line and block) |
| `rail-target-line` | Line target cell |
| `rail-target-word` | Word target cell |
| `rail-bulk-button` | Bulk actions footer button |
| `rail-hotkeys-button` | Keyboard shortcuts footer button (opens hotkey overlay) |

Active cells carry `data-active="true"`. Hotkeys: `1`/`2`/`3`/`4` → block/para/line/word;
`V`/`R`/`A`/`E` → view/region/annotate/erase.

### 2.15 Glyph annotations (spec `specs/20-glyph-annotations.md §7`, issue #270)

Parameterised testids use `{line}` and `{word}` (0-based indices matching the
word's position in the page line-match list).

| Testid | What it is |
|---|---|
| `word-glyph-badge-{line}-{word}` | Corner badge on `<WordCell>`; absent when no annotations/predictions |
| `word-glyph-chip-row-{line}-{word}` | Chip row under GT input |
| `word-glyph-chip-{line}-{word}-{kind}` | Individual chip (`kind` ∈ `ct`, `st`, `long_s`, `fi`, `swash`, `predicted-{kind}`) |
| `glyph-panel-{line}-{word}` | The `<GlyphAnnotationPanel>` popover/section |
| `glyph-panel-add-ligature` | "Add ligature" button inside panel |
| `glyph-panel-ligature-kind-select` | Ligature kind enum picker |
| `glyph-panel-charspan-cell-{i}` | i-th char-cell in the span picker |
| `glyph-panel-long-s-cell-{i}` | i-th char-cell in the long-s picker |
| `glyph-panel-swash-checkbox` | Swash toggle |
| `glyph-panel-mark-reviewed-empty` | "Mark reviewed (no marks)" button |
| `glyph-panel-reset` | "Reset" → set annotations back to None |
| `glyph-panel-accept-prediction-{kind}` | Accept a single predicted mark |
| `glyph-panel-reject-prediction-{kind}` | Reject a single predicted mark |
| `bulk-glyph-mark-button` | Toolbar entry that opens the bulk dialog |
| `bulk-glyph-mark-dialog` | The `<BulkGlyphMarkDialog>` |
| `bulk-glyph-recipe-select` | Recipe dropdown |
| `bulk-glyph-skip-annotated-checkbox` | "Skip already annotated" |
| `bulk-glyph-accept-predictions-checkbox` | "Also confirm matching predictions" |
| `bulk-glyph-dry-run-button` | Preview button |
| `bulk-glyph-apply-button` | Apply button |
| `bulk-glyph-preview-count` | Span containing preview count text (e.g. `47 words will be modified`) |

The `{line}-{word}` suffix matches the legacy `gt-text-input-{l}-{w}` convention.
Parameterised testids above (`*-{line}-{word}`, `*-{kind}`, `*-{i}`) exist for
specific values only; the conformance test asserts the static/trigger testids.

### 2.16 MultiLineDetail (multi-line selection)

Rendered in the right panel when `selectedLines.length > 1`.
`{n}` is the 0-based `line_index` of each selected line.

| Testid | What it is |
|---|---|
| `multi-line-detail` | Outer container |
| `multi-line-card-{n}` | Card for line `n` (`data-line-index={n}`) |
| `multi-line-bulk-bar` | Sticky bulk-action bar |
| `multi-line-bulk-validate` | Validate all words in all selected lines |
| `multi-line-bulk-unvalidate` | Unvalidate all words in all selected lines |
| `multi-line-bulk-copy-ocr-to-gt` | Copy OCR→GT for all selected lines |
| `multi-line-bulk-delete` | Delete all selected lines (with confirm dialog) |

Per-line buttons within each card reuse existing driver-contract testids
(`line-validate-button-{n}`, `line-gt-to-ocr-button-{n}`,
`line-ocr-to-gt-button-{n}`, `line-delete-button-{n}`).
Per-word inputs reuse `gt-text-input-{l}-{w}` and
`word-validate-button-{l}-{w}`.

---

## 3. ARIA + accessible-name guarantees

For every interactive element above:

- Buttons have either visible text **or** an `aria-label`. Icon-only
  buttons (delete, close, sort) MUST have `aria-label`.
- Selects/radios have associated `<label>` or `aria-label`.
- Dialogs have `role="dialog"` + `aria-modal="true"` (Radix default).
- The `role="status" aria-live="polite"` slot in `App.tsx` narrates
  bulk changes — same as pgdp-prep `TextReviewPage.tsx:528-538`.

---

## 4. Notification semantics

The legacy uses `ui.notify(type='positive'|'negative'|'warning'|'info')`.
The SPA's `NotificationKind` enum preserves these four values in the
SSE stream. The driver agent reads notifications via either:

(a) The `notification-{kind}-{id}` DOM elements (sonner-rendered
toasts), or
(b) `GET /api/notifications/stream` (SSE) — for headless drivers.

Both paths must produce the same sequence of `{kind, message, id}`
records for any user action. Duplicate one notification across both
paths exactly once (the SSE backend dispatches; sonner consumes).

---

## 5. Stable resource keys

| Concept | Stable id |
|---|---|
| Project | directory name (e.g. `belloc-the-four-men`) |
| Page | `page_index` (0-based, matches `image_paths` ordering) |
| Line | `line_index` (0-based, matches `page.lines[]` ordering) |
| Word | `(line_index, word_index)` tuple |
| Word (across edits) | `word_id` from `pdomain_book_tools.Word.id` (stable across moves but new on splits) |
| Job | `job_id` from `core/jobs/runner.py` |
| Notification | `notification_id` |

Tests and the driver agent use `(line_index, word_index)` for indexing
because that's how the testid suffixes are formed. Splitting a word
shifts later-word indices; the driver re-reads the matches view after
any structural mutation.

---

## 6. CSS classes the driver doesn't depend on

For completeness — these are NiceGUI/Quasar class names the legacy
exposes that we're **not** preserving:

- `.q-dialog`, `.q-card`, `.q-btn`, `.q-checkbox`, `.q-radio`,
  `.q-input`, `.q-toggle`, `.q-select`, `.q-tabs`, `.q-notification`,
  `.q-spinner`. Replaced by shadcn/Radix DOM. Tests that searched for
  `.q-notification.bg-negative` must be rewritten to use
  `[data-testid^="notification-negative-"]`.

The driver-agent's selectors are `data-testid`-only, so this is
already fine.

CSS classes we DO preserve (for any external script that may style):

- `.monospace` — applied to OCR text labels and GT inputs
- `.ocr-drag-rect` — drag rectangle on the viewport
- `.word-tag-chip` — style/component chip outer
- `.word-tag-clear-button` — × button on a chip

---

## 7. URL deep-link behaviour

The driver agent navigates to the **canonical** routes from section 1.1:

- `/projects/foo/pages/pageno/3` — opens project `foo` at page 3.
- `/projects/foo/pages/pageno/3` after a refresh — same.
- `/projects/foo` — opens project `foo` at page 1.
- `/` — placeholder OR last-loaded redirect.

Legacy paths (`/project/foo/page/3`, `/project/foo`) remain valid via 301
redirects (see section 1.2) but the driver should prefer the canonical forms
above to avoid the extra round-trip.

Edge cases (verbatim from legacy `_initialize_from_url:523`):

1. Project `foo` not in the discovered list: try absolute path
   resolution; try `<source_projects_root>/foo`; try `cwd/foo`. If
   none found, render "Project not found" but keep the URL.
2. Page index out of range: clamp to last valid page; update URL.
3. Page index is non-numeric: 404 the route (this is a malformed URL,
   not a missing page).

Implementation lives in `frontend/src/pages/ProjectPage.tsx` +
backend `core/app_state.resolve_project_path`.

---

## 8. Conformance test

`tests/e2e/test_driver_contract.py` is the canonical regression test
for everything in this document. It:

1. Loads a fixture project.
2. Walks the full UI (load → navigate → open dialog → toolbar action →
   export).
3. For each step, asserts every testid in this document is present
   (or `data-testid-stub="true"`).
4. Asserts URL invariants after each navigation.

If a milestone adds UI, that milestone's PR must update both the test
and this document.

---

## 9. Versioning

This document follows the SPA's app version. Bumping a major version
means breaking driver compatibility — needs a coordinated update of
`pd-ocr-labeler-driver` first. Adding new testids without removing
any is a non-breaking minor bump.

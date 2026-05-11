# 13 — Driver-Compatibility Contract

> **Status**: Active
> **Last updated**: 2026-05-11
> **Spec-Issue**: ConcaveTrillion/pd-ocr-labeler-spa#30

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
[D-035](17-decisions.md) (resolves Q-A4). 308 was on the table but
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
[OPEN_QUESTIONS.md](../OPEN_QUESTIONS.md) approval before it's dropped.

### 2.1 Header bar / project load

| Testid | What it is | Spec |
|---|---|---|
| `project-select` | Project dropdown (Radix Select trigger) | [03](03-frontend.md) §HeaderBar |
| `load-project-button` | LOAD button | same |
| `source-folder-button` | Folder-icon button | same |
| `ocr-config-trigger-button` | Tune-icon button | same |

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

| Testid | What it is |
|---|---|
| `ocr-config-trigger-button` | (header trigger) |
| `ocr-detection-model-select` | Detection model select |
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
| `image-viewport` | The Konva `<Stage>`'s outer wrapper div |

Drag rectangle CSS class: `.ocr-drag-rect` (legacy CSS class
preserved for any external script that might style it).

### 2.7 Text tabs / right pane

| Testid | What it is |
|---|---|
| `text-tab-matches` | Tabs trigger: Matches |
| `text-tab-ground-truth` | Tabs trigger: Ground Truth |
| `text-tab-ocr` | Tabs trigger: OCR |
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
| `export-results` | Container for per-export results |
| `export-close-button` | Close |

### 2.13 Notifications + busy

| Testid | What it is |
|---|---|
| `busy-overlay` | The blur overlay during long actions |
| `project-loading-overlay` | The blur overlay during project load |
| `notification-{kind}-{id}` | Sonner toast wrapper. `{kind}` ∈ positive/negative/warning/info; `{id}` is the server-issued id |

The driver agent specifically watches for `notification-negative-*` to
detect operation failures.

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
| Word (across edits) | `word_id` from `pd_book_tools.Word.id` (stable across moves but new on splits) |
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

The driver agent navigates to:

- `/project/foo/page/3` — opens project `foo` at page 3.
- `/project/foo/page/3` after a refresh — same.
- `/project/foo` — opens project `foo` at page 1.
- `/` — placeholder OR last-loaded redirect.

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

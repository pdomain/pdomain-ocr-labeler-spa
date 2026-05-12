# pd-ocr-labeler-spa: Driver-Compatibility Contract

> **Status**: Draft
> **Last updated**: 2026-05-12
> **Spec-Issue**: ConcaveTrillion/pd-ocr-labeler-spa#30

## TL;DR

`data-testid` attributes and stable URL paths are the Playwright driver's only interface to the
SPA. This spec catalogs every required testid (header, nav, page-actions, viewport, matches,
toolbar, dialogs, notifications) and every URL invariant (canonical `/projects/{id}/pages/pageno/{n}`,
legacy 301 redirects). A conformance E2E test walks the full UI and asserts every testid is present.

## Context

The `pd-ocr-labeler-driver` agent operates the SPA via Playwright using `data-testid` selectors
and URL navigation. If the SPA diverges from this contract, the driver breaks. This spec is the
canonical list; the SPA is wrong if it diverges. The driver still issues legacy URLs
(`/project/{id}/page/{n}`) so 301 redirects must be permanent. Removing a testid requires
OPEN_QUESTIONS.md approval before it's dropped.

## Constraints

- **`data-testid` attributes are the only Playwright selector surface.** No CSS class selectors
  except the four preserved classes (`.monospace`, `.ocr-drag-rect`, `.word-tag-chip`,
  `.word-tag-clear-button`).
- **Legacy URLs redirect permanently (301).** `/project/{id}` → `/projects/{id}`;
  `/project/{id}/page/{n}` → `/projects/{id}/pages/pageno/{n}`.
- **Stub testids for absent cells.** Toolbar cells that don't apply (e.g. word-merge) are
  `display: none` but still carry `data-testid` + `data-testid-stub="true"` so the driver can
  distinguish missing from stubbed.
- **Notification testid format.** Sonner toasts rendered with
  `data-testid="notification-{kind}-{id}"` where kind ∈ positive/negative/warning/info.
- **Resource keys are stable.** Project = directory name; page = `page_index` (0-based);
  line/word = `(line_index, word_index)` tuple; word_id from `pd_book_tools.Word.id` stable
  across moves but new on splits.

## Decision

### URL grammar

Canonical: `/projects/{project_id}/pages/pageno/{n}` (1-based, human-friendly). Also:
`/projects/{project_id}` → page 1, `/projects/{project_id}/pages/index/{idx0}` (0-based).
`/` with no session → `<EmptyProjectState>`; with session → redirect to last page.
Project-not-found renders "Project not found" inline — does NOT 404 the route (chrome stays).
Page-index out of range: clamp to last valid page + update URL. Non-numeric page index: 404.
Within-project navigation uses `router.navigate(..., { replace: true })`; cross-project pushes.

### Testid catalogue (summary of groups)

**Header/project-load:** `project-select`, `load-project-button`, `source-folder-button`,
`ocr-config-trigger-button`.

**Source folder dialog:** `source-folder-current-path-label`, `source-folder-path-input`,
`source-folder-home-button`, `source-folder-up-button`, `source-folder-open-typed-button`,
`source-folder-use-current-button`, `source-folder-cancel-button`, `source-folder-apply-button`.

**OCR config modal:** `ocr-detection-model-select`, `ocr-recognition-model-select`,
`ocr-hf-revision-input`, `ocr-rescan-models-button`, `ocr-config-cancel-button`,
`ocr-config-apply-button`.

**Project nav:** `nav-prev-button`, `nav-next-button`, `nav-goto-button`, `nav-page-input`,
`nav-page-total-label`.

**Page actions:** `reload-ocr-button`, `reload-ocr-edited-button`, `save-page-button`,
`save-project-button`, `load-page-button`, `rematch-gt-button`, `export-button`,
`page-source-badge`, `page-name-label`.

**Viewport:** `layer-paragraphs-checkbox`, `layer-lines-checkbox`, `layer-words-checkbox`,
`selection-mode-paragraph`, `selection-mode-line`, `selection-mode-word`,
`erase-pixels-button`, `image-viewport`.

**Text tabs:** `text-tab-matches`, `text-tab-ground-truth`, `text-tab-ocr`,
`match-filter-toggle`, `match-filter-unvalidated`, `match-filter-mismatched`,
`match-filter-all`.

**Per-line (n):** `line-card-{n}`, `paragraph-checkbox-{p}`, `line-checkbox-{n}`,
`line-gt-to-ocr-button-{n}`, `line-ocr-to-gt-button-{n}`, `line-validate-button-{n}`,
`line-delete-button-{n}`.

**Per-word (l,w):** `word-checkbox-{l}-{w}`, `edit-word-button-{l}-{w}`,
`word-validate-button-{l}-{w}`, `gt-text-input-{l}-{w}`, `ocr-text-label-{l}-{w}`,
`word-status-icon-{l}-{w}`, `word-image-cell-{l}-{w}`, `word-tag-chip-{l}-{w}-{label}`,
`word-tag-clear-button-{l}-{w}-{label}`.

**Toolbar:** `toolbar-{scope}-{action}` (scope ∈ page/paragraph/line/word; action ∈
merge/refine/expand-refine/expand-bboxes/split-after/split-selected/word-to-line/
to-paragraph/gt-to-ocr/ocr-to-gt/validate/unvalidate/delete).

**Apply-style row:** `apply-style-select`, `scope-select`, `apply-style-button`,
`apply-component-select`, `apply-component-button`, `clear-component-button`, `word-add-button`.

**Word edit dialog:** `word-edit-dialog`, `dialog-header-label`, `dialog-apply-close-button`,
`dialog-close-button`, `dialog-gt-input`, `dialog-style-select`, `dialog-scope-select`,
`dialog-component-select`, `dialog-apply-style-button`, `dialog-apply-component-button`,
`dialog-clear-component-button`, `dialog-merge-prev-button`, `dialog-merge-next-button`,
`dialog-split-h-button`, `dialog-split-v-button`, `dialog-delete-word-button`,
`dialog-crop-{above,below,left,right}-button`, `dialog-refine-button`,
`dialog-expand-refine-button`, `dialog-nudge-{edge}-{sign}-button` (8 buttons),
`dialog-reset-button`, `dialog-apply-button`, `dialog-apply-refine-button`,
`dialog-previous-preview-column`, `dialog-current-preview-column`,
`dialog-next-preview-column`, `dialog-tag-chips-slot`, `dialog-current-zoom-toggle`.

**Export dialog:** `export-dialog`, `export-scope-current`, `export-scope-all`,
`export-style-all-checkbox`, `export-style-checkbox-{key}`, `export-button`, `export-results`,
`export-close-button`.

**Notifications/busy:** `busy-overlay`, `project-loading-overlay`,
`notification-{kind}-{id}`.

### Conformance test

`tests/e2e/test_driver_contract.py`: load fixture project → walk full UI (load, navigate,
dialog, toolbar, export) → assert every testid present or `data-testid-stub="true"` →
assert URL invariants after each navigation.

## Contract / Acceptance

- Every testid in §2 exists in the rendered SPA after project load (or carries `data-testid-stub="true"`).
- `GET /project/{id}/page/{n}` returns 301 to `/projects/{id}/pages/pageno/{n}`.
- `notification-negative-*` testids appear in DOM on operation failure (driver-agent detects via these).
- Conformance E2E (`test_driver_contract.py`) passes with zero missing testids.
- Project-not-found renders inline message; chrome and URL remain intact.
- Page-index out-of-range clamps + updates URL; does not 500.

## Trade-offs considered

**Testid on every element vs selective.** Sparse testids make driver scripting fragile (fallback
to CSS selectors). Dense testids decouple driver from CSS churn. Chosen: testid on every
interactive element.

**301 vs 308 for legacy redirects.** 308 preserves method (matters for POST). Legacy routes
are GET-only SPA navigation; 301 is semantically correct for permanent moves. Chosen: 301.

**data-testid-stub vs omit absent cells.** Omitting means the driver can't distinguish "cell
doesn't exist yet" from "cell is gone forever." Stub with boolean attribute enables that
distinction. Chosen: stub.

## Consequences

- Every new UI element added in any milestone PR must include its testid before merge. Failing
  to do so breaks the conformance test (it fails on missing testids, not just on errors).
- Renaming a testid is a breaking change; requires coordinated update of `pd-ocr-labeler-driver`.
- The conformance test must be updated in the same PR that adds new UI.

## Open questions

None.

## References

- `specs/13-driver-contract.md` — legacy feature doc (full testid catalogue and URL invariants)
- `specs/17-decisions.md §D-030, §D-035` — URL grammar and redirect decisions
- `pd-ocr-labeler-driver` agent — Playwright driver for the labeler UI
- `tests/e2e/test_driver_contract.py` — conformance test

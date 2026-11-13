---
kind: architecture
status: built
owner: maintainers
created: 2026-05-16
last_verified: 2026-11-13
---

# 26 — Right Panel Detail Views

The right panel is the mounted word/line/paragraph/block editor. The old standalone word-edit modal is
retired. Word IDs and logical word_index determine lookup/pager behavior rather than array position.

## Routing and actions

Source-alignment detail has priority. Selected word, multi-line, line, paragraph and block views then
follow the current RightPanel routing. ProjectPage supplies 640px width for line/block editing and 520px
for other detail views. ParagraphDetail exposes the mounted paragraph actions.

Line GT commits on blur through its mutation. LineDetail bulk Skip unvalidates selected words.
WordFooter Skip advances to the next word without a server mutation. Block-scope Save patches every paragraph
group; paragraph scope patches only that
paragraph. The earlier missing-commit/bulk/block-save/width notes are resolved implementation history.

## Typography and limits

TypographySection owns server-head-aware grapheme/journal editing. Suggestion acceptance/editing and
predecessor compensation remain open under OPEN_QUESTIONS.md and architecture 31. BlockDetail's model
suggestion state remains null; no source or trigger is implemented, and no new predictor is approved here.

BBox/refine, rebox, erase, structure and character tools are described in the companion sections document.
The local panel frame remains local; this migration does not authorize a shared workbench extraction.

## 6. data-testid contract

### WordDetail / WordHeader / WordFooter / WordImagePreview

| testid | element | description |
|---|---|---|
| `word-detail` | div | Outer container; also used for empty-state |
| `word-detail-accordion` | Accordion root | Multi-accordion of editing sections |
| `word-header` | div | Identity strip |
| `word-header-id` | span | "Line N · Word N" mono label |
| `word-header-prev` | button | Navigate to previous word |
| `word-header-next` | button | Navigate to next word |
| `word-image-preview` | div | Outer wrapper |
| `word-image-preview-box` | div | 76px preview box |
| `word-image-preview-ocr-bar` | div | OCR confidence bar fill |
| `word-image-preview-gt-bar` | div | GT confidence bar fill |
| `word-footer` | div | Sticky three-button footer |
| `word-footer-validate` | button | Validate / unvalidate toggle |
| `word-footer-skip` | button | Skip to next word |
| `word-footer-delete` | button | Delete (opens confirm) |

### OcrGtCompareRow

| testid | element | description |
|---|---|---|
| `ocr-gt-compare` | div | Outer wrapper |
| `ocr-gt-ocr-well` | div | Read-only OCR text well |
| `ocr-gt-copy-btn` | button | Copy OCR → GT |
| `ocr-gt-input` | input | Editable GT text field |
| `ocr-gt-omega-btn` | button | Toggle Unicode picker |
| `ocr-gt-unicode-picker` | div | Inline UnicodePicker (when open) |

### LineDetail

| testid | element | description |
|---|---|---|
| `line-detail` | div | Outer container |
| `line-detail-tabs` | Tabs root | Line / Words tab root |
| `line-detail-tab-line` | TabsTrigger | "Line" tab |
| `line-detail-tab-words` | TabsTrigger | "Words" tab |
| `line-detail-structure-box` | div | Line identity + validation count |
| `line-detail-gt-input` | input | Editable full-line GT field |
| `line-detail-validate-all` | button | Validate all words in line |
| `line-detail-merge-prev` | button | Merge with previous line |
| `line-detail-merge-next` | button | Merge with next line |
| `line-detail-density-toggle` | button | Cards / Rows view toggle |
| `line-detail-bulk-bar` | div | Bulk action bar (shown when words checked) |
| `line-detail-bulk-validate` | button | Validate selected words |
| `line-detail-bulk-skip` | button | Skip selected words |
| `line-words-card-{wordIndex}` | div | Per-word card |
| `line-words-card-checkbox-{wordIndex}` | input[type=checkbox] | Bulk selection |
| `line-detail-word-row-{wordIndex}` | div | Row in density="rows" mode |

### BlockDetail

| testid | element | description |
|---|---|---|
| `block-detail` | div | Outer container |
| `block-detail-tabs` | Tabs root | Layout / Items / Para Layout tabs |
| `block-detail-tab-layout` | TabsTrigger | Layout tab (block level only) |
| `block-detail-tab-items` | TabsTrigger | Items tab |
| `block-detail-tab-para-layout` | TabsTrigger | Para Layout tab (block level only) |
| `block-detail-layout-chip-{id}` | button | Layout type glyph card (19 cards) |
| `block-detail-layout-accept` | button | Accept model suggestion |
| `block-detail-layout-save` | button | Save layout type footer button |
| `block-detail-preview` | div | Layout preview pane |
| `block-detail-items-tree` | div | Items tree/flat container |
| `block-detail-items-view-flat` | button | Flat view toggle |
| `block-detail-items-view-tree` | button | Tree view toggle |
| `block-detail-density-toggle` | div | Compat alias for the flat/tree toggle group |
| `block-detail-para-{paraId\|"null"}` | button | Para group header (tree view) |
| `block-detail-para-scope-{pId\|"null"}` | button | Para scope button (Para Layout tab) |
| `block-detail-line-card-{lineIndex}` | button | Clickable line card |
| `block-detail-line-row-{lineIndex}` | button | Clickable line row (LineItemRow) |

### MultiLineDetail (selectedLines.length > 1)

Rendered when two or more lines are selected simultaneously.
`{n}` is the 0-based `line_index` of each selected line.

| testid | element | description |
|---|---|---|
| `multi-line-detail` | div | Outer container |
| `multi-line-card-{n}` | div | Card for line `n` (`data-line-index={n}`) |
| `multi-line-bulk-bar` | div | Sticky bulk-action bar (bottom of panel) |
| `multi-line-bulk-validate` | button | Validate all words in all selected lines |
| `multi-line-bulk-unvalidate` | button | Unvalidate all words in all selected lines |
| `multi-line-bulk-copy-ocr-to-gt` | button | Copy OCR text to GT for all selected lines |
| `multi-line-bulk-delete` | button | Delete all selected lines (routed through confirm dialog) |
| `line-validate-button-{n}` | button | Per-line validate (shared with worklist convention) |
| `line-gt-to-ocr-button-{n}` | button | GT→OCR for line `n` |
| `line-ocr-to-gt-button-{n}` | button | OCR→GT for line `n` |
| `line-delete-button-{n}` | button | Delete line `n` (routed through confirm dialog) |
| `gt-text-input-{l}-{w}` | input | GT edit input for word `(l, w)` |
| `word-validate-button-{l}-{w}` | button | Per-word validate for word `(l, w)` |

## Multi-line editing

Selecting more than one line opens MultiLineDetail. Cards appear in ascending line-index order. Each card shows
line identity, OCR text, validation counts, and editable ground-truth words. Enter commits a word edit; Tab
traverses inputs across cards.

Per-line controls validate words, copy text between OCR and ground truth, and delete the line with confirmation.
The bulk bar applies validation, text copying, and deletion to the selected lines. A single selected line still
opens LineDetail; multi-word selection keeps its own detail view. The driver identifiers remain in
[the driver contract](13-driver-contract.md) .

### Evidence

- Code: `frontend/src/components/right-panel/MultiLineDetail.tsx` and `frontend/src/components/shell/RightPanel.tsx`.
- Tests: `frontend/src/components/right-panel/MultiLineDetail.test.tsx`; `tests/e2e/test_multi_line_detail.py`
  covers drag selection, GT reload, bulk validation, and single-line routing.
- Verified: 2026-11-07 by source inspection. Mixed-selection and mutation-error browser coverage remain risks; this
  cleanup does not claim a fresh browser-suite pass.

## Current evidence

RightPanel.tsx, LineDetail.tsx, BlockDetail.tsx, ParagraphDetail.tsx and their component tests establish
the routing/actions above. `tests/e2e/test_project_page_smoke.py` drives the mounted word editor.
Verified by source/test inspection on 2026-11-13; the older dated evidence above retains its original scope.

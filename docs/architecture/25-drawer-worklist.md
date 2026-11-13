---
kind: architecture
status: built
owner: maintainers
created: 2026-05-16
last_verified: 2026-11-13
---

# 25 — Drawer: Worklist, Hierarchy, Bulk Actions

Worklist and Hierarchy are permanent Labeler adapters over page data and canonical selection helpers.
They are not an approved shared-library migration or a PGDP pipeline surface.

## Worklist

The worklist store owns filters, sort, searchQuery, selection and page-change resets. Rows use canonical
selection helpers and expose checkbox multi-selection. Query failures surface user-visible errors.
QuickSearch filters both OCR and GT text with case-insensitive substrings. The queue wrapper's test ID
does not make it a second application role.

## Hierarchy and bulk actions

Hierarchy supports optional blocks as well as paragraph/line/word structure. It uses canonical selection
helpers and waits for fetched nodes rather than hiding an empty tree with a test skip. ProjectPage supplies
drawer counts. BulkActions is always visible; its selected-count header is conditional. Selected lines
scope mark-reviewed, while reload and export act on the page even without selection.

The former six wiring questions are implemented: selection, errors, hierarchy helpers, checkboxes, block
structure and counts. No new backlog item follows from those old questions.

## 6. data-testid contract

### Worklist

| testid | element | description |
|---|---|---|
| `worklist` | div | Outer container |
| `worklist-filter-row` | div | Filter chips + sort dropdown |
| `worklist-filter-all` | button | "All" count chip |
| `worklist-filter-unvalidated` | button | "Unvalidated" count chip |
| `worklist-filter-mismatched` | button | "Error" count chip |
| `worklist-sort-select` | select | Sort order dropdown |
| `worklist-queue` | div | Test-ID wrapper; shared WordList owns the listbox role |
| `worklist-row-{lineIndex}` | button (role=option) | Per-line row |
| `worklist-row-{lineIndex}-gt` | span | GT diff line (only when OCR≠GT) |

All `data-active` and `data-selected` attributes are `"true"` when active,
absent otherwise.

### Hierarchy

| testid | element | description |
|---|---|---|
| `hierarchy-filter-row` | div | Filter pills + node count header |
| `hierarchy-filter-all` | button | "All" kind filter pill |
| `hierarchy-filter-para` | button | "¶ Para" kind filter pill |
| `hierarchy-filter-line` | button | "Line" kind filter pill |
| `hierarchy-filter-word` | button | "Word" kind filter pill |
| `hierarchy-node-count` | span | Count of visible nodes after filter |
| `hierarchy` | div (role=tree) | Tree container |
| `hierarchy-node-{id}` | div (role=treeitem) | One row per visible node; `data-kind={kind}` |
| `hierarchy-color-{id}` | span | 6px layer-color square within a node |

Node IDs embedded in testids: `para-{paraIndex | "null"}`, `line-{lineIndex}`,
`word-{lineIndex}-{wordIndex}`.

### BulkActions

| testid | element | description |
|---|---|---|
| `bulk-actions` | div | Outer container (absent when count=0) |
| `bulk-actions-count` | span | "N selected" label |
| `bulk-actions-clear` | button | Clear bulk selection |
| `bulk-actions-mark-reviewed` | button | Validate selected lines |
| `bulk-actions-rerun-match` | button | Re-run OCR match |
| `bulk-actions-export` | button | Export filtered content |

## Evidence

- Code: Worklist.tsx, WorklistRow.tsx, Hierarchy.tsx, BulkActions.tsx, worklist-store.ts and ProjectPage.tsx
  under frontend/src.
- Tests: Worklist.test.tsx, Hierarchy.test.tsx, BulkActions.test.tsx and the mounted project-page suites.
- Verified: 2026-11-13 by source/test inspection. No new full browser exercise is claimed.

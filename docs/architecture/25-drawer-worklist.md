---
kind: architecture
status: built
owner: maintainers
created: 2026-05-16
last_verified: 2026-07-13
---

# 25 — Drawer: Worklist, Hierarchy, Bulk Actions

> **Status**: Active (shipped — hi-fi redesign Slices 11–12, Slice 23, P5.a–P5.c)
> **Last updated**: 2026-05-16
> **Components documented**: `Worklist`, `Hierarchy`, `BulkActions`,
> `worklist-store`

## 1. Overview

The collapsible 320 px drawer houses two tabs: a Worklist queue of all lines on
the current page, and a Hierarchy tree that maps the page's paragraph → line →
word structure. The Worklist is the primary navigation surface for working
through a labeling queue — labelers filter by validation status, sort by
confidence, and click rows to select lines for editing. BulkActions appears at
the bottom of the Worklist panel when lines are multi-selected, providing
batch-validate, re-run-match, and export actions. The Hierarchy provides an
alternative structural navigation mode for understanding how lines are
organized into paragraphs.

## 2. User-facing goals

- I need to see all lines at a glance, filtered to only the unvalidated ones, so
  I can work through the queue without revisiting already-done lines.
- I need to see the OCR text and GT diff for each line in the list so I can
  prioritize the lines that need the most attention.
- I need to sort the queue by status (errors first) or by confidence percentage
  to prioritize my effort.
- I need to select multiple lines and mark them all validated at once when they
  look correct.
- I need to browse the para/line/word tree to understand the document structure
  and jump directly to any paragraph, line, or word.

## 3. Component tree / layout

```
Drawer (320px when open)
├── Header: tab strip + optional count badges + collapse button
│   ├── drawer-tab-worklist button
│   └── drawer-tab-hierarchy button
│
├── [activeTab === "worklist"]
│   └── Worklist                       data-testid="worklist"
│       ├── FilterRow                  data-testid="worklist-filter-row"
│       │   ├── CountChip × 3 (All / Unvalidated / Error)
│       │   └── Sort <select>
│       └── Queue list (role=listbox)  data-testid="worklist-queue"
│           └── WorklistRow × N        data-testid="worklist-row-{lineIndex}"
│
│   (When selectedIds.length > 0)
│   └── BulkActions                    data-testid="bulk-actions"
│
└── [activeTab === "hierarchy"]
    └── Hierarchy                      data-testid="hierarchy"  (role=tree)
        ├── Filter pills + node count  data-testid="hierarchy-filter-row"
        └── NodeRow × N                data-testid="hierarchy-node-{id}"
```

## 4. Data model

### worklist-store

```typescript
interface WorklistState {
  activeFilter: MatchFilter;           // "all" | "unvalidated" | "mismatched"
  sort: WorklistSort;                  // "index" | "confidence" | "status"
  selectedLineIndex: number | null;    // single-selected line (click to navigate)
  selectedIds: number[];               // bulk-selected line indices
}
```

`activeFilter` default: `"unvalidated"`. `sort` default: `"index"`. Both are
session-state only (not persisted to localStorage).

Filter semantics (implemented in `lib/filter-predicates.filterLines`):

- `"all"`: all lines.
- `"unvalidated"`: lines where `!line.is_fully_validated`.
- `"mismatched"`: lines where `overall_match_status === "mismatch"`.

Sort semantics:

- `"index"`: original order (no sort).
- `"confidence"`: ascending by `validatedWordCount / totalWordCount × 100`.
- `"status"`: ascending by `STATUS_SORT_ORDER` — mismatch (0), fuzzy (1),
  unmatched_gt (2), unmatched_ocr (3), exact (4). Errors appear first.

Counts (computed from the unfiltered list for the chip row):
```typescript
interface StatusCounts {
  all: number;
  validated: number;       // is_fully_validated
  unvalidated: number;     // !is_fully_validated && status !== "mismatch"
  error: number;           // overall_match_status === "mismatch"
}
```

### WorklistRow data

Each row uses a `LineMatch` from `PagePayload.line_matches`:

- `line.line_index` → 1-based ID stamp `"L-{pad3}"`.
- `line.overall_match_status` → pip color + 4px left bar color.
- `line.validated_word_count / total_word_count` → confidence `%`.
- `line.ocr_line_text` → primary OCR text (monospace).
- GT diff line: shown only when `ocr_line_text !== ground_truth_line_text`
  and at least one is non-empty.

### Hierarchy tree data model

Built from `PagePayload.line_matches` at render time (no separate endpoint):

```typescript
interface ParaNode  { kind: "para"; paraIndex: number | null; label: string; children: LineNode[] }
interface LineNode  { kind: "line"; lineIndex: number; text: string; children: WordNode[] }
interface WordNode  { kind: "word"; lineIndex: number; wordIndex: number; text: string }
```

Lines with `paragraph_index === null` are grouped under a synthetic
`"Unsorted"` para node. Paragraphs are sorted by `paraIndex` ascending; null
para appears last.

Flat navigation index: built from `flattenTree(paras, expanded)` which
produces `FlatNode[]` where depth 0 = para, 1 = line, 2 = word. Only
expanded branches contribute children to the flat list.

Node IDs: `"para-{paraIndex | 'null'}"`, `"line-{lineIndex}"`, `"word-{lineIndex}-{wordIndex}"`.

### BulkActions data

Reads `worklist-store.selectedIds` (array of line indices).
Fired mutations:

- Mark reviewed: `POST .../words/validate-batch` with `scope: "line"`,
  `line_indices: selectedIds`, `validated: true`.
- Re-run match: `POST .../pages/{idx}/reload-ocr` with
  `{ use_edited_image: false }`. Returns `{ job_id }`.
- Export filtered: `POST .../projects/{pid}/export` with
  `{ scope: "current", page_index, style_filters: [], ... }`. Returns `{ job_id }`.

Job progress is polled via `useJobProgress(jobId)`.

## 5. Interactions and behaviors

### Worklist

**Filter chips** (CountChip)

- Clicking a chip sets `worklistStore.setActiveFilter(filter)`. The active chip
  has `data-active="true"` and accent background.
- Filter counts are always from the unfiltered full line list; the chip count
  stays stable as the filter changes.

**Sort dropdown**

- `<select>` change → `worklistStore.setSort(value)`. Three options: "By ID",
  "By confidence", "By status".

**Row click**

- `worklistStore.setSelectedLineIndex(line.line_index)`.
- The selected row has `data-selected="true"` and `bg-bg-raised` background.
- Note: clicking a row in the Worklist sets `selectedLineIndex` but does NOT
  update `selectionStore` (the canvas/right-panel selection). The
  `selectedLineIndex` is Worklist-local navigation. The caller (ProjectPage)
  may need to bridge this to `selectLine(lineIndex)` — this wiring is an open
  question.

**Empty filtered queue**

- When `filtered.length === 0`: shows "No lines match current filter" in a
  centered muted paragraph.

**WorklistRow structure** (P5.a)

- 4px left status color bar (bg-status-exact / fuzzy / mismatch).
- Mono ID stamp `L-{pad3}` + StatusPip + confidence percentage (right-aligned).
- OCR text (monospace, truncated).
- GT diff line (`worklist-row-{lineIndex}-gt`): shown only when OCR ≠ GT.

### Hierarchy

**Filter pills** (P5.c)

- Four pills: All / ¶ Para / Line / Word.
- Clicking sets `kindFilter`. The visible flat list is filtered to only nodes
  of that kind.
- Node count badge (`hierarchy-node-count`): total visible node count after
  kind filter.

**Expand/collapse**

- Nodes with children show a `▸` or `▾` chevron.
- Clicking the node row OR pressing Enter/Space → `handleSelect(id, node)`.
- Arrow Left / Arrow Right on a node with children → `toggleExpand(id)`.
- Nodes start collapsed. Expanding a para reveals lines; expanding a line
  reveals words.

**Selection**

- Clicking a `line` node: sets `selectionStore.selectedLines = [lineIndex]`,
  clears `selectedWords` and `selectedParagraphs`.
- Clicking a `word` node: sets `selectionStore.selectedWords = [[lineIndex, wordIndex]]`.
- Clicking a `para` node (non-null): sets `selectionStore.selectedParagraphs = [paraIndex]`.
- Clicking a null-para node: no mutation (`paraIndex === null` is skipped).
- The clicked node gets `data-selected="true"`.

**Keyboard navigation**

- `ArrowDown` / `ArrowUp` on the container element (`data-testid="hierarchy"`)
  navigates through the current flat visible list.
- `ArrowRight` / `ArrowLeft` within a `NodeRow` (via `onKeyDown` on the row)
  collapses/expands that node if it has children.

**Node row structure** (P5.c)

- Expand chevron (3px wide placeholder for alignment).
- 6px layer-color square.
- Kind chip (¶ / L / W with layer-color border).
- Mono ID stamp: `P-{N}` / `L-{N}` / `W-{pad3}`.
- Truncated label text.

### BulkActions

- Rendered only when `selectedIds.length > 0` (returns `null` otherwise).
- Count label (`bulk-actions-count`): "N selected".
- Clear button (`bulk-actions-clear`): `worklistStore.clearBulk()`.
- "Mark all reviewed" (`bulk-actions-mark-reviewed`): POST validate-batch,
  calls `worklistStore.clearBulk()` on success. Error is console-logged.
- "Re-run match" (`bulk-actions-rerun-match`): POST reload-ocr, stores
  `job_id` in local state. Progress shown inline.
- "Export filtered" (`bulk-actions-export`): POST export, stores `job_id`.
- All action buttons disabled while a job is in-flight (`isBusy`).
- Job progress display: "Done." (complete), "Error: {message}" (error), or
  `jobProgress.progress.message` (running).

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
| `worklist-queue` | div (role=listbox) | Scrollable line list |
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

## 7. Keyboard shortcuts

Hierarchy container handles:

- `ArrowDown` / `ArrowUp` (on container `keydown`): navigate flat visible list.

Individual NodeRow handles:

- `Enter` / `Space` → select node.
- `ArrowRight` / `ArrowLeft` (when node `hasChildren`) → toggle expand.

These are focus-scoped to the Hierarchy tree container. No document-level
hotkeys are registered by these components.

## 8. Edge cases

- **No page data** (Hierarchy): renders "No page data" centered muted message.
- **All lines match filter** (Worklist): full list shown; no empty-state message.
- **No lines match filter** (Worklist): "No lines match current filter".
- **Null-para lines** (Hierarchy): grouped under a synthetic "Unsorted" node
  (`paraIndex = null`, `id = "para-null"`). Selecting this node is skipped in
  `handleSelect` (null check).
- **BulkActions absent**: `BulkActions` returns `null` when `selectedIds.length
  === 0` — it is not rendered in the DOM at all, so `bulk-actions` testid is
  absent.
- **Job progress race**: if a second job is triggered while the first is still
  running, the `jobId` state is replaced, and the progress display shows the
  new job only.
- **No OCR text** (WorklistRow): shows italic "∅ no OCR text" fallback.
- **is_fully_validated with status=mismatch**: the mismatch chip in the count
  row counts this line under "Error"; the validated chip in the count row does
  NOT count it under validated (because `is_fully_validated` is not checked
  when `status === "mismatch"` in `computeCounts`).

## 9. Open questions

1. **Worklist selectedLineIndex not wired to selectionStore**: clicking a
   Worklist row calls `worklistStore.setSelectedLineIndex` but does not call
   `selectLine(lineIndex)` in `selectionStore`. This means the right panel does
   not switch to that line's detail view when the user clicks a worklist row.
   The wiring should be done at the `ProjectPage` level by subscribing to
   `worklistStore.selectedLineIndex` and calling `selectLine` reactively.

2. **BulkActions error handling**: errors from mark-reviewed, re-run-match, and
   export are `console.error`-only. No toast notification or inline error state
   is shown to the user. The `useNotificationStream` toast infrastructure is
   available (via `sonner`) but not wired here.

3. **Hierarchy selection vs. selectionStore**: the `handleSelect` function in
   Hierarchy calls `selectionStore.setState(...)` directly with a partial patch.
   This bypasses the `selectLine`/`selectPara`/`selectWord` helper functions in
   `selection-store.ts` and may miss any side-effects those helpers perform.
   Consider routing through the canonical helpers.

4. **Worklist bulk selection UI**: `worklistStore.selectedIds` is used by
   `BulkActions` but there is no checkbox or multi-select affordance in
   `WorklistRow` itself. Clicking a row only sets `selectedLineIndex` (single
   selection). The mechanism for adding a line to `selectedIds` is not exposed
   in the current `Worklist` component — `toggle(id)` exists on the store but
   nothing calls it from the Worklist UI. BulkActions can therefore show count
   > 0 only if `selectedIds` is populated externally.

5. **Hierarchy block layer**: the current tree shows paragraphs as top-level
   nodes because `PagePayload` has no `block_index` field. If/when
   `block_index` is added to `LineMatch`, the tree should be extended to show
   block nodes at depth 0.

6. **Drawer tab count source**: `Drawer` accepts a `tabCounts` prop but the
   parent `ProjectPage` does not currently pass it. The spec does not define
   which count is meaningful for each tab (e.g. for Worklist: total lines?
   unvalidated lines? error lines?).

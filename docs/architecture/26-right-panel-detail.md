# 26 — Right Panel Detail Views

> **Status**: Active (shipped — hi-fi redesign Slices 16–22, P2, P5.e–P5.g)
> **Last updated**: 2026-05-16
> **Components documented**: `WordDetail`, `WordHeader`, `WordFooter`,
> `WordImagePreview`, `LineDetail`, `LineWordsCard`, `BlockDetail`,
> `OcrGtCompareRow`, `dialog-store`, `useLineMutations`, `useWordMutations`,
> `useRefineAvailable`

## 1. Overview

The right panel is a context-sensitive detail view that changes based on
the current selection level (word / line / block or para). At the word level it
presents a multi-section accordion editor — image preview, OCR/GT comparison,
style and component tagging, and five specialist editing tools. At the line
level it shows a two-tab view (Line tab with GT editing + Line tab with a
scrollable word list). At the block/para level it shows layout-type selection
and a tree of child items. Together these views allow a labeler to inspect,
correct, and annotate every OCR artifact at the right granularity without
switching to a separate dialog.

## 2. User-facing goals

- I need to see the OCR and GT text side-by-side for any word I click so I can
  spot and fix transcription errors without scrolling.
- I need to mark a word as validated (or skip to the next one) with a single
  keystroke to work through a long queue efficiently.
- I need to see all words on a line at once, toggle their validation state in
  bulk, and merge adjacent lines when the OCR has split them incorrectly.
- I need to classify each block as a heading, footnote, body text, etc. so the
  downstream export is structured correctly.
- I need to delete a word with a confirmation step so I don't accidentally
  destroy data.

## 3. Component tree / layout

### Routing priority (evaluated top-to-bottom in RightPanel)

| Condition | Component rendered | testid |
|---|---|---|
| `selectedWords.length > 1` | `MultiWordDetail` | `multi-word-detail` |
| `level === "line" && selectedLines.length > 1` | `MultiLineDetail` | `multi-line-detail` |
| `level === "line" && selectedLines.length === 1` | `LineDetail` | `line-detail` |
| `level === "word"` | `WordDetail` | `word-detail` |
| `level === "block" \| "para"` | `BlockDetail` | `block-detail` |
| `level === "none"` | placeholder | `right-panel-placeholder` |

```
RightPanel (rendered inside StudioShell's "right" slot)
├── [selectedWords.length > 1]
│   └── MultiWordDetail             data-testid="multi-word-detail"
│
├── [level === "line" && selectedLines.length > 1]
│   └── MultiLineDetail             data-testid="multi-line-detail"
│       ├── LineCard (per selected line)  data-testid="multi-line-card-{lineIndex}"
│       │   └── WordRow (per word)        data-testid="gt-text-input-{l}-{w}"
│       └── BulkBar (sticky footer)   data-testid="multi-line-bulk-bar"
│
├── [level === "line" && selectedLines.length === 1]
│   └── LineDetail                  data-testid="line-detail"
│       └── Tabs
│           ├── LineCard (in "line" tab)
│           ├── GTRow (in "line" tab)
│           ├── StructureBox (in "line" tab)
│           └── WordCardsView / WordRowsView (in "words" tab)
│               └── LineWordsCard (per word)
│
├── [level === "word"]
│   └── WordDetail                  data-testid="word-detail"
│       ├── WordHeader              data-testid="word-header"
│       ├── WordImagePreview        data-testid="word-image-preview"
│       ├── OcrGtCompareRow         data-testid="ocr-gt-compare"
│       │   └── UnicodePicker (inline, collapsible)
│       ├── StylePalette            data-testid="style-palette"
│       ├── ComponentPalette        data-testid="component-palette"
│       ├── Accordion               data-testid="word-detail-accordion"
│       │   ├── BBoxSection
│       │   ├── ReboxSection (Konva canvas)
│       │   ├── ErasePixelsSection
│       │   ├── StructureSection
│       │   ├── CharRangesSection
│       │   └── CharFixerSection (Konva canvas)
│       └── WordFooter              data-testid="word-footer"  (sticky bottom)
│
└── [level === "block" | "para"]
    └── BlockDetail                 data-testid="block-detail"
        └── Tabs
            ├── Layout tab (block level only)
            ├── Items tab
            └── Para Layout tab (block level only)
```

## 4. Data model

### Primary types (from `frontend/src/api/types.ts`)

```typescript
// WordMatch — a single word's OCR+GT state
interface WordMatch {
  line_index: number;
  word_index?: number;
  ocr_text: string;
  ground_truth_text: string;
  match_status: "exact" | "fuzzy" | "mismatch" | "unmatched_gt" | "unmatched_ocr";
  fuzz_score?: number;          // 0–100
  is_validated?: boolean;
  bbox: BBox;                   // { x, y, width, height } in image pixels
  text_style_labels?: string[]; // ["bold", "italic", ...]
  word_components?: string[];   // ["drop-cap", "footnote-ref", ...]
  char_bboxes?: BBox[];         // per-char boxes (SPA sidecar, optional)
}

// LineMatch — a line on the page
interface LineMatch {
  line_index: number;
  paragraph_index: number | null;
  ocr_line_text?: string;
  ground_truth_line_text?: string;
  overall_match_status: MatchStatus;
  word_matches: WordMatch[];
  validated_word_count: number;
  total_word_count: number;
  is_fully_validated?: boolean;
}

// PagePayload — full page response
interface PagePayload {
  line_matches: LineMatch[];
  // ... other fields
}
```

### Mutations

All mutations invalidate the `["page", projectId, pageIndex]` react-query cache
on success, triggering a re-render of the right panel.

| Hook | Endpoint | Notes |
|---|---|---|
| `useUpdateWordGroundTruth` | `POST .../words/{li}/{wi}/gt` | Blur-commit |
| `useApplyStyle` | `POST .../words/{li}/{wi}/style` | `scope: "whole"\|"part"` |
| `useApplyComponent` | `POST .../words/{li}/{wi}/component` | Toggle |
| `useReboxWord` | `POST .../words/{li}/{wi}/rebox` | BBoxSection + ReboxSection |
| `useMergeWord` | `POST .../words/{li}/{wi}/merge` | `direction: "left"\|"right"` |
| `useSplitWord` | `POST .../words/{li}/{wi}/split` | `x_fraction: float` |
| `useErasePixels` | `POST .../words/{li}/{wi}/erase-pixels` | Sequential ops |
| `useSetCharRanges` | `POST .../words/{li}/{wi}/char-ranges` | Full replace |
| `useSetCharBboxes` | `POST .../words/{li}/{wi}/char-bboxes` | SPA sidecar |
| `useToggleValidated` (WordFooter) | `POST .../words/{li}/{wi}/validated` | Toggle |
| `useDeleteWord` (WordFooter) | `POST .../delete` with `scope:"word"` | Confirm first |
| `useValidateLine` | `POST .../words/validate-batch` | scope="line" |
| `useMergeLines` | `POST .../lines/merge` | Two-element `line_indices` |
| `usePatchParagraph` | `PATCH .../paragraphs/{pi}` | `layout_type` field |
| `useRefineAvailable` | `GET /api/refine/available` | Probe, 5-min stale |

### dialog-store

All dialogs are managed via a single imperative store:

```typescript
type SimpleDialogKey = "ocrConfig" | "export" | "hotkeyHelp" | "sourceFolder";
// Also: wordEdit (with lineIdx/wordIdx params), confirm (with title/body/onConfirm)
```

`dialogStore.openWordEdit({ lineIdx, wordIdx })` and
`dialogStore.openConfirm({ title, body, onConfirm })` are the compound openers.

## 5. Interactions and behaviors

### WordDetail

Reads `selectionStore.level` and `selectionStore.path` to determine which word
to display. Renders an empty-state `"No word selected."` div when `level !==
"word"`.

**Navigation (WordHeader)**

- `◀` (`word-header-prev`) → `walkSibling("prev", page)` via `selection-store`.
  Disabled when `wordIdx === 0`.
- `▶` (`word-header-next`) → `walkSibling("next", page)`.
  Disabled when `wordIdx === lineLength - 1`.
- `StatusPip` renders the word's `match_status` mapped to `exact | fuzzy | mismatch`.
  When `is_validated`, a `"✓"` label is shown on the pip.

**Image preview (WordImagePreview)**

- 76px-tall preview box with `bg-sunk` background.
- When `imageUrl` is provided: shows `<img>` of the cropped word slice.
- Fallback: renders `word.ocr_text` in 28px Georgia serif. When OCR is empty,
  shows italic `∅`.
- OCR confidence bar: uses `fuzz_score` (or 100 for exact matches) clamped 0–100.
  Color: green ≥ 80%, amber ≥ 50%, red < 50%.
- GT confidence bar: 100% when `is_validated`, 50% when OCR ≥ 80%, else 0%.

**OCR/GT compare (OcrGtCompareRow)**

- Left column: read-only OCR text well (monospace, `select-all`).
- Right column: editable GT `<Input>`. Commits on blur (if changed) or on Enter.
- "← OCR" button (`ocr-gt-copy-btn`): copies OCR text into the GT input and
  immediately calls `onCommitGt`. Focuses the input after copy.
- "Ω" button (`ocr-gt-omega-btn`): toggles inline `UnicodePicker`. When open,
  `aria-pressed="true"` and accent background.
- UnicodePicker: inserts selected glyphs at the current cursor position in the
  GT input. See [`28-palettes-pickers.md` §UnicodePicker](28-palettes-pickers.md).
- The `localGt` state syncs back from `gtText` only when the input is not
  currently focused (prevents remote-update overwriting an in-progress edit).

**StylePalette / ComponentPalette**

- See [`28-palettes-pickers.md`](28-palettes-pickers.md).

**Accordion (WordDetail)**

- Uses `Accordion` in `type="multiple"` mode — any number of sections can be
  open simultaneously.
- The accordion body has `paddingBottom: "52px"` so the sticky WordFooter does
  not obscure the bottom item.
- Six items in order: Bounding Box (keycap B), Rebox (keycap R, tag="accent"),
  Erase Pixels (keycap E, tag="mismatch"), Structure (keycap S), Char Ranges
  (keycap C), Char Fixer (keycap F).
- Accordion trigger hints: `BBoxSection` uses `bboxHint(word.bbox)` (formatted
  coords); Rebox shows `"W × H px"`; CharFixer shows `"N ranges"` or
  `"edit · fix · unicode"` when empty.

**WordFooter** (sticky `bottom-0`)

- Validate button (`word-footer-validate`): calls `toggleValidated.mutate(...)`.
  Accent style when already validated ("✓ Validated"), neutral when not.
- Skip button (`word-footer-skip`): `walkSibling("next", page)` — no server call.
- Delete button (`word-footer-delete`): opens a `ConfirmDialog` inline.
  On confirm: `deleteWord.mutate({ lineIndex, wordIndex })` then closes dialog.

### LineDetail

**Line tab**

- `StructureBox` shows: StatusPip + "Line N · Para N" mono label +
  "N/N validated" count.
- `GTRow` shows: editable input for `ground_truth_line_text`. Currently local
  state only — the input captures edits but no blur-commit mutation is wired
  (open question).
- `LineCard` renders the existing words in the line (from `useWordMatches` or
  passed `line` prop).
- Validate-all footer button (`line-detail-validate-all`): calls
  `validateLine.mutate({ lineIndex, validated: true })`. Disabled and shows
  "All words validated ✓" when `line.is_fully_validated`.
- Merge-prev (`line-detail-merge-prev`) / Merge-next (`line-detail-merge-next`)
  buttons: call `mergeLines.mutate({ lineIndex, direction })`. Merge-prev is
  disabled when `line_index === 0`. Error message shown when `mergeLines.isError`.

**Words tab**

- Density toggle (`line-detail-density-toggle`): switches between "Cards" view
  (LineWordsCard per word) and "Rows" view (status pip + mono OCR text per word).
  Preference persisted to `useUiPrefs.lineWordsDensity`.
- Bulk bar (`line-detail-bulk-bar`): appears when any word checkboxes are
  checked. Shows count + "Validate selected" + "Skip selected" + clear button.
  Note: the bulk validate/skip actions in the current code clear the selection
  but do not fire mutations — this is an open question.
- `LineWordsCard`: per-word card with checkbox, 12px serif preview, OCR text,
  and a GT diff line when OCR ≠ GT.

### BlockDetail (level = "block" or "para")

**Layout tab (block level only)**

- 19 layout-type glyph cards in two groups: Structural (9) and Content (10).
- Each card (`block-detail-layout-chip-{id}`) is a button with an inline SVG
  glyph and label. Active card has `data-active="true"`, accent border,
  `bg-accent/10`.
- Model suggestion callout: shown when `suggestedLayout` is non-null (currently
  always null — backend not wired). "Use suggestion" button
  (`block-detail-layout-accept`) accepts and saves immediately.
- Preview pane (`block-detail-preview`): shows sample text (first line's OCR
  text, max 60 chars) styled to match the pending layout type.
- Sticky footer: shows "Unsaved: {label}" when `pendingLayout !== selectedLayout`,
  else shows current. "Save layout type" button (`block-detail-layout-save`)
  disabled when no pending change or mutation pending. Saves via `patchParagraph`.

**Items tab**

- View sub-toggle: Flat (`block-detail-items-view-flat`) / Tree
  (`block-detail-items-view-tree`). Default: Tree.
- Flat: all relevant lines as `LineItemCard` rows. Tree: grouped by paragraph
  with `ParaGroup` headers (`block-detail-para-{paraId}`).
- Clicking a `LineItemCard` (`block-detail-line-card-{lineIndex}`) → `selectLine`.

**Para Layout tab (block level only)**

- Lists each paragraph as a button. Clicking → `selectPara(pId)`.
- No layout editing within this tab — it navigates to the para's context.

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

## 7. Keyboard shortcuts

WordFooter renders `<KeyCap>` hints next to its buttons for discovery purposes
but the key bindings themselves are owned by `useGlobalHotkeys` (wired at the
ProjectPage level, outside this component set). Per-component hotkeys:

- `Enter` inside `ocr-gt-input` → blurs the input (triggers commit).
- `Enter` / `Space` on Hierarchy tree nodes → select action (in Hierarchy; not
  in this group).

No component in this group registers document-level hotkeys directly.

## 8. Edge cases

- **No word selected** (WordDetail): renders `"No word selected."` with the
  `word-detail` testid.
- **Word not found in page data** (WordDetail): renders `"Word not found in
  page data."` with the `word-detail` testid.
- **No line selected** (LineDetail): renders `"No line selected."`.
- **Line not found in page data** (LineDetail): renders `"Line not found in
  page data."`.
- **No block/para selected** (BlockDetail): renders `"No block selected."` or
  `"No paragraph selected."`.
- **Word OCR text empty**: WordImagePreview shows italic `∅`; CharFixer shows no
  cells; CharRanges shows no cells; StructureSection SplitPicker shows nothing.
- **Line is fully validated**: `line-detail-validate-all` is disabled with text
  "All words validated ✓".
- **Merge-prev at first line**: `line-detail-merge-prev` is disabled
  (`line.line_index === 0`).
- **BlockDetail model suggestion**: `suggestedLayout` is currently always `null`
  (backend not wired). The "No model suggestion available" muted callout is
  shown instead.
- **WordFooter delete in-flight**: the delete button is disabled while
  `deleteWord.isPending`.
- **Merge error**: `mergeLines.isError` shows `"Merge failed. Try again."` in
  the Line tab footer.

## 9. Open questions

1. **LineDetail GT input commit**: `GTRow` maintains a local `gtText` state but
   no blur-commit mutation is wired. When should the full-line GT text be
   committed to the server? Via `PUT .../lines/{li}/gt` (which does not exist
   yet), or by updating words individually?

2. **LineDetail bulk validate/skip**: The "Validate selected" and "Skip selected"
   buttons in the bulk action bar call `clearChecked()` but do not fire any
   mutations. These need to be wired to `validate-batch` (for validate) and to
   `walkSibling`-style iteration (for skip).

3. **BlockDetail layout persistence at block scope**: `patchParagraph` patches a
   single paragraph's `layout_type`. When the user is in `level="block"` mode
   and no `paraId` is set (all lines selected), the save button is rendered but
   the mutation is skipped (`if (paraId !== null) patchParagraph.mutate(...)`).
   Should block-level layout type be saved to all paragraphs in the block, or
   is there a separate block-level field?

4. **BlockDetail model suggestion source**: `suggestedLayout` is `useState<LayoutType | null>(null)`
   — always null. The spec does not yet define the endpoint or trigger for
   model-based block layout suggestions.

5. **Right panel width for line/block**: The `StudioShell.rightWidth` prop can
   be set to 640 for line/block views. The `ProjectPage` must pass the correct
   width based on the selection level. This wiring is not currently present
   (the default 520 px is used for all levels).

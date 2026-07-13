---
kind: architecture
status: built
owner: maintainers
created: 2026-05-16
last_verified: 2026-07-13
---

# 27 — Right Panel Action Sections

> **Status**: Active (shipped — hi-fi redesign Slices 16–20, P3.a–P4.b)
> **Last updated**: 2026-05-16
> **Components documented**: `BBoxSection`, `ReboxSection`, `ReboxCanvas`,
> `ErasePixelsSection`, `EraseCanvas`, `CharRangesSection`, `CharFixerSection`,
> `CharFixerCanvas`, `StructureSection`

## 1. Overview

The accordion sections are specialist editing tools mounted inside `WordDetail`.
Each lives in its own `Accordion.Item` and opens on demand. They cover the five
geometric and structural operations a labeler performs on a word: bounding-box
nudging, interactive rebox via a Konva mini-canvas, pixel erasure, word merge /
split / gap adjustment, per-character style ranges, and per-character GT
correction with a character-bbox canvas. Collectively they replace the legacy
`word_edit_dialog.py`'s historical inline tool rows (superseded by
[`26-right-panel-detail.md`](26-right-panel-detail.md)
for the legacy reference).

## 2. User-facing goals

- I need to precisely adjust a word's bounding box by typing pixel coordinates
  or nudging in small steps without leaving the right panel.
- I need to drag handles on a cropped image to interactively redefine a word
  boundary, then commit the change with one click.
- I need to paint over noise pixels in a word image (brush, lasso, or rect
  selection) and erase them server-side to clean up the image for OCR retraining.
- I need to merge two accidentally-split words or split a joined word at the
  right character position.
- I need to tag individual character ranges within a word with bold, italic, or
  other styles when the styles differ per character (e.g. a superscript digit
  inside a word).
- I need to fix per-character OCR errors in a grid where each cell shows the
  OCR character above an editable input for the GT character.

## 3. Component tree / layout

```
WordDetail > Accordion
├── BBoxSection              [Accordion.Item value="bbox"]
│   ├── CoordReadout strip
│   ├── 2×2 numeric input grid (X, Y, W, H)
│   ├── Nudge sub-row (step input + L/R/U/D buttons)
│   └── Actions sub-row (Refine / Expand+Refine / Crop) + Reset
│
├── ReboxSection             [Accordion.Item value="rebox", tag="accent"]
│   ├── Tool segmented control (Snap / Draw / Pan)
│   ├── ReboxCanvas (react-konva Stage)
│   ├── Zoom controls (−/N×/+) + bbox size summary
│   └── Apply + Reset buttons
│
├── ErasePixelsSection       [Accordion.Item value="erase", tag="mismatch"]
│   ├── EraseCanvas (react-konva Stage)
│   │   ├── Tool switcher (Brush / Lasso / Rect)
│   │   └── Brush-size slider
│   ├── Ops list (scrollable, per-op remove)
│   └── Clear all + Apply erases footer
│
├── StructureSection         [Accordion.Item value="structure"]
│   ├── Neighbors strip (prev · current · next)
│   ├── Merge row (← Merge with prev / Merge with next →) + hover preview
│   ├── Gap slider (−10…+10 px)
│   └── Split affordance (character picker + Split button)
│
├── CharRangesSection        [Accordion.Item value="char-ranges"]
│   ├── Char cell row (clickable per OCR character)
│   ├── Pending panel (range readout + style chips + Add range button)
│   └── Rich editor cards (per range: glyph card + positions + kind + palette)
│
└── CharFixerSection         [Accordion.Item value="char-fixer"]
    ├── CharFixerCanvas (react-konva Stage, per-char bbox rectangles)
    ├── Selected-range detail strip (char text + x1/y1/x2/y2 inputs + Apply)
    ├── Per-char GT input grid (OCR label above, editable input below)
    └── Unicode picker toggle + inline UnicodePicker
```

## 4. Data model

### BBoxSection

Input: `word.bbox: BBox = { x, y, width, height }` in image pixels.

Local draft state mirrors the server value. Blur or nudge commits immediately
via `useReboxWord`. Reset restores from `word.bbox` (the un-drafted original
from the server).

### ReboxSection / ReboxCanvas

Input: `word.bbox: BBox`.

The section owns:

- `draft: BBox` — current pending bbox (image-pixel coords).
- `tool: "snap" | "draw" | "pan"` — interaction mode.
- `zoom: number` — integer 1–5; applied as Stage scale.

The canvas (ReboxCanvas) takes the `bbox` prop (from the section's draft) and
reports changes via `onChange(next: BBox)`. Identity key `${word.line_index}-${word.word_index}`
reseeds the draft + tool + zoom when the word changes.

`dirty = roundBbox(draft) !== roundBbox(word.bbox)` gates the Apply button.

The Stage is `240×120` CSS pixels. Bboxes are reported in image-pixel coords;
the canvas applies a scale to fit within the stage.

### ErasePixelsSection / EraseCanvas

Input: `backendAvailable?: boolean` (explicit override) or the `useRefineAvailable`
probe result (`GET /api/refine/available`, 5-min stale, returns
`{ available: boolean, reason: string }`).

The section owns:

- `tool: "brush" | "lasso" | "rect"`
- `brushSize: number` (default 8 px radius)
- `ops: EraseOp[]` — accumulated paint operations

```typescript
type EraseOp =
  | { tool: "brush"; x: number; y: number; radius: number }
  | { tool: "lasso"; points: Array<[number, number]> }
  | { tool: "rect"; x: number; y: number; width: number; height: number }
```

On Apply: the parent `WordDetail` calls `useErasePixels.mutateAsync({ ops })`.
The hook maps each op to a `BBox + shape` and fires one
`POST .../words/{li}/{wi}/erase-pixels` per op (sequentially). Brush ops use
`shape: "circle"` (inscribed ellipse mask); rect and lasso ops use `shape: "rect"`.

### StructureSection

Input: `word: WordMatch`, `page: PagePayload`.

Reads neighbor words from `page.line_matches` without a separate fetch.
Gap computation: `next.bbox.x - (current.bbox.x + current.bbox.width)`.

`gapDelta` (slider state, −10…+10) resets to 0 when `currentGap` changes
(i.e. after a successful rebox of the next word).

Merge direction API field: `"left"` (merge with prev) / `"right"` (merge with next).
Split: `x_fraction = splitPos / charCount` where `splitPos` is the 1-based
character boundary index.

### CharRangesSection

Input: `word: WordMatch`.

The section owns:

- `anchor: number | null`, `endPos: number | null` — pending selection.
- `pendingStyles: Record<PendingStyleKey, TristateValue>` — styles for the
  pending range.
- `ranges: CharRange[]` — persisted range cards (local state only until
  persisted via `useSetCharRanges`).

```typescript
interface CharRange {
  start: number;
  end: number;
  styles: Record<PendingStyleKey, TristateValue>; // legacy field
  kind: "style" | "component";
  activeStyles: Set<string>;
  activeComponents: Set<string>;
}
```

API payload: `{ ranges: [{ start, end, styles: string[] }] }` via
`POST .../words/{li}/{wi}/char-ranges`. The `styles` array merges both the
legacy `styles` map and `activeStyles` set, deduplicated.

Overlap detection: O(n²) comparison; overlapping ranges get amber borders and
an `overlap` badge.

Note: The compat alias rows (`char-ranges-row-{i}`, `char-ranges-delete-{i}`)
are `sr-only` and `aria-hidden` — they exist solely for legacy test selectors.

### CharFixerSection

Input: `word: WordMatch`.

Two independent local states:

1. `draft: string[]` — per-char GT edits. Debounced 500 ms then committed via
   `useUpdateWordGroundTruth` (reconstructing the full GT string by joining).
2. `charBboxes: CharRangeBBox[]` — one bbox per OCR character. Initial layout
   divides `word.bbox` evenly across characters. Dirty when any bbox differs
   from initial. Committed via `useSetCharBboxes` (stores in SPA sidecar,
   `POST .../char-bboxes`).

`cellCount = max(ocrChars.length, gtChars.length)` so the grid shows all
characters even when GT is longer than OCR.

WordKey `${line_index}-${word_index}-${ground_truth_text}` reseeds both states
when the word changes.

## 5. Interactions and behaviors

### BBoxSection

- Typing in any of the four inputs (X/Y/W/H) updates the local draft
  immediately; blur commits the current draft value to the server.
- Nudge: "Step" input sets `nudgeStep` (integer px, min 1). L/R/T/B buttons
  call `applyNudge(draft, dir, nudgeStep)` and commit immediately.
- Refine button: currently calls `commitBbox(draft)` (same as a manual
  commit — snap-to-ink is not yet wired).
- Expand+Refine: expands the draft bbox by 4 px on each side, updates draft,
  then commits.
- Crop: calls `commitBbox(draft)` (same as Refine — backend crop endpoint not
  yet separately wired).
- Reset: restores draft to `originalBbox` and commits.

### ReboxSection / ReboxCanvas

Tool modes affect mouse interaction on the canvas:

- **Snap**: 8 handle-drag mode. Dragging a handle (`rebox-handle-{pos}`)
  resizes the bbox by updating the corresponding edge(s).
- **Draw**: click-drag on empty canvas defines a new bbox from scratch.
- **Pan**: drag shifts the view offset without changing the bbox.

Zoom controls (−/+): clamp to MIN_ZOOM=1 / MAX_ZOOM=5. Apply is disabled when
`!dirty`. Reset restores `draft = word.bbox`.

Canvas coordinate space: bboxes are in image-pixel coords; the stage applies
a uniform scale so the content fits in `240×120 px`.

### ErasePixelsSection

Probe state:

- `showLoading`: shown only when `backendAvailable` prop was not provided AND
  the probe is still loading.
- `available: false`: shows the `erase-not-available` message.
- `available: true`: renders the full erase UI.

After a draw gesture on EraseCanvas, `onOpCommit` appends the op to `ops`.
Remove button (`erase-op-${i}-remove`) removes that op by index.
Apply (`erase-apply`): disabled when `ops.length === 0` or apply is in-flight.
Sets `busy = true`, calls `onApply(ops)`, clears ops on success.
Clear all (`erase-clear`): disabled when `ops.length === 0`.

### StructureSection

Neighbors strip: three cards — prev (muted), current (accent/border), next (muted).
"none" label shown when the neighbor does not exist.

Merge buttons: hover sets `hoveredMerge` which shows a live preview of the
merged text (e.g. `prevText + currentText`). Click opens `ConfirmDialog` with
the preview in the message. Confirm fires `mergeWord.mutate`.

Gap slider: `value = gapDelta` (−10…+10 px delta from current gap). The slider
commits on `mouseup` and `blur` via `handleGapCommit`. Clamped so the gap
stays ≥ 0 and next word's x stays ≥ 0.

Split: `SplitPicker` renders one button per OCR character. Clicking selects
that split position (highlighted in accent). The Split button label changes to
"Split at position N". Click fires `splitWord.mutate({ xFraction })`.
When no position selected, splits at midpoint by default.

### CharRangesSection

Char cells: first click sets anchor. Second click sets `endPos`. Third click
restarts from the new anchor. Pending range is highlighted with accent background.

Add range button: enabled when both `anchor` and `endPos` are set. Creates a
new range card with the pending position + styles, persists immediately, clears
the pending state.

Range cards (P4.a additions):

- **Glyph card**: shows the characters from `text[start..end+1]` in serif 13px.
- **Position inputs** (S, E): editable 0-based character offsets. S is clamped
  ≤ end; E is clamped ≥ start.
- **Kind switcher**: toggles the palette shown below between "Style" chips and
  "Component" chips.
- **Overlap badge**: shown when this range intersects any other range.
- **Delete** (x): removes the range and persists immediately.
- **Blank Add range button** (`char-range-add`): appends a new full-word blank
  range (0..maxIdx).

### CharFixerSection

Per-char GT grid: each cell shows `ocrChars[i]` as a read-only label above an
editable input for `gtChars[i]`. Mismatch cells have a 2px left `status-mismatch`
border. Editing any input schedules a 500 ms debounced save.

CharFixerCanvas: clicking a per-char rectangle selects it (`onSelect(index)`).
The selected range shows 8 drag handles. Drag adjusts `charBboxes[index].bbox`.
Editing x1/y1/x2/y2 in the detail strip also updates the selected range's bbox.
Both paths set `dirty = true`.

Apply button (`charfixer-apply`): enabled when `dirty`. Calls `handleApply()`
which POSTs `charBboxes.map(r => r.bbox)` to the char-bboxes endpoint, then
sets `dirty = false`.

Unicode picker toggle (`char-fixer-open-picker-button`): shows/hides inline
`UnicodePicker`. Insertion target is the last-focused character input cell.

## 6. data-testid contract

### BBoxSection

| testid | element | description |
|---|---|---|
| `bbox-section` | div | Outer wrapper; `data-word-key="{li}-{wi}"` |
| `bbox-input-x` | input[type=number] | X coordinate |
| `bbox-input-y` | input[type=number] | Y coordinate |
| `bbox-input-w` | input[type=number] | Width |
| `bbox-input-h` | input[type=number] | Height |
| `bbox-nudge-step` | input[type=number] | Step size in px |
| `bbox-nudge-left` | button | Nudge left |
| `bbox-nudge-right` | button | Nudge right |
| `bbox-nudge-top` | button | Nudge up |
| `bbox-nudge-bottom` | button | Nudge down |
| `bbox-refine-button` | button | Refine (snap-to-ink stub) |
| `bbox-expand-refine-button` | button | Expand 4px then commit |
| `bbox-crop-button` | button | Crop (stub) |
| `bbox-reset-button` | button | Restore original bbox |

### ReboxSection / ReboxCanvas

| testid | element | description |
|---|---|---|
| `rebox-section` | div | Outer wrapper; `data-word-key="{li}-{wi}"` |
| `rebox-tool-snap` | button[role=radio] | Snap mode |
| `rebox-tool-draw` | button[role=radio] | Draw mode |
| `rebox-tool-pan` | button[role=radio] | Pan mode |
| `rebox-canvas` | Stage (Konva) / div in tests | Canvas root |
| `rebox-bbox` | Rect (Konva) | Bbox overlay rectangle |
| `rebox-handle-{nw\|n\|ne\|e\|se\|s\|sw\|w}` | Rect (Konva) | Drag handle (8 handles) |
| `rebox-zoom-out` | button | Zoom out (−) |
| `rebox-zoom-level` | span | Current zoom label ("1×") |
| `rebox-zoom-in` | button | Zoom in (+) |
| `rebox-bbox-summary` | span | Current bbox size ("W × H px") |
| `rebox-apply` | button | Apply rebox (disabled when not dirty) |
| `rebox-reset` | button (link style) | Reset to original bbox |

### ErasePixelsSection / EraseCanvas

| testid | element | description |
|---|---|---|
| `erase-pixels-section` | div | Outer wrapper |
| `erase-not-available` | p | Fallback when probe returns false |
| `erase-canvas` | Stage (Konva) / div | Canvas root |
| `erase-tool-brush` | button | Brush tool |
| `erase-tool-lasso` | button | Lasso tool |
| `erase-tool-rect` | button | Rect tool |
| `erase-brush-size` | input[type=range] | Brush radius slider |
| `erase-ops-list` | div | Scrollable ops list |
| `erase-op-{N}-remove` | button | Remove op at index N |
| `erase-apply` | button | Apply all ops |
| `erase-clear` | button | Clear all ops |

### StructureSection

| testid | element | description |
|---|---|---|
| `structure-section` | div | Outer wrapper |
| `structure-prev-word` | div | Previous word neighbor card |
| `structure-current-word` | div | Current word card (accent) |
| `structure-next-word` | div | Next word neighbor card |
| `structure-merge-prev` | button | Merge with prev (opens confirm) |
| `structure-merge-next` | button | Merge with next (opens confirm) |
| `structure-gap-slider` | input[type=range] | Inter-word gap slider |
| `structure-split-button` | button | Split word at selected position |

### CharRangesSection

| testid | element | description |
|---|---|---|
| `char-ranges-section` | div | Outer container |
| `char-cell-{i}` | button | Clickable OCR character cell |
| `char-ranges-pending` | p | Pending range readout |
| `char-ranges-chip-{style}` | Chip | Style chip in pending panel |
| `char-ranges-add-button` | button | Add range from pending selection |
| `char-range-{N}` | div | Rich editor card for range N |
| `char-range-{N}-glyph` | div | Glyph preview card |
| `char-range-{N}-delete` | button | Delete range N |
| `char-range-{N}-overlap-warning` | span | Overlap badge (when overlapping) |
| `char-range-{N}-kind-style` | button | Switch kind to Style |
| `char-range-{N}-kind-component` | button | Switch kind to Component |
| `char-range-add` | button | Append blank full-word range |
| `char-ranges-row-{i}` | div (sr-only) | Compat alias for range row |
| `char-ranges-delete-{i}` | button (sr-only) | Compat alias for delete |

### CharFixerSection / CharFixerCanvas

| testid | element | description |
|---|---|---|
| `char-fixer-section` | div | Outer container |
| `char-fixer-cell-{i}` | div | Per-char wrapper; `data-mismatch="true"` when OCR≠GT |
| `char-fixer-orig-{i}` | span | Read-only OCR char label |
| `char-fixer-input-{i}` | input | Editable GT char input |
| `char-fixer-open-picker-button` | button | Toggle Unicode picker |
| `charfixer-canvas` | Stage (Konva) | Canvas root |
| `charfixer-range-{N}` | Rect (Konva) | Per-char bbox rectangle |
| `charfixer-range-{N}-handle-{pos}` | Rect (Konva) | Drag handles on selected range |
| `charfixer-detail-strip` | div | Selected-range coordinate detail |
| `charfixer-detail-text` | span | Selected character(s) label |
| `charfixer-detail-x1` | input[type=number] | x1 coordinate |
| `charfixer-detail-y1` | input[type=number] | y1 coordinate |
| `charfixer-detail-x2` | input[type=number] | x2 coordinate |
| `charfixer-detail-y2` | input[type=number] | y2 coordinate |
| `charfixer-apply` | button | Apply bbox changes |

## 7. Keyboard shortcuts

No section registers document-level hotkeys directly. The `AccordionTrigger`
renders a `<KeyCap>` hint for each section (B / R / E / S / C / F) but the
actual hotkey bindings live in `useGlobalHotkeys` at the ProjectPage level.

Enter in `char-fixer-input-{i}` does not submit — the input is single-character
cells, not form fields.

## 8. Edge cases

- **`word.ocr_text` is empty** (CharRangesSection): no char cells are rendered.
  Pending panel shows "Click a char to start a range" but the Add range button
  is disabled (no pending range can be formed). The bottom `char-range-add`
  button is still enabled and creates a `start=0, end=0` range.
- **`word.ocr_text` is empty** (CharFixerSection): `charBboxes` is empty; the
  CharFixerCanvas is not rendered. `cellCount = max(0, gtChars.length)` — cells
  only appear if GT is non-empty.
- **Erase probe loading**: only the loading state is shown when `backendAvailable`
  was not provided as a prop and the probe has not yet resolved.
- **Erase not available**: "Not available for this word." message with
  `erase-not-available` testid. No canvas or ops list.
- **No neighbor** (StructureSection): `prev` or `next` card shows italic "none"
  label. Merge button for the absent direction is disabled. Gap slider is
  disabled when `hasNext = false`.
- **Split with no position selected**: `splitPos = null`; the Split button
  reads "Split at midpoint" and uses `Math.floor(charCount / 2)`.
- **ReboxCanvas zoom limits**: zoom-out disabled at zoom=1; zoom-in disabled at
  zoom=5.
- **CharFixer wordKey includes `ground_truth_text`**: when the word's GT changes
  externally (e.g. from OcrGtCompareRow), the `wordKey` changes, resetting the
  draft to the new GT.

## 9. Open questions

1. **BBoxSection Refine / Crop wiring**: both "Refine" and "Crop" currently call
   `commitBbox(draft)` — identical to a manual save. Snap-to-ink refinement would
   require a dedicated backend endpoint (e.g. `POST .../words/{li}/{wi}/snap-bbox`)
   that accepts a candidate bbox and returns an ink-snapped version. This endpoint
   does not exist yet.

2. **ErasePixels lasso polygon fill**: lasso ops are sent as `shape: "rect"`
   (AABB approximation). Backend polygon fill is not yet implemented. A future
   slice could pass the lasso `points` to a new backend parameter.

3. **CharFixerCanvas persistence**: the `charfixer-apply` button commits bboxes
   to the SPA's word-attributes sidecar via `POST .../char-bboxes`. This data is
   not yet used for anything by the backend — it exists to survive page reloads
   locally. The spec for "what uses char-bboxes" (e.g. char-level segmentation
   training export) has not been written.

4. **CharRangesSection local state**: `ranges` is pure component state initialized
   empty on every mount. Previously-saved ranges from the backend (stored in
   `WordMatch.char_bboxes_map` sidecar) are not loaded back into this section on
   open. A round-trip load path needs to be defined.

5. **StructureSection confirm on merge**: the ConfirmDialog message shows a preview
   of the merged text. But the message content mentions "This cannot be undone" —
   there is no undo in the current design. Future sessions may want to clarify
   whether merge is reversible (e.g. via a split operation on the result).

6. **ReboxCanvas "snap" mode**: currently behaves identically to handle-drag
   (no ink-snapping). A future slice would inject an image-luminance probe so
   Snap mode auto-snaps handles to the nearest dark ink region.

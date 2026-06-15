# 04 — Image Viewport (Left Pane)

> **Status**: Active
> **Last updated**: 2026-05-11
> **Spec-Issue**: pdomain/pdomain-ocr-labeler-spa#12

The left pane shows the page image with paragraph/line/word bounding-box
overlays. It supports four interaction modes (select, rebox, add-word,
erase) and persistent layer-visibility / selection-mode prefs.

> Cross-refs:
> Legacy implementation —
> `pd-ocr-labeler/pd_ocr_labeler/views/projects/pages/image_tabs.py`
> Coordinate algorithm —
> `pd-ocr-labeler/.../image_tabs.py:946-985`
> Backend wire shape — [`02-backend.md`](02-backend.md)
> §5.4 (`/api/.../erase-pixels`, `/api/.../words/add`,
> `/api/.../words/{l}/{w}/rebox`)

---

## 0. Implementation choice — research spike at M4 start (D-020)

The renderer choice (Konva vs raw `<canvas>` vs SVG) is **deferred**.
At the start of M4, run a research spike with a real labeled-data
fixture (~200 lines × ~20 words = ~600 word rects per page across 4
layers) and pick the renderer that holds 60Hz on drag-move with no
jank.

Default-of-record: **raw `<canvas>` + custom hit-testing** (D-020 / Q6
answer). The component map below is written for Konva because it's
the more portable contract; if the spike picks raw canvas, replace
the `<Stage>/<Layer>/<Rect>` skeleton with an imperative paint
function. The bbox layout, color palette, modes, and event semantics
are unchanged across renderers.

The decision happens in M4. Document the result in a new ADR.

## 1. Component map (Konva sketch — actual choice in M4)

> **D-050/D-053 (shipped):** `ImageTabsHeader` was retired. Layer-visibility
> controls now live in the Rail (`rail-layer-*` buttons). Selection-mode and
> zoom controls live in the canvas overlay (`canvas-zoom-fit`, `canvas-zoom-100`,
> `mismatches-only-toggle`). `erase-pixels-button` and `add-word-button` remain
> in the canvas overlay.

```
<Rail />                                       (components/shell/Rail.tsx)
  rail-layer-block, rail-layer-para, rail-layer-line, rail-layer-word (aria-pressed)
  rail-target-block, rail-target-para, rail-target-line, rail-target-word (data-active)
<PageImageCanvas />                            (components/PageImageCanvas.tsx)
    <Stage>
      <Layer name="image">
        <Image src={page.image_url} />
      </Layer>
      <Layer name="overlays">
        <BBoxOverlay layer="paragraphs" />
      </Layer>
      <Layer name="overlays">
        <BBoxOverlay layer="lines" />
      </Layer>
      <Layer name="overlays">
        <BBoxOverlay layer="words" />
      </Layer>
      <Layer name="selection">
        <BBoxOverlay layer="selection-paragraphs" />
        <BBoxOverlay layer="selection-lines" />
        <BBoxOverlay layer="selection-words" />
      </Layer>
      <Layer name="drag">
        <DragRect />
      </Layer>
    </Stage>
```

The `<Stage>` is sized to `(encoded.display_width, encoded.display_height)`
from `PagePayload.encoded`. The wrapping div fills the available
horizontal space and adds `overflow: auto` for vertical scrolling.

---

## 2. Viewport Controls (re-homed from retired ImageTabsHeader — D-050/D-053)

### Rail layer toggles

Four `aria-pressed` buttons in the Rail control layer visibility:

- `rail-layer-block` — block bbox overlay
- `rail-layer-para` — paragraph bbox overlay (replaces `layer-paragraphs-checkbox`)
- `rail-layer-line` — line bbox overlay (replaces `layer-lines-checkbox`)
- `rail-layer-word` — word bbox overlay (replaces `layer-words-checkbox`)

Bound to `useUiPrefs.layerVisibility`. Default: all visible.

### Rail selection-mode targets

Four `data-active` buttons in the Rail control the canvas hit-test unit:

- `rail-target-block`, `rail-target-para`, `rail-target-line`, `rail-target-word`
  (replace `selection-mode-paragraph`, `selection-mode-line`, `selection-mode-word`)

Bound to `railStore.target` / `useUiPrefs.selectionMode`. Default: `word`.

### Canvas overlay controls

- **Erase Pixels** — `erase-pixels-button` (canvas overlay, `aria-pressed`).
  Toggles `useViewportStore.mode === "erase"`.
- **Add Word** — `add-word-button` (canvas overlay, `aria-pressed`).
- **Mismatches only** — `mismatches-only-toggle` (canvas overlay, `aria-pressed`).
  Dims exact/validated word bboxes to 20% opacity.
- **Zoom Fit** — `canvas-zoom-fit` (replaces `zoom-fit-button`).
- **Zoom 100%** — `canvas-zoom-100` (replaces `zoom-100-button`).

Layer colors (RGBA verbatim from legacy
`image_tabs.py:280-285,500-535`):

| Layer | Fill | Border | Stroke (selection) |
|---|---|---|---|
| Paragraphs | `rgba(34,197,94,0.20)` (green-500/20) | `rgba(22,163,74,0.65)` | `rgba(22,163,74,0.70)` 3px |
| Lines | `rgba(236,72,153,0.20)` (pink-500/20) | `rgba(190,24,93,0.65)` | `rgba(236,72,153,0.70)` 3px |
| Words | `rgba(59,130,246,0.18)` (blue-500/18) | `rgba(29,78,216,0.65)` | `rgba(59,130,246,0.60)` 3px |
| Drag rect | (no fill) | `#2563eb` 2px dashed `4 2` | — |

Tag-chip colors (used in `WordMatchView`, repeated here for cross-ref):

- Style chips: bg `#e7f0ff`, border `#b8ccf3`, color `#1f4b99`.
- Component chips: bg `#e7f8ee`, border `#b7dfc3`, color `#1f6b3a`.

`mix-blend-mode: multiply` is applied to the overlay layers so the
underlying image stays visible — match exact via Konva
`globalCompositeOperation = 'multiply'` on the `<Layer>`.

---

## 3. Coordinates

The Konva Stage works in **display pixels**. The backend works in
**source pixels**. Translate via `PagePayload.encoded`:

```ts
const scale = page.encoded.scale;   // display_width / src_width
function srcToDisplay(b: BBox): BBox {
  return { x: b.x*scale, y: b.y*scale, width: b.width*scale, height: b.height*scale };
}
function displayToSrc(b: BBox): BBox {
  return { x: Math.round(b.x/scale), y: Math.round(b.y/scale), width: ..., height: ... };
}
```

The Stage size is `display_width × display_height` (from `encoded`).
The image source is `image_url` (the cached `original` overlay,
already at `display_width`). Match exactly so the bbox rects line up
without sub-pixel drift.

`encoded.display_width` is `min(src_width, 1200)` (legacy
`_compute_encoded_dimensions:962`). Image cache is keyed by the
encoded image's content hash, so the SPA reads bytes that round-trip
the same algorithm.

---

## 4. Modes

The viewport has four mutually-exclusive modes, owned by
`useViewportStore.mode`:

### 4.1 Select (default)

Drag = box-select.

- `selectionMode` controls which overlay set is selected.
- Modifiers (handled by mousedown event):
  - **Plain drag** = replace selection.
  - **Shift+drag** = remove from selection (XOR-set difference).
  - **Ctrl+drag** = symmetric difference (toggle).
- On `mouseup`, the SPA POSTs to a backend selection endpoint:
  `POST /api/projects/{pid}/pages/{idx}/selection`
  with `{mode: "replace"|"remove"|"toggle", selection: Selection}`.
  Optimistic update via `useSelectionStore`.

The selection box draws live via the `<DragRect />` component, blue
dashed border, no fill. Clear on Escape.

### 4.2 Rebox

Triggered programmatically from the Word Edit Dialog's "Rebox" button.

- `useViewportStore.mode = "rebox"`.
- `pendingReboxTarget = { lineIdx, wordIdx }`.
- Drag draws the rect; on `mouseup`, POST
  `/api/projects/{pid}/pages/{idx}/words/{l}/{w}/rebox` with
  `{bbox: BBox}` (source coords).
- On success, mode resets to `select`; the dialog re-renders.

If the user clicks elsewhere (Esc / Cancel), mode resets without a
POST.

### 4.3 Add Word

Triggered by `Add Word` button in the toolbar.

- `useViewportStore.mode = "add-word"`.
- Drag draws the rect; on `mouseup`, POST
  `/api/projects/{pid}/pages/{idx}/words/add` with
  `{bbox: BBox, text: ""}`. The backend picks the nearest line
  (`AddWordRequest.line_index = null`).
- On success, the new word is added; mode stays in `add-word` until
  the toolbar button is clicked again (allows multi-add).

The `Add Word` button is a **toggle**: pressed-state while in mode.

### 4.4 Erase

Triggered by the `Erase Pixels` button.

- `useViewportStore.mode = "erase"`.
- Drag draws a red-fill rect (preview) `rgba(255,255,255,0.92)`,
  `rgba(220,38,38,0.75)` stroke. Match legacy.
- On `mouseup`, POST
  `/api/projects/{pid}/pages/{idx}/erase-pixels` with `{bbox}`. The
  backend mutates the in-memory page image (white-out fill_value=255).
- Multiple drags allowed without leaving mode (same as Add Word).
- Click `Erase Pixels` again to leave mode, or Escape.

---

## 5. Selection rendering

Overlay rectangles for paragraphs, lines, words come from
`PagePayload.line_matches[].word_matches[].bbox` (words),
`page_dict.lines[].bbox` (lines), and
`page_dict.lines[].paragraph_bbox` (paragraphs).

Selection rectangles are rendered in a separate Konva layer on top
with `stroke-width=3` per the legacy. The selection set comes from
`useSelectionStore`, which is reconciled with `selection` from the
backend on every page fetch.

When selection-mode = `paragraph`, click inside a paragraph bbox
selects that paragraph; ditto for line/word. Click outside any bbox
clears.

---

## 6. Hotkeys (viewport-scope)

Registered via `useHotkey` only when the canvas has focus
(implementation: tabindex=0 wrapper + `:focus` selector or React
event handlers). See [`12-hotkeys-a11y.md`](12-hotkeys-a11y.md).

| Key | Action |
|---|---|
| `Esc` | Cancel pending mode (back to select); clear drag rect; clear selection |
| `Shift+P` | Toggle paragraph layer |
| `Shift+L` | Toggle line layer |
| `Shift+W` | Toggle word layer |
| `Shift+1` / `Shift+2` / `Shift+3` | Switch selection mode (paragraph/line/word) |
| `Shift+E` | Toggle Erase mode |
| `Shift+A` | Toggle Add Word mode |

These are **new** — the legacy has no viewport hotkeys
([D-022](../../specs/17-decisions.md)).

---

## 7. Performance budget

- Re-render per drag-move event: only the `<DragRect />` layer
  re-renders (Konva `Layer.batchDraw()`). Paragraph/line/word layers
  are static between drags.
- 200-line page: ~600 word rects × 4 layers ≈ 2,400 Konva nodes.
  Acceptable per Konva docs (their threshold is ~10k).
- If we exceed 5k word rects (huge pages), switch to a single-canvas
  approach: render bbox rects with `<Shape>` and a custom paint
  function. Defer; not v1.

---

## 8. Tests

- Unit (Vitest, jsdom + Konva mock): `BBoxOverlay.test.tsx` — given a
  list of bboxes + visibility flag, renders the right number of rects
  with the right colors.
- Unit: `coords.test.ts` — `srcToDisplay` / `displayToSrc` round-trip,
  edge cases (negative scale, integer rounding).
- Unit: `marquee.test.ts` — port from pgdp-prep — rect-overlap helper.
- E2E (Playwright): `test_image_viewport.py` —
  - load page, see image rendered
  - toggle each layer checkbox, see overlays appear/disappear
  - drag a box in `word` selection mode, see the affected words
    highlighted (selection layer rects have `stroke-width=3`)
  - Shift+drag removes from selection
  - Click Erase Pixels, drag a box, see edit applied (Reload OCR
    Edited produces different OCR text)
  - Click Add Word, drag a box, see new word appear in the matches
    view at the corresponding line.

---

## 9. Open issues

- **Word-rebox UI conflict.** When the dialog is open AND mode is
  `rebox`, where does the Stage live? Options: (a) keep the main
  viewport's Stage in `rebox` mode; the user dismisses the dialog
  while rebox happens. (b) embed a smaller Stage inside the dialog.
  Spec author's bet: **(a)** — the dialog is closed for the duration
  of the rebox drag, then reopened with the new bbox preview.
  Confirm in M7 implementation.
- **Drag throttling.** The legacy redraws on every server-side mousemove
  (websocket roundtrip!). The SPA can throttle to ~60Hz client-side
  with `requestAnimationFrame`. Implement and benchmark in M4.

## 10. Closed decisions

- **ImageTabs text-overlay sub-tabs (#295).** Resolved 2026-05-16 per
  D-045: no text-overlay sub-tabs (GT / OCR / Matches overlaid on the
  canvas) will be added. The `mismatches-only-toggle` in the canvas
  overlay is the shipped resolution. Coverage for the GT and
  OCR use-cases comes from the right-pane `TextTabs` (Matches / Ground
  Truth / OCR) and the `WordDetail` / `LineDetail` panels. See
  `specs/17-decisions.md` D-045.

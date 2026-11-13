---
kind: architecture
status: built
owner: maintainers
created: 2026-05-06
last_verified: 2026-11-13
---

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

The renderer choice is shipped: `PageImageCanvas.tsx` mounts the shared `PdUiPageImageCanvas` Konva host.
The host owns the Stage and layer skeleton; Labeler supplies domain overlays, hit testing and gestures.
`BBoxOverlay` delegates rectangles to the shared `RectOverlayLayer`. The original M4 decision is history;
see [renderer ownership](21-konva-renderer.md).

## 1. Component map (Konva sketch — actual choice in M4)

The shared PageImageCanvas host owns Stage/bitmap/focus/scale. Labeler fills selection/tool slots with
BBoxOverlay, block/region overlays and mode gestures. Hidden DOM geometry sidecars serve automation.
The right panel is the editor; it does not require a second Stage or a word-edit modal.

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

- **Erase Pixels** — `rail-mode-erase` (Rail).
  Toggles `useViewportStore.mode === "erase"`.
- **Add Word** — `add-word-button` (canvas overlay, `aria-pressed`).
- **Mismatches only** — `mismatches-only-toggle` (canvas overlay, `aria-pressed`).
  Dims exact/validated word bboxes to 20% opacity.
- **Zoom Fit** — `canvas-zoom-fit` (replaces `zoom-fit-button`).
- **Zoom 100%** — `canvas-zoom-100` (replaces `zoom-100-button`).

Current layer colors resolve theme CSS aliases through useLayerColors and the shared RectOverlayLayer.
The palette below is a historical legacy comparison, not the current token contract
(`image_tabs.py:280-285,500-535`):

| Layer | Fill | Border | Stroke (selection) |
|---|---|---|---|
| Paragraphs | `rgba(34,197,94,0.20)` (green-500/20) | `rgba(22,163,74,0.65)` | `rgba(22,163,74,0.70)` 3px |
| Lines | `rgba(236,72,153,0.20)` (pink-500/20) | `rgba(190,24,93,0.65)` | `rgba(236,72,153,0.70)` 3px |
| Words | `rgba(59,130,246,0.18)` (blue-500/18) | `rgba(29,78,216,0.65)` | `rgba(59,130,246,0.60)` 3px |
| Drag rect | (no fill) | `#2563eb` 2px dashed `4 2` | — |

Tag-chip colors (used in `WordMatchView`, repeated here for cross-ref):

- Style chips: bg `#e7f0ff`, border `#b8ccf3`, color `#1f4b99`.
- Component chips: bg `#e7f8ee`, border `#b7dfc3`, color `#1f6b3a`.

Current composition belongs to the shared host/overlay implementation. Do not infer an exact blend-mode
requirement from the historical palette. PageImageCanvas.test.tsx verifies CSS-token fallback mode colors.

---

## 3. Coordinates

Geometry mutations use source-pixel boxes. `lib/coords.ts` handles source/display encoding transforms;
the shared host supplies effective pointer scale including viewport zoom. Encoded-image scale and zoom
are distinct and must not be applied twice. Existing tests cover round-trip geometry within one pixel.
PageImageCanvas passes the source geometry to the current rebox/add/erase handlers.

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

The viewport actions register at document scope through `useHotkey`, with an enabled flag.
Viewport ownership here describes the action, not a requirement that the canvas hold keyboard focus.

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

Word editing is mounted in the right panel. `ReboxSection` owns draft geometry and Apply rebox; a viewport
rebox drag uses the main shared Stage. There is no word-edit dialog/secondary-Stage decision left to make.

The performance budgets above are targets. This source inspection does not establish a fresh 60 Hz benchmark
or a new drag-throttling result.

## 10. Closed decisions

- **ImageTabs text-overlay sub-tabs (#295).** Resolved 2026-05-16 per
  D-045: no text-overlay sub-tabs (GT / OCR / Matches overlaid on the
  canvas) will be added. The `mismatches-only-toggle` in the canvas
  overlay is the shipped resolution. Coverage for the GT and
  OCR use-cases comes from the right-pane `TextTabs` (Matches / Ground
  Truth / OCR) and the `WordDetail` / `LineDetail` panels. See
  `specs/17-decisions.md` D-045.

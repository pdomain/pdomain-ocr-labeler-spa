# pdomain-ocr-labeler-spa: Image Viewport (Left Pane)

> **Status**: Draft
> **Last updated**: 2026-05-12
> **Spec-Issue**: ConcaveTrillion/pdomain-ocr-labeler-spa#12

## TL;DR

The left pane shows the scanned page image with paragraph/line/word bbox overlays and
supports four interaction modes (select, rebox, add-word, erase). Renderer: **Konva**
(planned default; D-020 defers final choice to a research spike at M4 start). Overlays use `mix-blend-mode: multiply` with
legacy-exact RGBA color values. Coordinate translation between source pixels (backend)
and display pixels (Konva Stage) is via `PagePayload.encoded.scale`.

## Context

The legacy implementation (`image_tabs.py`) renders overlays using PIL/OpenCV into
pre-composited JPEG images served from the image cache. The SPA replaces this with a
live Konva canvas where overlays are drawn as interactive vector rects, enabling
selection, drag-rebox, and add-word operations without server round-trips for the render
itself. Only mutations (selection POST, rebox POST, add-word POST, erase POST) require a
network call.

The renderer decision is deferred to M4 (D-020) with a research spike on a real ~600-word
fixture. Konva is the planned path documented here; the spike may confirm or revise this choice
before M4 implementation begins.

## Constraints

- **Legacy-exact layer colors.** RGBA values are verbatim from `image_tabs.py:280-285,500-535`;
  deviating causes visual regressions in user workflows trained on the legacy UI.
- **`mix-blend-mode: multiply` on overlays.** The underlying image must remain visible.
  Implemented via Konva `globalCompositeOperation = 'multiply'` on overlay Layers.
- **Source-pixel API.** All bbox coordinates sent to the backend are in source image
  pixels (top-left origin). The Stage works in display pixels; `coords.ts` handles the
  translation.
- **Four mutually-exclusive modes.** At most one of `select | rebox | add-word | erase`
  is active at a time. Mode is owned by `useViewportStore.mode`.
- **Rebox triggered programmatically.** The rebox mode is entered only from the Word
  Edit Dialog's "Rebox" button; there is no direct UI toggle.
- **Konva only in canvas components.** `react-konva` is not imported outside
  `PageImageCanvas.tsx` and `WordEditDialog.tsx`.

## Decision

### Component tree

```
<ImageTabs>
  <ImageTabsHeader>   — layer checkboxes, selection-mode radio, Erase button, legend
  <PageImageCanvas>
    <Stage w=display_width h=display_height>
      <Layer name="image">   <Image src={image_url} />
      <Layer name="overlays" globalCompositeOperation="multiply">
        <BBoxOverlay layer="paragraphs" />
        <BBoxOverlay layer="lines" />
        <BBoxOverlay layer="words" />
      </Layer>
      <Layer name="selection">   <BBoxOverlay layer="selection-*" />
      <Layer name="drag">        <DragRect />   (box-select / rebox / add-word preview)
```

### Coordinate system

`lib/coords.ts` exports:

- `srcToDisplay(bbox, scale)` — multiply x/y/w/h by `scale`.
- `displayToSrc(bbox, scale)` — divide and `Math.round`.

`scale = encoded.display_width / encoded.src_width`. Stage dimensions:
`display_width × display_height`. Image `src` is `image_url` (cached at display size).

### Layer colors (verbatim from legacy)

| Layer      | Fill                   | Border               |
|------------|------------------------|----------------------|
| Paragraphs | `rgba(34,197,94,0.20)` | `rgba(22,163,74,0.65)` |
| Lines      | `rgba(236,72,153,0.20)`| `rgba(190,24,93,0.65)` |
| Words      | `rgba(59,130,246,0.18)`| `rgba(29,78,216,0.65)` |
| Drag rect  | none                   | `#2563eb` 2px dashed   |

Selection strokes: 3px solid at 0.70 alpha of the border color.

### Interaction modes

**Select (default).** Drag = box-select. Modifier keys on `mousedown`: plain = replace,
Shift = remove (XOR), Ctrl = toggle. On `mouseup`, POST
`/api/projects/{pid}/pages/{idx}/selection`. Optimistic update via `useSelectionStore`.
Escape clears selection. `<DragRect />` shows the live drag box.

**Rebox.** Entered programmatically from Word Edit Dialog. `pendingReboxTarget` holds
`{lineIdx, wordIdx}`. Drag + `mouseup` → POST `.../words/{l}/{w}/rebox`. Mode resets to
`select` on success or Escape.

**Add Word.** Toggle button in toolbar. Drag + `mouseup` → POST `.../words/add` with
`{bbox, text: ""}` (backend auto-assigns nearest line). Mode stays active for
multi-add until toggled off.

**Erase.** Toggle button in `ImageTabsHeader` (`data-testid="erase-pixels-button"`).
Drag + `mouseup` → POST `.../erase-pixels` with `{bbox, fill_value: 255}`. Mode stays
active until toggled off or Escape.

### Viewport hotkeys

`Shift+P/L/W` — toggle paragraph/line/word layer. `1/2/3` — set selection mode
(paragraph/line/word). `Shift+E` — toggle erase mode. `Shift+A` — toggle add-word mode.
`Esc` — clear selection / exit non-select mode. RAF throttle on `mousemove` drag events.

## Contract / Acceptance

- Playwright: bbox rects align with the page image at 1:1 display scale (no sub-pixel
  drift) for a known fixture envelope.
- Playwright: drag box-select in word mode sends POST selection with correct word indices.
- Playwright: layer visibility toggles hide/show overlay rects without page reload.
- Vitest: `coords.ts` round-trips `srcToDisplay → displayToSrc` to within 1 px for a
  set of known bbox values.
- Layer colors match legacy RGBA values (snapshot test on `BBoxOverlay` render).

## Trade-offs considered

**Konva vs raw `<canvas>` vs SVG.** Konva is the planned choice: scene-graph abstraction
makes bbox overlay and interaction modes tractable; raw canvas requires hand-rolling hit
detection and layer management; SVG degrades on large bbox counts. D-020 spike at M4 start
will validate Konva at 60 Hz on a 600-word fixture before implementation commits.

**Client-side selection state vs server-only.** Optimistic updates (client mirrors
before server confirms) give instant visual feedback on click/drag. The server is
authoritative; on conflict the server response wins and the store is reconciled.

**RAF throttle on mousemove.** Without throttling, `mousemove` fires at display refresh
rate and triggers Konva re-renders on every event. RAF throttle caps redraws to one per
frame, eliminating jank on drag.

**Erase button in header vs toolbar.** The erase operation affects the image, not a
word-level label — it belongs with the viewport controls, not the labeling toolbar.
Header placement mirrors legacy UI positioning.

## Consequences

- Every new overlay layer (e.g., a glyph-highlight layer in M9.9) requires a new color
  constant in `coords.ts` and a new `<BBoxOverlay>` instance in the Stage.
- `displayToSrc` must round to integers before sending to the API; non-integer bbox
  coordinates will be rejected by the Pydantic model.
- The Konva Stage size is fixed at `display_width × display_height`; zooming (if added
  in a later milestone) requires scaling the Stage transform, not resizing it.

## Open questions

- **D-020 / Q-A14 — renderer choice.** Konva vs raw canvas is deferred to the M4 research
  spike. If the spike recommends raw canvas, this spec's Decision and Contract sections must
  be revised before M4 implementation begins. See `OPEN_QUESTIONS.md §Q-A14`.

## References

- `specs/04-image-viewport.md` — legacy feature doc (full interaction detail)
- `specs/13-driver-contract.md` — testids for layer checkboxes and selection-mode radio
- `lib/coords.ts` — coordinate transform utilities
- `specs/01-data-models.md §BBox`, `§EncodedDims` — coordinate model
- `pd-ocr-labeler/pd_ocr_labeler/views/projects/pages/image_tabs.py` — legacy reference

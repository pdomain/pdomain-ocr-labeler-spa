---
kind: architecture
status: built
owner: maintainers
created: 2026-05-14
last_verified: 2026-07-13
---

# 21 — Konva renderer for the image viewport

> **Status**: Active (shipped — supersedes D-020 deferral via D-043).
> **Spec-Issue**: pdomain/pdomain-ocr-labeler-spa#289
> **Replaces**: `04-image-viewport.md` §0
> **Last updated**: 2026-05-14

Replaces the DOM-stub `PageImageCanvas` and the no-op `BBoxOverlay`
with a real Konva renderer. The component shape from
[`04-image-viewport.md`](04-image-viewport.md) stands; this spec fills in
the bodies. The shipped
`frontend/src/components/PageImageCanvas.tsx`
contains the resulting `react-konva` patterns, hover guides, drag preview, and
image loading at full-page viewport scale.

---

## 1. Goals

- Render the full page image at `EncodedDims.display_width`.
- Draw overlay rects for `paragraphs`, `lines`, `words` per
  visibility checkboxes, with `globalCompositeOperation="multiply"`
  so the image remains visible.
- Support four mutually-exclusive drag interaction modes from
  `useViewportStore`: `select` (with replace / remove / toggle
  modifiers), `rebox`, `add-word`, `erase`.
- Render the live drag preview rect with mode-specific stroke
  color.
- Render the selection overlay with 3px stroke per layer color.
- Stay at 60 Hz on a 4 K page with ~600 word rects across 4 layers
  (the legacy threshold).

---

## 2. Non-goals (this spec)

- Pan / zoom UI controls — out of v1; the legacy doesn't have them
  either. The Stage is sized to display dimensions and lives inside
  an `overflow: auto` div. Future work.
- A "minimap" / fit-to-window mode — not in legacy, not in v1.
- Sub-pixel rect anti-aliasing toggles — Konva's defaults are
  acceptable.
- Konva-Image filter pipeline (brightness, contrast). Not in legacy.

---

## 3. Decision — Konva commitment (D-043)

Confirmed: **Konva is the renderer for v1 and beyond.** Raw
`<canvas>` fallback in D-020 is dropped because:

1. `WordImageCanvas.tsx` already proves Konva works in our toolchain
   (jsdom mock + production bundle).
2. The legacy bbox count per page (~600 word rects × 4 layers
   ≈ 2,400 nodes) is well below Konva's "~10 k nodes" performance
   ceiling per the official docs.
3. Refactor cost from D-020's research-spike framing has accumulated
   for 8 months without producing a measurement, and the absence has
   left the renderer un-implementable.
4. The component contract in `04-image-viewport.md` is already
   Konva-shaped; switching to raw canvas would require rewriting all
   downstream specs (selection, drag-rect overlay, hover guides).

See [`specs/17-decisions.md` D-043](../../specs/17-decisions.md#d-043--konva-renderer-commitment-supersedes-d-020).

---

## 4. Component layout

```text
<PageImageCanvas
  imageUrl=…
  encoded=…
  paragraphs=…
  lines=…
  words=…
  selection=…
  onBoxSelect / onRebox / onAddWord / onErasePixels
>
  <Stage width=encoded.display_width height=encoded.display_height>
    <Layer name="image">
      <KonvaImage image=img />                       ← loaded via useImage
    </Layer>
    <Layer name="overlay-paragraphs" listening=false
           globalCompositeOperation="multiply">
      <BBoxOverlay layer="paragraphs" items=paragraphs visible=… />
    </Layer>
    <Layer name="overlay-lines" listening=false …>
      <BBoxOverlay layer="lines" items=lines visible=… />
    </Layer>
    <Layer name="overlay-words" listening=false …>
      <BBoxOverlay layer="words" items=words visible=… />
    </Layer>
    <Layer name="selection" listening=false>
      <BBoxOverlay layer="selection-paragraphs" items=selection.paragraphs />
      <BBoxOverlay layer="selection-lines"      items=selection.lines />
      <BBoxOverlay layer="selection-words"      items=selection.words />
    </Layer>
    <Layer name="drag">
      {dragRect && <Rect … stroke=MODE_RECT_COLORS[mode] dash=[4,2] />}
    </Layer>
  </Stage>
</PageImageCanvas>
```

`listening={false}` on overlay layers turns off Konva hit-testing for
the static rects — gives a ~10× speedup on hit-test-heavy pages.
Selection drag fires on the Stage itself, not on overlay rects.

---

## 5. Image loading

Use `use-image` (peer dependency to `react-konva`; already in the
ecosystem). If we choose not to add a new dep, the
`WordImageCanvas.ImageLayer` pattern (line 347-373) — native
`new window.Image()` + `useState` + `Rect fillPatternImage` — works
but is awkward for a primary image (not a fill pattern).

**Decision.** Add `use-image@^1.1` as a dep alongside `react-konva`.
Worth ~3 KB gzip to avoid the fill-pattern shim.

```tsx
import useImage from "use-image";

function PageImage({ url, width, height }: { url: string; width: number; height: number }) {
  const [img] = useImage(url, "anonymous");  // CORS — backend serves image cache
  if (!img) return <Rect width={width} height={height} fill="#f3f4f6" />;
  return <KonvaImage image={img} width={width} height={height} />;
}
```

`anonymous` CORS mode is required so Konva can read pixels (for any
future toDataURL exports); the backend image-cache route must respond
with `Access-Control-Allow-Origin: *` for same-origin or `null` —
already true per spec 02 §image-cache.

---

## 6. Overlay rendering

`BBoxOverlay` is rewritten from "data-div stub" to a real
`<>` fragment of `<Rect>` elements:

```tsx
export function BBoxOverlay({ layer, items, visible = true }: BBoxOverlayProps) {
  if (!visible) return null;
  const colors = LAYER_COLORS[layer];
  return (
    <>
      {items.map((item) => (
        <Rect
          key={item.id}
          x={item.bbox.x}
          y={item.bbox.y}
          width={item.bbox.width}
          height={item.bbox.height}
          fill={colors.fill}
          stroke={colors.stroke}
          strokeWidth={item.selected ? SELECTION_STROKE_WIDTH : colors.strokeWidth}
          listening={false}            // hit-testing handled by parent Stage
          perfectDrawEnabled={false}   // disables 2-pass stroke render — faster
        />
      ))}
    </>
  );
}
```

**Important.** `BBoxOverlay` no longer carries `data-testid` on a div
(Konva nodes don't render DOM elements). Driver-contract tests must
shift to either:

- Walking the Stage via `stage.find('Rect')` from a test helper
  exposed on `window.__bbox_overlay_introspect` (Vitest only); OR
- A parallel `<div role="presentation" data-bbox-count="…">` rendered
  *outside* the Stage as a test-only sidecar; OR
- E2E-only assertions via Playwright clicking on rect locations.

**Decision.** Keep the sidecar div alongside the Stage:

```tsx
{import.meta.env.MODE !== "production" && (
  <div
    data-testid={`bbox-overlay-${layer}`}
    data-layer={layer}
    data-item-count={items.length}
    style={{ position: "absolute", visibility: "hidden", pointerEvents: "none" }}
    aria-hidden="true"
  />
)}
```

Production bundles drop the div entirely; jsdom tests keep the
existing assertion contract. Driver-contract Playwright tests
continue to use the data-attribute counts; visual assertions move to
real screenshot tests in E2E.

---

## 7. Drag modes

Modes live in `useViewportStore.mode: "select" | "rebox" | "add-word"
| "erase"` (already in `frontend/src/stores/viewport-store.ts`).

Stage handlers:

```ts
function handleMouseDown(e: KonvaEventObject<MouseEvent>) {
  const pos = e.target.getStage()?.getPointerPosition();
  if (!pos) return;
  setDragState({ startX: pos.x, startY: pos.y, modifier: resolveModifier(e.evt) });
}

function handleMouseMove(e: KonvaEventObject<MouseEvent>) {
  if (!dragState) return;
  // Throttle to rAF — set state on rAF tick, not every mousemove
  scheduleDragUpdate(() => {
    const pos = e.target.getStage()?.getPointerPosition();
    if (!pos) return;
    setDragRect(computeRect(dragState, pos));
  });
}

function handleMouseUp(e: KonvaEventObject<MouseEvent>) {
  if (!dragState) return;
  const rect = computeRect(dragState, e.target.getStage()!.getPointerPosition()!);
  const isTrivial = rect.width <= 2 && rect.height <= 2;
  clearDrag();
  if (isTrivial) return;
  switch (mode) {
    case "select":   onBoxSelect?.(rect, dragState.modifier); break;
    case "rebox":    onRebox?.(rect); exitToSelectMode(); break;
    case "add-word": onAddWord?.(rect); /* stay */ break;
    case "erase":    onErasePixels?.(rect); exitToSelectMode(); break;
  }
}
```

`scheduleDragUpdate` is a single-flight rAF scheduler — see
`frontend/src/lib/rafSchedule.ts` (new). At 60 Hz a typical drag
fires ~60 update calls per second, well below React 19's render
budget.

---

## 8. Selection

`PagePayload.selection: Selection` carries `paragraph_indices: int[]`,
`line_indices: (line_index)[]`, `word_indices: (line_index, word_index)[]`
(per spec 01 §2). The renderer expands these into BBox lists by
joining against `PageRecord.lines` / `line_matches`. Helper:

```ts
function expandSelection(page: PagePayload): {
  paragraphs: BBoxItem[];
  lines: BBoxItem[];
  words: BBoxItem[];
} { ... }
```

Lives in `frontend/src/lib/selection-expand.ts` (new). Tested with
Vitest fixtures.

When `selectionMode` is `paragraph` (legacy default for "paragraph"
mode), drag-rect intersection is computed against paragraph bboxes;
ditto for line / word. The legacy implements this in
`_apply_box_selection` in the legacy sibling's `image_tabs.py`.

Selection-mode types must align with the legacy:
`paragraph | line | word`. The current SPA mismatch
(`"box" | "line" | "word"`) is fixed as part of this spec.

---

## 9. Cursors

| Mode | Cursor | Drag-rect stroke |
|---|---|---|
| select | `crosshair` | `#2563eb` (blue-600) |
| rebox | `cell` | `#16a34a` (green-600) |
| add-word | `copy` | `#9333ea` (purple-600) |
| erase | `not-allowed` | `#dc2626` (red-600), fill `rgba(220,38,38,0.20)` |

Set via `Stage`'s wrapping `<div style={{ cursor: MODE_CURSORS[mode] }}>`.

---

## 10. Hotkeys (viewport-scope)

Already defined in `useViewportHotkeys.ts` — this spec doesn't change
them. They become functional once the viewport is wired into a
focused element:

- `Esc` — return to select, clear drag, clear selection
- `Shift+P/L/W` — toggle paragraph/line/word layer visibility
- `Shift+1/2/3` — selection mode paragraph/line/word
- `Shift+E` — toggle erase mode
- `Shift+A` — toggle add-word mode

`Stage` cannot natively `tabIndex`; we wrap it in
`<div tabIndex={0} ref={focusRef} onKeyDown={…}>` and call `focus()`
on mount. Keep keyboard focus visible (`focus-visible:ring-2`).

---

## 11. Performance pinning

- `Layer` props: `listening={false}` on overlay layers (image,
  paragraphs, lines, words, selection). Only the `drag` layer
  listens.
- `Rect` props: `perfectDrawEnabled={false}` on every overlay rect.
- `BBoxOverlay` memoizes its `items` via `React.memo` keyed on
  `items` identity. Parent must pass stable references — backed by
  `useMemo` over the relevant payload slice.
- `Stage.batchDraw()` is unnecessary in `react-konva` (auto-batched).
- rAF throttling on `mousemove` (spec §7).

**Acceptance benchmark.** On a typical book page (200 lines, ~20
words/line → 4 000 word rects), `useViewportHotkeys` test reports
`drag-move duration <16 ms` for 60 consecutive frames in headless
Chromium. Add an E2E benchmark in `tests/e2e/test_viewport_perf.py`.

---

## 12. Driver-contract testids

Preserve every legacy testid that lands inside the viewport:

| testid | Element | Source |
|---|---|---|
| `image-viewport` | wrapper div | retained from current stub |
| `ocr-drag-rect` | drag-preview Rect | retained — must be the DOM sidecar div, not the Konva node |
| `bbox-overlay-paragraphs` | sidecar div | dev/test mode only |
| `bbox-overlay-lines` | sidecar div | dev/test mode only |
| `bbox-overlay-words` | sidecar div | dev/test mode only |

The Konva `Stage` is `data-testid="image-stage"` (new — for E2E
assertions about Stage geometry). `ocr-drag-rect` cannot be a Konva
node and remain a `data-testid` selector for Playwright — therefore
during a drag we **mirror** the drag rect into a transparent sibling
div (positioned absolutely over the Stage) so the driver can locate
it without touching Konva.

---

## 13. Edge cases

- **No image yet.** `encoded == null` ⇒ render an empty
  `<div data-testid="image-viewport" data-state="empty">` — no Stage.
- **Image fetch fails.** `useImage` returns `[undefined, "failed"]`;
  show a fallback `Rect` with `fill="#f3f4f6"` plus a centered text
  Konva node "Failed to load page image". Emit `image-load-failed`
  notification (spec 11).
- **Drag exits Stage area.** Use `onMouseLeave` on the wrapping div
  to clear `dragState` and `dragRect`. Don't fire the mode callback.
- **Window resize.** Stage dimensions come from `EncodedDims`, not
  window size; resize doesn't matter. The `overflow: auto` wrapper
  handles viewport sizing.
- **Multiple selection layers active.** Selection layer always
  renders all three (paragraph/line/word) sets simultaneously, even
  when only one selection mode is active — the legacy does this and
  it makes "what's selected" obvious across multi-step edits.

---

## 14. Tests

**Unit (Vitest + Konva mock).**

- `PageImageCanvas.test.tsx` — gain test cases: image renders when
  `imageUrl` provided; Stage size matches `encoded`; drag in each
  mode fires the right callback; mode auto-resets per rules.
- `BBoxOverlay.test.tsx` — given `items=[…]`, the Stage finds N
  `Rect` nodes (use `stage.find('Rect').length` via the Konva mock).
  Colors match `LAYER_COLORS`.
- `selection-expand.test.ts` — round-trip selection indices to
  BBox lists.

**E2E (Playwright).**

- `test_viewport_drag_select.py` — load page; drag word-area box;
  assert selection POST fires with right payload; assert selection
  layer renders rects.
- `test_viewport_rebox.py` — open word edit dialog; click Rebox; drag;
  assert rebox POST fires; mode resets.
- `test_viewport_perf.py` — synthetic 4 000-rect page; drag for 1 s;
  assert `frame_count >= 55`.

---

## 15. Migration plan

This spec lands as **3 issues**:

1. **spec-21-A** Konva primary canvas — `PageImageCanvas` Stage +
   image loading + drag handlers. Acceptance: page image visible,
   drag rect fires `onBoxSelect`.
2. **spec-21-B** Overlay rendering — `BBoxOverlay` Rect-based;
   sidecar test divs; selection expansion helper. Acceptance:
   overlay rects render with correct colors; selection rects
   show 3 px stroke.
3. **spec-21-C** Rebox / add-word / erase mode wiring + perf passes.
   Acceptance: each mode fires the right callback, resets per rules,
   60 Hz benchmark passes.

Issues 21-A and 21-B can run in parallel; 21-C depends on both. All
three land before any work on [`22-page-surface-wireup.md`](22-page-surface-wireup.md)
because spec 22 mounts `PageImageCanvas` in `ProjectPage`.

---

## 16. Refs

- Component contract that this spec implements:
  [`04-image-viewport.md`](04-image-viewport.md).
- Konva commitment:
  [`../../specs/17-decisions.md` D-043](../../specs/17-decisions.md#d-043--konva-renderer-commitment-supersedes-d-020).
- Superseded:
  [`../../specs/17-decisions.md` D-020](../../specs/17-decisions.md#d-020--defer-konva-vs-canvas-decision-to-m4-with-research-subagent).
- Legacy renderer: `pd-ocr-labeler/pd_ocr_labeler/views/projects/pages/image_tabs.py`.
- Shipped renderer: `frontend/src/components/PageImageCanvas.tsx`.
- `react-konva` + `use-image` docs.

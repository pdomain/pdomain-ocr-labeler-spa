---
kind: architecture
status: built
owner: maintainers
created: 2026-05-14
last_verified: 2026-11-13
---

# 21 — Konva renderer and shared canvas ownership

The mounted renderer uses `PdUiPageImageCanvas` from `@pdomain/pdomain-ui/canvas`. The shared host owns
the Konva Stage, bitmap, sizing, focus and effective scale. Labeler owns domain overlays, selection and
gesture dispatch. This is the implemented boundary, not a pending renderer migration.

## Layers and state

Local overlays cover paragraph, line, word, block and region geometry, including confirmed/proposed/selected
regions. `BBoxOverlay` delegates rectangle rendering to the shared `RectOverlayLayer`, preserving theme
colors, selected strokes and dimming. Selection comes from the local selection store and its expansion
helpers, rather than waiting for a page payload to echo a canvas click.

Pointer callbacks use `CoordContext.scale` from the host. Encoded-image scale and viewport zoom are separate
transforms. Fit-page and 100% controls are mounted. `image-stage` and `ocr-drag-rect` are hidden DOM geometry
sidecars for automation, not IDs attached directly to the Konva Stage.

## Gestures and editing

Select, rebox, add-word and erase remain distinct modes. Replace, add and remove modifiers are tested by
`PageImageCanvas.test.tsx`; a 3px threshold distinguishes a drag from a click. The main Stage remains mounted
while the right panel edits a selected word. There is no word-edit modal or second-Stage rebox decision.
Region hit-testing and resize gestures share the host coordinate context.

The page-scoped erase route persists edited pixels; a successful canvas erase resets the mode to View/select.
Word-scoped erasure in the right panel is a separate operation. The earlier erase-stays-active target is not
the mounted behavior; it remains a design discrepancy in the partial behavior-completion spec.

## Performance and limits

`tests/e2e/test_viewport_perf.py` exercises 4,000 rectangles and counts requestAnimationFrame callbacks,
with a target of at least 55. That test is not a per-frame sub-16ms measurement or a fresh measured 60 Hz result
from this documentation inspection. Existing performance targets remain targets. Minimap/filter ideas do
not become approved implementation work through this migration.

## Evidence

- Code: `frontend/src/components/PageImageCanvas.tsx`, `BBoxOverlay.tsx`, `lib/coords.ts`,
  `lib/selection-expand.ts` and the local viewport/selection stores.
- Tests: `PageImageCanvas.test.tsx`, `BBoxOverlay.test.tsx`, `lib/selection-expand.test.ts`,
  `tests/e2e/test_viewport_perf.py`, `test_image_click_selection.py` and `test_canvas_erase.py`.
- Current shell composition: [shell layout](24-shell-layout.md); coordinate/mode contract:
  [image viewport](04-image-viewport.md); current automation: [driver contract](13-driver-contract.md).
- Verified: 2026-11-13 by source and test inspection. Historical renderer decisions remain in the ADR log.

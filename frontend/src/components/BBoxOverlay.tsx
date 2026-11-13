import { type LayerName, LAYER_COLORS } from "./layerColors";
// BBoxOverlay.tsx — Konva bounding-box overlay (spec-21-A3, #298).
//
// Spec: specs/21-konva-renderer.md §6 (overlay rendering), §12 (testids).
// Issues: #196 (LAYER_COLORS RGBA constants), #298 (Konva-rect rewrite),
//         #328 (FO-4: migrate to useLayerColors CSS vars).
// Slice 13: added `dimmed` prop for target-scoped opacity (hi-fi redesign).
//
// Renders one react-konva <Rect> per item inside whatever <Layer> the caller
// has provided. Colours come from useLayerColors() for theme-mapped layers
// (paragraphs / lines / words); drag-rect and selection-* use hardcoded specs.
// Selected items use SELECTION_STROKE_WIDTH (3 px). perfectDrawEnabled=false
// and listening=false per spec §11 perf pinning (overlay rects never
// participate in hit-testing).
//
// A dev/test-only sidecar <div data-testid="bbox-overlay-${layer}"
// data-layer data-item-count data-dimmed> is rendered alongside the fragment
// so the driver-contract Playwright tests can read the per-layer item count
// without poking into Konva nodes (spec §6, §12). Production bundles drop
// the sidecar entirely via the `import.meta.env.MODE !== "production"` gate.
//
// Legacy-exact RGBA values from
// pd-ocr-labeler/pd_ocr_labeler/views/projects/pages/image_tabs.py:280-285,500-535
// are now the FALLBACK values inside useLayerColors.ts; the live colors are
// theme-controlled via --layer-* CSS custom properties.
// Selection RGBA from image_tabs.py:514-519 (fill rgba(37,99,235,0.20),
// stroke #1d4ed8). The legacy renders selection strokes at width 1; spec
// §6/§8 bumps to 3 px via the `selected` branch on BBoxItem.

import { memo } from "react";
import { RectOverlayLayer, type RectOverlayItem } from "@pdomain/pdomain-ui/canvas";
import type { BBox } from "../lib/coords";
import {
  useLayerColors,
  hexToLayerColorSpec,
  buildSelectionLayerSpec,
  buildDragRectLayerSpec,
  type LayerColorSpec,
} from "../hooks/useLayerColors";

/** Layer name type. */

/**
 * Legacy-exact layer colors — static fallback constants.
 *
 * These match the hardcoded RGBA values from the legacy NiceGUI labeler
 * (image_tabs.py:280-285,500-535) and double as the DARK-THEME fallbacks in
 * `useLayerColors.ts`. They are exported so legend/UI components that need
 * a static reference can still import them. BBoxOverlay itself reads from
 * `useLayerColors()` at render time (FO-4, issue #328).
 *
 * Source: image_tabs.py:280-285,500-535.
 */

/** Selection stroke width: 3 px (spec §6, §8). */
export const SELECTION_STROKE_WIDTH = 3;

// ─── Props ────────────────────────────────────────────────────────────────────

export interface BBoxItem extends RectOverlayItem {
  /** 0-based flat index within the layer's array (used as React key). */
  id: string;
  bbox: BBox;
  selected?: boolean;
  /**
   * When true, this individual item is rendered at MISMATCH_DIM_OPACITY (0.2)
   * to visually de-emphasise it. Takes priority over the layer-level `dimmed`
   * prop. Used by the Mismatches-only overlay filter (Issue #295).
   */
  dimmed?: boolean;
}

interface BBoxOverlayProps {
  /** Which overlay layer to render. */
  layer: LayerName;
  /** Bounding boxes in display-pixel coordinates. */
  items: BBoxItem[];
  /** Whether this layer is currently visible. */
  visible?: boolean;
  /**
   * When true, renders at reduced opacity (0.3) to indicate this layer is
   * not the active Rail target. Used by PageImageCanvas (Slice 13).
   */
  dimmed?: boolean;
}

/**
 * BBoxOverlay — renders one Konva <Rect> per bounding-box item.
 *
 * Must be mounted inside a parent <Layer>; the component itself returns a
 * fragment of <Rect> nodes plus the dev/test sidecar div used by the driver
 * contract.
 *
 * Wrapped in `React.memo` (spec §11 perf pinning) so parent re-renders that
 * keep the same `items` reference skip the entire bbox map. Callers MUST
 * provide a memoised `items` array (e.g. via `useMemo`) for the memo to
 * actually catch — passing a freshly-built `[...]` literal each render
 * defeats the shallow-equal default.
 */
/** Opacity applied to each Rect when the layer is dimmed (inactive target). */
const DIMMED_OPACITY = 0.3;

/**
 * Opacity applied to a per-item dimmed Rect (Mismatches-only filter, Issue #295).
 * Distinct from DIMMED_OPACITY (layer-level) so the two concepts compose:
 * a mismatch-filter-dimmed item at 0.2 is clearly de-emphasised vs 0.3.
 */
export const MISMATCH_DIM_OPACITY = 0.2;

/**
 * Derive a LayerColorSpec from a LayerColors object for a given LayerName.
 *
 * Pure function (no hook call) — called inside BBoxOverlayInner after the
 * hook result is available. Keeps the hook call unconditional.
 */
function resolveLayerColorSpec(
  layer: LayerName,
  layerColors: ReturnType<typeof useLayerColors>,
): LayerColorSpec {
  switch (layer) {
    case "blocks":
      return hexToLayerColorSpec(layerColors.block);
    case "paragraphs":
      return hexToLayerColorSpec(layerColors.para);
    case "lines":
      return hexToLayerColorSpec(layerColors.line);
    case "words":
      return hexToLayerColorSpec(layerColors.word);
    case "regions-confirmed":
    case "regions-proposed":
    case "regions-selected":
      // No theme token exists yet for region layers (Task 7); use the
      // static LAYER_COLORS constants directly, same as drag-rect/selection.
      return LAYER_COLORS[layer];
    case "drag-rect":
      // Gap 26: use --accent token instead of hardcoded blue.
      return buildDragRectLayerSpec();
    case "selection-paragraphs":
    case "selection-lines":
    case "selection-words":
      // Gap 25: use --accent token instead of hardcoded blue.
      return buildSelectionLayerSpec();
  }
}

function BBoxOverlayInner({ layer, items, visible = true, dimmed = false }: BBoxOverlayProps) {
  // Call useLayerColors unconditionally (hooks rules). The result is used only
  // when visible=true, but the call must happen regardless of the early-return.
  const layerColors = useLayerColors();

  if (!visible) return null;

  // Resolve theme-aware colors: CSS vars for paragraphs/lines/words; hardcoded
  // for drag-rect and selection layers (no CSS token exists for these).
  const colors = resolveLayerColorSpec(layer, layerColors);

  return (
    <RectOverlayLayer
      layer={layer}
      items={items}
      colors={colors}
      visible={visible}
      dimmed={dimmed}
      selectionStrokeWidth={SELECTION_STROKE_WIDTH}
      layerDimmedOpacity={DIMMED_OPACITY}
      itemDimmedOpacity={MISMATCH_DIM_OPACITY}
    />
  );
}

/**
 * Memoised public export. React.memo's default shallow-equal compares
 * each prop by reference — so a stable `items` array (parent's `useMemo`)
 * skips the bbox map entirely on parent re-renders. Spec §11.
 */
export const BBoxOverlay = memo(BBoxOverlayInner);
BBoxOverlay.displayName = "BBoxOverlay";

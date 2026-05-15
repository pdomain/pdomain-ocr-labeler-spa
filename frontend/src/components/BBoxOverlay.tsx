// BBoxOverlay.tsx — Konva bounding-box overlay (spec-21-A3, #298).
//
// Spec: specs/21-konva-renderer.md §6 (overlay rendering), §12 (testids).
// Issues: #196 (LAYER_COLORS RGBA constants), #298 (Konva-rect rewrite).
//
// Renders one react-konva <Rect> per item inside whatever <Layer> the caller
// has provided. Colours come from LAYER_COLORS[layer]; selected items use
// SELECTION_STROKE_WIDTH (3 px). perfectDrawEnabled=false and listening=false
// per spec §11 perf pinning (overlay rects never participate in hit-testing).
//
// A dev/test-only sidecar <div data-testid="bbox-overlay-${layer}"
// data-layer data-item-count> is rendered alongside the fragment so the
// driver-contract Playwright tests can read the per-layer item count
// without poking into Konva nodes (spec §6, §12). Production bundles drop
// the sidecar entirely via the `import.meta.env.MODE !== "production"` gate.
//
// Legacy-exact RGBA values from
// pd-ocr-labeler/pd_ocr_labeler/views/projects/pages/image_tabs.py:280-285,500-535.
// Selection RGBA from image_tabs.py:514-519 (fill rgba(37,99,235,0.20),
// stroke #1d4ed8). The legacy renders selection strokes at width 1; spec
// §6/§8 bumps to 3 px via the `selected` branch on BBoxItem.

import { memo } from "react";
import { Rect } from "react-konva";
import type { BBox } from "../lib/coords";

/** Layer name type. */
export type LayerName =
  | "paragraphs"
  | "lines"
  | "words"
  | "drag-rect"
  | "selection-paragraphs"
  | "selection-lines"
  | "selection-words";

/** Fill + stroke RGBA string pair per layer. */
export interface LayerColorSpec {
  fill: string;
  stroke: string;
  /** Stroke width in display pixels (default 1). */
  strokeWidth: number;
}

/**
 * Legacy-exact layer colors.
 * Source: image_tabs.py:280-285,500-535.
 */
export const LAYER_COLORS: Record<LayerName, LayerColorSpec> = {
  paragraphs: {
    fill: "rgba(34,197,94,0.20)",
    stroke: "rgba(22,163,74,0.65)",
    strokeWidth: 1,
  },
  lines: {
    fill: "rgba(236,72,153,0.20)",
    stroke: "rgba(190,24,93,0.65)",
    strokeWidth: 1,
  },
  words: {
    fill: "rgba(59,130,246,0.18)",
    stroke: "rgba(29,78,216,0.65)",
    strokeWidth: 1,
  },
  "drag-rect": {
    fill: "transparent",
    stroke: "#2563eb",
    strokeWidth: 2,
  },
  // Selection layers share legacy fill/stroke (image_tabs.py:514-519);
  // selection items carry `selected: true` so BBoxOverlay's selected
  // branch upgrades strokeWidth to SELECTION_STROKE_WIDTH (spec §6, §8).
  "selection-paragraphs": {
    fill: "rgba(37,99,235,0.20)",
    stroke: "#1d4ed8",
    strokeWidth: 1,
  },
  "selection-lines": {
    fill: "rgba(37,99,235,0.20)",
    stroke: "#1d4ed8",
    strokeWidth: 1,
  },
  "selection-words": {
    fill: "rgba(37,99,235,0.20)",
    stroke: "#1d4ed8",
    strokeWidth: 1,
  },
};

/** Selection stroke width: 3 px (spec §6, §8). */
export const SELECTION_STROKE_WIDTH = 3;

// ─── Props ────────────────────────────────────────────────────────────────────

export interface BBoxItem {
  /** 0-based flat index within the layer's array (used as React key). */
  id: string;
  bbox: BBox;
  selected?: boolean;
}

interface BBoxOverlayProps {
  /** Which overlay layer to render. */
  layer: LayerName;
  /** Bounding boxes in display-pixel coordinates. */
  items: BBoxItem[];
  /** Whether this layer is currently visible. */
  visible?: boolean;
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
function BBoxOverlayInner({ layer, items, visible = true }: BBoxOverlayProps) {
  if (!visible) return null;
  const colors = LAYER_COLORS[layer];
  // Vite injects `import.meta.env.MODE` at build time. The frontend tsconfig
  // doesn't pull in vite/client typings (which would polute every file with
  // an `env` global), so we read it through a local narrow cast.
  const mode = (import.meta as unknown as { env?: { MODE?: string } }).env?.MODE;
  const isDevOrTest = mode !== "production";

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
          listening={false}
          perfectDrawEnabled={false}
        />
      ))}
      {isDevOrTest && (
        <div
          data-testid={`bbox-overlay-${layer}`}
          data-layer={layer}
          data-item-count={items.length}
          style={{ position: "absolute", visibility: "hidden", pointerEvents: "none" }}
          aria-hidden="true"
        />
      )}
    </>
  );
}

/**
 * Memoised public export. React.memo's default shallow-equal compares
 * each prop by reference — so a stable `items` array (parent's `useMemo`)
 * skips the bbox map entirely on parent re-renders. Spec §11.
 */
export const BBoxOverlay = memo(BBoxOverlayInner);
BBoxOverlay.displayName = "BBoxOverlay";

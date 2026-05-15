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

import { Rect } from "react-konva";
import type { BBox } from "../lib/coords";

/** Layer name type. */
export type LayerName = "paragraphs" | "lines" | "words" | "drag-rect";

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
 */
export function BBoxOverlay({ layer, items, visible = true }: BBoxOverlayProps) {
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

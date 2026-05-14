// BBoxOverlay.tsx — Konva layer for bounding-box overlays.
// Spec: docs/specs/2026-05-12-image-viewport-design.md §Layer colors
// Issue #196
//
// Legacy-exact RGBA color values from pd-ocr-labeler/pd_ocr_labeler/views/
// projects/pages/image_tabs.py:280-285,500-535.
// mix-blend-mode: multiply on Konva Layer so the underlying image shows through.
//
// LAYER_COLORS is exported for Vitest snapshot tests.

import type { BBox } from "../lib/coords";

/** Layer name type. */
export type LayerName = "paragraphs" | "lines" | "words" | "drag-rect";

/** Fill + stroke RGBA string pair per layer. */
export interface LayerColorSpec {
  fill: string;
  stroke: string;
  /** Stroke width in display pixels (default 1). */
  strokeWidth?: number;
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

/** Selection stroke multiplier: 3px at 0.70 alpha of border color. */
export const SELECTION_STROKE_WIDTH = 3;

// ─── Props ────────────────────────────────────────────────────────────────────

export interface BBoxItem {
  /** 0-based flat index within the layer's array. */
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
 * BBoxOverlay — renders bounding boxes for one layer.
 *
 * In the full Konva implementation this will be a `<Layer>` wrapping
 * `<Rect>` elements with `globalCompositeOperation="multiply"`.
 * For the M4 research spike (D-020) this stub renders a hidden div that
 * carries the correct data attributes so tests can verify the color constants
 * and component interface without a full Konva canvas.
 *
 * Replace the stub body with `<Layer globalCompositeOperation="multiply">…`
 * when Konva is wired up at M4.
 */
export function BBoxOverlay({ layer, items, visible = true }: BBoxOverlayProps) {
  const colors = LAYER_COLORS[layer];

  // Stub: render nothing when hidden, data-div when visible (for tests/debug).
  if (!visible) return null;

  return (
    <div
      data-testid={`bbox-overlay-${layer}`}
      data-layer={layer}
      data-fill={colors.fill}
      data-stroke={colors.stroke}
      data-item-count={items.length}
      style={{ display: "none" }}
      aria-hidden="true"
    />
  );
}

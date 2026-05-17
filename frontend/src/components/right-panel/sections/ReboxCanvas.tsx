// ReboxCanvas.tsx — Konva mini-canvas for inline word-bbox editing (P3.b, Gap 35).
// Spec: docs/plans/hifi-gaps-plan.md slice P3.b.
//
// Renders a fixed ~240×120 px Konva Stage that shows the word image cropped
// from the page with an interactive bbox overlay. Users drag the 8 handles
// (4 corners + 4 midpoints) to reposition the word boundary, or — in "draw"
// mode — click-drag to define a brand-new bbox from scratch. "pan" mode
// shifts the on-stage view without committing changes. "snap" mode behaves
// like ordinary handle-drag for now (snap-to-ink is wired by a future
// slice that injects an image-luminance probe).
//
// Coordinate spaces:
//   - bbox is reported in *image-pixel* coordinates (matches WordMatch.bbox).
//   - The Stage shows a scaled-to-fit view; the parent ReboxSection owns
//     the canonical bbox state and feeds it back via the `bbox` prop.
//
// Tool modes are purely interaction modes; the bbox shape is the same
// regardless of mode.
//
// data-testids:
//   rebox-canvas        — outer Konva Stage (the mock turns it into a div)
//   rebox-handle-{pos}  — the 8 drag handles (nw|n|ne|e|se|s|sw|w)
//   rebox-bbox          — the bbox <Rect> overlay

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Layer, Rect, Stage } from "react-konva";
import type Konva from "konva";
import type { components } from "../../../api/types";
import { readCssToken, hexToRgba } from "../../../hooks/useLayerColors";

type BBox = components["schemas"]["BBox"];

export type ReboxTool = "snap" | "draw" | "pan";

export interface ReboxCanvasProps {
  /** Original bbox (image-pixel coords). The canvas mirrors this on reset. */
  originalBbox: BBox;
  /** Current bbox (image-pixel coords). The canvas renders this as the overlay. */
  bbox: BBox;
  /** Called when the user finishes a drag / draw / handle move. */
  onChange: (next: BBox) => void;
  /** Current tool mode (controls how mouse events on empty canvas behave). */
  tool: ReboxTool;
  /** Integer zoom factor (1×–5×). Applied as a Stage scale. */
  zoom: number;
  /** Optional URL for the cropped word image. Falls back to a neutral fill. */
  imageUrl?: string | undefined;
}

/** Width/height of the Konva Stage in CSS pixels (before zoom). */
const CANVAS_WIDTH = 240;
const CANVAS_HEIGHT = 120;
/** Side length (px) of each drag handle. */
const HANDLE_SIZE = 8;

function buildCanvasColors() {
  const accent = readCssToken("--accent", "#d6925a");
  const bgSunk = readCssToken("--bg-sunk", "#08080c");
  const ink1 = readCssToken("--ink-1", "#f0f0f2");
  const ocr = readCssToken("--status-ocr", "#5d9fdf");
  return {
    bboxStroke: accent,
    bboxFill: hexToRgba(accent, 0.12),
    handleFill: bgSunk,
    handleStroke: ink1,
    ghostFill: hexToRgba(ocr, 0.15),
    ghostStroke: hexToRgba(ocr, 0.5),
  };
}

type HandlePos = "nw" | "n" | "ne" | "e" | "se" | "s" | "sw" | "w";

interface HandleDef {
  pos: HandlePos;
  /** Compute (x,y) of the handle centre from a bbox, both in image coords. */
  centre: (b: BBox) => { x: number; y: number };
  /** Compute the next bbox when this handle is dragged to (x,y) in image coords. */
  apply: (b: BBox, x: number, y: number) => BBox;
}

const HANDLES: HandleDef[] = [
  {
    pos: "nw",
    centre: (b) => ({ x: b.x, y: b.y }),
    apply: (b, x, y) => ({
      x,
      y,
      width: b.x + b.width - x,
      height: b.y + b.height - y,
    }),
  },
  {
    pos: "n",
    centre: (b) => ({ x: b.x + b.width / 2, y: b.y }),
    apply: (b, _x, y) => ({ x: b.x, y, width: b.width, height: b.y + b.height - y }),
  },
  {
    pos: "ne",
    centre: (b) => ({ x: b.x + b.width, y: b.y }),
    apply: (b, x, y) => ({ x: b.x, y, width: x - b.x, height: b.y + b.height - y }),
  },
  {
    pos: "e",
    centre: (b) => ({ x: b.x + b.width, y: b.y + b.height / 2 }),
    apply: (b, x, _y) => ({ x: b.x, y: b.y, width: x - b.x, height: b.height }),
  },
  {
    pos: "se",
    centre: (b) => ({ x: b.x + b.width, y: b.y + b.height }),
    apply: (b, x, y) => ({ x: b.x, y: b.y, width: x - b.x, height: y - b.y }),
  },
  {
    pos: "s",
    centre: (b) => ({ x: b.x + b.width / 2, y: b.y + b.height }),
    apply: (b, _x, y) => ({ x: b.x, y: b.y, width: b.width, height: y - b.y }),
  },
  {
    pos: "sw",
    centre: (b) => ({ x: b.x, y: b.y + b.height }),
    apply: (b, x, y) => ({ x, y: b.y, width: b.x + b.width - x, height: y - b.y }),
  },
  {
    pos: "w",
    centre: (b) => ({ x: b.x, y: b.y + b.height / 2 }),
    apply: (b, x, _y) => ({ x, y: b.y, width: b.x + b.width - x, height: b.height }),
  },
];

/** Normalize bbox so width/height are positive (and bbox.x/y remains top-left). */
function normalize(b: BBox): BBox {
  let { x, y, width, height } = b;
  if (width < 0) {
    x += width;
    width = -width;
  }
  if (height < 0) {
    y += height;
    height = -height;
  }
  return { x, y, width: Math.max(1, width), height: Math.max(1, height) };
}

export function ReboxCanvas({
  originalBbox,
  bbox,
  onChange,
  tool,
  zoom,
  imageUrl,
}: ReboxCanvasProps) {
  const canvasColors = buildCanvasColors();

  // Fit the *original* bbox into the canvas. We size around the original so
  // the visible scale doesn't change as the user drags the bbox around.
  const fit = useMemo(() => {
    // Add a generous margin around the original bbox so drag handles aren't
    // pinned to the edge.
    const margin = Math.max(20, Math.round(originalBbox.width * 0.4));
    const viewW = originalBbox.width + 2 * margin;
    const viewH = originalBbox.height + 2 * margin;
    const scale = Math.min(CANVAS_WIDTH / viewW, CANVAS_HEIGHT / viewH);
    const originX = originalBbox.x - margin;
    const originY = originalBbox.y - margin;
    return { scale, originX, originY };
  }, [originalBbox]);

  /** Image-coords → canvas-coords (with zoom and view fit). */
  const toCanvas = useCallback(
    (px: number, py: number): { x: number; y: number } => ({
      x: (px - fit.originX) * fit.scale * zoom,
      y: (py - fit.originY) * fit.scale * zoom,
    }),
    [fit, zoom],
  );

  /** Canvas-coords → image-coords. */
  const toImage = useCallback(
    (cx: number, cy: number): { x: number; y: number } => ({
      x: cx / (fit.scale * zoom) + fit.originX,
      y: cy / (fit.scale * zoom) + fit.originY,
    }),
    [fit, zoom],
  );

  // Draw-mode state — track an in-progress freshly-drawn bbox.
  const [drawing, setDrawing] = useState<BBox | null>(null);
  const dragStartRef = useRef<{ x: number; y: number } | null>(null);

  // Reset drawing if user switches away from draw mode.
  useEffect(() => {
    if (tool !== "draw") {
      setDrawing(null);
      dragStartRef.current = null;
    }
  }, [tool]);

  // ── Pointer helpers ─────────────────────────────────────────────────────
  const pointerImage = useCallback(
    (e: Konva.KonvaEventObject<MouseEvent>): { x: number; y: number } | null => {
      const stage = e.target.getStage?.();
      if (!stage) return null;
      const pos = stage.getPointerPosition();
      if (!pos) return null;
      return toImage(pos.x, pos.y);
    },
    [toImage],
  );

  const handleStageMouseDown = useCallback(
    (e: Konva.KonvaEventObject<MouseEvent>) => {
      if (tool !== "draw") return;
      const img = pointerImage(e);
      if (!img) return;
      dragStartRef.current = img;
      setDrawing({ x: img.x, y: img.y, width: 0, height: 0 });
    },
    [tool, pointerImage],
  );

  const handleStageMouseMove = useCallback(
    (e: Konva.KonvaEventObject<MouseEvent>) => {
      if (tool !== "draw" || !dragStartRef.current) return;
      const img = pointerImage(e);
      if (!img) return;
      const start = dragStartRef.current;
      setDrawing(
        normalize({
          x: start.x,
          y: start.y,
          width: img.x - start.x,
          height: img.y - start.y,
        }),
      );
    },
    [tool, pointerImage],
  );

  const handleStageMouseUp = useCallback(
    (_e: Konva.KonvaEventObject<MouseEvent>) => {
      if (tool !== "draw" || !drawing || !dragStartRef.current) return;
      const finalised = normalize(drawing);
      dragStartRef.current = null;
      setDrawing(null);
      onChange(finalised);
    },
    [tool, drawing, onChange],
  );

  // ── Handle-drag wiring (corner + midpoint) ──────────────────────────────
  const handleHandleDragMove = useCallback(
    (pos: HandlePos) => (e: Konva.KonvaEventObject<DragEvent>) => {
      const stage = e.target.getStage?.();
      if (!stage) return;
      const ptr = stage.getPointerPosition();
      if (!ptr) return;
      const img = toImage(ptr.x, ptr.y);
      const def = HANDLES.find((h) => h.pos === pos);
      if (!def) return;
      const next = normalize(def.apply(bbox, img.x, img.y));
      onChange(next);
    },
    [bbox, onChange, toImage],
  );

  // ── Ghost bbox — shown when draft differs from original ──────────────────
  const showGhost =
    bbox.x !== originalBbox.x ||
    bbox.y !== originalBbox.y ||
    bbox.width !== originalBbox.width ||
    bbox.height !== originalBbox.height;
  const ghostTL = toCanvas(originalBbox.x, originalBbox.y);
  const ghostBR = toCanvas(
    originalBbox.x + originalBbox.width,
    originalBbox.y + originalBbox.height,
  );

  // ── Render ──────────────────────────────────────────────────────────────
  const renderBbox = drawing ?? bbox;
  const tl = toCanvas(renderBbox.x, renderBbox.y);
  const br = toCanvas(renderBbox.x + renderBbox.width, renderBbox.y + renderBbox.height);
  const overlayX = Math.min(tl.x, br.x);
  const overlayY = Math.min(tl.y, br.y);
  const overlayW = Math.abs(br.x - tl.x);
  const overlayH = Math.abs(br.y - tl.y);

  return (
    <div
      className="rounded border border-border-2 overflow-hidden bg-sunk"
      style={{
        cursor: tool === "draw" ? "crosshair" : tool === "pan" ? "grab" : "default",
      }}
    >
      <Stage
        width={CANVAS_WIDTH}
        height={CANVAS_HEIGHT}
        data-testid="rebox-canvas"
        onMouseDown={handleStageMouseDown}
        onMouseMove={handleStageMouseMove}
        onMouseUp={handleStageMouseUp}
      >
        <Layer>
          {/* Background — image when provided, else neutral fill. */}
          <Rect
            x={0}
            y={0}
            width={CANVAS_WIDTH}
            height={CANVAS_HEIGHT}
            {...(!imageUrl ? { fill: readCssToken("--bg-raised", "#1d1d24") } : {})}
            data-testid="rebox-canvas-background"
          />
        </Layer>
        <Layer>
          {/* Ghost bbox — original position shown faintly when draft differs. */}
          {showGhost && (
            <Rect
              data-testid="rebox-ghost"
              x={ghostTL.x}
              y={ghostTL.y}
              width={Math.abs(ghostBR.x - ghostTL.x)}
              height={Math.abs(ghostBR.y - ghostTL.y)}
              fill={canvasColors.ghostFill}
              stroke={canvasColors.ghostStroke}
              strokeWidth={1}
              dash={[4, 3]}
              listening={false}
            />
          )}
        </Layer>
        <Layer>
          {/* Active bbox overlay. */}
          <Rect
            data-testid="rebox-bbox"
            x={overlayX}
            y={overlayY}
            width={overlayW}
            height={overlayH}
            stroke={canvasColors.bboxStroke}
            strokeWidth={1.5}
            fill={canvasColors.bboxFill}
            {...(drawing ? { dash: [4, 2] } : {})}
          />
          {/* Drag handles — only in snap mode and not mid-draw. */}
          {tool === "snap" &&
            !drawing &&
            HANDLES.map((h) => {
              const c = h.centre(bbox);
              const can = toCanvas(c.x, c.y);
              return (
                <Rect
                  key={h.pos}
                  data-testid={`rebox-handle-${h.pos}`}
                  x={can.x - HANDLE_SIZE / 2}
                  y={can.y - HANDLE_SIZE / 2}
                  width={HANDLE_SIZE}
                  height={HANDLE_SIZE}
                  fill={canvasColors.handleFill}
                  stroke={canvasColors.handleStroke}
                  strokeWidth={1}
                  draggable
                  onDragMove={handleHandleDragMove(h.pos)}
                />
              );
            })}
        </Layer>
      </Stage>
    </div>
  );
}

export type { BBox };

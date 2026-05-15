// EraseCanvas.tsx — Konva-backed erase-pixels canvas overlay for P3.c.
// Spec: docs/plans/hifi-gaps-plan.md Slice P3.c (Gap 36).
//
// Owns:
//   - Three-mode tool switcher (brush / lasso / rect) as a segmented control
//   - Brush size slider (only visible in brush mode)
//   - Konva Stage with the word image (or placeholder) + a red semi-transparent
//     overlay layer drawing each committed op
//
// Op model — every interaction produces an `EraseOp` discriminated by `tool`:
//   - brush: a single dab at (x, y) with radius r
//   - lasso: a closed polygon (points: number[][])  // [[x,y], [x,y], ...]
//   - rect:  axis-aligned (x, y, width, height)
//
// data-testids (driver contract for P3.c):
//   erase-canvas              — the Konva Stage root
//   erase-tool-brush          — brush tool toggle
//   erase-tool-lasso          — lasso tool toggle
//   erase-tool-rect           — rect tool toggle
//   erase-brush-size          — brush radius slider (visible in brush mode)
//   erase-overlay-op-{N}      — each committed op rendered on the overlay
//
// NOTE: this component is a *visual* canvas — the ops list display + clear/apply
// footer lives in the parent ErasePixelsSection.

import { useCallback, useRef, useState } from "react";
import { Layer, Rect, Stage } from "react-konva";
import type Konva from "konva";

// ───────────────────────────────────────────────────────────────────────────
// Types
// ───────────────────────────────────────────────────────────────────────────

export type EraseTool = "brush" | "lasso" | "rect";

export interface BrushOp {
  tool: "brush";
  x: number;
  y: number;
  radius: number;
}

export interface LassoOp {
  tool: "lasso";
  points: Array<[number, number]>;
}

export interface RectOp {
  tool: "rect";
  x: number;
  y: number;
  width: number;
  height: number;
}

export type EraseOp = BrushOp | LassoOp | RectOp;

export interface EraseCanvasProps {
  /** URL of the word image slice (optional — placeholder shown when absent). */
  imageUrl?: string;
  /** Current tool selection (controlled by parent). */
  tool: EraseTool;
  /** Called when the user picks a different tool. */
  onToolChange: (next: EraseTool) => void;
  /** Brush radius for the brush tool (controlled by parent). */
  brushSize: number;
  /** Called when the brush size slider moves. */
  onBrushSizeChange: (next: number) => void;
  /** Committed ops, rendered as red overlays. */
  ops: EraseOp[];
  /** Called when an op completes (mouse-up / rect drag-end). */
  onOpCommit: (op: EraseOp) => void;
  /** Stage width in CSS pixels (defaults to 200). */
  width?: number;
  /** Stage height in CSS pixels (defaults to 80). */
  height?: number;
}

// ───────────────────────────────────────────────────────────────────────────
// Constants
// ───────────────────────────────────────────────────────────────────────────

const DEFAULT_WIDTH = 200;
const DEFAULT_HEIGHT = 80;
const ERASE_FILL = "rgba(220,38,38,0.35)"; // red semi-transparent
const ERASE_STROKE = "#dc2626";
const MIN_BRUSH = 2;
const MAX_BRUSH = 32;

// ───────────────────────────────────────────────────────────────────────────
// Component
// ───────────────────────────────────────────────────────────────────────────

interface RectDragState {
  startX: number;
  startY: number;
  current: { x: number; y: number; width: number; height: number };
}

interface LassoDragState {
  points: Array<[number, number]>;
}

export function EraseCanvas({
  imageUrl,
  tool,
  onToolChange,
  brushSize,
  onBrushSizeChange,
  ops,
  onOpCommit,
  width = DEFAULT_WIDTH,
  height = DEFAULT_HEIGHT,
}: EraseCanvasProps) {
  const stageRef = useRef<Konva.Stage>(null);
  const [rectDrag, setRectDrag] = useState<RectDragState | null>(null);
  const [lassoDrag, setLassoDrag] = useState<LassoDragState | null>(null);

  // Extract pointer position from a Konva event. Returns null if unavailable.
  const pointerPos = useCallback((e: Konva.KonvaEventObject<MouseEvent>) => {
    const stage = e.target.getStage();
    if (!stage) return null;
    return stage.getPointerPosition();
  }, []);

  const handleMouseDown = useCallback(
    (e: Konva.KonvaEventObject<MouseEvent>) => {
      const pos = pointerPos(e);
      if (!pos) return;
      if (tool === "rect") {
        setRectDrag({
          startX: pos.x,
          startY: pos.y,
          current: { x: pos.x, y: pos.y, width: 0, height: 0 },
        });
      } else if (tool === "lasso") {
        setLassoDrag({ points: [[pos.x, pos.y]] });
      }
    },
    [tool, pointerPos],
  );

  const handleMouseMove = useCallback(
    (e: Konva.KonvaEventObject<MouseEvent>) => {
      const pos = pointerPos(e);
      if (!pos) return;
      if (tool === "rect" && rectDrag) {
        const x = Math.min(pos.x, rectDrag.startX);
        const y = Math.min(pos.y, rectDrag.startY);
        const w = Math.abs(pos.x - rectDrag.startX);
        const h = Math.abs(pos.y - rectDrag.startY);
        setRectDrag({ ...rectDrag, current: { x, y, width: w, height: h } });
      } else if (tool === "lasso" && lassoDrag) {
        setLassoDrag({ points: [...lassoDrag.points, [pos.x, pos.y]] });
      }
    },
    [tool, rectDrag, lassoDrag, pointerPos],
  );

  const handleMouseUp = useCallback(
    (e: Konva.KonvaEventObject<MouseEvent>) => {
      const pos = pointerPos(e);
      if (!pos) return;
      if (tool === "brush") {
        // Single click = one brush dab.
        onOpCommit({ tool: "brush", x: pos.x, y: pos.y, radius: brushSize });
        return;
      }
      if (tool === "rect" && rectDrag) {
        const { current } = rectDrag;
        if (current.width > 1 && current.height > 1) {
          onOpCommit({ tool: "rect", ...current });
        }
        setRectDrag(null);
        return;
      }
      if (tool === "lasso" && lassoDrag) {
        if (lassoDrag.points.length >= 3) {
          onOpCommit({ tool: "lasso", points: lassoDrag.points });
        }
        setLassoDrag(null);
        return;
      }
    },
    [tool, brushSize, rectDrag, lassoDrag, onOpCommit, pointerPos],
  );

  const handleMouseLeave = useCallback(() => {
    // Cancel an in-progress drag if the cursor leaves the stage.
    setRectDrag(null);
    setLassoDrag(null);
  }, []);

  // ─── Render ──────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-col gap-2">
      {/* Tool switcher (segmented control) */}
      <div role="radiogroup" aria-label="Erase tool" className="flex gap-1">
        {(["brush", "lasso", "rect"] as const).map((t) => (
          <button
            key={t}
            data-testid={`erase-tool-${t}`}
            role="radio"
            aria-checked={tool === t}
            onClick={() => onToolChange(t)}
            className={[
              "flex-1 h-6 px-2 text-[11px] rounded-md border transition-colors capitalize",
              tool === t
                ? "bg-accent text-accent-ink border-accent"
                : "bg-raised text-ink-2 border-border-2 hover:bg-sunk",
            ].join(" ")}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Brush size slider — only in brush mode */}
      {tool === "brush" && (
        <label className="flex items-center gap-2 text-[11px] text-ink-2">
          <span>Size</span>
          <input
            data-testid="erase-brush-size"
            type="range"
            min={MIN_BRUSH}
            max={MAX_BRUSH}
            value={brushSize}
            onChange={(e) => onBrushSizeChange(Number(e.target.value))}
            className="flex-1 accent-accent"
          />
          <span className="w-6 text-right tabular-nums">{brushSize}px</span>
        </label>
      )}

      {/* Konva stage */}
      <div
        className="border border-border-2 rounded overflow-hidden bg-sunk"
        style={{ width, cursor: "crosshair" }}
      >
        <Stage
          ref={stageRef}
          width={width}
          height={height}
          data-testid="erase-canvas"
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseLeave}
        >
          <Layer>
            {/* Background: image or placeholder rect (Konva-mock tests render this as a stub). */}
            <Rect
              x={0}
              y={0}
              width={width}
              height={height}
              fill={imageUrl ? undefined : "#1f2937"}
            />
          </Layer>

          {/* Committed op overlays */}
          <Layer>
            {ops.map((op, i) => renderOpRect(op, i))}

            {/* Pending rect drag preview */}
            {rectDrag && (
              <Rect
                x={rectDrag.current.x}
                y={rectDrag.current.y}
                width={rectDrag.current.width}
                height={rectDrag.current.height}
                fill={ERASE_FILL}
                stroke={ERASE_STROKE}
                strokeWidth={1}
                dash={[4, 2]}
              />
            )}
          </Layer>
        </Stage>
      </div>
    </div>
  );
}

/**
 * Render one committed op as a Konva.Rect (approximation — lasso renders as
 * its bounding-box for now; the polygon outline is purely visual feedback).
 */
function renderOpRect(op: EraseOp, index: number) {
  if (op.tool === "brush") {
    const r = op.radius;
    return (
      <Rect
        key={index}
        data-testid={`erase-overlay-op-${index}`}
        x={op.x - r}
        y={op.y - r}
        width={r * 2}
        height={r * 2}
        cornerRadius={r}
        fill={ERASE_FILL}
        stroke={ERASE_STROKE}
        strokeWidth={1}
      />
    );
  }
  if (op.tool === "rect") {
    return (
      <Rect
        key={index}
        data-testid={`erase-overlay-op-${index}`}
        x={op.x}
        y={op.y}
        width={op.width}
        height={op.height}
        fill={ERASE_FILL}
        stroke={ERASE_STROKE}
        strokeWidth={1}
      />
    );
  }
  // Lasso — bounding-box approximation.
  const xs = op.points.map((p) => p[0]);
  const ys = op.points.map((p) => p[1]);
  const minX = Math.min(...xs);
  const minY = Math.min(...ys);
  const maxX = Math.max(...xs);
  const maxY = Math.max(...ys);
  return (
    <Rect
      key={index}
      data-testid={`erase-overlay-op-${index}`}
      x={minX}
      y={minY}
      width={maxX - minX}
      height={maxY - minY}
      fill={ERASE_FILL}
      stroke={ERASE_STROKE}
      strokeWidth={1}
      dash={[2, 2]}
    />
  );
}

/** Human-readable summary for the ops list display. */
export function describeOp(op: EraseOp, index: number): string {
  if (op.tool === "brush") {
    return `Op ${index + 1}: brush at (${Math.round(op.x)},${Math.round(op.y)}) r=${op.radius}`;
  }
  if (op.tool === "rect") {
    return `Op ${index + 1}: rect at (${Math.round(op.x)},${Math.round(op.y)}) ${Math.round(op.width)}×${Math.round(op.height)}`;
  }
  return `Op ${index + 1}: lasso (${op.points.length} pts)`;
}

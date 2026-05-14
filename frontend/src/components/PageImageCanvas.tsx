// PageImageCanvas.tsx — image viewport with drag box-select (#197)
// Spec: docs/specs/2026-05-12-image-viewport-design.md
//
// Supports four interaction modes (via viewportStore):
//   select  — drag box-select; POST /api/.../selection on mouseup (#197)
//   rebox   — drag to set new bbox; POST .../rebox on mouseup (#198)
//   add-word — drag to add new word; POST .../words/add on mouseup (#198)
//   erase   — drag erase rect; POST .../erase-pixels on mouseup (#198)
//
// DragRect preview: data-testid="ocr-drag-rect" (driver-contract §2).
// Modifier keys on mousedown: plain = replace, Shift = remove, Ctrl = toggle.
//
// Konva Stage not wired in this stub — will be replaced by react-konva at M4
// after the D-020 research spike. Current implementation uses DOM events on a
// div for acceptance-test coverage.

import { useEffect, useRef, useState } from "react";
import { getStageDimensions, type EncodedDims } from "../lib/canvas-utils";
import type { BBox } from "../lib/coords";
import { setDragRect, clearSelection } from "../stores/selection-store";
import { viewportStore, type ViewportMode } from "../stores/viewport-store";

export type SelectionModifier = "replace" | "remove" | "toggle";

interface DragState {
  startX: number;
  startY: number;
}

interface PageImageCanvasProps {
  imageUrl: string;
  encoded: EncodedDims;
  /** Project ID for constructing selection POST URL. */
  projectId?: string;
  /** Page index (0-based) for constructing selection POST URL. */
  pageIndex?: number;
  /**
   * Called when a drag-select completes (mouseup).
   * Receives the drag rect in display pixels and the modifier.
   * Parent is responsible for resolving which items fall within the rect
   * and POSTing to the selection endpoint.
   */
  onBoxSelect?: (rect: BBox, modifier: SelectionModifier) => void;
}

/**
 * Image viewport canvas.
 *
 * Tracks mouse events to implement drag box-select in "select" mode.
 * The DragRect preview is rendered as an absolutely-positioned div
 * (testid: `ocr-drag-rect`) so Vitest can verify it without Konva.
 *
 * At M4 the DOM-event implementation will be replaced with react-konva
 * once the D-020 research spike confirms Konva.
 */
export default function PageImageCanvas({
  imageUrl: _imageUrl,
  encoded,
  onBoxSelect,
}: PageImageCanvasProps) {
  const stageRef = useRef<HTMLDivElement>(null);
  const dims = getStageDimensions(encoded);

  const [dragState, setDragState] = useState<DragState | null>(null);
  const [dragRect, setLocalDragRect] = useState<BBox | null>(null);
  const [mode, setMode] = useState<ViewportMode>(viewportStore.getState().mode);

  // Subscribe to viewport store mode changes
  useEffect(() => {
    const unsub = viewportStore.subscribe((s) => setMode(s.mode));
    return unsub;
  }, []);

  function getRelativePos(e: React.MouseEvent<HTMLDivElement>): {
    x: number;
    y: number;
  } {
    const rect = stageRef.current?.getBoundingClientRect();
    if (!rect) return { x: 0, y: 0 };
    return {
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
    };
  }

  function resolveModifier(e: React.MouseEvent): SelectionModifier {
    if (e.shiftKey) return "remove";
    if (e.ctrlKey || e.metaKey) return "toggle";
    return "replace";
  }

  function handleMouseDown(e: React.MouseEvent<HTMLDivElement>) {
    if (mode !== "select") return;
    const pos = getRelativePos(e);
    setDragState({ startX: pos.x, startY: pos.y });
    setLocalDragRect(null);
    // Prevent text selection during drag
    e.preventDefault();
  }

  function handleMouseMove(e: React.MouseEvent<HTMLDivElement>) {
    if (mode !== "select" || !dragState) return;
    const pos = getRelativePos(e);
    const rect: BBox = {
      x: Math.min(pos.x, dragState.startX),
      y: Math.min(pos.y, dragState.startY),
      width: Math.abs(pos.x - dragState.startX),
      height: Math.abs(pos.y - dragState.startY),
    };
    setLocalDragRect(rect);
    setDragRect(rect);
  }

  function handleMouseUp(e: React.MouseEvent<HTMLDivElement>) {
    if (mode !== "select" || !dragState) return;
    const pos = getRelativePos(e);
    const rect: BBox = {
      x: Math.min(pos.x, dragState.startX),
      y: Math.min(pos.y, dragState.startY),
      width: Math.abs(pos.x - dragState.startX),
      height: Math.abs(pos.y - dragState.startY),
    };
    const modifier = resolveModifier(e);

    // Clear drag state
    setDragState(null);
    setLocalDragRect(null);
    setDragRect(null);

    // Only fire if drag had non-trivial size (> 2px)
    if (rect.width > 2 || rect.height > 2) {
      onBoxSelect?.(rect, modifier);
    }
  }

  function handleMouseLeave() {
    if (dragState) {
      setDragState(null);
      setLocalDragRect(null);
      setDragRect(null);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Escape") {
      clearSelection();
      setDragState(null);
      setLocalDragRect(null);
      setDragRect(null);
    }
  }

  return (
    <div
      ref={stageRef}
      className="page-image-canvas relative select-none"
      style={{
        width: dims.width,
        height: dims.height,
        cursor: mode === "select" ? "crosshair" : "default",
      }}
      data-width={dims.width}
      data-height={dims.height}
      data-testid="image-viewport"
      data-mode={mode}
      role="img"
      aria-label="Page image viewport"
      tabIndex={0}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseLeave}
      onKeyDown={handleKeyDown}
    >
      {/* Drag-rect preview overlay */}
      {dragRect && (
        <div
          data-testid="ocr-drag-rect"
          className="ocr-drag-rect absolute pointer-events-none"
          style={{
            left: dragRect.x,
            top: dragRect.y,
            width: dragRect.width,
            height: dragRect.height,
            border: "2px dashed #2563eb",
            backgroundColor: "transparent",
          }}
        />
      )}
    </div>
  );
}

// PageImageCanvas.tsx — image viewport with four interaction modes (#197, #198, #297)
//
// Spec: specs/21-konva-renderer.md §4 (component layout), §12 (testids),
//       §13 (edge cases — empty state).
//
// spec-21-A2 (#297) replaces the DOM-stub viewport with a real react-konva
// <Stage> host carrying the 6-layer skeleton from spec §4:
//
//   image / overlay-paragraphs / overlay-lines / overlay-words / selection / drag
//
// Overlay layers stay empty in this slice; spec-21-A3 (#298) wires BBoxOverlay
// into them and spec-21-C migrates drag handlers from DOM events to Konva
// Stage events. Until then, drag input is captured by DOM mouse events on the
// wrapping viewport div — same callbacks, same `data-mode`, same modifiers.
//
// Interaction modes (via viewportStore):
//   select   — drag box-select; fires onBoxSelect(rect, modifier) (#197)
//   rebox    — drag to set new bbox; fires onRebox(rect) (#198)
//   add-word — drag to add new word; fires onAddWord(rect) (#198)
//   erase    — drag erase rect; fires onErasePixels(rect) (#198)
//
// Testid layout (spec §12):
//   image-viewport     — wrapper div around the Stage (also empty-state branch)
//   image-stage        — sidecar div mirroring Stage geometry (Konva nodes
//                        cannot themselves carry testids in jsdom or Playwright)
//   ocr-drag-rect      — drag-preview Rect (must be a DOM sidecar, NOT a Konva
//                        node — required for Playwright selector access)
//   bbox-overlay-*     — sidecars rendered by BBoxOverlay (spec-21-A3 #298),
//                        not by this component
//
// DragRect preview: data-testid="ocr-drag-rect", CSS class "ocr-drag-rect".
// Modifier keys on select mousedown: plain = replace, Shift = remove, Ctrl = toggle.
// Rebox + erase modes reset to "select" on successful drag; add-word stays active.

import { useEffect, useRef, useState } from "react";
import { Layer, Stage } from "react-konva";
import { getStageDimensions, type EncodedDims } from "../lib/canvas-utils";
import type { BBox } from "../lib/coords";
import { PageImage } from "./PageImage";
import { setDragRect, clearSelection } from "../stores/selection-store";
import { viewportStore, exitToSelectMode, type ViewportMode } from "../stores/viewport-store";

export type SelectionModifier = "replace" | "remove" | "toggle";

interface DragState {
  startX: number;
  startY: number;
}

interface PageImageCanvasProps {
  imageUrl: string;
  /**
   * Page encoding dims. `null` renders the empty-state viewport
   * (spec §13: `<div data-testid="image-viewport" data-state="empty">`).
   */
  encoded: EncodedDims | null;
  /** Project ID for constructing POST URLs. */
  projectId?: string;
  /** Page index (0-based) for constructing POST URLs. */
  pageIndex?: number;
  /**
   * Called when a drag-select completes in "select" mode.
   * Receives the drag rect in display pixels and the modifier.
   * Parent resolves which items fall within the rect and POSTs to the selection endpoint.
   */
  onBoxSelect?: (rect: BBox, modifier: SelectionModifier) => void;
  /**
   * Called when a rebox drag completes.
   * Receives the new bbox in display pixels.
   * Parent POSTs to .../words/{l}/{w}/rebox (with source-pixel conversion).
   * Mode resets to "select" after callback.
   */
  onRebox?: (rect: BBox) => void;
  /**
   * Called when an add-word drag completes.
   * Receives the new word bbox in display pixels.
   * Parent POSTs to .../words/add with {bbox, text: ""}.
   * Mode stays "add-word" for multi-add.
   */
  onAddWord?: (rect: BBox) => void;
  /**
   * Called when an erase-pixels drag completes.
   * Receives the erase rect in display pixels.
   * Parent POSTs to .../erase-pixels with {bbox, fill_value: 255}.
   * Mode resets to "select" after callback.
   */
  onErasePixels?: (rect: BBox) => void;
}

/** Cursor style per mode. */
const MODE_CURSORS: Record<ViewportMode, string> = {
  select: "crosshair",
  rebox: "cell",
  "add-word": "copy",
  erase: "not-allowed",
};

/** Drag-rect border color per mode. */
const MODE_RECT_COLORS: Record<ViewportMode, string> = {
  select: "#2563eb", // blue
  rebox: "#16a34a", // green
  "add-word": "#9333ea", // purple
  erase: "#dc2626", // red
};

/**
 * Image viewport canvas — Konva Stage host with four interaction modes.
 *
 * The wrapping div carries `data-testid="image-viewport"` and captures DOM
 * mouse events for drag interactions; the Konva `<Stage>` lives inside it
 * with `data-testid="image-stage"` for Playwright introspection. Drag
 * handlers will migrate to Konva Stage events in spec-21-C.
 */
export default function PageImageCanvas({
  imageUrl,
  encoded,
  onBoxSelect,
  onRebox,
  onAddWord,
  onErasePixels,
}: PageImageCanvasProps) {
  const stageRef = useRef<HTMLDivElement>(null);
  const [dragState, setDragState] = useState<DragState | null>(null);
  const [dragRect, setLocalDragRect] = useState<BBox | null>(null);
  const [mode, setMode] = useState<ViewportMode>(viewportStore.getState().mode);

  // Subscribe to viewport store mode changes
  useEffect(() => {
    const unsub = viewportStore.subscribe((s) => setMode(s.mode));
    return unsub;
  }, []);

  // ── Empty-state branch (spec §13) ──────────────────────────────────────────
  if (!encoded) {
    return (
      <div
        data-testid="image-viewport"
        data-state="empty"
        role="img"
        aria-label="Page image viewport (no page loaded)"
      />
    );
  }

  const dims = getStageDimensions(encoded);

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

  function computeRect(end: { x: number; y: number }): BBox {
    if (!dragState) return { x: 0, y: 0, width: 0, height: 0 };
    return {
      x: Math.min(end.x, dragState.startX),
      y: Math.min(end.y, dragState.startY),
      width: Math.abs(end.x - dragState.startX),
      height: Math.abs(end.y - dragState.startY),
    };
  }

  function clearDrag() {
    setDragState(null);
    setLocalDragRect(null);
    setDragRect(null);
  }

  function handleMouseDown(e: React.MouseEvent<HTMLDivElement>) {
    const pos = getRelativePos(e);
    setDragState({ startX: pos.x, startY: pos.y });
    setLocalDragRect(null);
    e.preventDefault(); // prevent text selection
  }

  function handleMouseMove(e: React.MouseEvent<HTMLDivElement>) {
    if (!dragState) return;
    const pos = getRelativePos(e);
    const rect = computeRect(pos);
    setLocalDragRect(rect);
    setDragRect(rect);
  }

  function handleMouseUp(e: React.MouseEvent<HTMLDivElement>) {
    if (!dragState) return;
    const pos = getRelativePos(e);
    const rect = computeRect(pos);
    const isTrivial = rect.width <= 2 && rect.height <= 2;
    clearDrag();

    if (isTrivial) return;

    switch (mode) {
      case "select": {
        const modifier = resolveModifier(e);
        onBoxSelect?.(rect, modifier);
        break;
      }
      case "rebox": {
        onRebox?.(rect);
        // Reset to select mode after rebox
        exitToSelectMode();
        break;
      }
      case "add-word": {
        onAddWord?.(rect);
        // Stay in add-word mode for multi-add (no reset)
        break;
      }
      case "erase": {
        onErasePixels?.(rect);
        // Reset to select mode after erase
        exitToSelectMode();
        break;
      }
    }
  }

  function handleMouseLeave() {
    if (dragState) {
      clearDrag();
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Escape") {
      clearSelection();
      clearDrag();
      // Return to select mode on Escape
      exitToSelectMode();
    }
  }

  return (
    <div
      ref={stageRef}
      className="page-image-canvas relative select-none"
      style={{
        width: dims.width,
        height: dims.height,
        cursor: MODE_CURSORS[mode],
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
      {/* Sidecar div mirroring Stage geometry (spec §12 — Konva nodes
          cannot themselves carry testids in jsdom or Playwright). */}
      <div
        data-testid="image-stage"
        data-width={dims.width}
        data-height={dims.height}
        aria-hidden="true"
        style={{
          position: "absolute",
          inset: 0,
          pointerEvents: "none",
          visibility: "hidden",
        }}
      />

      {/* Konva Stage + 6-layer skeleton from spec §4. Overlay layers
          stay empty in spec-21-A2; spec-21-A3 (#298) fills BBoxOverlay. */}
      <Stage width={dims.width} height={dims.height}>
        <Layer name="image">
          <PageImage url={imageUrl} width={dims.width} height={dims.height} />
        </Layer>
        <Layer name="overlay-paragraphs" listening={false} />
        <Layer name="overlay-lines" listening={false} />
        <Layer name="overlay-words" listening={false} />
        <Layer name="selection" listening={false} />
        <Layer name="drag" />
      </Stage>

      {/* Drag-rect preview overlay — DOM sidecar (spec §12).
          Must NOT be a Konva node; Playwright needs a CSS selector. */}
      {dragRect && (
        <div
          data-testid="ocr-drag-rect"
          className="ocr-drag-rect absolute pointer-events-none"
          style={{
            left: dragRect.x,
            top: dragRect.y,
            width: dragRect.width,
            height: dragRect.height,
            border: `2px dashed ${MODE_RECT_COLORS[mode]}`,
            backgroundColor: "transparent",
          }}
        />
      )}
    </div>
  );
}

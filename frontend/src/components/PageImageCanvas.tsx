// PageImageCanvas.tsx — image viewport with four interaction modes (#197, #198, #297, #302)
//
// Spec: specs/21-konva-renderer.md §4 (component layout), §7 (drag modes),
//       §9 (cursors), §12 (testids), §13 (edge cases — empty state).
//
// spec-21-A2 (#297) replaced the DOM-stub viewport with a real react-konva
// <Stage> host carrying the 6-layer skeleton from spec §4:
//
//   image / overlay-paragraphs / overlay-lines / overlay-words / selection / drag
//
// spec-21-A6 (#302) migrates drag handlers from DOM events on the wrapping
// viewport div onto the Konva <Stage> per spec §7. The handlers receive
// `KonvaEventObject<MouseEvent>` and read pointer position via
// `e.target.getStage().getPointerPosition()`; modifiers come from `e.evt`
// (the underlying DOM event) and are captured at mousedown so a later
// shift/ctrl release mid-drag doesn't change the resolved modifier. Mousemove
// is rAF-throttled through `scheduleDragUpdate` (spec §7 / #301) so 60 Hz
// mouse movement turns into one state update per animation frame.
//
// A Konva <Rect> in the `drag` <Layer> renders the live drag-preview with
// stroke `#2563eb` (blue-600) and `dash=[4, 2]` per spec §9. A DOM sidecar
// `<div data-testid="ocr-drag-rect">` mirrors its position so Playwright can
// locate the drag rect via a CSS selector (Konva nodes can't carry
// `data-testid` — spec §12).
//
// Interaction modes (via viewportStore):
//   select   — drag box-select; fires onBoxSelect(rect, modifier) (#197)
//   rebox    — drag to set new bbox; fires onRebox(rect) (#198)
//   add-word — drag to add new word; fires onAddWord(rect) (#198)
//   erase    — drag erase rect; fires onErasePixels(rect) (#198)
//
// Testid layout (spec §12):
//   image-viewport       — wrapper div around the Stage (also empty-state branch)
//   image-stage          — sidecar div mirroring Stage geometry
//   konva-drag-preview   — the Konva drag-preview Rect inside the `drag` Layer
//   ocr-drag-rect        — DOM sidecar mirroring drag-rect position (Playwright)
//   bbox-overlay-*       — sidecars rendered by BBoxOverlay (#298)
//
// Modifier keys captured at mousedown: plain = replace, Shift = remove,
// Ctrl/Cmd = toggle. Rebox + erase reset to "select" on a successful drag;
// add-word stays active for multi-add.

import { useEffect, useMemo, useRef, useState } from "react";
import type { KonvaEventObject } from "konva/lib/Node";
import { Layer, Rect, Stage } from "react-konva";
import type { components } from "../api/types";
import { getStageDimensions, type EncodedDims } from "../lib/canvas-utils";
import type { BBox } from "../lib/coords";
import { expandSelection } from "../lib/selection-expand";
import { BBoxOverlay, type BBoxItem } from "./BBoxOverlay";
import { PageImage } from "./PageImage";
import { scheduleDragUpdate } from "../lib/rafSchedule";
import { setDragRect, clearSelection } from "../stores/selection-store";
import {
  viewportStore,
  exitToSelectMode,
  toggleAddWordMode,
  toggleEraseMode,
  type ViewportMode,
} from "../stores/viewport-store";
import { useUiPrefs, type LayerVisibility } from "../stores/ui-prefs";
import type { SelectionMode } from "./ImageTabsHeader";
import { useViewportHotkeys } from "../hooks/useViewportHotkeys";

export type SelectionModifier = "replace" | "remove" | "toggle";

interface DragState {
  startX: number;
  startY: number;
  /** Captured at mousedown per spec §7 (Shift release mid-drag does not flip the modifier). */
  modifier: SelectionModifier;
}

/** Resolve the select-mode modifier from a raw DOM MouseEvent (spec §7). */
function resolveModifier(evt: {
  shiftKey?: boolean;
  ctrlKey?: boolean;
  metaKey?: boolean;
}): SelectionModifier {
  if (evt.shiftKey) return "remove";
  if (evt.ctrlKey || evt.metaKey) return "toggle";
  return "replace";
}

type PagePayload = components["schemas"]["PagePayload"];

interface PageImageCanvasProps {
  imageUrl: string;
  /**
   * Page encoding dims. `null` renders the empty-state viewport
   * (spec §13: `<div data-testid="image-viewport" data-state="empty">`).
   */
  encoded: EncodedDims | null;
  /**
   * Full page payload — feeds the selection layer via `expandSelection`
   * (spec §4, §8). `null` or `undefined` renders an empty selection
   * (zero rects, sidecars at item-count=0).
   */
  page?: PagePayload | null;
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
  select: "#2563eb", // blue-600
  rebox: "#16a34a", // green-600
  "add-word": "#9333ea", // purple-600
  erase: "#dc2626", // red-600
};

/**
 * Drag-rect fill per mode (spec §9). Only erase fills its preview rect —
 * the other modes use stroke-only so the page image stays visible
 * underneath the dashed outline.
 */
const MODE_RECT_FILLS: Partial<Record<ViewportMode, string>> = {
  erase: "rgba(220,38,38,0.20)", // red-600 @ 20%
};

/**
 * Image viewport canvas — Konva Stage host with four interaction modes.
 *
 * The wrapping div carries `data-testid="image-viewport"` and captures DOM
 * mouse events for drag interactions; the Konva `<Stage>` lives inside it
 * with `data-testid="image-stage"` for Playwright introspection. Drag
 * handlers will migrate to Konva Stage events in spec-21-C.
 */
/** Tag every BBoxItem with `selected: true` so BBoxOverlay's selected
 * branch lights the SELECTION_STROKE_WIDTH (3 px) path per spec §6/§8. */
function markSelected(items: BBoxItem[]): BBoxItem[] {
  return items.map((item) => ({ ...item, selected: true }));
}

export default function PageImageCanvas({
  imageUrl,
  encoded,
  page,
  onBoxSelect,
  onRebox,
  onAddWord,
  onErasePixels,
}: PageImageCanvasProps) {
  const wrapperRef = useRef<HTMLDivElement>(null);
  // Hold dragState in a ref *and* state so async rAF callbacks (mousemove)
  // see the latest start coordinates without re-binding handlers.
  const dragStateRef = useRef<DragState | null>(null);
  const [dragRect, setLocalDragRect] = useState<BBox | null>(null);
  const [mode, setMode] = useState<ViewportMode>(viewportStore.getState().mode);

  // Subscribe to viewport store mode changes
  useEffect(() => {
    const unsub = viewportStore.subscribe((s) => setMode(s.mode));
    return unsub;
  }, []);

  // Focus the wrapper on mount so keyboard hotkeys (Esc / Shift+…) work
  // immediately without an explicit click. The Stage cannot itself receive
  // focus, so the wrapping div carries tabIndex=0 + focus-visible:ring-2
  // (spec 21 §10, #304).
  useEffect(() => {
    wrapperRef.current?.focus();
  }, []);

  // Spec 21 §10 viewport hotkeys (#304). Wired to useUiPrefs (layer
  // visibility + selection mode) and viewportStore (erase/add-word toggle,
  // cancel mode). The hook listens at document scope; the focus wrapper
  // gives the user a visible focus ring while these are armed.
  //
  // Called unconditionally before any early return so the Rules of Hooks
  // are satisfied — `enabled: true` even on the empty-state branch is
  // harmless because the keys still call store actions; the legacy parity
  // is "global once mounted", which matches the document-scope behaviour
  // the #237 hook already had. Modals self-disable global hotkeys via
  // their own useHotkey scope/options.
  // Spec §4/§8 (spec-21-A5, #300): expand PagePayload.selection into
  // per-layer BBoxItem arrays for the `selection` Konva layer. Memoised
  // on the page reference so unchanged pages don't re-walk line_matches.
  // Items are marked `selected: true` so BBoxOverlay's selected branch
  // upgrades strokeWidth to SELECTION_STROKE_WIDTH=3 (spec §6).
  // Called unconditionally before any early return per Rules of Hooks.
  const expandedSelection = useMemo(() => {
    if (!page) return { paragraphs: [], lines: [], words: [] };
    const e = expandSelection(page);
    return {
      paragraphs: markSelected(e.paragraphs),
      lines: markSelected(e.lines),
      words: markSelected(e.words),
    };
  }, [page]);

  useViewportHotkeys({
    enabled: true,
    layerVisibility: useUiPrefs.getState().layerVisibility,
    onLayerToggle: (layer: keyof LayerVisibility) => {
      useUiPrefs.setState((s) => ({
        layerVisibility: { ...s.layerVisibility, [layer]: !s.layerVisibility[layer] },
      }));
    },
    onEraseToggle: () => toggleEraseMode(),
    onAddWordToggle: () => toggleAddWordMode(),
    onCancelMode: () => {
      clearSelection();
      clearDrag();
      exitToSelectMode();
    },
    onSelectionModeChange: (m: SelectionMode) => {
      useUiPrefs.setState({ selectionMode: m });
    },
  });

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

  function readStagePos(e: KonvaEventObject<MouseEvent>): { x: number; y: number } | null {
    const stage = e.target?.getStage?.();
    const pos = stage?.getPointerPosition();
    if (!pos) return null;
    return { x: pos.x, y: pos.y };
  }

  function computeRect(start: DragState, end: { x: number; y: number }): BBox {
    return {
      x: Math.min(end.x, start.startX),
      y: Math.min(end.y, start.startY),
      width: Math.abs(end.x - start.startX),
      height: Math.abs(end.y - start.startY),
    };
  }

  function clearDrag() {
    dragStateRef.current = null;
    setLocalDragRect(null);
    setDragRect(null);
  }

  function handleStageMouseDown(e: KonvaEventObject<MouseEvent>) {
    const pos = readStagePos(e);
    if (!pos) return;
    dragStateRef.current = {
      startX: pos.x,
      startY: pos.y,
      // Capture modifier at mousedown per spec §7.
      modifier: resolveModifier(e.evt),
    };
    setLocalDragRect(null);
  }

  function handleStageMouseMove(e: KonvaEventObject<MouseEvent>) {
    if (!dragStateRef.current) return;
    const pos = readStagePos(e);
    if (!pos) return;
    // rAF-throttle the React state update (spec §7 / #301).
    scheduleDragUpdate(() => {
      const start = dragStateRef.current;
      if (!start) return;
      const rect = computeRect(start, pos);
      setLocalDragRect(rect);
      setDragRect(rect);
    });
  }

  function handleStageMouseUp(e: KonvaEventObject<MouseEvent>) {
    const start = dragStateRef.current;
    if (!start) return;
    const pos = readStagePos(e) ?? { x: start.startX, y: start.startY };
    const rect = computeRect(start, pos);
    const isTrivial = rect.width <= 2 && rect.height <= 2;
    const modifier = start.modifier;
    clearDrag();

    if (isTrivial) return;

    switch (mode) {
      case "select": {
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

  function handleStageMouseLeave() {
    if (dragStateRef.current) {
      // Drag escaped the Stage area — abort it without firing the callback (spec §13).
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
      ref={wrapperRef}
      className="page-image-canvas relative select-none outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
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

      {/* Konva Stage + 6-layer skeleton from spec §4. Drag handlers live on
          the Stage per spec §7; mousemove is rAF-throttled (spec §7 / #301). */}
      <Stage
        width={dims.width}
        height={dims.height}
        onMouseDown={handleStageMouseDown}
        onMouseMove={handleStageMouseMove}
        onMouseUp={handleStageMouseUp}
        onMouseLeave={handleStageMouseLeave}
      >
        <Layer name="image" listening={false}>
          <PageImage url={imageUrl} width={dims.width} height={dims.height} />
        </Layer>
        <Layer name="overlay-paragraphs" listening={false} />
        <Layer name="overlay-lines" listening={false} />
        <Layer name="overlay-words" listening={false} />
        <Layer name="selection" listening={false}>
          <BBoxOverlay layer="selection-paragraphs" items={expandedSelection.paragraphs} />
          <BBoxOverlay layer="selection-lines" items={expandedSelection.lines} />
          <BBoxOverlay layer="selection-words" items={expandedSelection.words} />
        </Layer>
        <Layer name="drag">
          {dragRect && (
            <Rect
              data-testid="konva-drag-preview"
              x={dragRect.x}
              y={dragRect.y}
              width={dragRect.width}
              height={dragRect.height}
              stroke={MODE_RECT_COLORS[mode]}
              fill={MODE_RECT_FILLS[mode]}
              strokeWidth={2}
              dash={[4, 2]}
              listening={false}
              perfectDrawEnabled={false}
            />
          )}
        </Layer>
      </Stage>

      {/* Drag-rect preview DOM sidecar (spec §12).
          Mirrors the Konva <Rect>; Playwright needs a CSS selector. */}
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
            backgroundColor: MODE_RECT_FILLS[mode] ?? "transparent",
          }}
        />
      )}
    </div>
  );
}

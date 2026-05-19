// PageImageCanvas.tsx — image viewport with four interaction modes (#197, #198, #297, #302)
//
// Phase 2.2: Replaced local Konva Stage + layers with @concavetrillion/pd-ui's
// PageImageCanvas as the canvas host. Labeler-specific layer code lives in
// slot fills (children.selection, children.tool). DOM overlays (mode pill,
// zoom controls, bulk actions, event-capture div) are rendered as siblings
// alongside pd-ui's canvas output.
//
// Spec: specs/21-konva-renderer.md §4 (component layout), §7 (drag modes),
//       §9 (cursors), §12 (testids), §13 (edge cases — empty state).
//       docs/specs/2026-05-16-cross-cut-design.md §7.2 (Phase 2.2).
//
// Layer slot mapping (pd-ui layer name → labeler content):
//   image     — page bitmap (managed entirely by pd-ui)
//   underlay  — (unused by labeler)
//   overlay   — (unused by labeler; word bboxes go via BBoxOverlay in selection slot)
//   selection — BBoxOverlay for paragraphs / lines / words + selection highlight
//   tool      — drag-preview Rect (mode-coloured, dashed)
//   hud       — (unused — DOM HUD elements are positioned outside the Stage)
//
// Interaction modes (via viewportStore):
//   select   — drag box-select; fires onBoxSelect(rect, modifier) (#197)
//   rebox    — drag to set new bbox; fires onRebox(rect) (#198)
//   add-word — drag to add new word; fires onAddWord(rect) (#198)
//   erase    — drag erase rect; fires onErasePixels(rect) (#198)
//
// Testid layout (spec §12):
//   image-viewport       — pd-ui's outer wrapper div (carries data-width / data-height)
//   image-stage          — sidecar div mirroring Stage geometry
//   image-event-overlay  — transparent event-capture div (carries data-mode + cursor)
//   konva-drag-preview   — the Konva drag-preview Rect inside the `tool` Layer
//   ocr-drag-rect        — DOM sidecar mirroring drag-rect position (Playwright, driver-contract)
//   bbox-overlay-*       — sidecars rendered by BBoxOverlay (#298)
//   canvas-mode-pill     — mode indicator pill (top-left overlay)
//   canvas-zoom-controls — zoom buttons (bottom-left overlay)
//   canvas-bulk-actions  — bulk-action strip (top-right overlay, ≥2 words selected)
//
// Capability gaps vs plain local implementation (shims):
//   GAP-1: pd-ui manages its own internal drag for basic selection (mode=select).
//          The labeler overrides this entirely via the event-capture overlay div
//          which captures all mouse events. pd-ui's internal drag never fires.
//          TODO: when pd-ui adds an `onDragComplete(rect)` callback, remove the
//          event-capture overlay and wire callbacks through pd-ui instead.
//   GAP-2: pd-ui's selection is word-ID-based (Set<string>). The labeler uses
//          paragraph/line/word index tuples in selectionStore. The selection slot
//          renders the labeler's BBoxOverlay directly from selectionStore; pd-ui's
//          selection prop is not used (uncontrolled).
//          TODO: when pd-ui adds a paragraph/line selection model, migrate.
//   GAP-3: pd-ui's image-viewport outer div carries data-testid="image-viewport"
//          but NOT data-mode or cursor style. Those attributes live on the
//          image-event-overlay div instead. See §12 note in driver-contract.md.
//
// Modifier keys captured at mousedown: plain = replace, Shift = remove,
// Ctrl/Cmd = toggle. Rebox + erase reset to "select" on a successful drag;
// add-word stays active for multi-add.
//
// Issue #295 (Option C): Mismatches-only word bbox overlay.
// When matchFilterMode is "mismatches_only" (read from useUiPrefs), the
// overlay-words Layer shows all word bboxes but dims exact/validated words
// to MISMATCH_DIM_OPACITY (0.2) via BBoxItem.dimmed.

import { useEffect, useMemo, useRef, useState } from "react";
import { Rect } from "react-konva";
import { PageImageCanvas as PdUiPageImageCanvas } from "@concavetrillion/pd-ui/canvas";
import type { components } from "../api/types";
import { getStageDimensions, type EncodedDims } from "../lib/canvas-utils";
import type { BBox } from "../lib/coords";
import { expandSelection } from "../lib/selection-expand";
import { BBoxOverlay, type BBoxItem } from "./BBoxOverlay";
import { scheduleDragUpdate } from "../lib/rafSchedule";
import { readCssToken, hexToRgba } from "../hooks/useLayerColors";
import { setDragRect, clearSelection, selectionStore, selectWord } from "../stores/selection-store";
import {
  viewportStore,
  exitToSelectMode,
  toggleAddWordMode,
  toggleEraseMode,
  setCanvasZoom,
  type ViewportMode,
} from "../stores/viewport-store";
import { useUiPrefs, type LayerVisibility } from "../stores/ui-prefs";
import type { SelectionMode } from "./ImageTabsHeader";
import { useViewportHotkeys } from "../hooks/useViewportHotkeys";
import { railStore, type RailTarget } from "../stores/rail-store";

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
  page?: PagePayload | null | undefined;
  /** Project ID for constructing POST URLs. */
  projectId?: string | undefined;
  /** Page index (0-based) for constructing POST URLs. */
  pageIndex?: number | undefined;
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

/** Human-readable label per mode for the indicator pill (P5.d). */
const MODE_LABELS: Record<ViewportMode, string> = {
  select: "VIEW",
  rebox: "REFINE",
  "add-word": "ADD",
  erase: "ERASE",
};

/** Drag-rect border color per mode — reads CSS tokens at render time. */
function buildModeRectColors(): Record<ViewportMode, string> {
  return {
    select: readCssToken("--status-ocr", "#5d9fdf"),
    rebox: readCssToken("--status-exact", "#5fbf6a"),
    "add-word": readCssToken("--status-gt", "#a888d4"),
    erase: readCssToken("--status-mismatch", "#dc6555"),
  };
}

/**
 * Drag-rect fill per mode (spec §9). Only erase fills its preview rect —
 * the other modes use stroke-only so the page image stays visible
 * underneath the dashed outline.
 */
function buildModeRectFills(): Partial<Record<ViewportMode, string>> {
  const mismatch = readCssToken("--status-mismatch", "#dc6555");
  return {
    erase: hexToRgba(mismatch, 0.2),
  };
}

/** Tag every BBoxItem with `selected: true` so BBoxOverlay's selected
 * branch lights the SELECTION_STROKE_WIDTH (3 px) path per spec §6/§8. */
function markSelected(items: BBoxItem[]): BBoxItem[] {
  return items.map((item) => ({ ...item, selected: true }));
}

/**
 * Image viewport canvas — pd-ui Konva Stage host with four interaction modes.
 *
 * Phase 2.2: The Konva Stage and image layer are now managed by
 * @concavetrillion/pd-ui's PageImageCanvas. Labeler-specific layers
 * (selection overlays, drag preview) live in slot fills. DOM overlays
 * (mode pill, zoom controls, bulk actions) and the event-capture div
 * are positioned absolutely alongside the pd-ui canvas.
 *
 * The testid `image-viewport` is carried by pd-ui's outer wrapper div.
 * The testid `image-event-overlay` is our event-capture div (carries data-mode + cursor).
 * The testid `ocr-drag-rect` and `.ocr-drag-rect` CSS class are kept for driver compat.
 */
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
  const [railTarget, setRailTarget] = useState<RailTarget>(railStore.getState().target);

  // clearDrag is defined here (before useViewportHotkeys and the early return)
  // because onCancelMode in useViewportHotkeys calls it.
  function clearDrag() {
    dragStateRef.current = null;
    setLocalDragRect(null);
    setDragRect(null);
  }

  // Build per-mode color maps from CSS tokens (called once per render).
  const modeRectColors = buildModeRectColors();
  const modeRectFills = buildModeRectFills();

  // Subscribe to viewport store mode changes
  useEffect(() => {
    const unsub = viewportStore.subscribe((s) => {
      setMode(s.mode);
    });
    return unsub;
  }, []);

  // Subscribe to rail target changes (Slice 13 — target-scoped bbox opacity).
  useEffect(() => {
    const unsub = railStore.subscribe(() => {
      setRailTarget(railStore.getState().target);
    });
    return unsub;
  }, []);

  // Sync rail interaction mode to viewportStore so rail buttons drive canvas behavior.
  useEffect(() => {
    const unsub = railStore.subscribe(() => {
      const railMode = railStore.getState().mode;
      const modeMap: Record<typeof railMode, ViewportMode> = {
        erase: "erase",
        annotate: "add-word",
        view: "select",
        region: "select",
      };
      const target = modeMap[railMode];
      if (target !== undefined && viewportStore.getState().mode !== target) {
        viewportStore.setState({ mode: target, pendingReboxTarget: null });
      }
    });
    return unsub;
  }, []);

  // Track selected word count for bulk-actions strip (P5.d).
  const [selectedWordCount, setSelectedWordCount] = useState(
    () => selectionStore.getState().selectedWords.length,
  );
  useEffect(() => {
    return selectionStore.subscribe((s) => {
      setSelectedWordCount(s.selectedWords.length);
    });
  }, []);

  // Subscribe to matchFilterMode from useUiPrefs (Issue #295).
  const [matchFilterMode, setMatchFilterModeState] = useState(
    () => useUiPrefs.getState().matchFilterMode,
  );
  useEffect(() => {
    return useUiPrefs.subscribe(() => {
      setMatchFilterModeState(useUiPrefs.getState().matchFilterMode);
    });
  }, []);

  // Zoom state (P5.d) — subscribe to viewportStore.canvasZoom.
  const [canvasZoom, setCanvasZoomLocal] = useState(() => viewportStore.getState().canvasZoom);
  useEffect(() => {
    return viewportStore.subscribe((s) => {
      setCanvasZoomLocal(s.canvasZoom);
    });
  }, []);

  // Container size — measured via ResizeObserver on our outer wrapperRef div
  // so our event coordinate conversion matches pd-ui's fit scale. Must be
  // declared before any early return (Rules of Hooks).
  const [containerSize, setContainerSize] = useState({ w: 0, h: 0 });
  useEffect(() => {
    const el = wrapperRef.current;
    if (!el) return;
    setContainerSize({ w: el.clientWidth, h: el.clientHeight });
    const ro = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) {
        setContainerSize({
          w: entry.contentRect.width,
          h: entry.contentRect.height,
        });
      }
    });
    ro.observe(el);
    return () => {
      ro.disconnect();
    };
  }, []);

  // Spec §4/§8 (spec-21-A5, #300): expand PagePayload.selection into
  // per-layer BBoxItem arrays for the `selection` Konva layer.
  const expandedSelection = useMemo(() => {
    if (!page) return { paragraphs: [], lines: [], words: [] };
    const e = expandSelection(page);
    return {
      paragraphs: markSelected(e.paragraphs),
      lines: markSelected(e.lines),
      words: markSelected(e.words),
    };
  }, [page]);

  // Issue #295: Word bbox overlay items for the overlay-words layer.
  const wordOverlayItems = useMemo<BBoxItem[]>(() => {
    const lineMatches = page?.line_matches ?? [];
    const isMismatchOnly = matchFilterMode === "mismatches_only";
    const items: BBoxItem[] = [];
    for (const line of lineMatches) {
      for (const word of line.word_matches) {
        if (word.word_index === null) continue;
        const isExactAndValidated = word.match_status === "exact" && word.is_validated;
        items.push({
          id: `${line.line_index}-${word.word_index}`,
          bbox: word.bbox,
          dimmed: isMismatchOnly ? isExactAndValidated : false,
        });
      }
    }
    return items;
  }, [page, matchFilterMode]);

  // Spec 21 §10 viewport hotkeys (#304).
  // Called unconditionally before any early return (Rules of Hooks).
  useViewportHotkeys({
    enabled: true,
    layerVisibility: useUiPrefs.getState().layerVisibility,
    onLayerToggle: (layer: keyof LayerVisibility) => {
      useUiPrefs.setState((s) => ({
        layerVisibility: { ...s.layerVisibility, [layer]: !s.layerVisibility[layer] },
      }));
    },
    onEraseToggle: () => {
      toggleEraseMode();
    },
    onAddWordToggle: () => {
      toggleAddWordMode();
    },
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

  // Synthetic page shape for pd-ui (only width/height needed; pd-ui CanvasPage interface).
  const pdUiPage = { width: dims.width, height: dims.height };

  function computeRect(start: DragState, end: { x: number; y: number }): BBox {
    return {
      x: Math.min(end.x, start.startX),
      y: Math.min(end.y, start.startY),
      width: Math.abs(end.x - start.startX),
      height: Math.abs(end.y - start.startY),
    };
  }

  // ── Event-capture overlay handlers ─────────────────────────────────────────
  // The event-capture overlay sits above the pd-ui Stage and intercepts all
  // mouse events. This overrides pd-ui's internal drag (GAP-1 shim): pd-ui's
  // Stage never sees mouse events because our overlay captures them first.
  // Pointer position is read from the overlay's bounding rect so coordinates
  // are in Stage-space (the overlay exactly covers the Stage area).

  function readOverlayPos(e: React.MouseEvent, scale: number): { x: number; y: number } {
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const x = (e.clientX - rect.left) / scale;
    const y = (e.clientY - rect.top) / scale;
    return { x, y };
  }

  // P5.d zoom: effective scale derived from canvasZoom and container size.
  // containerSize is measured above (before early return) to satisfy Rules of Hooks.
  const fitScale =
    containerSize.w > 0 && containerSize.h > 0
      ? Math.min(containerSize.w / dims.width, containerSize.h / dims.height, 1.0)
      : 1.0;
  const effectiveScale = canvasZoom === 0 ? fitScale : canvasZoom;

  function handleOverlayMouseDown(e: React.MouseEvent) {
    const pos = readOverlayPos(e, effectiveScale);
    dragStateRef.current = {
      startX: pos.x,
      startY: pos.y,
      modifier: resolveModifier(e),
    };
    setLocalDragRect(null);
  }

  function handleOverlayMouseMove(e: React.MouseEvent) {
    if (!dragStateRef.current) return;
    const pos = readOverlayPos(e, effectiveScale);
    scheduleDragUpdate(() => {
      const start = dragStateRef.current;
      if (!start) return;
      const rect = computeRect(start, pos);
      setLocalDragRect(rect);
      setDragRect(rect);
    });
  }

  function handleOverlayMouseUp(e: React.MouseEvent) {
    const start = dragStateRef.current;
    if (!start) return;
    const pos = readOverlayPos(e, effectiveScale);
    const rect = computeRect(start, pos);
    const isTrivial = rect.width <= 2 && rect.height <= 2;
    const modifier = start.modifier;
    clearDrag();

    if (isTrivial) {
      if (mode === "select") {
        const { x: cx, y: cy } = pos;
        const hit = wordOverlayItems.find(
          (item) =>
            cx >= item.bbox.x &&
            cx <= item.bbox.x + item.bbox.width &&
            cy >= item.bbox.y &&
            cy <= item.bbox.y + item.bbox.height,
        );
        if (hit) {
          const parts = hit.id.split("-").map(Number);
          selectWord(parts[0]!, parts[1]!);
          useUiPrefs.setState({ rightPanelOpen: true });
        }
      }
      return;
    }

    switch (mode) {
      case "select": {
        onBoxSelect?.(rect, modifier);
        break;
      }
      case "rebox": {
        onRebox?.(rect);
        exitToSelectMode();
        break;
      }
      case "add-word": {
        onAddWord?.(rect);
        break;
      }
      case "erase": {
        onErasePixels?.(rect);
        exitToSelectMode();
        break;
      }
    }
  }

  function handleOverlayMouseLeave() {
    if (dragStateRef.current) {
      clearDrag();
    }
  }

  // Note: keyboard handling (Escape, Shift+E, etc.) is provided by useViewportHotkeys
  // which listens at document scope. No inline onKeyDown needed on the wrapper div.

  return (
    <div
      ref={wrapperRef}
      className="page-image-canvas relative select-none"
      style={{ width: "100%", height: "100%" }}
    >
      {/* ── pd-ui PageImageCanvas — Konva Stage host ──────────────────────────
          Provides: image layer, Stage setup, ResizeObserver for container size,
          focus management (tabIndex=0 + focus() on mount), context provider.
          Renders outer div with data-testid="image-viewport" (driver contract §2.7).
          data-width / data-height on that div come from pdUiPage.width/height.
          The image-stage sidecar and image-event-overlay below handle the
          remaining testid / attribute requirements from spec §12. */}
      <PdUiPageImageCanvas
        src={imageUrl}
        page={pdUiPage}
        words={[]}
        initialZoom={canvasZoom}
        fitOnMount={canvasZoom === 0}
      >
        {{
          // ── selection slot: labeler BBoxOverlay layers ──────────────────
          // Rendered inside Konva Layer name="selection" by pd-ui.
          // Replaces the local overlay-paragraphs / overlay-lines /
          // overlay-words / selection layers from the previous implementation.
          selection: () => (
            <>
              {/* Word overlay (#295 — mismatches filter) */}
              <BBoxOverlay
                layer="words"
                items={wordOverlayItems}
                visible={useUiPrefs.getState().layerVisibility.word}
              />
              {/* Selection highlight overlays (Slice 13 — rail target scoping) */}
              <BBoxOverlay
                layer="selection-paragraphs"
                items={expandedSelection.paragraphs}
                dimmed={railTarget !== "block"}
              />
              <BBoxOverlay
                layer="selection-lines"
                items={expandedSelection.lines}
                dimmed={railTarget !== "line"}
              />
              <BBoxOverlay
                layer="selection-words"
                items={expandedSelection.words}
                dimmed={railTarget !== "word"}
              />
            </>
          ),

          // ── tool slot: drag-preview Rect ────────────────────────────────
          // Rendered inside Konva Layer name="tool" by pd-ui.
          // Replaces the local `drag` Layer Rect.
          tool: () =>
            dragRect ? (
              <Rect
                data-testid="konva-drag-preview"
                x={dragRect.x}
                y={dragRect.y}
                width={dragRect.width}
                height={dragRect.height}
                stroke={modeRectColors[mode]}
                {...(modeRectFills[mode] !== undefined ? { fill: modeRectFills[mode] } : {})}
                strokeWidth={2}
                dash={[4, 2]}
                listening={false}
                perfectDrawEnabled={false}
              />
            ) : null,
        }}
      </PdUiPageImageCanvas>

      {/* ── image-stage sidecar (spec §12) ────────────────────────────────────
          Mirrors Stage geometry so tests and Playwright can introspect natural
          dimensions without diving into Konva's internal canvas nodes. */}
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

      {/* ── event-capture overlay (GAP-1 shim) ────────────────────────────────
          Absolutely positioned over the entire canvas area. Captures all mouse
          events so pd-ui's internal Stage drag never fires. Carries data-mode
          (used by tests + Playwright) and cursor style (spec §9).
          data-testid="image-event-overlay" — not a driver-contract testid;
          used only by Vitest. The driver-contract testid is "image-viewport"
          (on pd-ui's outer div) and ".ocr-drag-rect" (the DOM sidecar below). */}
      <div
        data-testid="image-event-overlay"
        data-mode={mode}
        style={{
          position: "absolute",
          inset: 0,
          cursor: MODE_CURSORS[mode],
        }}
        onMouseDown={handleOverlayMouseDown}
        onMouseMove={handleOverlayMouseMove}
        onMouseUp={handleOverlayMouseUp}
        onMouseLeave={handleOverlayMouseLeave}
        aria-hidden="true"
      />

      {/* ── Drag-rect sidecar (driver contract) ───────────────────────────────
          Invisible DOM element for Playwright CSS selector targeting only.
          CSS class `.ocr-drag-rect` preserved per docs/architecture/13-driver-contract.md §2.
          Coordinates are stage-space (not wrapper-space). */}
      {dragRect && (
        <div
          data-testid="ocr-drag-rect"
          className="ocr-drag-rect absolute pointer-events-none"
          style={{
            left: dragRect.x,
            top: dragRect.y,
            width: dragRect.width,
            height: dragRect.height,
          }}
          aria-hidden="true"
        />
      )}

      {/* ── Mode-indicator pill (P5.d, Gap 24) ───────────────────────────────
          Top-left overlay. Positioned outside the Stage (DOM sibling). */}
      <div
        data-testid="canvas-mode-pill"
        className="absolute top-2 left-2 flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-mono font-semibold pointer-events-none select-none"
        style={{
          backgroundColor: `${modeRectColors[mode]}22`,
          border: `1px solid ${modeRectColors[mode]}88`,
          color: modeRectColors[mode],
        }}
        aria-label={`Canvas mode: ${MODE_LABELS[mode]}`}
      >
        <span
          className="w-[6px] h-[6px] rounded-full flex-shrink-0"
          style={{ backgroundColor: modeRectColors[mode] }}
        />
        {MODE_LABELS[mode]}
      </div>

      {/* ── Zoom controls (P5.d) ──────────────────────────────────────────────
          Bottom-left overlay. Positioned outside the Stage (DOM sibling). */}
      <div
        data-testid="canvas-zoom-controls"
        className="absolute bottom-2 left-2 flex items-center gap-1 pointer-events-auto"
        role="group"
        aria-label="Zoom controls"
      >
        <button
          type="button"
          data-testid="canvas-zoom-fit"
          aria-pressed={canvasZoom === 0}
          onClick={() => {
            setCanvasZoom(0);
          }}
          className={`text-[10px] px-2 py-0.5 rounded border transition-colors ${canvasZoom === 0 ? "border-accent/60 bg-accent/10 text-accent" : "border-border-2 bg-bg-surface/90 text-ink-2 hover:text-ink-1"}`}
        >
          Fit
        </button>
        <button
          type="button"
          data-testid="canvas-zoom-100"
          aria-pressed={canvasZoom === 1.0}
          onClick={() => {
            setCanvasZoom(1.0);
          }}
          className={`text-[10px] px-2 py-0.5 rounded border transition-colors ${canvasZoom === 1.0 ? "border-accent/60 bg-accent/10 text-accent" : "border-border-2 bg-bg-surface/90 text-ink-2 hover:text-ink-1"}`}
        >
          100%
        </button>
      </div>

      {/* ── Bulk-actions strip (P5.d, Gap 24) ────────────────────────────────
          Shown when 2+ words selected. Top-right overlay. */}
      {selectedWordCount >= 2 && (
        <div
          data-testid="canvas-bulk-actions"
          className="absolute top-2 right-2 flex items-center gap-1 pointer-events-auto"
          role="toolbar"
          aria-label="Bulk word actions"
        >
          <button
            type="button"
            data-testid="canvas-bulk-validate"
            className="text-[10px] px-2 py-0.5 rounded border border-status-exact/60 bg-bg-surface/90 text-status-exact hover:bg-status-exact/10 transition-colors"
            onClick={() => {
              /* bulk validate — wired when useWordMutations bulk API lands */
            }}
          >
            Validate all
          </button>
          <button
            type="button"
            data-testid="canvas-bulk-skip"
            className="text-[10px] px-2 py-0.5 rounded border border-status-fuzzy/60 bg-bg-surface/90 text-status-fuzzy hover:bg-status-fuzzy/10 transition-colors"
            onClick={() => {
              /* bulk skip */
            }}
          >
            Skip all
          </button>
          <button
            type="button"
            data-testid="canvas-bulk-delete"
            className="text-[10px] px-2 py-0.5 rounded border border-status-mismatch/60 bg-bg-surface/90 text-status-mismatch hover:bg-status-mismatch/10 transition-colors"
            onClick={() => {
              /* bulk delete */
            }}
          >
            Delete
          </button>
        </div>
      )}
    </div>
  );
}

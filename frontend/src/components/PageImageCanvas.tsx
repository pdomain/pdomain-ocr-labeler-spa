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
//
// Issue #295 (Option C): Mismatches-only word bbox overlay.
// When matchFilterMode is "mismatches_only" (read from useUiPrefs), the
// overlay-words Layer shows all word bboxes but dims exact/validated words
// to MISMATCH_DIM_OPACITY (0.2) via BBoxItem.dimmed. Mismatch/fuzzy/
// unmatched/unvalidated words remain at full opacity.

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
  const [railTarget, setRailTarget] = useState<RailTarget>(railStore.getState().target);

  // Build per-mode color maps from CSS tokens (called once per render).
  const modeRectColors = buildModeRectColors();
  const modeRectFills = buildModeRectFills();

  // Subscribe to viewport store mode changes
  useEffect(() => {
    const unsub = viewportStore.subscribe((s) => setMode(s.mode));
    return unsub;
  }, []);

  // Subscribe to rail target changes (Slice 13 — target-scoped bbox opacity).
  // railStore.subscribe takes a no-arg Listener; read state via getState().
  useEffect(() => {
    const unsub = railStore.subscribe(() => setRailTarget(railStore.getState().target));
    return unsub;
  }, []);

  // Sync rail interaction mode to viewportStore so rail buttons drive canvas behavior.
  // Use direct setState (not toggle helpers) so the result is deterministic regardless of
  // prior mode — toggles have flip semantics that break if the guard drifts.
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
    return selectionStore.subscribe((s) => setSelectedWordCount(s.selectedWords.length));
  }, []);

  // Subscribe to matchFilterMode from useUiPrefs (Issue #295).
  // Triggers a re-render when the user toggles the Mismatches-only filter.
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
    return viewportStore.subscribe((s) => setCanvasZoomLocal(s.canvasZoom));
  }, []);

  // Container size — measured via ResizeObserver so fitScale stays correct
  // when the pane is resized (P5.d).
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
    return () => ro.disconnect();
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

  // Issue #295: Word bbox overlay items for the overlay-words Layer.
  // Builds BBoxItems from page.line_matches, applying per-item `dimmed`
  // when matchFilterMode is "mismatches_only". Exact + validated words
  // are dimmed; mismatch/fuzzy/unmatched/unvalidated words stay at full opacity.
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

  // P5.d zoom: compute effective scale from canvasZoom + container size.
  // canvasZoom === 0  → fit-to-container (scale ≤ 1.0 so it never upscales)
  // canvasZoom === 1.0 → natural/100% (current legacy behaviour)
  const fitScale =
    containerSize.w > 0 && containerSize.h > 0
      ? Math.min(containerSize.w / dims.width, containerSize.h / dims.height, 1.0)
      : 1.0;
  const effectiveScale = canvasZoom === 0 ? fitScale : canvasZoom;

  function readStagePos(e: KonvaEventObject<MouseEvent>): { x: number; y: number } | null {
    const stage = e.target?.getStage?.();
    const pos = stage?.getPointerPosition();
    if (!pos) return null;
    // Convert screen-pixel coords → Konva/image coordinate space.
    // getPointerPosition() returns pixels relative to the stage container;
    // the stage has scaleX/Y = effectiveScale, so divide to get image coords.
    const s = effectiveScale || 1;
    return { x: pos.x / s, y: pos.y / s };
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

    if (isTrivial) {
      // Treat a trivial drag (≤2px) as a point click.
      // Hit-test word bboxes (display-pixel coords) against the click position.
      // On a hit, select the word and open the right panel.
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
          // parts always has ≥2 elements (id is "lineIdx-wordIdx") — non-null safe.
          selectWord(parts[0]!, parts[1]!);
          // Open the right panel so WordDetail becomes visible
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
      className="page-image-canvas relative select-none outline-none focus-visible:ring-2 focus-visible:ring-accent"
      style={{
        width: "100%",
        height: "100%",
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
      {/* Inner scroll container — wraps Stage only so pinned overlays are
          not clipped when the user scrolls in 100% zoom mode. */}
      <div className="w-full h-full overflow-auto">
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
            the Stage per spec §7; mousemove is rAF-throttled (spec §7 / #301).
            P5.d: scaleX/scaleY drive zoom; Stage width/height are the scaled
            visual dimensions; data-width/data-height on the sidecar retain the
            unscaled natural size for driver inspection. */}
        <Stage
          width={dims.width * effectiveScale}
          height={dims.height * effectiveScale}
          scaleX={effectiveScale}
          scaleY={effectiveScale}
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
          <Layer name="overlay-words" listening={false}>
            {/* Issue #295: word bbox overlay with per-item dimming for mismatches filter */}
            <BBoxOverlay
              layer="words"
              items={wordOverlayItems}
              visible={useUiPrefs.getState().layerVisibility.word}
            />
          </Layer>
          <Layer name="selection" listening={false}>
            {/* Slice 13: active target layer renders full opacity; others dimmed.
              "block" target maps to paragraph layer (closest available). */}
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
          </Layer>
          <Layer name="drag">
            {dragRect && (
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
            )}
          </Layer>
        </Stage>
      </div>
      {/* end inner scroll container */}

      {/* Drag-rect sidecar — invisible element for Playwright CSS selector targeting only.
          The Konva <Rect> in the stage layer is the actual visual.
          Coordinates are stage-space and do NOT match wrapper-space, so no visual styling. */}
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

      {/* Mode-indicator pill (P5.d, Gap 24) — top-left overlay. */}
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

      {/* Zoom controls (P5.d) — bottom-left overlay. */}
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
          onClick={() => setCanvasZoom(0)}
          className={`text-[10px] px-2 py-0.5 rounded border transition-colors ${canvasZoom === 0 ? "border-accent/60 bg-accent/10 text-accent" : "border-border-2 bg-bg-surface/90 text-ink-2 hover:text-ink-1"}`}
        >
          Fit
        </button>
        <button
          type="button"
          data-testid="canvas-zoom-100"
          aria-pressed={canvasZoom === 1.0}
          onClick={() => setCanvasZoom(1.0)}
          className={`text-[10px] px-2 py-0.5 rounded border transition-colors ${canvasZoom === 1.0 ? "border-accent/60 bg-accent/10 text-accent" : "border-border-2 bg-bg-surface/90 text-ink-2 hover:text-ink-1"}`}
        >
          100%
        </button>
      </div>

      {/* Bulk-actions strip (P5.d, Gap 24) — shown when 2+ words selected. */}
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

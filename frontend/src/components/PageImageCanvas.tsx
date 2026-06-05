// PageImageCanvas.tsx — image viewport with four interaction modes (#197, #198, #297, #302)
//
// Replaced the local Konva Stage + layers with @pdomain/pdomain-ui's
// PageImageCanvas as the canvas host. Labeler-specific layer code lives in
// slot fills (children.selection, children.tool). DOM overlays (mode pill,
// zoom controls, bulk actions) are rendered as siblings alongside the canvas.
//
// Pointer interaction is driven by pdomain-ui's onStagePointerDown/Move/Up slot
// callbacks. The callback receives the raw Konva event plus a CoordContext whose
// `scale` is the SAME effective scale pdomain-ui applies internally. Page-space
// coords are derived from `e.target.getStage().getPointerPosition()` divided by
// `ctx.scale` — Konva's pointer position is already scroll- AND scale-aware, so
// hit-testing lands on the right bbox regardless of the canvas scroll offset or
// the internally-computed fit scale. This replaced a hand-rolled DOM
// event-capture overlay that read `clientX - rect.left` and computed its own
// scale; that overlay ignored the scroll offset and could disagree with
// pdomain-ui's scale, causing bbox clicks to miss (#bbox-click-selection).
//
// Spec: specs/21-konva-renderer.md §4 (component layout), §7 (drag modes),
//       §9 (cursors), §12 (testids), §13 (edge cases — empty state).
//       docs/specs/2026-05-16-cross-cut-design.md §7.2 (Phase 2.2).
//
// Layer slot mapping (pdomain-ui layer name → labeler content):
//   image     — page bitmap (managed entirely by pdomain-ui)
//   underlay  — (unused by labeler)
//   overlay   — (unused by labeler; word bboxes go via BBoxOverlay in selection slot)
//   selection — BBoxOverlay for paragraphs / lines / words + selection highlight
//   tool      — drag-preview Rect (mode-coloured, dashed)
//   hud       — (unused — DOM HUD elements are positioned outside the Stage)
//
// Interaction modes (via viewportStore):
//   select   — point-click (≤2px) selects a word; drag box-select fires
//              onBoxSelect(rect, modifier) (#197)
//   rebox    — drag to set new bbox; fires onRebox(rect) (#198)
//   add-word — drag to add new word; fires onAddWord(rect) (#198)
//   erase    — drag erase rect; fires onErasePixels(rect) (#198)
//
// Testid layout (spec §12):
//   image-viewport       — pdomain-ui's outer wrapper div (carries data-width / data-height)
//   image-stage          — sidecar div mirroring Stage geometry (carries data-mode for tests)
//   konva-drag-preview   — the Konva drag-preview Rect inside the `tool` Layer
//   ocr-drag-rect        — DOM sidecar mirroring drag-rect position (Playwright, driver-contract)
//   bbox-overlay-*       — sidecars rendered by BBoxOverlay (#298)
//   canvas-mode-pill     — mode indicator pill (top-left overlay)
//   canvas-zoom-controls — zoom buttons (bottom-left overlay)
//   canvas-bulk-actions  — bulk-action strip (top-right overlay, ≥2 words selected)
//
// Capability gaps vs plain local implementation (shims):
//   GAP-2: pdomain-ui's built-in selection is word-ID-based (Set<string>). The
//          labeler uses paragraph/line/word index tuples in selectionStore, so
//          the canvas does NOT pass `selection`/`onSelectionChange`; it drives
//          selection itself via the onStagePointer* callbacks and the labeler's
//          selectionStore. The selection slot renders the labeler's BBoxOverlay.
//          TODO: when pdomain-ui adds a paragraph/line selection model, migrate.
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
import type { KonvaEventObject } from "konva/lib/Node";
import {
  PageImageCanvas as PdUiPageImageCanvas,
  rectItemsToDisplay,
  rectToDisplay,
  type CoordContext,
} from "@pdomain/pdomain-ui/canvas";
import type { components } from "../api/types";
import { getStageDimensions, type EncodedDims } from "../lib/canvas-utils";
import type { BBox } from "../lib/coords";
import { expandFromStore } from "../lib/selection-expand";
import { BBoxOverlay, type BBoxItem } from "./BBoxOverlay";
import { scheduleDragUpdate } from "../lib/rafSchedule";
import { readCssToken, hexToRgba } from "../hooks/useLayerColors";
import {
  setDragRect,
  clearSelection,
  selectionStore,
  selectBlock,
  selectPara,
  selectLine,
  selectWord,
} from "../stores/selection-store";
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
type LineMatch = components["schemas"]["LineMatch"];
type WordMatch = components["schemas"]["WordMatch"];

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

function itemsToDisplay(items: BBoxItem[], encoded: EncodedDims | null): BBoxItem[] {
  return rectItemsToDisplay(items, encoded);
}

function unionBBoxes(bboxes: readonly BBox[]): BBox | null {
  if (bboxes.length === 0) return null;
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const bbox of bboxes) {
    minX = Math.min(minX, bbox.x);
    minY = Math.min(minY, bbox.y);
    maxX = Math.max(maxX, bbox.x + bbox.width);
    maxY = Math.max(maxY, bbox.y + bbox.height);
  }
  return { x: minX, y: minY, width: maxX - minX, height: maxY - minY };
}

function visibleWordBoxes(words: readonly WordMatch[]): BBox[] {
  return words.map((word) => word.bbox).filter((bbox) => bbox.width > 0 && bbox.height > 0);
}

function buildGroupItems(lines: readonly LineMatch[], groupKey: "block_index" | "paragraph_index") {
  const groups = new Map<number, BBox[]>();
  for (const line of lines) {
    const key = line[groupKey];
    if (key === null || key === undefined) continue;
    const boxes = groups.get(key) ?? [];
    boxes.push(...visibleWordBoxes(line.word_matches));
    groups.set(key, boxes);
  }
  return Array.from(groups.entries())
    .sort(([a], [b]) => a - b)
    .flatMap(([key, boxes]) => {
      const bbox = unionBBoxes(boxes);
      return bbox ? [{ id: String(key), bbox }] : [];
    });
}

function buildLineItems(lines: readonly LineMatch[]): BBoxItem[] {
  return lines.flatMap((line) => {
    const bbox = unionBBoxes(visibleWordBoxes(line.word_matches));
    return bbox ? [{ id: String(line.line_index), bbox }] : [];
  });
}

function hitTest(items: readonly BBoxItem[], x: number, y: number): BBoxItem | undefined {
  return items.find(
    (item) =>
      x >= item.bbox.x &&
      x <= item.bbox.x + item.bbox.width &&
      y >= item.bbox.y &&
      y <= item.bbox.y + item.bbox.height,
  );
}

/**
 * Image viewport canvas — pdomain-ui Konva Stage host with four interaction modes.
 *
 * The Konva Stage and image layer are managed by @pdomain/pdomain-ui's
 * PageImageCanvas. Labeler-specific layers (selection overlays, drag preview)
 * live in slot fills. DOM overlays (mode pill, zoom controls, bulk actions)
 * are positioned absolutely alongside the pdomain-ui canvas.
 *
 * Pointer interaction is wired through pdomain-ui's onStagePointerDown/Move/Up
 * slot callbacks rather than a DOM event-capture overlay, so coordinate math
 * uses Konva's scroll- and scale-aware pointer position.
 *
 * The testid `image-viewport` is carried by pdomain-ui's outer wrapper div.
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
  // Drag start coordinates (page-space). Held in state because the drag-preview
  // Rect and the ocr-drag-rect sidecar render from React state.
  const dragStateRef = useRef<DragState | null>(null);
  const [dragRect, setLocalDragRect] = useState<BBox | null>(null);
  const [mode, setMode] = useState<ViewportMode>(viewportStore.getState().mode);
  const [railTarget, setRailTarget] = useState<RailTarget>(railStore.getState().target);
  const [layerVisibility, setLayerVisibility] = useState<LayerVisibility>(
    () => useUiPrefs.getState().layerVisibility,
  );

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
      const nextTarget = railStore.getState().target;
      setRailTarget(nextTarget);
      if (nextTarget === "para") {
        useUiPrefs.setState({ selectionMode: "paragraph" });
      } else if (nextTarget === "line" || nextTarget === "word") {
        useUiPrefs.setState({ selectionMode: nextTarget });
      }
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

  // SEL-1: Subscribe to selectionStore for both bulk-action count and highlight overlay.
  const [selectionState, setSelectionState] = useState(() => {
    const s = selectionStore.getState();
    return {
      selectedWords: s.selectedWords,
      selectedLines: s.selectedLines,
      selectedParagraphs: s.selectedParagraphs,
    };
  });
  // Derived for backward-compat callers that still use selectedWordCount.
  const selectedWordCount = selectionState.selectedWords.length;
  useEffect(() => {
    return selectionStore.subscribe((s) => {
      setSelectionState({
        selectedWords: s.selectedWords,
        selectedLines: s.selectedLines,
        selectedParagraphs: s.selectedParagraphs,
      });
    });
  }, []);

  // Subscribe to UI prefs used by the canvas.
  const [matchFilterMode, setMatchFilterModeState] = useState(
    () => useUiPrefs.getState().matchFilterMode,
  );
  useEffect(() => {
    return useUiPrefs.subscribe(() => {
      const state = useUiPrefs.getState();
      setMatchFilterModeState(state.matchFilterMode);
      setLayerVisibility(state.layerVisibility);
    });
  }, []);

  // Zoom state (P5.d) — subscribe to viewportStore.canvasZoom.
  const [canvasZoom, setCanvasZoomLocal] = useState(() => viewportStore.getState().canvasZoom);
  useEffect(() => {
    return viewportStore.subscribe((s) => {
      setCanvasZoomLocal(s.canvasZoom);
    });
  }, []);

  // SEL-1: Derive selection highlight overlay from selectionStore (local state),
  // not from page.selection (server round-trip). Clicking a word sets the store
  // synchronously → highlight appears with no network round-trip.
  const expandedSelection = useMemo(() => {
    if (!page) return { paragraphs: [], lines: [], words: [] };
    const e = expandFromStore(selectionState, page);
    return {
      paragraphs: markSelected(itemsToDisplay(e.paragraphs, encoded)),
      lines: markSelected(itemsToDisplay(e.lines, encoded)),
      words: markSelected(itemsToDisplay(e.words, encoded)),
    };
  }, [page, encoded, selectionState]);

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
          bbox: encoded ? rectToDisplay(word.bbox, encoded) : word.bbox,
          dimmed: isMismatchOnly ? isExactAndValidated : false,
        });
      }
    }
    return items;
  }, [page, matchFilterMode, encoded]);

  const structuralOverlayItems = useMemo(() => {
    const lineMatches = page?.line_matches ?? [];
    return {
      blocks: itemsToDisplay(buildGroupItems(lineMatches, "block_index"), encoded),
      paragraphs: itemsToDisplay(buildGroupItems(lineMatches, "paragraph_index"), encoded),
      lines: itemsToDisplay(buildLineItems(lineMatches), encoded),
    };
  }, [page, encoded]);

  // Spec 21 §10 viewport hotkeys (#304).
  // Called unconditionally before any early return (Rules of Hooks).
  useViewportHotkeys({
    enabled: true,
    layerVisibility,
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

  // Synthetic page shape for pdomain-ui (only width/height needed; pdomain-ui CanvasPage interface).
  const pdUiPage = { width: dims.width, height: dims.height };

  function computeRect(start: DragState, end: { x: number; y: number }): BBox {
    return {
      x: Math.min(end.x, start.startX),
      y: Math.min(end.y, start.startY),
      width: Math.abs(end.x - start.startX),
      height: Math.abs(end.y - start.startY),
    };
  }

  // ── Konva Stage pointer handlers (pdomain-ui slot callbacks) ────────────────
  // pdomain-ui calls these with the raw Konva event and a CoordContext. The
  // Stage's getPointerPosition() is already scroll- AND scale-aware, so dividing
  // by ctx.scale yields page-space (= display-pixel) coords that match the
  // wordOverlayItems bboxes and the dims passed to pdomain-ui. This is what
  // replaces the old DOM event-capture overlay's clientX/rect.left math.

  function readStagePos(
    e: KonvaEventObject<MouseEvent>,
    ctx: CoordContext,
  ): { x: number; y: number } | null {
    const stage = e.target.getStage();
    const pointer = stage?.getPointerPosition();
    if (!pointer) return null;
    const scale = ctx.scale || 1;
    return { x: pointer.x / scale, y: pointer.y / scale };
  }

  function handleStagePointerDown(e: KonvaEventObject<MouseEvent>, ctx: CoordContext) {
    const pos = readStagePos(e, ctx);
    if (!pos) return;
    dragStateRef.current = {
      startX: pos.x,
      startY: pos.y,
      modifier: resolveModifier(e.evt),
    };
    setLocalDragRect(null);
  }

  function handleStagePointerMove(e: KonvaEventObject<MouseEvent>, ctx: CoordContext) {
    const start = dragStateRef.current;
    if (!start) return;
    const pos = readStagePos(e, ctx);
    if (!pos) return;
    scheduleDragUpdate(() => {
      const rect = computeRect(start, pos);
      setLocalDragRect(rect);
      setDragRect(rect);
    });
  }

  function handleStagePointerUp(e: KonvaEventObject<MouseEvent>, ctx: CoordContext) {
    const start = dragStateRef.current;
    if (!start) return;
    const pos = readStagePos(e, ctx);
    if (!pos) {
      clearDrag();
      return;
    }
    const rect = computeRect(start, pos);
    const isTrivial = rect.width <= 2 && rect.height <= 2;
    const modifier = start.modifier;
    clearDrag();

    if (isTrivial) {
      if (mode === "select") {
        const { x: cx, y: cy } = pos;
        const hit =
          railTarget === "block"
            ? hitTest(structuralOverlayItems.blocks, cx, cy)
            : railTarget === "para"
              ? hitTest(structuralOverlayItems.paragraphs, cx, cy)
              : railTarget === "line"
                ? hitTest(structuralOverlayItems.lines, cx, cy)
                : hitTest(wordOverlayItems, cx, cy);
        if (!hit) return;

        if (railTarget === "block") {
          selectBlock(hit.id);
        } else if (railTarget === "para") {
          selectPara(Number(hit.id));
        } else if (railTarget === "line") {
          selectLine(Number(hit.id));
        } else {
          const parts = hit.id.split("-").map(Number);
          selectWord(parts[0]!, parts[1]!);
        }
        useUiPrefs.setState({ rightPanelOpen: true });
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

  // Note: keyboard handling (Escape, Shift+E, etc.) is provided by useViewportHotkeys
  // which listens at document scope. No inline onKeyDown needed on the wrapper div.

  return (
    <div
      data-testid="image-canvas-wrapper"
      className="page-image-canvas relative select-none"
      style={{ width: "100%", height: "100%", cursor: MODE_CURSORS[mode] }}
    >
      {/* ── pdomain-ui PageImageCanvas — Konva Stage host ──────────────────────────
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
        onStagePointerDown={handleStagePointerDown}
        onStagePointerMove={handleStagePointerMove}
        onStagePointerUp={handleStagePointerUp}
      >
        {{
          // ── selection slot: labeler BBoxOverlay layers ──────────────────
          // Rendered inside Konva Layer name="selection" by pdomain-ui.
          // Replaces the local overlay-paragraphs / overlay-lines /
          // overlay-words / selection layers from the previous implementation.
          selection: () => (
            <>
              {/* Regular bbox overlays; visibility is controlled by the rail Layers section. */}
              <BBoxOverlay
                layer="blocks"
                items={structuralOverlayItems.blocks}
                visible={layerVisibility.block}
              />
              <BBoxOverlay
                layer="paragraphs"
                items={structuralOverlayItems.paragraphs}
                visible={layerVisibility.paragraph}
              />
              <BBoxOverlay
                layer="lines"
                items={structuralOverlayItems.lines}
                visible={layerVisibility.line}
              />
              <BBoxOverlay layer="words" items={wordOverlayItems} visible={layerVisibility.word} />
              {/* Selection highlight overlays (Slice 13 — rail target scoping) */}
              <BBoxOverlay
                layer="selection-paragraphs"
                items={expandedSelection.paragraphs}
                dimmed={railTarget !== "para"}
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
          // Rendered inside Konva Layer name="tool" by pdomain-ui.
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
          dimensions without diving into Konva's internal canvas nodes. Carries
          data-mode (consumed by Vitest only — not a driver-contract attribute). */}
      <div
        data-testid="image-stage"
        data-width={dims.width}
        data-height={dims.height}
        data-mode={mode}
        aria-hidden="true"
        style={{
          position: "absolute",
          inset: 0,
          pointerEvents: "none",
          visibility: "hidden",
        }}
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
        className="absolute top-10 left-2 flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-mono font-semibold pointer-events-none select-none"
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
        className="absolute top-2 left-2 flex items-center gap-1 pointer-events-auto"
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

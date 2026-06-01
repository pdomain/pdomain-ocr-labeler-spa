// PageImageCanvas.test.tsx — viewport canvas tests (#196, #197, #198, #297, #302)
// Covers: B-CANVAS-001, B-CANVAS-002, B-CANVAS-003, B-CANVAS-005, B-CANVAS-006, B-CANVAS-010, B-CANVAS-011, B-CANVAS-012
//
// Pointer interaction is driven by pdomain-ui's onStagePointerDown/Move/Up slot
// callbacks (replacing the former DOM event-capture overlay). Tests fire DOM
// mouse events on the mocked canvas's `image-event-surface`, which forwards them
// as Konva-style stage events with a CoordContext (scale=1) — exercising the
// real `getPointerPosition() / ctx.scale` math.
//
// Testid notes:
//   - `data-mode` lives on the `image-stage` sidecar (Vitest-only attribute).
//   - The mode cursor lives on the `.page-image-canvas` wrapper div.
//   - Drag Layer is `konva-layer-tool` (pdomain-ui naming).
//   - Selection BBoxOverlays render inside `konva-layer-selection` (selection slot).
//   - `image-viewport` is pdomain-ui's outer div (tabIndex=0, auto-focus).
//
// Spec: specs/21-konva-renderer.md §4, §7, §9, §12, §13.

import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { getStageDimensions } from "../lib/canvas-utils";
import { viewportStore } from "../stores/viewport-store";
import { selectionStore } from "../stores/selection-store";
import { useUiPrefs } from "../stores/ui-prefs";
import { railStore } from "../stores/rail-store";

// ── @pdomain/pdomain-ui/canvas mock ───────────────────────────────────────
//
// pdomain-ui's canvas bundle imports react-konva, which in Node.js loads
// konva/lib/index-node.js, which requires('canvas') — a native addon not
// available in jsdom. Mock the entire pdomain-ui canvas module before any
// imports resolve so the canvas binary is never loaded.
//
// The mock renders the structural skeleton that the real pdomain-ui component
// renders, so PageImageCanvas.tsx's slot fills land inside the right layer
// divs. It also exposes a DOM hit-surface (`image-event-surface`) that
// translates DOM mouse events into the Konva-style event + CoordContext shape
// pdomain-ui passes to onStagePointerDown/Move/Up. The Konva pointer position
// is taken straight from clientX/clientY and the CoordContext uses scale=1 so
// the helper coordinates below land 1:1 in page space — this is exactly the
// `pointer / ctx.scale` math the real component runs.
type StagePointerHandler = (
  e: {
    evt: { shiftKey: boolean; ctrlKey: boolean; metaKey: boolean };
    target: { getStage: () => { getPointerPosition: () => { x: number; y: number } } };
  },
  ctx: {
    scale: number;
    stageWidth: number;
    stageHeight: number;
    pageWidth: number;
    pageHeight: number;
  },
) => void;

// Controllable CoordContext scale for the mocked canvas. Tests set this to a
// value != 1 to prove the component divides the Konva pointer position by
// ctx.scale (i.e. that hit-testing is scale-aware, not relying on a 1:1
// jsdom zero-rect fallback). Reset to 1 in afterEach.
const mockStageScale = vi.hoisted(() => ({ value: 1 }));

vi.mock("@pdomain/pdomain-ui/canvas", async () => {
  const { useEffect, useRef } = await import("react");
  const isNormalizedRect = (bbox: { x: number; y: number; width: number; height: number }) =>
    bbox.x >= 0 &&
    bbox.y >= 0 &&
    bbox.width >= 0 &&
    bbox.height >= 0 &&
    bbox.x <= 1 &&
    bbox.y <= 1 &&
    bbox.width <= 1 &&
    bbox.height <= 1 &&
    bbox.x + bbox.width <= 1.000_001 &&
    bbox.y + bbox.height <= 1.000_001;

  const rectToDisplay = (
    bbox: { x: number; y: number; width: number; height: number },
    encoded: {
      display_width: number;
      display_height: number;
      scale: number;
    },
  ) => {
    if (isNormalizedRect(bbox)) {
      return {
        x: bbox.x * encoded.display_width,
        y: bbox.y * encoded.display_height,
        width: bbox.width * encoded.display_width,
        height: bbox.height * encoded.display_height,
      };
    }
    return {
      x: bbox.x * encoded.scale,
      y: bbox.y * encoded.scale,
      width: bbox.width * encoded.scale,
      height: bbox.height * encoded.scale,
    };
  };

  const rectItemsToDisplay = <
    T extends { bbox: { x: number; y: number; width: number; height: number } },
  >(
    items: T[],
    encoded: { display_width: number; display_height: number; scale: number } | null,
  ) =>
    encoded ? items.map((item) => ({ ...item, bbox: rectToDisplay(item.bbox, encoded) })) : items;

  return {
    rectToDisplay,
    rectItemsToDisplay,
    RectOverlayLayer: ({
      layer,
      items,
      colors,
      dimmed,
      selectionStrokeWidth = 3,
      layerDimmedOpacity = 0.3,
      itemDimmedOpacity = 0.2,
    }: {
      layer: string;
      items: Array<{
        id: string;
        bbox: { x: number; y: number; width: number; height: number };
        selected?: boolean;
        dimmed?: boolean;
      }>;
      colors: { fill: string; stroke: string; strokeWidth: number };
      dimmed?: boolean;
      selectionStrokeWidth?: number;
      layerDimmedOpacity?: number;
      itemDimmedOpacity?: number;
    }) => {
      const layerOpacity = dimmed ? layerDimmedOpacity : 1;
      return (
        <>
          {items.map((item) => (
            <div
              key={item.id}
              data-testid={`rect-overlay-${layer}-${item.id}`}
              data-x={item.bbox.x}
              data-y={item.bbox.y}
              data-width={item.bbox.width}
              data-height={item.bbox.height}
              data-fill={colors.fill}
              data-stroke={colors.stroke}
              data-stroke-width={item.selected ? selectionStrokeWidth : colors.strokeWidth}
              data-opacity={item.dimmed ? itemDimmedOpacity : layerOpacity}
            />
          ))}
          <div
            key={`bbox-overlay-${layer}-sidecar`}
            data-testid={`bbox-overlay-${layer}`}
            data-layer={layer}
            data-item-count={items.length}
            data-dimmed={dimmed ? "true" : undefined}
            aria-hidden="true"
          />
        </>
      );
    },
    PageImageCanvas: ({
      page,
      children,
      onStagePointerDown,
      onStagePointerMove,
      onStagePointerUp,
    }: {
      src?: string;
      page?: { width: number; height: number };
      words?: unknown[];
      initialZoom?: number;
      fitOnMount?: boolean;
      onStagePointerDown?: StagePointerHandler;
      onStagePointerMove?: StagePointerHandler;
      onStagePointerUp?: StagePointerHandler;
      children?: {
        selection?: (p: Record<string, unknown>) => React.ReactNode;
        tool?: (p: Record<string, unknown>) => React.ReactNode;
        hud?: (p: Record<string, unknown>) => React.ReactNode;
      };
    }) => {
      const divRef = useRef<HTMLDivElement>(null);
      // Mirror pdomain-ui's focus-on-mount (yt's useEffect in the real component).
      useEffect(() => {
        divRef.current?.focus();
      }, []);
      const slotProps = {};
      const ctx = {
        scale: mockStageScale.value,
        stageWidth: (page?.width ?? 0) * mockStageScale.value,
        stageHeight: (page?.height ?? 0) * mockStageScale.value,
        pageWidth: page?.width ?? 0,
        pageHeight: page?.height ?? 0,
      };
      const toKonva = (e: React.MouseEvent) => {
        // Konva's getPointerPosition() returns stage-space coords (already
        // scaled). clientX/Y stand in for that scaled position here.
        const pos = { x: e.clientX, y: e.clientY };
        return {
          evt: { shiftKey: !!e.shiftKey, ctrlKey: !!e.ctrlKey, metaKey: !!e.metaKey },
          target: { getStage: () => ({ getPointerPosition: () => pos }) },
        };
      };
      return (
        <div
          ref={divRef}
          data-testid="image-viewport"
          data-width={page?.width}
          data-height={page?.height}
          tabIndex={0}
          role="img"
          aria-label="Page image viewport"
          style={{ width: "100%", height: "100%" }}
        >
          {/* Mirrors pdomain-ui's inner Stage structure */}
          <div data-testid="canvas-stage">
            <div data-testid="konva-layer-image" data-layer-name="image" data-listening="false" />
            <div
              data-testid="konva-layer-underlay"
              data-layer-name="underlay"
              data-listening="false"
            />
            <div
              data-testid="konva-layer-overlay"
              data-layer-name="overlay"
              data-listening="false"
            />
            <div
              data-testid="konva-layer-selection"
              data-layer-name="selection"
              data-listening="false"
            >
              {children?.selection?.(slotProps)}
            </div>
            <div data-testid="konva-layer-tool" data-layer-name="tool">
              {children?.tool?.(slotProps)}
            </div>
            <div data-testid="konva-layer-hud" data-layer-name="hud" data-listening="false">
              {children?.hud?.(slotProps)}
            </div>
          </div>
          {/* Hit-surface translating DOM mouse events → Konva stage callbacks. */}
          <div
            data-testid="image-event-surface"
            onMouseDown={(e) => onStagePointerDown?.(toKonva(e), ctx)}
            onMouseMove={(e) => onStagePointerMove?.(toKonva(e), ctx)}
            onMouseUp={(e) => onStagePointerUp?.(toKonva(e), ctx)}
          />
        </div>
      );
    },
  };
});

// ── use-image mock (used by pdomain-ui's internal image loading) ──────────────────
const mockUseImageState = vi.hoisted(() => ({
  image: undefined as HTMLImageElement | undefined,
  status: "loading",
}));

vi.mock("use-image", () => ({
  default: () => [mockUseImageState.image, mockUseImageState.status] as const,
}));

// ── react-konva mock — render simple divs so jsdom can probe the tree ────────
//
// The labeler component renders only Konva <Rect> (drag-preview) directly; the
// Stage is owned by the mocked pdomain-ui PageImageCanvas above. Pointer events
// are delivered through that mock's image-event-surface, not via react-konva.
vi.mock("react-konva", () => ({
  Layer: ({
    children,
    name,
    listening,
    globalCompositeOperation,
  }: {
    children?: React.ReactNode;
    name?: string;
    listening?: boolean;
    globalCompositeOperation?: string;
  }) => (
    <div
      data-testid={`konva-layer-${name ?? "unnamed"}`}
      data-layer-name={name}
      data-listening={listening === undefined ? undefined : String(listening)}
      data-gco={globalCompositeOperation}
    >
      {children}
    </div>
  ),
  Image: ({
    width,
    height,
    image,
    "data-testid": testId,
  }: {
    width?: number;
    height?: number;
    image?: HTMLImageElement;
    "data-testid"?: string;
  }) => (
    <div
      data-testid={testId ?? "konva-image"}
      data-width={width}
      data-height={height}
      data-has-image={image ? "true" : "false"}
    />
  ),
  Rect: ({
    x,
    y,
    width,
    height,
    fill,
    stroke,
    strokeWidth,
    dash,
    "data-testid": testId,
  }: {
    x?: number;
    y?: number;
    width?: number;
    height?: number;
    fill?: string;
    stroke?: string;
    strokeWidth?: number;
    dash?: number[];
    "data-testid"?: string;
  }) => (
    <div
      data-testid={testId ?? "konva-rect"}
      data-x={x}
      data-y={y}
      data-width={width}
      data-height={height}
      data-fill={fill}
      data-stroke={stroke}
      data-stroke-width={strokeWidth}
      data-dash={dash ? dash.join(",") : undefined}
    />
  ),
}));

// rafSchedule mock — run the scheduled callback synchronously so tests can
// assert dragRect state immediately after mousemove.
vi.mock("../lib/rafSchedule", () => ({
  scheduleDragUpdate: (fn: () => void) => fn(),
}));

// Import the component AFTER mocks so it pulls the mocked react-konva.
import PageImageCanvas from "./PageImageCanvas";
import type { components } from "../api/types";
import { SELECTION_STROKE_WIDTH } from "./BBoxOverlay";

type PagePayload = components["schemas"]["PagePayload"];
type LineMatch = components["schemas"]["LineMatch"];
type WordMatch = components["schemas"]["WordMatch"];

// ── Selection-layer fixture helpers (spec-21-A5, #300) ──────────────────────

function makeWord(
  line_index: number,
  word_index: number,
  bbox: { x: number; y: number; width: number; height: number },
): WordMatch {
  return {
    line_index,
    word_index,
    ocr_text: `w${line_index}-${word_index}`,
    ground_truth_text: "",
    match_status: "exact",
    normalized_match: false,
    is_validated: false,
    bbox,
  };
}

function makeLine(
  line_index: number,
  paragraph_index: number | null,
  word_bboxes: { x: number; y: number; width: number; height: number }[],
): LineMatch {
  return {
    line_index,
    paragraph_index,
    ocr_line_text: `line ${line_index}`,
    ground_truth_line_text: "",
    word_matches: word_bboxes.map((b, i) => makeWord(line_index, i, b)),
    overall_match_status: "exact",
    exact_count: word_bboxes.length,
    fuzzy_count: 0,
    mismatch_count: 0,
    unmatched_gt_count: 0,
    unmatched_ocr_count: 0,
    validated_word_count: 0,
    total_word_count: word_bboxes.length,
    is_fully_validated: false,
  };
}

function makePage(line_matches: LineMatch[], selection?: PagePayload["selection"]): PagePayload {
  return {
    project_id: "proj-001",
    page_index: 0,
    page_record: null,
    line_matches,
    ...(selection !== undefined && { selection }),
    encoded_dims: null,
    line_filter: "all",
    image_url: null,
    generation: 1,
  };
}

const encoded = {
  src_width: 1600,
  src_height: 1200,
  display_width: 800,
  display_height: 600,
  scale: 0.5,
};

// Reset stores and use-image state after each test
afterEach(() => {
  viewportStore.setState({ mode: "select", pendingReboxTarget: null, canvasZoom: 0 });
  selectionStore.setState({
    selectedParagraphs: [],
    selectedLines: [],
    selectedWords: [],
    dragRect: null,
    level: "none",
    path: {},
  });
  useUiPrefs.setState({
    lineFilter: null,
    layerVisibility: { block: true, paragraph: true, line: true, word: true },
    splitterRatio: 0.5,
    selectionMode: "paragraph",
    matchFilter: "unvalidated",
    rightPanelOpen: false,
  });
  railStore.getState().setTarget("word");
  mockUseImageState.image = undefined;
  mockUseImageState.status = "loading";
  mockStageScale.value = 1;
});

// ── Pointer-interaction helpers ──────────────────────────────────────────────
//
// Pointer interaction is driven by pdomain-ui's onStagePointer* slot callbacks.
// The mocked pdomain-ui canvas above exposes `image-event-surface`, which
// translates DOM mouse events into Konva-style stage events (clientX/Y →
// getPointerPosition()) with a CoordContext scale of 1. Firing DOM mouse events
// on this surface exercises the real component handlers and their
// `pointer / ctx.scale` coordinate math.

function getOverlay(): HTMLElement {
  return screen.getByTestId("image-event-surface");
}

function simulateDrag(
  from: { x: number; y: number },
  to: { x: number; y: number },
  opts: { shiftKey?: boolean; ctrlKey?: boolean } = {},
) {
  const overlay = getOverlay();
  fireEvent.mouseDown(overlay, { clientX: from.x, clientY: from.y, ...opts });
  fireEvent.mouseMove(overlay, { clientX: to.x, clientY: to.y, ...opts });
  fireEvent.mouseUp(overlay, { clientX: to.x, clientY: to.y, ...opts });
}

function sourceToDisplayPoint(x: number, y: number): { x: number; y: number } {
  return { x: x * encoded.scale, y: y * encoded.scale };
}

// ── spec-21-A2 (#297): Stage scaffold ─────────────────────────────────────────

describe("PageImageCanvas — Konva Stage scaffold (spec-21-A2, #297)", () => {
  it("renders an empty-state viewport when encoded is null (spec §13)", () => {
    render(<PageImageCanvas imageUrl="" encoded={null} />);
    const viewport = screen.getByTestId("image-viewport");
    expect(viewport.getAttribute("data-state")).toBe("empty");
    // No Stage / Layers / event-overlay in the empty branch.
    expect(screen.queryByTestId("canvas-stage")).toBeNull();
    expect(screen.queryByTestId("image-event-surface")).toBeNull();
  });

  it("mounts a Konva Stage sized to encoded.display_width × display_height (spec §4)", () => {
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    // image-stage sidecar mirrors geometry (spec §12).
    const stageSidecar = screen.getByTestId("image-stage");
    expect(stageSidecar.getAttribute("data-width")).toBe("800");
    expect(stageSidecar.getAttribute("data-height")).toBe("600");
    // pdomain-ui's outer image-viewport div also carries data-width / data-height.
    const viewport = screen.getByTestId("image-viewport");
    expect(viewport.getAttribute("data-width")).toBe("800");
    expect(viewport.getAttribute("data-height")).toBe("600");
  });

  it("renders the Konva layer skeleton via pdomain-ui (image / underlay / overlay / selection / tool / hud)", () => {
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    expect(screen.getByTestId("konva-layer-image")).not.toBeNull();
    expect(screen.getByTestId("konva-layer-underlay")).not.toBeNull();
    expect(screen.getByTestId("konva-layer-overlay")).not.toBeNull();
    expect(screen.getByTestId("konva-layer-selection")).not.toBeNull();
    expect(screen.getByTestId("konva-layer-tool")).not.toBeNull();
    expect(screen.getByTestId("konva-layer-hud")).not.toBeNull();
  });

  it("image layer has listening=false (perf pinning)", () => {
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    const imageLayer = screen.getByTestId("konva-layer-image");
    expect(imageLayer.getAttribute("data-listening")).toBe("false");
  });

  it("selection layer has listening=false (perf pinning)", () => {
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    const selLayer = screen.getByTestId("konva-layer-selection");
    expect(selLayer.getAttribute("data-listening")).toBe("false");
  });
});

// ── Existing dimensions assertion (kept) ─────────────────────────────────────

describe("PageImageCanvas — dimensions", () => {
  it("Stage dimensions == encoded.display_width × display_height", () => {
    const testCases = [
      {
        encoded: {
          src_width: 1600,
          src_height: 1200,
          display_width: 800,
          display_height: 600,
          scale: 0.5,
        },
      },
      {
        encoded: {
          src_width: 2400,
          src_height: 3200,
          display_width: 1200,
          display_height: 1600,
          scale: 0.5,
        },
      },
    ];

    for (const { encoded } of testCases) {
      const dims = getStageDimensions(encoded);
      expect(dims.width).toBe(encoded.display_width);
      expect(dims.height).toBe(encoded.display_height);
    }
  });

  it("renders image-viewport with correct dimensions attributes (pdomain-ui outer div)", () => {
    const { getByTestId } = render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    const viewport = getByTestId("image-viewport");
    expect(viewport.getAttribute("data-width")).toBe("800");
    expect(viewport.getAttribute("data-height")).toBe("600");
  });
});

// ── Drag-mode behavior (pdomain-ui onStagePointer* callbacks) ─────────────────
//
// Drag is driven through the mocked canvas's image-event-surface (which forwards
// to onStagePointerDown/Move/Up), not a DOM event-capture overlay.

describe("PageImageCanvas — Select mode (drag box-select, #197, #302)", () => {
  it("shows no drag-rect initially", () => {
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    expect(screen.queryByTestId("ocr-drag-rect")).toBeNull();
  });

  it("drag-rect appears during mouse drag", () => {
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    const overlay = getOverlay();

    fireEvent.mouseDown(overlay, { clientX: 100, clientY: 100 });
    fireEvent.mouseMove(overlay, { clientX: 200, clientY: 200 });

    expect(screen.queryByTestId("ocr-drag-rect")).not.toBeNull();
  });

  it("drag-rect disappears after mouseup", () => {
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    simulateDrag({ x: 100, y: 100 }, { x: 200, y: 200 });
    expect(screen.queryByTestId("ocr-drag-rect")).toBeNull();
  });

  it("calls onBoxSelect with rect and 'replace' modifier on plain drag", () => {
    const onBoxSelect = vi.fn();
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} onBoxSelect={onBoxSelect} />);
    simulateDrag({ x: 50, y: 50 }, { x: 150, y: 120 });

    expect(onBoxSelect).toHaveBeenCalledOnce();
    const [rect, modifier] = onBoxSelect.mock.calls[0];
    expect(modifier).toBe("replace");
    expect(rect.width).toBeGreaterThan(2);
  });

  it("calls onBoxSelect with 'remove' modifier when Shift held (modifier captured at mousedown per spec §7)", () => {
    const onBoxSelect = vi.fn();
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} onBoxSelect={onBoxSelect} />);
    simulateDrag({ x: 50, y: 50 }, { x: 150, y: 120 }, { shiftKey: true });

    expect(onBoxSelect.mock.calls[0][1]).toBe("remove");
  });

  it("calls onBoxSelect with 'toggle' modifier when Ctrl held", () => {
    const onBoxSelect = vi.fn();
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} onBoxSelect={onBoxSelect} />);
    simulateDrag({ x: 50, y: 50 }, { x: 150, y: 120 }, { ctrlKey: true });

    expect(onBoxSelect.mock.calls[0][1]).toBe("toggle");
  });

  it("does NOT call onBoxSelect for tiny drag (≤2px)", () => {
    const onBoxSelect = vi.fn();
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} onBoxSelect={onBoxSelect} />);
    simulateDrag({ x: 100, y: 100 }, { x: 101, y: 101 });

    expect(onBoxSelect).not.toHaveBeenCalled();
  });

  it("data-mode attribute is 'select' by default on image-stage", () => {
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    expect(screen.getByTestId("image-stage").getAttribute("data-mode")).toBe("select");
  });

  it("Escape key clears drag state", () => {
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    const overlay = getOverlay();

    fireEvent.mouseDown(overlay, { clientX: 50, clientY: 50 });
    fireEvent.mouseMove(overlay, { clientX: 150, clientY: 150 });
    expect(screen.queryByTestId("ocr-drag-rect")).not.toBeNull();

    // Keyboard handling is at document scope via useViewportHotkeys.
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByTestId("ocr-drag-rect")).toBeNull();
  });
});

// ── drag-preview Rect + sidecar ──────────────────────────────────────────────

describe("PageImageCanvas — drag-preview Rect + sidecar", () => {
  it("wrapper has cursor: crosshair in select mode (spec §9)", () => {
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    const wrapper = screen.getByTestId("image-canvas-wrapper");
    expect(wrapper.style.cursor).toBe("crosshair");
  });

  it("ocr-drag-rect sidecar mirrors the Konva drag-preview rect position", () => {
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    const overlay = getOverlay();
    fireEvent.mouseDown(overlay, { clientX: 30, clientY: 40 });
    fireEvent.mouseMove(overlay, { clientX: 130, clientY: 110 });

    const sidecar = screen.getByTestId("ocr-drag-rect");
    expect(sidecar.style.left).toBe("30px");
    expect(sidecar.style.top).toBe("40px");
    expect(sidecar.style.width).toBe("100px");
    expect(sidecar.style.height).toBe("70px");
  });

  it("drag-preview Konva Rect renders in the tool Layer with spec §9 stroke + dashed pattern", () => {
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    const overlay = getOverlay();
    fireEvent.mouseDown(overlay, { clientX: 30, clientY: 40 });
    fireEvent.mouseMove(overlay, { clientX: 130, clientY: 110 });

    const toolLayer = screen.getByTestId("konva-layer-tool");
    const dragPreview = toolLayer.querySelector('[data-testid="konva-drag-preview"]');
    expect(dragPreview).not.toBeNull();
    expect(dragPreview?.getAttribute("data-stroke")).toBe("#5d9fdf"); // spec §9 --status-ocr fallback
    expect(dragPreview?.getAttribute("data-dash")).toBe("4,2"); // spec §9
    expect(dragPreview?.getAttribute("data-x")).toBe("30");
    expect(dragPreview?.getAttribute("data-y")).toBe("40");
    expect(dragPreview?.getAttribute("data-width")).toBe("100");
    expect(dragPreview?.getAttribute("data-height")).toBe("70");
  });
});

// ── spec-21-A7 (#303): per-mode cursors + drag-preview colours/fill ─────────

describe("PageImageCanvas — per-mode cursors (spec-21-A7, #303, spec §9)", () => {
  it("cursor is 'cell' in rebox mode", () => {
    viewportStore.setState({ mode: "rebox", pendingReboxTarget: null });
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    expect(screen.getByTestId("image-canvas-wrapper").style.cursor).toBe("cell");
  });

  it("cursor is 'copy' in add-word mode", () => {
    viewportStore.setState({ mode: "add-word", pendingReboxTarget: null });
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    expect(screen.getByTestId("image-canvas-wrapper").style.cursor).toBe("copy");
  });

  it("cursor is 'not-allowed' in erase mode", () => {
    viewportStore.setState({ mode: "erase", pendingReboxTarget: null });
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    expect(screen.getByTestId("image-canvas-wrapper").style.cursor).toBe("not-allowed");
  });
});

describe("PageImageCanvas — per-mode drag-preview stroke (spec-21-A7, #303, spec §9, CSS token fallbacks)", () => {
  function dragPreviewStroke(mode: "rebox" | "add-word" | "erase"): string | null {
    viewportStore.setState({ mode, pendingReboxTarget: null });
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    const overlay = getOverlay();
    fireEvent.mouseDown(overlay, { clientX: 30, clientY: 40 });
    fireEvent.mouseMove(overlay, { clientX: 130, clientY: 110 });
    const toolLayer = screen.getByTestId("konva-layer-tool");
    return (
      toolLayer.querySelector('[data-testid="konva-drag-preview"]')?.getAttribute("data-stroke") ??
      null
    );
  }

  it("rebox stroke is --status-exact fallback (#5fbf6a)", () => {
    expect(dragPreviewStroke("rebox")).toBe("#5fbf6a");
  });

  it("add-word stroke is --status-gt fallback (#a888d4)", () => {
    expect(dragPreviewStroke("add-word")).toBe("#a888d4");
  });

  it("erase stroke is --status-mismatch fallback (#dc6555)", () => {
    expect(dragPreviewStroke("erase")).toBe("#dc6555");
  });
});

describe("PageImageCanvas — erase drag-preview fill (spec-21-A7, #303, spec §9, CSS token fallbacks)", () => {
  it("erase mode drag-preview Rect has --status-mismatch fallback fill", () => {
    viewportStore.setState({ mode: "erase", pendingReboxTarget: null });
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    const overlay = getOverlay();
    fireEvent.mouseDown(overlay, { clientX: 30, clientY: 40 });
    fireEvent.mouseMove(overlay, { clientX: 130, clientY: 110 });

    const toolLayer = screen.getByTestId("konva-layer-tool");
    const dragPreview = toolLayer.querySelector('[data-testid="konva-drag-preview"]');
    expect(dragPreview?.getAttribute("data-fill")).toBe("rgba(220,101,85,0.2)"); // hexToRgba("#dc6555", 0.20)
  });

  it("non-erase modes have no fill on the drag-preview Rect", () => {
    for (const mode of ["select", "rebox", "add-word"] as const) {
      viewportStore.setState({ mode, pendingReboxTarget: null });
      const { unmount } = render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
      const overlay = getOverlay();
      fireEvent.mouseDown(overlay, { clientX: 30, clientY: 40 });
      fireEvent.mouseMove(overlay, { clientX: 130, clientY: 110 });

      const toolLayer = screen.getByTestId("konva-layer-tool");
      const dragPreview = toolLayer.querySelector('[data-testid="konva-drag-preview"]');
      expect(dragPreview?.getAttribute("data-fill")).toBeNull();
      unmount();
    }
  });
});

describe("PageImageCanvas — Rebox mode (#198)", () => {
  it("data-mode='rebox' when rebox mode active (on image-stage)", () => {
    viewportStore.setState({ mode: "rebox", pendingReboxTarget: { lineIndex: 0, wordIndex: 0 } });
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    expect(screen.getByTestId("image-stage").getAttribute("data-mode")).toBe("rebox");
  });

  it("calls onRebox with drag rect", () => {
    const onRebox = vi.fn();
    viewportStore.setState({ mode: "rebox", pendingReboxTarget: { lineIndex: 0, wordIndex: 0 } });
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} onRebox={onRebox} />);
    simulateDrag({ x: 50, y: 50 }, { x: 150, y: 120 });

    expect(onRebox).toHaveBeenCalledOnce();
    const rect = onRebox.mock.calls[0][0];
    expect(rect.width).toBeGreaterThan(2);
  });

  it("mode resets to select after rebox completes", () => {
    const onRebox = vi.fn();
    viewportStore.setState({ mode: "rebox", pendingReboxTarget: { lineIndex: 0, wordIndex: 0 } });
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} onRebox={onRebox} />);
    simulateDrag({ x: 50, y: 50 }, { x: 150, y: 120 });

    expect(viewportStore.getState().mode).toBe("select");
  });

  it("does NOT call onBoxSelect during rebox mode", () => {
    const onBoxSelect = vi.fn();
    viewportStore.setState({ mode: "rebox", pendingReboxTarget: null });
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} onBoxSelect={onBoxSelect} />);
    simulateDrag({ x: 50, y: 50 }, { x: 150, y: 120 });

    expect(onBoxSelect).not.toHaveBeenCalled();
  });
});

describe("PageImageCanvas — Add Word mode (#198)", () => {
  it("data-mode='add-word' when add-word mode active (on image-stage)", () => {
    viewportStore.setState({ mode: "add-word", pendingReboxTarget: null });
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    expect(screen.getByTestId("image-stage").getAttribute("data-mode")).toBe("add-word");
  });

  it("calls onAddWord with drag rect", () => {
    const onAddWord = vi.fn();
    viewportStore.setState({ mode: "add-word", pendingReboxTarget: null });
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} onAddWord={onAddWord} />);
    simulateDrag({ x: 50, y: 50 }, { x: 150, y: 120 });

    expect(onAddWord).toHaveBeenCalledOnce();
  });

  it("mode stays add-word after add-word completes (multi-add)", () => {
    const onAddWord = vi.fn();
    viewportStore.setState({ mode: "add-word", pendingReboxTarget: null });
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} onAddWord={onAddWord} />);
    simulateDrag({ x: 50, y: 50 }, { x: 150, y: 120 });

    expect(viewportStore.getState().mode).toBe("add-word");
  });
});

// ── spec-21-A8 (#304): focus wrapper + viewport hotkeys ─────────────────────
//
// Phase 2.2: pdomain-ui's PageImageCanvas renders its outer div with tabIndex=0
// and calls focus() on it via a useEffect. The outer div carries
// data-testid="image-viewport". These behaviours remain intact.

describe("PageImageCanvas — focus wrapper (spec-21-A8, #304, spec §10)", () => {
  it("image-viewport div has tabIndex=0 (pdomain-ui renders this)", () => {
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    const viewport = screen.getByTestId("image-viewport");
    expect(viewport.getAttribute("tabindex")).toBe("0");
  });

  it("image-viewport is focused on mount (pdomain-ui calls focus() in effect)", () => {
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    const viewport = screen.getByTestId("image-viewport");
    expect(document.activeElement).toBe(viewport);
  });
});

describe("PageImageCanvas — viewport hotkeys (spec-21-A8, #304, spec §10)", () => {
  it("Esc clears drag state (acceptance criterion)", () => {
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    const overlay = getOverlay();

    fireEvent.mouseDown(overlay, { clientX: 50, clientY: 50 });
    fireEvent.mouseMove(overlay, { clientX: 150, clientY: 150 });
    expect(screen.queryByTestId("ocr-drag-rect")).not.toBeNull();

    // Document-scope Esc (the hook listens at document scope per #237).
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByTestId("ocr-drag-rect")).toBeNull();
  });

  it("Shift+1 sets selectionMode to 'paragraph' (acceptance criterion)", () => {
    useUiPrefs.setState({ selectionMode: "word" });
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);

    fireEvent.keyDown(document, { key: "!", code: "Digit1", shiftKey: true });
    expect(useUiPrefs.getState().selectionMode).toBe("paragraph");
  });

  it("Shift+2 sets selectionMode to 'line'", () => {
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    fireEvent.keyDown(document, { key: "@", code: "Digit2", shiftKey: true });
    expect(useUiPrefs.getState().selectionMode).toBe("line");
  });

  it("Shift+3 sets selectionMode to 'word'", () => {
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    fireEvent.keyDown(document, { key: "#", code: "Digit3", shiftKey: true });
    expect(useUiPrefs.getState().selectionMode).toBe("word");
  });

  it("Shift+W toggles layerVisibility.word (acceptance criterion)", () => {
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    expect(useUiPrefs.getState().layerVisibility.word).toBe(true);

    fireEvent.keyDown(document, { key: "W", shiftKey: true });
    expect(useUiPrefs.getState().layerVisibility.word).toBe(false);
  });

  it("Shift+P toggles layerVisibility.paragraph", () => {
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    expect(useUiPrefs.getState().layerVisibility.paragraph).toBe(true);

    fireEvent.keyDown(document, { key: "P", shiftKey: true });
    expect(useUiPrefs.getState().layerVisibility.paragraph).toBe(false);
  });

  it("Shift+L toggles layerVisibility.line", () => {
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    expect(useUiPrefs.getState().layerVisibility.line).toBe(true);

    fireEvent.keyDown(document, { key: "L", shiftKey: true });
    expect(useUiPrefs.getState().layerVisibility.line).toBe(false);
  });

  it("Shift+E toggles erase mode via viewportStore", () => {
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    expect(viewportStore.getState().mode).toBe("select");

    fireEvent.keyDown(document, { key: "E", shiftKey: true });
    expect(viewportStore.getState().mode).toBe("erase");
  });

  it("Shift+A toggles add-word mode via viewportStore", () => {
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    expect(viewportStore.getState().mode).toBe("select");

    fireEvent.keyDown(document, { key: "A", shiftKey: true });
    expect(viewportStore.getState().mode).toBe("add-word");
  });
});

// ── spec-21-A5 (#300): selection layer rendering ────────────────────────────
//
// Phase 2.2: Word overlay + selection BBoxOverlays render inside the `selection`
// slot, which pdomain-ui wraps in konva-layer-selection. Overlay-paragraphs/lines/words
// are gone as separate layers; their content merges into konva-layer-selection.

describe("PageImageCanvas — selection layer rendering (spec-21-A5, #300)", () => {
  it("renders selection BBoxOverlay sidecars inside konva-layer-selection with count=0 when page is null", () => {
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} page={null} />);
    const selectionLayer = screen.getByTestId("konva-layer-selection");
    const paragraphs = selectionLayer.querySelector(
      '[data-testid="bbox-overlay-selection-paragraphs"]',
    );
    const lines = selectionLayer.querySelector('[data-testid="bbox-overlay-selection-lines"]');
    const words = selectionLayer.querySelector('[data-testid="bbox-overlay-selection-words"]');
    expect(paragraphs).not.toBeNull();
    expect(lines).not.toBeNull();
    expect(words).not.toBeNull();
    expect(paragraphs?.getAttribute("data-item-count")).toBe("0");
    expect(lines?.getAttribute("data-item-count")).toBe("0");
    expect(words?.getAttribute("data-item-count")).toBe("0");
  });

  it("renders three BBoxOverlay sidecars when page has no selection", () => {
    const page = makePage([makeLine(0, 0, [{ x: 10, y: 20, width: 30, height: 5 }])], undefined);
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} page={page} />);
    expect(
      screen.getByTestId("bbox-overlay-selection-paragraphs").getAttribute("data-item-count"),
    ).toBe("0");
    expect(screen.getByTestId("bbox-overlay-selection-lines").getAttribute("data-item-count")).toBe(
      "0",
    );
    expect(screen.getByTestId("bbox-overlay-selection-words").getAttribute("data-item-count")).toBe(
      "0",
    );
  });

  it("renders all layer overlay bboxes from the page by default", () => {
    const first = makeLine(0, 0, [
      { x: 10, y: 20, width: 30, height: 5 },
      { x: 45, y: 21, width: 20, height: 4 },
    ]);
    first.block_index = 0;
    const second = makeLine(1, 1, [{ x: 100, y: 60, width: 50, height: 10 }]);
    second.block_index = 1;
    const page = makePage([first, second], undefined);

    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} page={page} />);

    expect(screen.getByTestId("bbox-overlay-blocks").getAttribute("data-item-count")).toBe("2");
    expect(screen.getByTestId("bbox-overlay-paragraphs").getAttribute("data-item-count")).toBe("2");
    expect(screen.getByTestId("bbox-overlay-lines").getAttribute("data-item-count")).toBe("2");
    expect(screen.getByTestId("bbox-overlay-words").getAttribute("data-item-count")).toBe("3");

    const firstBlock = screen.getByTestId("rect-overlay-blocks-0");
    expect(firstBlock).toHaveAttribute("data-x", "5");
    expect(firstBlock).toHaveAttribute("data-y", "10");
    expect(firstBlock).toHaveAttribute("data-width", "27.5");
    expect(firstBlock).toHaveAttribute("data-height", "2.5");
  });

  it("layer visibility hides overlays independently of the active rail target", () => {
    const first = makeLine(0, 0, [
      { x: 10, y: 20, width: 30, height: 5 },
      { x: 45, y: 21, width: 20, height: 4 },
    ]);
    first.block_index = 0;
    const page = makePage([first], undefined);

    railStore.getState().setTarget("line");
    useUiPrefs.setState((state) => ({
      layerVisibility: {
        ...state.layerVisibility,
        line: false,
      },
    }));
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} page={page} />);

    expect(screen.getByTestId("bbox-overlay-blocks").getAttribute("data-item-count")).toBe("1");
    expect(screen.getByTestId("bbox-overlay-paragraphs").getAttribute("data-item-count")).toBe("1");
    expect(screen.queryByTestId("bbox-overlay-lines")).toBeNull();
    expect(screen.getByTestId("bbox-overlay-words").getAttribute("data-item-count")).toBe("2");
  });

  it("selected line populates bbox-overlay-selection-lines with item-count=1 and a Rect with stroke width 3 (acceptance criterion)", () => {
    const page = makePage(
      [
        makeLine(0, 0, [
          { x: 10, y: 20, width: 30, height: 5 },
          { x: 45, y: 20, width: 20, height: 5 },
        ]),
      ],
      {
        selection_mode: "line",
        selected_paragraphs: [],
        selected_lines: [0],
        selected_words: [],
      },
    );
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} page={page} />);

    const sidecar = screen.getByTestId("bbox-overlay-selection-lines");
    expect(sidecar.getAttribute("data-item-count")).toBe("1");

    const selectionLayer = screen.getByTestId("konva-layer-selection");
    const rects = selectionLayer.querySelectorAll('[data-testid^="rect-overlay-selection-lines-"]');
    // One selection-lines rect (the selected line bbox)
    const selectionRects = Array.from(rects).filter(
      (r) => r.getAttribute("data-stroke-width") === String(SELECTION_STROKE_WIDTH),
    );
    expect(selectionRects.length).toBeGreaterThanOrEqual(1);
  });

  it("selected word populates bbox-overlay-selection-words with item-count=1", () => {
    const page = makePage([makeLine(0, 0, [{ x: 10, y: 20, width: 30, height: 5 }])], {
      selection_mode: "word",
      selected_paragraphs: [],
      selected_lines: [],
      selected_words: [[0, 0]],
    });
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} page={page} />);
    expect(screen.getByTestId("bbox-overlay-selection-words").getAttribute("data-item-count")).toBe(
      "1",
    );
  });

  it("selected paragraph populates bbox-overlay-selection-paragraphs with item-count=1", () => {
    const page = makePage([makeLine(0, 0, [{ x: 10, y: 20, width: 30, height: 5 }])], {
      selection_mode: "paragraph",
      selected_paragraphs: [0],
      selected_lines: [],
      selected_words: [],
    });
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} page={page} />);
    expect(
      screen.getByTestId("bbox-overlay-selection-paragraphs").getAttribute("data-item-count"),
    ).toBe("1");
  });
});

// ── Target click → selection action (canvas entry point wiring) ─────────────

describe("PageImageCanvas — target bbox click → selection action", () => {
  it("scales source-image word bboxes into display space for hit-testing", () => {
    const page = makePage([makeLine(2, 0, [{ x: 100, y: 200, width: 50, height: 20 }])]);
    page.line_matches![0].word_matches[0].word_index = 3;

    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} page={page} />);
    const overlay = getOverlay();

    // encoded.scale=0.5, so source bbox 100..150 × 200..220 renders at
    // display bbox 50..75 × 100..110.
    fireEvent.mouseDown(overlay, { clientX: 62.5, clientY: 105 });
    fireEvent.mouseUp(overlay, { clientX: 62.5, clientY: 105 });

    const sel = selectionStore.getState();
    expect(sel.level).toBe("word");
    expect(sel.selectedWords).toEqual([[2, 3]]);
  });

  it("clicking within a word bbox in select mode calls selectWord(lineIdx, wordIdx)", () => {
    const page = makePage([makeLine(2, 0, [{ x: 100, y: 200, width: 50, height: 20 }])]);
    page.line_matches![0].word_matches[0].word_index = 3;

    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} page={page} />);
    const overlay = getOverlay();
    const point = sourceToDisplayPoint(125, 210);

    // Click inside the source bbox (125, 210), projected to display space.
    fireEvent.mouseDown(overlay, { clientX: point.x, clientY: point.y });
    fireEvent.mouseUp(overlay, { clientX: point.x, clientY: point.y });

    const sel = selectionStore.getState();
    expect(sel.level).toBe("word");
    expect(sel.selectedWords).toEqual([[2, 3]]);
  });

  it("clicking with line target selects the hit line", () => {
    const page = makePage([
      makeLine(7, 0, [
        { x: 100, y: 200, width: 50, height: 20 },
        { x: 160, y: 200, width: 40, height: 20 },
      ]),
    ]);
    railStore.getState().setTarget("line");

    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} page={page} />);
    const overlay = getOverlay();
    const point = sourceToDisplayPoint(125, 210);

    fireEvent.mouseDown(overlay, { clientX: point.x, clientY: point.y });
    fireEvent.mouseUp(overlay, { clientX: point.x, clientY: point.y });

    const sel = selectionStore.getState();
    expect(sel.level).toBe("line");
    expect(sel.selectedLines).toEqual([7]);
  });

  it("clicking with paragraph target selects the hit paragraph", () => {
    const page = makePage([makeLine(2, 4, [{ x: 100, y: 200, width: 50, height: 20 }])]);
    railStore.getState().setTarget("para");

    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} page={page} />);
    const overlay = getOverlay();
    const point = sourceToDisplayPoint(125, 210);

    fireEvent.mouseDown(overlay, { clientX: point.x, clientY: point.y });
    fireEvent.mouseUp(overlay, { clientX: point.x, clientY: point.y });

    const sel = selectionStore.getState();
    expect(sel.level).toBe("para");
    expect(sel.selectedParagraphs).toEqual([4]);
  });

  it("clicking with block target selects the hit block", () => {
    const line = makeLine(2, 0, [{ x: 100, y: 200, width: 50, height: 20 }]);
    line.block_index = 9;
    const page = makePage([line]);
    railStore.getState().setTarget("block");

    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} page={page} />);
    const overlay = getOverlay();
    const point = sourceToDisplayPoint(125, 210);

    fireEvent.mouseDown(overlay, { clientX: point.x, clientY: point.y });
    fireEvent.mouseUp(overlay, { clientX: point.x, clientY: point.y });

    const sel = selectionStore.getState();
    expect(sel.level).toBe("block");
    expect(sel.path.blockId).toBe("9");
  });

  it("clicking within a word bbox opens the right panel (rightPanelOpen=true)", () => {
    const page = makePage([makeLine(0, 0, [{ x: 10, y: 10, width: 40, height: 15 }])]);
    useUiPrefs.setState({ rightPanelOpen: false });

    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} page={page} />);
    const overlay = getOverlay();
    const point = sourceToDisplayPoint(25, 15);

    fireEvent.mouseDown(overlay, { clientX: point.x, clientY: point.y });
    fireEvent.mouseUp(overlay, { clientX: point.x, clientY: point.y });

    expect(useUiPrefs.getState().rightPanelOpen).toBe(true);
  });

  it("clicking outside all word bboxes does NOT call selectWord", () => {
    const page = makePage([makeLine(0, 0, [{ x: 100, y: 100, width: 50, height: 20 }])]);

    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} page={page} />);
    const overlay = getOverlay();

    fireEvent.mouseDown(overlay, { clientX: 400, clientY: 400 });
    fireEvent.mouseUp(overlay, { clientX: 400, clientY: 400 });

    const sel = selectionStore.getState();
    expect(sel.level).toBe("none");
    expect(sel.selectedWords).toEqual([]);
  });

  it("a real drag (>2px) does NOT trigger word selection even if it ends inside a bbox", () => {
    const page = makePage([makeLine(0, 0, [{ x: 50, y: 50, width: 100, height: 30 }])]);

    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} page={page} />);

    simulateDrag({ x: 50, y: 50 }, { x: 150, y: 80 });

    const sel = selectionStore.getState();
    expect(sel.level).toBe("none");
    expect(sel.selectedWords).toEqual([]);
  });

  it("word click in rebox mode does NOT trigger word selection (only select mode responds)", () => {
    const page = makePage([makeLine(0, 0, [{ x: 10, y: 10, width: 40, height: 15 }])]);
    viewportStore.setState({ mode: "rebox", pendingReboxTarget: null });

    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} page={page} />);
    const overlay = getOverlay();
    const point = sourceToDisplayPoint(25, 15);

    fireEvent.mouseDown(overlay, { clientX: point.x, clientY: point.y });
    fireEvent.mouseUp(overlay, { clientX: point.x, clientY: point.y });

    const sel = selectionStore.getState();
    expect(sel.level).toBe("none");
  });

  // ── Scale-aware hit-testing (regression for #bbox-click-selection) ──────────
  //
  // The previous DOM event-capture overlay computed its OWN effectiveScale and
  // divided (clientX - rect.left) by it. Under jsdom that rect was zero-size, so
  // scale fell back to 1 and the tests passed without ever exercising the
  // divide — masking the production bug where the overlay's scale disagreed with
  // pdomain-ui's internal scale and clicks missed the bbox.
  //
  // These tests force ctx.scale != 1, so a hit is only registered if the
  // component divides the (scaled) Konva pointer position by ctx.scale. They
  // would FAIL against the old overlay (which ignored pdomain-ui's scale).

  it("hit-tests in page space: a 2x-scaled pointer maps back through ctx.scale onto the word bbox", () => {
    mockStageScale.value = 2;
    const page = makePage([makeLine(2, 0, [{ x: 100, y: 200, width: 50, height: 20 }])]);
    page.line_matches![0].word_matches[0].word_index = 3;

    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} page={page} />);
    const overlay = getOverlay();
    const displayPoint = sourceToDisplayPoint(125, 210);

    // Stage-space pointer ÷ scale 2 = display-space point inside the word bbox.
    fireEvent.mouseDown(overlay, { clientX: displayPoint.x * 2, clientY: displayPoint.y * 2 });
    fireEvent.mouseUp(overlay, { clientX: displayPoint.x * 2, clientY: displayPoint.y * 2 });

    const sel = selectionStore.getState();
    expect(sel.level).toBe("word");
    expect(sel.selectedWords).toEqual([[2, 3]]);
  });

  it("does NOT hit when the raw (un-divided) stage pointer would fall inside the bbox", () => {
    // Guard against a regression that forgets the ÷ ctx.scale: the raw pointer
    // lands in the display bbox, but the page-space coord at scale 2 is outside.
    mockStageScale.value = 2;
    const page = makePage([makeLine(2, 0, [{ x: 100, y: 200, width: 50, height: 20 }])]);
    page.line_matches![0].word_matches[0].word_index = 3;

    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} page={page} />);
    const overlay = getOverlay();
    const displayPoint = sourceToDisplayPoint(125, 210);

    fireEvent.mouseDown(overlay, { clientX: displayPoint.x, clientY: displayPoint.y });
    fireEvent.mouseUp(overlay, { clientX: displayPoint.x, clientY: displayPoint.y });

    const sel = selectionStore.getState();
    expect(sel.level).toBe("none");
    expect(sel.selectedWords).toEqual([]);
  });
});

describe("PageImageCanvas — Erase mode (#198)", () => {
  it("data-mode='erase' when erase mode active (on image-stage)", () => {
    viewportStore.setState({ mode: "erase", pendingReboxTarget: null });
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    expect(screen.getByTestId("image-stage").getAttribute("data-mode")).toBe("erase");
  });

  it("calls onErasePixels with drag rect", () => {
    const onErasePixels = vi.fn();
    viewportStore.setState({ mode: "erase", pendingReboxTarget: null });
    render(
      <PageImageCanvas imageUrl="/test.jpg" encoded={encoded} onErasePixels={onErasePixels} />,
    );
    simulateDrag({ x: 50, y: 50 }, { x: 150, y: 120 });

    expect(onErasePixels).toHaveBeenCalledOnce();
  });

  it("mode resets to select after erase completes", () => {
    const onErasePixels = vi.fn();
    viewportStore.setState({ mode: "erase", pendingReboxTarget: null });
    render(
      <PageImageCanvas imageUrl="/test.jpg" encoded={encoded} onErasePixels={onErasePixels} />,
    );
    simulateDrag({ x: 50, y: 50 }, { x: 150, y: 120 });

    expect(viewportStore.getState().mode).toBe("select");
  });
});

// ── Rail mode → viewport interaction mode sync ──────────────────────────────

describe("rail mode → viewport sync", () => {
  afterEach(() => {
    railStore.reset();
  });

  it("setting rail mode to erase activates viewportStore erase mode", () => {
    render(<PageImageCanvas imageUrl="/img.png" encoded={null} />);
    act(() => railStore.getState().setMode("erase"));
    expect(viewportStore.getState().mode).toBe("erase");
  });

  it("setting rail mode to annotate activates add-word mode", () => {
    render(<PageImageCanvas imageUrl="/img.png" encoded={null} />);
    act(() => railStore.getState().setMode("annotate"));
    expect(viewportStore.getState().mode).toBe("add-word");
  });

  it("setting rail mode back to view resets to select", () => {
    render(<PageImageCanvas imageUrl="/img.png" encoded={null} />);
    act(() => railStore.getState().setMode("erase"));
    act(() => railStore.getState().setMode("view"));
    expect(viewportStore.getState().mode).toBe("select");
  });
});

// ── Zoom controls (P5.d) ────────────────────────────────────────────────────

describe("PageImageCanvas — zoom controls (P5.d)", () => {
  it("renders canvas-zoom-controls, canvas-zoom-fit and canvas-zoom-100 buttons", () => {
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    expect(screen.getByTestId("canvas-zoom-controls")).toBeInTheDocument();
    expect(screen.getByTestId("canvas-zoom-fit")).toBeInTheDocument();
    expect(screen.getByTestId("canvas-zoom-100")).toBeInTheDocument();
  });

  it("positions zoom controls as a top-left canvas overlay", () => {
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    const controls = screen.getByTestId("canvas-zoom-controls");
    expect(controls.className).toMatch(/\btop-2\b/);
    expect(controls.className).toMatch(/\bleft-2\b/);
    expect(controls.className).not.toMatch(/\bbottom-2\b/);
  });

  it("100% button is initially active (aria-pressed=true) and Fit is inactive", () => {
    viewportStore.setState({ canvasZoom: 1.0 });
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    expect(screen.getByTestId("canvas-zoom-100").getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByTestId("canvas-zoom-fit").getAttribute("aria-pressed")).toBe("false");
  });

  it("clicking Fit sets canvasZoom to 0 in viewportStore and marks Fit as active", () => {
    viewportStore.setState({ canvasZoom: 1.0 });
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    fireEvent.click(screen.getByTestId("canvas-zoom-fit"));
    expect(viewportStore.getState().canvasZoom).toBe(0);
    expect(screen.getByTestId("canvas-zoom-fit").getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByTestId("canvas-zoom-100").getAttribute("aria-pressed")).toBe("false");
  });

  it("clicking 100% sets canvasZoom to 1.0 in viewportStore and marks 100% as active", () => {
    viewportStore.setState({ canvasZoom: 0 });
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    fireEvent.click(screen.getByTestId("canvas-zoom-100"));
    expect(viewportStore.getState().canvasZoom).toBe(1.0);
    expect(screen.getByTestId("canvas-zoom-100").getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByTestId("canvas-zoom-fit").getAttribute("aria-pressed")).toBe("false");
  });

  it("zoom controls are not rendered in empty-state viewport", () => {
    render(<PageImageCanvas imageUrl="" encoded={null} />);
    expect(screen.queryByTestId("canvas-zoom-controls")).toBeNull();
  });
});

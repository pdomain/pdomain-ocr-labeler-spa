// PageImageCanvas.test.tsx — viewport canvas tests (#196, #197, #198, #297, #302)
//
// Spec: specs/21-konva-renderer.md §4 (component layout), §7 (drag modes),
//       §9 (cursors), §12 (testids), §13 (empty state).
//
// spec-21-A6 (#302) — drag handlers now live on the Konva <Stage> instead
// of the wrapping viewport div. The mock Stage forwards onMouseDown/Move/Up
// to a real inner div, synthesizing a KonvaEventObject whose
// target.getStage().getPointerPosition() reflects the fireEvent clientX/Y
// relative to the Stage element, and whose .evt carries the modifier keys.
//
// spec-21-A2 (#297) earlier replaced the DOM-stub viewport with a real
// Konva <Stage> + 6-layer skeleton; #298 filled BBoxOverlay; #301 added the
// rafSchedule helper this slice consumes.

import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { getStageDimensions } from "../lib/canvas-utils";
import { viewportStore } from "../stores/viewport-store";
import { selectionStore } from "../stores/selection-store";
import { useUiPrefs } from "../stores/ui-prefs";
import { railStore } from "../stores/rail-store";

// ── use-image mock (used by PageImage) ───────────────────────────────────────
// Default state: image not yet loaded → PageImage renders the grey fallback Rect.
const mockUseImageState = vi.hoisted(() => ({
  image: undefined as HTMLImageElement | undefined,
  status: "loading",
}));

vi.mock("use-image", () => ({
  default: () => [mockUseImageState.image, mockUseImageState.status] as const,
}));

// ── react-konva mock — render simple divs so jsdom can probe the tree ────────
//
// Stage forwards onMouseDown / onMouseMove / onMouseUp / onMouseLeave from
// react-konva props onto an inner DOM div, synthesizing a Konva-style event
// object whose target.getStage().getPointerPosition() reflects the
// fireEvent clientX/clientY (jsdom getBoundingClientRect is all zeros, so
// clientX === stage-relative X for our purposes) and whose .evt carries
// the modifier keys.
type KonvaMouseHandler = (e: {
  evt: { shiftKey: boolean; ctrlKey: boolean; metaKey: boolean };
  target: { getStage: () => { getPointerPosition: () => { x: number; y: number } } };
}) => void;

function makeKonvaEvent(e: React.MouseEvent) {
  const pos = { x: e.clientX, y: e.clientY };
  return {
    evt: {
      shiftKey: !!e.shiftKey,
      ctrlKey: !!e.ctrlKey,
      metaKey: !!e.metaKey,
    },
    target: {
      getStage: () => ({ getPointerPosition: () => pos }),
    },
  };
}

vi.mock("react-konva", () => ({
  Stage: ({
    children,
    width,
    height,
    "data-testid": testId,
    onMouseDown,
    onMouseMove,
    onMouseUp,
    onMouseLeave,
  }: {
    children?: React.ReactNode;
    width?: number;
    height?: number;
    "data-testid"?: string;
    onMouseDown?: KonvaMouseHandler;
    onMouseMove?: KonvaMouseHandler;
    onMouseUp?: KonvaMouseHandler;
    onMouseLeave?: KonvaMouseHandler;
    [key: string]: unknown;
  }) => (
    <div
      data-testid={testId ?? "konva-stage"}
      data-width={width}
      data-height={height}
      onMouseDown={(e) => onMouseDown?.(makeKonvaEvent(e))}
      onMouseMove={(e) => onMouseMove?.(makeKonvaEvent(e))}
      onMouseUp={(e) => onMouseUp?.(makeKonvaEvent(e))}
      onMouseLeave={(e) => onMouseLeave?.(makeKonvaEvent(e))}
    >
      {children}
    </div>
  ),
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
// assert dragRect state immediately after mousemove (no rAF in jsdom).
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
    selection,
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
    layerVisibility: { paragraph: true, line: true, word: true },
    splitterRatio: 0.5,
    selectionMode: "paragraph",
    matchFilter: "unvalidated",
    rightPanelOpen: false,
  });
  mockUseImageState.image = undefined;
  mockUseImageState.status = "loading";
});

// Helper: simulate a drag (mousedown → mousemove → mouseup) on the Konva Stage.
// Pre-#302 the handlers were on the wrapping viewport div; per spec §7 they
// now live on the Stage, mocked here as `data-testid="konva-stage"`.
function getStage(): HTMLElement {
  return screen.getByTestId("konva-stage");
}

function simulateDrag(
  from: { x: number; y: number },
  to: { x: number; y: number },
  opts: { shiftKey?: boolean; ctrlKey?: boolean } = {},
) {
  const stage = getStage();
  fireEvent.mouseDown(stage, { clientX: from.x, clientY: from.y, ...opts });
  fireEvent.mouseMove(stage, { clientX: to.x, clientY: to.y, ...opts });
  fireEvent.mouseUp(stage, { clientX: to.x, clientY: to.y, ...opts });
}

// ── spec-21-A2 (#297): Stage scaffold ─────────────────────────────────────────

describe("PageImageCanvas — Konva Stage scaffold (spec-21-A2, #297)", () => {
  it("renders an empty-state viewport when encoded is null (spec §13)", () => {
    render(<PageImageCanvas imageUrl="" encoded={null} />);
    const viewport = screen.getByTestId("image-viewport");
    expect(viewport.getAttribute("data-state")).toBe("empty");
    // No Stage / Layers in the empty branch.
    expect(screen.queryByTestId("image-stage")).toBeNull();
    expect(screen.queryByTestId("konva-layer-image")).toBeNull();
  });

  it("mounts a Konva Stage sized to encoded.display_width × display_height (spec §4)", () => {
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    // The Stage itself is mocked as a div carrying data-width / data-height.
    // The wrapper div carries data-testid="image-stage" (spec §12 — Konva
    // nodes cannot themselves carry testids; the sidecar mirrors geometry).
    const stageSidecar = screen.getByTestId("image-stage");
    expect(stageSidecar.getAttribute("data-width")).toBe("800");
    expect(stageSidecar.getAttribute("data-height")).toBe("600");
  });

  it("renders the 6-layer skeleton from spec §4 (image / overlay-paragraphs / overlay-lines / overlay-words / selection / drag)", () => {
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    expect(screen.getByTestId("konva-layer-image")).not.toBeNull();
    expect(screen.getByTestId("konva-layer-overlay-paragraphs")).not.toBeNull();
    expect(screen.getByTestId("konva-layer-overlay-lines")).not.toBeNull();
    expect(screen.getByTestId("konva-layer-overlay-words")).not.toBeNull();
    expect(screen.getByTestId("konva-layer-selection")).not.toBeNull();
    expect(screen.getByTestId("konva-layer-drag")).not.toBeNull();
  });

  it("overlay layers have listening=false per spec §4 (perf pinning)", () => {
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    for (const name of ["overlay-paragraphs", "overlay-lines", "overlay-words", "selection"]) {
      const layer = screen.getByTestId(`konva-layer-${name}`);
      expect(layer.getAttribute("data-listening")).toBe("false");
    }
  });

  it("image layer has listening=false per spec §11 (perf pinning, #305)", () => {
    // spec §11: "Only the `drag` layer listens." Image layer carries the
    // page bitmap and never participates in hit-testing, so it must opt
    // out of Konva's per-node hit graph.
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    const imageLayer = screen.getByTestId("konva-layer-image");
    expect(imageLayer.getAttribute("data-listening")).toBe("false");
  });

  it("renders PageImage inside the image layer at the encoded display dimensions", () => {
    // use-image returns no image → PageImage renders the grey fallback Rect.
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    const imageLayer = screen.getByTestId("konva-layer-image");
    const fallback = imageLayer.querySelector('[data-testid="page-image-fallback"]');
    expect(fallback).not.toBeNull();
    expect(fallback?.getAttribute("data-width")).toBe("800");
    expect(fallback?.getAttribute("data-height")).toBe("600");
  });

  it("renders a loaded Konva Image when use-image resolves", () => {
    const img = { width: 1600, height: 1200 } as unknown as HTMLImageElement;
    mockUseImageState.image = img;
    mockUseImageState.status = "loaded";

    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    const pageImage = screen.getByTestId("page-image");
    expect(pageImage.getAttribute("data-has-image")).toBe("true");
    expect(pageImage.getAttribute("data-width")).toBe("800");
    expect(pageImage.getAttribute("data-height")).toBe("600");
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

  it("renders viewport wrapper with correct dimensions attributes", () => {
    const { getByTestId } = render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    const canvas = getByTestId("image-viewport");
    expect(canvas.getAttribute("data-width")).toBe("800");
    expect(canvas.getAttribute("data-height")).toBe("600");
  });
});

// ── Drag-mode behavior (DOM event handlers remain on viewport div) ──────────
// Konva handler migration is deferred to spec-21-C. Until then, drag input
// is captured by DOM mouse events on the wrapping viewport div, which is
// why these tests use fireEvent.mouseDown/Move/Up on the viewport.

describe("PageImageCanvas — Select mode (drag box-select, #197, #302)", () => {
  it("shows no drag-rect initially", () => {
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    expect(screen.queryByTestId("ocr-drag-rect")).toBeNull();
  });

  it("drag-rect appears during mouse drag", () => {
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    const stage = getStage();

    fireEvent.mouseDown(stage, { clientX: 100, clientY: 100 });
    fireEvent.mouseMove(stage, { clientX: 200, clientY: 200 });

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

  it("data-mode attribute is 'select' by default", () => {
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    expect(screen.getByTestId("image-viewport").getAttribute("data-mode")).toBe("select");
  });

  it("Escape key clears drag state", () => {
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    const stage = getStage();
    const viewport = screen.getByTestId("image-viewport");

    fireEvent.mouseDown(stage, { clientX: 50, clientY: 50 });
    fireEvent.mouseMove(stage, { clientX: 150, clientY: 150 });
    expect(screen.queryByTestId("ocr-drag-rect")).not.toBeNull();

    fireEvent.keyDown(viewport, { key: "Escape" });
    expect(screen.queryByTestId("ocr-drag-rect")).toBeNull();
  });
});

// ── spec-21-A6 (#302): Konva Stage drag handlers + drag-preview Rect ─────────

describe("PageImageCanvas — Konva Stage drag handlers (spec-21-A6, #302)", () => {
  it("wrapping viewport div has cursor: crosshair in select mode (spec §9)", () => {
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    const viewport = screen.getByTestId("image-viewport");
    expect(viewport.style.cursor).toBe("crosshair");
  });

  it("ocr-drag-rect sidecar mirrors the Konva drag-preview rect position", () => {
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    const stage = getStage();
    fireEvent.mouseDown(stage, { clientX: 30, clientY: 40 });
    fireEvent.mouseMove(stage, { clientX: 130, clientY: 110 });

    const sidecar = screen.getByTestId("ocr-drag-rect");
    expect(sidecar.style.left).toBe("30px");
    expect(sidecar.style.top).toBe("40px");
    expect(sidecar.style.width).toBe("100px");
    expect(sidecar.style.height).toBe("70px");
  });

  it("drag-preview Konva Rect renders in the drag Layer with spec §9 stroke + dashed pattern", () => {
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    const stage = getStage();
    fireEvent.mouseDown(stage, { clientX: 30, clientY: 40 });
    fireEvent.mouseMove(stage, { clientX: 130, clientY: 110 });

    const dragLayer = screen.getByTestId("konva-layer-drag");
    const dragPreview = dragLayer.querySelector('[data-testid="konva-drag-preview"]');
    expect(dragPreview).not.toBeNull();
    expect(dragPreview?.getAttribute("data-stroke")).toBe("#5d9fdf"); // spec §9 --status-ocr fallback
    expect(dragPreview?.getAttribute("data-dash")).toBe("4,2"); // spec §9
    expect(dragPreview?.getAttribute("data-x")).toBe("30");
    expect(dragPreview?.getAttribute("data-y")).toBe("40");
    expect(dragPreview?.getAttribute("data-width")).toBe("100");
    expect(dragPreview?.getAttribute("data-height")).toBe("70");
  });

  it("mouseleave on the Konva Stage clears drag state (spec §13)", () => {
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    const stage = getStage();
    fireEvent.mouseDown(stage, { clientX: 50, clientY: 50 });
    fireEvent.mouseMove(stage, { clientX: 150, clientY: 150 });
    expect(screen.queryByTestId("ocr-drag-rect")).not.toBeNull();

    fireEvent.mouseLeave(stage);
    expect(screen.queryByTestId("ocr-drag-rect")).toBeNull();
  });

  it("mouseleave on the Stage does NOT fire onBoxSelect (drag aborted)", () => {
    const onBoxSelect = vi.fn();
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} onBoxSelect={onBoxSelect} />);
    const stage = getStage();
    fireEvent.mouseDown(stage, { clientX: 50, clientY: 50 });
    fireEvent.mouseMove(stage, { clientX: 150, clientY: 150 });
    fireEvent.mouseLeave(stage);

    expect(onBoxSelect).not.toHaveBeenCalled();
  });
});

// ── spec-21-A7 (#303): per-mode cursors + drag-preview colours/fill ─────────

describe("PageImageCanvas — per-mode cursors (spec-21-A7, #303, spec §9)", () => {
  it("cursor is 'cell' in rebox mode", () => {
    viewportStore.setState({ mode: "rebox", pendingReboxTarget: null });
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    expect(screen.getByTestId("image-viewport").style.cursor).toBe("cell");
  });

  it("cursor is 'copy' in add-word mode", () => {
    viewportStore.setState({ mode: "add-word", pendingReboxTarget: null });
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    expect(screen.getByTestId("image-viewport").style.cursor).toBe("copy");
  });

  it("cursor is 'not-allowed' in erase mode", () => {
    viewportStore.setState({ mode: "erase", pendingReboxTarget: null });
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    expect(screen.getByTestId("image-viewport").style.cursor).toBe("not-allowed");
  });
});

describe("PageImageCanvas — per-mode drag-preview stroke (spec-21-A7, #303, spec §9, CSS token fallbacks)", () => {
  function dragPreviewStroke(mode: "rebox" | "add-word" | "erase"): string | null {
    viewportStore.setState({ mode, pendingReboxTarget: null });
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    const stage = getStage();
    fireEvent.mouseDown(stage, { clientX: 30, clientY: 40 });
    fireEvent.mouseMove(stage, { clientX: 130, clientY: 110 });
    const dragLayer = screen.getByTestId("konva-layer-drag");
    return (
      dragLayer.querySelector('[data-testid="konva-drag-preview"]')?.getAttribute("data-stroke") ??
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
    const stage = getStage();
    fireEvent.mouseDown(stage, { clientX: 30, clientY: 40 });
    fireEvent.mouseMove(stage, { clientX: 130, clientY: 110 });

    const dragLayer = screen.getByTestId("konva-layer-drag");
    const dragPreview = dragLayer.querySelector('[data-testid="konva-drag-preview"]');
    expect(dragPreview?.getAttribute("data-fill")).toBe("rgba(220,101,85,0.2)"); // hexToRgba("#dc6555", 0.20)
  });

  it("non-erase modes have no fill on the drag-preview Rect", () => {
    for (const mode of ["select", "rebox", "add-word"] as const) {
      viewportStore.setState({ mode, pendingReboxTarget: null });
      const { unmount } = render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
      const stage = getStage();
      fireEvent.mouseDown(stage, { clientX: 30, clientY: 40 });
      fireEvent.mouseMove(stage, { clientX: 130, clientY: 110 });

      const dragLayer = screen.getByTestId("konva-layer-drag");
      const dragPreview = dragLayer.querySelector('[data-testid="konva-drag-preview"]');
      // data-fill is undefined when no fill prop is set (rect mock omits the attr).
      expect(dragPreview?.getAttribute("data-fill")).toBeNull();
      unmount();
    }
  });
});

describe("PageImageCanvas — Rebox mode (#198)", () => {
  it("data-mode='rebox' when rebox mode active", () => {
    viewportStore.setState({ mode: "rebox", pendingReboxTarget: { lineIndex: 0, wordIndex: 0 } });
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    expect(screen.getByTestId("image-viewport").getAttribute("data-mode")).toBe("rebox");
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
  it("data-mode='add-word' when add-word mode active", () => {
    viewportStore.setState({ mode: "add-word", pendingReboxTarget: null });
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    expect(screen.getByTestId("image-viewport").getAttribute("data-mode")).toBe("add-word");
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

    // Still in add-word mode for next drag
    expect(viewportStore.getState().mode).toBe("add-word");
  });
});

// ── spec-21-A8 (#304): focus wrapper + viewport hotkeys ─────────────────────

describe("PageImageCanvas — focus wrapper (spec-21-A8, #304, spec §10)", () => {
  it("wrapper carries focus-visible:ring-2 class for visible keyboard focus", () => {
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    const viewport = screen.getByTestId("image-viewport");
    expect(viewport.className).toContain("focus-visible:ring-2");
  });

  it("wrapper is focused on mount (focusRef.current.focus() in effect)", () => {
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    const viewport = screen.getByTestId("image-viewport");
    expect(document.activeElement).toBe(viewport);
  });

  it("wrapper has tabIndex=0 so it can receive focus (spec §10)", () => {
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    const viewport = screen.getByTestId("image-viewport");
    expect(viewport.getAttribute("tabindex")).toBe("0");
  });
});

describe("PageImageCanvas — viewport hotkeys (spec-21-A8, #304, spec §10)", () => {
  it("Esc clears drag state (acceptance criterion)", () => {
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    const stage = getStage();

    fireEvent.mouseDown(stage, { clientX: 50, clientY: 50 });
    fireEvent.mouseMove(stage, { clientX: 150, clientY: 150 });
    expect(screen.queryByTestId("ocr-drag-rect")).not.toBeNull();

    // Document-scope Esc (the hook listens at document scope per #237).
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByTestId("ocr-drag-rect")).toBeNull();
  });

  it("Shift+1 sets selectionMode to 'paragraph' (acceptance criterion)", () => {
    // Start from a non-paragraph state so the assertion is meaningful.
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

describe("PageImageCanvas — selection layer rendering (spec-21-A5, #300)", () => {
  it("renders three BBoxOverlay sidecars inside the selection layer with count=0 when page is null", () => {
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
    // Find rects rendered inside the selection layer. There should be exactly
    // one rect across all three selection-* BBoxOverlays (the selected line).
    const rects = selectionLayer.querySelectorAll('[data-testid="konva-rect"]');
    expect(rects.length).toBe(1);
    expect(rects[0].getAttribute("data-stroke-width")).toBe(String(SELECTION_STROKE_WIDTH));
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

// ── Word click → selectWord (canvas entry point wiring) ─────────────────────

describe("PageImageCanvas — word bbox click → selectWord", () => {
  it("clicking within a word bbox in select mode calls selectWord(lineIdx, wordIdx)", () => {
    // Word at bbox (100,200,50,20) in display coords = line 2, word 3
    const page = makePage([makeLine(2, 0, [{ x: 100, y: 200, width: 50, height: 20 }])]);
    // Override the word_index to 3 to verify correct index propagation
    page.line_matches[0].word_matches[0].word_index = 3;

    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} page={page} />);
    const stage = getStage();

    // Click inside the bbox (x=125, y=210 is within 100..150, 200..220)
    fireEvent.mouseDown(stage, { clientX: 125, clientY: 210 });
    fireEvent.mouseUp(stage, { clientX: 125, clientY: 210 });

    const sel = selectionStore.getState();
    expect(sel.level).toBe("word");
    expect(sel.selectedWords).toEqual([[2, 3]]);
  });

  it("clicking within a word bbox opens the right panel (rightPanelOpen=true)", () => {
    const page = makePage([makeLine(0, 0, [{ x: 10, y: 10, width: 40, height: 15 }])]);
    useUiPrefs.setState({ rightPanelOpen: false });

    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} page={page} />);
    const stage = getStage();

    fireEvent.mouseDown(stage, { clientX: 25, clientY: 15 });
    fireEvent.mouseUp(stage, { clientX: 25, clientY: 15 });

    expect(useUiPrefs.getState().rightPanelOpen).toBe(true);
  });

  it("clicking outside all word bboxes does NOT call selectWord", () => {
    const page = makePage([makeLine(0, 0, [{ x: 100, y: 100, width: 50, height: 20 }])]);

    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} page={page} />);
    const stage = getStage();

    // Click far from any bbox
    fireEvent.mouseDown(stage, { clientX: 400, clientY: 400 });
    fireEvent.mouseUp(stage, { clientX: 400, clientY: 400 });

    const sel = selectionStore.getState();
    expect(sel.level).toBe("none");
    expect(sel.selectedWords).toEqual([]);
  });

  it("a real drag (>2px) does NOT trigger word selection even if it ends inside a bbox", () => {
    const page = makePage([makeLine(0, 0, [{ x: 50, y: 50, width: 100, height: 30 }])]);

    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} page={page} />);

    // Drag with width=100 → not trivial, so normal box-select fires, NOT selectWord
    simulateDrag({ x: 50, y: 50 }, { x: 150, y: 80 });

    const sel = selectionStore.getState();
    expect(sel.level).toBe("none");
    expect(sel.selectedWords).toEqual([]);
  });

  it("word click in rebox mode does NOT trigger word selection (only select mode responds)", () => {
    const page = makePage([makeLine(0, 0, [{ x: 10, y: 10, width: 40, height: 15 }])]);
    viewportStore.setState({ mode: "rebox", pendingReboxTarget: null });

    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} page={page} />);
    const stage = getStage();

    fireEvent.mouseDown(stage, { clientX: 25, clientY: 15 });
    fireEvent.mouseUp(stage, { clientX: 25, clientY: 15 });

    const sel = selectionStore.getState();
    expect(sel.level).toBe("none");
  });
});

describe("PageImageCanvas — Erase mode (#198)", () => {
  it("data-mode='erase' when erase mode active", () => {
    viewportStore.setState({ mode: "erase", pendingReboxTarget: null });
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    expect(screen.getByTestId("image-viewport").getAttribute("data-mode")).toBe("erase");
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

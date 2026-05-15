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
import { render, screen, fireEvent } from "@testing-library/react";
import { getStageDimensions } from "../lib/canvas-utils";
import { viewportStore } from "../stores/viewport-store";
import { selectionStore } from "../stores/selection-store";

// ── use-image mock (used by PageImage) ───────────────────────────────────────
// Default state: image not yet loaded → PageImage renders the grey fallback Rect.
const mockUseImageState = vi.hoisted(() => ({
  image: undefined as HTMLImageElement | undefined,
  status: "loading" as "loading" | "loaded" | "failed",
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
    dash,
    "data-testid": testId,
  }: {
    x?: number;
    y?: number;
    width?: number;
    height?: number;
    fill?: string;
    stroke?: string;
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

const encoded = {
  src_width: 1600,
  src_height: 1200,
  display_width: 800,
  display_height: 600,
  scale: 0.5,
};

// Reset stores and use-image state after each test
afterEach(() => {
  viewportStore.setState({ mode: "select", pendingReboxTarget: null });
  selectionStore.setState({
    selectedParagraphs: [],
    selectedLines: [],
    selectedWords: [],
    dragRect: null,
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
    expect(dragPreview?.getAttribute("data-stroke")).toBe("#2563eb"); // spec §9 blue-600
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

describe("PageImageCanvas — per-mode drag-preview stroke (spec-21-A7, #303, spec §9)", () => {
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

  it("rebox stroke is #16a34a (green-600)", () => {
    expect(dragPreviewStroke("rebox")).toBe("#16a34a");
  });

  it("add-word stroke is #9333ea (purple-600)", () => {
    expect(dragPreviewStroke("add-word")).toBe("#9333ea");
  });

  it("erase stroke is #dc2626 (red-600)", () => {
    expect(dragPreviewStroke("erase")).toBe("#dc2626");
  });
});

describe("PageImageCanvas — erase drag-preview fill (spec-21-A7, #303, spec §9)", () => {
  it("erase mode drag-preview Rect has rgba(220,38,38,0.20) fill", () => {
    viewportStore.setState({ mode: "erase", pendingReboxTarget: null });
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    const stage = getStage();
    fireEvent.mouseDown(stage, { clientX: 30, clientY: 40 });
    fireEvent.mouseMove(stage, { clientX: 130, clientY: 110 });

    const dragLayer = screen.getByTestId("konva-layer-drag");
    const dragPreview = dragLayer.querySelector('[data-testid="konva-drag-preview"]');
    expect(dragPreview?.getAttribute("data-fill")).toBe("rgba(220,38,38,0.20)");
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

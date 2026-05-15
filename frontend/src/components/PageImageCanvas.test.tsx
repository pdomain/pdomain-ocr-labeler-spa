// PageImageCanvas.test.tsx — viewport canvas tests (#196, #197, #198, #297)
//
// Spec: specs/21-konva-renderer.md §4 (component layout), §12 (testids), §13 (empty state).
//
// spec-21-A2 (#297) — the DOM-stub viewport is replaced with a real Konva
// <Stage> + 6-layer skeleton. Overlays remain empty in this slice; #298
// fills BBoxOverlay. DOM-event-based drag handlers stay on the wrapping
// viewport div (handler migration to Konva Stage events is deferred to
// spec-21-C). Tests mock react-konva and use-image so jsdom can probe the
// rendered tree without a real canvas — same pattern as PageImage.test.tsx
// and WordEditDialog.test.tsx.

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
vi.mock("react-konva", () => ({
  Stage: ({
    children,
    width,
    height,
    "data-testid": testId,
  }: {
    children?: React.ReactNode;
    width?: number;
    height?: number;
    "data-testid"?: string;
    [key: string]: unknown;
  }) => (
    <div data-testid={testId ?? "konva-stage"} data-width={width} data-height={height}>
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
    width,
    height,
    fill,
    "data-testid": testId,
  }: {
    width?: number;
    height?: number;
    fill?: string;
    "data-testid"?: string;
  }) => (
    <div
      data-testid={testId ?? "konva-rect"}
      data-width={width}
      data-height={height}
      data-fill={fill}
    />
  ),
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

// Helper: simulate a drag (mousedown → mousemove → mouseup)
function simulateDrag(
  viewport: HTMLElement,
  from: { x: number; y: number },
  to: { x: number; y: number },
  opts: { shiftKey?: boolean; ctrlKey?: boolean } = {},
) {
  fireEvent.mouseDown(viewport, { clientX: from.x, clientY: from.y, ...opts });
  fireEvent.mouseMove(viewport, { clientX: to.x, clientY: to.y, ...opts });
  fireEvent.mouseUp(viewport, { clientX: to.x, clientY: to.y, ...opts });
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

describe("PageImageCanvas — Select mode (drag box-select, #197)", () => {
  it("shows no drag-rect initially", () => {
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    expect(screen.queryByTestId("ocr-drag-rect")).toBeNull();
  });

  it("drag-rect appears during mouse drag", () => {
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    const viewport = screen.getByTestId("image-viewport");

    fireEvent.mouseDown(viewport, { clientX: 100, clientY: 100 });
    fireEvent.mouseMove(viewport, { clientX: 200, clientY: 200 });

    expect(screen.queryByTestId("ocr-drag-rect")).not.toBeNull();
  });

  it("drag-rect disappears after mouseup", () => {
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    const viewport = screen.getByTestId("image-viewport");
    simulateDrag(viewport, { x: 100, y: 100 }, { x: 200, y: 200 });
    expect(screen.queryByTestId("ocr-drag-rect")).toBeNull();
  });

  it("calls onBoxSelect with rect and 'replace' modifier on plain drag", () => {
    const onBoxSelect = vi.fn();
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} onBoxSelect={onBoxSelect} />);
    const viewport = screen.getByTestId("image-viewport");
    simulateDrag(viewport, { x: 50, y: 50 }, { x: 150, y: 120 });

    expect(onBoxSelect).toHaveBeenCalledOnce();
    const [rect, modifier] = onBoxSelect.mock.calls[0];
    expect(modifier).toBe("replace");
    expect(rect.width).toBeGreaterThan(2);
  });

  it("calls onBoxSelect with 'remove' modifier when Shift held", () => {
    const onBoxSelect = vi.fn();
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} onBoxSelect={onBoxSelect} />);
    const viewport = screen.getByTestId("image-viewport");
    simulateDrag(viewport, { x: 50, y: 50 }, { x: 150, y: 120 }, { shiftKey: true });

    expect(onBoxSelect.mock.calls[0][1]).toBe("remove");
  });

  it("calls onBoxSelect with 'toggle' modifier when Ctrl held", () => {
    const onBoxSelect = vi.fn();
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} onBoxSelect={onBoxSelect} />);
    const viewport = screen.getByTestId("image-viewport");
    simulateDrag(viewport, { x: 50, y: 50 }, { x: 150, y: 120 }, { ctrlKey: true });

    expect(onBoxSelect.mock.calls[0][1]).toBe("toggle");
  });

  it("does NOT call onBoxSelect for tiny drag (≤2px)", () => {
    const onBoxSelect = vi.fn();
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} onBoxSelect={onBoxSelect} />);
    const viewport = screen.getByTestId("image-viewport");
    simulateDrag(viewport, { x: 100, y: 100 }, { x: 101, y: 101 });

    expect(onBoxSelect).not.toHaveBeenCalled();
  });

  it("data-mode attribute is 'select' by default", () => {
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    expect(screen.getByTestId("image-viewport").getAttribute("data-mode")).toBe("select");
  });

  it("Escape key clears drag state", () => {
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    const viewport = screen.getByTestId("image-viewport");

    fireEvent.mouseDown(viewport, { clientX: 50, clientY: 50 });
    fireEvent.mouseMove(viewport, { clientX: 150, clientY: 150 });
    expect(screen.queryByTestId("ocr-drag-rect")).not.toBeNull();

    fireEvent.keyDown(viewport, { key: "Escape" });
    expect(screen.queryByTestId("ocr-drag-rect")).toBeNull();
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
    const viewport = screen.getByTestId("image-viewport");
    simulateDrag(viewport, { x: 50, y: 50 }, { x: 150, y: 120 });

    expect(onRebox).toHaveBeenCalledOnce();
    const rect = onRebox.mock.calls[0][0];
    expect(rect.width).toBeGreaterThan(2);
  });

  it("mode resets to select after rebox completes", () => {
    const onRebox = vi.fn();
    viewportStore.setState({ mode: "rebox", pendingReboxTarget: { lineIndex: 0, wordIndex: 0 } });
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} onRebox={onRebox} />);
    const viewport = screen.getByTestId("image-viewport");
    simulateDrag(viewport, { x: 50, y: 50 }, { x: 150, y: 120 });

    expect(viewportStore.getState().mode).toBe("select");
  });

  it("does NOT call onBoxSelect during rebox mode", () => {
    const onBoxSelect = vi.fn();
    viewportStore.setState({ mode: "rebox", pendingReboxTarget: null });
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} onBoxSelect={onBoxSelect} />);
    const viewport = screen.getByTestId("image-viewport");
    simulateDrag(viewport, { x: 50, y: 50 }, { x: 150, y: 120 });

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
    const viewport = screen.getByTestId("image-viewport");
    simulateDrag(viewport, { x: 50, y: 50 }, { x: 150, y: 120 });

    expect(onAddWord).toHaveBeenCalledOnce();
  });

  it("mode stays add-word after add-word completes (multi-add)", () => {
    const onAddWord = vi.fn();
    viewportStore.setState({ mode: "add-word", pendingReboxTarget: null });
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} onAddWord={onAddWord} />);
    const viewport = screen.getByTestId("image-viewport");
    simulateDrag(viewport, { x: 50, y: 50 }, { x: 150, y: 120 });

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
    const viewport = screen.getByTestId("image-viewport");
    simulateDrag(viewport, { x: 50, y: 50 }, { x: 150, y: 120 });

    expect(onErasePixels).toHaveBeenCalledOnce();
  });

  it("mode resets to select after erase completes", () => {
    const onErasePixels = vi.fn();
    viewportStore.setState({ mode: "erase", pendingReboxTarget: null });
    render(
      <PageImageCanvas imageUrl="/test.jpg" encoded={encoded} onErasePixels={onErasePixels} />,
    );
    const viewport = screen.getByTestId("image-viewport");
    simulateDrag(viewport, { x: 50, y: 50 }, { x: 150, y: 120 });

    expect(viewportStore.getState().mode).toBe("select");
  });
});

// PageImageCanvas.test.tsx — viewport canvas tests (#196, #197)
// Spec: docs/specs/2026-05-12-image-viewport-design.md

import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import PageImageCanvas from "./PageImageCanvas";
import { getStageDimensions } from "../lib/canvas-utils";
import { viewportStore } from "../stores/viewport-store";
import { selectionStore } from "../stores/selection-store";

const encoded = {
  src_width: 1600,
  src_height: 1200,
  display_width: 800,
  display_height: 600,
  scale: 0.5,
};

// Reset stores after each test
afterEach(() => {
  viewportStore.setState({ mode: "select", pendingReboxTarget: null });
  selectionStore.setState({
    selectedParagraphs: [],
    selectedLines: [],
    selectedWords: [],
    dragRect: null,
  });
});

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

  it("renders canvas with correct dimensions attributes", () => {
    const { getByTestId } = render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    const canvas = getByTestId("image-viewport");
    expect(canvas.getAttribute("data-width")).toBe("800");
    expect(canvas.getAttribute("data-height")).toBe("600");
  });
});

describe("PageImageCanvas — Select mode (drag box-select, #197)", () => {
  it("shows no drag-rect initially", () => {
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    expect(screen.queryByTestId("ocr-drag-rect")).toBeNull();
  });

  it("drag-rect appears during mouse drag in select mode", () => {
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    const viewport = screen.getByTestId("image-viewport");

    // Simulate drag: mousedown → mousemove → (no mouseup yet)
    fireEvent.mouseDown(viewport, { clientX: 100, clientY: 100 });
    fireEvent.mouseMove(viewport, { clientX: 200, clientY: 200 });

    const dragRect = screen.queryByTestId("ocr-drag-rect");
    expect(dragRect).not.toBeNull();
  });

  it("drag-rect disappears after mouseup", () => {
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    const viewport = screen.getByTestId("image-viewport");

    fireEvent.mouseDown(viewport, { clientX: 100, clientY: 100 });
    fireEvent.mouseMove(viewport, { clientX: 200, clientY: 200 });
    fireEvent.mouseUp(viewport, { clientX: 200, clientY: 200 });

    expect(screen.queryByTestId("ocr-drag-rect")).toBeNull();
  });

  it("calls onBoxSelect with rect and 'replace' modifier on plain drag", () => {
    const onBoxSelect = vi.fn();
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} onBoxSelect={onBoxSelect} />);
    const viewport = screen.getByTestId("image-viewport");

    fireEvent.mouseDown(viewport, { clientX: 50, clientY: 50 });
    fireEvent.mouseMove(viewport, { clientX: 150, clientY: 120 });
    fireEvent.mouseUp(viewport, { clientX: 150, clientY: 120 });

    expect(onBoxSelect).toHaveBeenCalledOnce();
    const [rect, modifier] = onBoxSelect.mock.calls[0];
    expect(modifier).toBe("replace");
    expect(rect.width).toBeGreaterThan(2);
    expect(rect.height).toBeGreaterThan(2);
  });

  it("calls onBoxSelect with 'remove' modifier when Shift held", () => {
    const onBoxSelect = vi.fn();
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} onBoxSelect={onBoxSelect} />);
    const viewport = screen.getByTestId("image-viewport");

    fireEvent.mouseDown(viewport, { clientX: 50, clientY: 50, shiftKey: true });
    fireEvent.mouseMove(viewport, { clientX: 150, clientY: 120, shiftKey: true });
    fireEvent.mouseUp(viewport, { clientX: 150, clientY: 120, shiftKey: true });

    expect(onBoxSelect).toHaveBeenCalledOnce();
    expect(onBoxSelect.mock.calls[0][1]).toBe("remove");
  });

  it("calls onBoxSelect with 'toggle' modifier when Ctrl held", () => {
    const onBoxSelect = vi.fn();
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} onBoxSelect={onBoxSelect} />);
    const viewport = screen.getByTestId("image-viewport");

    fireEvent.mouseDown(viewport, { clientX: 50, clientY: 50, ctrlKey: true });
    fireEvent.mouseMove(viewport, { clientX: 150, clientY: 120, ctrlKey: true });
    fireEvent.mouseUp(viewport, { clientX: 150, clientY: 120, ctrlKey: true });

    expect(onBoxSelect).toHaveBeenCalledOnce();
    expect(onBoxSelect.mock.calls[0][1]).toBe("toggle");
  });

  it("does NOT call onBoxSelect for tiny drag (≤2px)", () => {
    const onBoxSelect = vi.fn();
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} onBoxSelect={onBoxSelect} />);
    const viewport = screen.getByTestId("image-viewport");

    fireEvent.mouseDown(viewport, { clientX: 100, clientY: 100 });
    fireEvent.mouseMove(viewport, { clientX: 101, clientY: 101 });
    fireEvent.mouseUp(viewport, { clientX: 101, clientY: 101 });

    expect(onBoxSelect).not.toHaveBeenCalled();
  });

  it("data-mode attribute reflects viewport mode", () => {
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    const viewport = screen.getByTestId("image-viewport");
    expect(viewport.getAttribute("data-mode")).toBe("select");
  });

  it("Escape key clears drag state", () => {
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />);
    const viewport = screen.getByTestId("image-viewport");

    fireEvent.mouseDown(viewport, { clientX: 50, clientY: 50 });
    fireEvent.mouseMove(viewport, { clientX: 150, clientY: 150 });

    // Should have drag rect now
    expect(screen.queryByTestId("ocr-drag-rect")).not.toBeNull();

    fireEvent.keyDown(viewport, { key: "Escape" });
    expect(screen.queryByTestId("ocr-drag-rect")).toBeNull();
  });

  it("no drag interaction in non-select mode", () => {
    viewportStore.setState({ mode: "erase", pendingReboxTarget: null });
    const onBoxSelect = vi.fn();
    render(<PageImageCanvas imageUrl="/test.jpg" encoded={encoded} onBoxSelect={onBoxSelect} />);
    const viewport = screen.getByTestId("image-viewport");

    fireEvent.mouseDown(viewport, { clientX: 50, clientY: 50 });
    fireEvent.mouseMove(viewport, { clientX: 150, clientY: 150 });
    fireEvent.mouseUp(viewport, { clientX: 150, clientY: 150 });

    expect(screen.queryByTestId("ocr-drag-rect")).toBeNull();
    expect(onBoxSelect).not.toHaveBeenCalled();
  });
});

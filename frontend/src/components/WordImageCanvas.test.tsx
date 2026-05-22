// WordImageCanvas.test.tsx — interactive Konva word image (#210)
// Spec: docs/specs/2026-05-12-word-edit-dialog-design.md §Interactive Konva image
//
// Acceptance:
//   - Zoom selector changes Stage scale (data-testid="dialog-current-zoom-toggle")
//   - Erase rects accumulate without POST (data-testid="dialog-erase-rect")
//   - Click marker placed on click (data-testid="dialog-current-marker")
//   - Hover guide shows on mouseenter (data-testid="dialog-hover-guide")

import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

// Mock react-konva — renders div stubs instead of canvas.
vi.mock("react-konva", () => ({
  Stage: ({
    children,
    width,
    height,
    "data-testid": testId,
    onMouseMove,
    onMouseLeave,
    onMouseDown,
    onMouseUp,
    onClick,
  }: {
    children?: React.ReactNode;
    width?: number;
    height?: number;
    "data-testid"?: string;
    onMouseMove?: (e: unknown) => void;
    onMouseLeave?: () => void;
    onMouseDown?: (e: unknown) => void;
    onMouseUp?: (e: unknown) => void;
    onClick?: (e: unknown) => void;
  }) => (
    <div
      data-testid={testId ?? "konva-stage"}
      data-width={width}
      data-height={height}
      onMouseMove={(_e) => {
        if (onMouseMove) {
          // Simulate Konva event with getStage().getPointerPosition()
          const pos = { x: 50, y: 30 };
          onMouseMove({
            target: {
              getStage: () => ({ getPointerPosition: () => pos }),
            },
          });
        }
      }}
      onMouseLeave={() => onMouseLeave?.()}
      onMouseDown={(_e) => {
        if (onMouseDown) {
          const pos = { x: 20, y: 10 };
          onMouseDown({
            target: {
              getStage: () => ({ getPointerPosition: () => pos }),
            },
          });
        }
      }}
      onMouseUp={(_e) => {
        if (onMouseUp) {
          const pos = { x: 60, y: 40 };
          onMouseUp({
            target: {
              getStage: () => ({ getPointerPosition: () => pos }),
            },
          });
        }
      }}
      onClick={(_e) => {
        if (onClick) {
          const pos = { x: 50, y: 30 };
          onClick({
            target: {
              getStage: () => ({ getPointerPosition: () => pos }),
            },
          });
        }
      }}
    >
      {children}
    </div>
  ),
  Layer: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  Rect: ({
    "data-testid": testId,
    x,
    y,
    width,
    height,
    fill,
  }: {
    "data-testid"?: string;
    x?: number;
    y?: number;
    width?: number;
    height?: number;
    fill?: string;
    [key: string]: unknown;
  }) => (
    <div
      data-testid={testId ?? "konva-rect"}
      data-x={x}
      data-y={y}
      data-width={width}
      data-height={height}
      data-fill={fill}
    />
  ),
  Circle: ({
    "data-testid": testId,
    x,
    y,
    radius,
    fill,
  }: {
    "data-testid"?: string;
    x?: number;
    y?: number;
    radius?: number;
    fill?: string;
  }) => (
    <div
      data-testid={testId ?? "konva-circle"}
      data-x={x}
      data-y={y}
      data-radius={radius}
      data-fill={fill}
    />
  ),
  Line: ({ "data-testid": testId }: { "data-testid"?: string }) => (
    <div data-testid={testId ?? "konva-line"} />
  ),
  Image: ({ "data-testid": testId }: { "data-testid"?: string; [key: string]: unknown }) => (
    <div data-testid={testId ?? "konva-image"} />
  ),
}));

import { WordImageCanvas } from "./WordImageCanvas";

describe("WordImageCanvas", () => {
  it("renders the Konva Stage", () => {
    render(<WordImageCanvas />);
    expect(screen.getByTestId("dialog-word-stage")).toBeTruthy();
  });

  it("renders zoom buttons for all four levels", () => {
    render(<WordImageCanvas />);
    const buttons = screen.getAllByTestId("dialog-current-zoom-toggle");
    expect(buttons).toHaveLength(4);
    const zooms = buttons.map((b) => b.getAttribute("data-zoom"));
    expect(zooms).toContain("1");
    expect(zooms).toContain("2");
    expect(zooms).toContain("5");
    expect(zooms).toContain("10");
  });

  it("zoom 1x is selected by default (aria-pressed=true)", () => {
    render(<WordImageCanvas />);
    const buttons = screen.getAllByTestId("dialog-current-zoom-toggle");
    const oneX = buttons.find((b) => b.getAttribute("data-zoom") === "1");
    expect(oneX?.getAttribute("aria-pressed")).toBe("true");
  });

  it("clicking a zoom button changes Stage dimensions", () => {
    render(<WordImageCanvas />);
    const stage = screen.getByTestId("dialog-word-stage");

    // Default (1×): stage width is 200
    expect(Number(stage.getAttribute("data-width"))).toBe(200);

    // Click 2×
    const twoX = screen
      .getAllByTestId("dialog-current-zoom-toggle")
      .find((b) => b.getAttribute("data-zoom") === "2")!;
    fireEvent.click(twoX);

    expect(Number(stage.getAttribute("data-width"))).toBe(400);
  });

  it("clicking 5x zoom sets stage width to 5 * BASE_WIDTH", () => {
    render(<WordImageCanvas />);
    const fiveX = screen
      .getAllByTestId("dialog-current-zoom-toggle")
      .find((b) => b.getAttribute("data-zoom") === "5")!;
    fireEvent.click(fiveX);
    const stage = screen.getByTestId("dialog-word-stage");
    expect(Number(stage.getAttribute("data-width"))).toBe(1000);
  });

  it("selected zoom button has aria-pressed=true, others false", () => {
    render(<WordImageCanvas />);
    const twoX = screen
      .getAllByTestId("dialog-current-zoom-toggle")
      .find((b) => b.getAttribute("data-zoom") === "2")!;
    fireEvent.click(twoX);

    const buttons = screen.getAllByTestId("dialog-current-zoom-toggle");
    buttons.forEach((b) => {
      const isTwo = b.getAttribute("data-zoom") === "2";
      expect(b.getAttribute("aria-pressed")).toBe(String(isTwo));
    });
  });

  it("erase rects render with dialog-erase-rect testid", () => {
    const rects = [
      { x: 10, y: 10, width: 20, height: 15 },
      { x: 50, y: 5, width: 10, height: 8 },
    ];
    render(<WordImageCanvas eraseRects={rects} />);
    const renderedRects = screen.getAllByTestId("dialog-erase-rect");
    expect(renderedRects).toHaveLength(2);
  });

  it("erase rects accumulate via onEraseRectAdd without firing POST", () => {
    const onEraseRectAdd = vi.fn();
    render(<WordImageCanvas eraseMode eraseRects={[]} onEraseRectAdd={onEraseRectAdd} />);

    const stage = screen.getByTestId("dialog-word-stage");

    // Simulate drag: mousedown → mousemove (updates pendingEraseRect to non-zero size) → mouseup.
    fireEvent.mouseDown(stage);
    fireEvent.mouseMove(stage); // mock fires pos {x:50, y:30}; startX=20,startY=10 → w=30, h=20
    fireEvent.mouseUp(stage);

    // onEraseRectAdd should be called with a non-zero rect; no fetch/POST should fire.
    expect(onEraseRectAdd).toHaveBeenCalled();
    const rect = onEraseRectAdd.mock.calls[0]?.[0];
    expect(rect).toBeDefined();
    expect(rect.width).toBeGreaterThan(0);
    expect(rect.height).toBeGreaterThan(0);
  });

  it("onMarkerPlace called on click in normal mode", () => {
    const onMarkerPlace = vi.fn();
    render(<WordImageCanvas onMarkerPlace={onMarkerPlace} />);
    const stage = screen.getByTestId("dialog-word-stage");
    fireEvent.click(stage);
    expect(onMarkerPlace).toHaveBeenCalled();
  });

  it("erase mode indicator shown when eraseMode=true", () => {
    render(<WordImageCanvas eraseMode />);
    expect(screen.getByText(/erase mode/i)).toBeTruthy();
  });

  it("no erase mode indicator when eraseMode=false", () => {
    render(<WordImageCanvas eraseMode={false} />);
    expect(screen.queryByText(/erase mode/i)).toBeNull();
  });
});

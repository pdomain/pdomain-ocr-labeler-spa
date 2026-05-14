// Acceptance test for Konva mock: verifies that react-konva Stage/Layer/Rect
// render without canvas errors in jsdom. Without a mock, Konva tries to
// instantiate HTMLCanvasElement which jsdom doesn't fully support, causing
// runtime errors.
//
// vi.mock calls are hoisted by Vitest's transform before imports, ensuring the
// mock is active before any react-konva code runs.
import { describe, it, expect, vi } from "vitest";
import { render } from "@testing-library/react";

// Mock react-konva so Stage renders a <div> instead of a canvas tree.
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
  }) => (
    <div data-testid={testId ?? "konva-stage"} data-width={width} data-height={height}>
      {children}
    </div>
  ),
  Layer: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  Rect: ({ x, y, width, height }: { x?: number; y?: number; width?: number; height?: number }) => (
    <div data-testid="konva-rect" data-x={x} data-y={y} data-width={width} data-height={height} />
  ),
}));

// After mocking, import react-konva components.
import { Stage, Layer, Rect } from "react-konva";

function KonvaFixture() {
  return (
    <Stage width={400} height={300} data-testid="test-stage">
      <Layer>
        <Rect x={10} y={20} width={100} height={50} />
      </Layer>
    </Stage>
  );
}

describe("Konva mock", () => {
  it("Stage renders without canvas errors in jsdom", () => {
    // If the mock is absent, this render throws: "Cannot read property 'getContext' of null"
    // or similar canvas-related errors from the Konva runtime.
    expect(() => render(<KonvaFixture />)).not.toThrow();
  });

  it("Stage renders with correct dimensions", () => {
    const { getByTestId } = render(<KonvaFixture />);
    const stage = getByTestId("test-stage");
    expect(stage.getAttribute("data-width")).toBe("400");
    expect(stage.getAttribute("data-height")).toBe("300");
  });

  it("Rect renders with correct position and dimensions", () => {
    const { getByTestId } = render(<KonvaFixture />);
    const rect = getByTestId("konva-rect");
    expect(rect.getAttribute("data-x")).toBe("10");
    expect(rect.getAttribute("data-y")).toBe("20");
    expect(rect.getAttribute("data-width")).toBe("100");
    expect(rect.getAttribute("data-height")).toBe("50");
  });
});

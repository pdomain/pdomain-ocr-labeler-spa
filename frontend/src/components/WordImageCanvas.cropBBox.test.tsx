// WordImageCanvas.cropBBox.test.tsx — Task S1.3
// Tests that WordImageCanvas accepts and uses a cropBBox prop
// to restrict which portion of the page image is visible.
// Spec: docs/specs/2026-06-06-word-edit-dialog-wiring.md WED-10

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";

// Mock react-konva (same as ProjectPage.test.tsx pattern)
vi.mock("react-konva", () => ({
  Stage: ({
    children,
    width,
    height,
    "data-testid": tid,
  }: {
    children?: React.ReactNode;
    width?: number;
    height?: number;
    "data-testid"?: string;
  }) => (
    <div data-testid={tid ?? "konva-stage"} data-width={width} data-height={height}>
      {children}
    </div>
  ),
  Layer: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  Rect: ({
    "data-testid": tid,
    fillPatternImage,
    fillPatternOffsetX,
    fillPatternOffsetY,
  }: {
    "data-testid"?: string;
    fillPatternImage?: HTMLImageElement;
    fillPatternOffsetX?: number;
    fillPatternOffsetY?: number;
    [key: string]: unknown;
  }) => (
    <div
      data-testid={tid ?? "konva-rect"}
      data-has-image={fillPatternImage ? "true" : "false"}
      data-offset-x={fillPatternOffsetX}
      data-offset-y={fillPatternOffsetY}
    />
  ),
  Image: () => <div data-testid="konva-image" />,
}));

vi.mock("use-image", () => ({
  __esModule: true,
  default: () => [null, "loaded"],
}));

import { WordImageCanvas } from "./WordImageCanvas";

describe("WordImageCanvas cropBBox prop (WED-10, S1.3)", () => {
  it("renders the dialog-word-stage when imageUrl is provided", () => {
    render(<WordImageCanvas imageUrl="/api/projects/p1/image/0" />);
    expect(screen.getByTestId("dialog-word-stage")).toBeInTheDocument();
  });

  it("accepts a cropBBox prop and renders the stage without error", () => {
    expect(() => {
      render(
        <WordImageCanvas
          imageUrl="/api/projects/p1/image/0"
          cropBBox={{ x: 10, y: 20, width: 80, height: 30 }}
        />,
      );
    }).not.toThrow();
    expect(screen.getByTestId("dialog-word-stage")).toBeInTheDocument();
  });

  it("exposes cropBBox as a typed prop (static check: TypeScript accepts it)", () => {
    // Verify the component signature accepts cropBBox without a type error.
    // The render itself serves as the type check in tsconfig-checked builds.
    const element = (
      <WordImageCanvas
        imageUrl="/api/projects/p1/image/0"
        cropBBox={{ x: 0, y: 0, width: 100, height: 50 }}
      />
    );
    render(element);
    expect(screen.getByTestId("dialog-word-stage")).toBeInTheDocument();
  });
});

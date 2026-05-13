import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import PageImageCanvas from "./PageImageCanvas";
import { getStageDimensions } from "../lib/canvas-utils";

describe("PageImageCanvas", () => {
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
      {
        encoded: {
          src_width: 1920,
          src_height: 1080,
          display_width: 1200,
          display_height: 675,
          scale: 0.625,
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
    const encoded = {
      src_width: 1600,
      src_height: 1200,
      display_width: 800,
      display_height: 600,
      scale: 0.5,
    };

    const { getByTestId } = render(
      <PageImageCanvas imageUrl="/test.jpg" encoded={encoded} />
    );

    const canvas = getByTestId("image-viewport");
    expect(canvas.getAttribute("data-width")).toBe("800");
    expect(canvas.getAttribute("data-height")).toBe("600");
  });
});

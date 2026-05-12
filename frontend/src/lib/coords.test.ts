import { describe, it, expect } from "vitest";
import { srcToDisplay, displayToSrc, BBox } from "./coords";

describe("coords", () => {
  it("round-trips within 1px for known bbox set", () => {
    const testCases: Array<{ bbox: BBox; scale: number }> = [
      // Small scale (downsampling)
      { bbox: { x: 10, y: 20, width: 100, height: 50 }, scale: 0.5 },
      { bbox: { x: 0, y: 0, width: 800, height: 600 }, scale: 0.5 },
      // Larger scale (upsampling)
      { bbox: { x: 5, y: 10, width: 50, height: 75 }, scale: 1.5 },
      // Identity scale
      { bbox: { x: 25, y: 35, width: 200, height: 150 }, scale: 1.0 },
      // Very small bbox
      { bbox: { x: 100, y: 100, width: 1, height: 1 }, scale: 0.75 },
      // Edge case: zero coordinates
      { bbox: { x: 0, y: 0, width: 10, height: 10 }, scale: 0.666 },
      // Large bbox
      { bbox: { x: 50, y: 100, width: 1000, height: 800 }, scale: 0.4 },
    ];

    for (const { bbox, scale } of testCases) {
      const display = srcToDisplay(bbox, scale);
      const backToSrc = displayToSrc(display, scale);

      expect(Math.abs(backToSrc.x - bbox.x)).toBeLessThanOrEqual(1);
      expect(Math.abs(backToSrc.y - bbox.y)).toBeLessThanOrEqual(1);
      expect(Math.abs(backToSrc.width - bbox.width)).toBeLessThanOrEqual(1);
      expect(Math.abs(backToSrc.height - bbox.height)).toBeLessThanOrEqual(1);
    }
  });
});

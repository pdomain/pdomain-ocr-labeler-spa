// Coverage test for canvas-utils. Ensures 100% coverage on lib/ per the
// testing spec (docs/specs/2026-05-12-testing-design.md).
import { describe, it, expect } from "vitest";
import { getStageDimensions, type EncodedDims } from "./canvas-utils";

describe("getStageDimensions", () => {
  it("returns display_width and display_height from encoded dims", () => {
    const encoded: EncodedDims = {
      src_width: 1600,
      src_height: 1200,
      display_width: 800,
      display_height: 600,
      scale: 0.5,
    };
    const dims = getStageDimensions(encoded);
    expect(dims.width).toBe(800);
    expect(dims.height).toBe(600);
  });

  it("handles scale > 1 (upsampled display)", () => {
    const encoded: EncodedDims = {
      src_width: 400,
      src_height: 300,
      display_width: 800,
      display_height: 600,
      scale: 2.0,
    };
    const dims = getStageDimensions(encoded);
    expect(dims.width).toBe(800);
    expect(dims.height).toBe(600);
  });

  it("handles identity scale", () => {
    const encoded: EncodedDims = {
      src_width: 1024,
      src_height: 768,
      display_width: 1024,
      display_height: 768,
      scale: 1.0,
    };
    const dims = getStageDimensions(encoded);
    expect(dims.width).toBe(1024);
    expect(dims.height).toBe(768);
  });
});

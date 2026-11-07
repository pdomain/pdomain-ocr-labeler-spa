import { describe, it, expect } from "vitest";
import { hitResizeHandle, resizeBox } from "./region-geometry";

const box = { x: 10, y: 20, width: 40, height: 30 };

describe("hitResizeHandle", () => {
  it("prefers a corner when the pointer is inside both a corner and an edge", () => {
    expect(hitResizeHandle(box, 10, 20)).toBe("nw");
    expect(hitResizeHandle(box, 50, 50)).toBe("se");
  });

  it("returns an edge when the pointer is on that edge and outside the corner slop", () => {
    expect(hitResizeHandle(box, 30, 20)).toBe("n");
    expect(hitResizeHandle(box, 50, 35)).toBe("e");
  });

  it("returns null when the pointer misses the box", () => {
    expect(hitResizeHandle(box, 0, 0)).toBeNull();
  });
});

describe("resizeBox", () => {
  it("moves the southeast corner to the pointer", () => {
    expect(resizeBox(box, "se", { x: 80, y: 90 })).toEqual({
      x: 10,
      y: 20,
      width: 70,
      height: 70,
    });
  });

  it("normalizes a drag that crosses the opposite edge", () => {
    expect(resizeBox(box, "w", { x: 80, y: 0 })).toEqual({
      x: 50,
      y: 20,
      width: 30,
      height: 30,
    });
  });

  it("keeps a 1px minimum when the pointer lands on the opposite edge", () => {
    expect(resizeBox(box, "e", { x: 10, y: 40 })).toEqual({
      x: 10,
      y: 20,
      width: 1,
      height: 30,
    });
  });

  it("rounds fractional edges", () => {
    expect(resizeBox(box, "n", { x: 0, y: 21.6 })).toEqual({
      x: 10,
      y: 22,
      width: 40,
      height: 28,
    });
  });
});

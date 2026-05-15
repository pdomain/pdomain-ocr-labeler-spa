// bbox-select.test.ts — Pure function tests for target-scoped bbox intersection.
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 13.

import { describe, it, expect } from "vitest";
import { rectsOverlap, targetToLayerKey, intersectBboxes, selectByTarget } from "./bbox-select";
import type { BBoxItem } from "../components/BBoxOverlay";
import type { BBox } from "./coords";

function makeItem(id: string, x: number, y: number, w: number, h: number): BBoxItem {
  return { id, bbox: { x, y, width: w, height: h } };
}

function makeRect(x: number, y: number, w: number, h: number): BBox {
  return { x, y, width: w, height: h };
}

describe("rectsOverlap", () => {
  it("overlapping rects return true", () => {
    expect(rectsOverlap(makeRect(0, 0, 10, 10), makeRect(5, 5, 10, 10))).toBe(true);
  });

  it("non-overlapping rects to the right return false", () => {
    expect(rectsOverlap(makeRect(0, 0, 5, 5), makeRect(10, 0, 5, 5))).toBe(false);
  });

  it("non-overlapping rects below return false", () => {
    expect(rectsOverlap(makeRect(0, 0, 5, 5), makeRect(0, 10, 5, 5))).toBe(false);
  });

  it("contained rect overlaps", () => {
    expect(rectsOverlap(makeRect(0, 0, 20, 20), makeRect(5, 5, 5, 5))).toBe(true);
  });

  it("touching edges count as overlapping", () => {
    expect(rectsOverlap(makeRect(0, 0, 5, 5), makeRect(5, 0, 5, 5))).toBe(true);
  });
});

describe("targetToLayerKey", () => {
  it("block → paragraphs", () => {
    expect(targetToLayerKey("block")).toBe("paragraphs");
  });

  it("para → paragraphs", () => {
    expect(targetToLayerKey("para")).toBe("paragraphs");
  });

  it("line → lines", () => {
    expect(targetToLayerKey("line")).toBe("lines");
  });

  it("word → words", () => {
    expect(targetToLayerKey("word")).toBe("words");
  });
});

describe("intersectBboxes", () => {
  const items = [
    makeItem("a", 0, 0, 10, 10),
    makeItem("b", 20, 20, 10, 10),
    makeItem("c", 5, 5, 10, 10),
  ];

  it("returns items that overlap drag rect", () => {
    const drag = makeRect(0, 0, 8, 8);
    const result = intersectBboxes(items, drag);
    expect(result.map((i) => i.id)).toContain("a");
    expect(result.map((i) => i.id)).toContain("c");
    expect(result.map((i) => i.id)).not.toContain("b");
  });

  it("returns empty when no items overlap", () => {
    const drag = makeRect(100, 100, 5, 5);
    expect(intersectBboxes(items, drag)).toHaveLength(0);
  });

  it("returns all items when drag rect contains all", () => {
    const drag = makeRect(0, 0, 100, 100);
    expect(intersectBboxes(items, drag)).toHaveLength(3);
  });
});

describe("selectByTarget", () => {
  const lines = [makeItem("l0", 0, 0, 10, 5), makeItem("l1", 0, 20, 10, 5)];
  const words = [makeItem("w0", 0, 0, 4, 5), makeItem("w1", 5, 0, 4, 5)];
  const paras = [makeItem("p0", 0, 0, 10, 30)];

  const layers = { paragraphs: paras, lines, words };

  it("target=line picks lines not words", () => {
    const drag = makeRect(0, 0, 15, 10);
    const result = selectByTarget("line", layers, drag);
    expect(result.map((i) => i.id)).toContain("l0");
    // words are NOT in result because target is "line"
    expect(result.map((i) => i.id)).not.toContain("w0");
  });

  it("target=word picks words not lines", () => {
    const drag = makeRect(0, 0, 5, 5);
    const result = selectByTarget("word", layers, drag);
    expect(result.map((i) => i.id)).toContain("w0");
    expect(result.map((i) => i.id)).not.toContain("l0");
  });

  it("target=block picks paragraphs", () => {
    const drag = makeRect(0, 0, 15, 35);
    const result = selectByTarget("block", layers, drag);
    expect(result.map((i) => i.id)).toContain("p0");
    expect(result.map((i) => i.id)).not.toContain("l0");
  });

  it("target=para picks paragraphs (same as block)", () => {
    const drag = makeRect(0, 0, 15, 35);
    const result = selectByTarget("para", layers, drag);
    expect(result.map((i) => i.id)).toContain("p0");
    expect(result.map((i) => i.id)).not.toContain("l0");
  });

  it("returns empty when drag rect does not overlap active layer", () => {
    const drag = makeRect(100, 100, 5, 5);
    const result = selectByTarget("line", layers, drag);
    expect(result).toHaveLength(0);
  });
});

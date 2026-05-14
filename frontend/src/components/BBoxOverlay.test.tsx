// BBoxOverlay.test.tsx — Vitest snapshot: RGBA layer colors match spec table.
// Spec: docs/specs/2026-05-12-image-viewport-design.md §Layer colors
// Issue #196
//
// Acceptance:
//   - LAYER_COLORS constants match legacy-exact RGBA values from spec table
//   - BBoxOverlay is importable with correct props type

import { describe, it, expect } from "vitest";
import { LAYER_COLORS } from "./BBoxOverlay";

describe("BBoxOverlay RGBA colors (#196)", () => {
  it("paragraphs fill matches spec: rgba(34,197,94,0.20)", () => {
    expect(LAYER_COLORS.paragraphs.fill).toBe("rgba(34,197,94,0.20)");
  });

  it("paragraphs stroke matches spec: rgba(22,163,74,0.65)", () => {
    expect(LAYER_COLORS.paragraphs.stroke).toBe("rgba(22,163,74,0.65)");
  });

  it("lines fill matches spec: rgba(236,72,153,0.20)", () => {
    expect(LAYER_COLORS.lines.fill).toBe("rgba(236,72,153,0.20)");
  });

  it("lines stroke matches spec: rgba(190,24,93,0.65)", () => {
    expect(LAYER_COLORS.lines.stroke).toBe("rgba(190,24,93,0.65)");
  });

  it("words fill matches spec: rgba(59,130,246,0.18)", () => {
    expect(LAYER_COLORS.words.fill).toBe("rgba(59,130,246,0.18)");
  });

  it("words stroke matches spec: rgba(29,78,216,0.65)", () => {
    expect(LAYER_COLORS.words.stroke).toBe("rgba(29,78,216,0.65)");
  });

  it("drag-rect stroke matches spec: #2563eb", () => {
    expect(LAYER_COLORS["drag-rect"].stroke).toBe("#2563eb");
  });

  it("drag-rect fill is none/transparent", () => {
    expect(LAYER_COLORS["drag-rect"].fill).toBe("transparent");
  });
});

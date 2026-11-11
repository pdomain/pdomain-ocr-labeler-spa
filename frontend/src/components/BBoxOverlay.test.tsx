// BBoxOverlay.test.tsx — Konva-rect rendering + sidecar test (#298, #328)
//
// Spec: specs/21-konva-renderer.md §6 (overlay rendering), §12 (testids)
// Issues: #196 (LAYER_COLORS, original RGBA constants), #298 (spec-21-A3),
//         #328 (FO-4: migrate to useLayerColors CSS vars),
//         #295 (per-item dimmed for Mismatches-only filter)
//
// Acceptance for #298:
//   - Given N items, the wrapping Stage contains N <Rect> nodes (located via
//     the react-konva mock that materialises each <Rect> as a probe div).
//   - Each Rect carries fill/stroke/strokeWidth/listening/perfectDrawEnabled
//     props derived from useLayerColors(); `selected` items use SELECTION_STROKE_WIDTH.
//   - Sidecar `<div data-testid="bbox-overlay-${layer}" data-layer data-item-count>`
//     is rendered alongside (dev/test only — production-mode gating is checked
//     separately via import.meta.env.MODE).
//
// Acceptance for #328 (FO-4):
//   - BBoxOverlay reads colors from useLayerColors() (mocked here) rather than
//     hardcoded LAYER_COLORS constants.
//   - LAYER_COLORS constants are still exported for legend/UI callers (#196 coverage kept).
//
// Acceptance for #295 (per-item dimming):
//   - BBoxItem.dimmed=true renders Rect at MISMATCH_DIM_OPACITY (0.2).
//   - BBoxItem.dimmed=false (or undefined) renders Rect at layer-level opacity.
//   - Layer-level dimmed=true still applies to items without per-item dimming.
//
// LAYER_COLORS RGBA constants (#196) — retained from prior coverage.

import { describe, it, expect, vi } from "vitest";
import { render } from "@testing-library/react";

// ── Mock useLayerColors (FO-4, #328) ─────────────────────────────────────────
//
// Provide known hex values so the derived fill/stroke values are deterministic
// in jsdom (which has no CSS engine for custom properties).

const MOCK_LAYER_COLORS = {
  block: "#a89074",
  para: "#00ff00", // distinctive green → easy to assert on derived rgba
  line: "#ff00ff", // distinctive magenta
  word: "#0000ff", // distinctive blue
};

vi.mock("../hooks/useLayerColors", async (importOriginal) => {
  const original = await importOriginal<typeof import("../hooks/useLayerColors")>();
  return {
    ...original,
    // Override only the hook; keep hexToLayerColorSpec, hexToRgba, etc. real.
    useLayerColors: () => MOCK_LAYER_COLORS,
  };
});

// Counter incremented every time the react-konva Rect mock renders. The memo
// test renders BBoxOverlay twice with the same `items` reference and asserts
// the inner Rect count doesn't grow — i.e. React.memo skipped the second
// invocation entirely (spec §11 perf pinning, spec-21-C2 #305).
const rectRenderCount = vi.hoisted(() => ({ n: 0 }));

// Mock react-konva BEFORE importing BBoxOverlay so the component pulls the
// mocked Rect. The mock renders each <Rect> as a probe <div> carrying the
// props we want to assert against, plus a <Stage>/<Layer> host so we can
// wrap the fragment under test in the same tree shape it ships in.
vi.mock("react-konva", () => ({
  Stage: ({
    children,
    "data-testid": testId,
  }: {
    children?: React.ReactNode;
    "data-testid"?: string;
  }) => <div data-testid={testId ?? "konva-stage"}>{children}</div>,
  Layer: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  Rect: ({
    x,
    y,
    width,
    height,
    fill,
    stroke,
    strokeWidth,
    opacity,
    listening,
    perfectDrawEnabled,
  }: {
    x?: number;
    y?: number;
    width?: number;
    height?: number;
    fill?: string;
    stroke?: string;
    strokeWidth?: number;
    opacity?: number;
    listening?: boolean;
    perfectDrawEnabled?: boolean;
  }) => {
    rectRenderCount.n += 1;
    return (
      <div
        data-testid="konva-rect"
        data-x={x}
        data-y={y}
        data-width={width}
        data-height={height}
        data-fill={fill}
        data-stroke={stroke}
        data-stroke-width={strokeWidth}
        data-opacity={opacity}
        data-listening={listening === undefined ? undefined : String(listening)}
        data-perfect-draw={
          perfectDrawEnabled === undefined ? undefined : String(perfectDrawEnabled)
        }
      />
    );
  },
}));

import { Layer, Stage } from "react-konva";
import {
  BBoxOverlay,
  LAYER_COLORS,
  SELECTION_STROKE_WIDTH,
  MISMATCH_DIM_OPACITY,
  type BBoxItem,
} from "./BBoxOverlay";
import { hexToRgba, LAYER_FILL_ALPHA, LAYER_STROKE_ALPHA } from "../hooks/useLayerColors";

function mkItems(n: number, selected = false): BBoxItem[] {
  return Array.from({ length: n }, (_, i) => ({
    id: String(i),
    bbox: { x: i * 10, y: i * 5, width: 8, height: 4 },
    selected,
  }));
}

// ─── Exported LAYER_COLORS constants (#196) ───────────────────────────────────
//
// The static LAYER_COLORS export remains on BBoxOverlay for legend/UI callers.
// These exact RGBA values are legacy-parity constants; they are no longer used
// internally by BBoxOverlay (which reads from useLayerColors() instead) but
// must remain exported and correct.

describe("BBoxOverlay RGBA colors (#196) — exported constants", () => {
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

// ─── Theme-aware colors (FO-4, #328) ─────────────────────────────────────────
//
// BBoxOverlay now calls useLayerColors() (mocked above) and derives colors
// via hexToLayerColorSpec(). These tests assert the mock values flow through.

describe("BBoxOverlay theme-aware colors (FO-4, #328)", () => {
  it("words Rect fill is derived from mocked --layer-word CSS var", () => {
    const { getAllByTestId } = render(
      <Stage>
        <Layer>
          <BBoxOverlay layer="words" items={mkItems(1)} />
        </Layer>
      </Stage>,
    );
    const rect = getAllByTestId("konva-rect")[0]!;
    // Mock word color is "#0000ff" → rgba(0,0,255,0.20)
    const expectedFill = hexToRgba(MOCK_LAYER_COLORS.word, LAYER_FILL_ALPHA);
    expect(rect.getAttribute("data-fill")).toBe(expectedFill);
  });

  it("words Rect stroke is derived from mocked --layer-word CSS var", () => {
    const { getAllByTestId } = render(
      <Stage>
        <Layer>
          <BBoxOverlay layer="words" items={mkItems(1)} />
        </Layer>
      </Stage>,
    );
    const rect = getAllByTestId("konva-rect")[0]!;
    // Mock word color is "#0000ff" → rgba(0,0,255,0.65)
    const expectedStroke = hexToRgba(MOCK_LAYER_COLORS.word, LAYER_STROKE_ALPHA);
    expect(rect.getAttribute("data-stroke")).toBe(expectedStroke);
  });

  it("lines Rect fill is derived from mocked --layer-line CSS var", () => {
    const { getAllByTestId } = render(
      <Stage>
        <Layer>
          <BBoxOverlay layer="lines" items={mkItems(1)} />
        </Layer>
      </Stage>,
    );
    const rect = getAllByTestId("konva-rect")[0]!;
    const expectedFill = hexToRgba(MOCK_LAYER_COLORS.line, LAYER_FILL_ALPHA);
    expect(rect.getAttribute("data-fill")).toBe(expectedFill);
  });

  it("paragraphs Rect fill is derived from mocked --layer-para CSS var", () => {
    const { getAllByTestId } = render(
      <Stage>
        <Layer>
          <BBoxOverlay layer="paragraphs" items={mkItems(1)} />
        </Layer>
      </Stage>,
    );
    const rect = getAllByTestId("konva-rect")[0]!;
    const expectedFill = hexToRgba(MOCK_LAYER_COLORS.para, LAYER_FILL_ALPHA);
    expect(rect.getAttribute("data-fill")).toBe(expectedFill);
  });

  it("drag-rect uses transparent fill + accent stroke (Gap 26)", () => {
    // In jsdom, --accent CSS var is unavailable; readAccentColor() falls back
    // to "#d6925a". buildDragRectLayerSpec() uses that value.
    const { getAllByTestId } = render(
      <Stage>
        <Layer>
          <BBoxOverlay layer="drag-rect" items={mkItems(1)} />
        </Layer>
      </Stage>,
    );
    const rect = getAllByTestId("konva-rect")[0]!;
    expect(rect.getAttribute("data-fill")).toBe("transparent");
    // stroke is whatever readAccentColor() returns (jsdom fallback = #d6925a)
    expect(rect.getAttribute("data-stroke")).toMatch(/^#[0-9a-f]{6}$/i);
  });

  it("selection-words uses accent-based fill + stroke (Gap 25)", () => {
    // In jsdom, --accent CSS var is unavailable; readAccentColor() falls back
    // to "#d6925a". buildSelectionLayerSpec() uses hexToRgba(accent, 0.18).
    const { getAllByTestId } = render(
      <Stage>
        <Layer>
          <BBoxOverlay layer="selection-words" items={mkItems(1)} />
        </Layer>
      </Stage>,
    );
    const rect = getAllByTestId("konva-rect")[0]!;
    // Fill should be a valid rgba string derived from the accent token
    expect(rect.getAttribute("data-fill")).toMatch(/^rgba\(\d+,\d+,\d+,[\d.]+\)$/);
    expect(rect.getAttribute("data-stroke")).toMatch(/^#[0-9a-f]{6}$/i);
  });
});

describe("BBoxOverlay Konva-rect rendering (#298, spec §6)", () => {
  it("renders one Rect per item (N=0)", () => {
    const { queryAllByTestId } = render(
      <Stage>
        <Layer>
          <BBoxOverlay layer="words" items={[]} />
        </Layer>
      </Stage>,
    );
    expect(queryAllByTestId("konva-rect")).toHaveLength(0);
  });

  it("renders one Rect per item (N=3)", () => {
    const { queryAllByTestId } = render(
      <Stage>
        <Layer>
          <BBoxOverlay layer="words" items={mkItems(3)} />
        </Layer>
      </Stage>,
    );
    expect(queryAllByTestId("konva-rect")).toHaveLength(3);
  });

  it("renders one Rect per item (N=7) for paragraphs layer", () => {
    const { queryAllByTestId } = render(
      <Stage>
        <Layer>
          <BBoxOverlay layer="paragraphs" items={mkItems(7)} />
        </Layer>
      </Stage>,
    );
    expect(queryAllByTestId("konva-rect")).toHaveLength(7);
  });

  it("Rect fill/stroke/strokeWidth are non-empty for lines layer", () => {
    const { getAllByTestId } = render(
      <Stage>
        <Layer>
          <BBoxOverlay layer="lines" items={mkItems(1)} />
        </Layer>
      </Stage>,
    );
    const rect = getAllByTestId("konva-rect")[0]!;
    expect(rect.getAttribute("data-fill")).toBeTruthy();
    expect(rect.getAttribute("data-stroke")).toBeTruthy();
    expect(rect.getAttribute("data-stroke-width")).toBe("1");
  });

  it("Rect propagates bbox geometry (x/y/width/height)", () => {
    const { getAllByTestId } = render(
      <Stage>
        <Layer>
          <BBoxOverlay layer="words" items={mkItems(2)} />
        </Layer>
      </Stage>,
    );
    const rects = getAllByTestId("konva-rect");
    expect(rects[0]!.getAttribute("data-x")).toBe("0");
    expect(rects[0]!.getAttribute("data-y")).toBe("0");
    expect(rects[0]!.getAttribute("data-width")).toBe("8");
    expect(rects[0]!.getAttribute("data-height")).toBe("4");
    expect(rects[1]!.getAttribute("data-x")).toBe("10");
    expect(rects[1]!.getAttribute("data-y")).toBe("5");
  });

  it("selected items use SELECTION_STROKE_WIDTH (3px)", () => {
    const items: BBoxItem[] = [
      { id: "a", bbox: { x: 0, y: 0, width: 5, height: 5 }, selected: true },
      { id: "b", bbox: { x: 0, y: 0, width: 5, height: 5 }, selected: false },
    ];
    const { getAllByTestId } = render(
      <Stage>
        <Layer>
          <BBoxOverlay layer="words" items={items} />
        </Layer>
      </Stage>,
    );
    const rects = getAllByTestId("konva-rect");
    expect(rects[0]!.getAttribute("data-stroke-width")).toBe(String(SELECTION_STROKE_WIDTH));
    expect(rects[1]!.getAttribute("data-stroke-width")).toBe("1");
  });

  it("Rect has listening=false and perfectDrawEnabled=false (perf pinning)", () => {
    const { getAllByTestId } = render(
      <Stage>
        <Layer>
          <BBoxOverlay layer="words" items={mkItems(1)} />
        </Layer>
      </Stage>,
    );
    const rect = getAllByTestId("konva-rect")[0]!;
    expect(rect.getAttribute("data-listening")).toBe("false");
    expect(rect.getAttribute("data-perfect-draw")).toBe("false");
  });

  it("visible=false renders no Rect and no sidecar", () => {
    const { queryAllByTestId, queryByTestId } = render(
      <Stage>
        <Layer>
          <BBoxOverlay layer="words" items={mkItems(3)} visible={false} />
        </Layer>
      </Stage>,
    );
    expect(queryAllByTestId("konva-rect")).toHaveLength(0);
    expect(queryByTestId("bbox-overlay-words")).toBeNull();
  });
});

describe("BBoxOverlay sidecar div (#298, spec §12)", () => {
  it("renders sidecar div with testid, data-layer, data-item-count in test mode", () => {
    const { getByTestId } = render(
      <Stage>
        <Layer>
          <BBoxOverlay layer="words" items={mkItems(4)} />
        </Layer>
      </Stage>,
    );
    const sidecar = getByTestId("bbox-overlay-words");
    expect(sidecar.getAttribute("data-layer")).toBe("words");
    expect(sidecar.getAttribute("data-item-count")).toBe("4");
  });

  it("sidecar testid per layer (paragraphs/lines/words)", () => {
    const { getByTestId: getP } = render(
      <Stage>
        <Layer>
          <BBoxOverlay layer="paragraphs" items={mkItems(1)} />
        </Layer>
      </Stage>,
    );
    expect(getP("bbox-overlay-paragraphs").getAttribute("data-item-count")).toBe("1");

    const { getByTestId: getL } = render(
      <Stage>
        <Layer>
          <BBoxOverlay layer="lines" items={mkItems(2)} />
        </Layer>
      </Stage>,
    );
    expect(getL("bbox-overlay-lines").getAttribute("data-item-count")).toBe("2");

    const { getByTestId: getW } = render(
      <Stage>
        <Layer>
          <BBoxOverlay layer="words" items={mkItems(3)} />
        </Layer>
      </Stage>,
    );
    expect(getW("bbox-overlay-words").getAttribute("data-item-count")).toBe("3");
  });
});

// ── Per-item dimming (#295 — Mismatches-only filter) ─────────────────────────
//
// BBoxItem.dimmed=true renders at MISMATCH_DIM_OPACITY (0.2).
// BBoxItem.dimmed=false/undefined renders at full opacity (1.0) when layer
// dimmed=false, or DIMMED_OPACITY (0.3) when layer dimmed=true.

describe("BBoxOverlay per-item dimming (#295)", () => {
  it("item with dimmed=true renders at MISMATCH_DIM_OPACITY (0.2)", () => {
    const items: BBoxItem[] = [
      { id: "a", bbox: { x: 0, y: 0, width: 5, height: 5 }, dimmed: true },
    ];
    const { getAllByTestId } = render(
      <Stage>
        <Layer>
          <BBoxOverlay layer="words" items={items} />
        </Layer>
      </Stage>,
    );
    const rect = getAllByTestId("konva-rect")[0]!;
    expect(Number(rect.getAttribute("data-opacity"))).toBeCloseTo(MISMATCH_DIM_OPACITY);
  });

  it("item with dimmed=false renders at full opacity (1.0)", () => {
    const items: BBoxItem[] = [
      { id: "a", bbox: { x: 0, y: 0, width: 5, height: 5 }, dimmed: false },
    ];
    const { getAllByTestId } = render(
      <Stage>
        <Layer>
          <BBoxOverlay layer="words" items={items} />
        </Layer>
      </Stage>,
    );
    const rect = getAllByTestId("konva-rect")[0]!;
    expect(Number(rect.getAttribute("data-opacity"))).toBeCloseTo(1);
  });

  it("item without dimmed prop renders at full opacity (1.0)", () => {
    const items: BBoxItem[] = [{ id: "a", bbox: { x: 0, y: 0, width: 5, height: 5 } }];
    const { getAllByTestId } = render(
      <Stage>
        <Layer>
          <BBoxOverlay layer="words" items={items} />
        </Layer>
      </Stage>,
    );
    const rect = getAllByTestId("konva-rect")[0]!;
    expect(Number(rect.getAttribute("data-opacity"))).toBeCloseTo(1);
  });

  it("per-item dimmed overrides layer-level full opacity", () => {
    const items: BBoxItem[] = [
      { id: "a", bbox: { x: 0, y: 0, width: 5, height: 5 }, dimmed: true },
      { id: "b", bbox: { x: 10, y: 0, width: 5, height: 5 }, dimmed: false },
    ];
    const { getAllByTestId } = render(
      <Stage>
        <Layer>
          <BBoxOverlay layer="words" items={items} />
        </Layer>
      </Stage>,
    );
    const rects = getAllByTestId("konva-rect");
    // Item a: dimmed=true → MISMATCH_DIM_OPACITY
    expect(Number(rects[0]!.getAttribute("data-opacity"))).toBeCloseTo(MISMATCH_DIM_OPACITY);
    // Item b: dimmed=false → full opacity
    expect(Number(rects[1]!.getAttribute("data-opacity"))).toBeCloseTo(1);
  });

  it("in matchFilterMode='all', all items render at full opacity (no per-item dimming)", () => {
    // Simulates caller passing all items without dimmed prop
    const items: BBoxItem[] = [
      { id: "a", bbox: { x: 0, y: 0, width: 5, height: 5 } },
      { id: "b", bbox: { x: 10, y: 0, width: 5, height: 5 } },
    ];
    const { getAllByTestId } = render(
      <Stage>
        <Layer>
          <BBoxOverlay layer="words" items={items} />
        </Layer>
      </Stage>,
    );
    const rects = getAllByTestId("konva-rect");
    rects.forEach((rect) => {
      expect(Number(rect.getAttribute("data-opacity"))).toBeCloseTo(1);
    });
  });

  it("in matchFilterMode='mismatches_only', exact+validated items are dimmed", () => {
    // Simulates caller passing items with dimmed=true for exact+validated words
    const items: BBoxItem[] = [
      // exact+validated → dimmed
      { id: "0-0", bbox: { x: 0, y: 0, width: 5, height: 5 }, dimmed: true },
      // mismatch → not dimmed
      { id: "0-1", bbox: { x: 10, y: 0, width: 5, height: 5 }, dimmed: false },
      // fuzzy → not dimmed
      { id: "1-0", bbox: { x: 20, y: 0, width: 5, height: 5 }, dimmed: false },
    ];
    const { getAllByTestId } = render(
      <Stage>
        <Layer>
          <BBoxOverlay layer="words" items={items} />
        </Layer>
      </Stage>,
    );
    const rects = getAllByTestId("konva-rect");
    expect(Number(rects[0]!.getAttribute("data-opacity"))).toBeCloseTo(MISMATCH_DIM_OPACITY);
    expect(Number(rects[1]!.getAttribute("data-opacity"))).toBeCloseTo(1);
    expect(Number(rects[2]!.getAttribute("data-opacity"))).toBeCloseTo(1);
  });
});

// ── React.memo wrap (spec-21-C2 #305, spec §11) ──────────────────────────────
//
// BBoxOverlay is wrapped in React.memo so a parent re-render that keeps the
// same `items` reference skips the bbox map entirely. We assert this by
// counting Rect-mock renders across a rerender() call.

describe("BBoxOverlay memoisation (#305, spec §11)", () => {
  it("skips re-render when items reference is stable", () => {
    const items = mkItems(50);
    rectRenderCount.n = 0;
    const { rerender } = render(
      <Stage>
        <Layer>
          <BBoxOverlay layer="words" items={items} />
        </Layer>
      </Stage>,
    );
    const initial = rectRenderCount.n;
    expect(initial).toBe(50);

    // Rerender with the SAME items reference + same props → memo must
    // short-circuit; no new Rect renders should fire.
    rerender(
      <Stage>
        <Layer>
          <BBoxOverlay layer="words" items={items} />
        </Layer>
      </Stage>,
    );
    expect(rectRenderCount.n).toBe(initial);
  });

  it("re-renders when items reference changes (memo not over-aggressive)", () => {
    const a = mkItems(10);
    const b = mkItems(10);
    rectRenderCount.n = 0;
    const { rerender } = render(
      <Stage>
        <Layer>
          <BBoxOverlay layer="words" items={a} />
        </Layer>
      </Stage>,
    );
    const initial = rectRenderCount.n;
    expect(initial).toBe(10);

    rerender(
      <Stage>
        <Layer>
          <BBoxOverlay layer="words" items={b} />
        </Layer>
      </Stage>,
    );
    expect(rectRenderCount.n).toBe(initial + 10);
  });
});

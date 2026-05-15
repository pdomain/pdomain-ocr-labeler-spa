// BBoxOverlay.test.tsx — Konva-rect rendering + sidecar test (#298)
//
// Spec: specs/21-konva-renderer.md §6 (overlay rendering), §12 (testids)
// Issues: #196 (LAYER_COLORS, original RGBA constants) and #298 (spec-21-A3)
//
// Acceptance for #298:
//   - Given N items, the wrapping Stage contains N <Rect> nodes (located via
//     the react-konva mock that materialises each <Rect> as a probe div).
//   - Each Rect carries fill/stroke/strokeWidth/listening/perfectDrawEnabled
//     props from LAYER_COLORS[layer]; `selected` items use SELECTION_STROKE_WIDTH.
//   - Sidecar `<div data-testid="bbox-overlay-${layer}" data-layer data-item-count>`
//     is rendered alongside (dev/test only — production-mode gating is checked
//     separately via import.meta.env.MODE).
//
// LAYER_COLORS RGBA constants (#196) — retained from prior coverage.

import { describe, it, expect, vi } from "vitest";
import { render } from "@testing-library/react";

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
    listening?: boolean;
    perfectDrawEnabled?: boolean;
  }) => (
    <div
      data-testid="konva-rect"
      data-x={x}
      data-y={y}
      data-width={width}
      data-height={height}
      data-fill={fill}
      data-stroke={stroke}
      data-stroke-width={strokeWidth}
      data-listening={listening === undefined ? undefined : String(listening)}
      data-perfect-draw={perfectDrawEnabled === undefined ? undefined : String(perfectDrawEnabled)}
    />
  ),
}));

import { Layer, Stage } from "react-konva";
import { BBoxOverlay, LAYER_COLORS, SELECTION_STROKE_WIDTH, type BBoxItem } from "./BBoxOverlay";

function mkItems(n: number, selected = false): BBoxItem[] {
  return Array.from({ length: n }, (_, i) => ({
    id: String(i),
    bbox: { x: i * 10, y: i * 5, width: 8, height: 4 },
    selected,
  }));
}

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

  it("Rect fill/stroke/strokeWidth follow LAYER_COLORS[layer]", () => {
    const { getAllByTestId } = render(
      <Stage>
        <Layer>
          <BBoxOverlay layer="lines" items={mkItems(1)} />
        </Layer>
      </Stage>,
    );
    const rect = getAllByTestId("konva-rect")[0];
    expect(rect.getAttribute("data-fill")).toBe(LAYER_COLORS.lines.fill);
    expect(rect.getAttribute("data-stroke")).toBe(LAYER_COLORS.lines.stroke);
    expect(rect.getAttribute("data-stroke-width")).toBe(String(LAYER_COLORS.lines.strokeWidth));
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
    expect(rects[0].getAttribute("data-x")).toBe("0");
    expect(rects[0].getAttribute("data-y")).toBe("0");
    expect(rects[0].getAttribute("data-width")).toBe("8");
    expect(rects[0].getAttribute("data-height")).toBe("4");
    expect(rects[1].getAttribute("data-x")).toBe("10");
    expect(rects[1].getAttribute("data-y")).toBe("5");
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
    expect(rects[0].getAttribute("data-stroke-width")).toBe(String(SELECTION_STROKE_WIDTH));
    expect(rects[1].getAttribute("data-stroke-width")).toBe(String(LAYER_COLORS.words.strokeWidth));
  });

  it("Rect has listening=false and perfectDrawEnabled=false (perf pinning)", () => {
    const { getAllByTestId } = render(
      <Stage>
        <Layer>
          <BBoxOverlay layer="words" items={mkItems(1)} />
        </Layer>
      </Stage>,
    );
    const rect = getAllByTestId("konva-rect")[0];
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

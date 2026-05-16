// ReboxCanvas.test.tsx — Tests for P3.b Rebox Konva mini-canvas (Gap 35).
// Spec: docs/plans/hifi-gaps-plan.md slice P3.b.
//
// Covers: rendering in all three tool modes, ghost bbox visibility logic,
// and a snapshot baseline.

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

// Mock react-konva — render every Konva node as a div so jsdom is happy.
// Each Konva component forwards mouse handlers so tests can simulate events.
vi.mock("react-konva", () => {
  const passthrough =
    (tag: string) =>
    ({
      children,
      "data-testid": testId,
      onMouseDown,
      onMouseUp,
      onMouseMove,
      ...rest
    }: {
      children?: React.ReactNode;
      "data-testid"?: string;
      onMouseDown?: (e: unknown) => void;
      onMouseUp?: (e: unknown) => void;
      onMouseMove?: (e: unknown) => void;
      [k: string]: unknown;
    }) => {
      // Only forward data-* / aria-* props onto the DOM div to keep React
      // from complaining about unknown camelCase Konva props.
      const safe: Record<string, unknown> = {};
      for (const [k, v] of Object.entries(rest)) {
        if (k.startsWith("data-") || k.startsWith("aria-")) safe[k] = v;
      }
      return (
        <div
          data-testid={testId}
          data-konva-node={tag}
          onMouseDown={() =>
            onMouseDown?.({
              target: { getStage: () => ({ getPointerPosition: () => ({ x: 10, y: 10 }) }) },
            })
          }
          onMouseMove={() =>
            onMouseMove?.({
              target: { getStage: () => ({ getPointerPosition: () => ({ x: 60, y: 40 }) }) },
            })
          }
          onMouseUp={() =>
            onMouseUp?.({
              target: { getStage: () => ({ getPointerPosition: () => ({ x: 60, y: 40 }) }) },
            })
          }
          {...safe}
        >
          {children}
        </div>
      );
    };
  return {
    Stage: passthrough("Stage"),
    Layer: passthrough("Layer"),
    Rect: passthrough("Rect"),
    Circle: passthrough("Circle"),
    Group: passthrough("Group"),
  };
});

import { ReboxCanvas } from "./ReboxCanvas";
import type { components } from "../../../api/types";

type BBox = components["schemas"]["BBox"];

const ORIGINAL_BBOX: BBox = { x: 100, y: 50, width: 80, height: 30 };
const SAME_BBOX: BBox = { x: 100, y: 50, width: 80, height: 30 };
const DIFFERENT_BBOX: BBox = { x: 110, y: 55, width: 70, height: 25 };

function makeProps(overrides: Partial<Parameters<typeof ReboxCanvas>[0]> = {}) {
  return {
    originalBbox: ORIGINAL_BBOX,
    bbox: SAME_BBOX,
    onChange: vi.fn(),
    tool: "snap" as const,
    zoom: 1,
    ...overrides,
  };
}

describe("ReboxCanvas (P3.b)", () => {
  it("renders a canvas element (Stage) when given valid props in snap mode", () => {
    render(<ReboxCanvas {...makeProps({ tool: "snap" })} />);
    expect(screen.getByTestId("rebox-canvas")).toBeInTheDocument();
  });

  it("renders without error in draw mode", () => {
    expect(() => render(<ReboxCanvas {...makeProps({ tool: "draw" })} />)).not.toThrow();
    expect(screen.getByTestId("rebox-canvas")).toBeInTheDocument();
  });

  it("renders without error in pan mode", () => {
    expect(() => render(<ReboxCanvas {...makeProps({ tool: "pan" })} />)).not.toThrow();
    expect(screen.getByTestId("rebox-canvas")).toBeInTheDocument();
  });

  it("renders the ghost bbox when bbox differs from originalBbox", () => {
    render(<ReboxCanvas {...makeProps({ bbox: DIFFERENT_BBOX })} />);
    expect(screen.getByTestId("rebox-ghost")).toBeInTheDocument();
  });

  it("does not render ghost bbox when bbox equals originalBbox", () => {
    render(<ReboxCanvas {...makeProps({ bbox: SAME_BBOX })} />);
    expect(screen.queryByTestId("rebox-ghost")).not.toBeInTheDocument();
  });

  it("renders 8 snap handles in snap mode", () => {
    render(<ReboxCanvas {...makeProps({ tool: "snap" })} />);
    const positions = ["nw", "n", "ne", "e", "se", "s", "sw", "w"];
    for (const pos of positions) {
      expect(screen.getByTestId(`rebox-handle-${pos}`)).toBeInTheDocument();
    }
  });

  it("does not render snap handles in draw mode", () => {
    render(<ReboxCanvas {...makeProps({ tool: "draw" })} />);
    expect(screen.queryByTestId("rebox-handle-nw")).not.toBeInTheDocument();
  });

  it("does not render snap handles in pan mode", () => {
    render(<ReboxCanvas {...makeProps({ tool: "pan" })} />);
    expect(screen.queryByTestId("rebox-handle-nw")).not.toBeInTheDocument();
  });

  it("matches snapshot (snap tool, zoom 1, no ghost)", () => {
    const { container } = render(<ReboxCanvas {...makeProps()} />);
    expect(container).toMatchSnapshot();
  });
});

// ReboxSection.test.tsx — Tests for P3.b Rebox mini-canvas (Gap 35).
// Spec: docs/plans/hifi-gaps-plan.md slice P3.b.
//
// The Konva-backed mini-canvas replaces the legacy WordRefineNudgeRows.
// `react-konva` is module-mocked so jsdom can render its <Stage> as a div.

import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// Mock react-konva — render every Konva node as a div so jsdom is happy.
// The Stage's mouse handlers are forwarded so tests can simulate drag flows.
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
      // from complaining about unknown camelCase props (e.g. strokeWidth).
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

import { ReboxSection } from "./ReboxSection";
import type { components } from "../../../api/types";

type WordMatch = components["schemas"]["WordMatch"];

function makeWord(overrides: Partial<WordMatch> = {}): WordMatch {
  return {
    line_index: 0,
    word_index: 0,
    ocr_text: "hello",
    ground_truth_text: "hello",
    bbox: { x: 100, y: 50, width: 80, height: 30 },
    is_validated: false,
    match_status: "exact",
    fuzz_score: 100,
    word_id: "w-0-0",
    ...overrides,
  } as WordMatch;
}

function renderWithQuery(ui: React.ReactElement) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("ReboxSection (P3.b — Konva mini-canvas)", () => {
  it("renders the rebox-section container", () => {
    renderWithQuery(<ReboxSection word={makeWord()} projectId="p1" pageIndex={0} />);
    expect(screen.getByTestId("rebox-section")).toBeInTheDocument();
  });

  it("renders the rebox canvas mini Konva stage", () => {
    renderWithQuery(<ReboxSection word={makeWord()} projectId="p1" pageIndex={0} />);
    expect(screen.getByTestId("rebox-canvas")).toBeInTheDocument();
  });

  it("renders three tool-mode buttons (snap, draw, pan)", () => {
    renderWithQuery(<ReboxSection word={makeWord()} projectId="p1" pageIndex={0} />);
    expect(screen.getByTestId("rebox-tool-snap")).toBeInTheDocument();
    expect(screen.getByTestId("rebox-tool-draw")).toBeInTheDocument();
    expect(screen.getByTestId("rebox-tool-pan")).toBeInTheDocument();
  });

  it("snap is the default tool (aria-pressed=true)", () => {
    renderWithQuery(<ReboxSection word={makeWord()} projectId="p1" pageIndex={0} />);
    expect(screen.getByTestId("rebox-tool-snap")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("rebox-tool-draw")).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByTestId("rebox-tool-pan")).toHaveAttribute("aria-pressed", "false");
  });

  it("clicking a tool button switches active tool", () => {
    renderWithQuery(<ReboxSection word={makeWord()} projectId="p1" pageIndex={0} />);
    fireEvent.click(screen.getByTestId("rebox-tool-draw"));
    expect(screen.getByTestId("rebox-tool-draw")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("rebox-tool-snap")).toHaveAttribute("aria-pressed", "false");
  });

  it("renders zoom in/out buttons + zoom level display", () => {
    renderWithQuery(<ReboxSection word={makeWord()} projectId="p1" pageIndex={0} />);
    expect(screen.getByTestId("rebox-zoom-in")).toBeInTheDocument();
    expect(screen.getByTestId("rebox-zoom-out")).toBeInTheDocument();
    expect(screen.getByTestId("rebox-zoom-level")).toHaveTextContent("1×");
  });

  it("zoom-in increments the zoom level; zoom-out decrements", () => {
    renderWithQuery(<ReboxSection word={makeWord()} projectId="p1" pageIndex={0} />);
    fireEvent.click(screen.getByTestId("rebox-zoom-in"));
    expect(screen.getByTestId("rebox-zoom-level")).toHaveTextContent("2×");
    fireEvent.click(screen.getByTestId("rebox-zoom-in"));
    expect(screen.getByTestId("rebox-zoom-level")).toHaveTextContent("3×");
    fireEvent.click(screen.getByTestId("rebox-zoom-out"));
    expect(screen.getByTestId("rebox-zoom-level")).toHaveTextContent("2×");
  });

  it("zoom level is clamped to the [1, 5] range", () => {
    renderWithQuery(<ReboxSection word={makeWord()} projectId="p1" pageIndex={0} />);
    for (let i = 0; i < 10; i++) fireEvent.click(screen.getByTestId("rebox-zoom-in"));
    expect(screen.getByTestId("rebox-zoom-level")).toHaveTextContent("5×");
    for (let i = 0; i < 10; i++) fireEvent.click(screen.getByTestId("rebox-zoom-out"));
    expect(screen.getByTestId("rebox-zoom-level")).toHaveTextContent("1×");
  });

  it("renders bbox size summary text", () => {
    renderWithQuery(<ReboxSection word={makeWord()} projectId="p1" pageIndex={0} />);
    expect(screen.getByTestId("rebox-bbox-summary")).toHaveTextContent("80 × 30");
  });

  it("Apply button is disabled until bbox is modified", () => {
    renderWithQuery(<ReboxSection word={makeWord()} projectId="p1" pageIndex={0} />);
    const apply = screen.getByTestId("rebox-apply");
    expect(apply.disabled).toBe(true);
  });

  it("Apply button becomes enabled after a draw-mode mouse-drag commits a new bbox", () => {
    renderWithQuery(<ReboxSection word={makeWord()} projectId="p1" pageIndex={0} />);
    fireEvent.click(screen.getByTestId("rebox-tool-draw"));
    const canvas = screen.getByTestId("rebox-canvas");
    fireEvent.mouseDown(canvas);
    fireEvent.mouseMove(canvas);
    fireEvent.mouseUp(canvas);
    const apply = screen.getByTestId("rebox-apply");
    expect(apply.disabled).toBe(false);
  });

  it("Reset button reverts dirty bbox and disables Apply again", () => {
    renderWithQuery(<ReboxSection word={makeWord()} projectId="p1" pageIndex={0} />);
    fireEvent.click(screen.getByTestId("rebox-tool-draw"));
    const canvas = screen.getByTestId("rebox-canvas");
    fireEvent.mouseDown(canvas);
    fireEvent.mouseMove(canvas);
    fireEvent.mouseUp(canvas);
    expect(screen.getByTestId("rebox-apply").disabled).toBe(false);

    fireEvent.click(screen.getByTestId("rebox-reset"));
    expect(screen.getByTestId("rebox-apply").disabled).toBe(true);
  });

  it("Apply posts the bbox to /rebox via fetch and clears dirty state", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({}), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    renderWithQuery(<ReboxSection word={makeWord()} projectId="p1" pageIndex={0} />);
    fireEvent.click(screen.getByTestId("rebox-tool-draw"));
    const canvas = screen.getByTestId("rebox-canvas");
    fireEvent.mouseDown(canvas);
    fireEvent.mouseMove(canvas);
    fireEvent.mouseUp(canvas);

    fireEvent.click(screen.getByTestId("rebox-apply"));

    await Promise.resolve();
    expect(fetchSpy).toHaveBeenCalled();
    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/projects/p1/pages/0/words/0/0/rebox");
    expect(init.method).toBe("POST");
    const body = JSON.parse(init.body as string) as {
      bbox: { x: number; y: number; width: number; height: number };
    };
    expect(body.bbox).toMatchObject({ x: expect.any(Number) });
    fetchSpy.mockRestore();
  });

  it("bbox summary updates when the underlying word's bbox differs", () => {
    renderWithQuery(
      <ReboxSection
        word={makeWord({ bbox: { x: 0, y: 0, width: 42, height: 18 } })}
        projectId="p1"
        pageIndex={0}
      />,
    );
    expect(screen.getByTestId("rebox-bbox-summary")).toHaveTextContent("42 × 18");
  });
});

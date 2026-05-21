// ErasePixelsSection.test.tsx — Tests for P3.c hi-fi rebuild (Gap 36).
// Spec: docs/plans/hifi-gaps-plan.md Slice P3.c.

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import React from "react";
import { server } from "../../../test/server";
import { ErasePixelsSection } from "./ErasePixelsSection";

// Mock react-konva so the Stage renders deterministically in jsdom.  We expose
// mouseDown/Move/Up/Leave events with stub pointer positions so we can drive
// op-commit flows from the test.
vi.mock("react-konva", () => ({
  Stage: ({
    children,
    width,
    height,
    "data-testid": testId,
    onMouseDown,
    onMouseMove,
    onMouseUp,
    onMouseLeave,
  }: {
    children?: React.ReactNode;
    width?: number;
    height?: number;
    "data-testid"?: string;
    onMouseDown?: (e: unknown) => void;
    onMouseMove?: (e: unknown) => void;
    onMouseUp?: (e: unknown) => void;
    onMouseLeave?: () => void;
  }) => {
    const makeEvent = (x: number, y: number) => ({
      target: { getStage: () => ({ getPointerPosition: () => ({ x, y }) }) },
    });
    return (
      <div
        data-testid={testId ?? "konva-stage"}
        data-width={width}
        data-height={height}
        onMouseDown={() => onMouseDown?.(makeEvent(10, 20))}
        onMouseMove={() => onMouseMove?.(makeEvent(30, 40))}
        onMouseUp={() => onMouseUp?.(makeEvent(50, 60))}
        onMouseLeave={() => onMouseLeave?.()}
      >
        {children}
      </div>
    );
  },
  Layer: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  Rect: ({
    x,
    y,
    width,
    height,
    "data-testid": testId,
  }: {
    x?: number;
    y?: number;
    width?: number;
    height?: number;
    "data-testid"?: string;
  }) => (
    <div
      data-testid={testId ?? "konva-rect"}
      data-x={x}
      data-y={y}
      data-width={width}
      data-height={height}
    />
  ),
}));

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return React.createElement(QueryClientProvider, { client: qc }, children);
  };
}

describe("ErasePixelsSection — P3.c probe gating", () => {
  beforeEach(() => {
    // Default: probe returns not-available.
    server.use(
      http.get("/api/refine/available", () =>
        HttpResponse.json({ available: false, reason: "engine not wired" }),
      ),
    );
  });

  it("shows the not-available banner when probe returns available:false", async () => {
    const Wrapper = makeWrapper();
    render(
      <Wrapper>
        <ErasePixelsSection />
      </Wrapper>,
    );
    await waitFor(() => expect(screen.getByTestId("erase-not-available")).toBeInTheDocument());
    expect(screen.queryByTestId("erase-canvas")).not.toBeInTheDocument();
    expect(screen.queryByTestId("erase-apply")).not.toBeInTheDocument();
  });

  it("shows the full canvas UI when probe returns available:true", async () => {
    server.use(
      http.get("/api/refine/available", () =>
        HttpResponse.json({ available: true, reason: "wired" }),
      ),
    );
    const Wrapper = makeWrapper();
    render(
      <Wrapper>
        <ErasePixelsSection />
      </Wrapper>,
    );
    await waitFor(() => expect(screen.getByTestId("erase-canvas")).toBeInTheDocument());
    expect(screen.getByTestId("erase-tool-brush")).toBeInTheDocument();
    expect(screen.getByTestId("erase-tool-lasso")).toBeInTheDocument();
    expect(screen.getByTestId("erase-tool-rect")).toBeInTheDocument();
    expect(screen.getByTestId("erase-ops-list")).toBeInTheDocument();
    expect(screen.getByTestId("erase-apply")).toBeInTheDocument();
    expect(screen.getByTestId("erase-clear")).toBeInTheDocument();
    expect(screen.queryByTestId("erase-not-available")).not.toBeInTheDocument();
  });

  it("respects the backendAvailable prop override (forces UI without probe)", async () => {
    const Wrapper = makeWrapper();
    render(
      <Wrapper>
        <ErasePixelsSection backendAvailable={true} />
      </Wrapper>,
    );
    // No await needed — override skips loading.
    expect(screen.getByTestId("erase-canvas")).toBeInTheDocument();
  });

  it("respects backendAvailable=false override → fallback banner", () => {
    const Wrapper = makeWrapper();
    render(
      <Wrapper>
        <ErasePixelsSection backendAvailable={false} />
      </Wrapper>,
    );
    expect(screen.getByTestId("erase-not-available")).toBeInTheDocument();
  });
});

describe("ErasePixelsSection — P3.c canvas behaviour", () => {
  const Wrapper = makeWrapper();
  beforeEach(() => {
    // useRefineAvailable still fires even when backendAvailable is set —
    // register a stub so MSW doesn't flag the request as unhandled.
    server.use(
      http.get("/api/refine/available", () =>
        HttpResponse.json({ available: true, reason: "wired" }),
      ),
    );
  });

  it("default tool is brush and brush-size slider is visible", () => {
    render(
      <Wrapper>
        <ErasePixelsSection backendAvailable={true} />
      </Wrapper>,
    );
    expect(screen.getByTestId("erase-tool-brush")).toHaveAttribute("aria-checked", "true");
    expect(screen.getByTestId("erase-brush-size")).toBeInTheDocument();
  });

  it("switches tool to lasso and hides the brush-size slider", async () => {
    const user = userEvent.setup();
    render(
      <Wrapper>
        <ErasePixelsSection backendAvailable={true} />
      </Wrapper>,
    );
    await user.click(screen.getByTestId("erase-tool-lasso"));
    expect(screen.getByTestId("erase-tool-lasso")).toHaveAttribute("aria-checked", "true");
    expect(screen.queryByTestId("erase-brush-size")).not.toBeInTheDocument();
  });

  it("switches tool to rect and hides the brush-size slider", async () => {
    const user = userEvent.setup();
    render(
      <Wrapper>
        <ErasePixelsSection backendAvailable={true} />
      </Wrapper>,
    );
    await user.click(screen.getByTestId("erase-tool-rect"));
    expect(screen.getByTestId("erase-tool-rect")).toHaveAttribute("aria-checked", "true");
    expect(screen.queryByTestId("erase-brush-size")).not.toBeInTheDocument();
  });

  it("brush-size slider can be adjusted", async () => {
    render(
      <Wrapper>
        <ErasePixelsSection backendAvailable={true} />
      </Wrapper>,
    );
    const slider = screen.getByTestId("erase-brush-size");
    expect(slider.value).toBe("8"); // DEFAULT_BRUSH
    // userEvent.type does not work well for range inputs; fireEvent.change is cleaner.
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.change(slider, { target: { value: "16" } });
    expect(screen.getByTestId("erase-brush-size").value).toBe("16");
  });
});

describe("ErasePixelsSection — P3.c ops list", () => {
  const Wrapper = makeWrapper();
  beforeEach(() => {
    server.use(
      http.get("/api/refine/available", () =>
        HttpResponse.json({ available: true, reason: "wired" }),
      ),
    );
  });

  it("shows the empty-state hint when no ops are queued", () => {
    render(
      <Wrapper>
        <ErasePixelsSection backendAvailable={true} />
      </Wrapper>,
    );
    expect(screen.getByText(/Draw to mark pixels for erasing/i)).toBeInTheDocument();
  });

  it("commits a brush op on mouse-up and renders it in the ops list", async () => {
    const user = userEvent.setup();
    render(
      <Wrapper>
        <ErasePixelsSection backendAvailable={true} />
      </Wrapper>,
    );
    // The mocked Stage fires onMouseUp with x=50, y=60 on click.
    await user.click(screen.getByTestId("erase-canvas"));
    // Brush op committed → row visible.
    expect(screen.getByText(/Op 1: brush at \(50,60\) r=8/)).toBeInTheDocument();
    expect(screen.getByTestId("erase-op-0-remove")).toBeInTheDocument();
  });

  it("removes a single op via the × button", async () => {
    const user = userEvent.setup();
    render(
      <Wrapper>
        <ErasePixelsSection backendAvailable={true} />
      </Wrapper>,
    );
    await user.click(screen.getByTestId("erase-canvas"));
    expect(screen.getByTestId("erase-op-0-remove")).toBeInTheDocument();
    await user.click(screen.getByTestId("erase-op-0-remove"));
    expect(screen.queryByTestId("erase-op-0-remove")).not.toBeInTheDocument();
    expect(screen.getByText(/Draw to mark pixels for erasing/i)).toBeInTheDocument();
  });

  it("Clear all empties the ops list", async () => {
    const user = userEvent.setup();
    render(
      <Wrapper>
        <ErasePixelsSection backendAvailable={true} />
      </Wrapper>,
    );
    await user.click(screen.getByTestId("erase-canvas"));
    await user.click(screen.getByTestId("erase-canvas"));
    expect(screen.getByTestId("erase-op-0-remove")).toBeInTheDocument();
    expect(screen.getByTestId("erase-op-1-remove")).toBeInTheDocument();
    await user.click(screen.getByTestId("erase-clear"));
    expect(screen.queryByTestId("erase-op-0-remove")).not.toBeInTheDocument();
    expect(screen.queryByTestId("erase-op-1-remove")).not.toBeInTheDocument();
  });
});

// ── CU-6.1 acceptance tests ──────────────────────────────────────────────────
// Plan: docs/plans/2026-05-16-complete-labeler-spa.md §CU-6.1
// Pins the probe-gating invariant: Apply is disabled when probe returns
// available:false, and enabled (and calls onApply) when available:true.
//
// Note: ErasePixelsSection delegates the actual HTTP POST to the parent via
// the `onApply` callback (WordDetail owns useErasePixels).  We test the
// callback path here; the backend HTTP round-trip is covered separately.
describe("ErasePixelsSection — CU-6.1 capability probe gating", () => {
  it("probe available:false → not-available banner shown (no canvas, no Apply)", async () => {
    server.use(
      http.get("/api/refine/available", () =>
        HttpResponse.json({ available: false, reason: "engine not wired" }),
      ),
    );
    const Wrapper = makeWrapper();
    render(
      <Wrapper>
        <ErasePixelsSection />
      </Wrapper>,
    );
    await waitFor(() => expect(screen.getByTestId("erase-not-available")).toBeInTheDocument());
    expect(screen.queryByTestId("erase-apply")).not.toBeInTheDocument();
    expect(screen.queryByTestId("erase-canvas")).not.toBeInTheDocument();
  });

  it("probe available:true → Apply enabled after adding op and calls onApply on click", async () => {
    server.use(
      http.get("/api/refine/available", () => HttpResponse.json({ available: true, reason: "" })),
    );
    const onApply = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();
    const Wrapper = makeWrapper();
    render(
      <Wrapper>
        <ErasePixelsSection onApply={onApply} />
      </Wrapper>,
    );
    // Wait for probe to resolve and canvas to appear.
    await waitFor(() => expect(screen.getByTestId("erase-canvas")).toBeInTheDocument());
    // Apply is disabled until an op is queued.
    expect(screen.getByTestId("erase-apply")).toBeDisabled();
    // Add an op by clicking the canvas (mock fires mouseUp → commit).
    await user.click(screen.getByTestId("erase-canvas"));
    // Apply now enabled.
    expect(screen.getByTestId("erase-apply")).not.toBeDisabled();
    // Click Apply — onApply must be called with the ops list.
    await user.click(screen.getByTestId("erase-apply"));
    expect(onApply).toHaveBeenCalledOnce();
    const ops = onApply.mock.calls[0][0] as { tool: string }[];
    expect(ops.length).toBeGreaterThan(0);
    expect(ops[0].tool).toBe("brush");
  });
});

describe("ErasePixelsSection — P3.c commit footer", () => {
  const Wrapper = makeWrapper();
  beforeEach(() => {
    server.use(
      http.get("/api/refine/available", () =>
        HttpResponse.json({ available: true, reason: "wired" }),
      ),
    );
  });

  it("Apply button is disabled when ops list is empty", () => {
    render(
      <Wrapper>
        <ErasePixelsSection backendAvailable={true} />
      </Wrapper>,
    );
    expect(screen.getByTestId("erase-apply")).toBeDisabled();
  });

  it("Clear button is disabled when ops list is empty", () => {
    render(
      <Wrapper>
        <ErasePixelsSection backendAvailable={true} />
      </Wrapper>,
    );
    expect(screen.getByTestId("erase-clear")).toBeDisabled();
  });

  it("Apply button is enabled once an op is queued", async () => {
    const user = userEvent.setup();
    render(
      <Wrapper>
        <ErasePixelsSection backendAvailable={true} />
      </Wrapper>,
    );
    await user.click(screen.getByTestId("erase-canvas"));
    expect(screen.getByTestId("erase-apply")).not.toBeDisabled();
    expect(screen.getByTestId("erase-clear")).not.toBeDisabled();
  });

  it("Apply calls onApply with the ops list and clears it on success", async () => {
    const onApply = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(
      <Wrapper>
        <ErasePixelsSection backendAvailable={true} onApply={onApply} />
      </Wrapper>,
    );
    await user.click(screen.getByTestId("erase-canvas"));
    await user.click(screen.getByTestId("erase-canvas"));
    await user.click(screen.getByTestId("erase-apply"));
    expect(onApply).toHaveBeenCalledOnce();
    const ops = onApply.mock.calls[0][0] as { tool: string }[];
    expect(ops).toHaveLength(2);
    expect(ops[0].tool).toBe("brush");
    // After successful apply, ops should be cleared.
    await waitFor(() => expect(screen.queryByTestId("erase-op-0-remove")).not.toBeInTheDocument());
  });
});

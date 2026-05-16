// CharFixerSection.test.tsx — Tests for Slice 20 char-by-char editor +
// P4.b (Gap 39) per-char bbox canvas + drag handles + apply button.
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 20.
// Spec: docs/plans/hifi-gaps-plan.md Slice P4.b.

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import React from "react";
import { render, screen, waitFor, act, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// Mock react-konva so CharFixerCanvas renders deterministic <div>s carrying
// the data-testid props we exercise (the real Stage/Layer/Rect tree would
// otherwise need a canvas, which jsdom doesn't provide). The mock surfaces
// onClick + an onDragMove escape-hatch (callable via a custom event) so we
// can drive selection and handle-drag flows from the tests.
vi.mock("react-konva", () => ({
  Stage: ({
    children,
    width,
    height,
    "data-testid": testId,
  }: {
    children?: React.ReactNode;
    width?: number;
    height?: number;
    "data-testid"?: string;
  }) =>
    React.createElement(
      "div",
      { "data-testid": testId ?? "konva-stage", "data-width": width, "data-height": height },
      children,
    ),
  Layer: ({ children }: { children?: React.ReactNode }) =>
    React.createElement(React.Fragment, null, children),
  Rect: ({
    x,
    y,
    width,
    height,
    "data-testid": testId,
    onClick,
    onDragMove,
  }: {
    x?: number;
    y?: number;
    width?: number;
    height?: number;
    "data-testid"?: string;
    onClick?: () => void;
    onDragMove?: (e: unknown) => void;
  }) =>
    React.createElement("div", {
      "data-testid": testId ?? "konva-rect",
      "data-x": x,
      "data-y": y,
      "data-width": width,
      "data-height": height,
      onClick,
      // Surface onDragMove through a synthetic DOM event so tests can fire it
      // (we attach a custom "konvadrag" handler below via dispatchEvent).
      onMouseDown: (_ev: React.MouseEvent) => {
        if (!onDragMove) return;
        const fakeEvent = {
          target: {
            getStage: () => ({
              getPointerPosition: () => ({ x: 200, y: 100 }),
            }),
          },
        };
        onDragMove(fakeEvent);
      },
    }),
}));

import { CharFixerSection } from "./CharFixerSection";
import { server } from "../../../test/server";
import type { components } from "../../../api/types";

type WordMatch = components["schemas"]["WordMatch"];

function makeWord(ocr = "Hello", gt = "Hello"): WordMatch {
  return {
    line_index: 0,
    word_index: 0,
    ocr_text: ocr,
    ground_truth_text: gt,
    match_status: ocr === gt ? "exact" : "mismatch",
    normalized_match: false,
    is_validated: false,
    bbox: { x: 0, y: 0, width: 10, height: 10 },
  };
}

function makePageResponse(text: string) {
  return {
    project_id: "p1",
    page_index: 0,
    line_filter: "all",
    generation: 1,
    line_matches: [
      {
        line_index: 0,
        paragraph_index: 0,
        ocr_line_text: text,
        ground_truth_line_text: text,
        word_matches: [makeWord(text, text)],
        overall_match_status: "exact",
        exact_count: 1,
        fuzzy_count: 0,
        mismatch_count: 0,
        unmatched_gt_count: 0,
        unmatched_ocr_count: 0,
        validated_word_count: 0,
        total_word_count: 1,
        is_fully_validated: false,
      },
    ],
  };
}

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

function renderSection(word = makeWord()) {
  const qc = makeQueryClient();
  return {
    ...render(
      <QueryClientProvider client={qc}>
        <CharFixerSection word={word} projectId="p1" pageIndex={0} />
      </QueryClientProvider>,
    ),
    qc,
  };
}

describe("CharFixerSection (Slice 20)", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders outer container with data-testid=char-fixer-section", () => {
    renderSection();
    expect(screen.getByTestId("char-fixer-section")).toBeInTheDocument();
  });

  it("renders one editable input per char with the GT char as initial value", () => {
    renderSection(makeWord("Hello", "Hello"));
    expect((screen.getByTestId("char-fixer-input-0") as HTMLInputElement).value).toBe("H");
    expect((screen.getByTestId("char-fixer-input-1") as HTMLInputElement).value).toBe("e");
    expect((screen.getByTestId("char-fixer-input-4") as HTMLInputElement).value).toBe("o");
  });

  it("renders the original OCR char as a label next to each input", () => {
    renderSection(makeWord("Hello", "Hello"));
    expect(screen.getByTestId("char-fixer-orig-0")).toHaveTextContent("H");
    expect(screen.getByTestId("char-fixer-orig-4")).toHaveTextContent("o");
  });

  it("marks mismatched cells with data-mismatch=true", () => {
    renderSection(makeWord("Hellp", "Hello"));
    expect(screen.getByTestId("char-fixer-cell-4")).toHaveAttribute("data-mismatch", "true");
    expect(screen.getByTestId("char-fixer-cell-0")).not.toHaveAttribute("data-mismatch", "true");
  });

  it("editing a cell debounces and POSTs the new GT", async () => {
    const handler = vi.fn(async (info: { request: Request }) => {
      const body = (await info.request.json()) as { text: string };
      return HttpResponse.json(makePageResponse(body.text));
    });
    server.use(http.post("/api/projects/p1/pages/0/words/0/0/gt", handler));

    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderSection(makeWord("Hello", "Hello"));

    const input4 = screen.getByTestId("char-fixer-input-4") as HTMLInputElement;
    await user.clear(input4);
    await user.type(input4, "0");

    // Debounce: should not have fired yet
    expect(handler).not.toHaveBeenCalled();

    // Advance past debounce
    await act(async () => {
      vi.advanceTimersByTime(500);
    });

    await waitFor(() => expect(handler).toHaveBeenCalled());
  });

  it("renders an Open Unicode picker button", () => {
    renderSection();
    expect(screen.getByTestId("char-fixer-open-picker-button")).toBeInTheDocument();
  });

  it("clicking Open Unicode picker shows the picker", async () => {
    vi.useRealTimers();
    const user = userEvent.setup();
    renderSection();
    expect(screen.queryByTestId("unicode-picker")).not.toBeInTheDocument();
    await user.click(screen.getByTestId("char-fixer-open-picker-button"));
    expect(screen.getByTestId("unicode-picker")).toBeInTheDocument();
  });
});

describe("CharFixerSection — P4.b bbox canvas + handles (Gap 39)", () => {
  beforeEach(() => {
    vi.useRealTimers();
  });

  it("renders the canvas with one rect per char range", () => {
    renderSection(makeWord("abc", "abc"));
    expect(screen.getByTestId("charfixer-canvas")).toBeInTheDocument();
    expect(screen.getByTestId("charfixer-range-0")).toBeInTheDocument();
    expect(screen.getByTestId("charfixer-range-1")).toBeInTheDocument();
    expect(screen.getByTestId("charfixer-range-2")).toBeInTheDocument();
    expect(screen.queryByTestId("charfixer-range-3")).not.toBeInTheDocument();
  });

  it("renders the detail strip with the selected range's text by default", () => {
    renderSection(makeWord("abc", "abc"));
    expect(screen.getByTestId("charfixer-detail-strip")).toBeInTheDocument();
    expect(screen.getByTestId("charfixer-detail-text")).toHaveTextContent("a");
  });

  it("clicking a range rectangle updates the detail strip", async () => {
    const user = userEvent.setup();
    renderSection(makeWord("abc", "abc"));
    await user.click(screen.getByTestId("charfixer-range-2"));
    expect(screen.getByTestId("charfixer-detail-text")).toHaveTextContent("c");
  });

  it("Apply button is disabled until a bbox is modified", async () => {
    const user = userEvent.setup();
    renderSection(makeWord("ab", "ab"));
    const apply = screen.getByTestId("charfixer-apply") as HTMLButtonElement;
    expect(apply).toBeDisabled();

    // Edit the x1 coordinate input — that's a bbox modification.
    const x1 = screen.getByTestId("charfixer-detail-x1") as HTMLInputElement;
    await user.clear(x1);
    await user.type(x1, "42");

    expect((screen.getByTestId("charfixer-apply") as HTMLButtonElement).disabled).toBe(false);
  });

  it("editing a coordinate input updates the bbox in local state", async () => {
    const user = userEvent.setup();
    renderSection(makeWord("ab", "ab"));
    const x1Before = (screen.getByTestId("charfixer-detail-x1") as HTMLInputElement).value;
    expect(x1Before).toBe("0");

    const x1 = screen.getByTestId("charfixer-detail-x1") as HTMLInputElement;
    await user.clear(x1);
    await user.type(x1, "3");

    expect((screen.getByTestId("charfixer-detail-x1") as HTMLInputElement).value).toBe("3");
  });

  it("dragging a handle marks the bbox dirty (enables Apply)", () => {
    renderSection(makeWord("ab", "ab"));
    expect((screen.getByTestId("charfixer-apply") as HTMLButtonElement).disabled).toBe(true);

    // The Konva mock surfaces onDragMove via onMouseDown on the handle rect.
    fireEvent.mouseDown(screen.getByTestId("charfixer-range-0-handle-se"));

    expect((screen.getByTestId("charfixer-apply") as HTMLButtonElement).disabled).toBe(false);
  });

  it("clicking Apply resets the dirty flag (button disables again)", async () => {
    const user = userEvent.setup();
    renderSection(makeWord("ab", "ab"));
    const x1 = screen.getByTestId("charfixer-detail-x1") as HTMLInputElement;
    await user.clear(x1);
    await user.type(x1, "7");
    const apply = screen.getByTestId("charfixer-apply") as HTMLButtonElement;
    expect(apply.disabled).toBe(false);

    await user.click(apply);
    expect((screen.getByTestId("charfixer-apply") as HTMLButtonElement).disabled).toBe(true);
  });

  it("renders no canvas when the word has no OCR text", () => {
    renderSection(makeWord("", ""));
    expect(screen.queryByTestId("charfixer-canvas")).not.toBeInTheDocument();
    expect(screen.queryByTestId("charfixer-detail-strip")).not.toBeInTheDocument();
  });
});

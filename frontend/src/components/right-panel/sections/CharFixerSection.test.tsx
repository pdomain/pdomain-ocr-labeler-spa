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

// Mock lib/toast so we can assert toast.error calls without the real sonner DOM.
vi.mock("../../../lib/toast", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    warn: vi.fn(),
    info: vi.fn(),
  },
}));

import { toast } from "../../../lib/toast";

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
    expect(screen.getByTestId("char-fixer-input-0").value).toBe("H");
    expect(screen.getByTestId("char-fixer-input-1").value).toBe("e");
    expect(screen.getByTestId("char-fixer-input-4").value).toBe("o");
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

    const input4 = screen.getByTestId("char-fixer-input-4");
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

  // F-036 regression: unmounting before the debounce fires must still POST
  it("F-036: unmounting before debounce fires flushes the save immediately", async () => {
    let capturedText: string | null = null;
    const handler = vi.fn(async (info: { request: Request }) => {
      const body = (await info.request.json()) as { text: string };
      capturedText = body.text;
      return HttpResponse.json(makePageResponse(body.text));
    });
    server.use(http.post("/api/projects/p1/pages/0/words/0/0/gt", handler));

    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const { unmount } = renderSection(makeWord("Hello", "Hello"));

    const input4 = screen.getByTestId("char-fixer-input-4");
    await user.clear(input4);
    await user.type(input4, "0");

    // Debounce has NOT fired yet (no timer advance)
    expect(handler).not.toHaveBeenCalled();

    // Unmount simulates navigation / panel close
    unmount();

    // The flush-on-cleanup should have fired the save synchronously
    await waitFor(() => expect(handler).toHaveBeenCalledTimes(1));
    expect(capturedText).toBe("Hell0");
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
    const apply = screen.getByTestId("charfixer-apply");
    expect(apply).toBeDisabled();

    // Edit the x1 coordinate input — that's a bbox modification.
    const x1 = screen.getByTestId("charfixer-detail-x1");
    await user.clear(x1);
    await user.type(x1, "42");

    expect(screen.getByTestId("charfixer-apply").disabled).toBe(false);
  });

  it("editing a coordinate input updates the bbox in local state", async () => {
    const user = userEvent.setup();
    renderSection(makeWord("ab", "ab"));
    const x1Before = screen.getByTestId("charfixer-detail-x1").value;
    expect(x1Before).toBe("0");

    const x1 = screen.getByTestId("charfixer-detail-x1");
    await user.clear(x1);
    await user.type(x1, "3");

    expect(screen.getByTestId("charfixer-detail-x1").value).toBe("3");
  });

  it("dragging a handle marks the bbox dirty (enables Apply)", () => {
    renderSection(makeWord("ab", "ab"));
    expect(screen.getByTestId("charfixer-apply").disabled).toBe(true);

    // The Konva mock surfaces onDragMove via onMouseDown on the handle rect.
    fireEvent.mouseDown(screen.getByTestId("charfixer-range-0-handle-se"));

    expect(screen.getByTestId("charfixer-apply").disabled).toBe(false);
  });

  it("clicking Apply resets the dirty flag (button disables again)", async () => {
    server.use(
      http.post("/api/projects/p1/pages/0/words/0/0/char-bboxes", async () =>
        HttpResponse.json(makePageResponse("ab")),
      ),
    );
    const user = userEvent.setup();
    renderSection(makeWord("ab", "ab"));
    const x1 = screen.getByTestId("charfixer-detail-x1");
    await user.clear(x1);
    await user.type(x1, "7");
    const apply = screen.getByTestId("charfixer-apply");
    expect(apply.disabled).toBe(false);

    await user.click(apply);
    expect(screen.getByTestId("charfixer-apply").disabled).toBe(true);
  });

  it("clicking Apply POSTs char_bboxes to the backend", async () => {
    const handler = vi.fn(async () => HttpResponse.json(makePageResponse("ab")));
    server.use(http.post("/api/projects/p1/pages/0/words/0/0/char-bboxes", handler));
    const user = userEvent.setup();
    renderSection(makeWord("ab", "ab"));

    // Dirty the state by editing a coordinate input.
    const x1 = screen.getByTestId("charfixer-detail-x1");
    await user.clear(x1);
    await user.type(x1, "5");

    // Click Apply — should fire the POST.
    await user.click(screen.getByTestId("charfixer-apply"));

    await waitFor(() => expect(handler).toHaveBeenCalled());
  });

  it("renders no canvas when the word has no OCR text", () => {
    renderSection(makeWord("", ""));
    expect(screen.queryByTestId("charfixer-canvas")).not.toBeInTheDocument();
    expect(screen.queryByTestId("charfixer-detail-strip")).not.toBeInTheDocument();
  });
});

// ── CU-6.2 acceptance tests ───────────────────────────────────────────────────
// Plan: docs/plans/2026-05-16-complete-labeler-spa.md §CU-6.2
// Pins the char-bboxes POST body shape: { char_bboxes: [{x, y, width, height}, …] }.
describe("CharFixerSection — CU-6.2 char-bboxes POST body shape", () => {
  it("Apply POSTs { char_bboxes: [{x,y,width,height}] } shape to the backend", async () => {
    // Capture the request body so we can assert the payload shape.
    let capturedBody: unknown = undefined;
    server.use(
      http.post("/api/projects/p1/pages/0/words/0/0/char-bboxes", async (info) => {
        capturedBody = await info.request.json();
        return HttpResponse.json(makePageResponse("ab"));
      }),
    );
    const user = userEvent.setup();
    renderSection(makeWord("ab", "ab"));

    // Dirty bbox state by editing a coordinate.
    // Word "ab" with bbox {x:0,y:0,width:10,height:10}: char0 has x=0, width=5.
    // Setting x1=2 (< x2=5) is valid and produces x=2, width=3 for char0.
    const x1 = screen.getByTestId("charfixer-detail-x1");
    await user.clear(x1);
    await user.type(x1, "2");

    await user.click(screen.getByTestId("charfixer-apply"));

    await waitFor(() => expect(capturedBody).not.toBeUndefined());

    // Assert body shape: must have char_bboxes as an array of {x,y,width,height}.
    const body = capturedBody as {
      char_bboxes: { x: number; y: number; width: number; height: number }[];
    };
    expect(Array.isArray(body.char_bboxes)).toBe(true);
    expect(body.char_bboxes.length).toBeGreaterThan(0);
    const bbox0 = body.char_bboxes[0];
    expect(typeof bbox0.x).toBe("number");
    expect(typeof bbox0.y).toBe("number");
    expect(typeof bbox0.width).toBe("number");
    expect(typeof bbox0.height).toBe("number");
    // Fields must use "width"/"height" (not "w"/"h") per the BBox schema.
    expect("width" in bbox0).toBe(true);
    expect("height" in bbox0).toBe(true);
    // The modified bbox should have x=2 (we set charfixer-detail-x1 to "2").
    expect(bbox0.x).toBe(2);
  });
});

// ── F-041 regression tests ────────────────────────────────────────────────────
// Char-bbox Apply must NOT clear dirty state until the save succeeds.
// If the save fails, the Apply button should remain enabled and an error toast
// must be shown so the user knows the edit was NOT persisted.
describe("CharFixerSection — F-041 dirty state on failed save", () => {
  beforeEach(() => {
    vi.mocked(toast.error).mockClear();
  });

  it("keeps Apply enabled when the char-bboxes POST fails", async () => {
    // Return a 500 so the mutation rejects.
    server.use(
      http.post("/api/projects/p1/pages/0/words/0/0/char-bboxes", () =>
        HttpResponse.json({ detail: "internal error" }, { status: 500 }),
      ),
    );
    const user = userEvent.setup();
    renderSection(makeWord("ab", "ab"));

    // Dirty the state by editing a coordinate input.
    const x1 = screen.getByTestId("charfixer-detail-x1");
    await user.clear(x1);
    await user.type(x1, "7");
    const apply = screen.getByTestId("charfixer-apply");
    expect(apply.disabled).toBe(false);

    // Click Apply — mutation fires but server returns 500.
    await user.click(apply);

    // After the failed mutation, dirty state must remain true (button still enabled).
    await waitFor(() => expect(vi.mocked(toast.error)).toHaveBeenCalled());
    expect(screen.getByTestId("charfixer-apply").disabled).toBe(false);
  });

  it("calls toast.error when the char-bboxes POST fails", async () => {
    server.use(
      http.post("/api/projects/p1/pages/0/words/0/0/char-bboxes", () =>
        HttpResponse.json({ detail: "internal error" }, { status: 500 }),
      ),
    );
    const user = userEvent.setup();
    renderSection(makeWord("ab", "ab"));

    const x1 = screen.getByTestId("charfixer-detail-x1");
    await user.clear(x1);
    await user.type(x1, "3");

    await user.click(screen.getByTestId("charfixer-apply"));

    await waitFor(() =>
      expect(vi.mocked(toast.error)).toHaveBeenCalledWith("Failed to save char bboxes"),
    );
  });
});

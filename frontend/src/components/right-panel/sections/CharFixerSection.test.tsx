// CharFixerSection.test.tsx — Tests for Slice 20 char-by-char editor.
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 20.

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
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

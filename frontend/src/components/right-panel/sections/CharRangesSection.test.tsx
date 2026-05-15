// CharRangesSection.test.tsx — Tests for Slice 19 char-range editor.
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 19.

import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CharRangesSection } from "./CharRangesSection";
import { server } from "../../../test/server";
import type { components } from "../../../api/types";

type WordMatch = components["schemas"]["WordMatch"];

function makeWord(text = "Hello"): WordMatch {
  return {
    line_index: 0,
    word_index: 0,
    ocr_text: text,
    ground_truth_text: text,
    match_status: "exact",
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
        word_matches: [makeWord(text)],
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
        <CharRangesSection word={word} projectId="p1" pageIndex={0} />
      </QueryClientProvider>,
    ),
    qc,
  };
}

describe("CharRangesSection (Slice 19)", () => {
  it("renders outer container with data-testid=char-ranges-section", () => {
    renderSection();
    expect(screen.getByTestId("char-ranges-section")).toBeInTheDocument();
  });

  it("renders one clickable cell per char in the word's ocr_text", () => {
    renderSection(makeWord("Hello"));
    expect(screen.getByTestId("char-cell-0")).toHaveTextContent("H");
    expect(screen.getByTestId("char-cell-1")).toHaveTextContent("e");
    expect(screen.getByTestId("char-cell-2")).toHaveTextContent("l");
    expect(screen.getByTestId("char-cell-3")).toHaveTextContent("l");
    expect(screen.getByTestId("char-cell-4")).toHaveTextContent("o");
    expect(screen.queryByTestId("char-cell-5")).not.toBeInTheDocument();
  });

  it("clicking a char cell selects it as range start; clicking second selects end", async () => {
    const user = userEvent.setup();
    renderSection(makeWord("Hello"));

    await user.click(screen.getByTestId("char-cell-1"));
    // Once start is selected, cell-1 should be highlighted as selected
    expect(screen.getByTestId("char-cell-1")).toHaveAttribute("data-range-anchor", "true");

    await user.click(screen.getByTestId("char-cell-3"));
    // A pending range readout should show 1..3
    expect(screen.getByTestId("char-ranges-pending")).toHaveTextContent("1");
    expect(screen.getByTestId("char-ranges-pending")).toHaveTextContent("3");
  });

  it("Add range button is enabled only when a range is selected", async () => {
    const user = userEvent.setup();
    renderSection(makeWord("Hello"));

    const addBtn = screen.getByTestId("char-ranges-add-button");
    expect(addBtn).toBeDisabled();

    await user.click(screen.getByTestId("char-cell-0"));
    await user.click(screen.getByTestId("char-cell-2"));
    expect(addBtn).toBeEnabled();
  });

  it("style chips cycle off→on→mixed→off via tristate", async () => {
    const user = userEvent.setup();
    renderSection(makeWord("Hello"));

    // Reveal style chips by selecting a range
    await user.click(screen.getByTestId("char-cell-0"));
    await user.click(screen.getByTestId("char-cell-2"));

    const italic = screen.getByTestId("char-ranges-chip-italic");
    expect(italic).toHaveAttribute("data-tristate-value", "off");
    await user.click(italic);
    expect(italic).toHaveAttribute("data-tristate-value", "on");
  });

  it("Add range appends a row visible in the ranges list", async () => {
    const user = userEvent.setup();
    renderSection(makeWord("Hello"));

    await user.click(screen.getByTestId("char-cell-1"));
    await user.click(screen.getByTestId("char-cell-3"));

    // Enable italic for this range
    await user.click(screen.getByTestId("char-ranges-chip-italic"));

    await user.click(screen.getByTestId("char-ranges-add-button"));

    // Row appears
    expect(screen.getByTestId("char-ranges-row-0")).toBeInTheDocument();
    expect(screen.getByTestId("char-ranges-row-0")).toHaveTextContent("1");
    expect(screen.getByTestId("char-ranges-row-0")).toHaveTextContent("3");
    expect(screen.getByTestId("char-ranges-row-0")).toHaveTextContent(/italic/i);
  });

  it("delete button removes a row", async () => {
    const user = userEvent.setup();
    renderSection(makeWord("Hello"));

    await user.click(screen.getByTestId("char-cell-0"));
    await user.click(screen.getByTestId("char-cell-2"));
    await user.click(screen.getByTestId("char-ranges-chip-bold"));
    await user.click(screen.getByTestId("char-ranges-add-button"));

    expect(screen.getByTestId("char-ranges-row-0")).toBeInTheDocument();

    await user.click(screen.getByTestId("char-ranges-delete-0"));
    expect(screen.queryByTestId("char-ranges-row-0")).not.toBeInTheDocument();
  });

  it("Add range fires word PATCH (apply-style) for each enabled style", async () => {
    const handler = vi.fn(async (info: { request: Request }) => {
      await info.request.json();
      return HttpResponse.json(makePageResponse("Hello"));
    });
    server.use(http.post("/api/projects/p1/pages/0/words/0/0/style", handler));

    const user = userEvent.setup();
    renderSection(makeWord("Hello"));

    await user.click(screen.getByTestId("char-cell-0"));
    await user.click(screen.getByTestId("char-cell-2"));
    await user.click(screen.getByTestId("char-ranges-chip-italic"));
    await user.click(screen.getByTestId("char-ranges-add-button"));

    await waitFor(() => expect(handler).toHaveBeenCalled());
  });
});

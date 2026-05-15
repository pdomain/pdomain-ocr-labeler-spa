// WordDetail.test.tsx — Tests for Slice 16 word detail accordion scaffold.
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 16.

import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { WordDetail } from "./WordDetail";
import { clearSelection, selectWord } from "../../stores/selection-store";
import type { components } from "../../api/types";

type PagePayload = components["schemas"]["PagePayload"];

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

function makePage(): PagePayload {
  return {
    project_id: "p1",
    page_index: 0,
    line_filter: "all",
    generation: 0,
    line_matches: [
      {
        line_index: 0,
        paragraph_index: 0,
        ocr_line_text: "hello",
        ground_truth_line_text: "hello",
        word_matches: [
          {
            line_index: 0,
            word_index: 0,
            ocr_text: "hello",
            ground_truth_text: "hello",
            match_status: "exact",
            normalized_match: false,
            is_validated: false,
            bbox: { x: 10, y: 20, width: 30, height: 15 },
          },
        ],
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

function renderWithQuery(ui: React.ReactElement) {
  const qc = makeQueryClient();
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("WordDetail (Slice 16)", () => {
  beforeEach(() => {
    clearSelection();
  });

  it("shows 'No word selected' when no word in selection-store", () => {
    renderWithQuery(<WordDetail page={makePage()} projectId="p1" pageIndex={0} />);
    expect(screen.getByTestId("word-detail")).toHaveTextContent(/no word selected/i);
  });

  it("renders 6 accordion items when word is selected", () => {
    selectWord(0, 0);
    renderWithQuery(<WordDetail page={makePage()} projectId="p1" pageIndex={0} />);
    expect(screen.getByTestId("word-detail")).toBeInTheDocument();
    // 6 accordion triggers
    const triggers = screen.getAllByRole("button");
    const triggerLabels = triggers.map((t) => t.textContent ?? "");
    expect(triggerLabels).toEqual(
      expect.arrayContaining([
        expect.stringContaining("Bounding Box"),
        expect.stringContaining("Rebox"),
        expect.stringContaining("Erase Pixels"),
        expect.stringContaining("Structure"),
        expect.stringContaining("Char Ranges"),
        expect.stringContaining("Char Fixer"),
      ]),
    );
  });

  it("shows word identity label in the header (P2.a)", () => {
    selectWord(0, 0);
    renderWithQuery(<WordDetail page={makePage()} projectId="p1" pageIndex={0} />);
    // P2.a: header now shows "Line N · Word N", not the raw OCR text
    expect(screen.getByTestId("word-header-id")).toHaveTextContent("Line 1 · Word 1");
  });
});

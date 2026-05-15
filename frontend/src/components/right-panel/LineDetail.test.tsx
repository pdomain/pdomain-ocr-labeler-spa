// LineDetail.test.tsx — Tests for Slice 21: line-level right panel.
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 21.

import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { LineDetail } from "./LineDetail";
import { clearSelection, selectLine } from "../../stores/selection-store";
import { useUiPrefs } from "../../stores/ui-prefs";
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
        line_index: 3,
        paragraph_index: 0,
        ocr_line_text: "hello world",
        ground_truth_line_text: "hello world",
        word_matches: [
          {
            line_index: 3,
            word_index: 0,
            ocr_text: "hello",
            ground_truth_text: "hello",
            match_status: "exact",
            normalized_match: false,
            is_validated: false,
            bbox: { x: 10, y: 20, width: 30, height: 15 },
          },
          {
            line_index: 3,
            word_index: 1,
            ocr_text: "world",
            ground_truth_text: "world",
            match_status: "exact",
            normalized_match: false,
            is_validated: false,
            bbox: { x: 50, y: 20, width: 40, height: 15 },
          },
        ],
        overall_match_status: "exact",
        exact_count: 2,
        fuzzy_count: 0,
        mismatch_count: 0,
        unmatched_gt_count: 0,
        unmatched_ocr_count: 0,
        validated_word_count: 0,
        total_word_count: 2,
        is_fully_validated: false,
      },
    ],
  };
}

function renderWithQuery(ui: React.ReactElement) {
  const qc = makeQueryClient();
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("LineDetail (Slice 21)", () => {
  beforeEach(() => {
    clearSelection();
    // Reset density pref to default.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    useUiPrefs.setState({ lineWordsDensity: "cards" } as any);
  });

  it("shows 'No line selected' when no line in selection-store", () => {
    renderWithQuery(<LineDetail page={makePage()} projectId="p1" pageIndex={0} />);
    expect(screen.getByTestId("line-detail")).toHaveTextContent(/no line selected/i);
  });

  it("renders Line and Words tabs when line is selected", () => {
    selectLine(3);
    renderWithQuery(<LineDetail page={makePage()} projectId="p1" pageIndex={0} />);
    expect(screen.getByTestId("line-detail-tab-line")).toBeInTheDocument();
    expect(screen.getByTestId("line-detail-tab-words")).toBeInTheDocument();
  });

  it("tab switch shows Words content", async () => {
    const user = userEvent.setup();
    selectLine(3);
    renderWithQuery(<LineDetail page={makePage()} projectId="p1" pageIndex={0} />);
    await user.click(screen.getByTestId("line-detail-tab-words"));
    // Should show 2 word cards (default density = cards).
    expect(screen.getByTestId("line-detail-word-card-0")).toBeInTheDocument();
    expect(screen.getByTestId("line-detail-word-card-1")).toBeInTheDocument();
  });

  it("density toggle switches from Cards to Rows", async () => {
    const user = userEvent.setup();
    selectLine(3);
    renderWithQuery(<LineDetail page={makePage()} projectId="p1" pageIndex={0} />);
    await user.click(screen.getByTestId("line-detail-tab-words"));

    // Initially cards are visible.
    expect(screen.getByTestId("line-detail-word-card-0")).toBeInTheDocument();

    // Toggle to rows.
    await user.click(screen.getByTestId("line-detail-density-toggle"));
    expect(screen.queryByTestId("line-detail-word-card-0")).not.toBeInTheDocument();
    expect(screen.getByTestId("line-detail-word-row-0")).toBeInTheDocument();

    // Pref persists in store.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((useUiPrefs.getState() as any).lineWordsDensity).toBe("rows");
  });
});

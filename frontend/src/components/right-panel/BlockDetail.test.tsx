// BlockDetail.test.tsx — Tests for Slice 22: block/para-level right panel.
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 22.

import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BlockDetail } from "./BlockDetail";
import {
  clearSelection,
  selectBlock,
  selectPara,
  selectLine,
  selectionStore,
} from "../../stores/selection-store";
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
        line_index: 0,
        paragraph_index: 0,
        ocr_line_text: "first line",
        ground_truth_line_text: "first line",
        word_matches: [],
        overall_match_status: "exact",
        exact_count: 0,
        fuzzy_count: 0,
        mismatch_count: 0,
        unmatched_gt_count: 0,
        unmatched_ocr_count: 0,
        validated_word_count: 0,
        total_word_count: 0,
        is_fully_validated: false,
      },
      {
        line_index: 1,
        paragraph_index: 0,
        ocr_line_text: "second line",
        ground_truth_line_text: "second line",
        word_matches: [],
        overall_match_status: "fuzzy",
        exact_count: 0,
        fuzzy_count: 1,
        mismatch_count: 0,
        unmatched_gt_count: 0,
        unmatched_ocr_count: 0,
        validated_word_count: 0,
        total_word_count: 1,
        is_fully_validated: false,
      },
      {
        line_index: 2,
        paragraph_index: 1,
        ocr_line_text: "third line",
        ground_truth_line_text: "third line",
        word_matches: [],
        overall_match_status: "mismatch",
        exact_count: 0,
        fuzzy_count: 0,
        mismatch_count: 1,
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

describe("BlockDetail (Slice 22) — block level", () => {
  beforeEach(() => {
    clearSelection();
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    useUiPrefs.setState({ blockItemsDensity: "cards" } as any);
  });

  it("shows 'No block selected' when no block in selection-store", () => {
    renderWithQuery(<BlockDetail page={makePage()} projectId="p1" pageIndex={0} level="block" />);
    expect(screen.getByTestId("block-detail")).toHaveTextContent(/no block selected/i);
  });

  it("renders Layout and Items tabs when block is selected", () => {
    selectBlock("b1");
    renderWithQuery(<BlockDetail page={makePage()} projectId="p1" pageIndex={0} level="block" />);
    expect(screen.getByTestId("block-detail-tab-layout")).toBeInTheDocument();
    expect(screen.getByTestId("block-detail-tab-items")).toBeInTheDocument();
  });

  it("layout chip triggers state change", async () => {
    const user = userEvent.setup();
    selectBlock("b1");
    renderWithQuery(<BlockDetail page={makePage()} projectId="p1" pageIndex={0} level="block" />);
    // Body is the default active chip.
    const headingChip = screen.getByTestId("block-detail-layout-chip-heading");
    await user.click(headingChip);
    expect(headingChip).toHaveAttribute("data-active", "true");
  });

  it("Items tab shows para groups with lines", async () => {
    const user = userEvent.setup();
    selectBlock("b1");
    renderWithQuery(<BlockDetail page={makePage()} projectId="p1" pageIndex={0} level="block" />);
    await user.click(screen.getByTestId("block-detail-tab-items"));
    expect(screen.getByTestId("block-detail-items-tree")).toBeInTheDocument();
    // Lines should be present.
    expect(screen.getByTestId("block-detail-line-card-0")).toBeInTheDocument();
    expect(screen.getByTestId("block-detail-line-card-1")).toBeInTheDocument();
    expect(screen.getByTestId("block-detail-line-card-2")).toBeInTheDocument();
  });

  it("clicking a line in Items sets selection-store to that line", async () => {
    const user = userEvent.setup();
    selectBlock("b1");
    renderWithQuery(<BlockDetail page={makePage()} projectId="p1" pageIndex={0} level="block" />);
    await user.click(screen.getByTestId("block-detail-tab-items"));
    await user.click(screen.getByTestId("block-detail-line-card-2"));
    const { level, path } = selectionStore.getState();
    expect(level).toBe("line");
    expect(path.lineId).toBe(2);
  });
});

describe("BlockDetail (Slice 22) — para level", () => {
  beforeEach(() => {
    clearSelection();
  });

  it("shows 'No paragraph selected' when no para in selection-store", () => {
    renderWithQuery(<BlockDetail page={makePage()} projectId="p1" pageIndex={0} level="para" />);
    expect(screen.getByTestId("block-detail")).toHaveTextContent(/no paragraph selected/i);
  });

  it("shows only items tab (no layout tab) in para mode", () => {
    selectPara(0);
    renderWithQuery(<BlockDetail page={makePage()} projectId="p1" pageIndex={0} level="para" />);
    expect(screen.queryByTestId("block-detail-tab-layout")).not.toBeInTheDocument();
    expect(screen.getByTestId("block-detail-tab-items")).toBeInTheDocument();
  });

  it("para mode shows only lines for the selected para", () => {
    selectPara(1);
    renderWithQuery(<BlockDetail page={makePage()} projectId="p1" pageIndex={0} level="para" />);
    // Only line 2 is in para 1.
    expect(screen.getByTestId("block-detail-line-card-2")).toBeInTheDocument();
    expect(screen.queryByTestId("block-detail-line-card-0")).not.toBeInTheDocument();
  });
});

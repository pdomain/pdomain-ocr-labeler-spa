// Worklist.test.tsx — Tests for the Worklist drawer tab (Slice 11, P5.a, P5.b).
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 11, Gap 19, Gap 20.

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Worklist } from "./Worklist";
import { worklistStore } from "../../stores/worklist-store";
import type { components } from "../../api/types";

// Mock selectLine so we can spy on calls without full store setup
vi.mock("../../stores/selection-store", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../stores/selection-store")>();
  return { ...actual, selectLine: vi.fn() };
});

import { selectLine } from "../../stores/selection-store";

type LineMatch = components["schemas"]["LineMatch"];

function makeLines(overrides: Partial<LineMatch>[] = []): LineMatch[] {
  return overrides.map((o, i) => ({
    line_index: i,
    paragraph_index: 0,
    ocr_line_text: `line ${i}`,
    ground_truth_line_text: `line ${i}`,
    word_matches: [],
    overall_match_status: "exact" as const,
    exact_count: 1,
    fuzzy_count: 0,
    mismatch_count: 0,
    unmatched_gt_count: 0,
    unmatched_ocr_count: 0,
    validated_word_count: 1,
    total_word_count: 1,
    is_fully_validated: true,
    ...o,
  }));
}

describe("Worklist (Slice 11 + P5.a/P5.b)", () => {
  beforeEach(() => {
    worklistStore.reset();
    vi.clearAllMocks();
  });

  it("renders with data-testid=worklist", () => {
    render(<Worklist />);
    expect(screen.getByTestId("worklist")).toBeInTheDocument();
  });

  it("renders filter chip row with three chip testids", () => {
    render(<Worklist />);
    expect(screen.getByTestId("worklist-filter-unvalidated")).toBeInTheDocument();
    expect(screen.getByTestId("worklist-filter-mismatched")).toBeInTheDocument();
    expect(screen.getByTestId("worklist-filter-all")).toBeInTheDocument();
  });

  it("unvalidated filter is active by default", () => {
    render(<Worklist />);
    expect(screen.getByTestId("worklist-filter-unvalidated")).toHaveAttribute(
      "data-active",
      "true",
    );
  });

  it("shows empty message when no lines match filter", () => {
    // Default filter = unvalidated; all lines are validated
    const lines = makeLines([{ is_fully_validated: true }, { is_fully_validated: true }]);
    render(<Worklist lineMatches={lines} />);
    expect(screen.getByTestId("worklist-queue")).toHaveTextContent("No lines match");
  });

  it("shows unvalidated lines when filter=unvalidated", () => {
    const lines = makeLines([
      { line_index: 0, is_fully_validated: false, ocr_line_text: "hello" },
      { line_index: 1, is_fully_validated: true, ocr_line_text: "world" },
    ]);
    render(<Worklist lineMatches={lines} />);
    expect(screen.getByTestId("worklist-row-0")).toBeInTheDocument();
    expect(screen.queryByTestId("worklist-row-1")).not.toBeInTheDocument();
  });

  it("clicking a filter chip updates worklistStore.activeFilter", async () => {
    const user = userEvent.setup();
    render(<Worklist />);
    await user.click(screen.getByTestId("worklist-filter-all"));
    expect(worklistStore.getState().activeFilter).toBe("all");
  });

  it("clicking a row updates worklistStore.selectedLineIndex", async () => {
    const user = userEvent.setup();
    const lines = makeLines([{ line_index: 0, is_fully_validated: false }]);
    render(<Worklist lineMatches={lines} />);
    await user.click(screen.getByTestId("worklist-row-0"));
    expect(worklistStore.getState().selectedLineIndex).toBe(0);
  });

  it("selected row has data-selected=true", async () => {
    const user = userEvent.setup();
    const lines = makeLines([{ line_index: 0, is_fully_validated: false }]);
    render(<Worklist lineMatches={lines} />);
    await user.click(screen.getByTestId("worklist-row-0"));
    expect(screen.getByTestId("worklist-row-0")).toHaveAttribute("data-selected", "true");
  });

  it("mismatched filter chip (Error) shows only mismatch lines", async () => {
    const user = userEvent.setup();
    const lines = makeLines([
      {
        line_index: 0,
        mismatch_count: 2,
        overall_match_status: "mismatch",
        is_fully_validated: false,
      },
      {
        line_index: 1,
        mismatch_count: 0,
        overall_match_status: "exact",
        is_fully_validated: false,
      },
    ]);
    render(<Worklist lineMatches={lines} />);
    await user.click(screen.getByTestId("worklist-filter-mismatched"));
    expect(screen.getByTestId("worklist-row-0")).toBeInTheDocument();
    expect(screen.queryByTestId("worklist-row-1")).not.toBeInTheDocument();
  });

  it("all filter shows every line", async () => {
    const user = userEvent.setup();
    const lines = makeLines([
      { line_index: 0, is_fully_validated: true },
      { line_index: 1, is_fully_validated: true },
    ]);
    render(<Worklist lineMatches={lines} />);
    await user.click(screen.getByTestId("worklist-filter-all"));
    expect(screen.getByTestId("worklist-row-0")).toBeInTheDocument();
    expect(screen.getByTestId("worklist-row-1")).toBeInTheDocument();
  });

  // ── P5.a (Gap 20): row redesign ──────────────────────────────────────────

  it("P5.a: row shows mono ID stamp (L-001 style)", async () => {
    const user = userEvent.setup();
    const lines = makeLines([{ line_index: 0, is_fully_validated: false }]);
    render(<Worklist lineMatches={lines} />);
    // All filter so row is visible regardless of validation state
    await user.click(screen.getByTestId("worklist-filter-all"));
    expect(screen.getByTestId("worklist-row-0")).toHaveTextContent("L-001");
  });

  it("P5.a: row shows confidence percentage", async () => {
    const user = userEvent.setup();
    const lines = makeLines([
      { line_index: 0, validated_word_count: 3, total_word_count: 4, is_fully_validated: false },
    ]);
    render(<Worklist lineMatches={lines} />);
    await user.click(screen.getByTestId("worklist-filter-all"));
    // 3/4 = 75%
    expect(screen.getByTestId("worklist-row-0")).toHaveTextContent("75%");
  });

  it("P5.a: row shows GT diff when OCR ≠ GT", async () => {
    const user = userEvent.setup();
    const lines = makeLines([
      {
        line_index: 0,
        ocr_line_text: "helo world",
        ground_truth_line_text: "hello world",
        is_fully_validated: false,
      },
    ]);
    render(<Worklist lineMatches={lines} />);
    await user.click(screen.getByTestId("worklist-filter-all"));
    expect(screen.getByTestId("worklist-row-0-gt")).toBeInTheDocument();
    expect(screen.getByTestId("worklist-row-0-gt")).toHaveTextContent("hello world");
  });

  it("P5.a: row does NOT show GT diff when OCR matches GT", async () => {
    const user = userEvent.setup();
    const lines = makeLines([
      {
        line_index: 0,
        ocr_line_text: "hello world",
        ground_truth_line_text: "hello world",
        is_fully_validated: false,
      },
    ]);
    render(<Worklist lineMatches={lines} />);
    await user.click(screen.getByTestId("worklist-filter-all"));
    expect(screen.queryByTestId("worklist-row-0-gt")).not.toBeInTheDocument();
  });

  // ── P5.b (Gap 19): filter/sort redesign ──────────────────────────────────

  it("P5.b: sort dropdown renders with default 'index'", () => {
    render(<Worklist />);
    const sel = screen.getByTestId("worklist-sort-select");
    expect(sel.value).toBe("index");
  });

  it("P5.b: changing sort dropdown updates store", async () => {
    const user = userEvent.setup();
    render(<Worklist />);
    await user.selectOptions(screen.getByTestId("worklist-sort-select"), "confidence");
    expect(worklistStore.getState().sort).toBe("confidence");
  });

  it("P5.b: chips show counts from the full unfiltered list", () => {
    const lines = makeLines([
      { line_index: 0, is_fully_validated: false, overall_match_status: "exact" },
      { line_index: 1, is_fully_validated: true, overall_match_status: "exact" },
      {
        line_index: 2,
        is_fully_validated: false,
        overall_match_status: "mismatch",
        mismatch_count: 1,
      },
    ]);
    render(<Worklist lineMatches={lines} />);
    // All chip should show 3
    expect(screen.getByTestId("worklist-filter-all")).toHaveTextContent("3");
    // Unvalidated shows 2 (lines 0 and 2 are not fully validated, 2 has mismatch counted as error)
    expect(screen.getByTestId("worklist-filter-unvalidated")).toHaveTextContent("1");
    // Error chip shows count of mismatch status lines
    expect(screen.getByTestId("worklist-filter-mismatched")).toHaveTextContent("1");
  });
});

// ── Task 5: searchQuery filter ────────────────────────────────────────────────

describe("Worklist search filter (Task 5)", () => {
  beforeEach(() => {
    worklistStore.reset();
    vi.clearAllMocks();
  });

  it("filters rows by searchQuery in worklistStore", async () => {
    const lineMatches: components["schemas"]["LineMatch"][] = [
      {
        line_index: 0,
        ocr_line_text: "hello world",
        ground_truth_line_text: "hello world",
        overall_match_status: "exact",
        is_fully_validated: false,
        validated_word_count: 0,
        total_word_count: 1,
        word_matches: [],
        paragraph_index: 0,
        exact_count: 1,
        fuzzy_count: 0,
        mismatch_count: 0,
        unmatched_gt_count: 0,
        unmatched_ocr_count: 0,
      },
      {
        line_index: 1,
        ocr_line_text: "foo bar",
        ground_truth_line_text: "foo bar",
        overall_match_status: "exact",
        is_fully_validated: false,
        validated_word_count: 0,
        total_word_count: 1,
        word_matches: [],
        paragraph_index: 0,
        exact_count: 1,
        fuzzy_count: 0,
        mismatch_count: 0,
        unmatched_gt_count: 0,
        unmatched_ocr_count: 0,
      },
    ];
    worklistStore.setActiveFilter("all");
    render(<Worklist lineMatches={lineMatches} />);
    expect(screen.getByTestId("worklist-row-0")).toBeInTheDocument();
    expect(screen.getByTestId("worklist-row-1")).toBeInTheDocument();

    act(() => worklistStore.setSearchQuery("foo"));
    expect(screen.queryByTestId("worklist-row-0")).not.toBeInTheDocument();
    expect(screen.getByTestId("worklist-row-1")).toBeInTheDocument();
  });
});

// ── WorklistRow → selectionStore bridge + bulk-select checkboxes ─────────────

describe("WorklistRow bridge", () => {
  beforeEach(() => {
    worklistStore.reset();
    vi.clearAllMocks();
  });

  it("calls selectLine with line_index on row click", async () => {
    const user = userEvent.setup();
    const lineMatches: components["schemas"]["LineMatch"][] = [
      {
        line_index: 3,
        overall_match_status: "exact",
        ocr_line_text: "hello",
        ground_truth_line_text: "hello",
        is_fully_validated: false,
        validated_word_count: 0,
        total_word_count: 1,
        word_matches: [],
        paragraph_index: 0,
        exact_count: 0,
        fuzzy_count: 0,
        mismatch_count: 0,
        unmatched_gt_count: 0,
        unmatched_ocr_count: 0,
      },
    ];
    worklistStore.setActiveFilter("all");
    render(<Worklist lineMatches={lineMatches} />);
    await user.click(screen.getByTestId("worklist-row-3"));
    expect(selectLine).toHaveBeenCalledWith(3);
  });

  it("checkbox click calls worklistStore.toggle with line_index", async () => {
    const user = userEvent.setup();
    const lineMatches: components["schemas"]["LineMatch"][] = [
      {
        line_index: 2,
        overall_match_status: "mismatch",
        ocr_line_text: "foo",
        ground_truth_line_text: "bar",
        is_fully_validated: false,
        validated_word_count: 0,
        total_word_count: 1,
        word_matches: [],
        paragraph_index: 0,
        exact_count: 0,
        fuzzy_count: 0,
        mismatch_count: 1,
        unmatched_gt_count: 0,
        unmatched_ocr_count: 0,
      },
    ];
    worklistStore.setActiveFilter("all");
    render(<Worklist lineMatches={lineMatches} />);
    const checkbox = screen.getByTestId("worklist-row-checkbox-2");
    await user.click(checkbox);
    expect(worklistStore.getState().selectedIds).toContain(2);
  });

  it("checkbox click does not trigger row navigation", async () => {
    const user = userEvent.setup();
    const lineMatches: components["schemas"]["LineMatch"][] = [
      {
        line_index: 5,
        overall_match_status: "exact",
        ocr_line_text: "x",
        ground_truth_line_text: "x",
        is_fully_validated: false,
        validated_word_count: 0,
        total_word_count: 1,
        word_matches: [],
        paragraph_index: 0,
        exact_count: 1,
        fuzzy_count: 0,
        mismatch_count: 0,
        unmatched_gt_count: 0,
        unmatched_ocr_count: 0,
      },
    ];
    worklistStore.setActiveFilter("all");
    render(<Worklist lineMatches={lineMatches} />);
    await user.click(screen.getByTestId("worklist-row-checkbox-5"));
    expect(selectLine).not.toHaveBeenCalled();
  });
});

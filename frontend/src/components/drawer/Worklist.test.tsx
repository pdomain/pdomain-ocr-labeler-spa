// Worklist.test.tsx — Tests for the Worklist drawer tab (Slice 11).
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 11.

import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Worklist } from "./Worklist";
import { worklistStore } from "../../stores/worklist-store";
import type { components } from "../../api/types";

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

describe("Worklist (Slice 11)", () => {
  beforeEach(() => {
    worklistStore.reset();
  });

  it("renders with data-testid=worklist", () => {
    render(<Worklist />);
    expect(screen.getByTestId("worklist")).toBeInTheDocument();
  });

  it("renders filter chip row with three options", () => {
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

  it("mismatched filter shows only mismatched lines", async () => {
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
});

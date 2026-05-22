// Breadcrumb.test.tsx — Tests for the RightPanel breadcrumb header (Slice 14).
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 14.

import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Breadcrumb } from "./Breadcrumb";
import {
  selectionStore,
  clearSelection,
  selectPara,
  selectLine,
  selectWord,
  selectBlock,
} from "../../stores/selection-store";
import type { components } from "../../api/types";

type PagePayload = components["schemas"]["PagePayload"];
type WordMatch = components["schemas"]["WordMatch"];

function w(line: number, idx: number, text: string): WordMatch {
  return {
    line_index: line,
    word_index: idx,
    ocr_text: text,
    ground_truth_text: text,
    match_status: "exact",
    normalized_match: false,
    is_validated: false,
    bbox: { x: 0, y: 0, width: 0, height: 0 },
  };
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
        ocr_line_text: "hello world",
        ground_truth_line_text: "hello world",
        word_matches: [w(0, 0, "hello"), w(0, 1, "world")],
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

describe("Breadcrumb (Slice 14)", () => {
  beforeEach(() => {
    clearSelection();
  });

  it("renders a root 'Project' chip when nothing is selected", () => {
    render(<Breadcrumb page={makePage()} />);
    expect(screen.getByTestId("breadcrumb")).toBeInTheDocument();
    expect(screen.getByTestId("breadcrumb-chip-root")).toHaveTextContent("Project");
  });

  it("renders only the root chip when level=none", () => {
    render(<Breadcrumb page={makePage()} />);
    expect(screen.queryByTestId("breadcrumb-chip-block")).not.toBeInTheDocument();
    expect(screen.queryByTestId("breadcrumb-chip-para")).not.toBeInTheDocument();
    expect(screen.queryByTestId("breadcrumb-chip-line")).not.toBeInTheDocument();
    expect(screen.queryByTestId("breadcrumb-chip-word")).not.toBeInTheDocument();
  });

  it("renders Block chip when level=block", () => {
    selectBlock("b1");
    render(<Breadcrumb page={makePage()} />);
    expect(screen.getByTestId("breadcrumb-chip-block")).toBeInTheDocument();
  });

  it("renders Project › Para 1 when a paragraph is selected", () => {
    selectPara(0);
    render(<Breadcrumb page={makePage()} />);
    expect(screen.getByTestId("breadcrumb-chip-root")).toBeInTheDocument();
    expect(screen.getByTestId("breadcrumb-chip-para")).toHaveTextContent("Para 1");
  });

  it("renders four chips when a word is selected", () => {
    selectWord(0, 1);
    render(<Breadcrumb page={makePage()} />);
    expect(screen.getByTestId("breadcrumb-chip-root")).toBeInTheDocument();
    expect(screen.getByTestId("breadcrumb-chip-para")).toHaveTextContent("Para 1");
    expect(screen.getByTestId("breadcrumb-chip-line")).toHaveTextContent("Line 1");
    expect(screen.getByTestId("breadcrumb-chip-word")).toHaveTextContent("Word 2");
  });

  it("deepest chip uses ink-1 styling; ancestors use ink-3", () => {
    selectWord(0, 1);
    render(<Breadcrumb page={makePage()} />);
    expect(screen.getByTestId("breadcrumb-chip-word")).toHaveAttribute("data-active", "true");
    expect(screen.getByTestId("breadcrumb-chip-line")).toHaveAttribute("data-active", "false");
  });

  it("clicking ancestor line chip changes selection level to line", async () => {
    const user = userEvent.setup();
    selectWord(0, 1);
    render(<Breadcrumb page={makePage()} />);
    await user.click(screen.getByTestId("breadcrumb-chip-line"));
    const s = selectionStore.getState();
    expect(s.level).toBe("line");
    expect(s.path.lineId).toBe(0);
    expect(s.path.wordId).toBeUndefined();
  });

  it("clicking the root chip clears selection", async () => {
    const user = userEvent.setup();
    selectWord(0, 1);
    render(<Breadcrumb page={makePage()} />);
    await user.click(screen.getByTestId("breadcrumb-chip-root"));
    expect(selectionStore.getState().level).toBe("none");
  });

  it("para=null renders as 'Unsorted'", () => {
    selectPara(null);
    render(<Breadcrumb page={makePage()} />);
    expect(screen.getByTestId("breadcrumb-chip-para")).toHaveTextContent("Unsorted");
  });
});

// --- Gap 55: terminal chip kind-color fill ---

describe("Breadcrumb Gap 55 — terminal chip kind-color fill", () => {
  beforeEach(() => {
    clearSelection();
  });

  it("word chip (active) has bg-layer-word/10 class", () => {
    selectWord(0, 1);
    render(<Breadcrumb page={makePage()} />);
    const chip = screen.getByTestId("breadcrumb-chip-word");
    expect(chip.className).toMatch(/bg-layer-word/);
  });

  it("word chip (active) has text-layer-word class", () => {
    selectWord(0, 1);
    render(<Breadcrumb page={makePage()} />);
    const chip = screen.getByTestId("breadcrumb-chip-word");
    expect(chip.className).toMatch(/text-layer-word/);
  });

  it("line chip (active) has bg-layer-line/10 class", () => {
    selectLine(0);
    render(<Breadcrumb page={makePage()} />);
    const chip = screen.getByTestId("breadcrumb-chip-line");
    expect(chip.className).toMatch(/bg-layer-line/);
  });

  it("para chip (active) has bg-layer-para/10 class", () => {
    selectPara(0);
    render(<Breadcrumb page={makePage()} />);
    const chip = screen.getByTestId("breadcrumb-chip-para");
    expect(chip.className).toMatch(/bg-layer-para/);
  });

  it("root chip (active, no layer) uses text-ink-1 not a layer class", () => {
    render(<Breadcrumb page={makePage()} />);
    // Root chip has no layer prop — should get neutral active class.
    const chip = screen.getByTestId("breadcrumb-chip-root");
    expect(chip.className).not.toMatch(/bg-layer-/);
  });

  it("ancestor line chip (not active) does not get layer bg fill", () => {
    selectWord(0, 1);
    render(<Breadcrumb page={makePage()} />);
    // Line is an ancestor, not the deepest chip.
    const lineChip = screen.getByTestId("breadcrumb-chip-line");
    expect(lineChip.getAttribute("data-active")).toBe("false");
    expect(lineChip.className).not.toMatch(/bg-layer-/);
  });
});

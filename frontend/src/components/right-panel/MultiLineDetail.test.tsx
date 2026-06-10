// MultiLineDetail.test.tsx — TDD tests for ML-2, ML-3.
// Spec: docs/specs/2026-06-10-multi-line-detail.md Slice ML-A.
//
// ML-2: level==="line" && selectedLines.length > 1 → multi-line-detail renders,
//        line-detail absent, placeholder absent.
// ML-3: Each card shows line identity (line index, block/para badge, validated count,
//        ocr_line_text) and a word grid.

import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MultiLineDetail } from "./MultiLineDetail";
import { clearSelection, applyLineSelection } from "../../stores/selection-store";
import type { components } from "../../api/types";

type PagePayload = components["schemas"]["PagePayload"];
type WordMatch = components["schemas"]["WordMatch"];
type LineMatch = components["schemas"]["LineMatch"];

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

function wrap(ui: React.ReactElement) {
  return render(<QueryClientProvider client={makeQueryClient()}>{ui}</QueryClientProvider>);
}

function makeWord(line: number, idx: number, ocr: string, gt?: string): WordMatch {
  return {
    line_index: line,
    word_index: idx,
    ocr_text: ocr,
    ground_truth_text: gt ?? ocr,
    match_status: "exact",
    normalized_match: false,
    is_validated: false,
    bbox: { x: 0, y: 0, width: 10, height: 10 },
  };
}

function makeLine(
  lineIndex: number,
  paraIndex: number,
  blockIndex: number,
  words: WordMatch[],
): LineMatch {
  return {
    line_index: lineIndex,
    paragraph_index: paraIndex,
    block_index: blockIndex,
    ocr_line_text: words.map((w) => w.ocr_text).join(" "),
    ground_truth_line_text: words.map((w) => w.ground_truth_text).join(" "),
    word_matches: words,
    overall_match_status: "exact",
    exact_count: words.length,
    fuzzy_count: 0,
    mismatch_count: 0,
    unmatched_gt_count: 0,
    unmatched_ocr_count: 0,
    validated_word_count: 0,
    total_word_count: words.length,
    is_fully_validated: false,
  };
}

function makePage(): PagePayload {
  return {
    project_id: "p1",
    page_index: 0,
    line_filter: "all",
    generation: 0,
    line_matches: [
      makeLine(0, 0, 0, [makeWord(0, 0, "foo"), makeWord(0, 1, "bar")]),
      makeLine(1, 0, 0, [makeWord(1, 0, "baz"), makeWord(1, 1, "qux")]),
      makeLine(2, 1, 1, [makeWord(2, 0, "hello"), makeWord(2, 1, "world")]),
    ],
  };
}

describe("MultiLineDetail — ML-2: routing", () => {
  beforeEach(() => {
    clearSelection();
  });

  it("renders multi-line-detail when 2 lines are selected", () => {
    applyLineSelection([0, 1], "replace");
    wrap(<MultiLineDetail page={makePage()} projectId="p1" pageIndex={0} selectedLines={[0, 1]} />);
    expect(screen.getByTestId("multi-line-detail")).toBeInTheDocument();
  });

  it("renders one card per selected line in ascending line_index order", () => {
    wrap(<MultiLineDetail page={makePage()} projectId="p1" pageIndex={0} selectedLines={[2, 0]} />);
    // Cards should be in ascending order: line 0 first, then line 2
    expect(screen.getByTestId("multi-line-card-0")).toBeInTheDocument();
    expect(screen.getByTestId("multi-line-card-2")).toBeInTheDocument();
    const cards = screen.getAllByTestId(/^multi-line-card-/);
    const cardLineIds = cards.map((c) => parseInt(c.dataset.lineIndex ?? "0", 10));
    expect(cardLineIds).toEqual([0, 2]);
  });
});

describe("MultiLineDetail — ML-3: card content", () => {
  beforeEach(() => {
    clearSelection();
  });

  it("each card shows the ocr_line_text for that line", () => {
    wrap(<MultiLineDetail page={makePage()} projectId="p1" pageIndex={0} selectedLines={[0, 1]} />);
    const card0 = screen.getByTestId("multi-line-card-0");
    expect(card0).toHaveTextContent("foo bar");
    const card1 = screen.getByTestId("multi-line-card-1");
    expect(card1).toHaveTextContent("baz qux");
  });

  it("each card shows the validated count badge", () => {
    wrap(<MultiLineDetail page={makePage()} projectId="p1" pageIndex={0} selectedLines={[0, 1]} />);
    // 0/2 validated for both lines
    const card0 = screen.getByTestId("multi-line-card-0");
    expect(card0).toHaveTextContent(/0\s*\/\s*2/);
  });

  it("each card shows word inputs for each word in that line", () => {
    wrap(<MultiLineDetail page={makePage()} projectId="p1" pageIndex={0} selectedLines={[0]} />);
    // Line 0 has 2 words
    expect(screen.getByTestId("gt-text-input-0-0")).toBeInTheDocument();
    expect(screen.getByTestId("gt-text-input-0-1")).toBeInTheDocument();
  });

  it("each card has per-line validate/copy/delete buttons", () => {
    wrap(<MultiLineDetail page={makePage()} projectId="p1" pageIndex={0} selectedLines={[0, 1]} />);
    expect(screen.getByTestId("line-validate-button-0")).toBeInTheDocument();
    expect(screen.getByTestId("line-validate-button-1")).toBeInTheDocument();
    expect(screen.getByTestId("line-gt-to-ocr-button-0")).toBeInTheDocument();
    expect(screen.getByTestId("line-ocr-to-gt-button-0")).toBeInTheDocument();
    expect(screen.getByTestId("line-delete-button-0")).toBeInTheDocument();
  });

  it("bulk bar is visible with N lines selected count", () => {
    wrap(
      <MultiLineDetail page={makePage()} projectId="p1" pageIndex={0} selectedLines={[0, 1, 2]} />,
    );
    expect(screen.getByTestId("multi-line-bulk-bar")).toBeInTheDocument();
    expect(screen.getByTestId("multi-line-bulk-bar")).toHaveTextContent("3");
  });

  it("bulk bar has validate-all/unvalidate-all/copy-ocr-to-gt/delete buttons", () => {
    wrap(<MultiLineDetail page={makePage()} projectId="p1" pageIndex={0} selectedLines={[0, 1]} />);
    expect(screen.getByTestId("multi-line-bulk-validate")).toBeInTheDocument();
    expect(screen.getByTestId("multi-line-bulk-unvalidate")).toBeInTheDocument();
    expect(screen.getByTestId("multi-line-bulk-copy-ocr-to-gt")).toBeInTheDocument();
    expect(screen.getByTestId("multi-line-bulk-delete")).toBeInTheDocument();
  });
});

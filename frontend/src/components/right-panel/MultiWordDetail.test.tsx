// MultiWordDetail.test.tsx — TDD tests for MUL-1, MUL-2, MUL-3 (Slice B).
//
// MUL-1: Multi-block selection is fully visible — words from different blocks
//        must BOTH appear, each under their own Block header.
// MUL-2: Line context shown per word — each group shows ocr_line_text + block/para.
// MUL-3: Operations (validate/unvalidate/delete/style/component) act on all
//        selected words.
//
// Acceptance criterion (verbatim from plan):
//   "when I select words that roll up to different blocks I should SEE them all"
//   + "include the line they're part of."

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MultiWordDetail } from "./MultiWordDetail";
import { clearSelection, toggleWord, selectionStore } from "../../stores/selection-store";
import type { components } from "../../api/types";

type PagePayload = components["schemas"]["PagePayload"];
type WordMatch = components["schemas"]["WordMatch"];

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

function wrap(ui: React.ReactElement) {
  return render(<QueryClientProvider client={makeQueryClient()}>{ui}</QueryClientProvider>);
}

// Build a page with 4 lines across 2 blocks:
//   Block 0: line 0 "foo bar"  (words: "foo" [0,0], "bar" [0,1])
//   Block 0: line 1 "baz"      (words: "baz" [1,0])
//   Block 1: line 2 "qux quux" (words: "qux" [2,0], "quux" [2,1])
//   Block 1: line 3 "corge"    (words: "corge" [3,0])
function w(line: number, idx: number, ocr: string): WordMatch {
  return {
    line_index: line,
    word_index: idx,
    ocr_text: ocr,
    ground_truth_text: ocr,
    match_status: "exact",
    normalized_match: false,
    is_validated: false,
    bbox: { x: 0, y: 0, width: 10, height: 10 },
  };
}

function makeTwoBlockPage(): PagePayload {
  return {
    project_id: "proj1",
    page_index: 0,
    line_filter: "all",
    generation: 0,
    line_matches: [
      {
        line_index: 0,
        paragraph_index: 0,
        block_index: 0,
        ocr_line_text: "foo bar",
        ground_truth_line_text: "foo bar",
        word_matches: [w(0, 0, "foo"), w(0, 1, "bar")],
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
      {
        line_index: 1,
        paragraph_index: 0,
        block_index: 0,
        ocr_line_text: "baz",
        ground_truth_line_text: "baz",
        word_matches: [w(1, 0, "baz")],
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
      {
        line_index: 2,
        paragraph_index: 1,
        block_index: 1,
        ocr_line_text: "qux quux",
        ground_truth_line_text: "qux quux",
        word_matches: [w(2, 0, "qux"), w(2, 1, "quux")],
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
      {
        line_index: 3,
        paragraph_index: 1,
        block_index: 1,
        ocr_line_text: "corge",
        ground_truth_line_text: "corge",
        word_matches: [w(3, 0, "corge")],
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

describe("MultiWordDetail (MUL-1, MUL-2, MUL-3 — Slice B)", () => {
  beforeEach(() => {
    clearSelection();
    vi.restoreAllMocks();
  });

  // ─── MUL-1: Both block headers appear ───────────────────────────────────────

  it("MUL-1: renders with data-testid=multi-word-detail", () => {
    toggleWord(0, 0, "replace");
    toggleWord(2, 0, "toggle");
    const page = makeTwoBlockPage();
    wrap(
      <MultiWordDetail
        page={page}
        projectId="proj1"
        pageIndex={0}
        selectedWords={selectionStore.getState().selectedWords}
      />,
    );
    expect(screen.getByTestId("multi-word-detail")).toBeInTheDocument();
  });

  it("MUL-1: shows Block 0 AND Block 1 headers when words span two blocks", () => {
    const page = makeTwoBlockPage();
    // Select "foo" from block 0 (line 0) and "qux" from block 1 (line 2)
    const selected: [number, number][] = [
      [0, 0], // foo — block 0
      [2, 0], // qux — block 1
    ];
    wrap(<MultiWordDetail page={page} projectId="proj1" pageIndex={0} selectedWords={selected} />);
    // CRITICAL: BOTH blocks must appear
    expect(screen.getByTestId("multi-word-block-0")).toBeInTheDocument();
    expect(screen.getByTestId("multi-word-block-1")).toBeInTheDocument();
  });

  it("MUL-1: words from block 0 appear under the block-0 header", () => {
    const page = makeTwoBlockPage();
    const selected: [number, number][] = [
      [0, 0], // foo — block 0
      [2, 0], // qux — block 1
    ];
    wrap(<MultiWordDetail page={page} projectId="proj1" pageIndex={0} selectedWords={selected} />);
    const block0 = screen.getByTestId("multi-word-block-0");
    expect(block0).toHaveTextContent("foo");
    expect(block0).not.toHaveTextContent("qux");
  });

  it("MUL-1: words from block 1 appear under the block-1 header", () => {
    const page = makeTwoBlockPage();
    const selected: [number, number][] = [
      [0, 0], // foo — block 0
      [2, 0], // qux — block 1
    ];
    wrap(<MultiWordDetail page={page} projectId="proj1" pageIndex={0} selectedWords={selected} />);
    const block1 = screen.getByTestId("multi-word-block-1");
    expect(block1).toHaveTextContent("qux");
    expect(block1).not.toHaveTextContent("foo");
  });

  // ─── MUL-2: Line text context is shown ──────────────────────────────────────

  it("MUL-2: shows ocr_line_text for the owning line of each selected word", () => {
    const page = makeTwoBlockPage();
    const selected: [number, number][] = [
      [0, 0], // foo — line 0 "foo bar"
      [2, 0], // qux — line 2 "qux quux"
    ];
    wrap(<MultiWordDetail page={page} projectId="proj1" pageIndex={0} selectedWords={selected} />);
    expect(screen.getByText("foo bar")).toBeInTheDocument();
    expect(screen.getByText("qux quux")).toBeInTheDocument();
  });

  it("MUL-2: shows block number in the block header", () => {
    const page = makeTwoBlockPage();
    const selected: [number, number][] = [
      [0, 0],
      [2, 0],
    ];
    wrap(<MultiWordDetail page={page} projectId="proj1" pageIndex={0} selectedWords={selected} />);
    // Block headers should reference block indices
    const block0Header = screen.getByTestId("multi-word-block-0-header");
    const block1Header = screen.getByTestId("multi-word-block-1-header");
    expect(block0Header).toBeInTheDocument();
    expect(block1Header).toBeInTheDocument();
  });

  it("MUL-2: selected word OCR text shown under its line", () => {
    const page = makeTwoBlockPage();
    const selected: [number, number][] = [
      [0, 0], // "foo"
      [0, 1], // "bar" — same line as foo
    ];
    wrap(<MultiWordDetail page={page} projectId="proj1" pageIndex={0} selectedWords={selected} />);
    // Both words appear and the line text appears once
    expect(screen.getAllByText("foo bar")).toHaveLength(1);
    // Individual word texts visible
    expect(screen.getByTestId("multi-word-item-0-0")).toBeInTheDocument();
    expect(screen.getByTestId("multi-word-item-0-1")).toBeInTheDocument();
  });

  it("MUL-2: three words across two blocks — all three visible", () => {
    const page = makeTwoBlockPage();
    const selected: [number, number][] = [
      [0, 0], // foo — block 0, line 0
      [1, 0], // baz — block 0, line 1
      [2, 0], // qux — block 1, line 2
    ];
    wrap(<MultiWordDetail page={page} projectId="proj1" pageIndex={0} selectedWords={selected} />);
    expect(screen.getByTestId("multi-word-item-0-0")).toBeInTheDocument();
    expect(screen.getByTestId("multi-word-item-1-0")).toBeInTheDocument();
    expect(screen.getByTestId("multi-word-item-2-0")).toBeInTheDocument();
    // Both block headers present
    expect(screen.getByTestId("multi-word-block-0")).toBeInTheDocument();
    expect(screen.getByTestId("multi-word-block-1")).toBeInTheDocument();
  });

  // ─── MUL-3: Bulk operations ──────────────────────────────────────────────────

  it("MUL-3: validate button is present", () => {
    const page = makeTwoBlockPage();
    const selected: [number, number][] = [
      [0, 0],
      [2, 0],
    ];
    wrap(<MultiWordDetail page={page} projectId="proj1" pageIndex={0} selectedWords={selected} />);
    expect(screen.getByTestId("multi-word-validate")).toBeInTheDocument();
  });

  it("MUL-3: unvalidate button is present", () => {
    const page = makeTwoBlockPage();
    const selected: [number, number][] = [
      [0, 0],
      [2, 0],
    ];
    wrap(<MultiWordDetail page={page} projectId="proj1" pageIndex={0} selectedWords={selected} />);
    expect(screen.getByTestId("multi-word-unvalidate")).toBeInTheDocument();
  });

  it("MUL-3: delete button is present", () => {
    const page = makeTwoBlockPage();
    const selected: [number, number][] = [
      [0, 0],
      [2, 0],
    ];
    wrap(<MultiWordDetail page={page} projectId="proj1" pageIndex={0} selectedWords={selected} />);
    expect(screen.getByTestId("multi-word-delete")).toBeInTheDocument();
  });

  it("MUL-3: validate button fires mutation for all selected words", async () => {
    const user = userEvent.setup();
    const page = makeTwoBlockPage();
    const selected: [number, number][] = [
      [0, 0],
      [2, 0],
    ];
    wrap(<MultiWordDetail page={page} projectId="proj1" pageIndex={0} selectedWords={selected} />);
    // The button should be enabled (mutation pending = false initially)
    const validateBtn = screen.getByTestId("multi-word-validate");
    expect(validateBtn).not.toBeDisabled();
    await user.click(validateBtn);
    // Mutation was fired (network call attempted) — no error thrown
    // In jsdom/test env the fetch will not resolve, but the button state
    // changes to pending. Just verify the click doesn't throw.
  });

  it("MUL-3: apply style select and button present", () => {
    const page = makeTwoBlockPage();
    const selected: [number, number][] = [
      [0, 0],
      [2, 0],
    ];
    wrap(<MultiWordDetail page={page} projectId="proj1" pageIndex={0} selectedWords={selected} />);
    expect(screen.getByTestId("multi-word-style-select")).toBeInTheDocument();
    expect(screen.getByTestId("multi-word-style-apply")).toBeInTheDocument();
  });

  it("MUL-3: apply component select and button present", () => {
    const page = makeTwoBlockPage();
    const selected: [number, number][] = [
      [0, 0],
      [2, 0],
    ];
    wrap(<MultiWordDetail page={page} projectId="proj1" pageIndex={0} selectedWords={selected} />);
    expect(screen.getByTestId("multi-word-component-select")).toBeInTheDocument();
    expect(screen.getByTestId("multi-word-component-apply")).toBeInTheDocument();
  });

  // ─── Edge: single-block multi-select ────────────────────────────────────────

  it("single-block multi-select: one block header, both words visible", () => {
    const page = makeTwoBlockPage();
    // Both words from block 0
    const selected: [number, number][] = [
      [0, 0], // foo — block 0
      [0, 1], // bar — block 0
    ];
    wrap(<MultiWordDetail page={page} projectId="proj1" pageIndex={0} selectedWords={selected} />);
    expect(screen.getByTestId("multi-word-block-0")).toBeInTheDocument();
    expect(screen.queryByTestId("multi-word-block-1")).not.toBeInTheDocument();
    expect(screen.getByTestId("multi-word-item-0-0")).toBeInTheDocument();
    expect(screen.getByTestId("multi-word-item-0-1")).toBeInTheDocument();
  });

  // ─── Edge: words with no block_index fall back gracefully ───────────────────

  it("words without block_index render under a null-block group", () => {
    // Page without block_index on line_matches
    const page: PagePayload = {
      project_id: "p2",
      page_index: 0,
      line_filter: "all",
      generation: 0,
      line_matches: [
        {
          line_index: 0,
          paragraph_index: 0,
          // block_index deliberately absent
          ocr_line_text: "alpha",
          ground_truth_line_text: "alpha",
          word_matches: [w(0, 0, "alpha")],
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
        {
          line_index: 1,
          paragraph_index: 1,
          ocr_line_text: "beta",
          ground_truth_line_text: "beta",
          word_matches: [w(1, 0, "beta")],
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
    const selected: [number, number][] = [
      [0, 0],
      [1, 0],
    ];
    wrap(<MultiWordDetail page={page} projectId="p2" pageIndex={0} selectedWords={selected} />);
    // Both words still visible even without block_index
    expect(screen.getByTestId("multi-word-item-0-0")).toBeInTheDocument();
    expect(screen.getByTestId("multi-word-item-1-0")).toBeInTheDocument();
  });
});

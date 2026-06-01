// Hierarchy.test.tsx — Tests for the Hierarchy drawer tab (Slice 12, P5.c).
// Covers: B-DRAWER-002, B-DRAWER-007, B-DRAWER-008, B-DRAWER-009
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 12, Gaps 21, 22.

import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Hierarchy } from "./Hierarchy";
import { selectionStore } from "../../stores/selection-store";
import type { components } from "../../api/types";

type PagePayload = components["schemas"]["PagePayload"];

function makePage(): PagePayload {
  return {
    project_id: "p1",
    page_index: 0,
    line_matches: [
      {
        line_index: 0,
        paragraph_index: 0,
        ocr_line_text: "hello world",
        ground_truth_line_text: "hello world",
        word_matches: [
          {
            line_index: 0,
            word_index: 0,
            ocr_text: "hello",
            ground_truth_text: "hello",
            match_status: "exact",
            normalized_match: false,
            is_validated: false,
            bbox: { x: 0, y: 0, width: 0, height: 0 },
          },
          {
            line_index: 0,
            word_index: 1,
            ocr_text: "world",
            ground_truth_text: "world",
            match_status: "exact",
            normalized_match: false,
            is_validated: false,
            bbox: { x: 0, y: 0, width: 0, height: 0 },
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
      {
        line_index: 1,
        paragraph_index: 0,
        ocr_line_text: "foo bar",
        ground_truth_line_text: "foo bar",
        word_matches: [],
        overall_match_status: "exact",
        exact_count: 0,
        fuzzy_count: 0,
        mismatch_count: 0,
        unmatched_gt_count: 0,
        unmatched_ocr_count: 0,
        validated_word_count: 0,
        total_word_count: 0,
        is_fully_validated: true,
      },
      {
        line_index: 2,
        paragraph_index: 1,
        ocr_line_text: "second para",
        ground_truth_line_text: "second para",
        word_matches: [],
        overall_match_status: "exact",
        exact_count: 0,
        fuzzy_count: 0,
        mismatch_count: 0,
        unmatched_gt_count: 0,
        unmatched_ocr_count: 0,
        validated_word_count: 0,
        total_word_count: 0,
        is_fully_validated: true,
      },
    ],
    line_filter: "all",
    generation: 0,
  };
}

describe("Hierarchy (Slice 12 + P5.c)", () => {
  beforeEach(() => {
    selectionStore.setState({
      selectedParagraphs: [],
      selectedLines: [],
      selectedWords: [],
      dragRect: null,
    });
  });

  it("renders with data-testid=hierarchy", () => {
    render(<Hierarchy />);
    expect(screen.getByTestId("hierarchy")).toBeInTheDocument();
  });

  it("shows empty message when no page data", () => {
    render(<Hierarchy />);
    expect(screen.getByTestId("hierarchy")).toHaveTextContent("No page data");
  });

  it("renders paragraph nodes from page data", () => {
    render(<Hierarchy page={makePage()} />);
    expect(screen.getByTestId("hierarchy-node-para-0")).toBeInTheDocument();
    expect(screen.getByTestId("hierarchy-node-para-1")).toBeInTheDocument();
  });

  it("each paragraph node has a layer-color square", () => {
    render(<Hierarchy page={makePage()} />);
    expect(screen.getByTestId("hierarchy-color-para-0")).toBeInTheDocument();
    expect(screen.getByTestId("hierarchy-color-para-1")).toBeInTheDocument();
  });

  it("expanding a paragraph node reveals its lines", async () => {
    const user = userEvent.setup();
    render(<Hierarchy page={makePage()} />);
    // Lines are hidden until para is expanded
    expect(screen.queryByTestId("hierarchy-node-line-0")).not.toBeInTheDocument();
    await user.click(screen.getByTestId("hierarchy-node-para-0"));
    // After expanding, select para-0 — it doesn't auto-expand; we need to trigger expand
    // Para nodes expand on ArrowRight
    const paraNode = screen.getByTestId("hierarchy-node-para-0");
    fireEvent.keyDown(paraNode, { key: "ArrowRight" });
    expect(screen.getByTestId("hierarchy-node-line-0")).toBeInTheDocument();
    expect(screen.getByTestId("hierarchy-node-line-1")).toBeInTheDocument();
  });

  it("clicking a line node updates selection-store.selectedLines", async () => {
    const user = userEvent.setup();
    render(<Hierarchy page={makePage()} />);
    // Expand para-0 first
    const paraNode = screen.getByTestId("hierarchy-node-para-0");
    await user.click(paraNode);
    fireEvent.keyDown(paraNode, { key: "ArrowRight" });
    // Click line-0
    await user.click(screen.getByTestId("hierarchy-node-line-0"));
    expect(selectionStore.getState().selectedLines).toContain(0);
  });

  it("clicking a paragraph node updates selection-store.selectedParagraphs", async () => {
    const user = userEvent.setup();
    render(<Hierarchy page={makePage()} />);
    await user.click(screen.getByTestId("hierarchy-node-para-0"));
    expect(selectionStore.getState().selectedParagraphs).toContain(0);
  });

  it("selected node has data-selected=true", async () => {
    const user = userEvent.setup();
    render(<Hierarchy page={makePage()} />);
    await user.click(screen.getByTestId("hierarchy-node-para-0"));
    expect(screen.getByTestId("hierarchy-node-para-0")).toHaveAttribute("data-selected", "true");
  });

  it("expanding a line reveals its word nodes", async () => {
    const user = userEvent.setup();
    render(<Hierarchy page={makePage()} />);
    // Expand para-0
    const paraNode = screen.getByTestId("hierarchy-node-para-0");
    await user.click(paraNode);
    fireEvent.keyDown(paraNode, { key: "ArrowRight" });
    // Expand line-0
    const lineNode = screen.getByTestId("hierarchy-node-line-0");
    fireEvent.keyDown(lineNode, { key: "ArrowRight" });
    expect(screen.getByTestId("hierarchy-node-word-0-0")).toBeInTheDocument();
    expect(screen.getByTestId("hierarchy-node-word-0-1")).toBeInTheDocument();
  });

  it("ArrowDown selects next node when expanded", async () => {
    const user = userEvent.setup();
    render(<Hierarchy page={makePage()} />);
    // Select para-0
    await user.click(screen.getByTestId("hierarchy-node-para-0"));
    // Press ArrowDown to move to para-1
    fireEvent.keyDown(screen.getByTestId("hierarchy"), { key: "ArrowDown" });
    expect(screen.getByTestId("hierarchy-node-para-1")).toHaveAttribute("data-selected", "true");
  });

  it("word nodes have layer-color squares", async () => {
    const user = userEvent.setup();
    render(<Hierarchy page={makePage()} />);
    // Expand para-0 then line-0
    const paraNode = screen.getByTestId("hierarchy-node-para-0");
    await user.click(paraNode);
    fireEvent.keyDown(paraNode, { key: "ArrowRight" });
    fireEvent.keyDown(screen.getByTestId("hierarchy-node-line-0"), { key: "ArrowRight" });
    expect(screen.getByTestId("hierarchy-color-word-0-0")).toBeInTheDocument();
  });

  // ── P5.c (Gaps 21, 22): kind chips + filter pills + node count ────────────

  it("P5.c: filter pill row renders with all kind filters", () => {
    render(<Hierarchy page={makePage()} />);
    expect(screen.getByTestId("hierarchy-filter-all")).toBeInTheDocument();
    expect(screen.getByTestId("hierarchy-filter-para")).toBeInTheDocument();
    expect(screen.getByTestId("hierarchy-filter-line")).toBeInTheDocument();
    expect(screen.getByTestId("hierarchy-filter-word")).toBeInTheDocument();
  });

  it("P5.c: All filter is active by default", () => {
    render(<Hierarchy page={makePage()} />);
    expect(screen.getByTestId("hierarchy-filter-all")).toHaveAttribute("data-active", "true");
  });

  it("P5.c: node count badge shows total visible node count", () => {
    render(<Hierarchy page={makePage()} />);
    // Without expanding, only 2 para nodes are visible
    expect(screen.getByTestId("hierarchy-node-count")).toHaveTextContent("2");
  });

  it("P5.c: para filter shows only para nodes", async () => {
    const user = userEvent.setup();
    // First expand para-0 to have line nodes visible
    render(<Hierarchy page={makePage()} />);
    const paraNode = screen.getByTestId("hierarchy-node-para-0");
    await user.click(paraNode);
    fireEvent.keyDown(paraNode, { key: "ArrowRight" });
    // Now switch filter to para
    await user.click(screen.getByTestId("hierarchy-filter-para"));
    // Only para nodes visible
    expect(screen.getByTestId("hierarchy-node-para-0")).toBeInTheDocument();
    expect(screen.queryByTestId("hierarchy-node-line-0")).not.toBeInTheDocument();
  });

  it("P5.c: line filter shows only line nodes (when expanded)", async () => {
    const user = userEvent.setup();
    render(<Hierarchy page={makePage()} />);
    // Expand para-0 so lines are in the flat list
    const paraNode = screen.getByTestId("hierarchy-node-para-0");
    await user.click(paraNode);
    fireEvent.keyDown(paraNode, { key: "ArrowRight" });
    // Switch to line filter
    await user.click(screen.getByTestId("hierarchy-filter-line"));
    expect(screen.getByTestId("hierarchy-node-line-0")).toBeInTheDocument();
    expect(screen.queryByTestId("hierarchy-node-para-0")).not.toBeInTheDocument();
  });

  it("P5.c: each node shows a kind chip with data-kind attribute", () => {
    render(<Hierarchy page={makePage()} />);
    expect(screen.getByTestId("hierarchy-node-para-0")).toHaveAttribute("data-kind", "para");
  });

  // ── level/path layer (Q1 fix) ─────────────────────────────────────────────

  it("selecting a line node sets level=line on selectionStore", async () => {
    const user = userEvent.setup();
    render(<Hierarchy page={makePage()} />);
    // Expand para-0 to reveal lines
    const paraNode = screen.getByTestId("hierarchy-node-para-0");
    await user.click(paraNode);
    fireEvent.keyDown(paraNode, { key: "ArrowRight" });
    // Click line-0
    await user.click(screen.getByTestId("hierarchy-node-line-0"));
    expect(selectionStore.getState().level).toBe("line");
  });

  it("selecting a para node sets level=para on selectionStore", async () => {
    const user = userEvent.setup();
    render(<Hierarchy page={makePage()} />);
    await user.click(screen.getByTestId("hierarchy-node-para-0"));
    expect(selectionStore.getState().level).toBe("para");
  });

  it("selecting a word node sets level=word on selectionStore", async () => {
    const user = userEvent.setup();
    render(<Hierarchy page={makePage()} />);
    // Expand para-0, then line-0 to reveal words
    const paraNode = screen.getByTestId("hierarchy-node-para-0");
    await user.click(paraNode);
    fireEvent.keyDown(paraNode, { key: "ArrowRight" });
    const lineNode = screen.getByTestId("hierarchy-node-line-0");
    fireEvent.keyDown(lineNode, { key: "ArrowRight" });
    // Click word-0-0
    await user.click(screen.getByTestId("hierarchy-node-word-0-0"));
    expect(selectionStore.getState().level).toBe("word");
  });
});

// ── FO-7 / CU-4.3: block-layer rendering ─────────────────────────────────────

function makePageWithBlocks(): PagePayload {
  return {
    project_id: "p1",
    page_index: 0,
    line_filter: "all",
    generation: 0,
    line_matches: [
      // Block 0: para 0, line 0
      {
        line_index: 0,
        paragraph_index: 0,
        block_index: 0,
        ocr_line_text: "alpha",
        ground_truth_line_text: "alpha",
        word_matches: [],
        overall_match_status: "exact",
        exact_count: 0,
        fuzzy_count: 0,
        mismatch_count: 0,
        unmatched_gt_count: 0,
        unmatched_ocr_count: 0,
        validated_word_count: 0,
        total_word_count: 0,
        is_fully_validated: true,
      },
      // Block 1: para 1, lines 1 + 2
      {
        line_index: 1,
        paragraph_index: 1,
        block_index: 1,
        ocr_line_text: "beta",
        ground_truth_line_text: "beta",
        word_matches: [],
        overall_match_status: "exact",
        exact_count: 0,
        fuzzy_count: 0,
        mismatch_count: 0,
        unmatched_gt_count: 0,
        unmatched_ocr_count: 0,
        validated_word_count: 0,
        total_word_count: 0,
        is_fully_validated: true,
      },
      {
        line_index: 2,
        paragraph_index: 1,
        block_index: 1,
        ocr_line_text: "gamma",
        ground_truth_line_text: "gamma",
        word_matches: [],
        overall_match_status: "exact",
        exact_count: 0,
        fuzzy_count: 0,
        mismatch_count: 0,
        unmatched_gt_count: 0,
        unmatched_ocr_count: 0,
        validated_word_count: 0,
        total_word_count: 0,
        is_fully_validated: true,
      },
    ],
  };
}

describe("Hierarchy — block layer (FO-7 / CU-4.3)", () => {
  beforeEach(() => {
    selectionStore.setState({
      selectedParagraphs: [],
      selectedLines: [],
      selectedWords: [],
      dragRect: null,
    });
  });

  it("renders block nodes when block_index is present", () => {
    render(<Hierarchy page={makePageWithBlocks()} />);
    expect(screen.getByTestId("hierarchy-node-block-0")).toBeInTheDocument();
    expect(screen.getByTestId("hierarchy-node-block-1")).toBeInTheDocument();
  });

  it("block nodes have data-kind=block", () => {
    render(<Hierarchy page={makePageWithBlocks()} />);
    expect(screen.getByTestId("hierarchy-node-block-0")).toHaveAttribute("data-kind", "block");
  });

  it("block nodes have a layer-color square", () => {
    render(<Hierarchy page={makePageWithBlocks()} />);
    expect(screen.getByTestId("hierarchy-color-block-0")).toBeInTheDocument();
    expect(screen.getByTestId("hierarchy-color-block-1")).toBeInTheDocument();
  });

  it("does not render block nodes when no block_index on page", () => {
    render(<Hierarchy page={makePage()} />);
    expect(screen.queryByTestId("hierarchy-node-block-0")).not.toBeInTheDocument();
  });

  it("expanding a block node reveals its paragraph children", async () => {
    const user = userEvent.setup();
    render(<Hierarchy page={makePageWithBlocks()} />);
    // Para nodes should not be visible until block is expanded
    expect(screen.queryByTestId("hierarchy-node-para-0")).not.toBeInTheDocument();
    // Expand block-0 via ArrowRight
    const blockNode = screen.getByTestId("hierarchy-node-block-0");
    await user.click(blockNode);
    fireEvent.keyDown(blockNode, { key: "ArrowRight" });
    expect(screen.getByTestId("hierarchy-node-para-0")).toBeInTheDocument();
  });

  it("clicking a block node sets level=block on selectionStore", async () => {
    const user = userEvent.setup();
    render(<Hierarchy page={makePageWithBlocks()} />);
    await user.click(screen.getByTestId("hierarchy-node-block-0"));
    expect(selectionStore.getState().level).toBe("block");
    expect(selectionStore.getState().path.blockId).toBe("0");
  });

  it("block filter pill is visible when block layer is active", () => {
    render(<Hierarchy page={makePageWithBlocks()} />);
    expect(screen.getByTestId("hierarchy-filter-block")).toBeInTheDocument();
  });

  it("block filter pill is absent when no block layer", () => {
    render(<Hierarchy page={makePage()} />);
    expect(screen.queryByTestId("hierarchy-filter-block")).not.toBeInTheDocument();
  });

  it("node count shows 2 blocks without expanding", () => {
    render(<Hierarchy page={makePageWithBlocks()} />);
    expect(screen.getByTestId("hierarchy-node-count")).toHaveTextContent("2");
  });
});

// Hierarchy.test.tsx — Tests for the Hierarchy drawer tab (Slice 12).
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 12.

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
          },
          {
            line_index: 0,
            word_index: 1,
            ocr_text: "world",
            ground_truth_text: "world",
            match_status: "exact",
            normalized_match: false,
            is_validated: false,
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

describe("Hierarchy (Slice 12)", () => {
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
});

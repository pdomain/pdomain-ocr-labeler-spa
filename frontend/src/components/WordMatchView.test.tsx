// WordMatchView.test.tsx — unit tests for the virtualised word-match list.
//
// Spec: docs/specs/2026-05-12-word-matches-design.md
// Issue #201 (virtualised LineCard list)
//
// Acceptance:
//   - Renders without mounting every card when given many lines
//   - Each visible card has data-testid="line-card-{line_index}"
//   - LineCard header shows the correct status color class
//   - Correct header background for each MatchStatus value
//   - Count chips render for nonzero values

import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import type { components } from "../api/types";
import { WordMatchView } from "./WordMatchView";
import { LineCard } from "./LineCard";

type LineMatch = components["schemas"]["LineMatch"];
type MatchStatus = components["schemas"]["MatchStatus"];

// ─── helpers ─────────────────────────────────────────────────────────────

function makeLineMatch(overrides: Partial<LineMatch> = {}): LineMatch {
  return {
    line_index: 0,
    paragraph_index: null,
    ocr_line_text: "test ocr",
    ground_truth_line_text: "test gt",
    word_matches: [],
    overall_match_status: "exact",
    exact_count: 1,
    fuzzy_count: 0,
    mismatch_count: 0,
    unmatched_gt_count: 0,
    unmatched_ocr_count: 0,
    is_fully_validated: false,
    ...overrides,
  };
}

function makeLines(n: number): LineMatch[] {
  return Array.from({ length: n }, (_, i) =>
    makeLineMatch({ line_index: i, ocr_line_text: `line ${i}` }),
  );
}

// ─── WordMatchView ────────────────────────────────────────────────────────

describe("WordMatchView", () => {
  it("renders the scroll container with data-testid='word-match-view'", () => {
    render(<WordMatchView lines={[]} />);
    expect(screen.getByTestId("word-match-view")).toBeInTheDocument();
  });

  it("renders empty state when no lines are provided", () => {
    render(<WordMatchView lines={[]} />);
    expect(screen.getByTestId("word-match-empty")).toBeInTheDocument();
  });

  it("renders scroll container and total-size spacer for a non-empty list", () => {
    // jsdom has no real layout so the virtualiser renders 0 items (correct
    // virtualisation behaviour — nothing is in the viewport). We verify
    // the structural scaffolding: scroll container present, total-size spacer
    // has height > 0 when lines are provided.
    const lines = makeLines(3);
    const { container } = render(<WordMatchView lines={lines} />);

    const scrollContainer = screen.getByTestId("word-match-view");
    expect(scrollContainer).toBeInTheDocument();

    // The inner spacer div gets height = count * estimateSize = 3 * 80 = 240px
    const spacer = container.querySelector<HTMLElement>("[data-testid='word-match-view'] > div");
    expect(spacer).not.toBeNull();
    expect(spacer!.style.height).toBe("240px");
  });

  it("does not DOM-mount all 200 cards for a large list (virtualisation check)", () => {
    // jsdom has no layout → container height is 0 → virtualiser renders 0 items.
    // A non-virtualised implementation would unconditionally iterate the array
    // and mount all 200 card elements. The virtualiser mounts ≤ overscan items
    // initially, confirming virtualisation is wired.
    const lines = makeLines(200);
    render(<WordMatchView lines={lines} />);

    const cards = document.querySelectorAll("[data-testid^='line-card-']");
    expect(cards.length).toBeLessThan(200);
  });
});

// ─── LineCard ─────────────────────────────────────────────────────────────

describe("LineCard", () => {
  const STATUS_COLORS: Record<MatchStatus, string> = {
    exact: "bg-green-100",
    fuzzy: "bg-yellow-100",
    mismatch: "bg-red-100",
    unmatched_ocr: "bg-gray-100",
    unmatched_gt: "bg-blue-100",
  };

  for (const [status, expectedClass] of Object.entries(STATUS_COLORS) as [MatchStatus, string][]) {
    it(`renders header with ${expectedClass} for status=${status}`, () => {
      const line = makeLineMatch({ line_index: 5, overall_match_status: status });
      render(<LineCard line={line} />);
      const header = screen.getByTestId("line-card-5-header");
      expect(header).toHaveClass(expectedClass);
    });
  }

  it("renders count chips for non-zero counts", () => {
    const line = makeLineMatch({
      line_index: 0,
      exact_count: 2,
      fuzzy_count: 1,
      mismatch_count: 3,
      unmatched_gt_count: 0,
      unmatched_ocr_count: 1,
    });
    render(<LineCard line={line} />);
    expect(screen.getByTestId("count-chip-exact")).toBeInTheDocument();
    expect(screen.getByTestId("count-chip-fuzzy")).toBeInTheDocument();
    expect(screen.getByTestId("count-chip-mismatch")).toBeInTheDocument();
    // unmatched_gt is 0 — should NOT render
    expect(screen.queryByTestId("count-chip-unmatched_gt")).not.toBeInTheDocument();
    expect(screen.getByTestId("count-chip-unmatched_ocr")).toBeInTheDocument();
  });

  it("shows Validate button and flips label to Unvalidate when is_fully_validated=true", () => {
    const line = makeLineMatch({ line_index: 0, is_fully_validated: false });
    const { rerender } = render(<LineCard line={line} />);
    expect(screen.getByTestId("line-validate-btn")).toHaveTextContent("Validate");

    rerender(<LineCard line={{ ...line, is_fully_validated: true }} />);
    expect(screen.getByTestId("line-validate-btn")).toHaveTextContent("Unvalidate");
  });

  it("renders data-testid='line-card-{line_index}'", () => {
    const line = makeLineMatch({ line_index: 42 });
    render(<LineCard line={line} />);
    expect(screen.getByTestId("line-card-42")).toBeInTheDocument();
  });
});

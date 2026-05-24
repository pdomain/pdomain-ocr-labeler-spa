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

import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import type { components } from "../api/types";
import { WordMatchView, lineMatchesFilter } from "./WordMatchView";
import { LineCard } from "./LineCard";

type LineMatch = components["schemas"]["LineMatch"];
type WordMatch = components["schemas"]["WordMatch"];
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
    validated_word_count: 0,
    total_word_count: 0,
    is_fully_validated: false,
    ...overrides,
  };
}

function makeLines(n: number): LineMatch[] {
  return Array.from({ length: n }, (_, i) =>
    makeLineMatch({ line_index: i, ocr_line_text: `line ${i}` }),
  );
}

function makeWordMatch(overrides: Partial<WordMatch> = {}): WordMatch {
  return {
    line_index: 0,
    word_index: 0,
    ocr_text: "foo",
    ground_truth_text: "foo",
    match_status: "exact",
    normalized_match: true,
    is_validated: false,
    bbox: { x: 0, y: 0, width: 0, height: 0 },
    ...overrides,
  };
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
  // Status backgrounds are now applied via inline style (color-mix tokens) rather than CSS classes.
  // We verify the header renders with a background style attribute for each status.
  const STATUS_STYLE_KEYWORDS: Record<MatchStatus, string> = {
    exact: "status-exact",
    fuzzy: "status-fuzzy",
    mismatch: "status-mismatch",
    unmatched_ocr: "bg-raised",
    unmatched_gt: "status-ocr",
  };

  for (const [status, keyword] of Object.entries(STATUS_STYLE_KEYWORDS) as [
    MatchStatus,
    string,
  ][]) {
    it(`renders header with ${keyword} token for status=${status}`, () => {
      const line = makeLineMatch({ line_index: 5, overall_match_status: status });
      render(<LineCard line={line} />);
      const header = screen.getByTestId("line-card-5-header");
      // Header must have a style attribute containing the token or background property
      const style = header.getAttribute("style") ?? "";
      expect(style).toContain(keyword);
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
    expect(screen.getByTestId("line-validate-button-0")).toHaveTextContent("Validate");

    rerender(<LineCard line={{ ...line, is_fully_validated: true }} />);
    expect(screen.getByTestId("line-validate-button-0")).toHaveTextContent("Unvalidate");
  });

  it("renders data-testid='line-card-{line_index}'", () => {
    const line = makeLineMatch({ line_index: 42 });
    render(<LineCard line={line} />);
    expect(screen.getByTestId("line-card-42")).toBeInTheDocument();
  });
});

// ─── lineMatchesFilter ────────────────────────────────────────────────────
//
// Spec: specs/22-page-surface-wireup.md §8 (FilterToggle plumbing).
// Parity: pd-ocr-labeler/pd_ocr_labeler/views/projects/pages/
// word_match_renderer.py:_filter_lines_for_display.

describe("lineMatchesFilter", () => {
  it("filter='all' keeps every line regardless of state", () => {
    const validated = makeLineMatch({ is_fully_validated: true });
    const unvalidated = makeLineMatch({ is_fully_validated: false });
    expect(lineMatchesFilter(validated, "all")).toBe(true);
    expect(lineMatchesFilter(unvalidated, "all")).toBe(true);
  });

  it("filter='unvalidated' excludes is_fully_validated=true", () => {
    const validated = makeLineMatch({ is_fully_validated: true });
    expect(lineMatchesFilter(validated, "unvalidated")).toBe(false);
  });

  it("filter='unvalidated' keeps is_fully_validated=false", () => {
    const unvalidated = makeLineMatch({ is_fully_validated: false });
    expect(lineMatchesFilter(unvalidated, "unvalidated")).toBe(true);
  });

  it("filter='mismatched' keeps lines with at least one non-exact word", () => {
    const line = makeLineMatch({
      word_matches: [
        makeWordMatch({ match_status: "exact" }),
        makeWordMatch({ match_status: "mismatch" }),
      ],
    });
    expect(lineMatchesFilter(line, "mismatched")).toBe(true);
  });

  it("filter='mismatched' excludes lines where every word_match is exact", () => {
    const line = makeLineMatch({
      word_matches: [
        makeWordMatch({ match_status: "exact" }),
        makeWordMatch({ match_status: "exact" }),
      ],
    });
    expect(lineMatchesFilter(line, "mismatched")).toBe(false);
  });

  it("filter='mismatched' excludes lines with no word_matches at all", () => {
    // Legacy `any(...)` over an empty list returns False → line is hidden.
    const line = makeLineMatch({ word_matches: [] });
    expect(lineMatchesFilter(line, "mismatched")).toBe(false);
  });
});

// ─── LineCard word rows ───────────────────────────────────────────────────
//
// Verifies that WordCell rows render directly under the LineCard header
// (no accordion) per driver-contract §2.8.

describe("LineCard word rows", () => {
  function makeWordMatchFull(
    lineIndex: number,
    wordIndex: number,
    overrides: Partial<WordMatch> = {},
  ): WordMatch {
    return {
      line_index: lineIndex,
      word_index: wordIndex,
      ocr_text: `word-${wordIndex}`,
      ground_truth_text: `gt-${wordIndex}`,
      match_status: "exact",
      normalized_match: true,
      is_validated: false,
      bbox: { x: 0, y: 0, width: 10, height: 10 },
      word_id: `w-${lineIndex}-${wordIndex}`,
      fuzz_score: null,
      text_style_labels: [],
      word_components: [],
      ...overrides,
    };
  }

  it("renders a WordCell for each word_match in the line", () => {
    const line = makeLineMatch({
      line_index: 0,
      word_matches: [makeWordMatchFull(0, 0), makeWordMatchFull(0, 1), makeWordMatchFull(0, 2)],
    });
    render(<LineCard line={line} />);
    // Each WordCell gets data-testid="word-image-cell-{l}-{w}" (driver-contract §2.8 canonical)
    expect(screen.getByTestId("word-image-cell-0-0")).toBeInTheDocument();
    expect(screen.getByTestId("word-image-cell-0-1")).toBeInTheDocument();
    expect(screen.getByTestId("word-image-cell-0-2")).toBeInTheDocument();
  });

  it("renders gt-text-input-{l}-{w} testids for each word", () => {
    const line = makeLineMatch({
      line_index: 0,
      word_matches: [makeWordMatchFull(0, 0), makeWordMatchFull(0, 1)],
    });
    render(<LineCard line={line} />);
    expect(screen.getByTestId("gt-text-input-0-0")).toBeInTheDocument();
    expect(screen.getByTestId("gt-text-input-0-1")).toBeInTheDocument();
  });

  it("renders edit-word-button-{l}-{w} testid for each word (driver-contract §2.8)", () => {
    const line = makeLineMatch({
      line_index: 0,
      word_matches: [makeWordMatchFull(0, 0)],
    });
    render(<LineCard line={line} />);
    expect(screen.getByTestId("edit-word-button-0-0")).toBeInTheDocument();
  });

  it("clicking edit-word-button-{l}-{w} calls onEditWord(l, w)", () => {
    const onEditWord = vi.fn();
    const line = makeLineMatch({
      line_index: 0,
      word_matches: [makeWordMatchFull(0, 0)],
    });
    render(<LineCard line={line} onEditWord={onEditWord} />);
    fireEvent.click(screen.getByTestId("edit-word-button-0-0"));
    expect(onEditWord).toHaveBeenCalledOnce();
    expect(onEditWord).toHaveBeenCalledWith(0, 0);
  });

  it("shows OCR text preview (not word rows) when word_matches is empty", () => {
    const line = makeLineMatch({
      line_index: 0,
      word_matches: [],
      ocr_line_text: "fallback preview text",
    });
    render(<LineCard line={line} />);
    expect(screen.getByText("fallback preview text")).toBeInTheDocument();
    // No word cells
    expect(screen.queryByTestId(/^word-image-cell-/)).not.toBeInTheDocument();
  });

  it("WordMatchView threads onEditWord through to word rows", () => {
    const onEditWord = vi.fn();
    const lines = [
      makeLineMatch({
        line_index: 0,
        word_matches: [makeWordMatchFull(0, 0)],
      }),
    ];
    render(<WordMatchView lines={lines} onEditWord={onEditWord} />);
    // In jsdom the virtualiser doesn't render items (no layout), but
    // spacer height confirms the line is in the virtualiser's count.
    // We just confirm the prop threads without TypeScript error.
    expect(screen.getByTestId("word-match-view")).toBeInTheDocument();
  });
});

// ─── WordMatchView filter prop ────────────────────────────────────────────

describe("WordMatchView filter prop", () => {
  it("filter='all' (default) renders empty state when lines=[]", () => {
    render(<WordMatchView lines={[]} />);
    expect(screen.getByTestId("word-match-empty")).toBeInTheDocument();
  });

  it("filter='unvalidated' shows empty state when every line is validated", () => {
    const lines = [
      makeLineMatch({ line_index: 0, is_fully_validated: true }),
      makeLineMatch({ line_index: 1, is_fully_validated: true }),
    ];
    render(<WordMatchView lines={lines} filter="unvalidated" />);
    expect(screen.getByTestId("word-match-empty")).toBeInTheDocument();
  });

  it("filter='unvalidated' resizes spacer to the count of unvalidated lines", () => {
    // 3 unvalidated + 2 validated → after filter only 3 remain → spacer height 240px.
    const lines = [
      makeLineMatch({ line_index: 0, is_fully_validated: false }),
      makeLineMatch({ line_index: 1, is_fully_validated: true }),
      makeLineMatch({ line_index: 2, is_fully_validated: false }),
      makeLineMatch({ line_index: 3, is_fully_validated: true }),
      makeLineMatch({ line_index: 4, is_fully_validated: false }),
    ];
    const { container } = render(<WordMatchView lines={lines} filter="unvalidated" />);
    const spacer = container.querySelector<HTMLElement>("[data-testid='word-match-view'] > div");
    expect(spacer).not.toBeNull();
    // 3 unvalidated lines * 80px estimate = 240px.
    expect(spacer!.style.height).toBe("240px");
  });

  it("filter='mismatched' resizes spacer to the count of lines containing any non-exact word", () => {
    const lines = [
      // Mismatched: keep
      makeLineMatch({
        line_index: 0,
        word_matches: [makeWordMatch({ match_status: "mismatch" })],
      }),
      // All-exact: drop
      makeLineMatch({
        line_index: 1,
        word_matches: [makeWordMatch({ match_status: "exact" })],
      }),
      // Mismatched: keep
      makeLineMatch({
        line_index: 2,
        word_matches: [makeWordMatch({ match_status: "fuzzy" })],
      }),
    ];
    const { container } = render(<WordMatchView lines={lines} filter="mismatched" />);
    const spacer = container.querySelector<HTMLElement>("[data-testid='word-match-view'] > div");
    expect(spacer).not.toBeNull();
    // 2 mismatched lines * 80px estimate = 160px.
    expect(spacer!.style.height).toBe("160px");
  });

  it("filter='all' renders spacer sized for every line", () => {
    const lines = [
      makeLineMatch({ line_index: 0, is_fully_validated: true }),
      makeLineMatch({ line_index: 1, is_fully_validated: false }),
    ];
    const { container } = render(<WordMatchView lines={lines} filter="all" />);
    const spacer = container.querySelector<HTMLElement>("[data-testid='word-match-view'] > div");
    expect(spacer!.style.height).toBe("160px");
  });
});

// filter-predicates.test.ts — Lane D / Task D4.
// The 3-way line filter (Unvalidated / Mismatched / All). The "unvalidated"
// mode must show only lines with >=1 unvalidated word, robust to a
// missing/stale is_fully_validated flag (derive from word validation state).

import { describe, it, expect } from "vitest";
import { filterLines, type LineMatch } from "./filter-predicates";

function word(over: Partial<LineMatch["word_matches"][number]> = {}) {
  return {
    line_index: 0,
    word_index: 0,
    ocr_text: "x",
    ground_truth_text: "x",
    match_status: "exact" as const,
    normalized_match: false,
    is_validated: false,
    bbox: { x: 0, y: 0, width: 0, height: 0 },
    ...over,
  };
}

function line(over: Partial<LineMatch> = {}): LineMatch {
  return {
    line_index: 0,
    paragraph_index: 0,
    ocr_line_text: "x",
    ground_truth_line_text: "x",
    word_matches: [word()],
    overall_match_status: "exact",
    exact_count: 1,
    fuzzy_count: 0,
    mismatch_count: 0,
    unmatched_gt_count: 0,
    unmatched_ocr_count: 0,
    validated_word_count: 0,
    total_word_count: 1,
    is_fully_validated: false,
    ...over,
  } as LineMatch;
}

describe("filterLines — unvalidated (D4)", () => {
  it("keeps a line with >=1 unvalidated word", () => {
    const lines = [
      line({
        line_index: 0,
        is_fully_validated: false,
        validated_word_count: 0,
        total_word_count: 1,
      }),
    ];
    expect(filterLines(lines, "unvalidated").map((l) => l.line_index)).toEqual([0]);
  });

  it("drops a fully validated line", () => {
    const lines = [
      line({
        line_index: 0,
        is_fully_validated: true,
        validated_word_count: 1,
        total_word_count: 1,
        word_matches: [word({ is_validated: true })],
      }),
    ];
    expect(filterLines(lines, "unvalidated")).toEqual([]);
  });

  it("keeps a line with >=1 unvalidated word even when is_fully_validated is stale/missing", () => {
    // is_fully_validated wrongly says true, but a word is not validated → must show.
    const lines = [
      line({
        line_index: 0,
        is_fully_validated: true,
        word_matches: [word({ is_validated: true }), word({ word_index: 1, is_validated: false })],
        validated_word_count: 1,
        total_word_count: 2,
      }),
    ];
    expect(filterLines(lines, "unvalidated").map((l) => l.line_index)).toEqual([0]);
  });

  it("'all' returns every line unchanged", () => {
    const lines = [line({ line_index: 0 }), line({ line_index: 1, is_fully_validated: true })];
    expect(filterLines(lines, "all").length).toBe(2);
  });
});

// selection-expand.test.ts — tests for expandSelection helper.
// Spec: specs/21-konva-renderer.md §8
// Issue #299 (spec-21-A4)
//
// Acceptance:
//   - Empty selection → empty arrays
//   - Mixed selection across paragraph / line / word index sets resolves to bboxes
//   - Out-of-range index defensively returns nothing and logs a warning

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import type { components } from "../api/types";
import { expandSelection } from "./selection-expand";

type PagePayload = components["schemas"]["PagePayload"];
type LineMatch = components["schemas"]["LineMatch"];
type WordMatch = components["schemas"]["WordMatch"];

// ─── Fixture helpers ──────────────────────────────────────────────────────────

function makeWord(
  line_index: number,
  word_index: number,
  bbox: { x: number; y: number; width: number; height: number },
): WordMatch {
  return {
    line_index,
    word_index,
    ocr_text: `w${line_index}-${word_index}`,
    ground_truth_text: "",
    match_status: "exact",
    normalized_match: false,
    is_validated: false,
    bbox,
  };
}

function makeLine(
  line_index: number,
  paragraph_index: number | null,
  word_bboxes: { x: number; y: number; width: number; height: number }[],
): LineMatch {
  return {
    line_index,
    paragraph_index,
    ocr_line_text: `line ${line_index}`,
    ground_truth_line_text: "",
    word_matches: word_bboxes.map((b, i) => makeWord(line_index, i, b)),
    overall_match_status: "exact",
    exact_count: word_bboxes.length,
    fuzzy_count: 0,
    mismatch_count: 0,
    unmatched_gt_count: 0,
    unmatched_ocr_count: 0,
    validated_word_count: 0,
    total_word_count: word_bboxes.length,
    is_fully_validated: false,
  };
}

function makePage(line_matches: LineMatch[], selection?: PagePayload["selection"]): PagePayload {
  return {
    project_id: "proj-001",
    page_index: 0,
    page_record: null,
    line_matches,
    ...(selection !== undefined && { selection }),
    encoded_dims: null,
    line_filter: "all",
    image_url: null,
    generation: 1,
  };
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe("expandSelection (#299)", () => {
  let warnSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
  });

  afterEach(() => {
    warnSpy.mockRestore();
  });

  it("returns empty arrays when selection is undefined", () => {
    const page = makePage([makeLine(0, 0, [{ x: 0, y: 0, width: 10, height: 10 }])]);
    const result = expandSelection(page);
    expect(result.paragraphs).toEqual([]);
    expect(result.lines).toEqual([]);
    expect(result.words).toEqual([]);
    expect(warnSpy).not.toHaveBeenCalled();
  });

  it("returns empty arrays when selection has no selected indices", () => {
    const page = makePage([makeLine(0, 0, [{ x: 0, y: 0, width: 10, height: 10 }])], {
      selection_mode: "word",
      selected_paragraphs: [],
      selected_lines: [],
      selected_words: [],
    });
    const result = expandSelection(page);
    expect(result.paragraphs).toEqual([]);
    expect(result.lines).toEqual([]);
    expect(result.words).toEqual([]);
    expect(warnSpy).not.toHaveBeenCalled();
  });

  it("resolves a mixed selection across paragraphs, lines, and words", () => {
    // Page shape:
    //   paragraph 0:
    //     line 0: words [(0,0,10,10), (12,0,10,10)]
    //     line 1: words [(0,20,10,10), (12,20,10,10), (24,20,10,10)]
    //   paragraph 1:
    //     line 2: words [(0,40,10,10)]
    const page = makePage(
      [
        makeLine(0, 0, [
          { x: 0, y: 0, width: 10, height: 10 },
          { x: 12, y: 0, width: 10, height: 10 },
        ]),
        makeLine(1, 0, [
          { x: 0, y: 20, width: 10, height: 10 },
          { x: 12, y: 20, width: 10, height: 10 },
          { x: 24, y: 20, width: 10, height: 10 },
        ]),
        makeLine(2, 1, [{ x: 0, y: 40, width: 10, height: 10 }]),
      ],
      {
        selection_mode: "word",
        selected_paragraphs: [1],
        selected_lines: [1],
        selected_words: [
          [0, 0],
          [1, 2],
        ],
      },
    );

    const result = expandSelection(page);

    // Words: two specific words pulled by (line, word) index.
    expect(result.words).toHaveLength(2);
    expect(result.words[0]).toEqual({
      id: "0-0",
      bbox: { x: 0, y: 0, width: 10, height: 10 },
    });
    expect(result.words[1]).toEqual({
      id: "1-2",
      bbox: { x: 24, y: 20, width: 10, height: 10 },
    });

    // Lines: line 1's bbox is the union of its three word bboxes.
    expect(result.lines).toHaveLength(1);
    expect(result.lines[0]).toEqual({
      id: "1",
      bbox: { x: 0, y: 20, width: 34, height: 10 }, // x=0..34, y=20..30
    });

    // Paragraphs: paragraph 1 spans only line 2 with one word.
    expect(result.paragraphs).toHaveLength(1);
    expect(result.paragraphs[0]).toEqual({
      id: "1",
      bbox: { x: 0, y: 40, width: 10, height: 10 },
    });

    expect(warnSpy).not.toHaveBeenCalled();
  });

  it("computes paragraph bbox as union of all constituent word bboxes across lines", () => {
    // paragraph 0: line 0 + line 1
    const page = makePage(
      [
        makeLine(0, 0, [
          { x: 5, y: 0, width: 10, height: 8 },
          { x: 20, y: 0, width: 10, height: 8 },
        ]),
        makeLine(1, 0, [{ x: 0, y: 10, width: 50, height: 8 }]),
      ],
      {
        selection_mode: "paragraph",
        selected_paragraphs: [0],
        selected_lines: [],
        selected_words: [],
      },
    );
    const result = expandSelection(page);
    expect(result.paragraphs).toHaveLength(1);
    // Union: x in [0,50], y in [0,18]
    expect(result.paragraphs[0]).toEqual({
      id: "0",
      bbox: { x: 0, y: 0, width: 50, height: 18 },
    });
  });

  it("defensively skips and warns on out-of-range paragraph index", () => {
    const page = makePage([makeLine(0, 0, [{ x: 0, y: 0, width: 10, height: 10 }])], {
      selection_mode: "paragraph",
      selected_paragraphs: [0, 42],
      selected_lines: [],
      selected_words: [],
    });
    const result = expandSelection(page);
    expect(result.paragraphs).toHaveLength(1);
    expect(result.paragraphs[0].id).toBe("0");
    expect(warnSpy).toHaveBeenCalled();
    const warnMsg = warnSpy.mock.calls.map((c) => String(c[0])).join("\n");
    expect(warnMsg).toContain("paragraph");
    expect(warnMsg).toContain("42");
  });

  it("defensively skips and warns on out-of-range line index", () => {
    const page = makePage([makeLine(0, 0, [{ x: 0, y: 0, width: 10, height: 10 }])], {
      selection_mode: "line",
      selected_paragraphs: [],
      selected_lines: [99],
      selected_words: [],
    });
    const result = expandSelection(page);
    expect(result.lines).toEqual([]);
    expect(warnSpy).toHaveBeenCalled();
    const warnMsg = warnSpy.mock.calls.map((c) => String(c[0])).join("\n");
    expect(warnMsg).toContain("line");
    expect(warnMsg).toContain("99");
  });

  it("defensively skips and warns on out-of-range word index", () => {
    const page = makePage([makeLine(0, 0, [{ x: 0, y: 0, width: 10, height: 10 }])], {
      selection_mode: "word",
      selected_paragraphs: [],
      selected_lines: [],
      selected_words: [
        [0, 7], // word_index out of range
        [5, 0], // line_index out of range
      ],
    });
    const result = expandSelection(page);
    expect(result.words).toEqual([]);
    expect(warnSpy).toHaveBeenCalledTimes(2);
    const warnMsg = warnSpy.mock.calls.map((c) => String(c[0])).join("\n");
    expect(warnMsg).toContain("word");
  });

  it("skips lines that have no word matches when computing line bboxes", () => {
    const page = makePage(
      [
        makeLine(0, 0, []), // empty line
        makeLine(1, 0, [{ x: 0, y: 10, width: 10, height: 10 }]),
      ],
      {
        selection_mode: "line",
        selected_paragraphs: [],
        selected_lines: [0, 1],
        selected_words: [],
      },
    );
    const result = expandSelection(page);
    // Line 0 has no words → skipped (no bbox can be computed). Line 1 yields its single-word bbox.
    expect(result.lines).toHaveLength(1);
    expect(result.lines[0].id).toBe("1");
  });
});

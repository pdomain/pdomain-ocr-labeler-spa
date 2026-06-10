// box-select-handler.test.ts — SEL-2: onBoxSelect intersection math.
//
// applyBoxSelect(pagePayload, rect, modifier) computes which words in
// the page intersect the drag rect (display pixels) and returns
// [lineIdx, wordIdx][] with REPLACE semantics (Slice A).
//
// "Display pixels" means bbox coords after rectToDisplay conversion
// (source bbox × encoded.scale). The drag rect arriving from the
// canvas is already in display space.

import { describe, it, expect } from "vitest";
import { applyBoxSelect } from "./box-select-handler";
import type { components } from "../api/types";

type PagePayload = components["schemas"]["PagePayload"];
type LineMatch = components["schemas"]["LineMatch"];
type WordMatch = components["schemas"]["WordMatch"];

function makeWord(
  lineIdx: number,
  wordIdx: number,
  x: number,
  y: number,
  w: number,
  h: number,
): WordMatch {
  return {
    line_index: lineIdx,
    word_index: wordIdx,
    ocr_text: `w${lineIdx}-${wordIdx}`,
    ground_truth_text: "",
    match_status: "exact",
    normalized_match: false,
    is_validated: false,
    bbox: { x, y, width: w, height: h },
  };
}

function makeLine(lineIdx: number, words: WordMatch[]): LineMatch {
  return {
    line_index: lineIdx,
    paragraph_index: 0,
    ocr_line_text: `line ${lineIdx}`,
    ground_truth_line_text: "",
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

function makePage(lines: LineMatch[], scale = 0.5): PagePayload {
  return {
    project_id: "p1",
    page_index: 0,
    page_record: null,
    line_matches: lines,
    selection: undefined,
    encoded_dims: {
      src_width: 1600,
      src_height: 1200,
      display_width: 800,
      display_height: 600,
      scale,
    },
    line_filter: "all",
    image_url: null,
    generation: 1,
  };
}

describe("applyBoxSelect — SEL-2 intersection math", () => {
  it("returns words whose display bbox overlaps the drag rect", () => {
    // source bbox (100,200,50,20) → display bbox (50,100,25,10) at scale 0.5
    const page = makePage([
      makeLine(0, [makeWord(0, 0, 100, 200, 50, 20), makeWord(0, 1, 300, 200, 50, 20)]),
    ]);

    // drag rect covers display (40,95) to (80,115) — overlaps word 0, not word 1
    const result = applyBoxSelect(page, { x: 40, y: 95, width: 40, height: 20 }, "replace");
    expect(result.words).toEqual([[0, 0]]);
  });

  it("returns multiple words when drag rect covers several", () => {
    const page = makePage([
      makeLine(0, [makeWord(0, 0, 100, 200, 50, 20), makeWord(0, 1, 160, 200, 50, 20)]),
      makeLine(1, [makeWord(1, 0, 400, 200, 50, 20)]),
    ]);

    // drag rect covers display space (40,90) to (130,120) — overlaps line 0 words 0,1
    // display: word0=(50,100,25,10), word1=(80,100,25,10), word2=(200,100,25,10)
    const result = applyBoxSelect(page, { x: 40, y: 90, width: 100, height: 35 }, "replace");
    expect(result.words).toHaveLength(2);
    expect(result.words).toContainEqual([0, 0]);
    expect(result.words).toContainEqual([0, 1]);
  });

  it("returns empty array when drag rect covers no words", () => {
    const page = makePage([makeLine(0, [makeWord(0, 0, 100, 200, 50, 20)])]);

    // drag rect far from any word in display space
    const result = applyBoxSelect(page, { x: 0, y: 0, width: 10, height: 10 }, "replace");
    expect(result.words).toHaveLength(0);
  });

  it("skips words with null word_index", () => {
    const page = makePage([
      makeLine(0, [{ ...makeWord(0, 0, 100, 200, 50, 20), word_index: null }]),
    ]);

    const result = applyBoxSelect(page, { x: 40, y: 95, width: 40, height: 20 }, "replace");
    expect(result.words).toHaveLength(0);
  });

  it("returns empty when page has no encoded_dims (fallback scale 1)", () => {
    // Without encoded_dims, bboxes are treated as display-space directly (scale=1).
    const page: PagePayload = {
      project_id: "p1",
      page_index: 0,
      page_record: null,
      line_matches: [makeLine(0, [makeWord(0, 0, 10, 10, 20, 10)])],
      selection: undefined,
      encoded_dims: null,
      line_filter: "all",
      image_url: null,
      generation: 1,
    };
    // word bbox in source is (10,10,20,10), no scale → display is same
    const result = applyBoxSelect(page, { x: 5, y: 5, width: 30, height: 20 }, "replace");
    expect(result.words).toEqual([[0, 0]]);
  });

  it("line target returns intersecting line ids instead of word tuples", () => {
    const page = makePage([
      makeLine(0, [makeWord(0, 0, 100, 200, 50, 20), makeWord(0, 1, 160, 200, 50, 20)]),
      makeLine(1, [makeWord(1, 0, 400, 200, 50, 20)]),
    ]);

    const result = applyBoxSelect(
      page,
      { x: 40, y: 90, width: 100, height: 35 },
      "replace",
      "line",
    );

    expect(result.lines).toEqual([0]);
    expect(result.words).toEqual([]);
  });
});

// selection-walk.test.ts — Tests for hierarchy navigation helpers (Slice 15).
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 15.

import { describe, it, expect } from "vitest";
import { nextSibling, walkUp, walkDown, pathLevel } from "./selection-walk";
import type { components } from "../api/types";

type PagePayload = components["schemas"]["PagePayload"];
type WordMatch = components["schemas"]["WordMatch"];

function w(line: number, idx: number, ocr: string): WordMatch {
  return {
    line_index: line,
    word_index: idx,
    ocr_text: ocr,
    ground_truth_text: ocr,
    match_status: "exact",
    normalized_match: false,
    is_validated: false,
  };
}

function makePage(): PagePayload {
  return {
    project_id: "p1",
    page_index: 0,
    line_filter: "all",
    generation: 0,
    line_matches: [
      // Para 0: lines 0, 1
      {
        line_index: 0,
        paragraph_index: 0,
        ocr_line_text: "alpha beta",
        ground_truth_line_text: "alpha beta",
        word_matches: [w(0, 0, "alpha"), w(0, 1, "beta")],
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
        ocr_line_text: "gamma",
        ground_truth_line_text: "gamma",
        word_matches: [w(1, 0, "gamma")],
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
      // Para 1: line 2
      {
        line_index: 2,
        paragraph_index: 1,
        ocr_line_text: "delta epsilon",
        ground_truth_line_text: "delta epsilon",
        word_matches: [w(2, 0, "delta"), w(2, 1, "epsilon")],
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

describe("pathLevel", () => {
  it("returns 'none' for empty path", () => {
    expect(pathLevel({})).toBe("none");
  });
  it("returns deepest non-undefined level", () => {
    expect(pathLevel({ paraId: 0 })).toBe("para");
    expect(pathLevel({ paraId: 0, lineId: 1 })).toBe("line");
    expect(pathLevel({ paraId: 0, lineId: 1, wordId: [1, 0] })).toBe("word");
    expect(pathLevel({ blockId: "b1" })).toBe("block");
  });
});

describe("nextSibling — word level", () => {
  const page = makePage();

  it("walks forward to next word in line", () => {
    const out = nextSibling({ paraId: 0, lineId: 0, wordId: [0, 0] }, page, "next");
    expect(out.wordId).toEqual([0, 1]);
  });

  it("walks backward to prev word in line", () => {
    const out = nextSibling({ paraId: 0, lineId: 0, wordId: [0, 1] }, page, "prev");
    expect(out.wordId).toEqual([0, 0]);
  });

  it("at last word: stays put (no wrap)", () => {
    const path = { paraId: 0, lineId: 0, wordId: [0, 1] as [number, number] };
    const out = nextSibling(path, page, "next");
    expect(out).toEqual(path);
  });

  it("at first word: prev keeps path unchanged", () => {
    const path = { paraId: 0, lineId: 0, wordId: [0, 0] as [number, number] };
    const out = nextSibling(path, page, "prev");
    expect(out).toEqual(path);
  });
});

describe("nextSibling — line level", () => {
  const page = makePage();

  it("walks to next line within same paragraph", () => {
    const out = nextSibling({ paraId: 0, lineId: 0 }, page, "next");
    expect(out.lineId).toBe(1);
  });

  it("does not cross paragraph boundary (last line of para)", () => {
    const path = { paraId: 0, lineId: 1 };
    const out = nextSibling(path, page, "next");
    expect(out).toEqual(path);
  });

  it("falls back to global ordering when paraId is undefined", () => {
    const out = nextSibling({ lineId: 1 }, page, "next");
    expect(out.lineId).toBe(2);
  });
});

describe("nextSibling — para level", () => {
  const page = makePage();

  it("walks to next paragraph", () => {
    const out = nextSibling({ paraId: 0 }, page, "next");
    expect(out.paraId).toBe(1);
  });

  it("stops at last paragraph", () => {
    const path = { paraId: 1 };
    expect(nextSibling(path, page, "next")).toEqual(path);
  });
});

describe("walkUp", () => {
  const page = makePage();

  it("from word: drops wordId, keeps line/para", () => {
    const out = walkUp({ paraId: 0, lineId: 0, wordId: [0, 0] }, page);
    expect(out).toEqual({ paraId: 0, lineId: 0 });
  });

  it("from line: drops lineId", () => {
    const out = walkUp({ paraId: 0, lineId: 0 }, page);
    expect(out).toEqual({ paraId: 0 });
  });

  it("from para: drops paraId", () => {
    const out = walkUp({ paraId: 0 }, page);
    expect(out).toEqual({});
  });

  it("from empty: stays empty", () => {
    expect(walkUp({}, page)).toEqual({});
  });
});

describe("walkDown", () => {
  const page = makePage();

  it("from none: descends to first paragraph", () => {
    const out = walkDown({}, page);
    expect(out.paraId).toBe(0);
  });

  it("from para: descends to first line in that para", () => {
    const out = walkDown({ paraId: 1 }, page);
    expect(out.lineId).toBe(2);
  });

  it("from line: descends to first word in that line", () => {
    const out = walkDown({ paraId: 1, lineId: 2 }, page);
    expect(out.wordId).toEqual([2, 0]);
  });

  it("from word: stays put", () => {
    const path = { paraId: 0, lineId: 0, wordId: [0, 0] as [number, number] };
    expect(walkDown(path, page)).toEqual(path);
  });

  it("from line with no words: stays put", () => {
    const page2: PagePayload = {
      ...page,
      line_matches: [
        {
          line_index: 0,
          paragraph_index: 0,
          ocr_line_text: "",
          ground_truth_line_text: "",
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
    const path = { paraId: 0, lineId: 0 };
    expect(walkDown(path, page2)).toEqual(path);
  });
});

// Helper: page where LineMatch objects carry numeric block_index values.
// Block 0: lines 0, 1 (para 0). Block 1: line 2 (para 1).
function makePageWithBlocks(): PagePayload {
  return {
    project_id: "p1",
    page_index: 0,
    line_filter: "all",
    generation: 0,
    line_matches: [
      {
        line_index: 0,
        paragraph_index: 0,
        block_index: 0,
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
        paragraph_index: 0,
        block_index: 0,
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
      {
        line_index: 2,
        paragraph_index: 1,
        block_index: 1,
        ocr_line_text: "gamma",
        ground_truth_line_text: "gamma",
        word_matches: [w(2, 0, "gamma")],
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

describe("nextSibling — block level (FO-7)", () => {
  const page = makePageWithBlocks();

  it("walks forward to next block", () => {
    const out = nextSibling({ blockId: "0" }, page, "next");
    expect(out.blockId).toBe("1");
  });

  it("walks backward to prev block", () => {
    const out = nextSibling({ blockId: "1" }, page, "prev");
    expect(out.blockId).toBe("0");
  });

  it("stops at last block (next)", () => {
    const path = { blockId: "1" };
    expect(nextSibling(path, page, "next")).toEqual(path);
  });

  it("stops at first block (prev)", () => {
    const path = { blockId: "0" };
    expect(nextSibling(path, page, "prev")).toEqual(path);
  });

  it("no-op when all lines have null block_index", () => {
    // Page with no block_index set → blockIds() returns [] → falls through.
    const flatPage = makePage(); // makePage() has no block_index fields
    const path = { blockId: "synthetic-b1" };
    expect(nextSibling(path, flatPage, "next")).toEqual(path);
  });

  it("no-op when blockId is a non-numeric string", () => {
    const path = { blockId: "synthetic-b1" };
    expect(nextSibling(path, page, "next")).toEqual(path);
  });

  it("walkUp from block drops blockId", () => {
    const out = walkUp({ blockId: "0" }, page);
    expect(out).toEqual({});
  });

  it("walkDown from block descends to first paragraph", () => {
    const out = walkDown({ blockId: "0" }, page);
    expect(out.paraId).toBe(0);
  });
});

// CU-4.2 plan test: 3-block page — middle-block sibling walk.
describe("nextSibling — 3-block page (CU-4.2)", () => {
  // Minimal 3-block page: one line per block.
  const page3blocks: PagePayload = {
    project_id: "p1",
    page_index: 0,
    line_filter: "all",
    generation: 0,
    line_matches: [
      {
        line_index: 0,
        paragraph_index: 0,
        block_index: 0,
        ocr_line_text: "a",
        ground_truth_line_text: "a",
        word_matches: [w(0, 0, "a")],
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
        block_index: 1,
        ocr_line_text: "b",
        ground_truth_line_text: "b",
        word_matches: [w(1, 0, "b")],
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
        paragraph_index: 2,
        block_index: 2,
        ocr_line_text: "c",
        ground_truth_line_text: "c",
        word_matches: [w(2, 0, "c")],
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

  it("nextSibling({blockId:'1'}, page, 'next') → blockId:'2'", () => {
    const out = nextSibling({ blockId: "1" }, page3blocks, "next");
    expect(out.blockId).toBe("2");
  });

  it("nextSibling({blockId:'1'}, page, 'prev') → blockId:'0'", () => {
    const out = nextSibling({ blockId: "1" }, page3blocks, "prev");
    expect(out.blockId).toBe("0");
  });
});

describe("paragraph_index null bucket", () => {
  const page: PagePayload = {
    project_id: "p1",
    page_index: 0,
    line_filter: "all",
    generation: 0,
    line_matches: [
      {
        line_index: 0,
        paragraph_index: 0,
        ocr_line_text: "a",
        ground_truth_line_text: "a",
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
        line_index: 1,
        paragraph_index: null,
        ocr_line_text: "b",
        ground_truth_line_text: "b",
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

  it("nextSibling para 0 → null bucket", () => {
    const out = nextSibling({ paraId: 0 }, page, "next");
    expect(out.paraId).toBeNull();
  });

  it("walkDown into null paragraph picks its lines", () => {
    const out = walkDown({ paraId: null }, page);
    expect(out.lineId).toBe(1);
  });
});

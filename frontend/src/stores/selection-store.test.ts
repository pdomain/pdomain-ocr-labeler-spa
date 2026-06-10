// selection-store.test.ts — Tests for the hierarchical selection layer (Slice 15).
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 15.
// Slice B: toggleWord (SEL-4, SEL-5) — additive multi-select across blocks.

import { describe, it, expect, beforeEach } from "vitest";
import {
  selectionStore,
  clearSelection,
  selectBlock,
  selectPara,
  selectLine,
  selectWord,
  toggleWord,
  promoteCompleteWordLines,
  walkSibling,
  walkLevel,
} from "./selection-store";
import type { components } from "../api/types";

type PagePayload = components["schemas"]["PagePayload"];
type WordMatch = components["schemas"]["WordMatch"];

function w(line: number, idx: number): WordMatch {
  return {
    line_index: line,
    word_index: idx,
    ocr_text: `w${line}-${idx}`,
    ground_truth_text: `w${line}-${idx}`,
    match_status: "exact",
    normalized_match: false,
    is_validated: false,
    bbox: { x: 0, y: 0, width: 0, height: 0 },
  };
}

function makePage(): PagePayload {
  return {
    project_id: "p1",
    page_index: 0,
    line_filter: "all",
    generation: 0,
    line_matches: [
      {
        line_index: 0,
        paragraph_index: 0,
        ocr_line_text: "a b",
        ground_truth_line_text: "a b",
        word_matches: [w(0, 0), w(0, 1)],
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
        ocr_line_text: "c",
        ground_truth_line_text: "c",
        word_matches: [w(1, 0)],
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
        ocr_line_text: "d",
        ground_truth_line_text: "d",
        word_matches: [w(2, 0)],
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

describe("selection-store hierarchical layer", () => {
  beforeEach(() => {
    clearSelection();
  });

  it("initial level is 'none' and path is empty", () => {
    const s = selectionStore.getState();
    expect(s.level).toBe("none");
    expect(s.path).toEqual({});
  });

  it("selectBlock sets level=block and path.blockId", () => {
    selectBlock("b1");
    const s = selectionStore.getState();
    expect(s.level).toBe("block");
    expect(s.path.blockId).toBe("b1");
    expect(s.selectedParagraphs).toEqual([]);
  });

  it("selectPara sets level=para and updates legacy selectedParagraphs", () => {
    selectPara(0);
    const s = selectionStore.getState();
    expect(s.level).toBe("para");
    expect(s.path.paraId).toBe(0);
    expect(s.selectedParagraphs).toEqual([0]);
    expect(s.selectedLines).toEqual([]);
    expect(s.selectedWords).toEqual([]);
  });

  it("selectPara(null) treats the null bucket distinctly", () => {
    selectPara(null);
    const s = selectionStore.getState();
    expect(s.level).toBe("para");
    expect(s.path.paraId).toBeNull();
    // null bucket has no concrete paragraph_index so legacy array stays empty.
    expect(s.selectedParagraphs).toEqual([]);
  });

  it("selectLine sets level=line and updates legacy selectedLines", () => {
    selectLine(2);
    const s = selectionStore.getState();
    expect(s.level).toBe("line");
    expect(s.path.lineId).toBe(2);
    expect(s.selectedLines).toEqual([2]);
  });

  it("selectWord sets level=word, path.wordId, and legacy selectedWords", () => {
    selectWord(0, 1);
    const s = selectionStore.getState();
    expect(s.level).toBe("word");
    expect(s.path.wordId).toEqual([0, 1]);
    expect(s.path.lineId).toBe(0);
    expect(s.selectedWords).toEqual([[0, 1]]);
  });

  it("switching levels clears previous legacy arrays", () => {
    selectLine(2);
    expect(selectionStore.getState().selectedLines).toEqual([2]);
    selectWord(0, 0);
    const s = selectionStore.getState();
    expect(s.selectedLines).toEqual([]);
    expect(s.selectedWords).toEqual([[0, 0]]);
  });

  it("promotes selected words to line selection when all selectable words in a line are selected", () => {
    const page = makePage();
    toggleWord(0, 0, "replace");
    toggleWord(0, 1, "toggle");

    promoteCompleteWordLines(page);

    const s = selectionStore.getState();
    expect(s.selectedLines).toEqual([0]);
    expect(s.selectedWords).toEqual([]);
    expect(s.level).toBe("line");
    expect(s.path.lineId).toBe(0);
  });

  it("clearSelection wipes both layers", () => {
    selectWord(0, 0);
    clearSelection();
    const s = selectionStore.getState();
    expect(s.level).toBe("none");
    expect(s.path).toEqual({});
    expect(s.selectedWords).toEqual([]);
  });

  it("walkSibling next at word level → next word, updates legacy arrays", () => {
    const page = makePage();
    selectWord(0, 0);
    walkSibling("next", page);
    const s = selectionStore.getState();
    expect(s.path.wordId).toEqual([0, 1]);
    expect(s.selectedWords).toEqual([[0, 1]]);
  });

  it("walkSibling next at line level → next line in same para", () => {
    const page = makePage();
    selectLine(0);
    // Manually set paraId so paragraph-bound walking applies.
    selectionStore.setState((p) => ({ ...p, path: { ...p.path, paraId: 0 } }));
    walkSibling("next", page);
    expect(selectionStore.getState().path.lineId).toBe(1);
  });

  it("walkSibling at boundary is a no-op", () => {
    const page = makePage();
    selectWord(0, 1); // last word in line 0
    walkSibling("next", page);
    expect(selectionStore.getState().path.wordId).toEqual([0, 1]);
  });

  it("walkSibling when level=none is a no-op", () => {
    const page = makePage();
    walkSibling("next", page);
    expect(selectionStore.getState().level).toBe("none");
  });

  it("walkLevel up from word → line", () => {
    const page = makePage();
    selectWord(0, 0);
    walkLevel("up", page);
    const s = selectionStore.getState();
    expect(s.level).toBe("line");
    expect(s.path.wordId).toBeUndefined();
    expect(s.path.lineId).toBe(0);
    expect(s.selectedLines).toEqual([0]);
  });

  it("walkLevel down from para → first line", () => {
    const page = makePage();
    selectPara(1);
    walkLevel("down", page);
    const s = selectionStore.getState();
    expect(s.level).toBe("line");
    expect(s.path.lineId).toBe(2);
  });

  it("walkLevel up to none clears path completely", () => {
    const page = makePage();
    selectPara(0);
    walkLevel("up", page);
    const s = selectionStore.getState();
    expect(s.level).toBe("none");
    expect(s.path).toEqual({});
  });

  it("notifies subscribers on selection change", () => {
    let count = 0;
    const unsub = selectionStore.subscribe(() => {
      count += 1;
    });
    selectWord(0, 0);
    selectLine(1);
    unsub();
    selectWord(0, 0);
    expect(count).toBe(2);
  });

  it("preserves dragRect across selection changes", () => {
    selectionStore.setState((p) => ({ ...p, dragRect: { x: 0, y: 0, w: 10, h: 10 } }));
    selectLine(0);
    expect(selectionStore.getState().dragRect).toEqual({ x: 0, y: 0, w: 10, h: 10 });
  });
});

// ─── SEL-4/SEL-5: toggleWord additive multi-select ─────────────────────────
describe("toggleWord (SEL-4, SEL-5 — Slice B additive multi-select)", () => {
  beforeEach(() => {
    clearSelection();
  });

  it("replace mode: single word replaces entire selection, sets level=word", () => {
    toggleWord(0, 1, "replace");
    const s = selectionStore.getState();
    expect(s.selectedWords).toEqual([[0, 1]]);
    expect(s.level).toBe("word");
  });

  it("replace mode after prior multi-select: discards prior words", () => {
    toggleWord(0, 0, "replace");
    toggleWord(1, 0, "replace");
    // second replace should drop the first
    const s = selectionStore.getState();
    expect(s.selectedWords).toEqual([[1, 0]]);
  });

  it("toggle mode: adds word not currently selected (SEL-4 cross-block additive)", () => {
    toggleWord(0, 0, "replace");
    toggleWord(1, 0, "toggle"); // different line
    const s = selectionStore.getState();
    expect(s.selectedWords).toHaveLength(2);
    expect(s.selectedWords).toContainEqual([0, 0]);
    expect(s.selectedWords).toContainEqual([1, 0]);
    expect(s.level).toBe("word");
  });

  it("toggle mode: removes word that is already selected (deselect)", () => {
    toggleWord(0, 0, "replace");
    toggleWord(1, 0, "toggle");
    toggleWord(0, 0, "toggle"); // remove first word
    const s = selectionStore.getState();
    expect(s.selectedWords).toEqual([[1, 0]]);
    expect(s.level).toBe("word");
  });

  it("toggle mode: removes last word → level drops to none", () => {
    toggleWord(0, 0, "replace");
    toggleWord(0, 0, "toggle"); // remove the only word
    const s = selectionStore.getState();
    expect(s.selectedWords).toEqual([]);
    expect(s.level).toBe("none");
  });

  it("remove mode: removes a word from selection (SEL-5 shift-click)", () => {
    toggleWord(0, 0, "replace");
    toggleWord(1, 0, "toggle");
    toggleWord(0, 0, "remove"); // shift-click to remove
    const s = selectionStore.getState();
    expect(s.selectedWords).toEqual([[1, 0]]);
  });

  it("remove mode: no-op if word was not selected", () => {
    toggleWord(0, 0, "replace");
    toggleWord(2, 0, "remove"); // word not in selection
    const s = selectionStore.getState();
    expect(s.selectedWords).toEqual([[0, 0]]);
  });

  it("preserves other state (dragRect, selectedLines) when in replace mode", () => {
    selectionStore.setState((p) => ({ ...p, dragRect: { x: 1, y: 2, width: 3, height: 4 } }));
    selectLine(5);
    toggleWord(0, 0, "replace");
    const s = selectionStore.getState();
    // word-level: line arrays cleared
    expect(s.selectedLines).toEqual([]);
    // dragRect preserved
    expect(s.dragRect).toEqual({ x: 1, y: 2, width: 3, height: 4 });
  });

  it("three-word cross-block selection accumulates via toggle mode", () => {
    toggleWord(0, 0, "replace");
    toggleWord(1, 0, "toggle");
    toggleWord(2, 0, "toggle"); // third word from yet another line
    const s = selectionStore.getState();
    expect(s.selectedWords).toHaveLength(3);
    expect(s.selectedWords).toContainEqual([0, 0]);
    expect(s.selectedWords).toContainEqual([1, 0]);
    expect(s.selectedWords).toContainEqual([2, 0]);
  });
});

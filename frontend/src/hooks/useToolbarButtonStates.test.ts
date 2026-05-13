import { describe, expect, it } from "vitest";
import {
  type PageData,
  type Selection,
  useToolbarButtonStates,
} from "./useToolbarButtonStates";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const emptySelection: Selection = {
  selection_mode: "word",
  selected_paragraphs: [],
  selected_lines: [],
  selected_words: [],
};

/** Page with 3 lines, each with 2 words. Line i has paragraph_index = Math.floor(i/2). */
function makePage(overrides?: {
  validatedWords?: [number, number][];
}): PageData {
  const validatedSet = new Set(
    (overrides?.validatedWords ?? []).map(([li, wi]) => `${li}-${wi}`),
  );
  return {
    lines: [0, 1, 2].map((li) => ({
      line_index: li,
      paragraph_index: Math.floor(li / 2),
      words: [0, 1].map((wi) => ({
        line_index: li,
        word_index: wi,
        is_validated: validatedSet.has(`${li}-${wi}`),
      })),
      validated_word_count: [0, 1].filter((wi) =>
        validatedSet.has(`${li}-${wi}`),
      ).length,
      total_word_count: 2,
    })),
  };
}

const emptyPage: PageData = { lines: [] };

// ---------------------------------------------------------------------------
// §1 Page row — always enabled (selection-independent)
// ---------------------------------------------------------------------------

describe("page row — always enabled", () => {
  it("refine, expand_refine, expand, gt_to_ocr, ocr_to_gt are true with empty selection", () => {
    const s = useToolbarButtonStates(emptySelection, emptyPage);
    expect(s.page_refine).toBe(true);
    expect(s.page_expand_refine).toBe(true);
    expect(s.page_expand).toBe(true);
    expect(s.page_gt_to_ocr).toBe(true);
    expect(s.page_ocr_to_gt).toBe(true);
  });

  it("page buttons are true even when paragraphs/lines/words are selected", () => {
    const sel: Selection = {
      selection_mode: "word",
      selected_paragraphs: [0],
      selected_lines: [0, 1],
      selected_words: [[0, 0]],
    };
    const s = useToolbarButtonStates(sel, emptyPage);
    expect(s.page_refine).toBe(true);
    expect(s.page_expand_refine).toBe(true);
    expect(s.page_expand).toBe(true);
    expect(s.page_gt_to_ocr).toBe(true);
    expect(s.page_ocr_to_gt).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// §2 Page validate / unvalidate
// ---------------------------------------------------------------------------

describe("page validate / unvalidate", () => {
  it("page_validate is false when page has no words", () => {
    const s = useToolbarButtonStates(emptySelection, emptyPage);
    expect(s.page_validate).toBe(false);
  });

  it("page_unvalidate is false when page has no validated words", () => {
    const s = useToolbarButtonStates(emptySelection, makePage());
    expect(s.page_unvalidate).toBe(false);
  });

  it("page_validate is true when some words are unvalidated", () => {
    const s = useToolbarButtonStates(emptySelection, makePage());
    expect(s.page_validate).toBe(true);
  });

  it("page_validate is false when all words are validated", () => {
    const allValidated = makePage({
      validatedWords: [
        [0, 0],
        [0, 1],
        [1, 0],
        [1, 1],
        [2, 0],
        [2, 1],
      ],
    });
    const s = useToolbarButtonStates(emptySelection, allValidated);
    expect(s.page_validate).toBe(false);
  });

  it("page_unvalidate is true when some words are validated", () => {
    const s = useToolbarButtonStates(
      emptySelection,
      makePage({ validatedWords: [[0, 0]] }),
    );
    expect(s.page_unvalidate).toBe(true);
  });

  it("page_unvalidate is false when no words are validated", () => {
    const s = useToolbarButtonStates(emptySelection, makePage());
    expect(s.page_unvalidate).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// §3 Para row — requires ≥1 paragraph selected
// ---------------------------------------------------------------------------

describe("para row — requires ≥1 paragraph selected", () => {
  it("all para buttons are false with empty selection", () => {
    const s = useToolbarButtonStates(emptySelection, makePage());
    expect(s.para_merge).toBe(false);
    expect(s.para_refine).toBe(false);
    expect(s.para_expand_refine).toBe(false);
    expect(s.para_expand).toBe(false);
    expect(s.para_split_after).toBe(false);
    expect(s.para_split_selected).toBe(false);
    expect(s.para_gt_to_ocr).toBe(false);
    expect(s.para_ocr_to_gt).toBe(false);
    expect(s.para_validate).toBe(false);
    expect(s.para_unvalidate).toBe(false);
    expect(s.para_delete).toBe(false);
  });

  it("non-merge para buttons are true with 1 paragraph selected", () => {
    const sel: Selection = {
      ...emptySelection,
      selected_paragraphs: [0],
    };
    const s = useToolbarButtonStates(sel, makePage());
    expect(s.para_refine).toBe(true);
    expect(s.para_expand_refine).toBe(true);
    expect(s.para_expand).toBe(true);
    expect(s.para_split_after).toBe(true);
    expect(s.para_split_selected).toBe(true);
    expect(s.para_gt_to_ocr).toBe(true);
    expect(s.para_ocr_to_gt).toBe(true);
    expect(s.para_delete).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// §4 Para merge — requires ≥2 paragraphs
// ---------------------------------------------------------------------------

describe("para merge", () => {
  it("para_merge is false with 1 paragraph selected", () => {
    const sel: Selection = { ...emptySelection, selected_paragraphs: [0] };
    const s = useToolbarButtonStates(sel, emptyPage);
    expect(s.para_merge).toBe(false);
  });

  it("para_merge is true with 2 paragraphs selected", () => {
    const sel: Selection = { ...emptySelection, selected_paragraphs: [0, 1] };
    const s = useToolbarButtonStates(sel, emptyPage);
    expect(s.para_merge).toBe(true);
  });

  it("para_merge is true with 3 paragraphs selected", () => {
    const sel: Selection = {
      ...emptySelection,
      selected_paragraphs: [0, 1, 2],
    };
    const s = useToolbarButtonStates(sel, emptyPage);
    expect(s.para_merge).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// §5 Para validate / unvalidate
// ---------------------------------------------------------------------------

describe("para validate / unvalidate", () => {
  it("para_validate is false with no paragraphs selected", () => {
    const s = useToolbarButtonStates(emptySelection, makePage());
    expect(s.para_validate).toBe(false);
  });

  it("para_validate is true when selected para has unvalidated words", () => {
    // para 0 contains lines 0 and 1 (Math.floor(i/2))
    const sel: Selection = { ...emptySelection, selected_paragraphs: [0] };
    const s = useToolbarButtonStates(sel, makePage());
    expect(s.para_validate).toBe(true);
  });

  it("para_validate is false when all words in selected para are validated", () => {
    const sel: Selection = { ...emptySelection, selected_paragraphs: [0] };
    // para 0 = lines 0,1 → words [0,0],[0,1],[1,0],[1,1]
    const page = makePage({
      validatedWords: [
        [0, 0],
        [0, 1],
        [1, 0],
        [1, 1],
      ],
    });
    const s = useToolbarButtonStates(sel, page);
    expect(s.para_validate).toBe(false);
  });

  it("para_unvalidate is true when selected para has at least one validated word", () => {
    const sel: Selection = { ...emptySelection, selected_paragraphs: [0] };
    const page = makePage({ validatedWords: [[0, 0]] });
    const s = useToolbarButtonStates(sel, page);
    expect(s.para_unvalidate).toBe(true);
  });

  it("para_unvalidate is false when selected para has no validated words", () => {
    const sel: Selection = { ...emptySelection, selected_paragraphs: [0] };
    const s = useToolbarButtonStates(sel, makePage());
    expect(s.para_unvalidate).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// §6 Line row — requires ≥1 line selected
// ---------------------------------------------------------------------------

describe("line row — requires ≥1 line selected", () => {
  it("all line buttons are false with empty selection", () => {
    const s = useToolbarButtonStates(emptySelection, makePage());
    expect(s.line_merge).toBe(false);
    expect(s.line_refine).toBe(false);
    expect(s.line_expand_refine).toBe(false);
    expect(s.line_expand).toBe(false);
    expect(s.line_split_after).toBe(false);
    expect(s.line_split_selected).toBe(false);
    expect(s.line_to_para).toBe(false);
    expect(s.line_gt_to_ocr).toBe(false);
    expect(s.line_ocr_to_gt).toBe(false);
    expect(s.line_validate).toBe(false);
    expect(s.line_unvalidate).toBe(false);
    expect(s.line_delete).toBe(false);
  });

  it("non-merge line buttons are true with 1 line selected (no word selection for split)", () => {
    const sel: Selection = { ...emptySelection, selected_lines: [0] };
    const s = useToolbarButtonStates(sel, makePage());
    expect(s.line_refine).toBe(true);
    expect(s.line_expand_refine).toBe(true);
    expect(s.line_expand).toBe(true);
    expect(s.line_to_para).toBe(true);
    expect(s.line_gt_to_ocr).toBe(true);
    expect(s.line_ocr_to_gt).toBe(true);
    expect(s.line_delete).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// §7 Line merge — requires ≥2 lines
// ---------------------------------------------------------------------------

describe("line merge", () => {
  it("line_merge is false with 1 line selected", () => {
    const sel: Selection = { ...emptySelection, selected_lines: [0] };
    const s = useToolbarButtonStates(sel, emptyPage);
    expect(s.line_merge).toBe(false);
  });

  it("line_merge is true with 2 lines selected", () => {
    const sel: Selection = { ...emptySelection, selected_lines: [0, 1] };
    const s = useToolbarButtonStates(sel, emptyPage);
    expect(s.line_merge).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// §8 SplitAfter / SplitSelected (line scope) — all words in same line
// ---------------------------------------------------------------------------

describe("line split_after and split_selected", () => {
  it("line_split_after and line_split_selected are false with no words selected", () => {
    const sel: Selection = { ...emptySelection, selected_lines: [0] };
    const s = useToolbarButtonStates(sel, emptyPage);
    expect(s.line_split_after).toBe(false);
    expect(s.line_split_selected).toBe(false);
  });

  it("are true when selected words are all in the same line", () => {
    const sel: Selection = {
      ...emptySelection,
      selected_words: [
        [1, 0],
        [1, 1],
      ],
    };
    const s = useToolbarButtonStates(sel, emptyPage);
    expect(s.line_split_after).toBe(true);
    expect(s.line_split_selected).toBe(true);
  });

  it("are false when selected words span multiple lines", () => {
    const sel: Selection = {
      ...emptySelection,
      selected_words: [
        [0, 0],
        [1, 0],
      ],
    };
    const s = useToolbarButtonStates(sel, emptyPage);
    expect(s.line_split_after).toBe(false);
    expect(s.line_split_selected).toBe(false);
  });

  it("are true with exactly 1 selected word", () => {
    const sel: Selection = {
      ...emptySelection,
      selected_words: [[2, 0]],
    };
    const s = useToolbarButtonStates(sel, emptyPage);
    expect(s.line_split_after).toBe(true);
    expect(s.line_split_selected).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// §9 Line validate / unvalidate
// ---------------------------------------------------------------------------

describe("line validate / unvalidate", () => {
  it("line_validate is false with no lines selected", () => {
    const s = useToolbarButtonStates(emptySelection, makePage());
    expect(s.line_validate).toBe(false);
  });

  it("line_validate is true when selected line has unvalidated words", () => {
    const sel: Selection = { ...emptySelection, selected_lines: [0] };
    const s = useToolbarButtonStates(sel, makePage());
    expect(s.line_validate).toBe(true);
  });

  it("line_validate is false when all words in selected line are validated", () => {
    const sel: Selection = { ...emptySelection, selected_lines: [0] };
    const page = makePage({ validatedWords: [[0, 0], [0, 1]] });
    const s = useToolbarButtonStates(sel, page);
    expect(s.line_validate).toBe(false);
  });

  it("line_unvalidate is true when selected line has at least one validated word", () => {
    const sel: Selection = { ...emptySelection, selected_lines: [0] };
    const page = makePage({ validatedWords: [[0, 0]] });
    const s = useToolbarButtonStates(sel, page);
    expect(s.line_unvalidate).toBe(true);
  });

  it("line_unvalidate is false when no words in selected line are validated", () => {
    const sel: Selection = { ...emptySelection, selected_lines: [0] };
    const s = useToolbarButtonStates(sel, makePage());
    expect(s.line_unvalidate).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// §10 Word row — requires ≥1 word selected
// ---------------------------------------------------------------------------

describe("word row — requires ≥1 word selected", () => {
  it("all word buttons are false with empty selection", () => {
    const s = useToolbarButtonStates(emptySelection, makePage());
    expect(s.word_refine).toBe(false);
    expect(s.word_expand_refine).toBe(false);
    expect(s.word_expand).toBe(false);
    expect(s.word_w_to_l).toBe(false);
    expect(s.word_to_para).toBe(false);
    expect(s.word_gt_to_ocr).toBe(false);
    expect(s.word_ocr_to_gt).toBe(false);
    expect(s.word_validate).toBe(false);
    expect(s.word_unvalidate).toBe(false);
    expect(s.word_delete).toBe(false);
  });

  it("word buttons (except w_to_l) are true with 1 word selected", () => {
    const sel: Selection = {
      ...emptySelection,
      selected_words: [[0, 0]],
    };
    const s = useToolbarButtonStates(sel, makePage());
    expect(s.word_refine).toBe(true);
    expect(s.word_expand_refine).toBe(true);
    expect(s.word_expand).toBe(true);
    expect(s.word_to_para).toBe(true);
    expect(s.word_gt_to_ocr).toBe(true);
    expect(s.word_ocr_to_gt).toBe(true);
    expect(s.word_delete).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// §11 W→L — all selected words in same line
// ---------------------------------------------------------------------------

describe("word w_to_l", () => {
  it("word_w_to_l is false with no words selected", () => {
    const s = useToolbarButtonStates(emptySelection, emptyPage);
    expect(s.word_w_to_l).toBe(false);
  });

  it("word_w_to_l is true with 1 word selected", () => {
    const sel: Selection = { ...emptySelection, selected_words: [[0, 0]] };
    const s = useToolbarButtonStates(sel, emptyPage);
    expect(s.word_w_to_l).toBe(true);
  });

  it("word_w_to_l is true when all selected words are in the same line", () => {
    const sel: Selection = {
      ...emptySelection,
      selected_words: [
        [2, 0],
        [2, 1],
      ],
    };
    const s = useToolbarButtonStates(sel, emptyPage);
    expect(s.word_w_to_l).toBe(true);
  });

  it("word_w_to_l is false when selected words span multiple lines", () => {
    const sel: Selection = {
      ...emptySelection,
      selected_words: [
        [0, 0],
        [1, 0],
      ],
    };
    const s = useToolbarButtonStates(sel, emptyPage);
    expect(s.word_w_to_l).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// §12 word_to_para and line_to_para — requires ≥1 word OR ≥1 line selected
// ---------------------------------------------------------------------------

describe("word_to_para and line_to_para", () => {
  it("word_to_para is true with only words selected", () => {
    const sel: Selection = { ...emptySelection, selected_words: [[0, 0]] };
    const s = useToolbarButtonStates(sel, emptyPage);
    expect(s.word_to_para).toBe(true);
  });

  it("word_to_para is true with only lines selected", () => {
    const sel: Selection = { ...emptySelection, selected_lines: [0] };
    const s = useToolbarButtonStates(sel, emptyPage);
    expect(s.word_to_para).toBe(true);
  });

  it("word_to_para is false with empty selection", () => {
    const s = useToolbarButtonStates(emptySelection, emptyPage);
    expect(s.word_to_para).toBe(false);
  });

  it("line_to_para is true with only words selected", () => {
    const sel: Selection = { ...emptySelection, selected_words: [[0, 0]] };
    const s = useToolbarButtonStates(sel, emptyPage);
    expect(s.line_to_para).toBe(true);
  });

  it("line_to_para is true with only lines selected", () => {
    const sel: Selection = { ...emptySelection, selected_lines: [0] };
    const s = useToolbarButtonStates(sel, emptyPage);
    expect(s.line_to_para).toBe(true);
  });

  it("line_to_para is false with empty selection", () => {
    const s = useToolbarButtonStates(emptySelection, emptyPage);
    expect(s.line_to_para).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// §13 Word validate / unvalidate
// ---------------------------------------------------------------------------

describe("word validate / unvalidate", () => {
  it("word_validate is false with no words selected", () => {
    const s = useToolbarButtonStates(emptySelection, makePage());
    expect(s.word_validate).toBe(false);
  });

  it("word_validate is true when selected word is not validated", () => {
    const sel: Selection = { ...emptySelection, selected_words: [[0, 0]] };
    const s = useToolbarButtonStates(sel, makePage());
    expect(s.word_validate).toBe(true);
  });

  it("word_validate is false when all selected words are validated", () => {
    const sel: Selection = {
      ...emptySelection,
      selected_words: [
        [0, 0],
        [0, 1],
      ],
    };
    const page = makePage({ validatedWords: [[0, 0], [0, 1]] });
    const s = useToolbarButtonStates(sel, page);
    expect(s.word_validate).toBe(false);
  });

  it("word_unvalidate is true when at least one selected word is validated", () => {
    const sel: Selection = {
      ...emptySelection,
      selected_words: [
        [0, 0],
        [0, 1],
      ],
    };
    const page = makePage({ validatedWords: [[0, 0]] });
    const s = useToolbarButtonStates(sel, page);
    expect(s.word_unvalidate).toBe(true);
  });

  it("word_unvalidate is false when no selected words are validated", () => {
    const sel: Selection = { ...emptySelection, selected_words: [[0, 0]] };
    const s = useToolbarButtonStates(sel, makePage());
    expect(s.word_unvalidate).toBe(false);
  });

  it("word_validate is false when selected word is not in page data (unknown → treated as not validated)", () => {
    // word [5,5] doesn't exist in our page fixture
    const sel: Selection = { ...emptySelection, selected_words: [[5, 5]] };
    const s = useToolbarButtonStates(sel, makePage());
    // unknown words: is_validated defaults to false → validate should be enabled
    expect(s.word_validate).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// §14 Delete rules
// ---------------------------------------------------------------------------

describe("delete rules", () => {
  it("para_delete requires ≥1 paragraph", () => {
    expect(
      useToolbarButtonStates(emptySelection, emptyPage).para_delete,
    ).toBe(false);
    expect(
      useToolbarButtonStates(
        { ...emptySelection, selected_paragraphs: [0] },
        emptyPage,
      ).para_delete,
    ).toBe(true);
  });

  it("line_delete requires ≥1 line", () => {
    expect(useToolbarButtonStates(emptySelection, emptyPage).line_delete).toBe(
      false,
    );
    expect(
      useToolbarButtonStates(
        { ...emptySelection, selected_lines: [0] },
        emptyPage,
      ).line_delete,
    ).toBe(true);
  });

  it("word_delete requires ≥1 word", () => {
    expect(useToolbarButtonStates(emptySelection, emptyPage).word_delete).toBe(
      false,
    );
    expect(
      useToolbarButtonStates(
        { ...emptySelection, selected_words: [[0, 0]] },
        emptyPage,
      ).word_delete,
    ).toBe(true);
  });
});

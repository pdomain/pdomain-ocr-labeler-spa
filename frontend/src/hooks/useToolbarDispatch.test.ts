// S4.2 unit tests for resolveToolbarRequest — verifies word_keys injection.
import { describe, it, expect } from "vitest";
import { resolveToolbarRequest } from "./useToolbarDispatch";
import type { Selection } from "./useToolbarButtonStates";

const SELECTION_DEFAULTS: Selection = {
  selection_mode: "word",
  selected_paragraphs: [],
  selected_lines: [0],
  selected_words: [
    [0, 1],
    [0, 2],
  ],
};

describe("resolveToolbarRequest — word-word-to-line (S4.2)", () => {
  it("sends word_keys from selected_words to the split-with-selected route", () => {
    const req = resolveToolbarRequest("word_w_to_l", "proj1", 0, SELECTION_DEFAULTS);
    expect(req).not.toBeNull();
    expect(req!.url).toContain("/lines/0/split-with-selected");
    expect(req!.method).toBe("POST");
    // word_keys must be the selection's selected_words tuples.
    expect(req!.body["word_keys"]).toEqual([
      [0, 1],
      [0, 2],
    ]);
  });

  it("does not send a static mode field for word-word-to-line", () => {
    const req = resolveToolbarRequest("word_w_to_l", "proj1", 0, SELECTION_DEFAULTS);
    expect(req).not.toBeNull();
    expect(req!.body).not.toHaveProperty("mode");
  });

  it("returns null when no lines are selected (lineIndex required)", () => {
    const noLine: Selection = {
      ...SELECTION_DEFAULTS,
      selected_lines: [],
    };
    const req = resolveToolbarRequest("word_w_to_l", "proj1", 0, noLine);
    expect(req).toBeNull();
  });
});

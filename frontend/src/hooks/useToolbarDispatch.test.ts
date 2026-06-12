// S4.2 unit tests for resolveToolbarRequest — verifies word_keys injection.
// P1.7 (B-55/66): word-level selections must resolve {lineIndex} routes.
import { describe, it, expect, vi, beforeEach } from "vitest";
import React from "react";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { resolveToolbarRequest, useToolbarDispatch } from "./useToolbarDispatch";
import type { Selection } from "./useToolbarButtonStates";

vi.mock("../lib/toast", () => ({
  toast: {
    info: vi.fn(),
    success: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  },
}));
import { toast } from "../lib/toast";

const SELECTION_DEFAULTS: Selection = {
  selection_mode: "word",
  selected_paragraphs: [],
  selected_lines: [0],
  selected_words: [
    [0, 1],
    [0, 2],
  ],
};

// P1.7: the realistic word-level selection — selectWord/box-select leave
// selected_lines EMPTY. Cell enablement (allWordsInSameLine) allows the
// line-split-after / line-split-selected / word-w-to-l cells, so the
// resolver must derive the line from the words.
const WORD_ONLY_SELECTION: Selection = {
  selection_mode: "word",
  selected_paragraphs: [],
  selected_lines: [],
  selected_words: [
    [4, 1],
    [4, 2],
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
});

describe("resolveToolbarRequest — line derivation from word selections (P1.7 / B-55, B-66)", () => {
  it("word_w_to_l resolves the line from a word-only selection", () => {
    const req = resolveToolbarRequest("word_w_to_l", "proj1", 0, WORD_ONLY_SELECTION);
    expect(req).not.toBeNull();
    expect(req!.url).toContain("/lines/4/split-with-selected");
    expect(req!.body["word_keys"]).toEqual([
      [4, 1],
      [4, 2],
    ]);
  });

  it("line_split_after resolves line + word anchor from a word-only selection", () => {
    const req = resolveToolbarRequest("line_split_after", "proj1", 0, WORD_ONLY_SELECTION);
    expect(req).not.toBeNull();
    expect(req!.url).toContain("/lines/4/split-after-word");
    expect(req!.body["word_index"]).toBe(1);
  });

  it("line_split_selected resolves line + word_keys from a word-only selection", () => {
    const req = resolveToolbarRequest("line_split_selected", "proj1", 0, WORD_ONLY_SELECTION);
    expect(req).not.toBeNull();
    expect(req!.url).toContain("/lines/4/split-with-selected");
    // split-with-selected REQUIRES word_keys in the body (422 without) —
    // the old resolver never injected them for this cell.
    expect(req!.body["word_keys"]).toEqual([
      [4, 1],
      [4, 2],
    ]);
  });

  it("returns null when selected words span multiple lines (no unambiguous line)", () => {
    const crossLine: Selection = {
      ...WORD_ONLY_SELECTION,
      selected_words: [
        [4, 1],
        [5, 0],
      ],
    };
    const req = resolveToolbarRequest("word_w_to_l", "proj1", 0, crossLine);
    expect(req).toBeNull();
  });

  it("returns null when there are neither lines nor words", () => {
    const empty: Selection = {
      ...WORD_ONLY_SELECTION,
      selected_words: [],
    };
    const req = resolveToolbarRequest("word_w_to_l", "proj1", 0, empty);
    expect(req).toBeNull();
  });
});

// P1.7 acceptance bar: an enabled cell must NEVER silently no-op. When the
// resolver cannot produce a request, the dispatch must surface a toast —
// the old code resolved `null` successfully (no request, no toast).
describe("useToolbarDispatch — unresolvable actions toast instead of silently no-oping (P1.7)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  function makeWrapper() {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    return ({ children }: { children: React.ReactNode }) =>
      React.createElement(QueryClientProvider, { client: qc }, children);
  }

  it("toasts an error and fires no request when the line cannot be resolved", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const crossLine: Selection = {
      selection_mode: "word",
      selected_paragraphs: [],
      selected_lines: [],
      selected_words: [
        [4, 1],
        [5, 0],
      ],
    };
    const { result } = renderHook(() => useToolbarDispatch("proj1", 0, crossLine), {
      wrapper: makeWrapper(),
    });
    result.current("word_w_to_l");
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});

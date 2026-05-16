// WordCell.test.tsx — unit tests for the per-word grid cell with GT input.
// Spec: docs/specs/2026-05-12-word-matches-design.md §WordCell grid
// Issue #203, #241
//
// Acceptance:
//   - Renders with data-testid="word-cell-{word_id}"
//   - GT input has data-testid="gt-text-input-{l}-{w}" (spec canonical)
//   - Blur-commit: fires onCommitGt with new value when changed
//   - Blur with unchanged value: does NOT fire onCommitGt
//   - word_id used as React key / testid (not line/word index)
//   - Tag chips render for text_style_labels and word_components

import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import type { components } from "../api/types";
import { WordCell } from "./WordCell";

type WordMatch = components["schemas"]["WordMatch"];

function makeWordMatch(overrides: Partial<WordMatch> = {}): WordMatch {
  return {
    line_index: 0,
    word_index: 0,
    ocr_text: "hello",
    ground_truth_text: "hello",
    match_status: "exact",
    fuzz_score: null,
    normalized_match: false,
    is_validated: false,
    text_style_labels: [],
    word_components: [],
    bbox: { x0: 0, y0: 0, x1: 10, y1: 10 },
    word_id: "w-001",
    ...overrides,
  };
}

describe("WordCell", () => {
  it("renders with data-testid='word-cell-{word_id}'", () => {
    const word = makeWordMatch({ word_id: "w-abc" });
    render(<WordCell word={word} />);
    expect(screen.getByTestId("word-cell-w-abc")).toBeInTheDocument();
  });

  it("GT input has data-testid='gt-text-input-{l}-{w}' (spec canonical)", () => {
    // line_index=0, word_index=0 → gt-text-input-0-0
    const word = makeWordMatch({ word_id: "w-abc", line_index: 0, word_index: 0 });
    render(<WordCell word={word} />);
    expect(screen.getByTestId("gt-text-input-0-0")).toBeInTheDocument();
  });

  it("GT input shows ground_truth_text", () => {
    const word = makeWordMatch({
      word_id: "w-001",
      line_index: 0,
      word_index: 0,
      ground_truth_text: "world",
    });
    render(<WordCell word={word} />);
    const input = screen.getByTestId("gt-text-input-0-0") as HTMLInputElement;
    expect(input.value).toBe("world");
  });

  it("fires onCommitGt with new value on blur when value changed", () => {
    const onCommitGt = vi.fn();
    const word = makeWordMatch({
      word_id: "w-001",
      line_index: 0,
      word_index: 0,
      ground_truth_text: "hello",
    });
    render(<WordCell word={word} onCommitGt={onCommitGt} />);
    const input = screen.getByTestId("gt-text-input-0-0") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "world" } });
    fireEvent.blur(input);
    expect(onCommitGt).toHaveBeenCalledOnce();
    expect(onCommitGt).toHaveBeenCalledWith("w-001", 0, 0, "world");
  });

  it("does NOT fire onCommitGt when value is unchanged on blur", () => {
    const onCommitGt = vi.fn();
    const word = makeWordMatch({
      word_id: "w-001",
      line_index: 0,
      word_index: 0,
      ground_truth_text: "hello",
    });
    render(<WordCell word={word} onCommitGt={onCommitGt} />);
    const input = screen.getByTestId("gt-text-input-0-0");
    fireEvent.blur(input);
    expect(onCommitGt).not.toHaveBeenCalled();
  });

  it("renders text_style_labels as tag chips", () => {
    const word = makeWordMatch({
      word_id: "w-002",
      text_style_labels: ["bold", "italic"],
      word_components: [],
    });
    render(<WordCell word={word} />);
    expect(screen.getByText("bold")).toBeInTheDocument();
    expect(screen.getByText("italic")).toBeInTheDocument();
  });

  it("renders word_components as tag chips", () => {
    const word = makeWordMatch({
      word_id: "w-003",
      text_style_labels: [],
      word_components: ["header", "footnote"],
    });
    render(<WordCell word={word} />);
    expect(screen.getByText("header")).toBeInTheDocument();
    expect(screen.getByText("footnote")).toBeInTheDocument();
  });

  it("shows OCR text", () => {
    const word = makeWordMatch({ word_id: "w-004", ocr_text: "ocr-word" });
    render(<WordCell word={word} />);
    expect(screen.getByText("ocr-word")).toBeInTheDocument();
  });

  it("clicking edit-word-button calls onEditWord with lineIndex and wordIndex", () => {
    const onEditWord = vi.fn();
    const word = makeWordMatch({
      word_id: "w-edit",
      line_index: 2,
      word_index: 5,
    });
    render(<WordCell word={word} onEditWord={onEditWord} />);
    const button = screen.getByTestId("edit-word-button-2-5");
    fireEvent.click(button);
    expect(onEditWord).toHaveBeenCalledOnce();
    expect(onEditWord).toHaveBeenCalledWith(2, 5);
  });

  it("edit-word-button has correct data-testid format 'edit-word-button-{l}-{w}'", () => {
    const word = makeWordMatch({ word_id: "w-001", line_index: 3, word_index: 7 });
    render(<WordCell word={word} />);
    expect(screen.getByTestId("edit-word-button-3-7")).toBeInTheDocument();
  });

  it("edit-word-button does nothing when onEditWord is not provided", () => {
    const word = makeWordMatch({ word_id: "w-001", line_index: 0, word_index: 0 });
    render(<WordCell word={word} />);
    const button = screen.getByTestId("edit-word-button-0-0");
    // Should not throw
    expect(() => fireEvent.click(button)).not.toThrow();
  });

  it("uses word_id (not line/word index) as the testid", () => {
    // Two words with same line_index=0, word_index=0 but different word_ids
    const word1 = makeWordMatch({ word_id: "unique-a", line_index: 0, word_index: 0 });
    const word2 = makeWordMatch({ word_id: "unique-b", line_index: 0, word_index: 0 });
    const { unmount } = render(<WordCell word={word1} />);
    expect(screen.getByTestId("word-cell-unique-a")).toBeInTheDocument();
    unmount();
    render(<WordCell word={word2} />);
    expect(screen.getByTestId("word-cell-unique-b")).toBeInTheDocument();
  });
});

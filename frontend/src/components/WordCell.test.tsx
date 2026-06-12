// WordCell.test.tsx — unit tests for the per-word grid cell with GT input.
// Spec: docs/specs/2026-05-12-word-matches-design.md §WordCell grid
// Issue #203, #241
//
// Acceptance:
//   - Renders with data-testid="word-image-cell-{l}-{w}" (driver-contract §2.8 canonical)
//   - GT input has data-testid="gt-text-input-{l}-{w}" (spec canonical)
//   - Blur-commit: fires onCommitGt with new value when changed
//   - Blur with unchanged value: does NOT fire onCommitGt
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
  it("renders with data-testid='word-image-cell-{l}-{w}' (driver-contract §2.8 canonical)", () => {
    const word = makeWordMatch({ word_id: "w-abc", line_index: 0, word_index: 0 });
    render(<WordCell word={word} />);
    expect(screen.getByTestId("word-image-cell-0-0")).toBeInTheDocument();
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
    const input = screen.getByTestId("gt-text-input-0-0");
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
    const input = screen.getByTestId("gt-text-input-0-0");
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

  // P1.6 (B-22): Enter must commit (blur) like every other GT input in the
  // app; before this the only commit path was an explicit focus change.
  it("Enter commits the GT input (blurs, firing onCommitGt)", () => {
    const onCommitGt = vi.fn();
    const word = makeWordMatch({
      word_id: "w-001",
      line_index: 0,
      word_index: 0,
      ground_truth_text: "hello",
    });
    render(<WordCell word={word} onCommitGt={onCommitGt} />);
    const input = screen.getByTestId("gt-text-input-0-0");
    (input as HTMLInputElement).focus();
    fireEvent.change(input, { target: { value: "world" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onCommitGt).toHaveBeenCalledOnce();
    expect(onCommitGt).toHaveBeenCalledWith("w-001", 0, 0, "world");
  });

  it("Escape reverts the GT input without committing", () => {
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
    fireEvent.keyDown(input, { key: "Escape" });
    expect(input.value).toBe("hello");
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

  it("uses line/word index (not word_id) as the canonical testid (driver-contract §2.8)", () => {
    // The canonical testid is word-image-cell-{l}-{w}; word_id is on the alias attribute.
    const word1 = makeWordMatch({ word_id: "unique-a", line_index: 0, word_index: 0 });
    render(<WordCell word={word1} />);
    expect(screen.getByTestId("word-image-cell-0-0")).toBeInTheDocument();
  });

  // Glyph corner badge tests (spec §5.3, testid §7)
  it("does NOT render glyph badge when both annotations and predictions are null", () => {
    const word = makeWordMatch({ line_index: 0, word_index: 0 });
    render(<WordCell word={word} />);
    expect(screen.queryByTestId("word-glyph-badge-0-0")).toBeNull();
  });

  it("renders amber glyph badge when predictions present but annotations null", () => {
    const word = makeWordMatch({
      line_index: 1,
      word_index: 2,
      glyph_predictions: {
        ligatures: [{ kind: "ct", char_span: null }],
        long_s_positions: [],
        swash: false,
        source: "predicted",
      },
    });
    render(<WordCell word={word} />);
    const badge = screen.getByTestId("word-glyph-badge-1-2");
    expect(badge).toBeTruthy();
    expect(badge.className).toContain("amber");
  });

  it("renders blue glyph badge when annotations set (even empty)", () => {
    const word = makeWordMatch({
      line_index: 0,
      word_index: 3,
      glyph_annotations: {
        ligatures: [],
        long_s_positions: [],
        swash: false,
        source: "human",
      },
    });
    render(<WordCell word={word} />);
    const badge = screen.getByTestId("word-glyph-badge-0-3");
    expect(badge).toBeTruthy();
    expect(badge.className).toContain("blue");
  });

  it("renders green glyph badge when annotations have marks", () => {
    const word = makeWordMatch({
      line_index: 2,
      word_index: 1,
      glyph_annotations: {
        ligatures: [{ kind: "ct", char_span: [1, 3] }],
        long_s_positions: [],
        swash: false,
        source: "human",
      },
    });
    render(<WordCell word={word} />);
    const badge = screen.getByTestId("word-glyph-badge-2-1");
    expect(badge).toBeTruthy();
    expect(badge.className).toContain("green");
  });

  it("renders chip row when annotations exist", () => {
    const word = makeWordMatch({
      line_index: 0,
      word_index: 0,
      glyph_annotations: {
        ligatures: [{ kind: "ct", char_span: [1, 3] }],
        long_s_positions: [],
        swash: false,
        source: "human",
      },
    });
    render(<WordCell word={word} />);
    expect(screen.getByTestId("word-glyph-chip-row-0-0")).toBeTruthy();
  });

  it("does NOT render chip row when no annotations or predictions", () => {
    const word = makeWordMatch({ line_index: 0, word_index: 0 });
    render(<WordCell word={word} />);
    expect(screen.queryByTestId("word-glyph-chip-row-0-0")).toBeNull();
  });

  // STB-1: word-validate-button wires to onValidate
  describe("STB-1: word-validate-button onClick", () => {
    it("calls onValidate(lineIdx, wordIdx, !is_validated) when clicked (unvalidated→validate)", () => {
      const onValidate = vi.fn();
      const word = makeWordMatch({ line_index: 1, word_index: 3, is_validated: false });
      render(<WordCell word={word} onValidate={onValidate} />);
      fireEvent.click(screen.getByTestId("word-validate-button-1-3"));
      expect(onValidate).toHaveBeenCalledOnce();
      expect(onValidate).toHaveBeenCalledWith(1, 3, true);
    });

    it("calls onValidate(lineIdx, wordIdx, false) when word is already validated", () => {
      const onValidate = vi.fn();
      const word = makeWordMatch({ line_index: 0, word_index: 2, is_validated: true });
      render(<WordCell word={word} onValidate={onValidate} />);
      fireEvent.click(screen.getByTestId("word-validate-button-0-2"));
      expect(onValidate).toHaveBeenCalledWith(0, 2, false);
    });

    it("does not throw when onValidate is not provided", () => {
      const word = makeWordMatch({ line_index: 0, word_index: 0 });
      render(<WordCell word={word} />);
      expect(() => fireEvent.click(screen.getByTestId("word-validate-button-0-0"))).not.toThrow();
    });
  });

  // STB-2: word-tag-clear-button wires to onClearTag
  describe("STB-2: word-tag-clear-button onClick", () => {
    it("calls onClearTag(lineIdx, wordIdx, label, 'style') when style chip × is clicked", () => {
      const onClearTag = vi.fn();
      const word = makeWordMatch({
        line_index: 2,
        word_index: 1,
        text_style_labels: ["bold"],
        word_components: [],
      });
      render(<WordCell word={word} onClearTag={onClearTag} />);
      fireEvent.click(screen.getByTestId("word-tag-clear-button-2-1-bold"));
      expect(onClearTag).toHaveBeenCalledOnce();
      expect(onClearTag).toHaveBeenCalledWith(2, 1, "bold", "style");
    });

    it("calls onClearTag(lineIdx, wordIdx, comp, 'component') when component chip × is clicked", () => {
      const onClearTag = vi.fn();
      const word = makeWordMatch({
        line_index: 0,
        word_index: 0,
        text_style_labels: [],
        word_components: ["header"],
      });
      render(<WordCell word={word} onClearTag={onClearTag} />);
      fireEvent.click(screen.getByTestId("word-tag-clear-button-0-0-header"));
      expect(onClearTag).toHaveBeenCalledOnce();
      expect(onClearTag).toHaveBeenCalledWith(0, 0, "header", "component");
    });

    it("does not throw when onClearTag is not provided and chip × is clicked", () => {
      const word = makeWordMatch({
        line_index: 0,
        word_index: 0,
        text_style_labels: ["italic"],
        word_components: [],
      });
      render(<WordCell word={word} />);
      expect(() =>
        fireEvent.click(screen.getByTestId("word-tag-clear-button-0-0-italic")),
      ).not.toThrow();
    });
  });
});

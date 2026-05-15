// WordHeader.test.tsx — P2.a tests for the word identity strip.

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { WordHeader } from "./WordHeader";
import type { components } from "../../api/types";

type WordMatch = components["schemas"]["WordMatch"];

function makeWord(overrides: Partial<WordMatch> = {}): WordMatch {
  return {
    line_index: 6,
    word_index: 0,
    ocr_text: "hello",
    ground_truth_text: "hello",
    match_status: "exact",
    normalized_match: false,
    is_validated: false,
    bbox: { x: 10, y: 20, width: 30, height: 15 },
    ...overrides,
  };
}

describe("WordHeader (P2.a)", () => {
  it("renders 1-based Line/Word identity label", () => {
    render(
      <WordHeader
        word={makeWord({ line_index: 6, word_index: 0 })}
        hasPrev={false}
        hasNext={false}
        onPrev={vi.fn()}
        onNext={vi.fn()}
      />,
    );
    expect(screen.getByTestId("word-header-id")).toHaveTextContent("Line 7 · Word 1");
  });

  it("renders StatusPip for exact match", () => {
    render(
      <WordHeader
        word={makeWord({ match_status: "exact" })}
        hasPrev={false}
        hasNext={true}
        onPrev={vi.fn()}
        onNext={vi.fn()}
      />,
    );
    expect(screen.getByTestId("word-header")).toBeInTheDocument();
  });

  it("disables prev button when hasPrev=false", () => {
    render(
      <WordHeader
        word={makeWord()}
        hasPrev={false}
        hasNext={true}
        onPrev={vi.fn()}
        onNext={vi.fn()}
      />,
    );
    expect(screen.getByTestId("word-header-prev")).toBeDisabled();
    expect(screen.getByTestId("word-header-next")).not.toBeDisabled();
  });

  it("disables next button when hasNext=false", () => {
    render(
      <WordHeader
        word={makeWord()}
        hasPrev={true}
        hasNext={false}
        onPrev={vi.fn()}
        onNext={vi.fn()}
      />,
    );
    expect(screen.getByTestId("word-header-next")).toBeDisabled();
    expect(screen.getByTestId("word-header-prev")).not.toBeDisabled();
  });

  it("calls onPrev / onNext when buttons are clicked", async () => {
    const onPrev = vi.fn();
    const onNext = vi.fn();
    render(
      <WordHeader
        word={makeWord()}
        hasPrev={true}
        hasNext={true}
        onPrev={onPrev}
        onNext={onNext}
      />,
    );
    await userEvent.click(screen.getByTestId("word-header-prev"));
    await userEvent.click(screen.getByTestId("word-header-next"));
    expect(onPrev).toHaveBeenCalledTimes(1);
    expect(onNext).toHaveBeenCalledTimes(1);
  });
});

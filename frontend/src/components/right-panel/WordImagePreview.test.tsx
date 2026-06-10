// WordImagePreview.test.tsx — P2.b tests for the word image preview box.

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { WordImagePreview } from "./WordImagePreview";
import type { components } from "../../api/types";

type WordMatch = components["schemas"]["WordMatch"];

function makeWord(overrides: Partial<WordMatch> = {}): WordMatch {
  return {
    line_index: 0,
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

describe("WordImagePreview (P2.b)", () => {
  it("renders the preview container", () => {
    render(<WordImagePreview word={makeWord()} />);
    expect(screen.getByTestId("word-image-preview")).toBeInTheDocument();
  });

  it("renders the preview box with 76px height", () => {
    render(<WordImagePreview word={makeWord()} />);
    const box = screen.getByTestId("word-image-preview-box");
    expect(box).toBeInTheDocument();
    expect(box.className).toContain("h-[76px]");
  });

  it("shows OCR text in preview box when no image URL", () => {
    render(<WordImagePreview word={makeWord({ ocr_text: "world" })} />);
    expect(screen.getByTestId("word-image-preview-box")).toHaveTextContent("world");
  });

  it("shows img element when imageUrl provided", () => {
    render(<WordImagePreview word={makeWord()} imageUrl="/img/word.png" />);
    const img = screen.getByRole("img");
    expect(img).toHaveAttribute("src", "/img/word.png");
  });

  it("shows a source-image crop when imageUrl, bbox, and source dimensions are provided", () => {
    render(
      <WordImagePreview
        word={makeWord({ bbox: { x: 10, y: 20, width: 30, height: 15 }, ocr_text: "world" })}
        imageUrl="/api/projects/p1/image/0"
        cropBBox={{ x: 10, y: 20, width: 30, height: 15 }}
        sourceWidth={1600}
        sourceHeight={1200}
      />,
    );

    expect(screen.getByTestId("word-image-preview-box")).not.toHaveTextContent("world");
    const crop = screen.getByTestId("word-image-crop");
    expect(crop).toHaveAttribute("viewBox", "10 20 30 15");
    expect(crop.querySelector("image")).toHaveAttribute("href", "/api/projects/p1/image/0");
  });

  it("renders OCR confidence bar", () => {
    render(<WordImagePreview word={makeWord({ match_status: "exact" })} />);
    const ocrBar = screen.getByTestId("word-image-preview-ocr-bar");
    expect(ocrBar).toBeInTheDocument();
    // exact match → 100%
    expect(ocrBar).toHaveStyle({ width: "100%" });
  });

  it("renders GT confidence bar — 100% when is_validated", () => {
    render(<WordImagePreview word={makeWord({ is_validated: true })} />);
    const gtBar = screen.getByTestId("word-image-preview-gt-bar");
    expect(gtBar).toHaveStyle({ width: "100%" });
  });

  it("renders GT confidence bar — 0% when mismatch and not validated", () => {
    render(
      <WordImagePreview
        word={makeWord({ match_status: "mismatch", is_validated: false, fuzz_score: 20 })}
      />,
    );
    const gtBar = screen.getByTestId("word-image-preview-gt-bar");
    expect(gtBar).toHaveStyle({ width: "0%" });
  });

  it("shows ∅ placeholder for empty OCR text", () => {
    render(<WordImagePreview word={makeWord({ ocr_text: "" })} />);
    expect(screen.getByTestId("word-image-preview-box")).toHaveTextContent("∅");
  });
});

// TextTabs.test.tsx — unit tests for the TextTabs shell component.
// Spec: docs/specs/2026-05-12-word-matches-design.md §Layout
// Issue #200
//
// Acceptance criteria:
//   - data-testids: text-tab-matches, text-tab-ground-truth, text-tab-ocr, match-filter-*
//   - Switching to GT tab shows page_text_gt in a readOnly textarea

import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { TextTabs } from "./TextTabs";

describe("TextTabs", () => {
  it("renders all three tab triggers with required data-testids", () => {
    render(<TextTabs />);
    expect(screen.getByTestId("text-tab-matches")).toBeInTheDocument();
    expect(screen.getByTestId("text-tab-ground-truth")).toBeInTheDocument();
    expect(screen.getByTestId("text-tab-ocr")).toBeInTheDocument();
  });

  it("renders the filter segmented control with required data-testids", () => {
    render(<TextTabs />);
    expect(screen.getByTestId("match-filter-unvalidated")).toBeInTheDocument();
    expect(screen.getByTestId("match-filter-mismatched")).toBeInTheDocument();
    expect(screen.getByTestId("match-filter-all")).toBeInTheDocument();
  });

  it("starts on the matches tab by default", () => {
    render(<TextTabs />);
    const matchesTab = screen.getByTestId("text-tab-matches");
    expect(matchesTab).toHaveAttribute("aria-selected", "true");
    const gtTab = screen.getByTestId("text-tab-ground-truth");
    expect(gtTab).toHaveAttribute("aria-selected", "false");
  });

  it("shows children in the matches panel", () => {
    render(
      <TextTabs>
        <div data-testid="word-match-view">matches content</div>
      </TextTabs>,
    );
    expect(screen.getByTestId("word-match-view")).toBeInTheDocument();
  });

  it("switches to the Ground Truth tab and shows page_text_gt in readOnly textarea", () => {
    const gtText = "Once upon a time\nIn a land far away";
    render(<TextTabs pageTextGt={gtText} />);

    const gtTab = screen.getByTestId("text-tab-ground-truth");
    fireEvent.click(gtTab);

    const textarea = screen.getByTestId("text-panel-ground-truth");
    expect(textarea).toBeInTheDocument();
    expect(textarea).toHaveAttribute("readonly");
    expect((textarea as HTMLTextAreaElement).value).toBe(gtText);
  });

  it("switches to the OCR tab and shows page_text_ocr in readOnly textarea", () => {
    const ocrText = "OCR output text\nSecond line";
    render(<TextTabs pageTextOcr={ocrText} />);

    const ocrTab = screen.getByTestId("text-tab-ocr");
    fireEvent.click(ocrTab);

    const textarea = screen.getByTestId("text-panel-ocr");
    expect(textarea).toBeInTheDocument();
    expect(textarea).toHaveAttribute("readonly");
    expect((textarea as HTMLTextAreaElement).value).toBe(ocrText);
  });

  it("calls onLineFilterChange when a filter button is clicked", () => {
    const onChange = vi.fn();
    render(<TextTabs lineFilter="unvalidated" onLineFilterChange={onChange} />);

    fireEvent.click(screen.getByTestId("match-filter-mismatched"));
    expect(onChange).toHaveBeenCalledWith("mismatched");
  });

  it("marks the active filter button as pressed", () => {
    render(<TextTabs lineFilter="mismatched" />);
    const btn = screen.getByTestId("match-filter-mismatched");
    expect(btn).toHaveAttribute("aria-pressed", "true");

    const unvalidated = screen.getByTestId("match-filter-unvalidated");
    expect(unvalidated).toHaveAttribute("aria-pressed", "false");
  });

  it("renders Ground Truth tab with empty string when pageTextGt is null", () => {
    render(<TextTabs pageTextGt={null} />);
    fireEvent.click(screen.getByTestId("text-tab-ground-truth"));
    const textarea = screen.getByTestId("text-panel-ground-truth");
    expect((textarea as HTMLTextAreaElement).value).toBe("");
  });

  it("renders OCR tab with empty string when pageTextOcr is null", () => {
    render(<TextTabs pageTextOcr={null} />);
    fireEvent.click(screen.getByTestId("text-tab-ocr"));
    const textarea = screen.getByTestId("text-panel-ocr");
    expect((textarea as HTMLTextAreaElement).value).toBe("");
  });

  it("has correct aria role attributes on tabs", () => {
    render(<TextTabs />);
    const tabs = screen.getAllByRole("tab");
    expect(tabs).toHaveLength(3);
    const panels = screen.getAllByRole("tabpanel", { hidden: true });
    expect(panels).toHaveLength(3);
  });
});

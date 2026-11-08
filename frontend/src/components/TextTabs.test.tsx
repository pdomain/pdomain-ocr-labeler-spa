// TextTabs.test.tsx — unit tests for the TextTabs shell component.
// Spec: docs/specs/2026-05-12-word-matches-design.md §Layout
// Issue #200
//
// Acceptance criteria:
//   - data-testids: text-tab-matches, text-tab-ground-truth, text-tab-ocr, match-filter-*
//   - Switching to GT tab shows page_text_gt in a readOnly textarea

import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TextTabs } from "./TextTabs";

const sourcePreview = {
  project_id: "project-1",
  page_index: 0,
  page_key: "001.png",
  available: true,
  f2: { raw_text: "<i>F2</i>", visible_text: "F2" },
  p3: { raw_text: "<i>P3</i>", visible_text: "P3" },
  consolidated: {
    text: "P3",
    runs: [{ text: "P3", styles: ["italic"] }],
    layout_hints: [
      {
        kind: "verse",
        source_ref: "f2-line-1",
        lines: [{ text: "P3", stanza_index: 0, indent_hint: "  " }],
      },
    ],
    unresolved: [
      {
        source_kind: "style_span",
        source_ref: "italic",
        source_text: "F2",
        reason: "changed source text",
      },
    ],
  },
  warnings: [],
} as const;

describe("TextTabs", () => {
  it("renders the working and source tab triggers with stable data-testids", () => {
    render(<TextTabs />);
    expect(screen.getByTestId("text-tab-matches")).toBeInTheDocument();
    expect(screen.getByTestId("text-tab-ground-truth")).toBeInTheDocument();
    expect(screen.getByTestId("text-tab-p3")).toBeInTheDocument();
    expect(screen.getByTestId("text-tab-f2")).toBeInTheDocument();
    expect(screen.getByTestId("text-tab-consolidated")).toBeInTheDocument();
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

  it("renders the matches-panel child directly under a flex layout context (P0-CI-SOFT regression)", () => {
    // WordMatchView's own root carries className="flex-1 overflow-auto" and
    // style={{contain: "strict"}} so @tanstack/react-virtual gets a definite,
    // content-independent height to measure against. `flex-1` only produces
    // that height when the *immediate* parent is itself a flex container
    // (jsdom does not run a real layout engine, so this can't be asserted by
    // measuring pixels here — but the structural precondition can).
    //
    // Previously TextTabs wrapped `children` in an extra `<div className=
    // "flex-1 overflow-auto">`, a plain block element with no `display:
    // flex`. That broke the chain: `flex-1` on word-match-view did nothing,
    // `contain: strict` then blocked the content-derived fallback height,
    // and the container measured zero height in the browser — the
    // virtualizer mounted no rows and the Matches tab showed nothing for a
    // page with real word content. Fixed by rendering `children` as a
    // direct child of the already-flex `panel-matches` tabpanel (matching
    // the Ground Truth / OCR panels' own textarea, which are direct flex
    // children of their panels).
    render(
      <TextTabs>
        <div data-testid="word-match-view" className="flex-1 overflow-auto" />
      </TextTabs>,
    );
    const view = screen.getByTestId("word-match-view");
    const parent = view.parentElement;
    expect(parent).not.toBeNull();
    const parentClasses = (parent?.className ?? "").split(/\s+/);
    expect(parentClasses).toContain("flex");
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
    expect(screen.getByText("Edit individual words in Matches.")).toBeInTheDocument();
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

  it("shows raw F2 and P3 markers, and a read-only consolidated preview", () => {
    render(<TextTabs sourcePreview={sourcePreview} />);

    fireEvent.click(screen.getByTestId("text-tab-f2"));
    expect(screen.getByTestId("text-panel-f2")).toHaveTextContent("<i>F2</i>");

    fireEvent.click(screen.getByTestId("text-tab-p3"));
    expect(screen.getByTestId("text-panel-p3")).toHaveTextContent("<i>P3</i>");

    fireEvent.click(screen.getByTestId("text-tab-consolidated"));
    expect(screen.getByTestId("text-panel-consolidated")).toHaveTextContent("P3");
    expect(screen.getByTestId("consolidated-unresolved")).toHaveTextContent(
      "F2: changed source text",
    );
    expect(screen.getByTestId("consolidated-layout-hint")).not.toHaveAttribute("open");
    expect(screen.getByText("Source layout evidence: verse")).toBeInTheDocument();
  });

  it("does not reuse prior source text when the current page has no prepared source", () => {
    const { rerender } = render(<TextTabs sourcePreview={sourcePreview} />);
    fireEvent.click(screen.getByTestId("text-tab-p3"));
    expect(screen.getByTestId("text-panel-p3")).toHaveTextContent("P3");

    rerender(
      <TextTabs
        sourcePreview={{
          project_id: "project-1",
          page_index: 1,
          page_key: null,
          available: false,
          f2: null,
          p3: null,
          consolidated: null,
          warnings: ["This page has no prepared PGDP source."],
        }}
      />,
    );

    expect(screen.getByTestId("source-preview-unavailable-p3")).toHaveTextContent(
      "This page has no prepared PGDP source.",
    );
    expect(screen.queryByTestId("text-panel-p3")).not.toBeInTheDocument();
  });

  it("hides cached source text while the authoritative page source refreshes", () => {
    const { rerender } = render(<TextTabs sourcePreview={sourcePreview} />);
    fireEvent.click(screen.getByTestId("text-tab-p3"));
    expect(screen.getByTestId("text-panel-p3")).toHaveTextContent("P3");

    rerender(<TextTabs sourcePreview={sourcePreview} sourcePreviewPending />);

    expect(screen.getByTestId("source-preview-loading-p3")).toBeInTheDocument();
    expect(screen.queryByTestId("text-panel-p3")).not.toBeInTheDocument();
  });

  it("does not show stale source text after a source refresh error", () => {
    const { rerender } = render(<TextTabs sourcePreview={sourcePreview} />);
    fireEvent.click(screen.getByTestId("text-tab-p3"));

    rerender(<TextTabs sourcePreview={sourcePreview} sourcePreviewError />);

    expect(screen.getByTestId("source-preview-error-p3")).toBeInTheDocument();
    expect(screen.queryByTestId("text-panel-p3")).not.toBeInTheDocument();
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
    expect(tabs).toHaveLength(6);
    const panels = screen.getAllByRole("tabpanel", { hidden: true });
    expect(panels).toHaveLength(6);
    for (const tab of tabs) {
      const panelId = tab.getAttribute("aria-controls");
      expect(panelId).not.toBeNull();
      const panel = document.getElementById(panelId ?? "");
      expect(panel).toHaveAttribute("role", "tabpanel");
      expect(panel).toHaveAttribute("aria-labelledby", tab.id);
    }
  });

  it("assigns associations per TextTabs instance", () => {
    render(
      <>
        <TextTabs />
        <TextTabs />
      </>,
    );

    const tabIds = screen.getAllByRole("tab").map((tab) => tab.id);
    const panelIds = screen.getAllByRole("tabpanel", { hidden: true }).map((panel) => panel.id);
    expect(new Set(tabIds)).toHaveLength(tabIds.length);
    expect(new Set(panelIds)).toHaveLength(panelIds.length);
  });

  it("uses roving focus and automatic activation for tab keyboard commands", async () => {
    const user = userEvent.setup();
    render(<TextTabs sourcePreview={sourcePreview} />);
    const matches = screen.getByRole("tab", { name: "Matches" });
    const workingGt = screen.getByRole("tab", { name: "Working GT" });
    const p3 = screen.getByRole("tab", { name: "P3" });
    const ocr = screen.getByRole("tab", { name: "OCR" });

    matches.focus();
    await user.keyboard("{ArrowRight}");
    expect(document.activeElement).toBe(workingGt);
    expect(workingGt).toHaveAttribute("aria-selected", "true");
    expect(workingGt).toHaveAttribute("tabindex", "0");
    expect(matches).toHaveAttribute("tabindex", "-1");

    await user.keyboard("{ArrowRight}");
    expect(document.activeElement).toBe(p3);
    expect(p3).toHaveAttribute("aria-selected", "true");
    expect(screen.getByTestId("text-panel-p3")).toHaveTextContent("<i>P3</i>");

    await user.keyboard("{End}");
    expect(document.activeElement).toBe(ocr);
    expect(ocr).toHaveAttribute("aria-selected", "true");

    await user.keyboard("{Home}");
    expect(document.activeElement).toBe(matches);
    expect(matches).toHaveAttribute("aria-selected", "true");

    await user.keyboard("{ArrowLeft}");
    expect(document.activeElement).toBe(ocr);
    expect(ocr).toHaveAttribute("aria-selected", "true");
  });
});

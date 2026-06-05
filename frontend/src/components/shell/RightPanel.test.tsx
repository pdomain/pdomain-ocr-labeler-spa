// RightPanel.test.tsx — Tests for the right-panel router (Slice 14).
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 14.

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RightPanel } from "./RightPanel";
import {
  clearSelection,
  selectBlock,
  selectPara,
  selectLine,
  selectWord,
} from "../../stores/selection-store";
import type { components } from "../../api/types";

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

function renderWithQuery(ui: React.ReactElement) {
  const qc = makeQueryClient();
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

type PagePayload = components["schemas"]["PagePayload"];

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
        ocr_line_text: "hello",
        ground_truth_line_text: "hello",
        word_matches: [
          {
            line_index: 0,
            word_index: 0,
            ocr_text: "hello",
            ground_truth_text: "hello",
            match_status: "exact",
            normalized_match: false,
            is_validated: false,
            bbox: { x: 0, y: 0, width: 0, height: 0 },
          },
        ],
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

describe("RightPanel (Slice 14)", () => {
  beforeEach(() => {
    clearSelection();
  });

  it("renders with breadcrumb and collapse button", () => {
    render(<RightPanel page={makePage()} />);
    expect(screen.getByTestId("right-panel")).toBeInTheDocument();
    expect(screen.getByTestId("right-panel-header")).toBeInTheDocument();
    expect(screen.getByTestId("breadcrumb")).toBeInTheDocument();
    expect(screen.getByTestId("right-panel-collapse")).toBeInTheDocument();
  });

  it("body shows 'no selection' placeholder when level=none", () => {
    render(<RightPanel page={makePage()} />);
    const body = screen.getByTestId("right-panel-body");
    expect(body).toHaveAttribute("data-level", "none");
    expect(body).toHaveTextContent(/select/i);
  });

  it("body data-level updates when selection changes (block)", () => {
    selectBlock("b1");
    render(<RightPanel page={makePage()} />);
    expect(screen.getByTestId("right-panel-body")).toHaveAttribute("data-level", "block");
  });

  it("body data-level=para has correct data-level attribute", () => {
    selectPara(0);
    render(<RightPanel page={makePage()} />);
    const body = screen.getByTestId("right-panel-body");
    expect(body).toHaveAttribute("data-level", "para");
  });

  it("body data-level=line has correct data-level attribute", () => {
    selectLine(0);
    render(<RightPanel page={makePage()} />);
    const body = screen.getByTestId("right-panel-body");
    expect(body).toHaveAttribute("data-level", "line");
  });

  it("body data-level=word renders the word slot when provided", () => {
    selectWord(0, 0);
    render(
      <RightPanel
        page={makePage()}
        wordSlot={<div data-testid="word-detail-stub">stub-content</div>}
      />,
    );
    const body = screen.getByTestId("right-panel-body");
    expect(body).toHaveAttribute("data-level", "word");
    expect(screen.getByTestId("word-detail-stub")).toBeInTheDocument();
  });

  it("body data-level=word has correct data-level attribute", () => {
    selectWord(0, 0);
    render(<RightPanel page={makePage()} />);
    const body = screen.getByTestId("right-panel-body");
    expect(body).toHaveAttribute("data-level", "word");
  });

  it("collapse button calls onCollapse when clicked", async () => {
    const onCollapse = vi.fn();
    const user = userEvent.setup();
    render(<RightPanel page={makePage()} onCollapse={onCollapse} />);
    await user.click(screen.getByTestId("right-panel-collapse"));
    expect(onCollapse).toHaveBeenCalledTimes(1);
  });
});

// ─── STB-5: No placeholder for implemented levels ────────────────────────────

describe("STB-5: RightPanel never shows placeholder for implemented levels", () => {
  beforeEach(() => {
    clearSelection();
  });

  it("level=none still shows the placeholder", () => {
    renderWithQuery(<RightPanel page={makePage()} projectId="p1" pageIndex={0} />);
    expect(screen.getByTestId("right-panel-placeholder")).toBeInTheDocument();
  });

  it("level=line does NOT show the placeholder (renders LineDetail)", () => {
    selectLine(0);
    renderWithQuery(<RightPanel page={makePage()} projectId="p1" pageIndex={0} />);
    expect(screen.queryByTestId("right-panel-placeholder")).toBeNull();
    expect(screen.getByTestId("line-detail")).toBeInTheDocument();
  });

  it("level=block does NOT show the placeholder (renders BlockDetail)", () => {
    selectBlock("b1");
    renderWithQuery(<RightPanel page={makePage()} projectId="p1" pageIndex={0} />);
    expect(screen.queryByTestId("right-panel-placeholder")).toBeNull();
    expect(screen.getByTestId("block-detail")).toBeInTheDocument();
  });

  it("level=para does NOT show the placeholder (renders ParagraphDetail)", () => {
    selectPara(0);
    renderWithQuery(<RightPanel page={makePage()} projectId="p1" pageIndex={0} />);
    expect(screen.queryByTestId("right-panel-placeholder")).toBeNull();
    expect(screen.getByTestId("paragraph-detail")).toBeInTheDocument();
  });

  it("level=word with wordSlot does NOT show the placeholder", () => {
    selectWord(0, 0);
    renderWithQuery(
      <RightPanel
        page={makePage()}
        projectId="p1"
        pageIndex={0}
        wordSlot={<div data-testid="word-slot-stub">word content</div>}
      />,
    );
    expect(screen.queryByTestId("right-panel-placeholder")).toBeNull();
    expect(screen.getByTestId("word-slot-stub")).toBeInTheDocument();
  });
});

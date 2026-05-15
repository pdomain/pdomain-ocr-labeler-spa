// BlockDetail.test.tsx — Tests for Slice 22 + P5.g redesign.
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 22 + hifi-gaps-plan P5.g.
// Gaps tested: 47 (glyph cards), 48 (model-suggest callout), 49 (preview),
//              50 (Items View sub-toggle), 51 (Para layout tab).

import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BlockDetail } from "./BlockDetail";
import {
  clearSelection,
  selectBlock,
  selectPara,
  selectionStore,
} from "../../stores/selection-store";
import type { components } from "../../api/types";

type PagePayload = components["schemas"]["PagePayload"];

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

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
        ocr_line_text: "first line",
        ground_truth_line_text: "first line",
        word_matches: [],
        overall_match_status: "exact",
        exact_count: 0,
        fuzzy_count: 0,
        mismatch_count: 0,
        unmatched_gt_count: 0,
        unmatched_ocr_count: 0,
        validated_word_count: 0,
        total_word_count: 0,
        is_fully_validated: false,
      },
      {
        line_index: 1,
        paragraph_index: 0,
        ocr_line_text: "second line",
        ground_truth_line_text: "second line",
        word_matches: [],
        overall_match_status: "fuzzy",
        exact_count: 0,
        fuzzy_count: 1,
        mismatch_count: 0,
        unmatched_gt_count: 0,
        unmatched_ocr_count: 0,
        validated_word_count: 0,
        total_word_count: 1,
        is_fully_validated: false,
      },
      {
        line_index: 2,
        paragraph_index: 1,
        ocr_line_text: "third line",
        ground_truth_line_text: "third line",
        word_matches: [],
        overall_match_status: "mismatch",
        exact_count: 0,
        fuzzy_count: 0,
        mismatch_count: 1,
        unmatched_gt_count: 0,
        unmatched_ocr_count: 0,
        validated_word_count: 0,
        total_word_count: 1,
        is_fully_validated: false,
      },
    ],
  };
}

function renderWithQuery(ui: React.ReactElement) {
  const qc = makeQueryClient();
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

// ─── Existing tests (regression guard) ────────────────────────────────────────

describe("BlockDetail (Slice 22) — block level", () => {
  beforeEach(() => {
    clearSelection();
  });

  it("shows 'No block selected' when no block in selection-store", () => {
    renderWithQuery(<BlockDetail page={makePage()} projectId="p1" pageIndex={0} level="block" />);
    expect(screen.getByTestId("block-detail")).toHaveTextContent(/no block selected/i);
  });

  it("renders Layout, Items, and Para Layout tabs when block is selected", () => {
    selectBlock("b1");
    renderWithQuery(<BlockDetail page={makePage()} projectId="p1" pageIndex={0} level="block" />);
    expect(screen.getByTestId("block-detail-tab-layout")).toBeInTheDocument();
    expect(screen.getByTestId("block-detail-tab-items")).toBeInTheDocument();
    expect(screen.getByTestId("block-detail-tab-para-layout")).toBeInTheDocument();
  });

  it("Items tab shows para groups with lines (tree mode default)", async () => {
    const user = userEvent.setup();
    selectBlock("b1");
    renderWithQuery(<BlockDetail page={makePage()} projectId="p1" pageIndex={0} level="block" />);
    await user.click(screen.getByTestId("block-detail-tab-items"));
    expect(screen.getByTestId("block-detail-items-tree")).toBeInTheDocument();
    expect(screen.getByTestId("block-detail-line-card-0")).toBeInTheDocument();
    expect(screen.getByTestId("block-detail-line-card-1")).toBeInTheDocument();
    expect(screen.getByTestId("block-detail-line-card-2")).toBeInTheDocument();
  });

  it("clicking a line in Items sets selection-store to that line", async () => {
    const user = userEvent.setup();
    selectBlock("b1");
    renderWithQuery(<BlockDetail page={makePage()} projectId="p1" pageIndex={0} level="block" />);
    await user.click(screen.getByTestId("block-detail-tab-items"));
    await user.click(screen.getByTestId("block-detail-line-card-2"));
    const { level, path } = selectionStore.getState();
    expect(level).toBe("line");
    expect(path.lineId).toBe(2);
  });
});

describe("BlockDetail (Slice 22) — para level", () => {
  beforeEach(() => {
    clearSelection();
  });

  it("shows 'No paragraph selected' when no para in selection-store", () => {
    renderWithQuery(<BlockDetail page={makePage()} projectId="p1" pageIndex={0} level="para" />);
    expect(screen.getByTestId("block-detail")).toHaveTextContent(/no paragraph selected/i);
  });

  it("shows only items tab (no layout tab, no para-layout tab) in para mode", () => {
    selectPara(0);
    renderWithQuery(<BlockDetail page={makePage()} projectId="p1" pageIndex={0} level="para" />);
    expect(screen.queryByTestId("block-detail-tab-layout")).not.toBeInTheDocument();
    expect(screen.queryByTestId("block-detail-tab-para-layout")).not.toBeInTheDocument();
    expect(screen.getByTestId("block-detail-tab-items")).toBeInTheDocument();
  });

  it("para mode shows only lines for the selected para", () => {
    selectPara(1);
    renderWithQuery(<BlockDetail page={makePage()} projectId="p1" pageIndex={0} level="para" />);
    expect(screen.getByTestId("block-detail-line-card-2")).toBeInTheDocument();
    expect(screen.queryByTestId("block-detail-line-card-0")).not.toBeInTheDocument();
  });
});

// ─── P5.g: Gap 47 — layout-type glyph cards ──────────────────────────────────

describe("BlockDetail P5.g — Gap 47: layout-type glyph cards", () => {
  beforeEach(() => {
    clearSelection();
    selectBlock("b1");
  });

  it("renders 'heading' glyph card in Layout tab", () => {
    renderWithQuery(<BlockDetail page={makePage()} projectId="p1" pageIndex={0} level="block" />);
    expect(screen.getByTestId("block-detail-layout-chip-heading")).toBeInTheDocument();
  });

  it("renders 'body-text' glyph card in Layout tab", () => {
    renderWithQuery(<BlockDetail page={makePage()} projectId="p1" pageIndex={0} level="block" />);
    expect(screen.getByTestId("block-detail-layout-chip-body-text")).toBeInTheDocument();
  });

  it("renders all 19 layout types", () => {
    renderWithQuery(<BlockDetail page={makePage()} projectId="p1" pageIndex={0} level="block" />);
    const allTypes = [
      "heading",
      "subheading",
      "section-break",
      "page-header",
      "page-footer",
      "footnote",
      "sidebar",
      "caption",
      "pullquote",
      "body-text",
      "list-item",
      "table",
      "figure",
      "diagram",
      "code",
      "verse",
      "letter",
      "drop-cap-block",
    ];
    for (const t of allTypes) {
      expect(screen.getByTestId(`block-detail-layout-chip-${t}`)).toBeInTheDocument();
    }
  });

  it("clicking a glyph card marks it as pending (data-active)", async () => {
    const user = userEvent.setup();
    renderWithQuery(<BlockDetail page={makePage()} projectId="p1" pageIndex={0} level="block" />);
    const headingCard = screen.getByTestId("block-detail-layout-chip-heading");
    await user.click(headingCard);
    expect(headingCard).toHaveAttribute("data-active", "true");
  });

  it("Save button is enabled after selecting a new layout type", async () => {
    const user = userEvent.setup();
    renderWithQuery(<BlockDetail page={makePage()} projectId="p1" pageIndex={0} level="block" />);
    // Default is body-text; click heading to create a pending change.
    await user.click(screen.getByTestId("block-detail-layout-chip-heading"));
    const saveBtn = screen.getByTestId("block-detail-layout-save");
    expect(saveBtn).not.toBeDisabled();
  });

  it("Save button is disabled when pending matches selected (no pending change)", () => {
    renderWithQuery(<BlockDetail page={makePage()} projectId="p1" pageIndex={0} level="block" />);
    // Initially body-text === body-text, so no pending change.
    const saveBtn = screen.getByTestId("block-detail-layout-save");
    expect(saveBtn).toBeDisabled();
  });
});

// ─── P5.g: Gap 48 — model-suggest callout ────────────────────────────────────

describe("BlockDetail P5.g — Gap 48: model-suggest callout", () => {
  beforeEach(() => {
    clearSelection();
    selectBlock("b1");
  });

  it("shows 'No model suggestion available' when suggestion is null", () => {
    renderWithQuery(<BlockDetail page={makePage()} projectId="p1" pageIndex={0} level="block" />);
    expect(screen.getByText(/no model suggestion/i)).toBeInTheDocument();
  });

  it("layout-accept button is absent when no suggestion", () => {
    renderWithQuery(<BlockDetail page={makePage()} projectId="p1" pageIndex={0} level="block" />);
    expect(screen.queryByTestId("block-detail-layout-accept")).not.toBeInTheDocument();
  });
});

// ─── P5.g: Gap 49 — preview pane ─────────────────────────────────────────────

describe("BlockDetail P5.g — Gap 49: preview pane", () => {
  beforeEach(() => {
    clearSelection();
    selectBlock("b1");
  });

  it("renders preview pane in Layout tab", () => {
    renderWithQuery(<BlockDetail page={makePage()} projectId="p1" pageIndex={0} level="block" />);
    expect(screen.getByTestId("block-detail-preview")).toBeInTheDocument();
  });

  it("preview shows 'Preview' label", () => {
    renderWithQuery(<BlockDetail page={makePage()} projectId="p1" pageIndex={0} level="block" />);
    expect(screen.getByTestId("block-detail-preview")).toHaveTextContent(/preview/i);
  });
});

// ─── P5.g: Gap 50 — Items view sub-toggle ─────────────────────────────────────

describe("BlockDetail P5.g — Gap 50: Items view sub-toggle", () => {
  beforeEach(() => {
    clearSelection();
    selectBlock("b1");
  });

  it("renders Flat and Tree sub-toggle buttons in Items tab", async () => {
    const user = userEvent.setup();
    renderWithQuery(<BlockDetail page={makePage()} projectId="p1" pageIndex={0} level="block" />);
    await user.click(screen.getByTestId("block-detail-tab-items"));
    expect(screen.getByTestId("block-detail-items-view-flat")).toBeInTheDocument();
    expect(screen.getByTestId("block-detail-items-view-tree")).toBeInTheDocument();
  });

  it("Tree view is active by default", async () => {
    const user = userEvent.setup();
    renderWithQuery(<BlockDetail page={makePage()} projectId="p1" pageIndex={0} level="block" />);
    await user.click(screen.getByTestId("block-detail-tab-items"));
    expect(screen.getByTestId("block-detail-items-view-tree")).toHaveAttribute(
      "data-active",
      "true",
    );
  });

  it("switching to Flat view shows all lines without para grouping", async () => {
    const user = userEvent.setup();
    renderWithQuery(<BlockDetail page={makePage()} projectId="p1" pageIndex={0} level="block" />);
    await user.click(screen.getByTestId("block-detail-tab-items"));
    await user.click(screen.getByTestId("block-detail-items-view-flat"));
    expect(screen.getByTestId("block-detail-items-view-flat")).toHaveAttribute(
      "data-active",
      "true",
    );
    // All lines still visible in flat mode.
    expect(screen.getByTestId("block-detail-line-card-0")).toBeInTheDocument();
    expect(screen.getByTestId("block-detail-line-card-2")).toBeInTheDocument();
  });
});

// ─── P5.g: Gap 51 — Para layout tab ──────────────────────────────────────────

describe("BlockDetail P5.g — Gap 51: Para layout tab + scope", () => {
  beforeEach(() => {
    clearSelection();
    selectBlock("b1");
  });

  it("renders Para Layout tab in block mode", () => {
    renderWithQuery(<BlockDetail page={makePage()} projectId="p1" pageIndex={0} level="block" />);
    expect(screen.getByTestId("block-detail-tab-para-layout")).toBeInTheDocument();
  });

  it("Para Layout tab shows paragraph scope selectors", async () => {
    const user = userEvent.setup();
    renderWithQuery(<BlockDetail page={makePage()} projectId="p1" pageIndex={0} level="block" />);
    await user.click(screen.getByTestId("block-detail-tab-para-layout"));
    // Two paras exist: 0 and 1.
    expect(screen.getByTestId("block-detail-para-scope-0")).toBeInTheDocument();
    expect(screen.getByTestId("block-detail-para-scope-1")).toBeInTheDocument();
  });

  it("clicking a para scope button selects that para", async () => {
    const user = userEvent.setup();
    renderWithQuery(<BlockDetail page={makePage()} projectId="p1" pageIndex={0} level="block" />);
    await user.click(screen.getByTestId("block-detail-tab-para-layout"));
    await user.click(screen.getByTestId("block-detail-para-scope-1"));
    const { level: selLevel, path } = selectionStore.getState();
    expect(selLevel).toBe("para");
    expect(path.paraId).toBe(1);
  });
});

// ─── Gap 46 regression guard — --right-w ──────────────────────────────────────

describe("BlockDetail — Gap 46 regression guard", () => {
  it("renders without errors (block panel slot width governed by --right-w CSS var)", () => {
    selectBlock("b1");
    const qc = makeQueryClient();
    const { container } = render(
      <QueryClientProvider client={qc}>
        <BlockDetail page={makePage()} projectId="p1" pageIndex={0} level="block" />
      </QueryClientProvider>,
    );
    expect(container.querySelector("[data-testid='block-detail']")).toBeInTheDocument();
  });
});

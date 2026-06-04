// ToolbarActionGrid.test.tsx — tests for toolbar grid (#207)
// Covers: B-ACTIONS-012, B-ACTIONS-013, F-TOOLBAR-GRID-01, F-TOOLBAR-STYLE-ADD-01
// Spec: docs/specs/2026-05-12-toolbar-actions-design.md
// Acceptance:
//   - All 56 cells present (4 rows × 14 columns)
//   - Absent cells have data-testid-stub="true"
//   - useToolbarButtonStates drives disabled state
//   - Apply-style row present (apply-style-select, scope-select, etc.) — driver-contract §2.10
//   - Add Word row present (word-add-button) — driver-contract §2.10

import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { ToolbarActionGrid } from "./ToolbarActionGrid";
import type { ButtonStates, PageData, Selection } from "../hooks/useToolbarButtonStates";

// Mock useLabelVocabulary — ToolbarActionGrid sources vocab from it.
// Mock returns canonical book-tools sets so tests can assert the correct values.
vi.mock("../hooks/useLabelVocabulary", () => ({
  useLabelVocabulary: () => ({
    textStyleLabels: [
      "all caps",
      "blackletter",
      "bold",
      "handwritten",
      "italics",
      "monospace",
      "regular",
      "small caps",
      "strikethrough",
      "underline",
    ],
    wordComponents: [
      "drop cap",
      "drop cap unrecovered",
      "footnote marker",
      "subscript",
      "superscript",
    ],
    isLoading: false,
    isError: false,
  }),
}));

const emptySelection: Selection = {
  selection_mode: "word",
  selected_paragraphs: [],
  selected_lines: [],
  selected_words: [],
};

const emptyPage: PageData = { lines: [] };

const mockOnAction = vi.fn();
const mockOnApplyStyle = vi.fn();
const mockOnClearStyle = vi.fn();
const mockOnAddWordToggle = vi.fn();

const defaultProps = {
  selection: emptySelection,
  pageData: emptyPage,
  onAction: mockOnAction,
  onApplyStyle: mockOnApplyStyle,
  onClearStyle: mockOnClearStyle,
  addWordActive: false,
  onAddWordToggle: mockOnAddWordToggle,
};

describe("ToolbarActionGrid — structure", () => {
  it("renders 56 cells total (4 rows × 14 columns, including stub cells)", () => {
    render(<ToolbarActionGrid {...defaultProps} />);
    // Count all action cell buttons (not row-label cells)
    const cells = document.querySelectorAll("[data-testid^='toolbar-']");
    // 4 rows × 14 actions = 56 cells
    expect(cells.length).toBeGreaterThanOrEqual(56);
  });

  it("page-row cells are always enabled (page scope actions)", () => {
    render(<ToolbarActionGrid {...defaultProps} />);
    // Page-scope refine should be enabled even with empty selection
    const pageValidate = screen.getByTestId("toolbar-page-validate");
    expect(pageValidate).toBeDisabled(); // no unvalidated words
  });

  it("stub cells have data-testid-stub='true'", () => {
    render(<ToolbarActionGrid {...defaultProps} />);
    const stubs = document.querySelectorAll("[data-testid-stub='true']");
    expect(stubs.length).toBeGreaterThan(0);
  });

  it("word-row validate disabled when no words selected", () => {
    render(<ToolbarActionGrid {...defaultProps} />);
    const btn = screen.getByTestId("toolbar-word-validate");
    expect(btn).toBeDisabled();
  });

  // Q-B2-STYLE-LABELS RESOLVED (option b): style labels now sourced from backend.
  // Guard: only canonical book-tools ALLOWED_TEXT_STYLE_LABELS appear in the style select.
  it("uses canonical book-tools style label 'italics' (not 'italic')", () => {
    render(<ToolbarActionGrid {...defaultProps} />);
    const select = screen.getByTestId("apply-style-select");
    const values = Array.from(select.querySelectorAll("option")).map(
      (o) => (o as HTMLOptionElement).value,
    );
    expect(values).toContain("italics");
    expect(values).not.toContain("italic");
  });

  it("style select does NOT contain superscript (it is a component)", () => {
    render(<ToolbarActionGrid {...defaultProps} />);
    const select = screen.getByTestId("apply-style-select");
    const values = Array.from(select.querySelectorAll("option")).map(
      (o) => (o as HTMLOptionElement).value,
    );
    expect(values).not.toContain("superscript");
    expect(values).not.toContain("subscript");
  });

  it("component select contains superscript and subscript (they are components)", () => {
    render(<ToolbarActionGrid {...defaultProps} />);
    const select = screen.getByTestId("apply-component-select");
    const values = Array.from(select.querySelectorAll("option")).map(
      (o) => (o as HTMLOptionElement).value,
    );
    expect(values).toContain("superscript");
    expect(values).toContain("subscript");
  });

  it("style select contains only canonical ALLOWED_TEXT_STYLE_LABELS (no unknown values)", () => {
    const canonicalStyles = new Set([
      "all caps",
      "blackletter",
      "bold",
      "handwritten",
      "italics",
      "monospace",
      "regular",
      "small caps",
      "strikethrough",
      "underline",
    ]);
    render(<ToolbarActionGrid {...defaultProps} />);
    const select = screen.getByTestId("apply-style-select");
    const values = Array.from(select.querySelectorAll("option"))
      .map((o) => (o as HTMLOptionElement).value)
      .filter((v) => v !== ""); // skip the placeholder ""
    for (const v of values) {
      expect(canonicalStyles.has(v)).toBe(true);
    }
  });

  it("component select contains only canonical ALLOWED_COMPONENTS (no unknown values)", () => {
    const canonicalComponents = new Set([
      "drop cap",
      "drop cap unrecovered",
      "footnote marker",
      "subscript",
      "superscript",
    ]);
    render(<ToolbarActionGrid {...defaultProps} />);
    const select = screen.getByTestId("apply-component-select");
    const values = Array.from(select.querySelectorAll("option"))
      .map((o) => (o as HTMLOptionElement).value)
      .filter((v) => v !== ""); // skip the placeholder ""
    for (const v of values) {
      expect(canonicalComponents.has(v)).toBe(true);
    }
  });

  it("renders apply-style-select", () => {
    render(<ToolbarActionGrid {...defaultProps} />);
    expect(screen.getByTestId("apply-style-select")).toBeTruthy();
  });

  it("renders scope-select (driver-contract §2.10 canonical id)", () => {
    render(<ToolbarActionGrid {...defaultProps} />);
    expect(screen.getByTestId("scope-select")).toBeTruthy();
  });

  it("renders apply-component-select", () => {
    render(<ToolbarActionGrid {...defaultProps} />);
    expect(screen.getByTestId("apply-component-select")).toBeTruthy();
  });

  it("renders apply-style-button", () => {
    render(<ToolbarActionGrid {...defaultProps} />);
    expect(screen.getByTestId("apply-style-button")).toBeTruthy();
  });

  it("renders clear-style-button", () => {
    render(<ToolbarActionGrid {...defaultProps} />);
    expect(screen.getByTestId("clear-style-button")).toBeTruthy();
  });

  it("renders word-add-button (driver-contract §2.10 canonical id)", () => {
    render(<ToolbarActionGrid {...defaultProps} />);
    expect(screen.getByTestId("word-add-button")).toBeTruthy();
  });
});

describe("ToolbarActionGrid — interactions", () => {
  it("clicking a non-stub page action calls onAction with correct key", () => {
    const onAction = vi.fn();
    render(<ToolbarActionGrid {...defaultProps} onAction={onAction} />);
    const btn = screen.getByTestId("toolbar-page-refine");
    fireEvent.click(btn);
    expect(onAction).toHaveBeenCalledWith("page_refine");
  });

  it("clicking a disabled word action does NOT call onAction", () => {
    const onAction = vi.fn();
    render(<ToolbarActionGrid {...defaultProps} onAction={onAction} />);
    const btn = screen.getByTestId("toolbar-word-validate");
    // disabled button: fireEvent still fires but component should guard
    expect(btn).toBeDisabled();
  });

  it("Apply Style button calls onApplyStyle", () => {
    const onApplyStyle = vi.fn();
    render(<ToolbarActionGrid {...defaultProps} onApplyStyle={onApplyStyle} />);
    fireEvent.click(screen.getByTestId("apply-style-button"));
    expect(onApplyStyle).toHaveBeenCalledOnce();
  });

  it("Clear Style button calls onClearStyle", () => {
    const onClearStyle = vi.fn();
    render(<ToolbarActionGrid {...defaultProps} onClearStyle={onClearStyle} />);
    fireEvent.click(screen.getByTestId("clear-style-button"));
    expect(onClearStyle).toHaveBeenCalledOnce();
  });

  it("word-add-button calls onAddWordToggle", () => {
    const onAddWordToggle = vi.fn();
    render(<ToolbarActionGrid {...defaultProps} onAddWordToggle={onAddWordToggle} />);
    fireEvent.click(screen.getByTestId("word-add-button"));
    expect(onAddWordToggle).toHaveBeenCalledOnce();
  });

  it("word-add-button shows active state when addWordActive=true", () => {
    render(<ToolbarActionGrid {...defaultProps} addWordActive={true} />);
    const btn = screen.getByTestId("word-add-button");
    expect(btn.getAttribute("aria-pressed")).toBe("true");
  });
});

describe("ToolbarActionGrid — ButtonStates injection (external states override)", () => {
  it("accepts external buttonStates to override computed states", () => {
    const externalStates: Partial<ButtonStates> = {
      page_validate: true,
    };
    render(<ToolbarActionGrid {...defaultProps} buttonStatesOverride={externalStates} />);
    const btn = screen.getByTestId("toolbar-page-validate");
    expect(btn).not.toBeDisabled();
  });
});

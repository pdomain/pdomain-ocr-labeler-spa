// ComponentPalette.test.tsx — P2.e tests for the component chip palette.
//
// Q-B2-STYLE-LABELS option (b): ComponentPalette now sources labels from
// useLabelVocabulary (mocked here). Canonical keys from book-tools' ALLOWED_COMPONENTS.
// superscript / subscript now appear HERE (they are components, not styles).

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ComponentPalette } from "./ComponentPalette";

// Mock useLabelVocabulary so ComponentPalette renders the canonical set in tests.
vi.mock("../../hooks/useLabelVocabulary", () => ({
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
  FALLBACK_STYLES: [
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
  FALLBACK_COMPONENTS: [
    "drop cap",
    "drop cap unrecovered",
    "footnote marker",
    "subscript",
    "superscript",
  ],
}));

describe("ComponentPalette (P2.e + Q-B2-STYLE-LABELS)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the palette container", () => {
    render(<ComponentPalette activeComponents={[]} onComponentChange={vi.fn()} />);
    expect(screen.getByTestId("component-palette")).toBeInTheDocument();
  });

  it("renders chips for all 5 canonical component types (ALLOWED_COMPONENTS)", () => {
    render(<ComponentPalette activeComponents={[]} onComponentChange={vi.fn()} />);
    expect(screen.getByTestId("component-chip-drop-cap")).toBeInTheDocument();
    expect(screen.getByTestId("component-chip-drop-cap-unrecovered")).toBeInTheDocument();
    expect(screen.getByTestId("component-chip-footnote-marker")).toBeInTheDocument();
    expect(screen.getByTestId("component-chip-subscript")).toBeInTheDocument();
    expect(screen.getByTestId("component-chip-superscript")).toBeInTheDocument();
  });

  // Q-B2-STYLE-LABELS guard: superscript and subscript ARE components.
  // They MUST appear in ComponentPalette.
  it("renders superscript chip in ComponentPalette (it is a component)", () => {
    render(<ComponentPalette activeComponents={[]} onComponentChange={vi.fn()} />);
    expect(screen.getByTestId("component-chip-superscript")).toBeInTheDocument();
  });

  it("renders subscript chip in ComponentPalette (it is a component)", () => {
    render(<ComponentPalette activeComponents={[]} onComponentChange={vi.fn()} />);
    expect(screen.getByTestId("component-chip-subscript")).toBeInTheDocument();
  });

  it("shows drop-cap chip as 'on' when 'drop cap' is active", () => {
    render(<ComponentPalette activeComponents={["drop cap"]} onComponentChange={vi.fn()} />);
    expect(screen.getByTestId("component-chip-drop-cap")).toHaveAttribute(
      "data-tristate-value",
      "on",
    );
  });

  it("shows footnote-marker chip as 'off' when not active", () => {
    render(<ComponentPalette activeComponents={["drop cap"]} onComponentChange={vi.fn()} />);
    expect(screen.getByTestId("component-chip-footnote-marker")).toHaveAttribute(
      "data-tristate-value",
      "off",
    );
  });

  it("calls onComponentChange with canonical 'superscript' key when clicked", async () => {
    const onChange = vi.fn();
    render(<ComponentPalette activeComponents={[]} onComponentChange={onChange} />);
    await userEvent.click(screen.getByTestId("component-chip-superscript"));
    expect(onChange).toHaveBeenCalledWith("superscript", "on");
  });

  it("calls onComponentChange with canonical 'drop cap' (with space) when clicked", async () => {
    const onChange = vi.fn();
    render(<ComponentPalette activeComponents={[]} onComponentChange={onChange} />);
    await userEvent.click(screen.getByTestId("component-chip-drop-cap"));
    // Applied value must be the canonical "drop cap" (with space), not "drop-cap"
    expect(onChange).toHaveBeenCalledWith("drop cap", "on");
  });

  it("calls onComponentChange with canonical 'footnote marker' (with space) when clicked", async () => {
    const onChange = vi.fn();
    render(<ComponentPalette activeComponents={[]} onComponentChange={onChange} />);
    await userEvent.click(screen.getByTestId("component-chip-footnote-marker"));
    expect(onChange).toHaveBeenCalledWith("footnote marker", "on");
  });

  it("toggling active component calls onComponentChange with 'mixed'", async () => {
    const onChange = vi.fn();
    render(<ComponentPalette activeComponents={["superscript"]} onComponentChange={onChange} />);
    await userEvent.click(screen.getByTestId("component-chip-superscript"));
    expect(onChange).toHaveBeenCalledWith("superscript", "mixed");
  });
});

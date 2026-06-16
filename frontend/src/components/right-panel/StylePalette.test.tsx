// StylePalette.test.tsx — P2.d tests for the style chip palette.
//
// Q-B2-STYLE-LABELS option (b): StylePalette now sources labels from
// useLabelVocabulary (mocked here). Canonical keys from book-tools' ALLOWED_TEXT_STYLE_LABELS.
// superscript / subscript are COMPONENTS and must NOT appear in StylePalette.

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StylePalette, ChipPalette } from "./StylePalette";
import type { TriStateValue } from "@pdomain/pdomain-ui/primitives";

// Mock useLabelVocabulary so StylePalette renders the canonical set in tests
// without needing a real QueryClient + MSW.
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

describe("StylePalette (P2.d + Q-B2-STYLE-LABELS)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the palette container", () => {
    render(<StylePalette activeStyles={[]} onStyleChange={vi.fn()} />);
    expect(screen.getByTestId("style-palette")).toBeInTheDocument();
  });

  it("renders chips for all 10 canonical style types (ALLOWED_TEXT_STYLE_LABELS)", () => {
    render(<StylePalette activeStyles={[]} onStyleChange={vi.fn()} />);
    expect(screen.getByTestId("style-chip-bold")).toBeInTheDocument();
    expect(screen.getByTestId("style-chip-italics")).toBeInTheDocument();
    expect(screen.getByTestId("style-chip-small-caps")).toBeInTheDocument();
    expect(screen.getByTestId("style-chip-underline")).toBeInTheDocument();
    expect(screen.getByTestId("style-chip-strikethrough")).toBeInTheDocument();
    expect(screen.getByTestId("style-chip-regular")).toBeInTheDocument();
    expect(screen.getByTestId("style-chip-all-caps")).toBeInTheDocument();
    expect(screen.getByTestId("style-chip-blackletter")).toBeInTheDocument();
    expect(screen.getByTestId("style-chip-handwritten")).toBeInTheDocument();
    expect(screen.getByTestId("style-chip-monospace")).toBeInTheDocument();
  });

  // Q-B2-STYLE-LABELS guard: superscript and subscript are COMPONENTS, not styles.
  // They must NOT appear in StylePalette.
  it("does NOT render superscript chip in StylePalette (it is a component)", () => {
    render(<StylePalette activeStyles={[]} onStyleChange={vi.fn()} />);
    expect(screen.queryByTestId("style-chip-superscript")).not.toBeInTheDocument();
  });

  it("does NOT render subscript chip in StylePalette (it is a component)", () => {
    render(<StylePalette activeStyles={[]} onStyleChange={vi.fn()} />);
    expect(screen.queryByTestId("style-chip-subscript")).not.toBeInTheDocument();
  });

  it("shows bold chip as 'on' when bold is in activeStyles", () => {
    render(<StylePalette activeStyles={["bold"]} onStyleChange={vi.fn()} />);
    expect(screen.getByTestId("style-chip-bold")).toHaveAttribute("data-tristate-value", "on");
  });

  it("shows italic chip as 'off' when not in activeStyles", () => {
    render(<StylePalette activeStyles={["bold"]} onStyleChange={vi.fn()} />);
    expect(screen.getByTestId("style-chip-italics")).toHaveAttribute("data-tristate-value", "off");
  });

  it("calls onStyleChange with canonical key when a chip is clicked", async () => {
    const onStyleChange = vi.fn();
    render(<StylePalette activeStyles={[]} onStyleChange={onStyleChange} />);
    await userEvent.click(screen.getByTestId("style-chip-bold"));
    expect(onStyleChange).toHaveBeenCalledWith("bold", "on");
  });

  // P1.4 (B-41): ChipPalette is binary — an active chip's next value is
  // "off", never "mixed" (consumers skip "mixed", which made the off-toggle
  // unreachable: styles could never be cleared from the palette).
  it("toggling active style calls onStyleChange with 'off'", async () => {
    const onStyleChange = vi.fn();
    render(<StylePalette activeStyles={["bold"]} onStyleChange={onStyleChange} />);
    await userEvent.click(screen.getByTestId("style-chip-bold"));
    expect(onStyleChange).toHaveBeenCalledWith("bold", "off");
  });

  it("calls onStyleChange with canonical 'small caps' (with space) when clicked", async () => {
    const onStyleChange = vi.fn();
    render(<StylePalette activeStyles={[]} onStyleChange={onStyleChange} />);
    await userEvent.click(screen.getByTestId("style-chip-small-caps"));
    // Applied value must be the canonical "small caps" (with space), not "small-caps"
    expect(onStyleChange).toHaveBeenCalledWith("small caps", "on");
  });

  it("calls onStyleChange with canonical 'italics' (plural) when clicked", async () => {
    const onStyleChange = vi.fn();
    render(<StylePalette activeStyles={[]} onStyleChange={onStyleChange} />);
    await userEvent.click(screen.getByTestId("style-chip-italics"));
    expect(onStyleChange).toHaveBeenCalledWith("italics", "on");
  });
});

describe("ChipPalette (P2.d reusable)", () => {
  const items = [
    { key: "a", label: "A" },
    { key: "b", label: "B" },
  ];

  it("renders chips with correct testids", () => {
    const noop: (key: string, next: TriStateValue) => void = vi.fn();
    render(
      <ChipPalette
        items={items}
        activeKeys={new Set()}
        data-testid-prefix="test"
        onChange={noop}
      />,
    );
    expect(screen.getByTestId("test-a")).toBeInTheDocument();
    expect(screen.getByTestId("test-b")).toBeInTheDocument();
  });

  it("active keys show as 'on'", () => {
    const noop: (key: string, next: TriStateValue) => void = vi.fn();
    render(
      <ChipPalette
        items={items}
        activeKeys={new Set(["a"])}
        data-testid-prefix="test"
        onChange={noop}
      />,
    );
    expect(screen.getByTestId("test-a")).toHaveAttribute("data-tristate-value", "on");
    expect(screen.getByTestId("test-b")).toHaveAttribute("data-tristate-value", "off");
  });
});

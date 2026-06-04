// StylePalette.test.tsx — P2.d tests for the style chip palette.

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StylePalette, ChipPalette } from "./StylePalette";
import type { TristateValue } from "../ui/Chip";

describe("StylePalette (P2.d)", () => {
  it("renders the palette container", () => {
    render(<StylePalette activeStyles={[]} onStyleChange={vi.fn()} />);
    expect(screen.getByTestId("style-palette")).toBeInTheDocument();
  });

  it("renders chips for all 7 style types", () => {
    render(<StylePalette activeStyles={[]} onStyleChange={vi.fn()} />);
    expect(screen.getByTestId("style-chip-bold")).toBeInTheDocument();
    expect(screen.getByTestId("style-chip-italics")).toBeInTheDocument();
    expect(screen.getByTestId("style-chip-small-caps")).toBeInTheDocument();
    expect(screen.getByTestId("style-chip-superscript")).toBeInTheDocument();
    expect(screen.getByTestId("style-chip-subscript")).toBeInTheDocument();
    expect(screen.getByTestId("style-chip-strikethrough")).toBeInTheDocument();
    expect(screen.getByTestId("style-chip-underline")).toBeInTheDocument();
  });

  it("shows bold chip as 'on' when bold is in activeStyles", () => {
    render(<StylePalette activeStyles={["bold"]} onStyleChange={vi.fn()} />);
    expect(screen.getByTestId("style-chip-bold")).toHaveAttribute("data-tristate-value", "on");
  });

  it("shows italic chip as 'off' when not in activeStyles", () => {
    render(<StylePalette activeStyles={["bold"]} onStyleChange={vi.fn()} />);
    expect(screen.getByTestId("style-chip-italics")).toHaveAttribute("data-tristate-value", "off");
  });

  it("calls onStyleChange when a chip is clicked", async () => {
    const onStyleChange = vi.fn();
    render(<StylePalette activeStyles={[]} onStyleChange={onStyleChange} />);
    await userEvent.click(screen.getByTestId("style-chip-bold"));
    expect(onStyleChange).toHaveBeenCalledWith("bold", "on");
  });

  it("toggling active style calls onStyleChange with 'mixed'", async () => {
    const onStyleChange = vi.fn();
    render(<StylePalette activeStyles={["bold"]} onStyleChange={onStyleChange} />);
    await userEvent.click(screen.getByTestId("style-chip-bold"));
    expect(onStyleChange).toHaveBeenCalledWith("bold", "mixed");
  });
});

describe("ChipPalette (P2.d reusable)", () => {
  const items = [
    { key: "a", label: "A" },
    { key: "b", label: "B" },
  ];

  it("renders chips with correct testids", () => {
    const noop: (key: string, next: TristateValue) => void = vi.fn();
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
    const noop: (key: string, next: TristateValue) => void = vi.fn();
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

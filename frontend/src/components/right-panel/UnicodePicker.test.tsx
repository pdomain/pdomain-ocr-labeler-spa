// UnicodePicker.test.tsx — Tests for Slice 20 unicode glyph picker.
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 20.

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { UnicodePicker } from "./UnicodePicker";

describe("UnicodePicker (Slice 20)", () => {
  it("renders the picker container with data-testid=unicode-picker", () => {
    render(<UnicodePicker onInsert={() => {}} />);
    expect(screen.getByTestId("unicode-picker")).toBeInTheDocument();
  });

  it("renders accordion sub-sections (em-dash, curly quotes, fractions, ligatures)", () => {
    render(<UnicodePicker onInsert={() => {}} />);
    expect(screen.getByRole("button", { name: /em-dash/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /curly quotes/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /fractions/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /ligatures/i })).toBeInTheDocument();
  });

  it("renders a search input", () => {
    render(<UnicodePicker onInsert={() => {}} />);
    expect(screen.getByTestId("unicode-picker-search")).toBeInTheDocument();
  });

  it("clicking a glyph button invokes onInsert with that glyph", async () => {
    const onInsert = vi.fn();
    const user = userEvent.setup();
    render(<UnicodePicker onInsert={onInsert} />);

    // Open the em-dash section
    await user.click(screen.getByRole("button", { name: /em-dash/i }));

    // The em-dash glyph button should be visible — click it
    const emdashBtn = screen.getByTestId("unicode-glyph-em-dash");
    await user.click(emdashBtn);
    expect(onInsert).toHaveBeenCalledWith("—");
  });

  it("typing in search narrows visible glyphs", async () => {
    const user = userEvent.setup();
    render(<UnicodePicker onInsert={() => {}} />);

    const search = screen.getByTestId("unicode-picker-search");
    await user.type(search, "em-dash");

    // em-dash glyph should be present
    expect(screen.getByTestId("unicode-glyph-em-dash")).toBeInTheDocument();
    // ldquo (left curly double quote) should be filtered out
    expect(screen.queryByTestId("unicode-glyph-ldquo")).not.toBeInTheDocument();
  });
});

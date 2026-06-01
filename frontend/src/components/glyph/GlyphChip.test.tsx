// GlyphChip.test.tsx — unit tests for the GlyphChip pill component.
// Covers: B-GLYPH-001
// Spec: specs/20-glyph-annotations.md §5.2
// Issue #269

import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { GlyphChip } from "./GlyphChip";

describe("GlyphChip", () => {
  it("renders confirmed CT chip with correct testid", () => {
    render(<GlyphChip lineIndex={0} wordIndex={1} kind="ct" predicted={false} onClick={vi.fn()} />);
    expect(screen.getByTestId("word-glyph-chip-0-1-ct")).toBeTruthy();
  });

  it("renders predicted chip with '?' suffix in testid", () => {
    render(<GlyphChip lineIndex={2} wordIndex={3} kind="st" predicted={true} onClick={vi.fn()} />);
    expect(screen.getByTestId("word-glyph-chip-2-3-predicted-st")).toBeTruthy();
  });

  it("calls onClick when clicked", () => {
    const handleClick = vi.fn();
    render(
      <GlyphChip lineIndex={0} wordIndex={0} kind="ct" predicted={false} onClick={handleClick} />,
    );
    fireEvent.click(screen.getByTestId("word-glyph-chip-0-0-ct"));
    expect(handleClick).toHaveBeenCalledOnce();
  });

  it("predicted chip has muted styling class", () => {
    render(<GlyphChip lineIndex={0} wordIndex={0} kind="fi" predicted={true} onClick={vi.fn()} />);
    const chip = screen.getByTestId("word-glyph-chip-0-0-predicted-fi");
    // Predicted chips should have some visual distinction
    expect(chip.className).toContain("opacity");
  });
});

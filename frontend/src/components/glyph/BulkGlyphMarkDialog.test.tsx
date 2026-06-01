// BulkGlyphMarkDialog.test.tsx — unit tests for the bulk glyph mark dialog.
// Covers: B-GLYPH-004
// Spec: specs/20-glyph-annotations.md §5.5
// Issue #270

import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { BulkGlyphMarkDialog } from "./BulkGlyphMarkDialog";

describe("BulkGlyphMarkDialog", () => {
  it("renders with correct dialog testid when open", () => {
    render(<BulkGlyphMarkDialog open={true} projectId="proj1" pageIndex={0} onClose={vi.fn()} />);
    expect(screen.getByTestId("bulk-glyph-mark-dialog")).toBeTruthy();
  });

  it("does not render dialog content when closed", () => {
    render(<BulkGlyphMarkDialog open={false} projectId="proj1" pageIndex={0} onClose={vi.fn()} />);
    expect(screen.queryByTestId("bulk-glyph-mark-dialog")).toBeNull();
  });

  it("renders recipe select with correct testid", () => {
    render(<BulkGlyphMarkDialog open={true} projectId="proj1" pageIndex={0} onClose={vi.fn()} />);
    expect(screen.getByTestId("bulk-glyph-recipe-select")).toBeTruthy();
  });

  it("renders skip-annotated checkbox with correct testid", () => {
    render(<BulkGlyphMarkDialog open={true} projectId="proj1" pageIndex={0} onClose={vi.fn()} />);
    expect(screen.getByTestId("bulk-glyph-skip-annotated-checkbox")).toBeTruthy();
  });

  it("renders accept-predictions checkbox with correct testid", () => {
    render(<BulkGlyphMarkDialog open={true} projectId="proj1" pageIndex={0} onClose={vi.fn()} />);
    expect(screen.getByTestId("bulk-glyph-accept-predictions-checkbox")).toBeTruthy();
  });

  it("renders dry-run preview button with correct testid", () => {
    render(<BulkGlyphMarkDialog open={true} projectId="proj1" pageIndex={0} onClose={vi.fn()} />);
    expect(screen.getByTestId("bulk-glyph-dry-run-button")).toBeTruthy();
  });

  it("renders apply button with correct testid", () => {
    render(<BulkGlyphMarkDialog open={true} projectId="proj1" pageIndex={0} onClose={vi.fn()} />);
    expect(screen.getByTestId("bulk-glyph-apply-button")).toBeTruthy();
  });

  it("calls onClose when Cancel is clicked", () => {
    const handleClose = vi.fn();
    render(
      <BulkGlyphMarkDialog open={true} projectId="proj1" pageIndex={0} onClose={handleClose} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(handleClose).toHaveBeenCalledOnce();
  });

  it("recipe select defaults to ct_substring", () => {
    render(<BulkGlyphMarkDialog open={true} projectId="proj1" pageIndex={0} onClose={vi.fn()} />);
    const select = screen.getByTestId("bulk-glyph-recipe-select") as HTMLSelectElement;
    expect(select.value).toBe("ct_substring");
  });
});

// BulkGlyphMarkDialog.test.tsx — unit tests for the bulk glyph mark dialog.
// Covers: B-GLYPH-004
// Spec: specs/20-glyph-annotations.md §5.5
// Issue #270
//
// M11 Task 7 (docs/plans/2026-07-21-glyph-annotations-completion.md):
// a successful (non-dry-run) apply must invalidate the page query, or
// chips/badges stay stale until a manual refresh
// (docs/issues/2026-07-21-glyph-m11-usable-path-incomplete.md). The dialog
// now reads a QueryClient via useQueryClient, so every render below needs a
// QueryClientProvider ancestor.

import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import type React from "react";
import { server } from "../../test/server";
import { BulkGlyphMarkDialog } from "./BulkGlyphMarkDialog";

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

function renderWithQuery(ui: React.ReactElement, qc: QueryClient = makeQueryClient()) {
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("BulkGlyphMarkDialog", () => {
  it("renders with correct dialog testid when open", () => {
    renderWithQuery(
      <BulkGlyphMarkDialog open={true} projectId="proj1" pageIndex={0} onClose={vi.fn()} />,
    );
    expect(screen.getByTestId("bulk-glyph-mark-dialog")).toBeTruthy();
  });

  it("does not render dialog content when closed", () => {
    renderWithQuery(
      <BulkGlyphMarkDialog open={false} projectId="proj1" pageIndex={0} onClose={vi.fn()} />,
    );
    expect(screen.queryByTestId("bulk-glyph-mark-dialog")).toBeNull();
  });

  it("renders recipe select with correct testid", () => {
    renderWithQuery(
      <BulkGlyphMarkDialog open={true} projectId="proj1" pageIndex={0} onClose={vi.fn()} />,
    );
    expect(screen.getByTestId("bulk-glyph-recipe-select")).toBeTruthy();
  });

  it("renders skip-annotated checkbox with correct testid", () => {
    renderWithQuery(
      <BulkGlyphMarkDialog open={true} projectId="proj1" pageIndex={0} onClose={vi.fn()} />,
    );
    expect(screen.getByTestId("bulk-glyph-skip-annotated-checkbox")).toBeTruthy();
  });

  it("renders accept-predictions checkbox with correct testid", () => {
    renderWithQuery(
      <BulkGlyphMarkDialog open={true} projectId="proj1" pageIndex={0} onClose={vi.fn()} />,
    );
    expect(screen.getByTestId("bulk-glyph-accept-predictions-checkbox")).toBeTruthy();
  });

  it("renders dry-run preview button with correct testid", () => {
    renderWithQuery(
      <BulkGlyphMarkDialog open={true} projectId="proj1" pageIndex={0} onClose={vi.fn()} />,
    );
    expect(screen.getByTestId("bulk-glyph-dry-run-button")).toBeTruthy();
  });

  it("renders apply button with correct testid", () => {
    renderWithQuery(
      <BulkGlyphMarkDialog open={true} projectId="proj1" pageIndex={0} onClose={vi.fn()} />,
    );
    expect(screen.getByTestId("bulk-glyph-apply-button")).toBeTruthy();
  });

  it("calls onClose when Cancel is clicked", () => {
    const handleClose = vi.fn();
    renderWithQuery(
      <BulkGlyphMarkDialog open={true} projectId="proj1" pageIndex={0} onClose={handleClose} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(handleClose).toHaveBeenCalledOnce();
  });

  it("recipe select defaults to ct_substring", () => {
    renderWithQuery(
      <BulkGlyphMarkDialog open={true} projectId="proj1" pageIndex={0} onClose={vi.fn()} />,
    );
    const select = screen.getByTestId("bulk-glyph-recipe-select") as HTMLSelectElement;
    expect(select.value).toBe("ct_substring");
  });

  // ─── M11 Task 7: apply invalidates the page query ─────────────────────────

  it("invalidates the page query after a successful apply", async () => {
    server.use(
      http.post("/api/projects/proj1/pages/3/glyph-bulk-mark", () =>
        HttpResponse.json({ affected_word_ids: ["w1"], skipped_word_ids: [], page: {} }),
      ),
    );
    const qc = makeQueryClient();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const handleClose = vi.fn();
    renderWithQuery(
      <BulkGlyphMarkDialog open={true} projectId="proj1" pageIndex={3} onClose={handleClose} />,
      qc,
    );

    fireEvent.click(screen.getByTestId("bulk-glyph-apply-button"));

    await waitFor(() => expect(handleClose).toHaveBeenCalledOnce());
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["page", "proj1", 3] });
  });

  it("does not invalidate the page query when apply fails", async () => {
    server.use(
      http.post("/api/projects/proj1/pages/0/glyph-bulk-mark", () =>
        HttpResponse.json({ message: "boom" }, { status: 500 }),
      ),
    );
    const qc = makeQueryClient();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    renderWithQuery(
      <BulkGlyphMarkDialog open={true} projectId="proj1" pageIndex={0} onClose={vi.fn()} />,
      qc,
    );

    fireEvent.click(screen.getByTestId("bulk-glyph-apply-button"));

    await screen.findByText(/bulk mark failed/i);
    expect(invalidateSpy).not.toHaveBeenCalled();
  });

  it("does not invalidate the page query after a dry-run preview", async () => {
    server.use(
      http.post("/api/projects/proj1/pages/0/glyph-bulk-mark", () =>
        HttpResponse.json({ affected_word_ids: ["w1", "w2"], skipped_word_ids: [], page: {} }),
      ),
    );
    const qc = makeQueryClient();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    renderWithQuery(
      <BulkGlyphMarkDialog open={true} projectId="proj1" pageIndex={0} onClose={vi.fn()} />,
      qc,
    );

    fireEvent.click(screen.getByTestId("bulk-glyph-dry-run-button"));

    await screen.findByTestId("bulk-glyph-preview-count");
    expect(invalidateSpy).not.toHaveBeenCalled();
  });
});

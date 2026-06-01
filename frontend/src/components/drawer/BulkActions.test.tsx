// BulkActions.test.tsx — Tests for Slice 23: bulk actions bar.
// Covers: B-DRAWER-003, B-DRAWER-006
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 23.

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BulkActions } from "./BulkActions";
import { worklistStore } from "../../stores/worklist-store";

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

function renderWithQuery(ui: React.ReactElement) {
  const qc = makeQueryClient();
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("BulkActions (Slice 23)", () => {
  beforeEach(() => {
    worklistStore.reset();
    vi.restoreAllMocks();
  });

  it("renders the panel even when selectedIds is empty (page-level actions always visible)", () => {
    renderWithQuery(<BulkActions projectId="p1" pageIndex={0} />);
    expect(screen.getByTestId("bulk-actions")).toBeInTheDocument();
    // Selection-specific UI is hidden when nothing selected.
    expect(screen.queryByTestId("bulk-actions-count")).not.toBeInTheDocument();
    expect(screen.queryByTestId("bulk-actions-clear")).not.toBeInTheDocument();
    // Page-level actions are always present.
    expect(screen.getByTestId("bulk-actions-rerun-match")).toBeInTheDocument();
    expect(screen.getByTestId("bulk-actions-export")).toBeInTheDocument();
    // Mark reviewed is present but disabled.
    expect(screen.getByTestId("bulk-actions-mark-reviewed")).toBeDisabled();
  });

  it("renders the bar when selectedIds has items", () => {
    worklistStore.selectAll([1, 2, 3]);
    renderWithQuery(<BulkActions projectId="p1" pageIndex={0} />);
    expect(screen.getByTestId("bulk-actions")).toBeInTheDocument();
    expect(screen.getByTestId("bulk-actions-count")).toHaveTextContent("3 selected");
  });

  it("clear button empties selection", async () => {
    const user = userEvent.setup();
    worklistStore.selectAll([1, 2]);
    const { rerender } = renderWithQuery(<BulkActions projectId="p1" pageIndex={0} />);
    await user.click(screen.getByTestId("bulk-actions-clear"));
    // After clear, store should have 0 selected ids.
    expect(worklistStore.getState().selectedIds).toHaveLength(0);
    // Re-render — panel stays visible but selection row is gone.
    const qc = makeQueryClient();
    rerender(
      <QueryClientProvider client={qc}>
        <BulkActions projectId="p1" pageIndex={0} />
      </QueryClientProvider>,
    );
    expect(screen.getByTestId("bulk-actions")).toBeInTheDocument();
    expect(screen.queryByTestId("bulk-actions-count")).not.toBeInTheDocument();
    expect(screen.queryByTestId("bulk-actions-clear")).not.toBeInTheDocument();
  });

  it("mark-reviewed button triggers fetch and clears selection on success", async () => {
    const user = userEvent.setup();
    worklistStore.selectAll([0, 1]);

    // Mock fetch to succeed.
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({}),
      text: async () => "",
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWithQuery(<BulkActions projectId="p1" pageIndex={0} />);
    await user.click(screen.getByTestId("bulk-actions-mark-reviewed"));

    // fetch was called with validate-batch url.
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("validate-batch"),
      expect.objectContaining({ method: "POST" }),
    );

    // Selection cleared after success.
    expect(worklistStore.getState().selectedIds).toHaveLength(0);
  });

  it("shows all three action buttons", () => {
    worklistStore.selectAll([5]);
    renderWithQuery(<BulkActions projectId="p1" pageIndex={0} />);
    expect(screen.getByTestId("bulk-actions-mark-reviewed")).toBeInTheDocument();
    expect(screen.getByTestId("bulk-actions-rerun-match")).toBeInTheDocument();
    expect(screen.getByTestId("bulk-actions-export")).toBeInTheDocument();
  });
});

describe("error toasts (Slice 23)", () => {
  let toastErrorSpy: any;

  beforeEach(async () => {
    worklistStore.reset();
    vi.restoreAllMocks();
    const sonner = await import("sonner");

    toastErrorSpy = vi.spyOn(sonner.toast, "error").mockImplementation(() => "t1");
    worklistStore.selectAll([2]);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    worklistStore.clearBulk();
  });

  it("shows toast.error when mark-reviewed fails", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(
          new Response(JSON.stringify({ detail: "Server error" }), { status: 500 }),
        ),
    );
    renderWithQuery(<BulkActions projectId="p1" pageIndex={0} />);
    await user.click(screen.getByTestId("bulk-actions-mark-reviewed"));
    await vi.waitFor(() => expect(toastErrorSpy).toHaveBeenCalled());
  });

  it("shows toast.error when re-run-match fails", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(
          new Response(JSON.stringify({ detail: "Server error" }), { status: 503 }),
        ),
    );
    renderWithQuery(<BulkActions projectId="p1" pageIndex={0} />);
    await user.click(screen.getByTestId("bulk-actions-rerun-match"));
    await vi.waitFor(() => expect(toastErrorSpy).toHaveBeenCalled());
  });

  it("shows toast.error when export fails", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(
          new Response(JSON.stringify({ detail: "Server error" }), { status: 500 }),
        ),
    );
    renderWithQuery(<BulkActions projectId="p1" pageIndex={0} />);
    await user.click(screen.getByTestId("bulk-actions-export"));
    await vi.waitFor(() => expect(toastErrorSpy).toHaveBeenCalled());
  });
});

describe("worklist-store bulk helpers (Slice 23)", () => {
  beforeEach(() => {
    worklistStore.reset();
  });

  it("selectAll sets selectedIds", () => {
    worklistStore.selectAll([1, 2, 3]);
    expect(worklistStore.getState().selectedIds).toEqual([1, 2, 3]);
  });

  it("clearBulk empties selectedIds", () => {
    worklistStore.selectAll([1, 2]);
    worklistStore.clearBulk();
    expect(worklistStore.getState().selectedIds).toHaveLength(0);
  });

  it("toggle adds a new id", () => {
    worklistStore.toggle(5);
    expect(worklistStore.getState().selectedIds).toContain(5);
  });

  it("toggle removes an existing id", () => {
    worklistStore.selectAll([3, 5, 7]);
    worklistStore.toggle(5);
    expect(worklistStore.getState().selectedIds).not.toContain(5);
    expect(worklistStore.getState().selectedIds).toContain(3);
    expect(worklistStore.getState().selectedIds).toContain(7);
  });
});

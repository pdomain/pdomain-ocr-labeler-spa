// BusyOverlay.test.tsx — unit tests for BusyOverlay and ProjectLoadingOverlay.
// Covers: B-JOBS-003
// Spec: docs/specs/2026-05-12-notifications-design.md §BusyOverlay logic
// Issue #232
//
// After pdui Slice 1 migration (2026-06-16):
//   - BusyOverlay and ProjectLoadingOverlay are thin wrappers that keep their
//     own data-testid roots (required by driver contract + ProjectPage.test.tsx
//     containment assertion). BlockingOperationOverlay from pdui uses Radix
//     Dialog Portal (escapes to document.body) so cannot carry the testid;
//     instead, the wrapper div carries data-testid and the inner card uses
//     OperationStatusPanel from @pdomain/pdomain-ui/status.
//   - Cancel button logic (cancellable / best-effort) is preserved; cancel
//     button rendered via OperationStatusPanel.primaryAction.

import { describe, it, expect } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { BusyOverlay, ProjectLoadingOverlay } from "./BusyOverlay";

describe("BusyOverlay", () => {
  it("is NOT visible when no mutations are running and no active job", () => {
    const { container } = render(
      <QueryClientProvider client={new QueryClient()}>
        <BusyOverlay activeJob={null} />
      </QueryClientProvider>,
    );
    const overlay = container.querySelector("[data-testid='busy-overlay']");
    expect(overlay).toBeNull();
  });

  it("IS visible when activeJob is running", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <BusyOverlay
          activeJob={{
            id: "job-1",
            type: "reload_ocr",
            project_id: "proj-1",
            status: "running",
            progress: { current: 0, total: 0, message: "Running OCR…" },
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          }}
        />
      </QueryClientProvider>,
    );
    expect(screen.getByTestId("busy-overlay")).toBeInTheDocument();
  });

  it("shows cancel button for save_project job", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <BusyOverlay
          activeJob={{
            id: "job-2",
            type: "save_project",
            project_id: "proj-1",
            status: "running",
            progress: { current: 0, total: 0, message: "Saving…" },
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          }}
        />
      </QueryClientProvider>,
    );
    expect(screen.getByTestId("busy-overlay-cancel")).toBeInTheDocument();
  });

  it("shows cancel button for export job", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <BusyOverlay
          activeJob={{
            id: "job-3",
            type: "export",
            project_id: "proj-1",
            status: "running",
            progress: { current: 0, total: 0, message: "Exporting…" },
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          }}
        />
      </QueryClientProvider>,
    );
    expect(screen.getByTestId("busy-overlay-cancel")).toBeInTheDocument();
  });

  it("shows cancel button for auto_rotate_all job", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <BusyOverlay
          activeJob={{
            id: "job-6",
            type: "auto_rotate_all",
            project_id: "proj-1",
            status: "running",
            progress: { current: 0, total: 0, message: "Rotating…" },
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          }}
        />
      </QueryClientProvider>,
    );
    expect(screen.getByTestId("busy-overlay-cancel")).toBeInTheDocument();
  });

  it("shows cancel button for propose_page_kinds job", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <BusyOverlay
          activeJob={{
            id: "job-7",
            type: "propose_page_kinds",
            project_id: "proj-1",
            status: "running",
            progress: { current: 0, total: 0, message: "Measuring…" },
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          }}
        />
      </QueryClientProvider>,
    );
    expect(screen.getByTestId("busy-overlay-cancel")).toBeInTheDocument();
  });

  it("shows cancel button for propose_regions job", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <BusyOverlay
          activeJob={{
            id: "job-8",
            type: "propose_regions",
            project_id: "proj-1",
            status: "running",
            progress: { current: 0, total: 0, message: "Proposing…" },
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          }}
        />
      </QueryClientProvider>,
    );
    expect(screen.getByTestId("busy-overlay-cancel")).toBeInTheDocument();
  });

  it("shows cancel button with best-effort tooltip for reload_ocr", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <BusyOverlay
          activeJob={{
            id: "job-4",
            type: "reload_ocr",
            project_id: "proj-1",
            status: "running",
            progress: { current: 0, total: 0, message: "Reloading OCR…" },
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          }}
        />
      </QueryClientProvider>,
    );
    const cancelBtn = screen.getByTestId("busy-overlay-cancel");
    expect(cancelBtn).toBeInTheDocument();
    // best-effort marker
    expect(cancelBtn).toHaveAttribute("title");
    expect(cancelBtn.getAttribute("title")).toMatch(/best.effort/i);
  });

  it("does NOT show cancel button for refine_bboxes job", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <BusyOverlay
          activeJob={{
            id: "job-5",
            type: "refine_bboxes",
            project_id: "proj-1",
            status: "running",
            progress: { current: 0, total: 0, message: "Refining…" },
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          }}
        />
      </QueryClientProvider>,
    );
    // No cancel button for non-cancellable jobs (without best-effort override)
    expect(screen.queryByTestId("busy-overlay-cancel")).toBeNull();
  });

  // useCancelJob.ts: BusyOverlay and the PageActionsCompact book-scoped run
  // toasts now share one POST /api/jobs/{jobId}/cancel call site.
  it("clicking Cancel POSTs to /api/jobs/{jobId}/cancel with the active job's id", async () => {
    let hits = 0;
    let path: string | undefined;
    server.use(
      http.post("/api/jobs/:jobId/cancel", ({ request }) => {
        hits += 1;
        path = new URL(request.url).pathname;
        return HttpResponse.json({ job_id: "job-2", status: "cancelled" });
      }),
    );

    render(
      <QueryClientProvider client={new QueryClient()}>
        <BusyOverlay
          activeJob={{
            id: "job-2",
            type: "save_project",
            project_id: "proj-1",
            status: "running",
            progress: { current: 0, total: 0, message: "Saving…" },
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          }}
        />
      </QueryClientProvider>,
    );

    fireEvent.click(screen.getByTestId("busy-overlay-cancel"));

    await waitFor(() => expect(hits).toBe(1));
    expect(path).toBe("/api/jobs/job-2/cancel");
  });

  it("IS visible when isMutating prop is true", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <BusyOverlay activeJob={null} isMutating />
      </QueryClientProvider>,
    );
    expect(screen.getByTestId("busy-overlay")).toBeInTheDocument();
  });

  it("renders data-testid='busy-overlay' with pdui OperationStatusPanel inner content", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <BusyOverlay activeJob={null} isMutating />
      </QueryClientProvider>,
    );
    // Outer wrapper must carry data-testid (driver contract + DOM containment in ProjectPage.test.tsx)
    expect(screen.getByTestId("busy-overlay")).toBeInTheDocument();
    // Inner content rendered via OperationStatusPanel; data-state="running" appears inside overlay
    const overlay = screen.getByTestId("busy-overlay");
    expect(overlay.querySelector("[data-state='running']")).toBeInTheDocument();
  });
});

describe("ProjectLoadingOverlay", () => {
  it("is NOT visible when isLoading is false", () => {
    const { container } = render(
      <QueryClientProvider client={new QueryClient()}>
        <ProjectLoadingOverlay isLoading={false} />
      </QueryClientProvider>,
    );
    expect(container.querySelector("[data-testid='project-loading-overlay']")).toBeNull();
  });

  it("IS visible when isLoading is true", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <ProjectLoadingOverlay isLoading />
      </QueryClientProvider>,
    );
    expect(screen.getByTestId("project-loading-overlay")).toBeInTheDocument();
  });

  it("renders data-testid='project-loading-overlay' with pdui OperationStatusPanel inner content", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <ProjectLoadingOverlay isLoading />
      </QueryClientProvider>,
    );
    const overlay = screen.getByTestId("project-loading-overlay");
    // Inner content rendered via OperationStatusPanel; data-state="running" appears inside overlay
    expect(overlay.querySelector("[data-state='running']")).toBeInTheDocument();
  });
});

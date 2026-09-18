// JobsSurface.test.tsx — tests through the REAL pdomain-ui JobsPill /
// UtilityDockContext (unmocked), proving the actual `onClick` →
// `useUtilityDock().toggle('jobs')` wiring the installed package documents,
// and the real useJobsList → jobsMapping → AppShellJobsProps pipeline.
//
// Spec: docs/plans/2026-07-21-pgdp-alignment-remaining.md item 4.

import React from "react";
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import {
  UtilityDockContext,
  JobsPanelBody,
  type UtilityDockContextValue,
} from "@pdomain/pdomain-ui/shell";
import { server } from "../../test/server";
import { JobsIndicator, useJobsShellProps } from "./JobsSurface";
import { toJobRowJobs } from "../../lib/jobsMapping";
import type { JobsListJob } from "../../hooks/useJobsList";

function makeJob(overrides: Partial<JobsListJob>): JobsListJob {
  return {
    id: "job-1",
    type: "export",
    project_id: "proj-1",
    status: "running",
    progress: { current: 1, total: 4, message: "Exporting page 1 of 4" },
    error_message: null,
    created_at: "2026-09-18T00:00:00Z",
    updated_at: "2026-09-18T00:00:00Z",
    result: null,
    ...overrides,
  };
}

function makeDockValue(overrides: Partial<UtilityDockContextValue> = {}): UtilityDockContextValue {
  return {
    active: null,
    pinned: false,
    width: 320,
    open: vi.fn(),
    close: vi.fn(),
    toggle: vi.fn(),
    setPinned: vi.fn(),
    setWidth: vi.fn(),
    ...overrides,
  };
}

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={qc}>
        <MemoryRouter>{children}</MemoryRouter>
      </QueryClientProvider>
    );
  };
}

afterEach(() => {
  server.resetHandlers();
});

describe("JobsIndicator", () => {
  it("clicking the pill toggles the real UtilityDock's jobs surface", () => {
    const dock = makeDockValue();
    render(
      <UtilityDockContext.Provider value={dock}>
        <JobsIndicator activeJobs={[]} />
      </UtilityDockContext.Provider>,
    );

    fireEvent.click(screen.getByRole("button"));

    expect(dock.toggle).toHaveBeenCalledWith("jobs");
  });

  it("is wrapped in data-testid=jobs-pill for driver-contract access", () => {
    render(
      <UtilityDockContext.Provider value={makeDockValue()}>
        <JobsIndicator activeJobs={[]} />
      </UtilityDockContext.Provider>,
    );

    expect(screen.getByTestId("jobs-pill")).toBeInTheDocument();
  });
});

describe("useJobsShellProps", () => {
  it("shellJobsProps.activeJobs carries a cancelled job through as cancelled, not failed", async () => {
    server.use(http.get("/api/jobs", () => HttpResponse.json([makeJob({ status: "cancelled" })])));

    const { result } = renderHook(() => useJobsShellProps(), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.shellJobsProps.activeJobs).toHaveLength(1));
    expect(result.current.shellJobsProps.activeJobs?.[0]?.status).toBe("cancelled");
  });

  it("pillActiveJobs excludes a completed job — the pill must look idle once nothing is running", async () => {
    server.use(http.get("/api/jobs", () => HttpResponse.json([makeJob({ status: "complete" })])));

    const { result } = renderHook(() => useJobsShellProps(), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.shellJobsProps.activeJobs).toHaveLength(1));
    expect(result.current.pillActiveJobs).toEqual([]);
  });

  it("onJobCancel posts to the shared cancel endpoint", async () => {
    let cancelHits = 0;
    server.use(
      http.get("/api/jobs", () => HttpResponse.json([makeJob({ status: "running" })])),
      http.post("/api/jobs/:jobId/cancel", () => {
        cancelHits += 1;
        return HttpResponse.json({});
      }),
    );

    const { result } = renderHook(() => useJobsShellProps(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.shellJobsProps.activeJobs).toHaveLength(1));

    result.current.shellJobsProps.onJobCancel?.("job-1");

    await waitFor(() => expect(cancelHits).toBe(1));
  });

  it("every row is pausable: false — this backend has no pause/resume concept", async () => {
    server.use(http.get("/api/jobs", () => HttpResponse.json([makeJob({ status: "running" })])));

    const { result } = renderHook(() => useJobsShellProps(), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.shellJobsProps.activeJobs).toHaveLength(1));
    expect(result.current.shellJobsProps.activeJobs?.[0]?.pausable).toBe(false);
  });

  it("omits onJobDelete and onViewAll — neither capability exists on this backend", async () => {
    server.use(http.get("/api/jobs", () => HttpResponse.json([])));

    const { result } = renderHook(() => useJobsShellProps(), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.shellJobsProps.activeJobs).toEqual([]));
    expect(result.current.shellJobsProps.onJobDelete).toBeUndefined();
    expect(result.current.shellJobsProps.onViewAll).toBeUndefined();
  });
});

describe("mapped jobs render honestly through the real pdomain-ui JobsPanelBody", () => {
  it("a cancelled job renders job-row-status-cancelled, not -failed", () => {
    const jobs = toJobRowJobs([makeJob({ id: "job-c", status: "cancelled" })]);
    render(<JobsPanelBody activeJobs={jobs} />);

    expect(screen.getByTestId("job-row-status-cancelled")).toBeInTheDocument();
    expect(screen.queryByTestId("job-row-status-failed")).toBeNull();
    expect(screen.getByText("Cancelled")).toBeInTheDocument();
  });

  it("a failed job renders job-row-status-failed, not -cancelled", () => {
    const jobs = toJobRowJobs([makeJob({ id: "job-f", status: "error", error_message: "boom" })]);
    render(<JobsPanelBody activeJobs={jobs} />);

    expect(screen.getByTestId("job-row-status-failed")).toBeInTheDocument();
    expect(screen.queryByTestId("job-row-status-cancelled")).toBeNull();
    expect(screen.getByText("Failed")).toBeInTheDocument();
  });

  it("an empty job list renders the empty state, not a stale last job", () => {
    render(<JobsPanelBody activeJobs={[]} />);

    expect(screen.getByText(/No active jobs/)).toBeInTheDocument();
    expect(screen.queryByTestId("job-row")).toBeNull();
  });
});

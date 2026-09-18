// useJobsList.test.tsx — unit tests for the shared GET /api/jobs cache entry.
//
// Spec: docs/plans/2026-07-21-pgdp-alignment-remaining.md item 4.
//
// Covers:
//   - fetches GET /api/jobs and sorts by updated_at, most recent first
//   - computeRefetchInterval: polls only while a queued/running job exists
//   - a jobsBus signal triggers a refetch (debounced)

import React from "react";
import { describe, it, expect, afterEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { useJobsList, computeRefetchInterval, type JobsListJob } from "./useJobsList";
import { notifyJobsBus } from "../lib/jobsBus";

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

function makeJob(overrides: Partial<JobsListJob>): JobsListJob {
  return {
    id: "job-1",
    type: "export",
    project_id: "proj-1",
    status: "running",
    progress: { current: 1, total: 2, message: "Working" },
    error_message: null,
    created_at: "2026-09-18T00:00:00Z",
    updated_at: "2026-09-18T00:00:00Z",
    result: null,
    ...overrides,
  };
}

describe("useJobsList", () => {
  afterEach(() => {
    server.resetHandlers();
  });

  it("fetches GET /api/jobs and sorts by updated_at, most recent first", async () => {
    const older = makeJob({ id: "job-older", updated_at: "2026-09-18T00:00:00Z" });
    const newer = makeJob({ id: "job-newer", updated_at: "2026-09-18T01:00:00Z" });
    server.use(http.get("/api/jobs", () => HttpResponse.json([older, newer])));

    const { result } = renderHook(() => useJobsList(), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.jobs.map((j) => j.id)).toEqual(["job-newer", "job-older"]);
  });

  it("returns an empty list when the backend has no jobs", async () => {
    server.use(http.get("/api/jobs", () => HttpResponse.json([])));

    const { result } = renderHook(() => useJobsList(), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.jobs).toEqual([]);
  });

  it("refetches once (debounced) when jobsBus is notified", async () => {
    let hits = 0;
    server.use(
      http.get("/api/jobs", () => {
        hits += 1;
        return HttpResponse.json([]);
      }),
    );

    renderHook(() => useJobsList(), { wrapper: makeWrapper() });
    await waitFor(() => expect(hits).toBe(1));

    notifyJobsBus();
    notifyJobsBus();
    notifyJobsBus();

    await waitFor(() => expect(hits).toBe(2));
    // Three rapid signals coalesce into one extra fetch, not three.
    expect(hits).toBe(2);
  });
});

describe("computeRefetchInterval", () => {
  it("returns false (no polling) when the list is undefined (not yet fetched)", () => {
    expect(computeRefetchInterval(undefined)).toBe(false);
  });

  it("returns false (no polling) when no job is queued or running", () => {
    const jobs = [makeJob({ status: "complete" }), makeJob({ id: "job-2", status: "cancelled" })];
    expect(computeRefetchInterval(jobs)).toBe(false);
  });

  it("polls when at least one job is queued", () => {
    const jobs = [makeJob({ status: "queued" })];
    expect(computeRefetchInterval(jobs)).toBeGreaterThan(0);
  });

  it("polls when at least one job is running", () => {
    const jobs = [makeJob({ status: "complete" }), makeJob({ id: "job-2", status: "running" })];
    expect(computeRefetchInterval(jobs)).toBeGreaterThan(0);
  });
});

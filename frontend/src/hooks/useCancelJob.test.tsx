// useCancelJob.test.tsx — unit tests for the shared cooperative-cancel POST.
//
// Plan: docs/plans/2026-09-17-region-review-surface.md — P1-CANCEL
// reachability half.
//
// Covers:
//   - cancel(jobId) POSTs to /api/jobs/{jobId}/cancel
//   - a second cancel(jobId) for the same job id sends no second request
//   - wasRequested(jobId) reflects that guard

import React from "react";
import { describe, it, expect } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { useCancelJob } from "./useCancelJob";

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

describe("useCancelJob", () => {
  it("POSTs to /api/jobs/{jobId}/cancel", async () => {
    let hits = 0;
    let path: string | undefined;
    let method: string | undefined;
    server.use(
      http.post("/api/jobs/:jobId/cancel", ({ request, params }) => {
        hits += 1;
        method = request.method;
        path = new URL(request.url).pathname;
        return HttpResponse.json({ job_id: params.jobId, status: "cancelled" });
      }),
    );

    const { result } = renderHook(() => useCancelJob(), { wrapper: makeWrapper() });

    act(() => {
      result.current.cancel("job-1");
    });

    await waitFor(() => expect(hits).toBe(1));
    expect(method).toBe("POST");
    expect(path).toBe("/api/jobs/job-1/cancel");
  });

  it("sends only one request when cancel() is called twice for the same job id", async () => {
    let hits = 0;
    server.use(
      http.post("/api/jobs/:jobId/cancel", () => {
        hits += 1;
        return HttpResponse.json({ job_id: "job-1", status: "cancelled" });
      }),
    );

    const { result } = renderHook(() => useCancelJob(), { wrapper: makeWrapper() });

    act(() => {
      result.current.cancel("job-1");
      result.current.cancel("job-1");
    });

    await waitFor(() => expect(result.current.mutation.isSuccess).toBe(true));
    expect(hits).toBe(1);
  });

  it("wasRequested reflects whether cancel() has fired for a job id", async () => {
    server.use(
      http.post("/api/jobs/:jobId/cancel", () =>
        HttpResponse.json({ job_id: "job-1", status: "cancelled" }),
      ),
    );

    const { result } = renderHook(() => useCancelJob(), { wrapper: makeWrapper() });

    expect(result.current.wasRequested("job-1")).toBe(false);

    act(() => {
      result.current.cancel("job-1");
    });

    expect(result.current.wasRequested("job-1")).toBe(true);
    // A different job id is unaffected by another job's cancel request.
    expect(result.current.wasRequested("job-2")).toBe(false);

    await waitFor(() => expect(result.current.mutation.isSuccess).toBe(true));
  });
});

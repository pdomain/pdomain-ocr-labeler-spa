// useProposalRuns.test.tsx — unit tests for the page-kind and region proposal
// run hooks.
// Spec: docs/specs/2026-09-17-region-review-surface-design.md
// Plan: docs/plans/2026-09-17-region-review-surface.md — Task 3
//
// Covers:
//   - useProposePageKinds: POST .../propose-page-kinds, no body, 202 + job_id
//   - useProposeRegions: POST .../regions/propose, body {}, 202 + job_id
//
// Neither hook invalidates any query itself — Task 6's job-completion handler
// invalidates once the run actually finishes.

import React from "react";
import { describe, it, expect, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { useProposePageKinds, useProposeRegions } from "./useProposalRuns";

const PROJECT_ID = "proj1";

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

function makeWrapper(qc: QueryClient) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

describe("useProposePageKinds", () => {
  it("POSTs to propose-page-kinds with no body and returns the job id", async () => {
    let method: string | undefined;
    let path: string | undefined;
    let bodyText: string;
    server.use(
      http.post("/api/projects/:pid/propose-page-kinds", async ({ request }) => {
        method = request.method;
        path = new URL(request.url).pathname;
        bodyText = await request.text();
        return HttpResponse.json({ job_id: "job-1" }, { status: 202 });
      }),
    );
    const qc = makeQueryClient();
    const { result } = renderHook(() => useProposePageKinds(PROJECT_ID), {
      wrapper: makeWrapper(qc),
    });

    act(() => {
      result.current.mutate();
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(method).toBe("POST");
    expect(path).toBe(`/api/projects/${PROJECT_ID}/propose-page-kinds`);
    expect(bodyText!).toBe("");
    expect(result.current.data).toEqual({ job_id: "job-1" });
  });

  it("does not invalidate any query on success", async () => {
    server.use(
      http.post("/api/projects/:pid/propose-page-kinds", () =>
        HttpResponse.json({ job_id: "job-1" }, { status: 202 }),
      ),
    );
    const qc = makeQueryClient();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useProposePageKinds(PROJECT_ID), {
      wrapper: makeWrapper(qc),
    });

    act(() => {
      result.current.mutate();
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidateSpy).not.toHaveBeenCalled();
  });
});

describe("useProposeRegions", () => {
  it("POSTs {} to regions/propose and returns the job id", async () => {
    let method: string | undefined;
    let path: string | undefined;
    let body: unknown;
    server.use(
      http.post("/api/projects/:pid/regions/propose", async ({ request }) => {
        method = request.method;
        path = new URL(request.url).pathname;
        body = await request.json();
        return HttpResponse.json({ job_id: "job-2" }, { status: 202 });
      }),
    );
    const qc = makeQueryClient();
    const { result } = renderHook(() => useProposeRegions(PROJECT_ID), {
      wrapper: makeWrapper(qc),
    });

    act(() => {
      result.current.mutate();
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(method).toBe("POST");
    expect(path).toBe(`/api/projects/${PROJECT_ID}/regions/propose`);
    expect(body).toEqual({});
    expect(result.current.data).toEqual({ job_id: "job-2" });
  });

  it("does not invalidate any query on success", async () => {
    server.use(
      http.post("/api/projects/:pid/regions/propose", () =>
        HttpResponse.json({ job_id: "job-2" }, { status: 202 }),
      ),
    );
    const qc = makeQueryClient();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useProposeRegions(PROJECT_ID), {
      wrapper: makeWrapper(qc),
    });

    act(() => {
      result.current.mutate();
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidateSpy).not.toHaveBeenCalled();
  });
});

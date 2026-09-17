// useRegionMutations.test.tsx — unit tests for region review mutation hooks.
// Spec: docs/specs/2026-09-17-region-review-surface-design.md
// Plan: docs/plans/2026-09-17-region-review-surface.md — Task 3
//
// Covers:
//   - useAcceptProposal: POST .../regions/proposals/{id}/accept, body {} or { role }
//   - useRejectProposal: POST .../regions/proposals/{id}/reject, no body
//   - useEditRegion: PATCH .../regions/{id}, body { role }
//   - useDeleteRegion: DELETE .../regions/{id}, no body
//
// Every mutation invalidates ["page", projectId, pageIndex] on success and
// never writes the cache — the routes return a full PagePayload, which this
// suite deliberately does not feed to setQueryData.

import React from "react";
import { describe, it, expect, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import {
  useAcceptProposal,
  useRejectProposal,
  useEditRegion,
  useDeleteRegion,
} from "./useRegionMutations";

const PROJECT_ID = "proj1";
const PAGE_IDX = 4;

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

describe("useAcceptProposal", () => {
  it("POSTs exactly {} to the accept route with no role override", async () => {
    let method: string | undefined;
    let path: string | undefined;
    let body: unknown;
    server.use(
      http.post(
        "/api/projects/:pid/pages/:idx/regions/proposals/:proposalId/accept",
        async ({ request }) => {
          method = request.method;
          path = new URL(request.url).pathname;
          body = await request.json();
          return HttpResponse.json({
            project_id: PROJECT_ID,
            page_index: PAGE_IDX,
            line_matches: [],
          });
        },
      ),
    );
    const qc = makeQueryClient();
    const { result } = renderHook(() => useAcceptProposal(PROJECT_ID, PAGE_IDX), {
      wrapper: makeWrapper(qc),
    });

    await act(() => result.current.mutateAsync({ proposalId: "prop-1" }));

    expect(method).toBe("POST");
    expect(path).toBe(
      `/api/projects/${PROJECT_ID}/pages/${PAGE_IDX}/regions/proposals/prop-1/accept`,
    );
    expect(body).toEqual({});
  });

  it("POSTs exactly { role } to the accept route when a role override is given", async () => {
    let body: unknown;
    server.use(
      http.post(
        "/api/projects/:pid/pages/:idx/regions/proposals/:proposalId/accept",
        async ({ request }) => {
          body = await request.json();
          return HttpResponse.json({
            project_id: PROJECT_ID,
            page_index: PAGE_IDX,
            line_matches: [],
          });
        },
      ),
    );
    const qc = makeQueryClient();
    const { result } = renderHook(() => useAcceptProposal(PROJECT_ID, PAGE_IDX), {
      wrapper: makeWrapper(qc),
    });

    await act(() => result.current.mutateAsync({ proposalId: "prop-1", role: "page number" }));

    expect(body).toEqual({ role: "page number" });
  });

  it("invalidates the page query on success", async () => {
    server.use(
      http.post("/api/projects/:pid/pages/:idx/regions/proposals/:proposalId/accept", () =>
        HttpResponse.json({ project_id: PROJECT_ID, page_index: PAGE_IDX, line_matches: [] }),
      ),
    );
    const qc = makeQueryClient();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useAcceptProposal(PROJECT_ID, PAGE_IDX), {
      wrapper: makeWrapper(qc),
    });

    await act(() => result.current.mutateAsync({ proposalId: "prop-1" }));

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["page", PROJECT_ID, PAGE_IDX] });
  });
});

describe("useRejectProposal", () => {
  it("POSTs to the reject route and invalidates the page query", async () => {
    let method: string | undefined;
    let path: string | undefined;
    server.use(
      http.post(
        "/api/projects/:pid/pages/:idx/regions/proposals/:proposalId/reject",
        ({ request }) => {
          method = request.method;
          path = new URL(request.url).pathname;
          return HttpResponse.json({
            project_id: PROJECT_ID,
            page_index: PAGE_IDX,
            line_matches: [],
          });
        },
      ),
    );
    const qc = makeQueryClient();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useRejectProposal(PROJECT_ID, PAGE_IDX), {
      wrapper: makeWrapper(qc),
    });

    await act(() => result.current.mutateAsync({ proposalId: "prop-1" }));

    expect(method).toBe("POST");
    expect(path).toBe(
      `/api/projects/${PROJECT_ID}/pages/${PAGE_IDX}/regions/proposals/prop-1/reject`,
    );
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["page", PROJECT_ID, PAGE_IDX] });
  });
});

describe("useEditRegion", () => {
  it("PATCHes the region route with { role } and invalidates the page query", async () => {
    let method: string | undefined;
    let path: string | undefined;
    let body: unknown;
    server.use(
      http.patch("/api/projects/:pid/pages/:idx/regions/:regionId", async ({ request }) => {
        method = request.method;
        path = new URL(request.url).pathname;
        body = await request.json();
        return HttpResponse.json({
          project_id: PROJECT_ID,
          page_index: PAGE_IDX,
          line_matches: [],
        });
      }),
    );
    const qc = makeQueryClient();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useEditRegion(PROJECT_ID, PAGE_IDX), {
      wrapper: makeWrapper(qc),
    });

    await act(() => result.current.mutateAsync({ regionId: "region-1", role: "paragraph" }));

    expect(method).toBe("PATCH");
    expect(path).toBe(`/api/projects/${PROJECT_ID}/pages/${PAGE_IDX}/regions/region-1`);
    expect(body).toEqual({ role: "paragraph" });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["page", PROJECT_ID, PAGE_IDX] });
  });
});

describe("useDeleteRegion", () => {
  it("DELETEs the region route and invalidates the page query", async () => {
    let method: string | undefined;
    let path: string | undefined;
    server.use(
      http.delete("/api/projects/:pid/pages/:idx/regions/:regionId", ({ request }) => {
        method = request.method;
        path = new URL(request.url).pathname;
        return HttpResponse.json({
          project_id: PROJECT_ID,
          page_index: PAGE_IDX,
          line_matches: [],
        });
      }),
    );
    const qc = makeQueryClient();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useDeleteRegion(PROJECT_ID, PAGE_IDX), {
      wrapper: makeWrapper(qc),
    });

    await act(() => result.current.mutateAsync({ regionId: "region-1" }));

    expect(method).toBe("DELETE");
    expect(path).toBe(`/api/projects/${PROJECT_ID}/pages/${PAGE_IDX}/regions/region-1`);
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["page", PROJECT_ID, PAGE_IDX] });
  });
});

// useReviewQueue.test.tsx — unit tests for the review-queue TanStack Query hook.
// Spec: docs/specs/2026-09-17-book-review-queue-design.md
//   "One route answers the question for people and agents alike"

import React from "react";
import { describe, it, expect } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { useReviewQueue } from "./useReviewQueue";

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

describe("useReviewQueue", () => {
  it("fetches with the default order=reading and limit=0", async () => {
    let requestUrl: string | undefined;
    server.use(
      http.get("/api/projects/:pid/regions/review-queue", ({ request }) => {
        requestUrl = request.url;
        return HttpResponse.json({ total_undecided: 3, pages: [], items: [] });
      }),
    );

    const { result } = renderHook(() => useReviewQueue("proj-1"), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.total_undecided).toBe(3);
    const parsed = new URL(requestUrl ?? "");
    expect(parsed.pathname).toBe("/api/projects/proj-1/regions/review-queue");
    expect(parsed.searchParams.get("order")).toBe("reading");
    expect(parsed.searchParams.get("limit")).toBe("0");
  });

  it("passes a custom order and limit through as query params", async () => {
    let requestUrl: string | undefined;
    server.use(
      http.get("/api/projects/:pid/regions/review-queue", ({ request }) => {
        requestUrl = request.url;
        return HttpResponse.json({ total_undecided: 0, pages: [], items: [] });
      }),
    );

    const { result } = renderHook(
      () => useReviewQueue("proj-1", { order: "confidence", limit: 25 }),
      { wrapper: makeWrapper() },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const parsed = new URL(requestUrl ?? "");
    expect(parsed.searchParams.get("order")).toBe("confidence");
    expect(parsed.searchParams.get("limit")).toBe("25");
  });

  it("is disabled when projectId is undefined", () => {
    const { result } = renderHook(() => useReviewQueue(undefined), { wrapper: makeWrapper() });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is disabled when projectId is an empty string", () => {
    const { result } = renderHook(() => useReviewQueue(""), { wrapper: makeWrapper() });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("keys the cache by projectId, order and limit", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    server.use(
      http.get("/api/projects/:pid/regions/review-queue", () =>
        HttpResponse.json({ total_undecided: 7, pages: [], items: [] }),
      ),
    );
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );

    const { result } = renderHook(() => useReviewQueue("proj-1"), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const cached = qc.getQueryData(["review-queue", "proj-1", "reading", 0]);
    expect(cached).toEqual({ total_undecided: 7, pages: [], items: [] });
  });
});

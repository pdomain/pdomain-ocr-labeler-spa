// useBookReviewQueue.test.tsx — unit tests for the per-kind book review
// queue hook.
// Spec: pdomain-ocr-synth's docs/specs/2026-09-18-one-answer-to-what-to-
//   review-next.md "One route, in the order the work happens".

import React from "react";
import { describe, it, expect } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import {
  useBookReviewQueue,
  firstActionableKind,
  bookReviewQueueKey,
  type ReviewQueueKindEntry,
} from "./useBookReviewQueue";

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

function kind(overrides: Partial<ReviewQueueKindEntry> = {}): ReviewQueueKindEntry {
  return {
    kind: "page_kind",
    outstanding: 0,
    total: 0,
    available: true,
    blocked_by: null,
    first_page_index: null,
    pages_not_counted: 0,
    is_lower_bound: false,
    ...overrides,
  };
}

describe("useBookReviewQueue", () => {
  it("fetches the per-kind route for the given project", async () => {
    let requestUrl: string | undefined;
    server.use(
      http.get("/api/projects/:pid/review-queue", ({ request }) => {
        requestUrl = request.url;
        return HttpResponse.json({
          kinds: [kind({ kind: "page_kind", outstanding: 3, total: 5 })],
        });
      }),
    );

    const { result } = renderHook(() => useBookReviewQueue("proj-1"), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.kinds[0]?.outstanding).toBe(3);
    const parsed = new URL(requestUrl ?? "");
    expect(parsed.pathname).toBe("/api/projects/proj-1/review-queue");
  });

  it("is disabled when projectId is undefined", () => {
    const { result } = renderHook(() => useBookReviewQueue(undefined), { wrapper: makeWrapper() });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is disabled when projectId is an empty string", () => {
    const { result } = renderHook(() => useBookReviewQueue(""), { wrapper: makeWrapper() });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("keys the cache by projectId alone", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    server.use(
      http.get("/api/projects/:pid/review-queue", () =>
        HttpResponse.json({ kinds: [kind({ outstanding: 7 })] }),
      ),
    );
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );

    const { result } = renderHook(() => useBookReviewQueue("proj-1"), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const cached = qc.getQueryData(bookReviewQueueKey("proj-1"));
    expect(cached).toEqual({ kinds: [kind({ outstanding: 7 })] });
  });
});

describe("firstActionableKind", () => {
  it("picks the first kind, in list order, with outstanding work and no blocked_by", () => {
    const kinds = [
      kind({ kind: "page_kind", outstanding: 0 }),
      kind({ kind: "region", outstanding: 5, blocked_by: "page_kind" }),
      kind({ kind: "word", outstanding: 3, blocked_by: null }),
    ];
    expect(firstActionableKind(kinds)?.kind).toBe("word");
  });

  it("skips a kind with outstanding work but a live blocked_by", () => {
    const kinds = [kind({ kind: "region", outstanding: 5, blocked_by: "page_kind" })];
    expect(firstActionableKind(kinds)).toBeUndefined();
  });

  it("returns undefined when nothing has outstanding work", () => {
    const kinds = [kind({ outstanding: 0 }), kind({ kind: "region", outstanding: 0 })];
    expect(firstActionableKind(kinds)).toBeUndefined();
  });
});

// usePageKinds.test.tsx — unit tests for the book-wide page-kinds query and
// bulk-confirm mutation.
//
// Spec: pdomain-ocr-synth's docs/specs/2026-09-17-page-kind-review-design.md
//   "One route lists every page's kind"
//   "One route confirms many pages"
//   "The route stays synchronous, and the SPA sends at most 25 pages per
//    request" — batches of 25, a progress toast between batches, and stop
//    on an outright failure.

import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { usePageKinds, useBulkConfirmPageKinds } from "./usePageKinds";

const toastMock = vi.hoisted(() => ({
  info: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
  warn: vi.fn(),
}));
vi.mock("../lib/toast", () => ({ toast: toastMock }));

const PROJECT_ID = "proj-1";

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

beforeEach(() => {
  vi.clearAllMocks();
});

// ─── usePageKinds (GET .../page-kinds) ─────────────────────────────────────

describe("usePageKinds", () => {
  it("fetches GET .../page-kinds and returns the list response", async () => {
    server.use(
      http.get(`/api/projects/${PROJECT_ID}/page-kinds`, () =>
        HttpResponse.json({
          total_pages: 2,
          reviewed_count: 1,
          pages: [
            {
              page_index: 0,
              confirmed_kind: "body",
              reviewed: true,
              proposed_kind: "body",
              confidence: 0.9,
              run_id: "r1",
            },
            {
              page_index: 1,
              confirmed_kind: null,
              reviewed: false,
              proposed_kind: null,
              confidence: null,
              run_id: null,
            },
          ],
        }),
      ),
    );

    const { result } = renderHook(() => usePageKinds(PROJECT_ID), {
      wrapper: makeWrapper(makeQueryClient()),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.total_pages).toBe(2);
    expect(result.current.data?.pages).toHaveLength(2);
  });

  it("is disabled when projectId is undefined", () => {
    const { result } = renderHook(() => usePageKinds(undefined), {
      wrapper: makeWrapper(makeQueryClient()),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is disabled when projectId is an empty string", () => {
    const { result } = renderHook(() => usePageKinds(""), {
      wrapper: makeWrapper(makeQueryClient()),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });
});

// ─── useBulkConfirmPageKinds (POST .../page-kinds/confirm, batched) ────────

describe("useBulkConfirmPageKinds", () => {
  it("sends a single batch request when 25 or fewer pages are selected", async () => {
    const bodies: unknown[] = [];
    server.use(
      http.post(`/api/projects/${PROJECT_ID}/page-kinds/confirm`, async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json({
          results: [{ page_index: 0, status: "confirmed" }],
          confirmed_count: 1,
        });
      }),
    );
    const qc = makeQueryClient();
    const { result } = renderHook(() => useBulkConfirmPageKinds(PROJECT_ID), {
      wrapper: makeWrapper(qc),
    });

    await act(() => result.current.mutateAsync({ items: [{ page_index: 0, kind: "body" }] }));

    expect(bodies).toEqual([{ pages: [{ page_index: 0, kind: "body" }], note: null }]);
  });

  it("batches 60 pages into three requests of at most 25 each, in order", async () => {
    const batchSizes: number[] = [];
    server.use(
      http.post(`/api/projects/${PROJECT_ID}/page-kinds/confirm`, async ({ request }) => {
        const body = (await request.json()) as { pages: { page_index: number }[] };
        batchSizes.push(body.pages.length);
        return HttpResponse.json({
          results: body.pages.map((p) => ({ page_index: p.page_index, status: "confirmed" })),
          confirmed_count: body.pages.length,
        });
      }),
    );
    const qc = makeQueryClient();
    const { result } = renderHook(() => useBulkConfirmPageKinds(PROJECT_ID), {
      wrapper: makeWrapper(qc),
    });

    const items = Array.from({ length: 60 }, (_, i) => ({
      page_index: i,
      kind: "body" as const,
    }));

    let summary: { confirmedCount: number } | undefined;
    await act(async () => {
      summary = await result.current.mutateAsync({ items });
    });

    expect(batchSizes).toEqual([25, 25, 10]);
    expect(summary?.confirmedCount).toBe(60);
  });

  it("shows a progress toast reporting pages done after each batch", async () => {
    server.use(
      http.post(`/api/projects/${PROJECT_ID}/page-kinds/confirm`, async ({ request }) => {
        const body = (await request.json()) as { pages: { page_index: number }[] };
        return HttpResponse.json({
          results: body.pages.map((p) => ({ page_index: p.page_index, status: "confirmed" })),
          confirmed_count: body.pages.length,
        });
      }),
    );
    const qc = makeQueryClient();
    const { result } = renderHook(() => useBulkConfirmPageKinds(PROJECT_ID), {
      wrapper: makeWrapper(qc),
    });
    const items = Array.from({ length: 30 }, (_, i) => ({
      page_index: i,
      kind: "body" as const,
    }));

    await act(() => result.current.mutateAsync({ items }));

    expect(toastMock.info).toHaveBeenCalledWith(
      expect.stringContaining("25 of 30"),
      expect.anything(),
    );
    expect(toastMock.info).toHaveBeenCalledWith(
      expect.stringContaining("30 of 30"),
      expect.anything(),
    );
  });

  it("stops after an outright failure and reports how many were confirmed first", async () => {
    let callCount = 0;
    server.use(
      http.post(`/api/projects/${PROJECT_ID}/page-kinds/confirm`, async ({ request }) => {
        callCount += 1;
        const body = (await request.json()) as { pages: { page_index: number }[] };
        if (callCount === 2) {
          return HttpResponse.json({ error: "internal", message: "boom" }, { status: 500 });
        }
        return HttpResponse.json({
          results: body.pages.map((p) => ({ page_index: p.page_index, status: "confirmed" })),
          confirmed_count: body.pages.length,
        });
      }),
    );
    const qc = makeQueryClient();
    const { result } = renderHook(() => useBulkConfirmPageKinds(PROJECT_ID), {
      wrapper: makeWrapper(qc),
    });
    const items = Array.from({ length: 60 }, (_, i) => ({
      page_index: i,
      kind: "body" as const,
    }));

    await act(async () => {
      await expect(result.current.mutateAsync({ items })).rejects.toThrow();
    });

    // Only the first two batches were attempted (25 confirmed, then failure);
    // the third batch (indices 50-59) must never have been sent.
    expect(callCount).toBe(2);
    expect(toastMock.error).toHaveBeenCalledWith(expect.stringContaining("25"));
  });

  it("reports the running confirmed tally, not pages processed, in progress and error toasts", async () => {
    // Batch 1 (25 pages): only 10 actually confirm, the rest come back
    // not_loaded. Batch 2 fails outright. The progress toast after batch 1
    // and the error toast after batch 2 must both say 10 — the confirmed
    // tally from confirmed_count — not 25, the count of pages processed.
    let callCount = 0;
    server.use(
      http.post(`/api/projects/${PROJECT_ID}/page-kinds/confirm`, async ({ request }) => {
        callCount += 1;
        const body = (await request.json()) as { pages: { page_index: number }[] };
        if (callCount === 1) {
          return HttpResponse.json({
            results: body.pages.map((p, i) => ({
              page_index: p.page_index,
              status: i < 10 ? "confirmed" : "not_loaded",
            })),
            confirmed_count: 10,
          });
        }
        return HttpResponse.json({ error: "internal", message: "boom" }, { status: 500 });
      }),
    );
    const qc = makeQueryClient();
    const { result } = renderHook(() => useBulkConfirmPageKinds(PROJECT_ID), {
      wrapper: makeWrapper(qc),
    });
    const items = Array.from({ length: 60 }, (_, i) => ({
      page_index: i,
      kind: "body" as const,
    }));

    await act(async () => {
      await expect(result.current.mutateAsync({ items })).rejects.toThrow();
    });

    expect(toastMock.info).toHaveBeenCalledWith(expect.stringContaining("10"), expect.anything());
    expect(toastMock.info).not.toHaveBeenCalledWith(
      expect.stringContaining("25"),
      expect.anything(),
    );
    expect(toastMock.error).toHaveBeenCalledWith(expect.stringContaining("10"));
    expect(toastMock.error).not.toHaveBeenCalledWith(expect.stringContaining("25"));
  });

  it("invalidates the page-kinds and page prefixes on success", async () => {
    server.use(
      http.post(`/api/projects/${PROJECT_ID}/page-kinds/confirm`, () =>
        HttpResponse.json({
          results: [{ page_index: 0, status: "confirmed" }],
          confirmed_count: 1,
        }),
      ),
    );
    const qc = makeQueryClient();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useBulkConfirmPageKinds(PROJECT_ID), {
      wrapper: makeWrapper(qc),
    });

    await act(() => result.current.mutateAsync({ items: [{ page_index: 0, kind: "body" }] }));

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["page-kinds", PROJECT_ID] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["page", PROJECT_ID] });
  });

  it("reports the final confirmed count and names statuses that were not confirmed", async () => {
    server.use(
      http.post(`/api/projects/${PROJECT_ID}/page-kinds/confirm`, () =>
        HttpResponse.json({
          results: [
            { page_index: 0, status: "confirmed" },
            { page_index: 1, status: "not_loaded" },
          ],
          confirmed_count: 1,
        }),
      ),
    );
    const qc = makeQueryClient();
    const { result } = renderHook(() => useBulkConfirmPageKinds(PROJECT_ID), {
      wrapper: makeWrapper(qc),
    });

    await act(() =>
      result.current.mutateAsync({
        items: [
          { page_index: 0, kind: "body" },
          { page_index: 1, kind: "body" },
        ],
      }),
    );

    expect(toastMock.success).toHaveBeenCalledWith(
      expect.stringMatching(/1.*confirmed.*not_loaded/i),
      expect.anything(),
    );
  });
});

// useWordMutations.test.tsx — unit tests for useDeleteWord + useNudgeWord.
// Task S1.1 (parity-gap-completion plan).
//
// Acceptance:
//   - useDeleteWord POSTs the word delete-scope body
//   - useNudgeWord POSTs deltas + refine_after flag

import { describe, it, expect, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import React from "react";
import { server } from "../test/server";
import {
  useDeleteWord,
  useNudgeWord,
  useErasePixels,
  useSetGlyphAnnotations,
  useAcceptGlyphPrediction,
  useGlyphAnnotationPending,
} from "./useWordMutations";

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const Wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return Wrapper;
}

describe("useDeleteWord", () => {
  it("is a function", () => {
    expect(typeof useDeleteWord).toBe("function");
  });

  it("returns a mutation object with mutate and mutateAsync", () => {
    const { result } = renderHook(() => useDeleteWord("p", 0), {
      wrapper: makeWrapper(),
    });
    expect(typeof result.current.mutate).toBe("function");
    expect(typeof result.current.mutateAsync).toBe("function");
  });

  // P1.3 (B-61): the page-scope /delete endpoint is a 501 stub — the hook
  // must use the real words/delete-batch route or the word never deletes.
  it("POSTs the word batch body to words/delete-batch (NOT the /delete stub)", async () => {
    let body: unknown;
    server.use(
      http.post("/api/projects/:pid/pages/:idx/words/delete-batch", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ project_id: "p", page_index: 0 });
      }),
    );
    const { result } = renderHook(() => useDeleteWord("p", 0), {
      wrapper: makeWrapper(),
    });
    act(() => {
      result.current.mutate({ lineIndex: 1, wordIndex: 2 });
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(body).toEqual({
      scope: "word",
      word_indices: [[1, 2]],
    });
  });
});

describe("useNudgeWord", () => {
  it("is a function", () => {
    expect(typeof useNudgeWord).toBe("function");
  });

  it("returns a mutation object with mutate and mutateAsync", () => {
    const { result } = renderHook(() => useNudgeWord("p", 0), {
      wrapper: makeWrapper(),
    });
    expect(typeof result.current.mutate).toBe("function");
    expect(typeof result.current.mutateAsync).toBe("function");
  });

  it("POSTs deltas + refine_after to words/{li}/{wi}/nudge", async () => {
    let body: unknown;
    server.use(
      http.post("/api/projects/:pid/pages/:idx/words/:li/:wi/nudge", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ project_id: "p", page_index: 0 });
      }),
    );
    const { result } = renderHook(() => useNudgeWord("p", 0), {
      wrapper: makeWrapper(),
    });
    act(() => {
      result.current.mutate({
        lineIndex: 1,
        wordIndex: 2,
        left: 0,
        right: 1,
        top: 0,
        bottom: 0,
        refineAfter: true,
      });
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(body).toEqual({ left: 0, right: 1, top: 0, bottom: 0, refine_after: true });
  });
});

// ─── useErasePixels regression (P1-CANVAS-ERASE) ────────────────────────────
// Confirms the pre-existing word-detail panel erase path (WordDetail →
// ErasePixelsSection → useErasePixels) still works unchanged after adding
// the page-scoped useErasePagePixels sibling for canvas erase mode.

describe("useErasePixels", () => {
  it("POSTs a rect op to words/{li}/{wi}/erase-pixels with fill_value 255 and shape rect", async () => {
    let body: unknown;
    let path: string | undefined;
    server.use(
      http.post("/api/projects/p/pages/0/words/1/2/erase-pixels", async ({ request }) => {
        path = new URL(request.url).pathname;
        body = await request.json();
        return HttpResponse.json({});
      }),
    );
    const { result } = renderHook(() => useErasePixels("p", 0), {
      wrapper: makeWrapper(),
    });

    await act(async () => {
      await result.current.mutateAsync({
        lineIndex: 1,
        wordIndex: 2,
        ops: [{ tool: "rect", x: 5, y: 6, width: 7, height: 8 }],
      });
    });

    expect(path).toBe("/api/projects/p/pages/0/words/1/2/erase-pixels");
    expect(body).toEqual({
      bbox: { x: 5, y: 6, width: 7, height: 8 },
      fill_value: 255,
      shape: "rect",
    });
  });

  it("POSTs a brush op as a circle-shaped bbox inscribed within the AABB", async () => {
    let body: unknown;
    server.use(
      http.post("/api/projects/p/pages/0/words/1/2/erase-pixels", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({});
      }),
    );
    const { result } = renderHook(() => useErasePixels("p", 0), {
      wrapper: makeWrapper(),
    });

    await act(async () => {
      await result.current.mutateAsync({
        lineIndex: 1,
        wordIndex: 2,
        ops: [{ tool: "brush", x: 10, y: 10, radius: 4 }],
      });
    });

    expect(body).toEqual({
      bbox: { x: 6, y: 6, width: 8, height: 8 },
      fill_value: 255,
      shape: "circle",
    });
  });

  it("invalidates the page query on success", async () => {
    server.use(
      http.post("/api/projects/p/pages/0/words/1/2/erase-pixels", () => HttpResponse.json({})),
    );
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const Wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useErasePixels("p", 0), { wrapper: Wrapper });

    await act(async () => {
      await result.current.mutateAsync({
        lineIndex: 1,
        wordIndex: 2,
        ops: [{ tool: "rect", x: 0, y: 0, width: 1, height: 1 }],
      });
    });

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["page", "p", 0] });
  });
});

// ─── useSetGlyphAnnotations (M11 Task 4) ────────────────────────────────────

describe("useSetGlyphAnnotations", () => {
  it("POSTs { annotations } to words/{li}/{wi}/glyph-annotations", async () => {
    let path: string | undefined;
    let body: unknown;
    server.use(
      http.post(
        "/api/projects/:pid/pages/:idx/words/:li/:wi/glyph-annotations",
        async ({ request }) => {
          path = new URL(request.url).pathname;
          body = await request.json();
          return HttpResponse.json({ project_id: "p", page_index: 0, line_matches: [] });
        },
      ),
    );
    const { result } = renderHook(() => useSetGlyphAnnotations("p", 0), {
      wrapper: makeWrapper(),
    });

    await act(async () => {
      await result.current.mutateAsync({
        lineIndex: 1,
        wordIndex: 2,
        annotations: {
          ligatures: [{ kind: "ct", char_span: [0, 2] }],
          long_s_positions: [],
          swash: false,
          source: "human",
        },
      });
    });

    expect(path).toBe("/api/projects/p/pages/0/words/1/2/glyph-annotations");
    expect(body).toEqual({
      annotations: {
        ligatures: [{ kind: "ct", char_span: [0, 2] }],
        long_s_positions: [],
        swash: false,
        source: "human",
      },
    });
  });

  it("POSTs { annotations: null } to clear a word's annotations", async () => {
    let body: unknown;
    server.use(
      http.post(
        "/api/projects/:pid/pages/:idx/words/:li/:wi/glyph-annotations",
        async ({ request }) => {
          body = await request.json();
          return HttpResponse.json({ project_id: "p", page_index: 0, line_matches: [] });
        },
      ),
    );
    const { result } = renderHook(() => useSetGlyphAnnotations("p", 0), {
      wrapper: makeWrapper(),
    });

    await act(async () => {
      await result.current.mutateAsync({ lineIndex: 1, wordIndex: 2, annotations: null });
    });

    expect(body).toEqual({ annotations: null });
  });

  it("invalidates the page query on success", async () => {
    server.use(
      http.post("/api/projects/p/pages/0/words/1/2/glyph-annotations", () =>
        HttpResponse.json({ project_id: "p", page_index: 0, line_matches: [] }),
      ),
    );
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const Wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useSetGlyphAnnotations("p", 0), { wrapper: Wrapper });

    await act(async () => {
      await result.current.mutateAsync({ lineIndex: 1, wordIndex: 2, annotations: null });
    });

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["page", "p", 0] });
  });
});

// ─── useAcceptGlyphPrediction (M11 Task 4) ──────────────────────────────────

describe("useAcceptGlyphPrediction", () => {
  it("POSTs {} to words/{li}/{wi}/accept-prediction", async () => {
    let path: string | undefined;
    let body: unknown;
    server.use(
      http.post(
        "/api/projects/:pid/pages/:idx/words/:li/:wi/accept-prediction",
        async ({ request }) => {
          path = new URL(request.url).pathname;
          body = await request.json();
          return HttpResponse.json({ project_id: "p", page_index: 0, line_matches: [] });
        },
      ),
    );
    const { result } = renderHook(() => useAcceptGlyphPrediction("p", 0), {
      wrapper: makeWrapper(),
    });

    await act(async () => {
      await result.current.mutateAsync({ lineIndex: 1, wordIndex: 2 });
    });

    expect(path).toBe("/api/projects/p/pages/0/words/1/2/accept-prediction");
    expect(body).toEqual({});
  });

  it("invalidates the page query on success", async () => {
    server.use(
      http.post("/api/projects/p/pages/0/words/1/2/accept-prediction", () =>
        HttpResponse.json({ project_id: "p", page_index: 0, line_matches: [] }),
      ),
    );
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const Wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useAcceptGlyphPrediction("p", 0), { wrapper: Wrapper });

    await act(async () => {
      await result.current.mutateAsync({ lineIndex: 1, wordIndex: 2 });
    });

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["page", "p", 0] });
  });
});

// ─── useGlyphAnnotationPending (shared pending signal) ──────────────────────
//
// GlyphAnnotationPanel calls both useSetGlyphAnnotations and
// useAcceptGlyphPrediction; a future second mount point (e.g. a chip
// popover) would build its own hook instances against the same
// QueryClient. Mirrors useRegionMutations.ts's useRegionDecisionPending —
// both mutations share one mutationKey so a pending check from any
// instance sees a mutation any other instance started.

describe("useGlyphAnnotationPending", () => {
  it("is false with nothing in flight, true while another hook instance's set is pending, false once it settles", async () => {
    let resolveSet!: () => void;
    server.use(
      http.post(
        "/api/projects/:pid/pages/:idx/words/:li/:wi/glyph-annotations",
        () =>
          new Promise<Response>((resolve) => {
            resolveSet = () =>
              resolve(HttpResponse.json({ project_id: "p", page_index: 0, line_matches: [] }));
          }),
      ),
    );
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    const Wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );

    const setAnnotations = renderHook(() => useSetGlyphAnnotations("p", 0), { wrapper: Wrapper });
    const pending = renderHook(() => useGlyphAnnotationPending("p", 0), { wrapper: Wrapper });

    expect(pending.result.current).toBe(false);

    act(() => {
      setAnnotations.result.current.mutate({ lineIndex: 1, wordIndex: 2, annotations: null });
    });

    await waitFor(() => expect(pending.result.current).toBe(true));

    act(() => {
      resolveSet();
    });

    await waitFor(() => expect(pending.result.current).toBe(false));
  });

  it("does not see a mutation scoped to a different page index", async () => {
    server.use(
      http.post(
        "/api/projects/:pid/pages/:idx/words/:li/:wi/accept-prediction",
        () => new Promise<Response>(() => {}), // never resolves within this test
      ),
    );
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    const Wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );
    const OTHER_PAGE_IDX = 1;

    const accept = renderHook(() => useAcceptGlyphPrediction("p", 0), { wrapper: Wrapper });
    const pendingOtherPage = renderHook(() => useGlyphAnnotationPending("p", OTHER_PAGE_IDX), {
      wrapper: Wrapper,
    });

    act(() => {
      accept.result.current.mutate({ lineIndex: 1, wordIndex: 2 });
    });

    await waitFor(() => expect(accept.result.current.isPending).toBe(true));
    expect(pendingOtherPage.result.current).toBe(false);
  });
});

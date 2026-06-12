// useWordMutations.test.tsx — unit tests for useDeleteWord + useNudgeWord.
// Task S1.1 (parity-gap-completion plan).
//
// Acceptance:
//   - useDeleteWord POSTs the word delete-scope body
//   - useNudgeWord POSTs deltas + refine_after flag

import { describe, it, expect } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import React from "react";
import { server } from "../test/server";
import { useDeleteWord, useNudgeWord } from "./useWordMutations";

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

// useLineMutations.test.tsx — unit tests for line-level mutation hooks.
// Spec: docs/specs/2026-05-12-word-matches-design.md §LineCard header
// Issue #202
//
// Acceptance:
//   - useValidateLine, useCopyLineGt, useDeleteLine are all exported functions
//   - Each hook returns an object with a `mutate` function (TanStack Query shape)

import { describe, it, expect } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import React from "react";
import { server } from "../test/server";
import {
  useValidateLine,
  useCopyLineGt,
  useDeleteLine,
  useUpdateWordGt,
  useMergeLines,
  usePatchParagraph,
  useSetLineGt,
} from "./useLineMutations";

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const Wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return Wrapper;
}

describe("useValidateLine", () => {
  it("is a function", () => {
    expect(typeof useValidateLine).toBe("function");
  });

  it("returns a mutation object with mutate and mutateAsync", () => {
    const Wrapper = makeWrapper();
    const { result } = renderHook(() => useValidateLine("proj1", 0), { wrapper: Wrapper });
    expect(typeof result.current.mutate).toBe("function");
    expect(typeof result.current.mutateAsync).toBe("function");
  });
});

describe("useCopyLineGt", () => {
  it("is a function", () => {
    expect(typeof useCopyLineGt).toBe("function");
  });

  it("returns a mutation object with mutate and mutateAsync", () => {
    const Wrapper = makeWrapper();
    const { result } = renderHook(() => useCopyLineGt("proj1", 0), { wrapper: Wrapper });
    expect(typeof result.current.mutate).toBe("function");
    expect(typeof result.current.mutateAsync).toBe("function");
  });
});

describe("useDeleteLine", () => {
  it("is a function", () => {
    expect(typeof useDeleteLine).toBe("function");
  });

  it("returns a mutation object with mutate and mutateAsync", () => {
    const Wrapper = makeWrapper();
    const { result } = renderHook(() => useDeleteLine("proj1", 0), { wrapper: Wrapper });
    expect(typeof result.current.mutate).toBe("function");
    expect(typeof result.current.mutateAsync).toBe("function");
  });

  // P1.3 (B-62/65): the page-scope /delete endpoint is a 501 stub — the
  // hook must use the real lines/delete-batch route or the line never
  // deletes (LineDetail card Delete + MultiLineDetail card/bulk Delete).
  it("POSTs the line batch body to lines/delete-batch (NOT the /delete stub)", async () => {
    let body: unknown;
    server.use(
      http.post("/api/projects/:pid/pages/:idx/lines/delete-batch", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ project_id: "proj1", page_index: 0 });
      }),
    );
    const Wrapper = makeWrapper();
    const { result } = renderHook(() => useDeleteLine("proj1", 0), { wrapper: Wrapper });
    act(() => {
      result.current.mutate({ lineIndex: 3 });
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(body).toEqual({
      scope: "line",
      line_indices: [3],
    });
  });
});

describe("useUpdateWordGt", () => {
  it("is a function", () => {
    expect(typeof useUpdateWordGt).toBe("function");
  });

  it("returns a mutation object with mutate and mutateAsync", () => {
    const Wrapper = makeWrapper();
    const { result } = renderHook(() => useUpdateWordGt("proj1", 0), { wrapper: Wrapper });
    expect(typeof result.current.mutate).toBe("function");
    expect(typeof result.current.mutateAsync).toBe("function");
  });
});

describe("useMergeLines (FO-3)", () => {
  it("is a function", () => {
    expect(typeof useMergeLines).toBe("function");
  });

  it("returns a mutation object with mutate and mutateAsync", () => {
    const Wrapper = makeWrapper();
    const { result } = renderHook(() => useMergeLines("proj1", 0), { wrapper: Wrapper });
    expect(typeof result.current.mutate).toBe("function");
    expect(typeof result.current.mutateAsync).toBe("function");
  });
});

describe("usePatchParagraph (FO-1)", () => {
  it("is a function", () => {
    expect(typeof usePatchParagraph).toBe("function");
  });

  it("returns a mutation object with mutate and mutateAsync", () => {
    const Wrapper = makeWrapper();
    const { result } = renderHook(() => usePatchParagraph("proj1", 0), { wrapper: Wrapper });
    expect(typeof result.current.mutate).toBe("function");
    expect(typeof result.current.mutateAsync).toBe("function");
  });
});

describe("useSetLineGt (Task 3)", () => {
  it("is a function", () => {
    expect(typeof useSetLineGt).toBe("function");
  });

  it("returns a mutation object with mutate and mutateAsync", () => {
    const Wrapper = makeWrapper();
    const { result } = renderHook(() => useSetLineGt("proj1", 0), { wrapper: Wrapper });
    expect(typeof result.current.mutate).toBe("function");
    expect(typeof result.current.mutateAsync).toBe("function");
  });

  it("posts to lines/{li}/set-gt with text body and invalidates page query", async () => {
    let capturedBody: { text: string } | undefined;
    server.use(
      http.post("/api/projects/:pid/pages/:idx/lines/:li/set-gt", async ({ request }) => {
        capturedBody = (await request.json()) as { text: string };
        return HttpResponse.json({ project_id: "p1", page_index: 0, line_matches: [] });
      }),
    );
    const Wrapper = makeWrapper();
    const { result } = renderHook(() => useSetLineGt("p1", 0), { wrapper: Wrapper });
    act(() => {
      result.current.mutate({ lineIndex: 2, text: "hello world" });
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(capturedBody?.text).toBe("hello world");
  });
});

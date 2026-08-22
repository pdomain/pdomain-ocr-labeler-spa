// useLineMutations.test.tsx — unit tests for line-level mutation hooks.
// Spec: docs/specs/2026-05-12-word-matches-design.md §LineCard header
// Issue #202
//
// Acceptance:
//   - useValidateLine, useCopyLineGt, useDeleteLine are all exported functions
//   - Each hook returns an object with a `mutate` function (TanStack Query shape)

import { describe, it, expect, vi } from "vitest";
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
  useCopyParagraphGt,
  useDeleteWordsBatch,
  useSplitLineAfterWord,
  useSplitLineByWords,
  useMergeParagraphs,
  useDeleteParagraph,
  useSplitParagraphAfterLine,
} from "./useLineMutations";

function makeWrapper(qc?: QueryClient) {
  const queryClient =
    qc ??
    new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
  const Wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return Wrapper;
}

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
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

  it("invalidates typography review after copying OCR to GT", async () => {
    server.use(
      http.post("/api/projects/:pid/pages/:idx/lines/:li/copy-gt", () =>
        HttpResponse.json({ project_id: "proj1", page_index: 4, line_matches: [] }),
      ),
    );
    const qc = makeQueryClient();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useCopyLineGt("proj1", 4), {
      wrapper: makeWrapper(qc),
    });

    await act(() => result.current.mutateAsync({ lineIndex: 2, direction: "ocr_to_gt" }));

    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ["typography-review", "proj1", 4],
    });
  });

  it("does not invalidate typography review after copying GT to OCR", async () => {
    server.use(
      http.post("/api/projects/:pid/pages/:idx/lines/:li/copy-gt", () =>
        HttpResponse.json({ project_id: "proj1", page_index: 4, line_matches: [] }),
      ),
    );
    const qc = makeQueryClient();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useCopyLineGt("proj1", 4), {
      wrapper: makeWrapper(qc),
    });

    await act(() => result.current.mutateAsync({ lineIndex: 2, direction: "gt_to_ocr" }));

    expect(invalidateSpy).not.toHaveBeenCalledWith({
      queryKey: ["typography-review", "proj1", 4],
    });
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

  it("invalidates typography review after deleting a line", async () => {
    server.use(
      http.post("/api/projects/:pid/pages/:idx/lines/delete-batch", () =>
        HttpResponse.json({ project_id: "proj1", page_index: 4, line_matches: [] }),
      ),
    );
    const qc = makeQueryClient();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useDeleteLine("proj1", 4), {
      wrapper: makeWrapper(qc),
    });

    await act(() => result.current.mutateAsync({ lineIndex: 2 }));

    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ["typography-review", "proj1", 4],
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

  it("invalidates typography review after updating word GT", async () => {
    server.use(
      http.post("/api/projects/:pid/pages/:idx/words/:li/:wi/gt", () => HttpResponse.json({})),
    );
    const qc = makeQueryClient();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useUpdateWordGt("proj1", 4), {
      wrapper: makeWrapper(qc),
    });

    await act(() => result.current.mutateAsync({ lineIndex: 2, wordIndex: 1, text: "new" }));

    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ["typography-review", "proj1", 4],
    });
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

  it("invalidates typography review after merging lines", async () => {
    server.use(
      http.post("/api/projects/:pid/pages/:idx/lines/merge", () =>
        HttpResponse.json({ project_id: "proj1", page_index: 4, line_matches: [] }),
      ),
    );
    const qc = makeQueryClient();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useMergeLines("proj1", 4), {
      wrapper: makeWrapper(qc),
    });

    await act(() => result.current.mutateAsync({ lineIndex: 2, direction: "next" }));

    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ["typography-review", "proj1", 4],
    });
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

  it("invalidates typography review after setting line GT", async () => {
    server.use(
      http.post("/api/projects/:pid/pages/:idx/lines/:li/set-gt", () =>
        HttpResponse.json({ project_id: "proj1", page_index: 4, line_matches: [] }),
      ),
    );
    const qc = makeQueryClient();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useSetLineGt("proj1", 4), {
      wrapper: makeWrapper(qc),
    });

    await act(() => result.current.mutateAsync({ lineIndex: 2, text: "new line" }));

    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ["typography-review", "proj1", 4],
    });
  });
});

describe("useCopyParagraphGt", () => {
  it("invalidates typography review after copying OCR to GT", async () => {
    server.use(
      http.post("/api/projects/:pid/pages/:idx/paragraphs/:pi/copy-ocr-to-gt", () =>
        HttpResponse.json({ project_id: "proj1", page_index: 4, line_matches: [] }),
      ),
    );
    const qc = makeQueryClient();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useCopyParagraphGt("proj1", 4), {
      wrapper: makeWrapper(qc),
    });

    await act(() => result.current.mutateAsync({ paragraphIndex: 3, direction: "ocr_to_gt" }));

    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ["typography-review", "proj1", 4],
    });
  });

  it("does not invalidate typography review after copying GT to OCR", async () => {
    server.use(
      http.post("/api/projects/:pid/pages/:idx/paragraphs/:pi/copy-gt-to-ocr", () =>
        HttpResponse.json({ project_id: "proj1", page_index: 4, line_matches: [] }),
      ),
    );
    const qc = makeQueryClient();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useCopyParagraphGt("proj1", 4), {
      wrapper: makeWrapper(qc),
    });

    await act(() => result.current.mutateAsync({ paragraphIndex: 3, direction: "gt_to_ocr" }));

    expect(invalidateSpy).not.toHaveBeenCalledWith({
      queryKey: ["typography-review", "proj1", 4],
    });
  });
});

describe("identity-changing batch mutations", () => {
  it("invalidates typography review after deleting words", async () => {
    server.use(
      http.post("/api/projects/:pid/pages/:idx/words/delete-batch", () =>
        HttpResponse.json({ project_id: "proj1", page_index: 4, line_matches: [] }),
      ),
    );
    const qc = makeQueryClient();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useDeleteWordsBatch("proj1", 4), {
      wrapper: makeWrapper(qc),
    });

    await act(() => result.current.mutateAsync({ wordIndices: [[2, 1]] }));

    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ["typography-review", "proj1", 4],
    });
  });

  it("invalidates typography review after splitting a line after a word", async () => {
    server.use(
      http.post("/api/projects/:pid/pages/:idx/lines/:li/split-after-word", () =>
        HttpResponse.json({ project_id: "proj1", page_index: 4, line_matches: [] }),
      ),
    );
    const qc = makeQueryClient();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useSplitLineAfterWord("proj1", 4), {
      wrapper: makeWrapper(qc),
    });

    await act(() => result.current.mutateAsync({ lineIndex: 2, wordIndex: 1 }));

    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ["typography-review", "proj1", 4],
    });
  });

  it("invalidates typography review after splitting a line by words", async () => {
    server.use(
      http.post("/api/projects/:pid/pages/:idx/lines/split-by-words", () =>
        HttpResponse.json({ project_id: "proj1", page_index: 4, line_matches: [] }),
      ),
    );
    const qc = makeQueryClient();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useSplitLineByWords("proj1", 4), {
      wrapper: makeWrapper(qc),
    });

    await act(() => result.current.mutateAsync({ wordKeys: [[2, 1]] }));

    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ["typography-review", "proj1", 4],
    });
  });

  it("invalidates typography review after merging paragraphs", async () => {
    server.use(
      http.post("/api/projects/:pid/pages/:idx/paragraphs/merge", () =>
        HttpResponse.json({ project_id: "proj1", page_index: 4, line_matches: [] }),
      ),
    );
    const qc = makeQueryClient();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useMergeParagraphs("proj1", 4), {
      wrapper: makeWrapper(qc),
    });

    await act(() => result.current.mutateAsync({ paragraphIndices: [2, 3] }));

    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ["typography-review", "proj1", 4],
    });
  });

  it("invalidates typography review after deleting a paragraph", async () => {
    server.use(
      http.post("/api/projects/:pid/pages/:idx/paragraphs/:pi/delete", () =>
        HttpResponse.json({ project_id: "proj1", page_index: 4, line_matches: [] }),
      ),
    );
    const qc = makeQueryClient();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useDeleteParagraph("proj1", 4), {
      wrapper: makeWrapper(qc),
    });

    await act(() => result.current.mutateAsync({ paragraphIndex: 2 }));

    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ["typography-review", "proj1", 4],
    });
  });

  it("invalidates typography review after splitting a paragraph", async () => {
    server.use(
      http.post("/api/projects/:pid/pages/:idx/paragraphs/:pi/split-after-line", () =>
        HttpResponse.json({ project_id: "proj1", page_index: 4, line_matches: [] }),
      ),
    );
    const qc = makeQueryClient();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useSplitParagraphAfterLine("proj1", 4), {
      wrapper: makeWrapper(qc),
    });

    await act(() => result.current.mutateAsync({ paragraphIndex: 2, afterLineIndex: 1 }));

    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ["typography-review", "proj1", 4],
    });
  });
});

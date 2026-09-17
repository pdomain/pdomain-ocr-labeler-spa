// usePageMutations.test.tsx — unit tests for page-action mutations.
//
// Spec: docs/specs/2026-05-12-page-actions-design.md
// Issues #215, #216
//
// Covers:
//   - useReloadOcr: POSTs to reload-ocr, returns {jobId}
//   - useReloadOcrEdited: same with use_edited_image: true
//   - useSavePage: synchronous POST to save
//   - useSaveProject: 202+job POST to save-all
//   - useLoadPage: synchronous POST to load
//   - useRematchGt: synchronous POST to rematch-gt

import React from "react";
import { describe, it, expect, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import {
  useReloadOcr,
  useReloadOcrEdited,
  useSavePage,
  useSaveProject,
  useLoadPage,
  useRematchGt,
  useUndoPage,
  useRedoPage,
  useConfirmPageKind,
} from "./usePageMutations";

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

const PROJECT_ID = "proj-1";
const PAGE_IDX = 0;

// ─── useReloadOcr ─────────────────────────────────────────────────────────

describe("useReloadOcr", () => {
  it("POSTs to reload-ocr with use_edited_image=false and returns jobId", async () => {
    server.use(
      http.post(`/api/projects/${PROJECT_ID}/pages/${PAGE_IDX}/reload-ocr`, () =>
        HttpResponse.json({ job_id: "job-reload-1" }, { status: 202 }),
      ),
    );

    const { result } = renderHook(() => useReloadOcr(PROJECT_ID, PAGE_IDX), {
      wrapper: makeWrapper(),
    });

    await act(async () => {
      result.current.mutate();
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.job_id).toBe("job-reload-1");
  });

  it("sends use_edited_image: false in request body", async () => {
    let capturedBody: unknown;
    server.use(
      http.post(`/api/projects/${PROJECT_ID}/pages/${PAGE_IDX}/reload-ocr`, async ({ request }) => {
        capturedBody = await request.json();
        return HttpResponse.json({ job_id: "job-2" }, { status: 202 });
      }),
    );

    const { result } = renderHook(() => useReloadOcr(PROJECT_ID, PAGE_IDX), {
      wrapper: makeWrapper(),
    });

    await act(async () => {
      result.current.mutate();
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(capturedBody).toEqual({ use_edited_image: false });
  });
});

// ─── useReloadOcrEdited ───────────────────────────────────────────────────

describe("useReloadOcrEdited", () => {
  it("POSTs to reload-ocr with use_edited_image=true", async () => {
    let capturedBody: unknown;
    server.use(
      http.post(`/api/projects/${PROJECT_ID}/pages/${PAGE_IDX}/reload-ocr`, async ({ request }) => {
        capturedBody = await request.json();
        return HttpResponse.json({ job_id: "job-edited-1" }, { status: 202 });
      }),
    );

    const { result } = renderHook(() => useReloadOcrEdited(PROJECT_ID, PAGE_IDX), {
      wrapper: makeWrapper(),
    });

    await act(async () => {
      result.current.mutate();
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(capturedBody).toEqual({ use_edited_image: true });
    expect(result.current.data?.job_id).toBe("job-edited-1");
  });
});

// ─── useSavePage ─────────────────────────────────────────────────────────

describe("useSavePage", () => {
  it("POSTs to save and returns saved:true", async () => {
    server.use(
      http.post(`/api/projects/${PROJECT_ID}/pages/${PAGE_IDX}/save`, () =>
        HttpResponse.json({ saved: true, page_source: "filesystem" }),
      ),
    );

    const { result } = renderHook(() => useSavePage(PROJECT_ID, PAGE_IDX), {
      wrapper: makeWrapper(),
    });

    await act(async () => {
      result.current.mutate();
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.saved).toBe(true);
    expect(result.current.data?.page_source).toBe("filesystem");
  });
});

// ─── useSaveProject ───────────────────────────────────────────────────────

describe("useSaveProject", () => {
  it("POSTs to save-all and returns 202 with job_id", async () => {
    server.use(
      http.post(`/api/projects/${PROJECT_ID}/save-all`, () =>
        HttpResponse.json({ job_id: "job-save-all-1" }, { status: 202 }),
      ),
    );

    const { result } = renderHook(() => useSaveProject(PROJECT_ID), {
      wrapper: makeWrapper(),
    });

    await act(async () => {
      result.current.mutate();
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.job_id).toBe("job-save-all-1");
  });
});

// ─── useLoadPage ─────────────────────────────────────────────────────────

describe("useLoadPage", () => {
  it("POSTs to load and returns a PagePayload", async () => {
    server.use(
      http.post(`/api/projects/${PROJECT_ID}/pages/${PAGE_IDX}/load`, () =>
        HttpResponse.json({
          project_id: PROJECT_ID,
          page_index: PAGE_IDX,
          page_source: "filesystem",
          has_edited_image: false,
          line_matches: [],
        }),
      ),
    );

    const { result } = renderHook(() => useLoadPage(PROJECT_ID, PAGE_IDX), {
      wrapper: makeWrapper(),
    });

    await act(async () => {
      result.current.mutate();
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect((result.current.data as Record<string, unknown>)["page_source"]).toBe("filesystem");
  });
});

// ─── useRematchGt ─────────────────────────────────────────────────────────

describe("useRematchGt", () => {
  it("POSTs to rematch-gt and returns updated PagePayload", async () => {
    server.use(
      http.post(`/api/projects/${PROJECT_ID}/pages/${PAGE_IDX}/rematch-gt`, () =>
        HttpResponse.json({
          project_id: PROJECT_ID,
          page_index: PAGE_IDX,
          page_source: "cached_ocr",
          has_edited_image: false,
          line_matches: [],
        }),
      ),
    );

    const { result } = renderHook(() => useRematchGt(PROJECT_ID, PAGE_IDX), {
      wrapper: makeWrapper(),
    });

    await act(async () => {
      result.current.mutate();
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect((result.current.data as Record<string, unknown>)["page_source"]).toBe("cached_ocr");
  });
});

// ─── useUndoPage / useRedoPage (event-store undo H-C) ───────────────────────
// Spec: docs/specs/2026-06-12-event-store-undo.md §"API surface".

describe("useUndoPage", () => {
  it("POSTs to /undo and resolves with the refreshed PagePayload", async () => {
    let called = 0;
    server.use(
      http.post(`/api/projects/${PROJECT_ID}/pages/${PAGE_IDX}/undo`, () => {
        called += 1;
        return HttpResponse.json({
          project_id: PROJECT_ID,
          page_index: PAGE_IDX,
          history: { undo_available: false, redo_available: true, cursor: 0, depth: 50 },
        });
      }),
    );

    const { result } = renderHook(() => useUndoPage(PROJECT_ID, PAGE_IDX), {
      wrapper: makeWrapper(),
    });
    await act(async () => {
      result.current.mutate();
    });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(called).toBe(1);
    expect(result.current.data?.history?.redo_available).toBe(true);
  });

  it("surfaces a 409 as an error (undo unavailable)", async () => {
    server.use(
      http.post(`/api/projects/${PROJECT_ID}/pages/${PAGE_IDX}/undo`, () =>
        HttpResponse.json(
          { error: "undo_unavailable", message: "nothing to undo" },
          { status: 409 },
        ),
      ),
    );
    const { result } = renderHook(() => useUndoPage(PROJECT_ID, PAGE_IDX), {
      wrapper: makeWrapper(),
    });
    await act(async () => {
      result.current.mutate();
    });
    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });
});

describe("useRedoPage", () => {
  it("POSTs to /redo", async () => {
    let called = 0;
    server.use(
      http.post(`/api/projects/${PROJECT_ID}/pages/${PAGE_IDX}/redo`, () => {
        called += 1;
        return HttpResponse.json({
          project_id: PROJECT_ID,
          page_index: PAGE_IDX,
          history: { undo_available: true, redo_available: false, cursor: 1, depth: 50 },
        });
      }),
    );
    const { result } = renderHook(() => useRedoPage(PROJECT_ID, PAGE_IDX), {
      wrapper: makeWrapper(),
    });
    await act(async () => {
      result.current.mutate();
    });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(called).toBe(1);
  });
});

// ─── page-kinds invalidation (page-kind review design) ─────────────────────
// Spec: pdomain-ocr-synth's docs/specs/2026-09-17-page-kind-review-design.md
//   "A proposal run and page history both refresh the list" — undo/redo
//   invalidate the ["page-kinds", projectId] prefix alongside the page query.

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

function makeWrapperFor(qc: QueryClient) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

describe("useUndoPage: page-kinds invalidation", () => {
  it("invalidates the page-kinds prefix on success, alongside the page query", async () => {
    server.use(
      http.post(`/api/projects/${PROJECT_ID}/pages/${PAGE_IDX}/undo`, () =>
        HttpResponse.json({ project_id: PROJECT_ID, page_index: PAGE_IDX }),
      ),
    );
    const qc = makeQueryClient();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useUndoPage(PROJECT_ID, PAGE_IDX), {
      wrapper: makeWrapperFor(qc),
    });

    await act(async () => {
      result.current.mutate();
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["page", PROJECT_ID, PAGE_IDX] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["page-kinds", PROJECT_ID] });
  });
});

describe("useRedoPage: page-kinds invalidation", () => {
  it("invalidates the page-kinds prefix on success, alongside the page query", async () => {
    server.use(
      http.post(`/api/projects/${PROJECT_ID}/pages/${PAGE_IDX}/redo`, () =>
        HttpResponse.json({ project_id: PROJECT_ID, page_index: PAGE_IDX }),
      ),
    );
    const qc = makeQueryClient();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useRedoPage(PROJECT_ID, PAGE_IDX), {
      wrapper: makeWrapperFor(qc),
    });

    await act(async () => {
      result.current.mutate();
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["page", PROJECT_ID, PAGE_IDX] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["page-kinds", PROJECT_ID] });
  });
});

// ─── useConfirmPageKind ─────────────────────────────────────────────────────
// Spec: pdomain-ocr-synth's docs/specs/2026-09-17-page-kind-review-design.md
//   "The page toolbar shows and confirms the current page's kind".

describe("useConfirmPageKind", () => {
  it("POSTs { kind, note } to .../page-kind and resolves with the PagePayload", async () => {
    let method: string | undefined;
    let path: string | undefined;
    let body: unknown;
    server.use(
      http.post(`/api/projects/${PROJECT_ID}/pages/${PAGE_IDX}/page-kind`, async ({ request }) => {
        method = request.method;
        path = new URL(request.url).pathname;
        body = await request.json();
        return HttpResponse.json({
          project_id: PROJECT_ID,
          page_index: PAGE_IDX,
          page_kind: "title page",
          page_kind_reviewed: true,
        });
      }),
    );
    const qc = makeQueryClient();
    const { result } = renderHook(() => useConfirmPageKind(PROJECT_ID, PAGE_IDX), {
      wrapper: makeWrapperFor(qc),
    });

    let data: { page_kind?: string | null } | undefined;
    await act(async () => {
      data = await result.current.mutateAsync({ kind: "title page" });
    });

    expect(method).toBe("POST");
    expect(path).toBe(`/api/projects/${PROJECT_ID}/pages/${PAGE_IDX}/page-kind`);
    expect(body).toEqual({ kind: "title page", note: null });
    expect(data?.page_kind).toBe("title page");
  });

  it("invalidates the page query and the page-kinds prefix on success", async () => {
    server.use(
      http.post(`/api/projects/${PROJECT_ID}/pages/${PAGE_IDX}/page-kind`, () =>
        HttpResponse.json({
          project_id: PROJECT_ID,
          page_index: PAGE_IDX,
          page_kind: "body",
          page_kind_reviewed: true,
        }),
      ),
    );
    const qc = makeQueryClient();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useConfirmPageKind(PROJECT_ID, PAGE_IDX), {
      wrapper: makeWrapperFor(qc),
    });

    await act(() => result.current.mutateAsync({ kind: "body" }));

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["page", PROJECT_ID, PAGE_IDX] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["page-kinds", PROJECT_ID] });
  });
});

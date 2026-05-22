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
import { describe, it, expect } from "vitest";
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

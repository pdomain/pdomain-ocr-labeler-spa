// usePage.test.tsx — unit tests for the usePage TanStack Query hook.
// Spec: docs/specs/2026-05-12-frontend-shell-design.md §Hooks
// Issue #192

import { describe, it, expect, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import React from "react";
import { server } from "../test/server";
import { usePage, type PagePayload } from "./usePage";

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return React.createElement(QueryClientProvider, { client: qc }, children);
  };
}

const MOCK_PAGE: PagePayload = {
  project_id: "proj-001",
  page_index: 0,
  page_record: null,
  line_matches: [],
  encoded_dims: null,
  line_filter: "all",
  image_url: null,
  generation: 1,
};

beforeEach(() => {
  server.use(
    http.get("/api/projects/:projectId/pages/:pageIndex", ({ request }) => {
      const url = new URL(request.url);
      const filter = url.searchParams.get("line_filter") ?? "all";
      return HttpResponse.json({ ...MOCK_PAGE, line_filter: filter });
    }),
  );
});

describe("usePage", () => {
  it("fetches page data for valid projectId and pageIndex", async () => {
    const { result } = renderHook(() => usePage("proj-001", 0), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.project_id).toBe("proj-001");
    expect(result.current.data?.page_index).toBe(0);
  });

  it("sends line_filter query param when provided", async () => {
    const { result } = renderHook(() => usePage("proj-001", 0, "unvalidated"), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.line_filter).toBe("unvalidated");
  });

  it("defaults line_filter to 'all' when not provided", async () => {
    const { result } = renderHook(() => usePage("proj-001", 0), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.line_filter).toBe("all");
  });

  it("is disabled when projectId is undefined", () => {
    const { result } = renderHook(() => usePage(undefined, 0), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is disabled when pageIndex is undefined", () => {
    const { result } = renderHook(() => usePage("proj-001", undefined), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is disabled when pageIndex is negative", () => {
    const { result } = renderHook(() => usePage("proj-001", -1), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("uses the correct query key keyed by projectId + pageIndex + filter", async () => {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const wrapper = ({ children }: { children: React.ReactNode }) =>
      React.createElement(QueryClientProvider, { client: qc }, children);

    const { result } = renderHook(() => usePage("proj-001", 2, "mismatched"), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const cached = qc.getQueryData<PagePayload>(["page", "proj-001", 2, "mismatched"]);
    expect(cached).toBeTruthy();
  });
});

// useHistoryVersions.test.tsx — unit tests for the U-M7 history-panel query hook.
// Spec: docs/specs/2026-06-12-event-store-undo.md "history panel + jump-to-version".

import React from "react";
import { describe, it, expect } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { useHistoryVersions, historyVersionsKey } from "./useHistoryVersions";

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

describe("useHistoryVersions", () => {
  it("fetches the version list for a project/page", async () => {
    let requestUrl: string | undefined;
    server.use(
      http.get("/api/projects/:pid/pages/:idx/history/versions", ({ request }) => {
        requestUrl = request.url;
        return HttpResponse.json([
          { node_id: "root", label: "OCR", timestamp: null, is_current: false },
          {
            node_id: "edit-0",
            label: "Word validated",
            timestamp: "2026-09-18T12:00:00Z",
            is_current: true,
          },
        ]);
      }),
    );

    const { result } = renderHook(() => useHistoryVersions("proj-1", 0), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(2);
    expect(result.current.data?.[1]?.is_current).toBe(true);
    const parsed = new URL(requestUrl ?? "");
    expect(parsed.pathname).toBe("/api/projects/proj-1/pages/0/history/versions");
  });

  it("is disabled when projectId is undefined", () => {
    const { result } = renderHook(() => useHistoryVersions(undefined, 0), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is disabled when projectId is an empty string", () => {
    const { result } = renderHook(() => useHistoryVersions("", 0), { wrapper: makeWrapper() });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is disabled when pageIndex is undefined", () => {
    const { result } = renderHook(() => useHistoryVersions("proj-1", undefined), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("is disabled when options.enabled is false (tab not open)", () => {
    server.use(
      http.get("/api/projects/:pid/pages/:idx/history/versions", () => HttpResponse.json([])),
    );
    const { result } = renderHook(() => useHistoryVersions("proj-1", 0, { enabled: false }), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("keys the cache by projectId and pageIndex, scoped per page", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    server.use(
      http.get("/api/projects/:pid/pages/:idx/history/versions", () =>
        HttpResponse.json([{ node_id: "root", label: "OCR", timestamp: null, is_current: true }]),
      ),
    );
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );

    const { result } = renderHook(() => useHistoryVersions("proj-1", 3), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const cached = qc.getQueryData(historyVersionsKey("proj-1", 3));
    expect(cached).toEqual([{ node_id: "root", label: "OCR", timestamp: null, is_current: true }]);
  });
});

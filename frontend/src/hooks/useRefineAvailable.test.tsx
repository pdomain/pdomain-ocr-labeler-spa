// useRefineAvailable.test.tsx — unit tests for the useRefineAvailable hook.
// FO-9: wire backendAvailable to GET /api/refine/available instead of hardcoded false.
//
// Contracts:
//   - returns available:false while loading (data not yet resolved)
//   - returns available:false on fetch error (graceful degradation)
//   - returns available:true when endpoint says so
//   - uses queryKey ["refine-available"]

import { describe, it, expect } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import React from "react";
import { server } from "../test/server";
import { useRefineAvailable } from "./useRefineAvailable";

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return React.createElement(QueryClientProvider, { client: qc }, children);
  };
}

describe("useRefineAvailable", () => {
  it("returns available:false while loading (data undefined before first resolve)", () => {
    // No server handler registered → fetch will never resolve in this tick.
    // We confirm the hook's initial state before data arrives.
    const { result } = renderHook(() => useRefineAvailable(), {
      wrapper: makeWrapper(),
    });
    // Before the query resolves, data is undefined → available falls back to false.
    expect(result.current.data?.available ?? false).toBe(false);
  });

  it("returns available:false on fetch error (non-ok response)", async () => {
    server.use(
      http.get("/api/refine/available", () => {
        return HttpResponse.json({ detail: "internal error" }, { status: 500 });
      }),
    );

    const { result } = renderHook(() => useRefineAvailable(), {
      wrapper: makeWrapper(),
    });

    // The hook returns a synthetic { available: false, reason: "..." } on non-ok,
    // rather than throwing — so isSuccess should be true, not isError.
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.available).toBe(false);
    expect(result.current.data?.reason).toMatch(/probe failed/);
  });

  it("returns available:true when the endpoint says available:true", async () => {
    server.use(
      http.get("/api/refine/available", () => {
        return HttpResponse.json({ available: true, reason: "engine wired" });
      }),
    );

    const { result } = renderHook(() => useRefineAvailable(), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.available).toBe(true);
    expect(result.current.data?.reason).toBe("engine wired");
  });

  it("returns available:false when the endpoint says available:false", async () => {
    server.use(
      http.get("/api/refine/available", () => {
        return HttpResponse.json({ available: false, reason: "engine not wired" });
      }),
    );

    const { result } = renderHook(() => useRefineAvailable(), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.available).toBe(false);
    expect(result.current.data?.reason).toBe("engine not wired");
  });

  it("uses queryKey ['refine-available'] so result is cached", async () => {
    server.use(
      http.get("/api/refine/available", () => {
        return HttpResponse.json({ available: false, reason: "not wired" });
      }),
    );

    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const wrapper = ({ children }: { children: React.ReactNode }) =>
      React.createElement(QueryClientProvider, { client: qc }, children);

    const { result } = renderHook(() => useRefineAvailable(), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const cached = qc.getQueryData<{ available: boolean; reason: string }>(["refine-available"]);
    expect(cached).toBeTruthy();
    expect(cached?.available).toBe(false);
  });
});

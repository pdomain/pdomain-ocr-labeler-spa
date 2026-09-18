// useLaunchSuiteApp.test.tsx — unit tests for the launch mutation hook.
// docs/issues/2026-07-21-suite-launcher-app-shims.md (P1-SUITE).

import React from "react";
import { describe, it, expect } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { useLaunchSuiteApp } from "./useLaunchSuiteApp";

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

describe("useLaunchSuiteApp", () => {
  it("posts app_id and reports an 'opened' outcome", async () => {
    server.use(
      http.post("/api/suite/launch", () =>
        HttpResponse.json({ kind: "opened", url: "http://localhost:8090", spawned: true, pid: 1 }),
      ),
    );

    const { result } = renderHook(() => useLaunchSuiteApp(), { wrapper: makeWrapper() });
    act(() => {
      result.current.mutate("pdomain-ocr-trainer-spa");
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual({
      kind: "opened",
      url: "http://localhost:8090",
      spawned: true,
      pid: 1,
    });
  });

  it("reports a refused launch as mutation data, not a rejected mutation", async () => {
    server.use(
      http.post("/api/suite/launch", () =>
        HttpResponse.json({ detail: "app is disabled: pdomain-ocr-trainer-spa" }, { status: 409 }),
      ),
    );

    const { result } = renderHook(() => useLaunchSuiteApp(), { wrapper: makeWrapper() });
    act(() => {
      result.current.mutate("pdomain-ocr-trainer-spa");
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual({
      kind: "refused",
      reason: "app is disabled: pdomain-ocr-trainer-spa",
    });
    expect(result.current.isError).toBe(false);
  });
});

// useInstalledSuiteApps.test.tsx — unit tests for the installed-siblings
// query hook. docs/issues/2026-07-21-suite-launcher-app-shims.md (P1-SUITE).

import React from "react";
import { describe, it, expect } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { useInstalledSuiteApps } from "./useInstalledSuiteApps";

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

describe("useInstalledSuiteApps", () => {
  it("lists what GET /api/suite/installed returns", async () => {
    server.use(
      http.get("/api/suite/installed", () =>
        HttpResponse.json([
          {
            app_id: "pdomain-ocr-trainer-spa",
            display_name: "OCR Trainer",
            default_port: 8090,
            enabled: true,
          },
        ]),
      ),
    );

    const { result } = renderHook(() => useInstalledSuiteApps(), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual([
      {
        id: "pdomain-ocr-trainer-spa",
        displayName: "OCR Trainer",
        iconUrl: "/api/icons/64?app_id=pdomain-ocr-trainer-spa",
        launchUrl: "http://localhost:8090",
      },
    ]);
  });

  it("resolves an empty array — not an error — when no siblings are installed", async () => {
    server.use(http.get("/api/suite/installed", () => HttpResponse.json([])));

    const { result } = renderHook(() => useInstalledSuiteApps(), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual([]);
  });

  it("surfaces a fetch failure as query error state, not a silently-empty list", async () => {
    server.use(http.get("/api/suite/installed", () => new HttpResponse(null, { status: 503 })));

    const { result } = renderHook(() => useInstalledSuiteApps(), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.data).toBeUndefined();
  });
});

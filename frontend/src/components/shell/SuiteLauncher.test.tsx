// SuiteLauncher.test.tsx — end-to-end tests through the REAL pdomain-ui
// SuiteSiblingsProvider/LauncherSlot/LauncherTile (unmocked), proving the
// real fetchInstalled/postLaunch wiring, not just the api/suite.ts client
// or the hooks in isolation. docs/issues/2026-07-21-suite-launcher-app-shims.md
// (P1-SUITE).

import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../../test/server";

const toastMock = vi.hoisted(() => ({
  info: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
  warn: vi.fn(),
}));
vi.mock("../../lib/toast", () => ({ toast: toastMock }));

import { SuiteLauncherProvider, SuiteLauncherHeaderSlot } from "./SuiteLauncher";

function renderLauncher() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SuiteLauncherProvider>
        <SuiteLauncherHeaderSlot />
      </SuiteLauncherProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  toastMock.error.mockClear();
  toastMock.success.mockClear();
});

describe("SuiteLauncher: lists what the route returns", () => {
  it("renders a launcher tile for each installed sibling", async () => {
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

    renderLauncher();

    expect(await screen.findByRole("button", { name: "Launch OCR Trainer" })).toBeInTheDocument();
    expect(screen.queryByTestId("suite-launcher-empty")).toBeNull();
    expect(screen.queryByTestId("suite-launcher-unavailable")).toBeNull();
  });
});

describe("SuiteLauncher: a disabled sibling", () => {
  it("never becomes a tile — falls back to the empty state instead", async () => {
    server.use(
      http.get("/api/suite/installed", () =>
        HttpResponse.json([
          {
            app_id: "pdomain-ocr-trainer-spa",
            display_name: "OCR Trainer",
            default_port: 8090,
            enabled: false,
          },
        ]),
      ),
    );

    renderLauncher();

    expect(await screen.findByTestId("suite-launcher-empty")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Launch OCR Trainer" })).toBeNull();
    expect(screen.queryByTestId("launcher-tile-pdomain-ocr-trainer-spa")).toBeNull();
  });
});

describe("SuiteLauncher: no siblings installed", () => {
  it("says so instead of showing an empty menu", async () => {
    server.use(http.get("/api/suite/installed", () => HttpResponse.json([])));

    renderLauncher();

    expect(await screen.findByTestId("suite-launcher-empty")).toHaveTextContent(
      "No other suite apps installed",
    );
    expect(screen.queryByRole("button", { name: /^Launch / })).toBeNull();
  });
});

describe("SuiteLauncher: the suite route is unavailable", () => {
  it("surfaces the failure instead of a silent empty menu", async () => {
    server.use(http.get("/api/suite/installed", () => new HttpResponse(null, { status: 503 })));

    renderLauncher();

    expect(await screen.findByTestId("suite-launcher-unavailable")).toHaveTextContent(
      "Suite unavailable",
    );
  });
});

describe("SuiteLauncher: launching a sibling", () => {
  it("posts /api/suite/launch and opens the returned URL on success", async () => {
    let launchedAppId = "";
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
      http.post("/api/suite/launch", ({ request }) => {
        launchedAppId = new URL(request.url).searchParams.get("app_id") ?? "";
        return HttpResponse.json({
          kind: "opened",
          url: "http://localhost:8090",
          spawned: true,
          pid: 1,
        });
      }),
    );
    const openSpy = vi.spyOn(window, "open").mockImplementation(() => null);

    renderLauncher();
    const tile = await screen.findByRole("button", { name: "Launch OCR Trainer" });
    fireEvent.click(tile);

    await waitFor(() => expect(launchedAppId).toBe("pdomain-ocr-trainer-spa"));
    await waitFor(() =>
      expect(openSpy).toHaveBeenCalledWith(
        "http://localhost:8090",
        "_blank",
        "noopener,noreferrer",
      ),
    );
    expect(toastMock.error).not.toHaveBeenCalled();

    openSpy.mockRestore();
  });

  it("explains a refused launch (backend 409) with the backend's real reason", async () => {
    // The row itself reads enabled=true — a disabled row never becomes a
    // tile at all (see "SuiteLauncher: a disabled sibling" above). This
    // 409 models the backend refusing anyway (e.g. disabled server-side in
    // the gap between the list fetch and the click), the race the launcher
    // list can't rule out just by filtering at fetch time.
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
      http.post("/api/suite/launch", () =>
        HttpResponse.json({ detail: "app is disabled: pdomain-ocr-trainer-spa" }, { status: 409 }),
      ),
    );

    renderLauncher();
    const tile = await screen.findByRole("button", { name: "Launch OCR Trainer" });
    fireEvent.click(tile);

    await waitFor(() =>
      expect(toastMock.error).toHaveBeenCalledWith(
        "app is disabled: pdomain-ocr-trainer-spa",
        expect.objectContaining({ id: "suite-launch-pdomain-ocr-trainer-spa" }),
      ),
    );
    // pdomain-ui's LauncherTile has no honest "refused" kind of its own —
    // it renders the same generic text for anything but "opened".
    expect(await screen.findByTestId("launcher-tile-requires-config")).toHaveTextContent(
      "Host config required",
    );
  });
});

// suite.test.ts — unit tests for the shared /api/suite/* client.
// docs/issues/2026-07-21-suite-launcher-app-shims.md (P1-SUITE).

import { describe, it, expect } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import {
  fetchSuiteInstalledApps,
  fetchSuiteInstalledRaw,
  isEnabledSuiteApp,
  launchSuiteApp,
  toShellLaunchResult,
  describeLaunchFailure,
} from "./suite";

const FULL_ROW = {
  app_id: "pdomain-ocr-trainer-spa",
  package: "pdomain-ocr-trainer-spa",
  version: "1.2.3",
  binary: "/usr/bin/pdomain-ocr-trainer",
  default_port: 8090,
  icon: "trainer",
  display_name: "OCR Trainer",
  description: "Label training data.",
  enabled: true,
  registered_at: "2026-07-21T00:00:00Z",
};

describe("fetchSuiteInstalledApps", () => {
  it("lists what the route returns, mapped to the shell InstalledApp shape", async () => {
    server.use(http.get("/api/suite/installed", () => HttpResponse.json([FULL_ROW])));

    const apps = await fetchSuiteInstalledApps();

    expect(apps).toEqual([
      {
        id: "pdomain-ocr-trainer-spa",
        displayName: "OCR Trainer",
        iconUrl: "/api/icons/64?app_id=pdomain-ocr-trainer-spa",
        launchUrl: "http://localhost:8090",
      },
    ]);
  });

  it("returns an empty array when the route returns none installed", async () => {
    server.use(http.get("/api/suite/installed", () => HttpResponse.json([])));

    await expect(fetchSuiteInstalledApps()).resolves.toEqual([]);
  });

  it("throws when the route responds with a non-2xx status", async () => {
    server.use(http.get("/api/suite/installed", () => new HttpResponse(null, { status: 500 })));

    await expect(fetchSuiteInstalledApps()).rejects.toThrow(/500/);
  });

  it("throws on a network failure rather than silently returning an empty list", async () => {
    server.use(http.get("/api/suite/installed", () => HttpResponse.error()));

    await expect(fetchSuiteInstalledApps()).rejects.toThrow();
  });

  it("drops a malformed row instead of failing the whole list", async () => {
    server.use(
      http.get("/api/suite/installed", () =>
        HttpResponse.json([{ app_id: "no-other-fields" }, FULL_ROW]),
      ),
    );

    const apps = await fetchSuiteInstalledApps();
    expect(apps).toHaveLength(1);
    expect(apps[0]?.id).toBe("pdomain-ocr-trainer-spa");
  });
});

describe("fetchSuiteInstalledRaw + isEnabledSuiteApp", () => {
  it("finds an enabled app by app_id in a loosely-shaped row", async () => {
    server.use(
      http.get("/api/suite/installed", () =>
        HttpResponse.json([{ app_id: "pdomain-ocr-trainer-spa", enabled: true }]),
      ),
    );

    const rows = await fetchSuiteInstalledRaw();
    expect(rows.some((row) => isEnabledSuiteApp(row, "pdomain-ocr-trainer-spa"))).toBe(true);
  });

  it("does not match a disabled app", () => {
    expect(isEnabledSuiteApp({ app_id: "x", enabled: false }, "x")).toBe(false);
  });

  it("does not match a different app_id", () => {
    expect(isEnabledSuiteApp({ app_id: "y", enabled: true }, "x")).toBe(false);
  });
});

describe("launchSuiteApp", () => {
  it("resolves 'opened' on a 200 with the backend's local-mode shape", async () => {
    server.use(
      http.post("/api/suite/launch", () =>
        HttpResponse.json({
          kind: "opened",
          url: "http://localhost:8090",
          spawned: true,
          pid: 123,
        }),
      ),
    );

    const outcome = await launchSuiteApp("pdomain-ocr-trainer-spa");
    expect(outcome).toEqual({
      kind: "opened",
      url: "http://localhost:8090",
      spawned: true,
      pid: 123,
    });
  });

  it("sends app_id as a query param, not a JSON body", async () => {
    let capturedUrl: URL | undefined;
    let capturedBody = "";
    server.use(
      http.post("/api/suite/launch", async ({ request }) => {
        capturedUrl = new URL(request.url);
        capturedBody = await request.text();
        return HttpResponse.json({ kind: "opened", url: "http://localhost:8090", spawned: false });
      }),
    );

    await launchSuiteApp("pdomain-ocr-trainer-spa");

    expect(capturedUrl?.searchParams.get("app_id")).toBe("pdomain-ocr-trainer-spa");
    expect(capturedBody).toBe("");
  });

  it("resolves 'refused' with the backend's detail on a 404 (unknown app)", async () => {
    server.use(
      http.post("/api/suite/launch", () =>
        HttpResponse.json({ detail: "unknown app: ghost-app" }, { status: 404 }),
      ),
    );

    const outcome = await launchSuiteApp("ghost-app");
    expect(outcome).toEqual({ kind: "refused", reason: "unknown app: ghost-app" });
  });

  it("resolves 'refused' with the backend's detail on a 409 (disabled app)", async () => {
    server.use(
      http.post("/api/suite/launch", () =>
        HttpResponse.json({ detail: "app is disabled: pdomain-ocr-trainer-spa" }, { status: 409 }),
      ),
    );

    const outcome = await launchSuiteApp("pdomain-ocr-trainer-spa");
    expect(outcome).toEqual({
      kind: "refused",
      reason: "app is disabled: pdomain-ocr-trainer-spa",
    });
  });

  it("resolves 'error' on a plain-text 500 (unhandled LaunchTimeoutError)", async () => {
    server.use(
      http.post(
        "/api/suite/launch",
        () => new HttpResponse("Internal Server Error", { status: 500 }),
      ),
    );

    const outcome = await launchSuiteApp("pdomain-ocr-trainer-spa");
    expect(outcome.kind).toBe("error");
  });

  it("resolves 'error' rather than rejecting on a network failure", async () => {
    server.use(http.post("/api/suite/launch", () => HttpResponse.error()));

    const outcome = await launchSuiteApp("pdomain-ocr-trainer-spa");
    expect(outcome.kind).toBe("error");
  });
});

describe("toShellLaunchResult / describeLaunchFailure", () => {
  it("maps an 'opened' outcome straight through", () => {
    const outcome = {
      kind: "opened",
      url: "http://localhost:8090",
      spawned: true,
      pid: 1,
    } as const;
    expect(toShellLaunchResult(outcome, "app-1")).toEqual({
      kind: "opened",
      url: "http://localhost:8090",
    });
  });

  it("maps a refused/error outcome to pdomain-ui's requires-host-config kind", () => {
    const refused = { kind: "refused", reason: "app is disabled: app-1" } as const;
    expect(toShellLaunchResult(refused, "app-1")).toEqual({
      kind: "requires-host-config",
      siblingId: "app-1",
    });
  });

  it("describes a refused outcome with its reason", () => {
    expect(describeLaunchFailure({ kind: "refused", reason: "nope" })).toBe("nope");
  });

  it("describes an error outcome with its message", () => {
    expect(describeLaunchFailure({ kind: "error", message: "boom" })).toBe("boom");
  });
});

// ExportDialogUtils.test.ts — unit tests for the "Send to trainer" helpers.
// docs/issues/2026-07-21-suite-launcher-app-shims.md (P1-SUITE).
//
// These wrap api/suite.ts's shared client (isEnabledSuiteApp, launchSuiteApp)
// rather than hand-rolling their own fetch. fetchTrainerInstalled previously
// used a truthy check on `enabled`; it now relies on isEnabledSuiteApp's
// strict `=== true` equality instead. Covered here directly so a future
// change to either this file or api/suite.ts doesn't silently change what
// the "Send to trainer" button does — the indirect coverage in
// ExportDialog.test.tsx only exercises the `enabled: true` / absent-row
// cases, not a present-but-disabled row or a malformed `enabled` value.

import { describe, it, expect, vi, afterEach } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { fetchTrainerInstalled, launchTrainer } from "./ExportDialogUtils";

const TRAINER_ROW = {
  app_id: "pdomain-ocr-trainer-spa",
  display_name: "OCR Trainer",
  default_port: 8090,
  enabled: true,
};

describe("fetchTrainerInstalled", () => {
  it("is true when the trainer is installed and enabled", async () => {
    server.use(http.get("/api/suite/installed", () => HttpResponse.json([TRAINER_ROW])));

    await expect(fetchTrainerInstalled()).resolves.toBe(true);
  });

  it("is false when the trainer is not in the installed list", async () => {
    server.use(http.get("/api/suite/installed", () => HttpResponse.json([])));

    await expect(fetchTrainerInstalled()).resolves.toBe(false);
  });

  it("is false when the trainer is installed but disabled", async () => {
    server.use(
      http.get("/api/suite/installed", () =>
        HttpResponse.json([{ ...TRAINER_ROW, enabled: false }]),
      ),
    );

    await expect(fetchTrainerInstalled()).resolves.toBe(false);
  });

  it("is false when `enabled` is present but not the strict boolean true", async () => {
    // fetchTrainerInstalled used to do a truthy check on `enabled` (any
    // truthy value counted); it now goes through isEnabledSuiteApp's
    // `=== true`. A row that reports enabled as a non-boolean truthy value
    // must not be treated as installed — pin that here so a future
    // isEnabledSuiteApp change can't quietly loosen this back to truthy.
    server.use(
      http.get("/api/suite/installed", () => HttpResponse.json([{ ...TRAINER_ROW, enabled: 1 }])),
    );

    await expect(fetchTrainerInstalled()).resolves.toBe(false);
  });

  it("is false, not thrown, when the route is unreachable", async () => {
    server.use(http.get("/api/suite/installed", () => new HttpResponse(null, { status: 500 })));

    await expect(fetchTrainerInstalled()).resolves.toBe(false);
  });
});

describe("launchTrainer", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("returns kind and url on a successful launch", async () => {
    server.use(
      http.post("/api/suite/launch", ({ request }) => {
        const appId = new URL(request.url).searchParams.get("app_id");
        expect(appId).toBe("pdomain-ocr-trainer-spa");
        return HttpResponse.json({
          kind: "opened",
          url: "http://localhost:8090",
          spawned: true,
          pid: 1,
        });
      }),
    );

    await expect(launchTrainer()).resolves.toEqual({
      kind: "opened",
      url: "http://localhost:8090",
    });
  });

  it("returns null and logs the real reason when the launch is refused", async () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    server.use(
      http.post("/api/suite/launch", () =>
        HttpResponse.json({ detail: "app is disabled: pdomain-ocr-trainer-spa" }, { status: 409 }),
      ),
    );

    await expect(launchTrainer()).resolves.toBeNull();
    expect(warnSpy).toHaveBeenCalledWith(
      expect.stringContaining("app is disabled: pdomain-ocr-trainer-spa"),
    );
  });
});

// suite.ts — shared client for the pdomain-ops-mounted /api/suite/* routes
// (bootstrap.py's `mount_suite_routes`).
//
// Two callers share this module rather than each hand-rolling a fetch:
//   - components/shell/SuiteLauncher.tsx — the AppShell sibling-app launcher
//     (docs/issues/2026-07-21-suite-launcher-app-shims.md, P1-SUITE).
//   - components/ExportDialogUtils.ts — the export dialog's "Send to
//     trainer" affordance, which predates the launcher wiring.
//
// Backend contract (pdomain_ops.suite.routes.mount_routes, local-mode
// SuiteAdapters.local()):
//   GET  /api/suite/installed
//     -> list[dict] — a pydantic `InstalledApp.model_dump(mode="json")` per
//        row: app_id, package, version, binary, default_port, icon,
//        display_name, description, enabled, registered_at. Untyped on the
//        wire (bootstrap.py's `_suppress_ops_schema_violations` documents
//        why /api/suite/launch and /api/suite/prefs are excluded from the
//        OpenAPI schema's typed response models; /installed keeps a
//        response_model of `list[dict[str, object]]`, so generated
//        `components["schemas"]` has no InstalledApp type to import here) —
//        every row is `unknown` until validated below.
//   POST /api/suite/launch?app_id=<id>  (query param, not a JSON body — see
//        `launchSuiteApp`)
//     -> 200 `{kind:"opened", url, spawned, pid}` — the only kind
//        `pdomain_ops.suite.sibling_spawn.LocalSpawnLauncher` (this app's
//        launcher; `SuiteAdapters.local()`) ever returns. Its sibling kind,
//        `{kind:"requires-host-config", sibling_id}`, exists only on
//        `LaunchResultRequiresHostConfig` for a hosted-mode launcher that
//        `SuiteAdapters.from_env()` raises `NotImplementedError` for — this
//        app cannot reach it today.
//     -> 404 unknown app_id, 409 app disabled (FastAPI HTTPException,
//        `{"detail": "..."}` body)
//     -> 500 on `LaunchTimeoutError` (sibling spawned but never became
//        healthy) — no exception handler is registered, so this is
//        Starlette's default plain-text "Internal Server Error", not JSON.

import type { InstalledApp, LaunchResult } from "@pdomain/pdomain-ui/shell";

/** Icon size requested from `GET /api/icons/{size}` — routes.py's `_ALLOWED_ICON_SIZES`. */
const ICON_SIZE = 64;

/** TanStack Query key for the installed-siblings list. */
export const SUITE_INSTALLED_QUERY_KEY = ["suite", "installed"] as const;

// ─── GET /api/suite/installed ─────────────────────────────────────────────

/**
 * GET /api/suite/installed and return its parsed JSON array, unvalidated.
 * Throws on a non-2xx response, an unreachable route, or a non-array body —
 * every caller decides for itself how to treat one bad row vs. the whole
 * route being unavailable; nothing here silently returns `[]` to paper over
 * a real failure.
 */
export async function fetchSuiteInstalledRaw(): Promise<unknown[]> {
  const response = await fetch("/api/suite/installed");
  if (!response.ok) {
    throw new Error(
      `GET /api/suite/installed failed: ${String(response.status)} ${response.statusText}`,
    );
  }
  const body: unknown = await response.json();
  if (!Array.isArray(body)) {
    throw new Error("GET /api/suite/installed returned a non-array response");
  }
  // `Array.isArray` narrows `unknown` to `any[]`, not `unknown[]` (a known
  // TS/eslint gap) — cast back to the declared, honest element type.
  return body as unknown[];
}

/** Is `row.enabled` strictly `true`? Shared by every "usable sibling" check below. */
function isEnabledRow(row: Record<string, unknown>): boolean {
  return row["enabled"] === true;
}

/**
 * Loose per-row check: is `row` an installed, enabled app with this
 * `app_id`? Used by ExportDialogUtils, which only ever needs to know
 * whether one specific sibling (the trainer) is present — it doesn't need
 * the full shape `toShellInstalledApp` requires, so a registry row from an
 * older/newer sibling that's missing unrelated fields still counts.
 */
export function isEnabledSuiteApp(row: unknown, appId: string): boolean {
  if (typeof row !== "object" || row === null) return false;
  const r = row as Record<string, unknown>;
  return r["app_id"] === appId && isEnabledRow(r);
}

/** The subset of the backend's `InstalledApp` row the launcher list needs. */
interface SuiteInstalledAppRow {
  app_id: string;
  display_name: string;
  default_port: number;
}

/**
 * Strict per-row guard for the launcher list: every field
 * `toShellInstalledApp` reads must be present with the right runtime type,
 * AND the row must be enabled. A disabled sibling is dropped here rather
 * than rendered as a clickable tile that always 409s — pdomain-ui's
 * `LauncherTile` has no disabled visual state, so a disabled row would look
 * like an ordinary tile and, after the click, fall back to the same generic
 * "Host config required" text `postLaunch`'s failure path uses for every
 * other refusal, misdescribing why the launch didn't work.
 *
 * A malformed row (e.g. a sibling on an incompatible pdomain-ops version)
 * is likewise dropped rather than failing the whole list.
 */
function isSuiteInstalledAppRow(value: unknown): value is SuiteInstalledAppRow {
  if (typeof value !== "object" || value === null) return false;
  const r = value as Record<string, unknown>;
  return (
    typeof r["app_id"] === "string" &&
    typeof r["display_name"] === "string" &&
    typeof r["default_port"] === "number" &&
    isEnabledRow(r)
  );
}

/** Maps one validated backend row to pdomain-ui's `InstalledApp` shell shape. */
function toShellInstalledApp(row: SuiteInstalledAppRow): InstalledApp {
  return {
    id: row.app_id,
    displayName: row.display_name,
    iconUrl: `/api/icons/${String(ICON_SIZE)}?app_id=${encodeURIComponent(row.app_id)}`,
    // LocalSpawnLauncher.launch() computes the same URL from default_port
    // (sibling_spawn.py) — this is a best-effort address, not a guarantee
    // the sibling is actually running yet; postLaunch is what confirms that.
    launchUrl: `http://localhost:${String(row.default_port)}`,
  };
}

/**
 * Fetch the installed-sibling list, mapped to pdomain-ui's shell shape.
 * Used as `SuiteSiblingsProvider`'s `fetchInstalled` (via
 * components/shell/SuiteLauncher.tsx) and by `useInstalledSuiteApps`.
 */
export async function fetchSuiteInstalledApps(): Promise<InstalledApp[]> {
  const rows = await fetchSuiteInstalledRaw();
  return rows.filter(isSuiteInstalledAppRow).map(toShellInstalledApp);
}

// ─── POST /api/suite/launch ────────────────────────────────────────────────

/**
 * Outcome of a launch attempt — richer than pdomain-ui's `LaunchResult`,
 * which has no way to carry *why* a launch failed. Carrying the real reason
 * lets a caller show it (e.g. a toast) instead of collapsing every failure
 * into the generic text pdomain-ui's `LauncherTile` renders for anything
 * that isn't `"opened"` — see the "product-dishonest dual behavior" note in
 * docs/issues/2026-07-21-suite-launcher-app-shims.md.
 */
export type SuiteLaunchOutcome =
  | { kind: "opened"; url: string; spawned: boolean; pid: number | null }
  | { kind: "refused"; reason: string }
  | { kind: "error"; message: string };

function isOpenedLaunchBody(
  value: unknown,
): value is { kind: "opened"; url: string; spawned?: boolean; pid?: number | null } {
  if (typeof value !== "object" || value === null) return false;
  const r = value as Record<string, unknown>;
  return r["kind"] === "opened" && typeof r["url"] === "string";
}

/** Best-effort extraction of a FastAPI `{"detail": "..."}` error body. */
async function readErrorDetail(response: Response, fallback: string): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (
      typeof body === "object" &&
      body !== null &&
      typeof (body as Record<string, unknown>)["detail"] === "string"
    ) {
      return (body as Record<string, unknown>)["detail"] as string;
    }
  } catch {
    // Non-JSON body — e.g. Starlette's plain-text default 500. Fall through
    // to the caller-supplied fallback.
  }
  return fallback;
}

/**
 * POST /api/suite/launch with `app_id` as a query parameter — the mounted
 * route's actual signature (`async def launch_app(app_id: str)`), matching
 * ExportDialogUtils' existing "Send to trainer" call. This deliberately
 * does NOT match pdomain-ui's own `createApiSuiteSiblingsConfig()` default,
 * which POSTs `{id}` as a JSON body and would 422 against this backend —
 * see root-cause hypothesis 2 in
 * docs/issues/2026-07-21-suite-launcher-app-shims.md.
 *
 * Never rejects: every failure resolves to a `"refused"` or `"error"`
 * outcome. This matters because `SuiteSiblingsProvider`'s `postLaunch` is
 * called directly by pdomain-ui's `LauncherTile` with no try/catch of its
 * own — a rejected promise there would surface as an unhandled rejection.
 */
export async function launchSuiteApp(appId: string): Promise<SuiteLaunchOutcome> {
  let response: Response;
  try {
    response = await fetch(`/api/suite/launch?app_id=${encodeURIComponent(appId)}`, {
      method: "POST",
    });
  } catch (err) {
    return {
      kind: "error",
      message: err instanceof Error ? err.message : "Failed to reach the suite launcher.",
    };
  }

  if (response.status === 404) {
    return {
      kind: "refused",
      reason: await readErrorDetail(response, `${appId} is not installed.`),
    };
  }
  if (response.status === 409) {
    return { kind: "refused", reason: await readErrorDetail(response, `${appId} is disabled.`) };
  }
  if (!response.ok) {
    return {
      kind: "error",
      message: await readErrorDetail(response, `Launch failed: HTTP ${String(response.status)}.`),
    };
  }

  let body: unknown;
  try {
    body = await response.json();
  } catch {
    return { kind: "error", message: "Launch succeeded but returned an unreadable response." };
  }
  if (isOpenedLaunchBody(body)) {
    return { kind: "opened", url: body.url, spawned: body.spawned ?? false, pid: body.pid ?? null };
  }
  // Backend's LaunchResultRequiresHostConfig kind — unreachable from this
  // app's local-mode launcher today (see module doc comment); handled for
  // forward compatibility with a future hosted-mode adapter.
  return { kind: "refused", reason: `${appId} requires host configuration before it can launch.` };
}

/**
 * Adapts a `SuiteLaunchOutcome` to pdomain-ui's `LaunchResult` union for
 * `SuiteSiblingsProvider`'s `postLaunch` contract, which has no "refused" or
 * "error" kind — `LauncherTile` renders the same generic "Host config
 * required" text for anything but `"opened"`. Callers should show
 * `describeLaunchFailure(outcome)` themselves (e.g. a toast) before calling
 * this, since the adapted result loses the real reason.
 */
export function toShellLaunchResult(outcome: SuiteLaunchOutcome, siblingId: string): LaunchResult {
  if (outcome.kind === "opened") {
    return { kind: "opened", url: outcome.url };
  }
  return { kind: "requires-host-config", siblingId };
}

/**
 * Human-readable failure reason for a non-`"opened"` outcome. Callers only
 * ever invoke this after checking `outcome.kind !== "opened"`; the "opened"
 * case returns an empty string defensively rather than throwing.
 */
export function describeLaunchFailure(outcome: SuiteLaunchOutcome): string {
  if (outcome.kind === "refused") return outcome.reason;
  if (outcome.kind === "error") return outcome.message;
  return "";
}

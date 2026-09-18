// SuiteLauncher.tsx — wires the real /api/suite/* client into pdomain-ui's
// AppShell launcher, replacing the permanent-empty / permanent-
// "requires-host-config" shims from
// docs/issues/2026-07-21-suite-launcher-app-shims.md (P1-SUITE).
//
// Two pieces, both needed:
//
// 1. `SuiteLauncherProvider` — the real `fetchInstalled` / `postLaunch`
//    callbacks for `SuiteSiblingsProvider`, backed by api/suite.ts and a
//    TanStack Query hook + mutation (useInstalledSuiteApps,
//    useLaunchSuiteApp) rather than App.tsx's former hard-coded shims.
//
// 2. `SuiteLauncherHeaderSlot` — renders pdomain-ui's `<LauncherSlot/>` PLUS
//    the honest empty/error fallback it omits. Two things make this
//    necessary rather than decorative:
//
//    - App.tsx passes AppShell a custom `header` node (HeaderBar + the OCR
//      Config trigger). Per AppShell's own doc comment, it only assembles
//      its *built-in* header — app icon/name + headerActions + LauncherSlot
//      + SettingsSlot — when `header` is left undefined; a custom `header`
//      is "an escape hatch for apps that need full control" and bypasses
//      that assembly entirely. `launcherSlot="header"` (still passed below)
//      is therefore inert today — nothing rendered LauncherSlot at all,
//      independent of whether fetchInstalled/postLaunch worked. This slot
//      renders it explicitly instead.
//    - pdomain-ui's `LauncherSlot` renders `null` whenever the context has
//      an error OR an empty sibling list (dist/shell — `!ctx || ctx.error
//      !== null || ctx.siblings.length === 0`). That is the "silent
//      nothing" the issue calls out for the empty-siblings and
//      route-unavailable cases. `SuiteLauncherStatus` below covers exactly
//      those two cases using its own `useInstalledSuiteApps` query (not the
//      SuiteSiblingsContext), so it renders correctly regardless of what
//      pdomain-ui's internal context state is doing.

import { useCallback, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  SuiteSiblingsProvider,
  LauncherSlot,
  type InstalledApp,
  type LaunchResult,
} from "@pdomain/pdomain-ui/shell";
import {
  fetchSuiteInstalledApps,
  SUITE_INSTALLED_QUERY_KEY,
  toShellLaunchResult,
  describeLaunchFailure,
} from "../../api/suite";
import { useInstalledSuiteApps } from "../../hooks/useInstalledSuiteApps";
import { useLaunchSuiteApp } from "../../hooks/useLaunchSuiteApp";
import { toast } from "../../lib/toast";

/**
 * Renders nothing while the installed-siblings query is pending or once it
 * resolves with at least one app — `<LauncherSlot/>` already covers "has
 * siblings" on its own. Fills the two gaps LauncherSlot leaves silent.
 */
function SuiteLauncherStatus() {
  const installedQuery = useInstalledSuiteApps();

  if (installedQuery.isError) {
    return (
      <span
        data-testid="suite-launcher-unavailable"
        role="status"
        title={installedQuery.error.message}
        className="text-[10px] text-ink-3 px-1 select-none"
      >
        Suite unavailable
      </span>
    );
  }
  if (installedQuery.isSuccess && installedQuery.data.length === 0) {
    return (
      <span
        data-testid="suite-launcher-empty"
        role="status"
        className="text-[10px] text-ink-3 px-1 select-none"
      >
        No other suite apps installed
      </span>
    );
  }
  return null;
}

/**
 * Header-slot content: the real launcher tiles plus the fallback text for
 * the states `<LauncherSlot/>` renders as nothing. Meant to sit inside
 * AppShell's header (HeaderBar's `rightSlot`), a descendant of
 * `SuiteLauncherProvider` so both read the same context/cache.
 */
export function SuiteLauncherHeaderSlot() {
  return (
    <>
      <LauncherSlot />
      <SuiteLauncherStatus />
    </>
  );
}

/**
 * Supplies `SuiteSiblingsProvider` with real `fetchInstalled` / `postLaunch`
 * callbacks. Wrap the app tree with this in place of a bare
 * `<SuiteSiblingsProvider value={{fetchInstalled, postLaunch}}>` — it needs
 * `useQueryClient()` / `useLaunchSuiteApp()`, so it must be a component
 * rendered under `QueryClientProvider`, not a pair of module-level
 * functions.
 */
export function SuiteLauncherProvider({ children }: { children?: ReactNode }) {
  const queryClient = useQueryClient();
  const launchMutation = useLaunchSuiteApp();

  const fetchInstalled = useCallback(
    (): Promise<InstalledApp[]> =>
      queryClient.query({
        queryKey: SUITE_INSTALLED_QUERY_KEY,
        queryFn: fetchSuiteInstalledApps,
      }),
    [queryClient],
  );

  const postLaunch = useCallback(
    async (id: string): Promise<LaunchResult> => {
      const outcome = await launchMutation.mutateAsync(id);
      if (outcome.kind !== "opened") {
        // The honest reason: LauncherTile itself only ever shows the
        // generic "Host config required" text for any non-"opened" kind.
        toast.error(describeLaunchFailure(outcome), { id: `suite-launch-${id}` });
      }
      return toShellLaunchResult(outcome, id);
    },
    [launchMutation],
  );

  return (
    <SuiteSiblingsProvider value={{ fetchInstalled, postLaunch }}>{children}</SuiteSiblingsProvider>
  );
}

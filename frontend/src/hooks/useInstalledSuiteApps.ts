// useInstalledSuiteApps.ts — TanStack Query hook for GET /api/suite/installed.
// docs/issues/2026-07-21-suite-launcher-app-shims.md (P1-SUITE).
//
// Backs both the SuiteSiblingsProvider `fetchInstalled` callback (via
// components/shell/SuiteLauncher.tsx's queryClient.query under the same
// key) and the visible empty/error fallback pdomain-ui's LauncherSlot omits
// (SuiteLauncherStatus) — one cache entry, one fetch, two consumers.

import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import type { InstalledApp } from "@pdomain/pdomain-ui/shell";
import { fetchSuiteInstalledApps, SUITE_INSTALLED_QUERY_KEY } from "../api/suite";

/** The installed-sibling-apps list, mapped to pdomain-ui's shell shape. */
export function useInstalledSuiteApps(): UseQueryResult<InstalledApp[]> {
  return useQuery({
    queryKey: SUITE_INSTALLED_QUERY_KEY,
    queryFn: fetchSuiteInstalledApps,
  });
}

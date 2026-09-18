// useLaunchSuiteApp.ts — TanStack mutation for POST /api/suite/launch.
// docs/issues/2026-07-21-suite-launcher-app-shims.md (P1-SUITE).
//
// Wraps launchSuiteApp() (api/suite.ts), which never rejects — every
// failure resolves to a `SuiteLaunchOutcome` of kind "refused" or "error"
// instead of throwing, so `mutation.isError` never fires for this mutation;
// callers branch on `mutation.data.kind` instead.

import { useMutation, type UseMutationResult } from "@tanstack/react-query";
import { launchSuiteApp, type SuiteLaunchOutcome } from "../api/suite";

/** POST /api/suite/launch?app_id=... — launch (or focus) an installed sibling app. */
export function useLaunchSuiteApp(): UseMutationResult<SuiteLaunchOutcome, Error, string> {
  return useMutation({
    mutationFn: launchSuiteApp,
  });
}

// ExportDialogUtils.ts — non-component helpers for ExportDialog.
// Extracted per react-refresh rule: non-component exports must not live
// in .tsx files alongside components.
//
// Shares its /api/suite/* calls with the AppShell launcher
// (components/shell/SuiteLauncher.tsx) via api/suite.ts, rather than each
// hand-rolling its own fetch — see
// docs/issues/2026-07-21-suite-launcher-app-shims.md next step 2.

import {
  fetchSuiteInstalledRaw,
  isEnabledSuiteApp,
  launchSuiteApp,
  describeLaunchFailure,
} from "../api/suite";

/** App ID for the OCR trainer in the suite registry. */
const TRAINER_APP_ID = "pdomain-ocr-trainer-spa";

/**
 * Fetch the list of installed suite apps and return whether the trainer
 * is present and enabled.
 *
 * Returns false on any network error so the button is hidden rather than
 * throwing.
 */
export async function fetchTrainerInstalled(): Promise<boolean> {
  try {
    const rows = await fetchSuiteInstalledRaw();
    return rows.some((row) => isEnabledSuiteApp(row, TRAINER_APP_ID));
  } catch {
    return false;
  }
}

/**
 * Call /api/suite/launch for the trainer app.
 *
 * Returns the launch result on success; on any failure (refused or
 * network/server error) logs the honest reason to console and returns null
 * (caller decides whether to surface it to the user).
 */
export async function launchTrainer(): Promise<{ kind: string; url?: string } | null> {
  const outcome = await launchSuiteApp(TRAINER_APP_ID);
  if (outcome.kind === "opened") {
    return { kind: outcome.kind, url: outcome.url };
  }
  console.warn(`launch trainer: ${describeLaunchFailure(outcome)}`);
  return null;
}

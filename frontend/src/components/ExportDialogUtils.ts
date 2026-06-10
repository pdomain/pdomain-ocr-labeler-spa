// ExportDialogUtils.ts — non-component helpers for ExportDialog.
// Extracted per react-refresh rule: non-component exports must not live
// in .tsx files alongside components.

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
    const res = await fetch("/api/suite/installed");
    if (!res.ok) return false;
    const apps = (await res.json()) as Array<{ app_id: string; enabled: boolean }>;
    return apps.some((a) => a.app_id === TRAINER_APP_ID && a.enabled);
  } catch {
    return false;
  }
}

/**
 * Call /api/suite/launch for the trainer app.
 *
 * Returns the launch result on success; on any error logs to console
 * and returns null (caller decides whether to surface to the user).
 */
export async function launchTrainer(): Promise<{ kind: string; url?: string } | null> {
  try {
    const res = await fetch(`/api/suite/launch?app_id=${encodeURIComponent(TRAINER_APP_ID)}`, {
      method: "POST",
    });
    if (!res.ok) {
      console.warn(`launch trainer: HTTP ${res.status}`);
      return null;
    }
    return (await res.json()) as { kind: string; url?: string };
  } catch (e) {
    console.warn("launch trainer: fetch failed", e);
    return null;
  }
}

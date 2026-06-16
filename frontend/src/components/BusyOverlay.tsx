// BusyOverlay.tsx — full-page busy overlay shown during active mutations or jobs.
// ProjectLoadingOverlay — higher z-index overlay specifically for project load.
//
// Spec: docs/specs/2026-05-12-notifications-design.md §BusyOverlay logic
// Issue #232
//
// pdui Slice 1 (2026-06-16): inner card replaced with OperationStatusPanel from
// @pdomain/pdomain-ui/status. The outer fixed-position backdrop and data-testid
// root div are kept as a thin local wrapper because BlockingOperationOverlay from
// pdui uses a Radix Dialog Portal (escapes to document.body), which would break
// the driver-contract testid requirement and the DOM-containment assertion in
// ProjectPage.test.tsx (imagePaneEl.contains(screen.getByTestId("busy-overlay"))).
//
// BusyOverlay logic:
//   visible when isMutating prop is true OR activeJob is non-null.
//   Cancel button for save_project and export jobs (POST cancel endpoint).
//   Cancel button with "best-effort" tooltip for reload_ocr_page.
//   No cancel button for refine_bboxes_page / expand_refine_bboxes_page /
//   refine_bboxes_project.

import { useMutation } from "@tanstack/react-query";
import { OperationStatusPanel } from "@pdomain/pdomain-ui/status";
import type { components } from "../api/types";

type Job = components["schemas"]["Job"];
type JobType = components["schemas"]["JobType"];

/** Job types that support real cooperative cancel. */
const CANCELLABLE = new Set<JobType>(["save_project", "export"]);

/** Job type that has cancel button but with "best-effort" warning. */
const BEST_EFFORT_CANCEL = new Set<JobType>(["reload_ocr_page"]);

interface BusyOverlayProps {
  /** The currently active running job, if any. */
  activeJob: Job | null;
  /** True when a page/project mutation is in-flight. */
  isMutating?: boolean;
  /** Called when cancel button is clicked (override for testing). */
  onCancel?: () => void;
}

export function BusyOverlay({ activeJob, isMutating = false, onCancel }: BusyOverlayProps) {
  const visible = isMutating || activeJob !== null;

  const cancelMutation = useMutation({
    mutationFn: async (jobId: string) => {
      const res = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, { method: "POST" });
      if (!res.ok) throw new Error("Cancel failed");
      return res.json() as Promise<unknown>;
    },
  });

  if (!visible) return null;

  const jobType = activeJob?.type;
  const showCancel =
    jobType != null && (CANCELLABLE.has(jobType) || BEST_EFFORT_CANCEL.has(jobType));
  const isBestEffort = jobType != null && BEST_EFFORT_CANCEL.has(jobType);

  const message = activeJob?.progress?.message ?? "Working…";

  function handleCancel() {
    if (onCancel) {
      onCancel();
      return;
    }
    if (activeJob) {
      cancelMutation.mutate(activeJob.id);
    }
  }

  const cancelButton = showCancel ? (
    <button
      data-testid="busy-overlay-cancel"
      className="px-3 py-1.5 text-sm rounded border border-border-2 hover:bg-bg-raised disabled:opacity-50"
      onClick={handleCancel}
      disabled={cancelMutation.isPending}
      title={isBestEffort ? "Cancel (best-effort — OCR may not stop immediately)" : undefined}
    >
      Cancel
    </button>
  ) : undefined;

  return (
    // NOTE: data-testid MUST remain on this outer div (not on BlockingOperationOverlay
    // from pdui) because: (1) driver contract requires "busy-overlay" in DOM, and
    // (2) ProjectPage.test.tsx asserts imagePaneEl.contains(getByTestId("busy-overlay")).
    // BlockingOperationOverlay uses Radix Dialog.Portal which escapes to document.body,
    // breaking the containment assertion. OperationStatusPanel renders in-place (no portal).
    <div
      data-testid="busy-overlay"
      className="fixed inset-0 z-40 bg-black/30 backdrop-blur-sm flex items-center justify-center"
      aria-label="Operation in progress"
    >
      <OperationStatusPanel
        title="Working…"
        message={message}
        state="running"
        primaryAction={cancelButton}
      />
    </div>
  );
}

interface ProjectLoadingOverlayProps {
  /** True while the project is being fetched/loaded. */
  isLoading: boolean;
}

export function ProjectLoadingOverlay({ isLoading }: ProjectLoadingOverlayProps) {
  if (!isLoading) return null;

  return (
    // NOTE: data-testid MUST remain on this outer div — driver contract requires
    // "project-loading-overlay" testid. See BusyOverlay comment above for rationale.
    <div
      data-testid="project-loading-overlay"
      className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex items-center justify-center"
      aria-label="Loading project"
    >
      <OperationStatusPanel title="Loading project" message="Loading project…" state="running" />
    </div>
  );
}

// BusyOverlay.tsx — full-page busy overlay shown during active mutations or jobs.
// ProjectLoadingOverlay — higher z-index overlay specifically for project load.
//
// Spec: docs/specs/2026-05-12-notifications-design.md §BusyOverlay logic
// Issue #232
//
// BusyOverlay logic:
//   visible when isMutating prop is true OR activeJob is non-null.
//   Cancel button for save_project and export jobs (POST cancel endpoint).
//   Cancel button with "best-effort" tooltip for reload_ocr_page.
//   No cancel button for refine_bboxes_page / expand_refine_bboxes_page /
//   refine_bboxes_project.

import { useMutation } from "@tanstack/react-query";
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
      const res = await fetch(`/api/jobs/${jobId}/cancel`, { method: "POST" });
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

  return (
    <div
      data-testid="busy-overlay"
      className="fixed inset-0 z-40 bg-black/30 backdrop-blur-sm flex items-center justify-center"
      aria-live="polite"
      aria-label="Operation in progress"
    >
      <div className="bg-bg-surface rounded-lg border border-border-2 p-6 flex flex-col items-center gap-4 min-w-64">
        {/* Spinner */}
        <svg
          className="animate-spin h-8 w-8 text-accent"
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <circle
            className="opacity-25"
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            strokeWidth="4"
          />
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
          />
        </svg>
        <p className="text-sm text-ink-2 text-center">{message}</p>
        {showCancel && (
          <button
            data-testid="busy-overlay-cancel"
            className="px-3 py-1.5 text-sm rounded border border-border-2 hover:bg-bg-raised disabled:opacity-50"
            onClick={handleCancel}
            disabled={cancelMutation.isPending}
            title={isBestEffort ? "Cancel (best-effort — OCR may not stop immediately)" : undefined}
          >
            Cancel
          </button>
        )}
      </div>
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
    <div
      data-testid="project-loading-overlay"
      className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex items-center justify-center"
      aria-live="polite"
      aria-label="Loading project"
    >
      <div className="bg-bg-surface rounded-lg border border-border-2 p-6 flex flex-col items-center gap-3">
        <svg
          className="animate-spin h-8 w-8 text-accent"
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <circle
            className="opacity-25"
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            strokeWidth="4"
          />
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
          />
        </svg>
        <p className="text-sm text-ink-2">Loading project…</p>
      </div>
    </div>
  );
}

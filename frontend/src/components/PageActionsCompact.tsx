// PageActionsCompact.tsx — compact header action buttons for the header slot.
//
// IS-2: Lives in HeaderBar's actionsSlot when on a project route.
// P1.b (Gap 4, 7): Shows Reload OCR | Rematch GT | ✓ Save page | Export ▾
// styled as labelled header buttons (design-token classes, 28px height).
//
// Receives projectId + pageIndex as props (resolved by AppShell via
// useRouteProjectContext / useMatch, which works outside <Routes>).
// The full PageActions bar (with all driver-contract testids) remains
// mounted hidden inside ProjectPage for driver compatibility.

import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useReloadOcr, useSavePage, useRematchGt } from "../hooks/usePageMutations";
import { useJobProgress } from "../hooks/useJobProgress";
import { dialogStore } from "../stores/dialog-store";
import { toast } from "../lib/toast";

export interface PageActionsCompactProps {
  projectId: string;
  pageIndex: number;
}

export function PageActionsCompact({ projectId, pageIndex }: PageActionsCompactProps) {
  const qc = useQueryClient();

  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const jobProgress = useJobProgress(activeJobId);

  // Toast lifecycle: react to OCR job progress transitions.
  // Rematch GT is synchronous (no SSE job) so it uses onSuccess/onError directly.
  useEffect(() => {
    if (!activeJobId || jobProgress === null) return;

    if (jobProgress.status === "complete") {
      toast.success("OCR complete", { id: activeJobId });
      void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
      setActiveJobId(null);
    } else if (jobProgress.status === "error") {
      toast.error("OCR failed", { id: activeJobId });
      setActiveJobId(null);
    } else {
      // Running — update loading toast with current progress message.
      const msg = jobProgress.progress?.message ?? "Running OCR…";
      void import("sonner").then(({ toast: sonnerToast }) => {
        sonnerToast.loading(msg, { id: activeJobId });
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobProgress?.status, activeJobId]);

  const reloadOcr = useReloadOcr(projectId, pageIndex);
  const savePage = useSavePage(projectId, pageIndex);
  const rematchGt = useRematchGt(projectId, pageIndex);

  const isBusy =
    reloadOcr.isPending ||
    savePage.isPending ||
    rematchGt.isPending ||
    (jobProgress !== null && jobProgress.status !== "complete" && jobProgress.status !== "error");

  function handleReloadOcr() {
    reloadOcr.mutate(undefined, {
      onSuccess: (data) => {
        if (data?.job_id) {
          setActiveJobId(data.job_id);
          // Show initial loading toast immediately while SSE stream opens.
          void import("sonner").then(({ toast: sonnerToast }) => {
            sonnerToast.loading("Running OCR…", { id: data.job_id });
          });
        }
      },
      onError: () => {
        toast.error("Failed to start OCR");
      },
    });
  }

  function handleSavePage() {
    savePage.mutate(undefined, {
      onSuccess: () => {
        toast.success("Page saved");
      },
      onError: () => {
        toast.error("Save failed");
      },
      onSettled: () => {
        void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
      },
    });
  }

  function handleRematchGt() {
    rematchGt.mutate(undefined, {
      onSuccess: () => {
        // Rematch GT is synchronous — no job_id, just a direct page payload.
        toast.success("Rematch GT complete");
        void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
      },
      onError: () => {
        toast.error("Rematch GT failed");
      },
    });
  }

  function handleExport() {
    dialogStore.open("export");
  }

  const base =
    "flex items-center gap-1 h-7 px-2.5 rounded border text-[11px] font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed";
  const normal = "border-border-2 bg-bg-raised text-ink-2 hover:bg-bg-surface hover:text-ink-1";
  const accentBtn =
    "border-border-2 bg-bg-raised text-accent hover:border-accent hover:text-accent-ink hover:bg-accent";

  const disabled = isBusy || !projectId;

  /** Inline spinner — shown while this button's job is running. */
  const Spinner = () => (
    <svg
      className="animate-spin h-3 w-3 shrink-0"
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
      />
    </svg>
  );

  // Spinner is shown on the Reload OCR button while the SSE job is in flight.
  const ocrRunning = activeJobId !== null && isBusy;
  // Rematch is synchronous — show spinner while the mutation is pending.
  const rematchRunning = rematchGt.isPending;

  return (
    <div
      data-testid="page-actions-compact"
      className="flex items-center gap-1 shrink-0"
      aria-label="Page actions"
    >
      <button
        type="button"
        data-testid="page-actions-compact-reload-ocr"
        aria-label="Reload OCR"
        disabled={disabled}
        onClick={handleReloadOcr}
        title="Reload OCR (Ctrl+R)"
        className={`${base} ${normal}`}
      >
        {ocrRunning && <Spinner />}
        Reload OCR
      </button>

      <button
        type="button"
        data-testid="page-actions-compact-rematch-gt"
        aria-label="Rematch GT"
        disabled={disabled}
        onClick={handleRematchGt}
        title="Rematch GT (Ctrl+G)"
        className={`${base} ${normal}`}
      >
        {rematchRunning && <Spinner />}
        Rematch
      </button>

      <button
        type="button"
        data-testid="page-actions-compact-save-page"
        aria-label="Save page (Ctrl+S)"
        disabled={disabled}
        onClick={handleSavePage}
        title="Save page (Ctrl+S)"
        className={`${base} ${accentBtn}`}
      >
        <span aria-hidden="true">✓</span>
        <span>Save page</span>
      </button>

      <button
        type="button"
        data-testid="page-actions-compact-export"
        aria-label="Export"
        disabled={disabled}
        onClick={handleExport}
        title="Export (E)"
        className={`${base} ${normal}`}
      >
        Export
        <span aria-hidden="true" className="text-[9px] opacity-70">
          ▾
        </span>
      </button>
    </div>
  );
}

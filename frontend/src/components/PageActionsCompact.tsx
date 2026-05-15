// PageActionsCompact.tsx — 2-button header slot for the most-used page actions.
//
// IS-2: Lives in HeaderBar's actionsSlot when on a project route. Shows only
// Reload OCR and Save Page as small icon buttons. The full PageActions bar
// (with all driver-contract testids) remains mounted hidden inside
// ProjectPage for driver compatibility.
//
// Self-contained: reads projectId + pageIndex from URL params directly.

import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { useReloadOcr, useSavePage } from "../hooks/usePageMutations";
import { useJobProgress } from "../hooks/useJobProgress";

export function PageActionsCompact() {
  const { projectId, pageNo } = useParams<{ projectId: string; pageNo: string }>();
  const qc = useQueryClient();

  const idx0 = useMemo(() => {
    const n = parseInt(pageNo ?? "1", 10);
    return Number.isFinite(n) && n > 0 ? n - 1 : 0;
  }, [pageNo]);

  const pid = projectId ?? "";

  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const jobProgress = useJobProgress(activeJobId);

  const reloadOcr = useReloadOcr(pid, idx0);
  const savePage = useSavePage(pid, idx0);

  const isBusy =
    reloadOcr.isPending ||
    savePage.isPending ||
    (jobProgress !== null && jobProgress.status !== "complete" && jobProgress.status !== "error");

  function handleReloadOcr() {
    if (!projectId) return;
    reloadOcr.mutate(undefined, {
      onSuccess: (data) => {
        if (data?.job_id) setActiveJobId(data.job_id);
      },
      onSettled: () => {
        void qc.invalidateQueries({ queryKey: ["page", projectId, idx0] });
      },
    });
  }

  function handleSavePage() {
    if (!projectId) return;
    savePage.mutate(undefined, {
      onSettled: () => {
        void qc.invalidateQueries({ queryKey: ["page", projectId, idx0] });
      },
    });
  }

  return (
    <div data-testid="page-actions-compact" className="flex items-center gap-1 shrink-0">
      <button
        type="button"
        data-testid="page-actions-compact-reload-ocr"
        aria-label="Reload OCR"
        disabled={isBusy || !projectId}
        onClick={handleReloadOcr}
        title="Reload OCR"
        className="px-2 py-0.5 text-xs rounded border border-border-2 bg-bg-raised text-ink-2 hover:bg-bg-surface disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
      >
        ↺ OCR
      </button>

      <button
        type="button"
        data-testid="page-actions-compact-save-page"
        aria-label="Save Page"
        disabled={isBusy || !projectId}
        onClick={handleSavePage}
        title="Save Page"
        className="px-2 py-0.5 text-xs rounded border border-border-2 bg-bg-raised text-ink-2 hover:bg-bg-surface disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
      >
        &#10003; Save
      </button>
    </div>
  );
}

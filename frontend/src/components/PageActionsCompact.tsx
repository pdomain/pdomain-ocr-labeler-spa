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

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useReloadOcr, useSavePage, useRematchGt } from "../hooks/usePageMutations";
import { useJobProgress } from "../hooks/useJobProgress";
import { dialogStore } from "../stores/dialog-store";

export interface PageActionsCompactProps {
  projectId: string;
  pageIndex: number;
}

export function PageActionsCompact({ projectId, pageIndex }: PageActionsCompactProps) {
  const qc = useQueryClient();

  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const jobProgress = useJobProgress(activeJobId);

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
        if (data?.job_id) setActiveJobId(data.job_id);
      },
      onSettled: () => {
        void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
      },
    });
  }

  function handleSavePage() {
    savePage.mutate(undefined, {
      onSettled: () => {
        void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
      },
    });
  }

  function handleRematchGt() {
    rematchGt.mutate(undefined, {
      onSettled: () => {
        void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
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

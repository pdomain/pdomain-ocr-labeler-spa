// BulkActions.tsx — Bulk actions bar for multi-selected worklist items.
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 23.
//
// Appears at the bottom of the Worklist when selectedIds.length > 0.
// Buttons: "Mark all reviewed", "Re-run match", "Export filtered".
// Fires jobs via the validate-batch and export endpoints;
// progress via useJobProgress.
//
// data-testids:
//   bulk-actions              — outer container (rendered when count > 0; absent otherwise)
//   bulk-actions-count        — "N selected" label
//   bulk-actions-clear        — clear selection button
//   bulk-actions-mark-reviewed — "Mark all reviewed" button
//   bulk-actions-rerun-match  — "Re-run match" button
//   bulk-actions-export       — "Export filtered" button

import { useSyncExternalStore, useState } from "react";
import { toast } from "sonner";
import { worklistStore } from "../../stores/worklist-store";
import { useJobProgress } from "../../hooks/useJobProgress";
import { cn } from "@/lib/utils";

// ─── store bridge ─────────────────────────────────────────────────────────

function subscribeWorklist(cb: () => void): () => void {
  return worklistStore.subscribe(cb);
}
function getWorklistSnapshot() {
  return worklistStore.getState();
}

// ─── job helpers ──────────────────────────────────────────────────────────

async function apiPost<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    let message = res.statusText;
    try {
      const parsed = JSON.parse(text) as { message?: string };
      if (parsed.message) message = parsed.message;
    } catch {
      if (text) message = text;
    }
    throw Object.assign(new Error(message), { status: res.status });
  }
  return res.json() as Promise<T>;
}

// ─── BulkActions ─────────────────────────────────────────────────────────

export interface BulkActionsProps {
  projectId: string;
  pageIndex: number;
}

export function BulkActions({ projectId, pageIndex }: BulkActionsProps) {
  const state = useSyncExternalStore(subscribeWorklist, getWorklistSnapshot, getWorklistSnapshot);

  const [jobId, setJobId] = useState<string | null>(null);
  const jobProgress = useJobProgress(jobId);

  const { selectedIds } = state;
  const count = selectedIds.length;

  async function handleMarkReviewed() {
    try {
      const body = {
        scope: "line",
        line_indices: selectedIds,
        word_indices: [],
        paragraph_indices: [],
        validated: true,
      };
      await apiPost<unknown>(
        `/api/projects/${encodeURIComponent(projectId)}/pages/${encodeURIComponent(String(pageIndex))}/words/validate-batch`,
        body,
      );
      worklistStore.clearBulk();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Mark reviewed failed");
    }
  }

  async function handleRerunMatch() {
    try {
      const res = await apiPost<{ job_id: string }>(
        `/api/projects/${encodeURIComponent(projectId)}/pages/${encodeURIComponent(String(pageIndex))}/reload-ocr`,
        { use_edited_image: false },
      );
      setJobId(res.job_id);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Re-run match failed");
    }
  }

  async function handleExport() {
    try {
      const body = {
        scope: "current",
        page_index: pageIndex,
        style_filters: [],
        include_classification: false,
        detection_only: false,
        normalize_recognition_labels: false,
      };
      const res = await apiPost<{ job_id: string }>(
        `/api/projects/${encodeURIComponent(projectId)}/export`,
        body,
      );
      setJobId(res.job_id);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Export failed");
    }
  }

  const isBusy =
    jobProgress !== null && jobProgress.status !== "complete" && jobProgress.status !== "error";

  return (
    <div
      data-testid="bulk-actions"
      className="flex-shrink-0 border-t border-border-1 bg-bg-surface px-3 py-2 flex flex-col gap-2"
    >
      {/* Selection header — only when items are selected */}
      {count > 0 && (
        <div className="flex items-center justify-between">
          <span data-testid="bulk-actions-count" className="text-[11px] text-ink-2">
            {count} selected
          </span>
          <button
            type="button"
            data-testid="bulk-actions-clear"
            onClick={() => {
              worklistStore.clearBulk();
            }}
            className="text-[10px] text-ink-3 hover:text-ink-1 transition-colors"
          >
            Clear
          </button>
        </div>
      )}

      {/* Action buttons */}
      <div className="flex gap-1.5 flex-wrap">
        {/* Selection-scoped action — only enabled when items are selected */}
        <button
          type="button"
          data-testid="bulk-actions-mark-reviewed"
          disabled={isBusy || count === 0}
          onClick={() => void handleMarkReviewed()}
          className={cn(
            "text-[11px] px-2 py-1 rounded border transition-colors",
            "bg-bg-raised text-ink-2 border-border-2 hover:border-accent hover:text-ink-1",
            "disabled:opacity-40 disabled:pointer-events-none",
          )}
        >
          Mark all reviewed
        </button>
        <button
          type="button"
          data-testid="bulk-actions-rerun-match"
          disabled={isBusy}
          onClick={() => void handleRerunMatch()}
          className={cn(
            "text-[11px] px-2 py-1 rounded border transition-colors",
            "bg-bg-raised text-ink-2 border-border-2 hover:border-accent hover:text-ink-1",
            "disabled:opacity-40 disabled:pointer-events-none",
          )}
        >
          Re-run match
        </button>
        <button
          type="button"
          data-testid="bulk-actions-export"
          disabled={isBusy}
          onClick={() => void handleExport()}
          className={cn(
            "text-[11px] px-2 py-1 rounded border transition-colors",
            "bg-bg-raised text-ink-2 border-border-2 hover:border-accent hover:text-ink-1",
            "disabled:opacity-40 disabled:pointer-events-none",
          )}
        >
          Export filtered
        </button>
      </div>

      {/* Progress indicator */}
      {jobProgress && (
        <div className="text-[10px] text-ink-3">
          {jobProgress.status === "complete"
            ? "Done."
            : jobProgress.status === "error"
              ? `Error: ${jobProgress.error_message ?? "unknown"}`
              : (jobProgress.progress?.message ?? "Running…")}
        </div>
      )}
    </div>
  );
}

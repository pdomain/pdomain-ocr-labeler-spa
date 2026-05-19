// useJobCompletionInvalidation.ts — shared SSE-terminal-status side effect.
//
// Bug fix scaffolding for #377: the toolbar Reload OCR button (handled in
// ProjectPage.handleReloadOcr) only invalidated the page query via the
// mutation's onSettled — that fires on the 202 response, long before OCR
// has actually run. The compact action bar in PageActionsCompact already
// had the correct pattern inlined as a useEffect: watch
// `jobProgress?.status` and, on terminal status, invalidate the page
// query and reset the active job id.
//
// This hook extracts that pattern so both call sites use the same logic.
// Call-site-specific concerns (toast text, etc.) stay at the call site
// via the optional `onComplete` / `onError` callbacks; the hook itself
// only owns invalidation + active-job-id reset.

import { useEffect } from "react";
import { useQueryClient, type QueryKey } from "@tanstack/react-query";

import type { JobProgressEvent } from "./useJobProgress";

export interface UseJobCompletionInvalidationOptions {
  /**
   * Currently-tracked SSE job id, or null when no job is in flight. When
   * non-null and `jobProgress.status` reaches a terminal value, the hook
   * fires the invalidation and then calls `setActiveJobId(null)` to clear
   * the tracker so subsequent renders don't re-fire.
   */
  activeJobId: string | null;

  /**
   * Latest SSE progress event from `useJobProgress(activeJobId)`. May be
   * null if the EventSource hasn't yielded an event yet.
   */
  jobProgress: JobProgressEvent | null;

  /**
   * Setter for the active job id — called with `null` once a terminal
   * status has been observed. Pass the `setActiveJobId` from the same
   * `useState` that produced `activeJobId`.
   */
  setActiveJobId: (id: string | null) => void;

  /**
   * Query key to invalidate on `status === "complete"`. Typically
   * `["page", projectId, pageIndex]`.
   */
  invalidationKey: QueryKey;

  /**
   * Optional callback fired once on the `"complete"` transition, after
   * the invalidation has been queued. Use for success-toast text or
   * other call-site-specific finalisation. The job id is passed through
   * so the caller can address an existing loading toast by id.
   */
  onComplete?: (jobId: string) => void;

  /**
   * Optional callback fired once on the `"error"` transition. The job id
   * is passed through; `errorMessage` is `jobProgress.error_message`
   * when the backend supplied one, otherwise null.
   */
  onError?: (jobId: string, errorMessage: string | null) => void;

  /**
   * Optional callback fired on each non-terminal `"running"` update, so
   * the call site can refresh a loading toast / progress indicator. The
   * latest event is passed through verbatim.
   */
  onRunning?: (jobId: string, event: JobProgressEvent) => void;
}

/**
 * Subscribe an active SSE job to a query-cache invalidation on completion.
 *
 * Mirrors the inline useEffect that previously lived at
 * `PageActionsCompact.tsx:32-50` so the same lifecycle can be reused by
 * any component that holds an `activeJobId` and the matching
 * `useJobProgress` result. The hook handles only:
 *
 *   1. invalidating `invalidationKey` once on `status === "complete"`,
 *   2. clearing `activeJobId` once a terminal status (`complete` /
 *      `error`) has been observed.
 *
 * Toast lifecycle and other call-site-specific behaviour stay at the
 * call site via `onComplete` / `onError` / `onRunning`.
 */
export function useJobCompletionInvalidation({
  activeJobId,
  jobProgress,
  setActiveJobId,
  invalidationKey,
  onComplete,
  onError,
  onRunning,
}: UseJobCompletionInvalidationOptions): void {
  const qc = useQueryClient();

  useEffect(() => {
    if (!activeJobId || jobProgress === null) return;

    if (jobProgress.status === "complete") {
      void qc.invalidateQueries({ queryKey: invalidationKey });
      onComplete?.(activeJobId);
      setActiveJobId(null);
    } else if (jobProgress.status === "error") {
      onError?.(activeJobId, jobProgress.error_message ?? null);
      setActiveJobId(null);
    } else {
      onRunning?.(activeJobId, jobProgress);
    }
    // The hook is keyed on the status transition + active job id; the
    // callbacks and query key are intentionally omitted so an unstable
    // identity at the call site doesn't re-fire the effect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobProgress?.status, activeJobId]);
}

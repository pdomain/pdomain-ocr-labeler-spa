// useCancelJob.ts — shared cooperative-cancel POST for a running job.
//
// Wraps `POST /api/jobs/{jobId}/cancel` (Wave 3a / P1-CANCEL) behind one
// TanStack mutation so every UI surface that offers a Cancel button —
// BusyOverlay's `busy-overlay-cancel` and the book-scoped run toasts in
// PageActionsCompact (Propose page kinds / Propose regions / Auto-rotate
// all) — sends the exact same request instead of each hand-rolling its own
// `fetch`.
//
// Plan: docs/plans/2026-09-17-region-review-surface.md — P1-CANCEL
// reachability half. Backend cooperative-cancel support and the
// `BusyOverlay` `CANCELLABLE` policy set landed first; this hook is what
// lets the book-scoped runs (which never route through `BusyOverlay`) reach
// the same endpoint.

import { useRef } from "react";
import { useMutation, type UseMutationResult } from "@tanstack/react-query";

async function postCancel(jobId: string): Promise<unknown> {
  const res = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, { method: "POST" });
  if (!res.ok) throw new Error("Cancel failed");
  return res.json() as Promise<unknown>;
}

export interface UseCancelJobResult {
  /** The underlying TanStack mutation, exposed for `isPending` / `isError`. */
  mutation: UseMutationResult<unknown, Error, string>;
  /**
   * Request cancellation of `jobId`. A no-op — no second POST — if this
   * hook instance has already requested cancellation for that exact job id.
   *
   * The guard is a ref-backed set, not `mutation.isPending`: `isPending` is
   * a value snapshot captured at render time, so two clicks fired before
   * React re-renders (a real double-click, and how a test invoking the same
   * captured `onClick` twice behaves) would both still see the same stale
   * `isPending === false` and both would call `mutate`.
   */
  cancel: (jobId: string) => void;
  /** True once `cancel(jobId)` has fired for this exact job id. */
  wasRequested: (jobId: string) => boolean;
}

/** Cooperative-cancel POST, shared by every Cancel button in the app. */
export function useCancelJob(): UseCancelJobResult {
  const requested = useRef<Set<string>>(new Set());
  const mutation = useMutation({
    mutationFn: postCancel,
  });

  function cancel(jobId: string): void {
    if (requested.current.has(jobId)) return;
    requested.current.add(jobId);
    mutation.mutate(jobId);
  }

  function wasRequested(jobId: string): boolean {
    return requested.current.has(jobId);
  }

  return { mutation, cancel, wasRequested };
}

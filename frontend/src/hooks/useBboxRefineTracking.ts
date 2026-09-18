// useBboxRefineTracking.ts — hoists the refine_bboxes job tracker for
// BBoxSection out of the accordion-gated component tree.
//
// Review finding 3 (docs/issues/2026-07-21-bbox-refine-crop-misleading.md,
// P1-BBOX-UI follow-up): BBoxSection lives inside a Radix Accordion.Content
// that unmounts when the "Bounding Box" item collapses. When the job
// tracker (useJobProgress + useJobCompletionInvalidation) lived inside
// BBoxSection itself, collapsing the accordion mid-job closed the SSE
// connection and dropped the terminal event — the completed refine never
// invalidated the page query, so the UI never picked up the new bbox until
// something unrelated refetched it.
//
// ProjectPage owns this (not WordDetail): WordDetail itself unmounts
// whenever the selection drops back to "none" (deselecting the word
// entirely), an even easier way to lose tracking than collapsing one
// accordion item. ProjectPage is the only component in this tree that
// stays mounted for the whole project-page session, and it already owns
// job tracking for every other job type here (its own `activeJobId` /
// `trackJob`, wired to `useJobCompletionInvalidation` — see ProjectPage.tsx
// "Terminal-status invalidation"). This hook is the same pattern, factored
// out into its own state slot: bbox refine is scoped to a dynamic word
// rather than a fixed action type, and ProjectPage's existing `activeJobId`
// is a single shared slot already used by several other actions (reload
// OCR, save page, rotate, …) — reusing it here would let an unrelated
// toolbar action silently steal the slot mid-refine, and vice versa.
//
// Toast lifecycle lives here too (not at the BBoxSection call site): the
// call site can unmount mid-job (that's the whole bug this hook fixes), so
// it cannot be trusted to still be around to show the terminal toast.

import { useState } from "react";
import { useJobProgress, type JobProgressEvent } from "./useJobProgress";
import { useJobCompletionInvalidation } from "./useJobCompletionInvalidation";
import { toast } from "../lib/toast";

export interface BboxRefineOutcome {
  /** `${line_index}-${word_index}` — matches BBoxSection's own `wordKey`. */
  wordKey: string;
  /** `result.refined` from the terminal job event. 0 means a real no-op —
   * see the "refine no-ops without an attached OCR image" note in
   * BBoxSection.tsx. */
  refined: number;
  /** Monotonically increasing — lets a consumer distinguish two outcomes
   * that happen to carry the same `refined` count. */
  token: number;
}

export interface UseBboxRefineTrackingResult {
  /** The in-flight refine_bboxes job id, or null when none is running. */
  jobId: string | null;
  /** Which word (`${line_index}-${word_index}`) the in-flight job belongs
   * to. Stays set only while `jobId` is non-null. */
  wordKey: string | null;
  /** The most recent terminal outcome for any word. A consumer checks
   * `outcome.wordKey` against its own word key before acting on it. */
  outcome: BboxRefineOutcome | null;
  /** Call once a refine POST returns 202 + job_id. */
  start: (jobId: string, wordKey: string) => void;
}

/** Read `result.refined` off a terminal job event as a number, defaulting
 * to 0 (no-op) for a missing or non-numeric field. */
function readRefinedCount(event: JobProgressEvent): number {
  const raw = event.result?.refined;
  return typeof raw === "number" ? raw : 0;
}

/**
 * Owns the refine_bboxes job lifecycle for BBoxSection's Refine /
 * Expand+Refine / Expand buttons. Call this once from an always-mounted
 * ancestor (ProjectPage) and pass the result down as a prop; BBoxSection
 * only calls `start` and reads the result back, so an accordion collapse
 * or word deselection never drops the terminal SSE event.
 */
export function useBboxRefineTracking(
  projectId: string | undefined,
  pageIndex: number | undefined,
): UseBboxRefineTrackingResult {
  const [jobId, setJobId] = useState<string | null>(null);
  const [wordKey, setWordKey] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<BboxRefineOutcome | null>(null);
  const jobProgress = useJobProgress(jobId);

  useJobCompletionInvalidation({
    activeJobId: jobId,
    jobProgress,
    setActiveJobId: (id) => {
      setJobId(id);
      if (id === null) setWordKey(null);
    },
    invalidationKey: ["page", projectId, pageIndex],
    onComplete: (id, event) => {
      const refined = readRefinedCount(event);
      if (refined > 0) {
        toast.success(
          `Bbox refine complete (${String(refined)} word${refined === 1 ? "" : "s"} updated)`,
          { id },
        );
        if (wordKey) {
          setOutcome((prev) => ({ wordKey, refined, token: (prev?.token ?? 0) + 1 }));
        }
      } else {
        toast.warn("Bbox refine ran, but nothing changed.", { id });
      }
    },
    onError: (id, errorMessage) => {
      toast.error(errorMessage ?? "Bbox refine failed", { id });
    },
    // refine_bboxes is not in the backend's cancellable set — no Cancel
    // action is offered, so this is not expected in practice, but the
    // transition is still handled for completeness.
    onCancelled: (id, event) => {
      toast.warn(event.progress.message || "Bbox refine cancelled", { id });
    },
    onRunning: (id, event) => {
      const msg = event.progress.message || "Refining bbox…";
      void import("sonner").then(({ toast: sonnerToast }) => {
        sonnerToast.loading(msg, { id });
      });
    },
  });

  function start(newJobId: string, newWordKey: string): void {
    setJobId(newJobId);
    setWordKey(newWordKey);
  }

  return { jobId, wordKey, outcome, start };
}

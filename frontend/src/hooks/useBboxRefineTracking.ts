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
//
// Review round 2, finding 1: ProjectPage — the sole owner of this hook — is
// reused across page and project navigation (React Router keeps the same
// component instance; only its route params change), so `projectId` /
// `pageIndex` are live values that can drift out from under an in-flight
// job. `start()` captures them at call time into `word` (below); every
// later read (the invalidation key, the outcome's word) uses that captured
// value, never this hook's own current parameters. Without this, starting
// a refine on page 3 and navigating to page 4 before it completes would
// invalidate page 4 (leaving page 3, the page the job actually changed,
// stale) and would expose a bare `wordKey` string cheap enough for a
// same-indexed word on page 4 to collide with.

import { useEffect, useState } from "react";
import { useJobProgress, type JobProgressEvent } from "./useJobProgress";
import { useJobCompletionInvalidation } from "./useJobCompletionInvalidation";
import { toast } from "../lib/toast";

/**
 * How long a refine_bboxes job may run before this tracker gives up on it,
 * clears its slot, and warns (review round 2, finding 3). Measured from the
 * job's own first "running" status, not from `start()` / the 202 (review
 * round 3, finding 1) — the runner drains one job at a time
 * (core/jobs/runner.py's `run_forever`), so a slow job already in flight
 * (an export, a save project) can hold this one QUEUED well past any
 * window measured from submission. `handle_refine_bboxes` runs
 * synchronously, in-process, against a single word, with no OCR engine
 * call involved, once it actually starts — normal completion from there is
 * well under a second. 30s is generous enough to never false-positive on a
 * slow but genuine run, while still recovering in a realistic time from an
 * SSE drop, a server restart mid-job, or any other way the terminal event
 * never arrives after the job starts — refine_bboxes is not cancellable,
 * so without this a stuck job would otherwise claim this tracker's one
 * slot forever.
 */
const STALL_TIMEOUT_MS = 30_000;

/** Identifies which word, on which page of which project, a refine job or
 * outcome belongs to. */
export interface BboxWordRef {
  projectId: string;
  pageIndex: number;
  /** `${line_index}-${word_index}` within that page. */
  wordKey: string;
}

export interface BboxRefineOutcome {
  word: BboxWordRef;
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
  /** Which word the in-flight job belongs to — the project/page/word
   * captured when `start()` was called, not this hook's current
   * parameters. Stays set only while `jobId` is non-null. */
  word: BboxWordRef | null;
  /** The most recent terminal outcome for any word. A consumer compares
   * `outcome.word` against its own (projectId, pageIndex, wordKey) before
   * acting on it. */
  outcome: BboxRefineOutcome | null;
  /** Call once a refine POST returns 202 + job_id, passing this word's
   * local `${line_index}-${word_index}` key. Captures this hook's current
   * `projectId` / `pageIndex` at the moment of the call. */
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
  const [word, setWord] = useState<BboxWordRef | null>(null);
  const [outcome, setOutcome] = useState<BboxRefineOutcome | null>(null);
  const jobProgress = useJobProgress(jobId);

  useJobCompletionInvalidation({
    activeJobId: jobId,
    jobProgress,
    setActiveJobId: (id) => {
      setJobId(id);
      if (id === null) setWord(null);
    },
    // `word` here is still the value captured by `start()` — this render
    // (the one where `jobProgress.status` first reads "complete") runs
    // before `setWord(null)` above ever fires, so this key always names
    // the page the job actually started on, never this hook's current
    // (possibly since-navigated-away-from) `projectId` / `pageIndex`.
    invalidationKey: ["page", word?.projectId, word?.pageIndex],
    onComplete: (id, event) => {
      const refined = readRefinedCount(event);
      if (refined > 0) {
        toast.success(
          `Bbox refine complete (${String(refined)} word${refined === 1 ? "" : "s"} updated)`,
          { id },
        );
        if (word) {
          setOutcome((prev) => ({ word, refined, token: (prev?.token ?? 0) + 1 }));
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

  // Review round 2, finding 3 / round 3, finding 1: give up on a job that
  // starts running and then goes silent — see STALL_TIMEOUT_MS above for
  // why 30s and why it's measured from "running", not from `start()`. A
  // job still QUEUED behind an earlier one in the runner (see
  // core/jobs/runner.py's single-worker `run_forever`) has not started
  // yet, so it isn't stalled — timing it out here would clear the slot and
  // close the SSE subscription while the job is still genuinely in the
  // queue, then let a retry start a second job racing the first, and leave
  // nobody listening when the first one eventually completes and changes
  // the box. `isRunning` only reflects the SSE-reported status — no
  // separate "still queued" timer is started for it, on purpose: the
  // runner queue has no bound of its own, and this component has no way to
  // tell "a slow job ahead of it" apart from "stuck forever" while queued.
  // `isRunning` is a plain boolean, so multiple "running" progress ticks
  // (refine_bboxes reports none in practice; the handler is synchronous
  // with no sub-progress) don't restart the timer — it's one 30s window
  // from the first running signal. The effect's own cleanup cancels the
  // pending timer once the job leaves "running" for any reason (a normal
  // completion, or the slot clearing), so this never fires for a job that
  // resolves in time.
  const isRunning = jobId !== null && jobProgress?.status === "running";
  useEffect(() => {
    if (!isRunning) return;
    const timer = setTimeout(() => {
      setJobId(null);
      setWord(null);
      toast.warn("Bbox refine timed out — try again.", { id: jobId });
    }, STALL_TIMEOUT_MS);
    return () => {
      clearTimeout(timer);
    };
    // `jobId` is listed for the toast id it reads, alongside `isRunning`
    // (the actual gate). Every `jobProgress` update produces a new event
    // object, but `isRunning` collapses that to a stable boolean, so
    // repeated "running" ticks for the same job (refine_bboxes reports
    // none in practice — the handler is synchronous with no sub-progress)
    // don't restart the timer; it stays one 30s window from the first
    // running signal.
  }, [isRunning, jobId]);

  function start(newJobId: string, newWordKey: string): void {
    if (projectId === undefined || pageIndex === undefined) return;
    setJobId(newJobId);
    setWord({ projectId, pageIndex, wordKey: newWordKey });
  }

  return { jobId, word, outcome, start };
}

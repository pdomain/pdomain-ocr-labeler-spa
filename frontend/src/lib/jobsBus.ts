// jobsBus.ts — minimal in-process signal so a job-tracking hook can tell
// the shared jobs list (useJobsList) to refresh itself immediately.
//
// Why this exists (docs/plans/2026-07-21-pgdp-alignment-remaining.md item 4):
// useJobsList only polls GET /api/jobs while its last-known snapshot already
// contains a queued/running job — see that hook's file header for why. That
// leaves one gap: nothing polls while the app is idle, so a *newly created*
// job needs some other way to be discovered right away. Every job-starting
// call site in this app already calls useJobProgress(jobId) the instant it
// gets a job id back (ExportDialog, PageActionsCompact, ProjectPage,
// BulkActions, useBboxRefineTracking — 7 call sites total). useJobProgress
// calls notifyJobsBus() the moment it starts tracking a job and again on
// that job's terminal event; useJobsList subscribes and refetches once
// (debounced) per notification. That is event-driven off real job
// lifecycle transitions, not a timer — see useJobsList.ts.
//
// A plain module-level pub/sub, not a QueryClient call, so useJobProgress
// stays free of a React Query dependency — useJobProgress.test.tsx renders
// the hook with no QueryClientProvider, and this must not require one.

type Listener = () => void;

const listeners = new Set<Listener>();

/** Notify subscribers that some job's state may have changed. */
export function notifyJobsBus(): void {
  for (const listener of listeners) {
    listener();
  }
}

/** Subscribe to job-touched notifications. Returns an unsubscribe function. */
export function subscribeJobsBus(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

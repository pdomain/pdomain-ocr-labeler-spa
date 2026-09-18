// JobsSurface.tsx — the persistent jobs surface: a header-anchored pill plus
// AppShell's docked Jobs panel, fed from one shared `GET /api/jobs` cache
// entry (useJobsList).
//
// Spec: docs/plans/2026-07-21-pgdp-alignment-remaining.md item 4.
//
// Integration path: `JobsPill` + AppShell's `jobs` prop → `UtilityDock` →
// `JobsPanelBody`, per
// docs/issues/2026-09-18-jobs-pill-status-contract-gap.md's own
// recommendation — not the standalone `JobsDrawer`, because AppShell
// already docks a jobs surface. That issue blocked this integration on two
// upstream `pdomain-ui` gaps (no `cancelled` JobStatus, no pause/resume
// capability flag); both shipped in v0.13.0 — see jobsMapping.ts.
//
// Two pieces:
//   1. `useJobsShellProps()` — builds AppShell's `jobs` prop
//      (`AppShellJobsProps`) and the pill's own queued/running-only
//      `ActiveJob[]` list from one `useJobsList()` call. Call this once,
//      high up (App.tsx's `AppInner`), and thread `pillActiveJobs` down to
//      `JobsIndicator` as a prop — that keeps `useJobsList()` to a single
//      call site even though the pill and the panel both need its data.
//   2. `JobsIndicator` — the pill itself. Must be rendered *inside*
//      AppShell's own tree to call `useUtilityDock()` — verified against
//      the installed package that AppShell wraps its full grid, including
//      a custom `header` slot, in `UtilityDockContext.Provider`. App.tsx
//      renders this inside `HeaderBar`'s `rightSlot`, which is itself part
//      of the custom `header` node passed to `<AppShell>`.

import { useNavigate } from "react-router-dom";
import {
  JobsPill,
  useUtilityDock,
  type ActiveJob,
  type AppShellJobsProps,
} from "@pdomain/pdomain-ui/shell";
import { useJobsList } from "../../hooks/useJobsList";
import { useCancelJob } from "../../hooks/useCancelJob";
import { toJobRowJobs, toPillActiveJobs } from "../../lib/jobsMapping";

export interface UseJobsShellPropsResult {
  /** Pass straight through to `<AppShell jobs={...}>`. */
  shellJobsProps: AppShellJobsProps;
  /** Pass to `<JobsIndicator activeJobs={...}>`. */
  pillActiveJobs: ActiveJob[];
}

/** Builds AppShell's `jobs` prop and the pill's active-job list from the one
 * shared `useJobsList()` cache entry (react-query dedupes it against any
 * other `useJobsList()` caller, so this isn't a second network fetch). */
export function useJobsShellProps(): UseJobsShellPropsResult {
  const { jobs } = useJobsList();
  const { cancel } = useCancelJob();
  const navigate = useNavigate();

  const shellJobsProps: AppShellJobsProps = {
    activeJobs: toJobRowJobs(jobs),
    onJobOpen: (jobId) => {
      const job = jobs.find((j) => j.id === jobId);
      // ProjectRootRedirect (App.tsx) sends this on to pageno/1 — a job
      // record has no page number of its own to deep-link to.
      if (job?.project_id) {
        void navigate(`/projects/${encodeURIComponent(job.project_id)}`);
      }
    },
    onJobCancel: (jobId) => {
      cancel(jobId);
    },
    // No onJobPauseResume: every row's `pausable: false` (jobsMapping.ts)
    // already omits JobRow's Pause/Resume control, so nothing would ever
    // call this. This backend has no pause/resume concept to wire it to.
    // No onJobDelete: there is no "delete a job record" endpoint
    // (api/jobs.py has list / get / events / cancel only) — passing a
    // handler here would draw a Delete button for a capability that
    // doesn't exist, the same class of gap `pausable` closed.
    // No onViewAll: there is no dedicated "all jobs" page/route to link to;
    // omitting it hides JobsPanelBody's "View all jobs" footer entirely
    // (gated on `onViewAll !== undefined` — verified against the installed
    // package) rather than wiring it to nowhere.
  };

  return { shellJobsProps, pillActiveJobs: toPillActiveJobs(jobs) };
}

export interface JobsIndicatorProps {
  /** Queued/running jobs only — see `toPillActiveJobs`. */
  activeJobs: ActiveJob[];
}

/**
 * Header-anchored jobs pill. Clicking toggles AppShell's utility dock Jobs
 * panel — `JobsPill`'s own documented wiring (`onClick` →
 * `useUtilityDock().toggle('jobs')`, see the installed package's
 * `JobsPill.tsx` doc comment).
 *
 * Wrapped in a `data-testid` div because `JobsPillProps` has no testid prop
 * of its own — same pattern as `BusyOverlay`'s `OperationStatusPanel`
 * wrapper (components/BusyOverlay.tsx).
 */
export function JobsIndicator({ activeJobs }: JobsIndicatorProps) {
  const dock = useUtilityDock();
  return (
    <div data-testid="jobs-pill">
      <JobsPill
        activeJobs={activeJobs}
        onClick={() => {
          dock.toggle("jobs");
        }}
      />
    </div>
  );
}

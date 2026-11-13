// JobsSurface.tsx — the persistent jobs surface: a header-anchored pill plus
// AppShell's docked Jobs panel, fed from one shared `GET /api/jobs` cache
// entry (useJobsList).
//
// Spec: docs/architecture/13-driver-contract.md section 2.13a.
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

import { JobsPill, useUtilityDock, type ActiveJob } from "@pdomain/pdomain-ui/shell";

/** Builds AppShell's `jobs` prop and the pill's active-job list from the one
 * shared `useJobsList()` cache entry (react-query dedupes it against any
 * other `useJobsList()` caller, so this isn't a second network fetch). */

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

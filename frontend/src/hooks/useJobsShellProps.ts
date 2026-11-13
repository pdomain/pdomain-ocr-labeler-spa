import { useNavigate } from "react-router-dom";
import type { ActiveJob, AppShellJobsProps } from "@pdomain/pdomain-ui/shell";
import { useJobsList } from "./useJobsList";
import { useCancelJob } from "./useCancelJob";
import { toJobRowJobs, toPillActiveJobs } from "../lib/jobsMapping";

export interface UseJobsShellPropsResult {
  /** Pass straight through to `<AppShell jobs={...}>`. */
  shellJobsProps: AppShellJobsProps;
  /** Pass to `<JobsIndicator activeJobs={...}>`. */
  pillActiveJobs: ActiveJob[];
}

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

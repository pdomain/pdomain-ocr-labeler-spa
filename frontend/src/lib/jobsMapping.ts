// jobsMapping.ts — pure mapping from the backend's `Job` wire shape
// (GET /api/jobs) to pdomain-ui's `JobRow`/`JobsPill` contracts.
//
// Spec: docs/plans/2026-07-21-pgdp-alignment-remaining.md item 4.
// v0.13.0 fixed both gaps docs/issues/2026-09-18-jobs-pill-status-contract-gap.md
// blocked on: `JobStatus` now has a `cancelled` member with its own accent,
// label, and testid, and `Job.pausable` gates the Pause/Resume control —
// verified against the installed package (JobRow.d.ts, this file's tests).

import type {
  Job as JobRowJob,
  JobStatus as JobRowStatus,
  ActiveJob,
} from "@pdomain/pdomain-ui/shell";
import type { components } from "../api/types";
import type { JobsListJob } from "../hooks/useJobsList";

type BackendJobStatus = components["schemas"]["JobStatus"];
type BackendJobType = components["schemas"]["JobType"];

/** Caps how many past (non-active) jobs the panel keeps once a session
 * accumulates a long history — `GET /api/jobs` never prunes
 * (core/jobs/runner.py `_jobs` is an unbounded in-memory dict for the
 * process lifetime). Every currently active job is always kept regardless
 * of this cap; see `toJobRowJobs`. */
const MAX_PANEL_JOBS = 20;

const ACTIVE_STATUSES: ReadonlySet<BackendJobStatus> = new Set(["queued", "running"]);

/** Exhaustive — a missing key here is a compile error, not a silent `void`. */
const STATUS_MAP: Record<BackendJobStatus, JobRowStatus> = {
  queued: "queued",
  running: "running",
  complete: "done",
  error: "failed",
  cancelled: "cancelled",
};

/** `"propose_page_kinds"` → `"Propose page kinds"`. */
function humanizeJobType(type: BackendJobType): string {
  const spaced = type.replace(/_/g, " ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

function jobPct(job: JobsListJob): number {
  if (job.status === "complete") return 100;
  const { current, total } = job.progress;
  if (total <= 0) return 0;
  return Math.min(100, Math.max(0, Math.round((current / total) * 100)));
}

/** A failed job's phase line prefers the backend's own error message; every
 * other status falls back to the progress message, then the humanized job
 * type when neither is populated yet (e.g. the very first `queued` frame). */
function jobPhase(job: JobsListJob): string {
  if (job.status === "error" && job.error_message) return job.error_message;
  return job.progress.message || humanizeJobType(job.type);
}

function jobProjectLabel(job: JobsListJob): string {
  // No display-name field exists on a job or a project (see
  // hooks/useProject.ts's ProjectResponse comment) — project_id is the
  // established label of record elsewhere in this app (HeaderBar's
  // breadcrumb uses the same fallback).
  return job.project_id ?? "No project";
}

/** Map one backend `Job` to pdomain-ui's `JobRow` `Job` shape. */
export function toJobRowJob(job: JobsListJob): JobRowJob {
  return {
    id: job.id,
    project: jobProjectLabel(job),
    phase: jobPhase(job),
    pct: jobPct(job),
    status: STATUS_MAP[job.status],
    cancelable: ACTIVE_STATUSES.has(job.status),
    // This backend has no pause/resume concept — `core/jobs/runner.py`'s
    // only transitions are queued -> running -> one terminal state, plus
    // cooperative cancel. `false` (not omitted) so JobRow omits the
    // Pause/Resume control instead of rendering a button that does nothing
    // when clicked — the exact gap
    // docs/issues/2026-09-18-jobs-pill-status-contract-gap.md blocked on.
    pausable: false,
  };
}

/** Map the full job list to the rows `JobsPanelBody` renders, most recently
 * updated first (the caller, `useJobsList`, already sorts this way) and
 * capped so a long session's job history stays scannable. Every currently
 * active (queued/running) job is always included regardless of the cap —
 * those are exactly the jobs the panel most needs to keep showing. */
export function toJobRowJobs(jobs: readonly JobsListJob[]): JobRowJob[] {
  const active = jobs.filter((job) => ACTIVE_STATUSES.has(job.status));
  const finished = jobs.filter((job) => !ACTIVE_STATUSES.has(job.status));
  const keepFinished = Math.max(0, MAX_PANEL_JOBS - active.length);
  return [...active, ...finished.slice(0, keepFinished)].map(toJobRowJob);
}

/** Map only queued/running jobs to the pill's ambient count badge.
 * `JobsPill` reads nothing but `activeJobs.length` (verified against the
 * installed package's `JobsPill.tsx`), so a terminal job must never appear
 * here — an empty surface must look empty, not like a stale last job. */
export function toPillActiveJobs(jobs: readonly JobsListJob[]): ActiveJob[] {
  return jobs
    .filter((job) => ACTIVE_STATUSES.has(job.status))
    .map((job) => ({
      id: job.id,
      title: humanizeJobType(job.type),
      phase: jobPhase(job),
      pct: jobPct(job),
      project: jobProjectLabel(job),
    }));
}

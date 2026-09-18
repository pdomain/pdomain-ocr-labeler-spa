// useJobsList.ts — TanStack Query hook for GET /api/jobs, the source of
// truth for the persistent jobs surface (JobsPill + AppShell `jobs` prop).
//
// Spec: docs/plans/2026-07-21-pgdp-alignment-remaining.md item 4.
//
// Rebuild-from-list, not from-stream: the broker buffers nothing and a job
// only tracks its latest progress fraction, not a history
// (docs/context/decisions.md, "Fixed: a job that finished fast hung its
// event stream forever" — the follow-up note there is explicit that a late
// SSE subscriber can never recover missed intermediate or terminal events).
// `GET /api/jobs` always reflects each job's *current* state directly, so a
// surface built from it has no "subscribed late" failure mode — it is
// correct on the very first fetch, including right after a page load.
//
// Refresh strategy — do not poll hard:
//   - Polls only while the last-known list contains a queued or running
//     job, every ACTIVE_POLL_MS. Idle (nothing queued/running) →
//     `refetchInterval` is `false`: no timer at all, so a quiet session
//     costs one initial GET and nothing more.
//   - ACTIVE_POLL_MS (3s) matches the granularity job handlers actually
//     report progress at (per-page / per-step), not a sub-second poll.
//   - The resulting gap — nothing polls while idle, so how is a *newly
//     started* job discovered without waiting for the next window focus or
//     remount? — is closed by jobsBus, not by polling harder: every job the
//     app starts already calls useJobProgress(jobId) synchronously once it
//     has a job id, and that hook now signals jobsBus the moment it starts
//     tracking a job and again on that job's terminal event. This hook
//     refetches once (debounced) per signal. That is event-driven off real
//     job lifecycle transitions, not a timer — see jobsBus.ts and
//     useJobProgress.ts.

import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import type { components } from "../api/types";
import { subscribeJobsBus } from "../lib/jobsBus";

export type JobsListJob = components["schemas"]["Job"];
type JobStatus = components["schemas"]["JobStatus"];

const ACTIVE_STATUSES: ReadonlySet<JobStatus> = new Set(["queued", "running"]);
const ACTIVE_POLL_MS = 3_000;
/** Coalesces bursts of jobsBus signals (e.g. several jobs starting together). */
const BUS_DEBOUNCE_MS = 200;

export const JOBS_QUERY_KEY = ["jobs"] as const;

/**
 * Pure interval decision, exported so the "poll only while something is
 * queued/running" rule is unit-testable without depending on React Query's
 * own timer plumbing (`refetchInterval`'s function form otherwise only
 * receives a live `Query` instance, not a plain array).
 */
export function computeRefetchInterval(jobs: readonly JobsListJob[] | undefined): number | false {
  const hasActiveJob = jobs?.some((job) => ACTIVE_STATUSES.has(job.status)) ?? false;
  return hasActiveJob ? ACTIVE_POLL_MS : false;
}

async function fetchJobs(): Promise<JobsListJob[]> {
  const res = await fetch("/api/jobs");
  if (!res.ok) {
    throw new Error(`GET /api/jobs failed: ${String(res.status)}`);
  }
  const body: unknown = await res.json();
  return Array.isArray(body) ? (body as JobsListJob[]) : [];
}

export interface UseJobsListResult {
  /** Every job the backend currently knows about, most-recently-updated first. */
  jobs: JobsListJob[];
  /** True while the initial fetch is in flight and no data has arrived yet. */
  isLoading: boolean;
}

/**
 * Shared, deduplicated `GET /api/jobs` cache entry — every caller (the
 * JobsPill badge, the AppShell `jobs` panel) reads the same fetch/poll
 * cycle rather than each starting its own network request.
 */
export function useJobsList(): UseJobsListResult {
  const query = useQuery({
    queryKey: JOBS_QUERY_KEY,
    queryFn: fetchJobs,
    refetchInterval: (q) => computeRefetchInterval(q.state.data),
  });

  // Ref-forwarded so the bus subscription effect below doesn't need
  // `query.refetch` in its dependency array (a new function identity every
  // render would otherwise resubscribe on every render). Written from an
  // effect, not during render — a ref must never be mutated while
  // rendering (react-hooks/refs).
  const refetchRef = useRef(query.refetch);
  useEffect(() => {
    refetchRef.current = query.refetch;
  });

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | null = null;
    const unsubscribe = subscribeJobsBus(() => {
      if (timer !== null) return;
      timer = setTimeout(() => {
        timer = null;
        void refetchRef.current();
      }, BUS_DEBOUNCE_MS);
    });
    return () => {
      unsubscribe();
      if (timer !== null) clearTimeout(timer);
    };
  }, []);

  const jobs = [...(query.data ?? [])].sort((a, b) => b.updated_at.localeCompare(a.updated_at));

  return { jobs, isLoading: query.isLoading };
}

// useJobProgress.ts — EventSource hook for GET /api/jobs/{jobId}/events.
//
// Spec: docs/specs/2026-05-12-frontend-shell-design.md §Hooks
// Issue #192
//
// Opens an EventSource on mount (when jobId is provided) and closes it on
// unmount or when the job reaches a terminal state (complete / error).
//
// Event shape sent by the backend SSE stream (JobProgressEvent):
//   { job_id, status, progress: { current, total, current_page, message } }
//
// Returns null until the first progress event arrives.

import { useEffect, useRef, useState } from "react";
import type { components } from "../api/types";

export type JobStatus = components["schemas"]["JobStatus"];
export type JobProgress = components["schemas"]["JobProgress"];

export interface JobProgressEvent {
  job_id: string;
  status: JobStatus;
  progress: JobProgress;
  error_message?: string | null;
}

const TERMINAL: ReadonlySet<JobStatus> = new Set(["complete", "error"]);

/**
 * Subscribe to SSE progress events for a background job.
 *
 * @param jobId - job id returned by a 202 response, or null/undefined to skip
 * @returns the latest `JobProgressEvent`, or null if no event received yet
 *
 * Cleanup contract: the EventSource is closed when
 * (a) the component unmounts, or
 * (b) a terminal status (`complete` / `error`) is received — whichever comes first.
 */
export function useJobProgress(jobId: string | null | undefined): JobProgressEvent | null {
  const [latest, setLatest] = useState<JobProgressEvent | null>(null);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!jobId) {
      setLatest(null);
      return;
    }

    const es = new EventSource(`/api/jobs/${jobId}/events`);
    esRef.current = es;

    function handleProgress(e: MessageEvent) {
      let event: JobProgressEvent;
      try {
        event = JSON.parse(e.data as string) as JobProgressEvent;
      } catch {
        return;
      }

      setLatest(event);

      if (TERMINAL.has(event.status)) {
        es.close();
        esRef.current = null;
      }
    }

    es.addEventListener("progress", handleProgress);

    return () => {
      es.removeEventListener("progress", handleProgress);
      // EventSource.readyState: 0=CONNECTING, 1=OPEN, 2=CLOSED
      if (es.readyState !== EventSource.CLOSED) {
        es.close();
      }
      esRef.current = null;
    };
  }, [jobId]);

  // Reset when jobId changes so callers don't see stale progress from a
  // previous job while the new EventSource is opening.
  useEffect(() => {
    setLatest(null);
  }, [jobId]);

  return latest;
}

// useJobProgress.ts — EventSource hook for GET /api/jobs/{jobId}/events.
//
// Spec: docs/specs/2026-05-12-frontend-shell-design.md §Hooks
// Issue #192; Wave 3a / P1-JOB-SSE — adapt flat backend wire to nested FE shape.
//
// Backend SSE frames (flat):
//   event: snapshot | progress | complete | error | cancelled
//   data: { type, status, current, total, message, error, ...result }
//
// FE consumers expect nested JobProgressEvent:
//   { job_id, status, progress: { current, total, message }, error_message }

import { useEffect, useRef, useState } from "react";
import type { components } from "../api/types";

type JobStatus = components["schemas"]["JobStatus"];
type JobProgress = components["schemas"]["JobProgress"];

export interface JobProgressEvent {
  job_id: string;
  status: JobStatus;
  progress: JobProgress;
  error_message?: string | null;
  // Export stats breakdown (Lane E3) — present on the terminal event of an
  // export job. Flat top-level fields, matching the backend SSE wire format.
  words_exported_detection?: number;
  words_exported_recognition?: number;
  pages_skipped_not_validated?: number;
}

/** Wire payload from the backend (flat) or already-nested OpenAPI shape. */
interface WireJobEvent {
  type?: string;
  status?: string;
  current?: number;
  total?: number;
  message?: string | null;
  error?: string | null;
  job_id?: string;
  progress?: Partial<JobProgress> | null;
  error_message?: string | null;
  words_exported_detection?: number;
  words_exported_recognition?: number;
  pages_skipped_not_validated?: number;
}

const TERMINAL: ReadonlySet<string> = new Set(["complete", "error", "cancelled"]);

/**
 * Normalize a backend flat SSE payload (or a nested fixture) into JobProgressEvent.
 */
function normalizeJobProgressEvent(
  raw: WireJobEvent,
  fallbackJobId: string,
): JobProgressEvent | null {
  const statusRaw = raw.status ?? raw.type ?? "";
  if (!statusRaw) {
    return null;
  }

  const nested = raw.progress;
  const current =
    typeof nested?.current === "number"
      ? nested.current
      : typeof raw.current === "number"
        ? raw.current
        : 0;
  const total =
    typeof nested?.total === "number"
      ? nested.total
      : typeof raw.total === "number"
        ? raw.total
        : 0;
  let message = "";
  if (typeof nested?.message === "string") {
    message = nested.message;
  } else if (typeof raw.message === "string") {
    message = raw.message;
  }

  let error_message: string | null | undefined;
  if (raw.error_message !== undefined) {
    error_message = raw.error_message;
  } else if (raw.error !== undefined) {
    error_message = raw.error;
  }

  // Keep cancelled as a terminal status string even if OpenAPI JobStatus is narrower.
  const normalizedStatus = statusRaw as JobStatus;

  const progress: JobProgress = {
    current,
    total,
    message,
  };

  const event: JobProgressEvent = {
    job_id: typeof raw.job_id === "string" && raw.job_id ? raw.job_id : fallbackJobId,
    status: normalizedStatus,
    progress,
  };
  if (error_message !== undefined) {
    event.error_message = error_message;
  }
  if (typeof raw.words_exported_detection === "number") {
    event.words_exported_detection = raw.words_exported_detection;
  }
  if (typeof raw.words_exported_recognition === "number") {
    event.words_exported_recognition = raw.words_exported_recognition;
  }
  if (typeof raw.pages_skipped_not_validated === "number") {
    event.pages_skipped_not_validated = raw.pages_skipped_not_validated;
  }
  return event;
}

/**
 * Subscribe to SSE progress events for a background job.
 *
 * @param jobId - job id returned by a 202 response, or null/undefined to skip
 * @returns the latest `JobProgressEvent`, or null if no event received yet
 *
 * Cleanup contract: the EventSource is closed when
 * (a) the component unmounts, or
 * (b) a terminal status (`complete` / `error` / `cancelled`) is received.
 */
export function useJobProgress(jobId: string | null | undefined): JobProgressEvent | null {
  const [latest, setLatest] = useState<JobProgressEvent | null>(null);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!jobId) {
      setLatest(null);
      return;
    }

    const trackedJobId: string = jobId;
    const es = new EventSource(`/api/jobs/${encodeURIComponent(trackedJobId)}/events`);
    esRef.current = es;

    function handleProgress(e: MessageEvent) {
      let raw: WireJobEvent;
      try {
        raw = JSON.parse(e.data as string) as WireJobEvent;
      } catch {
        return;
      }

      const event = normalizeJobProgressEvent(raw, trackedJobId);
      if (!event) {
        return;
      }

      setLatest(event);

      if (TERMINAL.has(event.status) || TERMINAL.has(String(raw.type ?? ""))) {
        es.close();
        esRef.current = null;
      }
    }

    // Backend first frame is often `event: snapshot`; progress/complete/error
    // follow. Listen for cancelled too (Wave 3a.2).
    const names = ["snapshot", "progress", "complete", "error", "cancelled"] as const;
    for (const name of names) {
      es.addEventListener(name, handleProgress);
    }

    return () => {
      for (const name of names) {
        es.removeEventListener(name, handleProgress);
      }
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

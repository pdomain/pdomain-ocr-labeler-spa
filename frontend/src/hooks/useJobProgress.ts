// useJobProgress.ts — EventSource hook for GET /api/jobs/{jobId}/events.
//
// Spec: docs/specs/2026-05-12-frontend-shell-design.md §Hooks
// Issue #192; Wave 3a / P1-JOB-SSE.
//
// The backend now serializes the declared public `Job` model on every SSE
// frame — the same shape `GET /api/jobs/{id}` returns — plus one extra
// `event` field naming the SSE event kind. The event kind is a distinct
// field from the job's own `type` (job kind, e.g. `"export"`): the old wire
// shape reused `type` for the event kind, which collided with the model's
// `type` field once the two were unified. See
// docs/issues/2026-07-21-job-sse-fe-be-shape-mismatch.md and
// docs/issues/2026-07-21-jobs-api-openapi-mismatch.md (P1-JOB-SSE,
// P1-JOBS-API).
//
// Backend SSE frames:
//   event: snapshot | progress | complete | error | cancelled
//   data: { id, type, project_id, status, progress: { current, total,
//           current_page, message }, error_message, created_at, updated_at,
//           result, event }. `result` is job-type-specific handler output
//           (core.models.Job.result) — e.g. export's terminal stats
//           (words_exported_detection / words_exported_recognition /
//           pages_skipped_not_validated). The backend also still merges
//           export's stats flat at the frame's top level for backward
//           compatibility with older callers, but this hook reads them from
//           `result`, the one field every job type uses.

import { useEffect, useRef, useState } from "react";
import type { components } from "../api/types";
import { notifyJobsBus } from "../lib/jobsBus";

type Job = components["schemas"]["Job"];
type JobStatus = components["schemas"]["JobStatus"];
type JobProgress = components["schemas"]["JobProgress"];

// Not exported: `JobProgressEvent` (below, exported and widely consumed)
// carries this literal union structurally as its own `event` field, so no
// external caller needs to name `JobEventKind` itself.
/** The SSE event kind — the `event:` line name, echoed in the frame's own `event` field. */
type JobEventKind = "snapshot" | "progress" | "complete" | "error" | "cancelled";

/** A job-progress SSE frame: the public `Job` model plus the SSE event kind. */
export interface JobProgressEvent extends Job {
  event: JobEventKind;
}

const TERMINAL: ReadonlySet<JobStatus> = new Set(["complete", "error", "cancelled"]);

const EVENT_NAMES: readonly JobEventKind[] = [
  "snapshot",
  "progress",
  "complete",
  "error",
  "cancelled",
];

/**
 * Parse an SSE frame's JSON payload into a `JobProgressEvent`.
 *
 * The payload crosses an untrusted boundary (network JSON), so every field
 * this hook relies on is narrowed with `typeof` before use; malformed or
 * incomplete frames are dropped (return `null`) rather than surfaced as a
 * half-populated event. `type` / `status` / `event` are narrowed only to
 * `string` here, then asserted to their declared literal unions: the
 * backend is the single source of truth for those enums now that REST and
 * SSE both serialize the same declared `Job` model (P1-JOBS-API), and the
 * union members aren't re-derivable at runtime without a schema library
 * this project doesn't otherwise depend on.
 */
function parseJobProgressEvent(raw: unknown): JobProgressEvent | null {
  if (typeof raw !== "object" || raw === null) return null;
  const obj = raw as Record<string, unknown>;

  const { id, type, status, event, progress } = obj;
  if (
    typeof id !== "string" ||
    typeof type !== "string" ||
    typeof status !== "string" ||
    typeof event !== "string" ||
    typeof progress !== "object" ||
    progress === null
  ) {
    return null;
  }

  const rawProgress = progress as Record<string, unknown>;
  const current = typeof rawProgress["current"] === "number" ? rawProgress["current"] : 0;
  const total = typeof rawProgress["total"] === "number" ? rawProgress["total"] : 0;
  const message = typeof rawProgress["message"] === "string" ? rawProgress["message"] : "";
  const currentPage =
    typeof rawProgress["current_page"] === "number" ? rawProgress["current_page"] : null;

  const normalizedProgress: JobProgress = { current, total, message };
  if (currentPage !== null) {
    normalizedProgress.current_page = currentPage;
  }

  const parsed: JobProgressEvent = {
    id,
    // Validated string boundary; see doc comment above.
    type: type as Job["type"],
    project_id: typeof obj["project_id"] === "string" ? obj["project_id"] : null,
    status: status as JobStatus,
    progress: normalizedProgress,
    created_at: typeof obj["created_at"] === "string" ? obj["created_at"] : "",
    updated_at: typeof obj["updated_at"] === "string" ? obj["updated_at"] : "",
    event: event as JobEventKind,
  };
  if (typeof obj["error_message"] === "string" || obj["error_message"] === null) {
    parsed.error_message = obj["error_message"];
  }
  if (obj["result"] === null) {
    parsed.result = null;
  } else if (typeof obj["result"] === "object") {
    // Validated string boundary (object check above); see doc comment above.
    parsed.result = obj["result"] as Record<string, unknown>;
  }
  return parsed;
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

  // Reset `latest` during render (not in an effect) the moment `jobId`
  // changes, so callers never see a stale event from a previous job while a
  // new EventSource is still connecting, or after the job is cleared. See
  // https://react.dev/learn/you-might-not-need-an-effect#adjusting-some-state-when-a-prop-changes
  const [prevJobId, setPrevJobId] = useState(jobId);
  if (prevJobId !== jobId) {
    setPrevJobId(jobId);
    setLatest(null);
  }

  useEffect(() => {
    if (!jobId) {
      return;
    }

    const trackedJobId: string = jobId;
    const es = new EventSource(`/api/jobs/${encodeURIComponent(trackedJobId)}/events`);
    esRef.current = es;

    // Bridges useJobsList's idle→active gap (jobsBus.ts): the moment this
    // hook starts tracking a job is the earliest the app can know one
    // exists, well before any poll would find it.
    notifyJobsBus();

    function handleProgress(e: MessageEvent) {
      let raw: unknown;
      try {
        raw = JSON.parse(e.data as string);
      } catch {
        return;
      }

      const event = parseJobProgressEvent(raw);
      if (!event) {
        return;
      }

      setLatest(event);

      if (TERMINAL.has(event.status)) {
        es.close();
        esRef.current = null;
        // Final state reached — make sure the shared jobs list picks up
        // the terminal status even if its own poll interval had already
        // stopped (e.g. this was the only active job).
        notifyJobsBus();
      }
    }

    // First frame is the current snapshot (`event: snapshot`, or the
    // terminal event name if the job was already done); later frames are
    // `progress` until a terminal `complete` / `error` / `cancelled`.
    for (const name of EVENT_NAMES) {
      es.addEventListener(name, handleProgress);
    }

    return () => {
      for (const name of EVENT_NAMES) {
        es.removeEventListener(name, handleProgress);
      }
      if (es.readyState !== EventSource.CLOSED) {
        es.close();
      }
      esRef.current = null;
    };
  }, [jobId]);

  return latest;
}

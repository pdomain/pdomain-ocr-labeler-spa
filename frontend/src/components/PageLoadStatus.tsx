// PageLoadStatus.tsx — page-region status for the on-demand `load_page` job.
//
// Spec: docs/specs/2026-08-08-page-load-progress-design.md
// Issue: docs/issues/2026-08-08-page-load-progress-unbuilt.md
//
// `GET .../pages/{idx}` now returns immediately even on a store miss: the
// slow OCR pass moved onto a `load_page` job, and the response carries
// `PagePayload.page_load_job_id` instead of blocking. This component renders
// that job's stages ("Stored page not found — running OCR.", "Preparing the
// OCR engine and running OCR — {device}.", "Page loaded.") in the page
// region only — it is `absolute inset-0` inside `image-pane` (a
// `position: relative` ancestor), not `fixed inset-0` like `BusyOverlay` /
// `ProjectLoadingOverlay`. That is the deliberate difference: this status
// must NOT cover the rail, the page list, or the side panels while a page's
// OCR runs (design "While a page is being OCR'd, the OCR status sits in the
// page region and the rest of the shell stays interactive").
//
// A store hit never sets `page_load_job_id`, so `pageLoadJobId` is null and
// this component renders nothing — no progress UI and no flicker for the
// warm-page case (design acceptance criterion).
//
// A terminal `error` event (the job's OCR run itself failed) renders here
// with `error_message`, distinct from `OcrFailedBanner` / `page_load_error`
// (InlineBanners.tsx) — that banner is the *synchronous* lane-check failure
// path, a different case the backend still reports on the payload directly.

import { OperationStatusPanel } from "@pdomain/pdomain-ui/status";
import type { JobProgressEvent } from "../hooks/useJobProgress";

interface PageLoadStatusProps {
  /** `PagePayload.page_load_job_id`, or null when the page was served from
   * the store (no job — nothing to render). */
  pageLoadJobId: string | null;
  /** Latest SSE frame from `useJobProgress(pageLoadJobId)`; null before the
   * first frame arrives, or once the job id resets to null. */
  jobEvent: JobProgressEvent | null;
}

export function PageLoadStatus({ pageLoadJobId, jobEvent }: PageLoadStatusProps) {
  if (!pageLoadJobId) return null;

  const isError = jobEvent?.status === "error";
  const message = isError
    ? (jobEvent.error_message ?? "OCR failed for this page.")
    : (jobEvent?.progress.message ?? "Loading page…");

  return (
    <div
      data-testid={isError ? "page-load-error" : "page-load-status"}
      role={isError ? "alert" : "status"}
      aria-live={isError ? "assertive" : "polite"}
      className="absolute inset-0 z-10 flex items-center justify-center bg-bg-page/85 backdrop-blur-xs"
    >
      <OperationStatusPanel
        title={isError ? "Page load failed" : "Loading page"}
        message={message}
        state={isError ? "error" : "running"}
      />
    </div>
  );
}

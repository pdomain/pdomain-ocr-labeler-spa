// PageLoadStatus.test.tsx — unit tests for the page-region `load_page` job
// status.
//
// Spec: docs/specs/2026-08-08-page-load-progress-design.md
// Issue: docs/issues/2026-08-08-page-load-progress-unbuilt.md
//
// Covers, at the component level (ProjectPage.pageLoadProgress.test.tsx
// covers the same criteria wired into the real page):
//   - no `pageLoadJobId` → renders nothing (warm page, no flicker).
//   - a running stage renders its message.
//   - a terminal error renders `error_message`, with a distinct testid from
//     the running case (and from `OcrFailedBanner`'s `banner-ocr-failed`).

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { PageLoadStatus } from "./PageLoadStatus";
import type { JobProgressEvent } from "../hooks/useJobProgress";

function jobEvent(overrides: Partial<JobProgressEvent> & { status: JobProgressEvent["status"] }) {
  return {
    id: "job-1",
    type: "load_page",
    project_id: "p1",
    progress: { current: 0, total: 2, message: "" },
    created_at: new Date(0).toISOString(),
    updated_at: new Date(0).toISOString(),
    event: overrides.status,
    ...overrides,
  } as JobProgressEvent;
}

describe("PageLoadStatus", () => {
  it("renders nothing when pageLoadJobId is null (warm page — no job)", () => {
    const { container } = render(<PageLoadStatus pageLoadJobId={null} jobEvent={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing when pageLoadJobId is null even if a stale jobEvent is passed", () => {
    // Belt-and-suspenders: the job id gates rendering, not the event, so a
    // stale event from a previous job (whose id has since cleared) cannot
    // flicker a stage that no longer applies.
    const { container } = render(
      <PageLoadStatus
        pageLoadJobId={null}
        jobEvent={jobEvent({ status: "running", progress: { current: 1, total: 2, message: "x" } })}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("shows a fallback message before the first SSE frame arrives", () => {
    render(<PageLoadStatus pageLoadJobId="job-1" jobEvent={null} />);
    const status = screen.getByTestId("page-load-status");
    expect(status).toBeInTheDocument();
    expect(status.textContent).toMatch(/loading page/i);
  });

  it("shows the job's stage message while running", () => {
    render(
      <PageLoadStatus
        pageLoadJobId="job-1"
        jobEvent={jobEvent({
          status: "running",
          progress: { current: 0, total: 2, message: "Stored page not found — running OCR." },
        })}
      />,
    );
    const status = screen.getByTestId("page-load-status");
    expect(status.textContent).toContain("Stored page not found — running OCR.");
  });

  it("updates as later stage frames arrive", () => {
    const { rerender } = render(
      <PageLoadStatus
        pageLoadJobId="job-1"
        jobEvent={jobEvent({
          status: "running",
          progress: { current: 0, total: 2, message: "Stored page not found — running OCR." },
        })}
      />,
    );
    rerender(
      <PageLoadStatus
        pageLoadJobId="job-1"
        jobEvent={jobEvent({
          status: "running",
          progress: {
            current: 1,
            total: 2,
            message: "Preparing the OCR engine and running OCR — cpu.",
          },
        })}
      />,
    );
    const status = screen.getByTestId("page-load-status");
    expect(status.textContent).toContain("Preparing the OCR engine and running OCR — cpu.");
  });

  it("renders a terminal error with a distinct testid from the running status", () => {
    render(
      <PageLoadStatus
        pageLoadJobId="job-1"
        jobEvent={jobEvent({
          status: "error",
          progress: {
            current: 1,
            total: 2,
            message: "Preparing the OCR engine and running OCR — cpu.",
          },
          error_message: "OCR engine crashed",
        })}
      />,
    );
    expect(screen.queryByTestId("page-load-status")).toBeNull();
    const error = screen.getByTestId("page-load-error");
    expect(error.textContent).toContain("OCR engine crashed");
    expect(error).toHaveAttribute("role", "alert");
  });
});

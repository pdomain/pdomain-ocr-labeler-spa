// useJobCompletionInvalidation.test.tsx — unit tests for the shared
// SSE-terminal-status side effect.
//
// Refs #377. The hook owns:
//   - invalidating `invalidationKey` on jobProgress.status === "complete"
//   - clearing `activeJobId` on terminal status (complete / error)
//   - fanning out onComplete / onError / onRunning callbacks to the call site
//
// Toast lifecycle stays at the call site — the hook itself never touches it.

import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { useJobCompletionInvalidation } from "./useJobCompletionInvalidation";
import type { JobProgressEvent } from "./useJobProgress";

/**
 * Build a `JobProgressEvent` fixture — the public `Job` model plus the SSE
 * `event` field (Wave 3a / P1-JOB-SSE) — from the handful of fields each
 * test actually cares about.
 */
function jobEvent(overrides: {
  status: JobProgressEvent["status"];
  progress: JobProgressEvent["progress"];
  error_message?: string | null;
}): JobProgressEvent {
  return {
    id: "job-1",
    type: "reload_ocr",
    project_id: "proj-1",
    status: overrides.status,
    progress: overrides.progress,
    error_message: overrides.error_message ?? null,
    created_at: new Date(0).toISOString(),
    updated_at: new Date(0).toISOString(),
    event:
      overrides.status === "complete" ||
      overrides.status === "error" ||
      overrides.status === "cancelled"
        ? overrides.status
        : "progress",
  };
}

const RUNNING_EVENT: JobProgressEvent = jobEvent({
  status: "running",
  progress: { current: 3, total: 10, message: "Processing…" },
});

const COMPLETE_EVENT: JobProgressEvent = jobEvent({
  status: "complete",
  progress: { current: 10, total: 10, message: "Done" },
});

const ERROR_EVENT: JobProgressEvent = jobEvent({
  status: "error",
  progress: { current: 5, total: 10, message: "Failed" },
  error_message: "OCR engine crashed",
});

// "cancelled" is a real `JobStatus` member now that REST and SSE both
// serialize the declared public `Job` model (P1-JOBS-API) — no cast needed.
const CANCELLED_EVENT: JobProgressEvent = jobEvent({
  status: "cancelled",
  progress: {
    current: 3,
    total: 10,
    message: "Cancelled after processing 3 of 10 page(s); 1 rotated",
  },
});

interface HarnessOptions {
  activeJobId: string | null;
  jobProgress: JobProgressEvent | null;
  invalidationKey?: readonly unknown[];
  onComplete?: (jobId: string, event: JobProgressEvent) => void;
  onError?: (jobId: string, err: string | null) => void;
  onRunning?: (jobId: string, event: JobProgressEvent) => void;
  onCancelled?: (jobId: string, event: JobProgressEvent) => void;
}

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
  const Wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { qc, invalidateSpy, Wrapper };
}

function renderHarness(initial: HarnessOptions) {
  const setActiveJobId = vi.fn<(id: string | null) => void>();
  const { qc, invalidateSpy, Wrapper } = makeWrapper();

  const { rerender } = renderHook(
    (opts: HarnessOptions) => {
      useJobCompletionInvalidation({
        activeJobId: opts.activeJobId,
        jobProgress: opts.jobProgress,
        setActiveJobId,
        invalidationKey: opts.invalidationKey ?? ["page", "proj-1", 0],
        ...(opts.onComplete !== undefined && { onComplete: opts.onComplete }),
        ...(opts.onError !== undefined && { onError: opts.onError }),
        ...(opts.onRunning !== undefined && { onRunning: opts.onRunning }),
        ...(opts.onCancelled !== undefined && { onCancelled: opts.onCancelled }),
      });
    },
    { wrapper: Wrapper, initialProps: initial },
  );

  return { rerender, setActiveJobId, qc, invalidateSpy };
}

describe("useJobCompletionInvalidation", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("does nothing when activeJobId is null", () => {
    const onComplete = vi.fn();
    const { invalidateSpy, setActiveJobId } = renderHarness({
      activeJobId: null,
      jobProgress: COMPLETE_EVENT,
      onComplete,
    });
    expect(invalidateSpy).not.toHaveBeenCalled();
    expect(setActiveJobId).not.toHaveBeenCalled();
    expect(onComplete).not.toHaveBeenCalled();
  });

  it("does nothing when jobProgress is null", () => {
    const onRunning = vi.fn();
    const { invalidateSpy, setActiveJobId } = renderHarness({
      activeJobId: "job-1",
      jobProgress: null,
      onRunning,
    });
    expect(invalidateSpy).not.toHaveBeenCalled();
    expect(setActiveJobId).not.toHaveBeenCalled();
    expect(onRunning).not.toHaveBeenCalled();
  });

  it("invalidates the query key and clears activeJobId on 'complete'", () => {
    const onComplete = vi.fn();
    const { rerender, invalidateSpy, setActiveJobId } = renderHarness({
      activeJobId: "job-1",
      jobProgress: RUNNING_EVENT,
      onComplete,
    });

    // Running event — no invalidation, no reset.
    expect(invalidateSpy).not.toHaveBeenCalled();
    expect(setActiveJobId).not.toHaveBeenCalled();

    act(() => {
      rerender({
        activeJobId: "job-1",
        jobProgress: COMPLETE_EVENT,
        onComplete,
      });
    });

    expect(invalidateSpy).toHaveBeenCalledTimes(1);
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["page", "proj-1", 0] });
    expect(setActiveJobId).toHaveBeenCalledTimes(1);
    expect(setActiveJobId).toHaveBeenCalledWith(null);
    expect(onComplete).toHaveBeenCalledTimes(1);
    expect(onComplete).toHaveBeenCalledWith("job-1", COMPLETE_EVENT);
  });

  it("passes the terminal jobProgress event through to onComplete", () => {
    // Call sites need the terminal event's message (e.g. a job's run
    // summary) to build their completion toast — onComplete must receive
    // it directly rather than the caller reading a closed-over jobProgress,
    // which depends on render timing this hook does not guarantee.
    const onComplete = vi.fn();
    const { rerender } = renderHarness({
      activeJobId: "job-1",
      jobProgress: RUNNING_EVENT,
      onComplete,
    });

    const terminalEvent: JobProgressEvent = jobEvent({
      status: "complete",
      progress: { current: 6, total: 6, message: "Proposed 12 region(s) on 6 page(s)." },
    });

    act(() => {
      rerender({
        activeJobId: "job-1",
        jobProgress: terminalEvent,
        onComplete,
      });
    });

    expect(onComplete).toHaveBeenCalledTimes(1);
    expect(onComplete).toHaveBeenCalledWith("job-1", terminalEvent);
  });

  it("fires onError and clears activeJobId on 'error' but does NOT invalidate", () => {
    const onError = vi.fn();
    const { rerender, invalidateSpy, setActiveJobId } = renderHarness({
      activeJobId: "job-1",
      jobProgress: RUNNING_EVENT,
      onError,
    });

    act(() => {
      rerender({
        activeJobId: "job-1",
        jobProgress: ERROR_EVENT,
        onError,
      });
    });

    expect(invalidateSpy).not.toHaveBeenCalled();
    expect(setActiveJobId).toHaveBeenCalledWith(null);
    expect(onError).toHaveBeenCalledTimes(1);
    expect(onError).toHaveBeenCalledWith("job-1", "OCR engine crashed");
  });

  it("passes null error message through onError when backend omits it", () => {
    const onError = vi.fn();
    const noMessage: JobProgressEvent = { ...ERROR_EVENT, error_message: null };
    const { rerender } = renderHarness({
      activeJobId: "job-1",
      jobProgress: RUNNING_EVENT,
      onError,
    });

    act(() => {
      rerender({ activeJobId: "job-1", jobProgress: noMessage, onError });
    });

    expect(onError).toHaveBeenCalledWith("job-1", null);
  });

  it("fires onRunning on non-terminal updates without invalidating", () => {
    const onRunning = vi.fn();
    const { invalidateSpy, setActiveJobId } = renderHarness({
      activeJobId: "job-1",
      jobProgress: RUNNING_EVENT,
      onRunning,
    });

    expect(invalidateSpy).not.toHaveBeenCalled();
    expect(setActiveJobId).not.toHaveBeenCalled();
    expect(onRunning).toHaveBeenCalledTimes(1);
    expect(onRunning).toHaveBeenCalledWith("job-1", RUNNING_EVENT);
  });

  it("fires onCancelled and clears activeJobId on 'cancelled' but does NOT auto-invalidate", () => {
    // Unlike "complete", the hook does not assume a cancelled run wrote
    // anything durable — whether it did is handler-specific (some do,
    // some don't; see PageActionsCompact.tsx's per-tracker onCancelled
    // callbacks). Invalidation stays the call site's decision, same as
    // "error" already works.
    const onCancelled = vi.fn();
    const { rerender, invalidateSpy, setActiveJobId } = renderHarness({
      activeJobId: "job-1",
      jobProgress: RUNNING_EVENT,
      onCancelled,
    });

    act(() => {
      rerender({
        activeJobId: "job-1",
        jobProgress: CANCELLED_EVENT,
        onCancelled,
      });
    });

    expect(invalidateSpy).not.toHaveBeenCalled();
    expect(setActiveJobId).toHaveBeenCalledTimes(1);
    expect(setActiveJobId).toHaveBeenCalledWith(null);
    expect(onCancelled).toHaveBeenCalledTimes(1);
    expect(onCancelled).toHaveBeenCalledWith("job-1", CANCELLED_EVENT);
  });

  it("does not treat 'cancelled' as a non-terminal 'running' update", () => {
    // Before this hook grew an explicit "cancelled" branch, a cancelled
    // job fell into the same `else` clause as "running" and called
    // onRunning forever without ever clearing activeJobId.
    const onRunning = vi.fn();
    const onCancelled = vi.fn();
    const { rerender, setActiveJobId } = renderHarness({
      activeJobId: "job-1",
      jobProgress: RUNNING_EVENT,
      onRunning,
      onCancelled,
    });

    act(() => {
      rerender({
        activeJobId: "job-1",
        jobProgress: CANCELLED_EVENT,
        onRunning,
        onCancelled,
      });
    });

    expect(onRunning).toHaveBeenCalledTimes(1); // only the earlier RUNNING_EVENT render
    expect(onCancelled).toHaveBeenCalledTimes(1);
    expect(setActiveJobId).toHaveBeenCalledWith(null);
  });

  it("uses the supplied invalidation key verbatim", () => {
    const customKey = ["foo", "bar", 42] as const;
    const { rerender, invalidateSpy } = renderHarness({
      activeJobId: "job-1",
      jobProgress: RUNNING_EVENT,
      invalidationKey: customKey,
    });

    act(() => {
      rerender({
        activeJobId: "job-1",
        jobProgress: COMPLETE_EVENT,
        invalidationKey: customKey,
      });
    });

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: customKey });
  });
});

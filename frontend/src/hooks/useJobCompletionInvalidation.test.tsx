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

const RUNNING_EVENT: JobProgressEvent = {
  job_id: "job-1",
  status: "running",
  progress: { current: 3, total: 10, message: "Processing…" },
};

const COMPLETE_EVENT: JobProgressEvent = {
  job_id: "job-1",
  status: "complete",
  progress: { current: 10, total: 10, message: "Done" },
};

const ERROR_EVENT: JobProgressEvent = {
  job_id: "job-1",
  status: "error",
  progress: { current: 5, total: 10, message: "Failed" },
  error_message: "OCR engine crashed",
};

interface HarnessOptions {
  activeJobId: string | null;
  jobProgress: JobProgressEvent | null;
  invalidationKey?: readonly unknown[];
  onComplete?: (jobId: string) => void;
  onError?: (jobId: string, err: string | null) => void;
  onRunning?: (jobId: string, event: JobProgressEvent) => void;
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
        onComplete: opts.onComplete,
        onError: opts.onError,
        onRunning: opts.onRunning,
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
    expect(onComplete).toHaveBeenCalledWith("job-1");
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

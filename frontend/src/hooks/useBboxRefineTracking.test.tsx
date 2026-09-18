// useBboxRefineTracking.test.tsx — unit tests for the hoisted refine_bboxes
// job tracker (review finding 3, docs/issues/2026-07-21-bbox-refine-crop-misleading.md,
// plus review round 2 findings 1 and 3).
//
// See WordDetail.test.tsx's "collapses mid-job" test for the integration-
// level proof that this hook, called from an always-mounted ancestor,
// survives BBoxSection's own accordion collapsing mid-job — that is the
// scenario this hook exists to fix, and it needs the real Accordion +
// BBoxSection composition to demonstrate. This file covers the hook's own
// state machine in isolation: start/outcome/toast wiring, page-navigation
// safety (round 2 finding 1), and the stall timeout (round 2 finding 3).

import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useBboxRefineTracking } from "./useBboxRefineTracking";

const toastMock = vi.hoisted(() => {
  const fn = Object.assign(vi.fn(), {
    loading: vi.fn(),
    success: vi.fn(),
    error: vi.fn(),
  });
  return fn;
});
vi.mock("sonner", () => ({
  toast: toastMock,
}));

/** Build a synthetic SSE frame in the real wire shape — mirrors
 * BBoxSection.test.tsx's `jobFrame`. */
function jobFrame(input: {
  job_id: string;
  status: string;
  progress?: { message?: string; current?: number; total?: number };
  error_message?: string | null;
  result?: Record<string, unknown> | null;
}) {
  return {
    id: input.job_id,
    type: "refine_bboxes",
    project_id: "p1",
    status: input.status,
    progress: { current: 0, total: 0, message: "", ...input.progress },
    error_message: input.error_message ?? null,
    result: input.result ?? null,
    created_at: new Date(0).toISOString(),
    updated_at: new Date(0).toISOString(),
    event: input.status,
  };
}

function mockEventSource() {
  let progressListener: ((e: MessageEvent) => void) | null = null;
  const mockES = {
    addEventListener: vi.fn((type: string, fn: unknown) => {
      if (type === "progress" || type === "complete" || type === "error") {
        progressListener = fn as (e: MessageEvent) => void;
      }
    }),
    removeEventListener: vi.fn(),
    close: vi.fn(),
    readyState: 1 as number,
  };
  vi.stubGlobal(
    "EventSource",
    vi.fn(function () {
      return mockES;
    }),
  );
  return {
    dispatch(data: Parameters<typeof jobFrame>[0]) {
      act(() => {
        progressListener?.({ data: JSON.stringify(jobFrame(data)) } as MessageEvent);
      });
    },
  };
}

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
  const Wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { qc, invalidateSpy, Wrapper };
}

describe("useBboxRefineTracking", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("start() sets jobId and word (projectId, pageIndex, wordKey)", () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useBboxRefineTracking("p1", 0), { wrapper: Wrapper });

    expect(result.current.jobId).toBeNull();
    expect(result.current.word).toBeNull();

    act(() => {
      result.current.start("job-1", "0-0");
    });

    expect(result.current.jobId).toBe("job-1");
    expect(result.current.word).toEqual({ projectId: "p1", pageIndex: 0, wordKey: "0-0" });
  });

  it("a completed job with refined > 0 sets outcome, invalidates, and shows success", () => {
    const { Wrapper, invalidateSpy } = makeWrapper();
    const es = mockEventSource();
    const { result } = renderHook(() => useBboxRefineTracking("p1", 0), { wrapper: Wrapper });

    act(() => {
      result.current.start("job-1", "0-0");
    });

    es.dispatch({ job_id: "job-1", status: "complete", result: { refined: 2 } });

    expect(result.current.outcome).toEqual({
      word: { projectId: "p1", pageIndex: 0, wordKey: "0-0" },
      refined: 2,
      token: 1,
    });
    expect(result.current.jobId).toBeNull();
    expect(result.current.word).toBeNull();
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["page", "p1", 0] }),
    );
    // lib/toast.ts's success()/warn()/error() all call the base sonner
    // `toast(message, opts)` function directly (styling via a border-left
    // color, not sonner's own .success()/.warn()/.error() methods) — so the
    // mock's calls live on the callable itself, not sub-properties of it.
    expect(toastMock).toHaveBeenCalledWith(
      expect.stringContaining("Bbox refine complete"),
      expect.objectContaining({ id: "job-1" }),
    );

    vi.unstubAllGlobals();
  });

  it("a completed job with refined: 0 does not set outcome and says nothing changed", () => {
    const { Wrapper } = makeWrapper();
    const es = mockEventSource();
    const { result } = renderHook(() => useBboxRefineTracking("p1", 0), { wrapper: Wrapper });

    act(() => {
      result.current.start("job-1", "0-0");
    });

    es.dispatch({ job_id: "job-1", status: "complete", result: { refined: 0 } });

    expect(result.current.outcome).toBeNull();
    expect(result.current.jobId).toBeNull();
    expect(toastMock).toHaveBeenCalledWith(
      expect.stringContaining("nothing changed"),
      expect.objectContaining({ id: "job-1" }),
    );
    const successCall = toastMock.mock.calls.find(
      ([msg]: [unknown]) => msg === "Bbox refine complete",
    );
    expect(successCall).toBeUndefined();

    vi.unstubAllGlobals();
  });

  it("two outcomes for the same word with the same refined count get distinct tokens", () => {
    const { Wrapper } = makeWrapper();
    const es = mockEventSource();
    const { result } = renderHook(() => useBboxRefineTracking("p1", 0), { wrapper: Wrapper });

    act(() => {
      result.current.start("job-1", "0-0");
    });
    es.dispatch({ job_id: "job-1", status: "complete", result: { refined: 1 } });
    expect(result.current.outcome?.token).toBe(1);

    act(() => {
      result.current.start("job-2", "0-0");
    });
    es.dispatch({ job_id: "job-2", status: "complete", result: { refined: 1 } });
    expect(result.current.outcome?.token).toBe(2);

    vi.unstubAllGlobals();
  });

  it("a failed job shows an error toast and clears jobId without setting outcome", () => {
    const { Wrapper } = makeWrapper();
    const es = mockEventSource();
    const { result } = renderHook(() => useBboxRefineTracking("p1", 0), { wrapper: Wrapper });

    act(() => {
      result.current.start("job-1", "0-0");
    });
    es.dispatch({ job_id: "job-1", status: "error", error_message: "boom" });

    expect(toastMock).toHaveBeenCalledWith("boom", expect.objectContaining({ id: "job-1" }));
    expect(result.current.jobId).toBeNull();
    expect(result.current.outcome).toBeNull();

    vi.unstubAllGlobals();
  });

  // ─── Review round 2, finding 1 (high): ProjectPage is reused across page
  // and project navigation, so the project/page a job started on must be
  // captured at start() time, not read reactively from this hook's own
  // (drifting) parameters when the job later completes. ──────────────────

  it("invalidates the page a job started on, not whatever page is current when it completes", () => {
    const { Wrapper, invalidateSpy } = makeWrapper();
    const es = mockEventSource();
    const { result, rerender } = renderHook(
      ({ pageIndex }: { pageIndex: number }) => useBboxRefineTracking("p1", pageIndex),
      { wrapper: Wrapper, initialProps: { pageIndex: 3 } },
    );

    act(() => {
      result.current.start("job-1", "0-0");
    });

    // Navigate to page 4 before the job completes — ProjectPage re-renders
    // this same hook instance with new props; the job is still about the
    // bbox on page 3.
    rerender({ pageIndex: 4 });

    es.dispatch({ job_id: "job-1", status: "complete", result: { refined: 1 } });

    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["page", "p1", 3] }),
    );
    expect(invalidateSpy).not.toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["page", "p1", 4] }),
    );

    vi.unstubAllGlobals();
  });

  it("qualifies the outcome's word by the page the job started on — a same-indexed word on another page does not match", () => {
    const { Wrapper } = makeWrapper();
    const es = mockEventSource();
    const { result, rerender } = renderHook(
      ({ pageIndex }: { pageIndex: number }) => useBboxRefineTracking("p1", pageIndex),
      { wrapper: Wrapper, initialProps: { pageIndex: 3 } },
    );

    act(() => {
      result.current.start("job-1", "0-0");
    });
    rerender({ pageIndex: 4 });
    es.dispatch({ job_id: "job-1", status: "complete", result: { refined: 1 } });

    // A BBoxSection for word "0-0" now showing page 4 must not treat this
    // outcome as its own — it belongs to page 3's word "0-0", a different
    // word that merely shares the same (line, word) index.
    const outcome = result.current.outcome;
    expect(outcome).not.toBeNull();
    expect(outcome?.word).toEqual({ projectId: "p1", pageIndex: 3, wordKey: "0-0" });
    const matchesPage4Word00 =
      outcome?.word.projectId === "p1" &&
      outcome.word.pageIndex === 4 &&
      outcome.word.wordKey === "0-0";
    expect(matchesPage4Word00).toBe(false);

    vi.unstubAllGlobals();
  });

  // ─── Review round 2, finding 3 (medium): refine_bboxes is not
  // cancellable; a job that never reaches a terminal state must not leave
  // this tracker's one slot claimed forever. ─────────────────────────────

  describe("stall timeout", () => {
    beforeEach(() => {
      vi.useFakeTimers();
    });
    afterEach(() => {
      vi.useRealTimers();
      vi.unstubAllGlobals();
    });

    it("clears the slot and warns if the job never reaches a terminal state", () => {
      const { Wrapper } = makeWrapper();
      mockEventSource(); // stubs EventSource; no frame is ever dispatched — the hang this guards against.
      const { result } = renderHook(() => useBboxRefineTracking("p1", 0), { wrapper: Wrapper });

      act(() => {
        result.current.start("job-stuck", "0-0");
      });
      expect(result.current.jobId).toBe("job-stuck");

      act(() => {
        vi.advanceTimersByTime(30_000);
      });

      expect(result.current.jobId).toBeNull();
      expect(result.current.word).toBeNull();
      expect(toastMock).toHaveBeenCalledWith(
        expect.stringContaining("timed out"),
        expect.objectContaining({ id: "job-stuck" }),
      );
    });

    it("does not fire the stall warning for a job that completes before the timeout", () => {
      const { Wrapper } = makeWrapper();
      const es = mockEventSource();
      const { result } = renderHook(() => useBboxRefineTracking("p1", 0), { wrapper: Wrapper });

      act(() => {
        result.current.start("job-1", "0-0");
      });
      es.dispatch({ job_id: "job-1", status: "complete", result: { refined: 1 } });

      act(() => {
        vi.advanceTimersByTime(30_000);
      });

      const timeoutCall = toastMock.mock.calls.find(
        ([msg]: [unknown]) => typeof msg === "string" && msg.includes("timed out"),
      );
      expect(timeoutCall).toBeUndefined();
    });
  });
});

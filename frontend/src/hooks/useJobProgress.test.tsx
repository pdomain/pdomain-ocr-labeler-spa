// useJobProgress.test.tsx — unit tests for the useJobProgress SSE hook.
// Covers: B-JOBS-001, B-ACTIONS-010, F-JOB-SSE-01
// Spec: docs/specs/2026-05-12-frontend-shell-design.md §Hooks
// Issue #192; Wave 3a / P1-JOB-SSE.
//
// Key contracts:
//   - Opens EventSource for /api/jobs/{jobId}/events
//   - Returns null until first event
//   - Handles the first `snapshot` frame, not just `progress`
//   - Closes EventSource on unmount
//   - Closes EventSource on a terminal event (complete / error / cancelled)
//   - Resets to null when jobId changes
//   - Drops malformed / incomplete frames instead of surfacing a partial event

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { useJobProgress, type JobProgressEvent } from "./useJobProgress";
import { subscribeJobsBus } from "../lib/jobsBus";

// --- minimal EventSource mock ---

interface MockEventSource {
  url: string;
  listeners: Record<string, ((e: MessageEvent) => void)[]>;
  /** readyState: 0=CONNECTING, 1=OPEN, 2=CLOSED (mirrors EventSource API) */
  readyState: number;
  addEventListener(type: string, fn: (e: MessageEvent) => void): void;
  removeEventListener(type: string, fn: (e: MessageEvent) => void): void;
  close(): void;
  _emit(type: string, data: unknown): void;
}

function makeMockEventSource(url: string): MockEventSource {
  const es: MockEventSource = {
    url,
    listeners: {},
    readyState: 1, // OPEN
    addEventListener(type, fn) {
      es.listeners[type] = es.listeners[type] ?? [];
      es.listeners[type].push(fn);
    },
    removeEventListener(type, fn) {
      es.listeners[type] = (es.listeners[type] ?? []).filter((h) => h !== fn);
    },
    close() {
      es.readyState = 2; // CLOSED
    },
    _emit(type, data) {
      const e = new MessageEvent(type, { data: JSON.stringify(data) });
      (es.listeners[type] ?? []).forEach((h) => h(e));
    },
  };
  return es;
}

let lastSource: MockEventSource | null = null;

beforeEach(() => {
  lastSource = null;
  // Vitest 5 requires the mock's implementation to be a `function`/`class`
  // (not an arrow function) when the mock is invoked with `new` — an arrow
  // function is never constructible per the JS spec, and vi.fn() no longer
  // papers over that. `useJobProgress` calls `new EventSource(...)`, so the
  // stub must be a real function expression.
  const MockES = vi.fn(function (url: string) {
    lastSource = makeMockEventSource(url);
    return lastSource;
  });
  // Provide the static CLOSED constant that the production code reads.
  (MockES as unknown as { CLOSED: number }).CLOSED = 2;
  vi.stubGlobal("EventSource", MockES);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

/**
 * Build a wire-shaped SSE frame: the public `Job` model plus the `event`
 * field naming the SSE event kind — the real shape the backend sends today
 * (docs/issues/2026-07-21-job-sse-fe-be-shape-mismatch.md). Callers supply
 * only what a given test cares about; everything else defaults.
 */
function wireFrame(overrides: {
  id?: string;
  type?: string;
  status: string;
  progress?: { current?: number; total?: number; message?: string };
  error_message?: string | null;
  event?: string;
  result?: Record<string, unknown> | null;
}) {
  return {
    id: overrides.id ?? "job-abc",
    type: overrides.type ?? "reload_ocr",
    project_id: "proj-1",
    status: overrides.status,
    progress: { current: 0, total: 0, message: "", ...overrides.progress },
    error_message: overrides.error_message ?? null,
    created_at: new Date(0).toISOString(),
    updated_at: new Date(0).toISOString(),
    event: overrides.event ?? overrides.status,
    result: overrides.result ?? null,
  };
}

const RUNNING_FRAME = wireFrame({
  status: "running",
  progress: { current: 3, total: 10, message: "Processing…" },
  event: "progress",
});

const COMPLETE_FRAME = wireFrame({
  status: "complete",
  progress: { current: 10, total: 10, message: "Done" },
});

const ERROR_FRAME = wireFrame({
  status: "error",
  progress: { current: 5, total: 10, message: "Failed" },
  error_message: "OCR engine crashed",
});

const CANCELLED_FRAME = wireFrame({
  status: "cancelled",
  progress: { current: 4, total: 10, message: "Cancelled after page 4" },
});

describe("useJobProgress", () => {
  it("returns null initially", () => {
    const { result } = renderHook(() => useJobProgress("job-abc"));
    expect(result.current).toBeNull();
  });

  it("opens EventSource at correct URL", () => {
    renderHook(() => useJobProgress("job-abc"));
    expect(lastSource).not.toBeNull();
    expect(lastSource?.url).toBe("/api/jobs/job-abc/events");
  });

  it("does NOT open EventSource when jobId is null", () => {
    renderHook(() => useJobProgress(null));
    expect(lastSource).toBeNull();
  });

  it("does NOT open EventSource when jobId is undefined", () => {
    renderHook(() => useJobProgress(undefined));
    expect(lastSource).toBeNull();
  });

  it("parses a wire-shaped 'progress' frame", async () => {
    const { result } = renderHook(() => useJobProgress("job-abc"));

    act(() => {
      lastSource!._emit("progress", RUNNING_FRAME);
    });

    await waitFor(() => expect(result.current).not.toBeNull());
    expect(result.current?.status).toBe("running");
    expect(result.current?.progress.current).toBe(3);
    expect(result.current?.progress.total).toBe(10);
    expect(result.current?.id).toBe("job-abc");
    expect(result.current?.type).toBe("reload_ocr");
  });

  it("surfaces a terminal frame's `result` field (e.g. export stats)", async () => {
    const { result } = renderHook(() => useJobProgress("job-abc"));

    act(() => {
      lastSource!._emit(
        "complete",
        wireFrame({
          status: "complete",
          progress: { current: 5, total: 5, message: "done" },
          result: { words_exported_detection: 42, pages_skipped_not_validated: 0 },
        }),
      );
    });

    await waitFor(() => expect(result.current).not.toBeNull());
    expect(result.current?.result).toEqual({
      words_exported_detection: 42,
      pages_skipped_not_validated: 0,
    });
  });

  it("leaves `result` null when the backend sends no result", async () => {
    const { result } = renderHook(() => useJobProgress("job-abc"));

    act(() => {
      lastSource!._emit("progress", RUNNING_FRAME);
    });

    await waitFor(() => expect(result.current).not.toBeNull());
    expect(result.current?.result).toBeNull();
  });

  it("handles the 'snapshot' event (first frame)", async () => {
    const { result } = renderHook(() => useJobProgress("job-abc"));

    act(() => {
      lastSource!._emit(
        "snapshot",
        wireFrame({
          status: "running",
          progress: { current: 1, total: 5, message: "Starting" },
          event: "snapshot",
        }),
      );
    });

    await waitFor(() => expect(result.current).not.toBeNull());
    expect(result.current?.progress.current).toBe(1);
    expect(result.current?.event).toBe("snapshot");
  });

  it("signals jobsBus once it starts tracking a job and again on its terminal event", async () => {
    const listener = vi.fn();
    const unsubscribe = subscribeJobsBus(listener);

    const { result } = renderHook(() => useJobProgress("job-abc"));
    expect(listener).toHaveBeenCalledTimes(1);

    const src = lastSource!;
    act(() => {
      src._emit("complete", COMPLETE_FRAME);
    });
    await waitFor(() => expect(result.current?.status).toBe("complete"));

    expect(listener).toHaveBeenCalledTimes(2);
    unsubscribe();
  });

  it("closes EventSource on unmount before terminal event", () => {
    const { unmount } = renderHook(() => useJobProgress("job-abc"));
    const src = lastSource!;
    unmount();
    expect(src.readyState).toBe(2); // CLOSED
  });

  it("closes EventSource on 'complete' terminal event", async () => {
    const { result } = renderHook(() => useJobProgress("job-abc"));
    const src = lastSource!;

    act(() => {
      src._emit("complete", COMPLETE_FRAME);
    });

    await waitFor(() => expect(result.current?.status).toBe("complete"));
    expect(src.readyState).toBe(2); // CLOSED
  });

  it("closes EventSource on 'error' terminal event", async () => {
    const { result } = renderHook(() => useJobProgress("job-abc"));
    const src = lastSource!;

    act(() => {
      src._emit("error", ERROR_FRAME);
    });

    await waitFor(() => expect(result.current?.status).toBe("error"));
    expect(result.current?.error_message).toBe("OCR engine crashed");
    expect(src.readyState).toBe(2); // CLOSED
  });

  it("closes EventSource on 'cancelled' terminal event", async () => {
    const { result } = renderHook(() => useJobProgress("job-abc"));
    const src = lastSource!;

    act(() => {
      src._emit("cancelled", CANCELLED_FRAME);
    });

    await waitFor(() => expect(result.current?.status).toBe("cancelled"));
    expect(result.current?.progress.message).toBe("Cancelled after page 4");
    expect(src.readyState).toBe(2); // CLOSED
  });

  it("resets to null when jobId changes", async () => {
    let jobId = "job-abc";
    const { result, rerender } = renderHook(() => useJobProgress(jobId));

    act(() => {
      lastSource!._emit("progress", RUNNING_FRAME);
    });
    await waitFor(() => expect(result.current).not.toBeNull());

    jobId = "job-xyz";
    rerender();

    await waitFor(() => expect(result.current).toBeNull());
  });

  it("ignores malformed JSON in SSE events", async () => {
    const { result } = renderHook(() => useJobProgress("job-abc"));

    act(() => {
      const e = new MessageEvent("progress", { data: "not-valid-json{{{" });
      (lastSource!.listeners["progress"] ?? []).forEach((h) => h(e));
    });

    // State should remain null — no crash
    expect(result.current).toBeNull();
  });

  it("ignores a frame missing required fields (e.g. no `type`)", async () => {
    const { result } = renderHook(() => useJobProgress("job-abc"));

    act(() => {
      lastSource!._emit("progress", {
        id: "job-abc",
        status: "running",
        progress: { current: 1, total: 2, message: "" },
        event: "progress",
        // `type` deliberately omitted.
      });
    });

    expect(result.current).toBeNull();
  });

  it("satisfies JobProgressEvent's declared shape (type-level smoke check)", () => {
    // No assertions — this only needs to compile. It fails tsc if
    // JobProgressEvent's fields ever drift from the public Job model.
    const sample: JobProgressEvent = {
      id: "job-abc",
      type: "export",
      project_id: null,
      status: "cancelled",
      progress: { current: 1, total: 2, message: "" },
      created_at: new Date(0).toISOString(),
      updated_at: new Date(0).toISOString(),
      event: "cancelled",
    };
    expect(sample.status).toBe("cancelled");
  });
});

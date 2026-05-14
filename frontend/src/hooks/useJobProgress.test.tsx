// useJobProgress.test.tsx — unit tests for the useJobProgress SSE hook.
// Spec: docs/specs/2026-05-12-frontend-shell-design.md §Hooks
// Issue #192
//
// Key contracts:
//   - Opens EventSource for /api/jobs/{jobId}/events
//   - Returns null until first event
//   - Closes EventSource on unmount
//   - Closes EventSource on terminal event (complete / error)
//   - Resets to null when jobId changes

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { useJobProgress, type JobProgressEvent } from "./useJobProgress";

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
  const MockES = vi.fn((url: string) => {
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

const RUNNING_EVENT: JobProgressEvent = {
  job_id: "job-abc",
  status: "running",
  progress: { current: 3, total: 10, message: "Processing…" },
};

const COMPLETE_EVENT: JobProgressEvent = {
  job_id: "job-abc",
  status: "complete",
  progress: { current: 10, total: 10, message: "Done" },
};

const ERROR_EVENT: JobProgressEvent = {
  job_id: "job-abc",
  status: "error",
  progress: { current: 5, total: 10, message: "Failed" },
  error_message: "OCR engine crashed",
};

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

  it("updates with progress events", async () => {
    const { result } = renderHook(() => useJobProgress("job-abc"));

    act(() => {
      lastSource!._emit("progress", RUNNING_EVENT);
    });

    await waitFor(() => expect(result.current).not.toBeNull());
    expect(result.current?.status).toBe("running");
    expect(result.current?.progress.current).toBe(3);
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
      src._emit("progress", COMPLETE_EVENT);
    });

    await waitFor(() => expect(result.current?.status).toBe("complete"));
    expect(src.readyState).toBe(2); // CLOSED
  });

  it("closes EventSource on 'error' terminal event", async () => {
    const { result } = renderHook(() => useJobProgress("job-abc"));
    const src = lastSource!;

    act(() => {
      src._emit("progress", ERROR_EVENT);
    });

    await waitFor(() => expect(result.current?.status).toBe("error"));
    expect(src.readyState).toBe(2); // CLOSED
  });

  it("resets to null when jobId changes", async () => {
    let jobId = "job-abc";
    const { result, rerender } = renderHook(() => useJobProgress(jobId));

    act(() => {
      lastSource!._emit("progress", RUNNING_EVENT);
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
});

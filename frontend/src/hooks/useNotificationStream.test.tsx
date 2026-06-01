// useNotificationStream.test.tsx — unit tests for the SSE notification hook.
// Covers: B-JOBS-002, B-ACTIONS-011, F-NOTIFICATIONS-01
// Spec: docs/specs/2026-05-12-notifications-design.md §useNotificationStream hook
// Issue #231

import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { useNotificationStream } from "./useNotificationStream";

// --- minimal EventSource mock ---

interface MockEventSource {
  url: string;
  listeners: Record<string, ((e: MessageEvent) => void)[]>;
  addEventListener(type: string, fn: (e: MessageEvent) => void): void;
  removeEventListener(type: string, fn: (e: MessageEvent) => void): void;
  close(): void;
  _emit(type: string, data: string): void;
  closed: boolean;
}

function makeMockEventSource(url: string): MockEventSource {
  const es: MockEventSource = {
    url,
    listeners: {},
    closed: false,
    addEventListener(type, fn) {
      es.listeners[type] = es.listeners[type] ?? [];
      es.listeners[type].push(fn);
    },
    removeEventListener(type, fn) {
      es.listeners[type] = (es.listeners[type] ?? []).filter((h) => h !== fn);
    },
    close() {
      es.closed = true;
    },
    _emit(type, data) {
      const e = new MessageEvent(type, { data });
      (es.listeners[type] ?? []).forEach((h) => h(e));
    },
  };
  return es;
}

let lastSource: MockEventSource | null = null;

beforeEach(() => {
  lastSource = null;
  vi.stubGlobal(
    "EventSource",
    vi.fn((url: string) => {
      lastSource = makeMockEventSource(url);
      return lastSource;
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

// We mock the 'sonner' module so we can track toast.* calls.
vi.mock("sonner", () => ({
  toast: vi.fn(),
}));

// We mock our toast wrapper to track calls (internally uses mocked sonner).
vi.mock("../lib/toast", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    warn: vi.fn(),
    info: vi.fn(),
  },
}));

import { toast } from "../lib/toast";

/** Extract the `message` prop from the JSX element passed as the first toast arg. */
function lastCallMessage(mockFn: ReturnType<typeof vi.fn>): string {
  const calls = mockFn.mock.calls;
  if (calls.length === 0) return "";
  const firstArg = calls[calls.length - 1][0] as React.ReactElement<{
    message: string;
  }>;
  return firstArg?.props?.message ?? String(firstArg);
}

describe("useNotificationStream", () => {
  it("opens EventSource on /api/notifications/stream", () => {
    renderHook(() => useNotificationStream());
    expect(lastSource).not.toBeNull();
    expect(lastSource?.url).toBe("/api/notifications/stream");
  });

  it("calls toast.success for positive kind", async () => {
    renderHook(() => useNotificationStream());
    act(() => {
      lastSource!._emit(
        "notification",
        JSON.stringify({
          id: "abc",
          kind: "positive",
          message: "Saved!",
          created_at: new Date().toISOString(),
        }),
      );
    });
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    expect(lastCallMessage(vi.mocked(toast.success))).toBe("Saved!");
  });

  it("calls toast.error for negative kind", async () => {
    renderHook(() => useNotificationStream());
    act(() => {
      lastSource!._emit(
        "notification",
        JSON.stringify({
          id: "def",
          kind: "negative",
          message: "OCR failed",
          created_at: new Date().toISOString(),
        }),
      );
    });
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(lastCallMessage(vi.mocked(toast.error))).toBe("OCR failed");
  });

  it("calls toast.warn for warning kind", async () => {
    renderHook(() => useNotificationStream());
    act(() => {
      lastSource!._emit(
        "notification",
        JSON.stringify({
          id: "ghi",
          kind: "warning",
          message: "Low memory",
          created_at: new Date().toISOString(),
        }),
      );
    });
    await waitFor(() => expect(toast.warn).toHaveBeenCalled());
    expect(lastCallMessage(vi.mocked(toast.warn))).toBe("Low memory");
  });

  it("calls toast.info for info kind", async () => {
    renderHook(() => useNotificationStream());
    act(() => {
      lastSource!._emit(
        "notification",
        JSON.stringify({
          id: "jkl",
          kind: "info",
          message: "Project loaded",
          created_at: new Date().toISOString(),
        }),
      );
    });
    await waitFor(() => expect(toast.info).toHaveBeenCalled());
    expect(lastCallMessage(vi.mocked(toast.info))).toBe("Project loaded");
  });

  it("does NOT show toast for auto-save success notifications", async () => {
    vi.mocked(toast.success).mockClear();
    renderHook(() => useNotificationStream());
    act(() => {
      lastSource!._emit(
        "notification",
        JSON.stringify({
          id: "mno",
          kind: "positive",
          message: "auto-save: page saved",
          created_at: new Date().toISOString(),
        }),
      );
    });
    // small wait to ensure no call was made
    await new Promise((r) => setTimeout(r, 20));
    expect(toast.success).not.toHaveBeenCalled();
  });

  it("auto-save failure (negative kind) IS shown as toast", async () => {
    vi.mocked(toast.error).mockClear();
    renderHook(() => useNotificationStream());
    act(() => {
      lastSource!._emit(
        "notification",
        JSON.stringify({
          id: "pqr",
          kind: "negative",
          message: "auto-save: save failed",
          created_at: new Date().toISOString(),
        }),
      );
    });
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(lastCallMessage(vi.mocked(toast.error))).toBe("auto-save: save failed");
  });

  it("toast JSX element carries kind and id props for data-testid rendering", async () => {
    renderHook(() => useNotificationStream());
    act(() => {
      lastSource!._emit(
        "notification",
        JSON.stringify({
          id: "stu",
          kind: "positive",
          message: "Done",
          created_at: new Date().toISOString(),
        }),
      );
    });
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    const calls = vi.mocked(toast.success).mock.calls;
    const elem = calls[calls.length - 1][0] as React.ReactElement<{
      kind: string;
      id: string;
      message: string;
    }>;
    // ToastMessage props: kind, id, message
    expect(elem?.props?.kind).toBe("positive");
    expect(elem?.props?.id).toBe("stu");
    expect(elem?.props?.message).toBe("Done");
  });

  it("closes EventSource on unmount", () => {
    const { unmount } = renderHook(() => useNotificationStream());
    const src = lastSource!;
    unmount();
    expect(src.closed).toBe(true);
  });
});

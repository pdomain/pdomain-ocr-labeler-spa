// rafSchedule.test.ts — unit tests for the single-flight rAF batcher.
// Spec: specs/21-konva-renderer.md §7
// Issue #301
//
// Acceptance:
//   - Multiple calls in the same tick run the scheduled fn exactly once
//     on the next animation frame.
//   - After the frame fires, a subsequent call schedules another frame.
//   - The first call's fn is the one that runs (single-flight); later
//     same-frame calls are no-ops (standard rAF-throttle pattern).

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";

import { scheduleDragUpdate } from "./rafSchedule";

describe("scheduleDragUpdate", () => {
  let rafCallbacks: FrameRequestCallback[];
  let rafSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    rafCallbacks = [];
    rafSpy = vi.fn((cb: FrameRequestCallback) => {
      rafCallbacks.push(cb);
      return rafCallbacks.length; // synthetic handle
    });
    vi.stubGlobal("requestAnimationFrame", rafSpy);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function flushFrame() {
    const pending = rafCallbacks;
    rafCallbacks = [];
    pending.forEach((cb) => cb(performance.now()));
  }

  it("runs fn exactly once on the next animation frame", () => {
    const fn = vi.fn();
    scheduleDragUpdate(fn);
    expect(fn).not.toHaveBeenCalled();
    expect(rafSpy).toHaveBeenCalledTimes(1);
    flushFrame();
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it("coalesces multiple same-frame calls into a single rAF (first fn wins)", () => {
    const first = vi.fn();
    const second = vi.fn();
    const third = vi.fn();
    scheduleDragUpdate(first);
    scheduleDragUpdate(second);
    scheduleDragUpdate(third);
    // Only one rAF was scheduled across all three calls.
    expect(rafSpy).toHaveBeenCalledTimes(1);
    flushFrame();
    // Standard rAF-throttle: the first call's fn runs once; later
    // same-frame calls are dropped no-ops.
    expect(first).toHaveBeenCalledTimes(1);
    expect(second).not.toHaveBeenCalled();
    expect(third).not.toHaveBeenCalled();
  });

  it("re-arms after the frame fires so the next call schedules again", () => {
    const fnA = vi.fn();
    scheduleDragUpdate(fnA);
    flushFrame();
    expect(fnA).toHaveBeenCalledTimes(1);
    expect(rafSpy).toHaveBeenCalledTimes(1);

    const fnB = vi.fn();
    scheduleDragUpdate(fnB);
    expect(rafSpy).toHaveBeenCalledTimes(2);
    flushFrame();
    expect(fnB).toHaveBeenCalledTimes(1);
  });
});

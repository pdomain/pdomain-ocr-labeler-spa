// rail-store.test.ts — Tests for the Rail target/mode store.
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 10.
// Hi-fi gap P1.f (Gap 14): para added as valid target.

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { railStore, RAIL_TARGET_STORAGE_KEY } from "./rail-store";

describe("rail-store (Slice 10)", () => {
  beforeEach(() => {
    // Reset store to defaults and clear localStorage before each test.
    railStore.reset();
    localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("initial target is 'word'", () => {
    expect(railStore.getState().target).toBe("word");
  });

  it("initial mode is 'view'", () => {
    expect(railStore.getState().mode).toBe("view");
  });

  it("setTarget updates target to block", () => {
    railStore.getState().setTarget("block");
    expect(railStore.getState().target).toBe("block");
  });

  it("setTarget updates target to para", () => {
    railStore.getState().setTarget("para");
    expect(railStore.getState().target).toBe("para");
  });

  it("setMode updates mode", () => {
    railStore.getState().setMode("annotate");
    expect(railStore.getState().mode).toBe("annotate");
  });

  it("setTarget persists target to localStorage", () => {
    railStore.getState().setTarget("line");
    expect(localStorage.getItem(RAIL_TARGET_STORAGE_KEY)).toBe("line");
  });

  it("target persistence round-trip: reset reads from localStorage", () => {
    localStorage.setItem(RAIL_TARGET_STORAGE_KEY, "block");
    railStore.reset();
    expect(railStore.getState().target).toBe("block");
  });

  it("ignores invalid localStorage value on reset", () => {
    localStorage.setItem(RAIL_TARGET_STORAGE_KEY, "invalid-value");
    railStore.reset();
    expect(railStore.getState().target).toBe("word");
  });

  it("subscribe callback fires on state change", () => {
    const cb = vi.fn();
    const unsub = railStore.subscribe(cb);
    railStore.getState().setTarget("block");
    expect(cb).toHaveBeenCalledTimes(1);
    unsub();
    railStore.getState().setTarget("line");
    // After unsub, no more calls
    expect(cb).toHaveBeenCalledTimes(1);
  });
});

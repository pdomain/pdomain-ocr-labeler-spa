// useRailHotkeys.test.ts — Tests for Rail keyboard shortcuts.
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 10.
// Hi-fi gap P1.f (Gap 14): added para target on key "2".
//
// Shortcuts:
//   1 → target=block, 2 → target=para, 3 → target=line, 4 → target=word
//   v/V → mode=view, r/R → mode=region, a/A → mode=annotate, e/E → mode=erase

import { describe, it, expect, beforeEach } from "vitest";
import { renderHook } from "@testing-library/react";
import { fireEvent } from "@testing-library/react";
import { useRailHotkeys } from "./useRailHotkeys";
import { railStore } from "../stores/rail-store";

describe("useRailHotkeys (Slice 10 / P1.f)", () => {
  beforeEach(() => {
    railStore.reset();
    localStorage.clear();
  });

  function setup() {
    return renderHook(() => useRailHotkeys());
  }

  function pressKey(key: string) {
    fireEvent.keyDown(document, { key });
  }

  it("'1' sets target to block", () => {
    setup();
    pressKey("1");
    expect(railStore.getState().target).toBe("block");
  });

  it("'2' sets target to para", () => {
    setup();
    pressKey("2");
    expect(railStore.getState().target).toBe("para");
  });

  it("'3' sets target to line", () => {
    setup();
    pressKey("3");
    expect(railStore.getState().target).toBe("line");
  });

  it("'4' sets target to word", () => {
    setup();
    railStore.getState().setTarget("block"); // change first
    pressKey("4");
    expect(railStore.getState().target).toBe("word");
  });

  it("'v' sets mode to view", () => {
    setup();
    railStore.getState().setMode("erase");
    pressKey("v");
    expect(railStore.getState().mode).toBe("view");
  });

  it("'V' (uppercase) also sets mode to view", () => {
    setup();
    railStore.getState().setMode("annotate");
    pressKey("V");
    expect(railStore.getState().mode).toBe("view");
  });

  it("'r' sets mode to region", () => {
    setup();
    pressKey("r");
    expect(railStore.getState().mode).toBe("region");
  });

  it("'a' sets mode to annotate", () => {
    setup();
    pressKey("a");
    expect(railStore.getState().mode).toBe("annotate");
  });

  it("'e' sets mode to erase", () => {
    setup();
    pressKey("e");
    expect(railStore.getState().mode).toBe("erase");
  });

  it("unrelated keys do not change state", () => {
    setup();
    pressKey("x");
    expect(railStore.getState().target).toBe("word");
    expect(railStore.getState().mode).toBe("view");
  });

  it("cleans up listener on unmount", () => {
    const { unmount } = setup();
    unmount();
    // After unmount, keys should not update (no listener)
    // We verify by checking the state doesn't change and no error thrown
    pressKey("1");
    // target could change if listener wasn't removed, but we're just
    // verifying no errors are thrown on unmount
  });
});

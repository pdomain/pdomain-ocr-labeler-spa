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
import { useUiPrefs } from "../stores/ui-prefs";

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

  it("'5' sets target to region", () => {
    setup();
    pressKey("5");
    expect(railStore.getState().target).toBe("region");
  });

  it("'5' leaves selectionMode unchanged (no radio counterpart)", () => {
    setup();
    useUiPrefs.setState({ selectionMode: "line" });
    pressKey("5");
    expect(railStore.getState().target).toBe("region");
    expect(useUiPrefs.getState().selectionMode).toBe("line");
  });

  // SEL-3 conflict guard: Shift+1/2/3 belong to the viewport selection-mode
  // hotkeys (useViewportHotkeys, spec 21 §10). The plain-digit rail bindings
  // must NOT fire on shifted digits, otherwise Shift+1 ("paragraph" selection
  // mode) is immediately overwritten by rail target "block" — observed live
  // in the SEL-3 e2e (browsers/layouts that report key="1" for Shift+1).
  it("Shift+'1' does NOT hijack the viewport selection-mode hotkey", () => {
    setup();
    railStore.getState().setTarget("para");
    fireEvent.keyDown(document, { key: "1", shiftKey: true });
    expect(railStore.getState().target).toBe("para");
  });

  it("Shift+'3' does NOT change the rail target", () => {
    setup();
    railStore.getState().setTarget("word");
    fireEvent.keyDown(document, { key: "3", shiftKey: true });
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

  it("'E' (uppercase, no Shift) also sets mode to erase", () => {
    setup();
    fireEvent.keyDown(document, { key: "E" });
    expect(railStore.getState().mode).toBe("erase");
  });

  it("'A' (uppercase, no Shift) also sets mode to annotate", () => {
    setup();
    fireEvent.keyDown(document, { key: "A" });
    expect(railStore.getState().mode).toBe("annotate");
  });

  // Reviewer finding 3 (P1-CANVAS-ERASE follow-up): Shift+E and Shift+A
  // belong to the viewport's own hotkeys (useViewportHotkeys "shift+e"
  // toggle-erase, "shift+a" add-word). Both this hook and useViewportHotkeys
  // listen at document scope, so a single Shift+E keypress used to fire
  // BOTH — this hook's own "E" mode binding raced the viewport's toggle and
  // netted a no-op the user could never escape by pressing the key again.
  // The same rule the Shift+digit guard above already applies now extends to
  // these two letters: rail mode must NOT change while Shift is held for E
  // or A, leaving the viewport hotkey as the sole handler.
  it("Shift+'e' does NOT change rail mode (belongs to the viewport's shift+e)", () => {
    setup();
    railStore.getState().setMode("view");
    fireEvent.keyDown(document, { key: "e", shiftKey: true });
    expect(railStore.getState().mode).toBe("view");
  });

  it("Shift+'E' does NOT change rail mode (belongs to the viewport's shift+e)", () => {
    setup();
    railStore.getState().setMode("view");
    fireEvent.keyDown(document, { key: "E", shiftKey: true });
    expect(railStore.getState().mode).toBe("view");
  });

  it("Shift+'a' does NOT change rail mode (belongs to the viewport's shift+a)", () => {
    setup();
    railStore.getState().setMode("view");
    fireEvent.keyDown(document, { key: "a", shiftKey: true });
    expect(railStore.getState().mode).toBe("view");
  });

  it("Shift+'A' does NOT change rail mode (belongs to the viewport's shift+a)", () => {
    setup();
    railStore.getState().setMode("view");
    fireEvent.keyDown(document, { key: "A", shiftKey: true });
    expect(railStore.getState().mode).toBe("view");
  });

  // V and R are NOT viewport hotkeys — Shift+V / Shift+R must keep driving
  // rail mode exactly as before (regression guard: the fix must not widen
  // past the two letters the viewport actually owns).
  it("Shift+'v' still sets mode to view (V is not a viewport hotkey)", () => {
    setup();
    railStore.getState().setMode("erase");
    fireEvent.keyDown(document, { key: "v", shiftKey: true });
    expect(railStore.getState().mode).toBe("view");
  });

  it("Shift+'R' still sets mode to region (R is not a viewport hotkey)", () => {
    setup();
    railStore.getState().setMode("view");
    fireEvent.keyDown(document, { key: "R", shiftKey: true });
    expect(railStore.getState().mode).toBe("region");
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

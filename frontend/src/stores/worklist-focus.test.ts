// worklist-focus.test.ts — Tests for the shared "focus this line" action.
// Issue: docs/issues/2026-07-21-match-nav-selection-desync.md (P1-MATCH-NAV).
//
// `focusWorklistLine` is the single function the Worklist row click and the
// matches J/K hotkeys both call. These tests pin down the exact triple it
// writes so the two call sites cannot drift apart again.

import { describe, it, expect, beforeEach } from "vitest";
import { focusWorklistLine } from "./worklist-focus";
import { worklistStore } from "./worklist-store";
import { selectionStore, clearSelection, selectWord } from "./selection-store";
import { useUiPrefs } from "./ui-prefs";

describe("focusWorklistLine", () => {
  beforeEach(() => {
    worklistStore.reset();
    clearSelection();
    useUiPrefs.setState({ rightPanelOpen: false });
  });

  it("sets worklistStore.selectedLineIndex", () => {
    focusWorklistLine(3);
    expect(worklistStore.getState().selectedLineIndex).toBe(3);
  });

  it("selects the same line in selectionStore (level/path/selectedLines)", () => {
    focusWorklistLine(3);
    const state = selectionStore.getState();
    expect(state.level).toBe("line");
    expect(state.path).toEqual({ lineId: 3 });
    expect(state.selectedLines).toEqual([3]);
  });

  it("opens the right panel when it was collapsed (STB-4)", () => {
    useUiPrefs.setState({ rightPanelOpen: false });
    focusWorklistLine(3);
    expect(useUiPrefs.getState().rightPanelOpen).toBe(true);
  });

  it("keeps the right panel open when it was already open", () => {
    useUiPrefs.setState({ rightPanelOpen: true });
    focusWorklistLine(3);
    expect(useUiPrefs.getState().rightPanelOpen).toBe(true);
  });

  it("replaces an existing word selection, the same way a row click would", () => {
    selectWord(0, 0);
    expect(selectionStore.getState().level).toBe("word");

    focusWorklistLine(2);

    const state = selectionStore.getState();
    expect(state.level).toBe("line");
    expect(state.selectedWords).toEqual([]);
    expect(state.path).toEqual({ lineId: 2 });
  });
});

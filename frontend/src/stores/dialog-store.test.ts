// dialog-store.test.ts — contract tests for the dialog store.
// Spec: specs/22-page-surface-wireup.md §5
// Issue #309 (spec-22-A)

import { describe, it, expect, beforeEach, vi } from "vitest";
import { dialogStore } from "./dialog-store";

beforeEach(() => {
  dialogStore.reset();
});

describe("dialog-store: initial state", () => {
  it("starts with all dialogs closed", () => {
    const state = dialogStore.getState();
    expect(state.ocrConfig.open).toBe(false);
    expect(state.export.open).toBe(false);
    expect(state.hotkeyHelp.open).toBe(false);
    expect(state.confirm.open).toBe(false);
  });

  it("does not expose retired word-edit dialog state or launch API", () => {
    const state = dialogStore.getState() as Record<string, unknown>;
    const api = dialogStore as Record<string, unknown>;
    expect(state.wordEdit).toBeUndefined();
    expect(api.openWordEdit).toBeUndefined();
  });
});

describe("dialog-store: open(simple key)", () => {
  it("opens ocrConfig", () => {
    dialogStore.open("ocrConfig");
    expect(dialogStore.getState().ocrConfig.open).toBe(true);
  });

  it("opens export", () => {
    dialogStore.open("export");
    expect(dialogStore.getState().export.open).toBe(true);
  });

  it("opens hotkeyHelp", () => {
    dialogStore.open("hotkeyHelp");
    expect(dialogStore.getState().hotkeyHelp.open).toBe(true);
  });

  it("opening one dialog does not change others", () => {
    dialogStore.open("ocrConfig");
    const state = dialogStore.getState();
    expect(state.ocrConfig.open).toBe(true);
    expect(state.export.open).toBe(false);
    expect(state.hotkeyHelp.open).toBe(false);
  });
});

describe("dialog-store: close()", () => {
  it("closes a simple dialog", () => {
    dialogStore.open("ocrConfig");
    dialogStore.close("ocrConfig");
    expect(dialogStore.getState().ocrConfig.open).toBe(false);
  });

  it("closes confirm", () => {
    dialogStore.openConfirm({
      title: "Discard?",
      body: "Lose changes?",
      onConfirm: () => {},
    });
    dialogStore.close("confirm");
    expect(dialogStore.getState().confirm.open).toBe(false);
  });
});

describe("dialog-store: openConfirm", () => {
  it("opens with title/body/onConfirm captured", () => {
    const onConfirm = vi.fn();
    dialogStore.openConfirm({
      title: "Delete?",
      body: "This cannot be undone.",
      onConfirm,
    });
    const { confirm } = dialogStore.getState();
    expect(confirm.open).toBe(true);
    expect(confirm.title).toBe("Delete?");
    expect(confirm.body).toBe("This cannot be undone.");
    expect(confirm.onConfirm).toBe(onConfirm);
  });
});

describe("dialog-store: subscribe", () => {
  it("notifies listeners on state change", () => {
    const listener = vi.fn();
    const unsub = dialogStore.subscribe(listener);
    dialogStore.open("ocrConfig");
    expect(listener).toHaveBeenCalledTimes(1);
    dialogStore.close("ocrConfig");
    expect(listener).toHaveBeenCalledTimes(2);
    unsub();
    dialogStore.open("export");
    expect(listener).toHaveBeenCalledTimes(2); // no further calls after unsubscribe
  });

  it("each setState produces a new state reference (so React re-renders)", () => {
    const before = dialogStore.getState();
    dialogStore.open("ocrConfig");
    const after = dialogStore.getState();
    expect(after).not.toBe(before);
  });
});

describe("dialog-store: reset", () => {
  it("returns to initial state", () => {
    dialogStore.open("ocrConfig");
    dialogStore.reset();
    const state = dialogStore.getState();
    expect(state.ocrConfig.open).toBe(false);
    expect(state.confirm.open).toBe(false);
  });
});

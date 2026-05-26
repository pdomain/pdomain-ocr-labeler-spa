// useHotkey.test.tsx — unit tests for the useHotkey wrapper.
// Spec: docs/specs/2026-05-12-hotkeys-a11y-design.md
// Issue #235, #444
//
// Acceptance:
//   - useHotkey fires handler when key is pressed outside a form tag
//   - useHotkey does NOT fire inside form tags by default (enableOnFormTags: false)
//   - useHotkey does NOT fire page-scope hotkeys when a dialog is open (issue #444)
//   - useHotkey DOES fire when ignoreDialogGate: true, even with dialog open

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { useHotkey } from "./useHotkey";
import { dialogStore } from "../stores/dialog-store";

// Simple test component that calls useHotkey and renders a status
function HotkeyTestComponent({
  combo,
  handler,
  enableOnFormTags,
  ignoreDialogGate,
}: {
  combo: string;
  handler: () => void;
  enableOnFormTags?: boolean;
  ignoreDialogGate?: boolean;
}) {
  useHotkey(
    combo,
    handler,
    enableOnFormTags !== undefined || ignoreDialogGate !== undefined
      ? { enableOnFormTags, ignoreDialogGate }
      : undefined,
  );
  return <div data-testid="container">test</div>;
}

describe("useHotkey", () => {
  it("is importable and is a function", () => {
    expect(typeof useHotkey).toBe("function");
  });
});

describe("useHotkey hook", () => {
  it("renders without error", () => {
    const handler = vi.fn();
    render(<HotkeyTestComponent combo="a" handler={handler} />);
    expect(screen.getByTestId("container")).toBeInTheDocument();
  });

  it("accepts enableOnFormTags override", () => {
    const handler = vi.fn();
    // Should render without throwing
    render(<HotkeyTestComponent combo="b" handler={handler} enableOnFormTags={true} />);
    expect(screen.getByTestId("container")).toBeInTheDocument();
  });
});

describe("useHotkey dialog gate (issue #444)", () => {
  beforeEach(() => {
    dialogStore.reset();
  });

  afterEach(() => {
    dialogStore.reset();
  });

  it("fires page-scope hotkey when no dialog is open", () => {
    const handler = vi.fn();
    render(<HotkeyTestComponent combo="j" handler={handler} />);
    fireEvent.keyDown(document.body, { key: "j", code: "KeyJ" });
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("does NOT fire page-scope hotkey when a simple dialog is open (hotkeyHelp)", () => {
    const handler = vi.fn();
    render(<HotkeyTestComponent combo="j" handler={handler} />);
    dialogStore.open("hotkeyHelp");
    fireEvent.keyDown(document.body, { key: "j", code: "KeyJ" });
    expect(handler).not.toHaveBeenCalled();
  });

  it("does NOT fire page-scope hotkey when ocrConfig dialog is open", () => {
    const handler = vi.fn();
    render(<HotkeyTestComponent combo="s" handler={handler} />);
    dialogStore.open("ocrConfig");
    fireEvent.keyDown(document.body, { key: "s", code: "KeyS" });
    expect(handler).not.toHaveBeenCalled();
  });

  it("does NOT fire page-scope hotkey when wordEdit dialog is open", () => {
    const handler = vi.fn();
    render(<HotkeyTestComponent combo="v" handler={handler} />);
    dialogStore.openWordEdit({ lineIdx: 0, wordIdx: 0 });
    fireEvent.keyDown(document.body, { key: "v", code: "KeyV" });
    expect(handler).not.toHaveBeenCalled();
  });

  it("does NOT fire page-scope hotkey when confirm dialog is open", () => {
    const handler = vi.fn();
    render(<HotkeyTestComponent combo="d" handler={handler} />);
    dialogStore.openConfirm({ title: "Confirm", body: "Are you sure?", onConfirm: vi.fn() });
    fireEvent.keyDown(document.body, { key: "d", code: "KeyD" });
    expect(handler).not.toHaveBeenCalled();
  });

  it("fires again after dialog is closed", () => {
    const handler = vi.fn();
    render(<HotkeyTestComponent combo="k" handler={handler} />);
    dialogStore.open("export");
    fireEvent.keyDown(document.body, { key: "k", code: "KeyK" });
    expect(handler).not.toHaveBeenCalled();
    dialogStore.close("export");
    fireEvent.keyDown(document.body, { key: "k", code: "KeyK" });
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("fires dialog-scope hotkey even when dialog is open (ignoreDialogGate: true)", () => {
    const handler = vi.fn();
    render(<HotkeyTestComponent combo="arrowleft" handler={handler} ignoreDialogGate={true} />);
    dialogStore.openWordEdit({ lineIdx: 0, wordIdx: 0 });
    fireEvent.keyDown(document.body, { key: "ArrowLeft", code: "ArrowLeft" });
    expect(handler).toHaveBeenCalledTimes(1);
  });
});

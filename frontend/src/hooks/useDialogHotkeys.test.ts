// useDialogHotkeys.test.ts — tests for dialog-scope hotkeys (#237)
// Spec: docs/specs/2026-05-12-hotkeys-a11y-design.md §Word edit dialog
//
// Dialog hotkeys:
//   ArrowLeft/Right — prev/next word (NOT tested here — jsdom arrow-key issue, see E2E)
//   Shift+Enter     — apply + close
//   Esc             — close (discard)
//   R/Shift+R       — refine / expand+refine
//   Delete          — delete word (with confirm)
//   Shift+Arrow*    — nudge (4 directions: #212 will use accumulator)
//
// Note: ArrowLeft/Right combos rely on keyCode mapping in hotkeys-js which
// doesn't fire reliably via fireEvent.keyDown in jsdom. Covered by E2E (#242).
// Note: nudge accumulation (#212) registers Shift+Arrow variants.
// This hook covers the navigational/structural actions.

import { renderHook } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent } from "@testing-library/react";
import { useDialogHotkeys } from "./useDialogHotkeys";

describe("useDialogHotkeys", () => {
  const onPrevWord = vi.fn();
  const onNextWord = vi.fn();
  const onApplyClose = vi.fn();
  const onClose = vi.fn();
  const onRefine = vi.fn();
  const onExpandRefine = vi.fn();
  const onDelete = vi.fn();

  const callbacks = {
    onPrevWord,
    onNextWord,
    onApplyClose,
    onClose,
    onRefine,
    onExpandRefine,
    onDelete,
  };

  beforeEach(() => {
    [onPrevWord, onNextWord, onApplyClose, onClose, onRefine, onExpandRefine, onDelete].forEach(
      (fn) => fn.mockClear(),
    );
  });

  function renderHotkeys(enabled = true) {
    return renderHook(() => useDialogHotkeys({ enabled, ...callbacks }));
  }

  // ArrowLeft/Right not tested in jsdom — see note above about keyCode mapping.
  // Covered by E2E (#242).

  it("Shift+Enter calls onApplyClose", () => {
    renderHotkeys();
    fireEvent.keyDown(document, { key: "Enter", shiftKey: true });
    expect(onApplyClose).toHaveBeenCalledOnce();
  });

  it("Escape calls onClose", () => {
    renderHotkeys();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("R calls onRefine", () => {
    renderHotkeys();
    fireEvent.keyDown(document, { key: "r" });
    expect(onRefine).toHaveBeenCalledOnce();
  });

  it("Shift+R calls onExpandRefine", () => {
    renderHotkeys();
    fireEvent.keyDown(document, { key: "R", shiftKey: true });
    expect(onExpandRefine).toHaveBeenCalledOnce();
  });

  it("Delete calls onDelete", () => {
    renderHotkeys();
    fireEvent.keyDown(document, { key: "Delete" });
    expect(onDelete).toHaveBeenCalledOnce();
  });

  it("hotkeys do NOT fire when enabled=false", () => {
    renderHotkeys(false);
    fireEvent.keyDown(document, { key: "Enter", shiftKey: true });
    fireEvent.keyDown(document, { key: "r" });
    fireEvent.keyDown(document, { key: "Delete" });
    expect(onApplyClose).not.toHaveBeenCalled();
    expect(onRefine).not.toHaveBeenCalled();
    expect(onDelete).not.toHaveBeenCalled();
  });
});

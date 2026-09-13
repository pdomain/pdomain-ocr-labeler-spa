// useMatchesHotkeys.test.ts — tests for matches-scope hotkeys (#237)
// Spec: docs/specs/2026-05-12-hotkeys-a11y-design.md §Matches scope
//
// Acceptance:
//   - J/K navigate lines (onLineNav with delta)
//   - V/U call validate/unvalidate
//   - D calls delete with confirm
//   - R/Shift+R calls refine/expand+refine
//   - M calls merge; O/G call ocr-to-gt / gt-to-ocr
//   - Hotkeys disabled when enabled=false
//
// react-hotkeys-hook 5 matches against the physical `KeyboardEvent.code`
// (e.g. "KeyJ"), not `.key` — fireEvent.keyDown must set `code` explicitly,
// jsdom does not derive it from `key`.

import { renderHook } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent } from "@testing-library/react";
import { useMatchesHotkeys } from "./useMatchesHotkeys";

describe("useMatchesHotkeys", () => {
  const onLineNav = vi.fn();
  const onValidate = vi.fn();
  const onUnvalidate = vi.fn();
  const onDelete = vi.fn();
  const onRefine = vi.fn();
  const onExpandRefine = vi.fn();
  const onMerge = vi.fn();
  const onOcrToGt = vi.fn();
  const onGtToOcr = vi.fn();

  const defaultCallbacks = {
    onLineNav,
    onValidate,
    onUnvalidate,
    onDelete,
    onRefine,
    onExpandRefine,
    onMerge,
    onOcrToGt,
    onGtToOcr,
  };

  beforeEach(() => {
    [
      onLineNav,
      onValidate,
      onUnvalidate,
      onDelete,
      onRefine,
      onExpandRefine,
      onMerge,
      onOcrToGt,
      onGtToOcr,
    ].forEach((fn) => fn.mockClear());
  });

  function renderHotkeys(enabled = true) {
    return renderHook(() => useMatchesHotkeys({ enabled, ...defaultCallbacks }));
  }

  it("J calls onLineNav(+1) — next line", () => {
    renderHotkeys();
    fireEvent.keyDown(document, { key: "j", code: "KeyJ" });
    expect(onLineNav).toHaveBeenCalledWith(1);
  });

  it("K calls onLineNav(-1) — prev line", () => {
    renderHotkeys();
    fireEvent.keyDown(document, { key: "k", code: "KeyK" });
    expect(onLineNav).toHaveBeenCalledWith(-1);
  });

  it("V calls onValidate", () => {
    renderHotkeys();
    fireEvent.keyDown(document, { key: "v", code: "KeyV" });
    expect(onValidate).toHaveBeenCalledOnce();
  });

  it("U calls onUnvalidate", () => {
    renderHotkeys();
    fireEvent.keyDown(document, { key: "u", code: "KeyU" });
    expect(onUnvalidate).toHaveBeenCalledOnce();
  });

  it("D calls onDelete", () => {
    renderHotkeys();
    fireEvent.keyDown(document, { key: "d", code: "KeyD" });
    expect(onDelete).toHaveBeenCalledOnce();
  });

  it("R calls onRefine", () => {
    renderHotkeys();
    fireEvent.keyDown(document, { key: "r", code: "KeyR" });
    expect(onRefine).toHaveBeenCalledOnce();
  });

  it("Shift+R calls onExpandRefine", () => {
    renderHotkeys();
    fireEvent.keyDown(document, { key: "R", code: "KeyR", shiftKey: true });
    expect(onExpandRefine).toHaveBeenCalledOnce();
  });

  it("M calls onMerge", () => {
    renderHotkeys();
    fireEvent.keyDown(document, { key: "m", code: "KeyM" });
    expect(onMerge).toHaveBeenCalledOnce();
  });

  it("O calls onOcrToGt", () => {
    renderHotkeys();
    fireEvent.keyDown(document, { key: "o", code: "KeyO" });
    expect(onOcrToGt).toHaveBeenCalledOnce();
  });

  it("G calls onGtToOcr", () => {
    renderHotkeys();
    fireEvent.keyDown(document, { key: "g", code: "KeyG" });
    expect(onGtToOcr).toHaveBeenCalledOnce();
  });

  it("hotkeys do NOT fire when enabled=false", () => {
    renderHotkeys(false);
    fireEvent.keyDown(document, { key: "j", code: "KeyJ" });
    fireEvent.keyDown(document, { key: "v", code: "KeyV" });
    expect(onLineNav).not.toHaveBeenCalled();
    expect(onValidate).not.toHaveBeenCalled();
  });
});

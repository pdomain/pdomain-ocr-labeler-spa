// useViewportHotkeys.test.ts — tests for viewport-scope hotkeys (#237, #304)
// Spec: docs/specs/2026-05-12-hotkeys-a11y-design.md §Viewport scope,
//       specs/21-konva-renderer.md §10.
//
// Acceptance:
//   - Shift+P/L/W toggle paragraph/line/word layer
//   - Shift+1/2/3 set selection mode to paragraph/line/word (#304, spec §10)
//   - Shift+E toggles erase mode
//   - Shift+A toggles add-word mode
//   - Esc calls onCancelMode when viewport is active
//
// react-hotkeys-hook 5 matches against the physical `KeyboardEvent.code`
// (e.g. "KeyP"), not `.key` — fireEvent.keyDown must set `code` explicitly,
// jsdom does not derive it from `key`.

import { renderHook } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent } from "@testing-library/react";
import { useViewportHotkeys } from "./useViewportHotkeys";
import type { LayerVisibility } from "../stores/ui-prefs";

const defaultVisibility: LayerVisibility = {
  block: true,
  paragraph: true,
  line: true,
  word: true,
};

describe("useViewportHotkeys", () => {
  const onLayerToggle = vi.fn();
  const onEraseToggle = vi.fn();
  const onAddWordToggle = vi.fn();
  const onCancelMode = vi.fn();
  const onSelectionModeChange = vi.fn();

  beforeEach(() => {
    onLayerToggle.mockClear();
    onEraseToggle.mockClear();
    onAddWordToggle.mockClear();
    onCancelMode.mockClear();
    onSelectionModeChange.mockClear();
  });

  function renderHotkeys(enabled = true) {
    return renderHook(() =>
      useViewportHotkeys({
        enabled,
        layerVisibility: defaultVisibility,
        onLayerToggle,
        onEraseToggle,
        onAddWordToggle,
        onCancelMode,
        onSelectionModeChange,
      }),
    );
  }

  it("Shift+P calls onLayerToggle('paragraph')", () => {
    renderHotkeys();
    fireEvent.keyDown(document, { key: "P", code: "KeyP", shiftKey: true });
    expect(onLayerToggle).toHaveBeenCalledWith("paragraph");
  });

  it("Shift+L calls onLayerToggle('line')", () => {
    renderHotkeys();
    fireEvent.keyDown(document, { key: "L", code: "KeyL", shiftKey: true });
    expect(onLayerToggle).toHaveBeenCalledWith("line");
  });

  it("Shift+W calls onLayerToggle('word')", () => {
    renderHotkeys();
    fireEvent.keyDown(document, { key: "W", code: "KeyW", shiftKey: true });
    expect(onLayerToggle).toHaveBeenCalledWith("word");
  });

  it("Shift+E calls onEraseToggle", () => {
    renderHotkeys();
    fireEvent.keyDown(document, { key: "E", code: "KeyE", shiftKey: true });
    expect(onEraseToggle).toHaveBeenCalledOnce();
  });

  it("Shift+A calls onAddWordToggle", () => {
    renderHotkeys();
    fireEvent.keyDown(document, { key: "A", code: "KeyA", shiftKey: true });
    expect(onAddWordToggle).toHaveBeenCalledOnce();
  });

  it("Escape calls onCancelMode", () => {
    renderHotkeys();
    fireEvent.keyDown(document, { key: "Escape", code: "Escape" });
    expect(onCancelMode).toHaveBeenCalledOnce();
  });

  it("Shift+1 calls onSelectionModeChange('paragraph') (spec §10, #304)", () => {
    renderHotkeys();
    fireEvent.keyDown(document, { key: "!", code: "Digit1", shiftKey: true });
    expect(onSelectionModeChange).toHaveBeenCalledWith("paragraph");
  });

  it("Shift+2 calls onSelectionModeChange('line') (spec §10, #304)", () => {
    renderHotkeys();
    fireEvent.keyDown(document, { key: "@", code: "Digit2", shiftKey: true });
    expect(onSelectionModeChange).toHaveBeenCalledWith("line");
  });

  it("Shift+3 calls onSelectionModeChange('word') (spec §10, #304)", () => {
    renderHotkeys();
    fireEvent.keyDown(document, { key: "#", code: "Digit3", shiftKey: true });
    expect(onSelectionModeChange).toHaveBeenCalledWith("word");
  });

  it("hotkeys do NOT fire when enabled=false", () => {
    renderHotkeys(false);
    fireEvent.keyDown(document, { key: "P", shiftKey: true });
    fireEvent.keyDown(document, { key: "E", shiftKey: true });
    fireEvent.keyDown(document, { key: "!", code: "Digit1", shiftKey: true });
    expect(onLayerToggle).not.toHaveBeenCalled();
    expect(onEraseToggle).not.toHaveBeenCalled();
    expect(onSelectionModeChange).not.toHaveBeenCalled();
  });
});

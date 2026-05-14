// useViewportHotkeys.test.ts — tests for viewport-scope hotkeys (#237)
// Spec: docs/specs/2026-05-12-hotkeys-a11y-design.md §Viewport scope
//
// Acceptance:
//   - Shift+P/L/W toggle paragraph/line/word layer
//   - Shift+E toggles erase mode
//   - Shift+A toggles add-word mode
//   - Esc calls onCancelMode when viewport is active

import { renderHook } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent } from "@testing-library/react";
import { useViewportHotkeys } from "./useViewportHotkeys";
import type { LayerVisibility } from "../components/ImageTabsHeader";

const defaultVisibility: LayerVisibility = {
  paragraph: true,
  line: true,
  word: true,
};

describe("useViewportHotkeys", () => {
  const onLayerToggle = vi.fn();
  const onEraseToggle = vi.fn();
  const onAddWordToggle = vi.fn();
  const onCancelMode = vi.fn();

  beforeEach(() => {
    onLayerToggle.mockClear();
    onEraseToggle.mockClear();
    onAddWordToggle.mockClear();
    onCancelMode.mockClear();
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
      }),
    );
  }

  it("Shift+P calls onLayerToggle('paragraph')", () => {
    renderHotkeys();
    fireEvent.keyDown(document, { key: "P", shiftKey: true });
    expect(onLayerToggle).toHaveBeenCalledWith("paragraph");
  });

  it("Shift+L calls onLayerToggle('line')", () => {
    renderHotkeys();
    fireEvent.keyDown(document, { key: "L", shiftKey: true });
    expect(onLayerToggle).toHaveBeenCalledWith("line");
  });

  it("Shift+W calls onLayerToggle('word')", () => {
    renderHotkeys();
    fireEvent.keyDown(document, { key: "W", shiftKey: true });
    expect(onLayerToggle).toHaveBeenCalledWith("word");
  });

  it("Shift+E calls onEraseToggle", () => {
    renderHotkeys();
    fireEvent.keyDown(document, { key: "E", shiftKey: true });
    expect(onEraseToggle).toHaveBeenCalledOnce();
  });

  it("Shift+A calls onAddWordToggle", () => {
    renderHotkeys();
    fireEvent.keyDown(document, { key: "A", shiftKey: true });
    expect(onAddWordToggle).toHaveBeenCalledOnce();
  });

  it("Escape calls onCancelMode", () => {
    renderHotkeys();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onCancelMode).toHaveBeenCalledOnce();
  });

  it("hotkeys do NOT fire when enabled=false", () => {
    renderHotkeys(false);
    fireEvent.keyDown(document, { key: "P", shiftKey: true });
    fireEvent.keyDown(document, { key: "E", shiftKey: true });
    expect(onLayerToggle).not.toHaveBeenCalled();
    expect(onEraseToggle).not.toHaveBeenCalled();
  });
});

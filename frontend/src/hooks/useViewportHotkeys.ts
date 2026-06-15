// useViewportHotkeys.ts — viewport-scope hotkeys (#237, #304)
// Spec: docs/specs/2026-05-12-hotkeys-a11y-design.md §Viewport scope,
//       specs/21-konva-renderer.md §10.
//
// Viewport hotkeys:
//   Shift+P/L/W  — toggle paragraph/line/word layer visibility
//   Shift+1/2/3  — selection mode paragraph/line/word (#304, spec §10)
//   Shift+E      — toggle erase mode
//   Shift+A      — toggle add-word mode
//   Esc          — cancel current mode (reset to select)
//
// These fire at document scope. The viewport mounts a focusable wrapper
// (PageImageCanvas, #304) so users get a visible focus ring; the hook
// itself still listens globally via react-hotkeys-hook.

import { useHotkey } from "./useHotkey";
import type { LayerVisibility, SelectionMode } from "../stores/ui-prefs";

interface UseViewportHotkeysOptions {
  /** Disable all viewport hotkeys (e.g. when a modal is open). */
  enabled?: boolean;
  layerVisibility: LayerVisibility;
  onLayerToggle: (layer: keyof LayerVisibility) => void;
  onEraseToggle: () => void;
  onAddWordToggle: () => void;
  onCancelMode: () => void;
  /**
   * Set the selection mode (paragraph/line/word).
   * Bound to Shift+1/2/3 per spec 21 §10 (#304).
   */
  onSelectionModeChange: (mode: SelectionMode) => void;
}

/**
 * Register viewport-scope hotkeys.
 *
 * Call this hook inside the component that owns layer-visibility state
 * (PageImageCanvas, or any parent that wraps the viewport).
 */
export function useViewportHotkeys({
  enabled = true,
  onLayerToggle,
  onEraseToggle,
  onAddWordToggle,
  onCancelMode,
  onSelectionModeChange,
}: UseViewportHotkeysOptions): void {
  useHotkey(
    "shift+p",
    () => {
      onLayerToggle("paragraph");
    },
    { enabled },
  );
  useHotkey(
    "shift+l",
    () => {
      onLayerToggle("line");
    },
    { enabled },
  );
  useHotkey(
    "shift+w",
    () => {
      onLayerToggle("word");
    },
    { enabled },
  );
  useHotkey(
    "shift+e",
    () => {
      onEraseToggle();
    },
    { enabled },
  );
  useHotkey(
    "shift+a",
    () => {
      onAddWordToggle();
    },
    { enabled },
  );
  useHotkey(
    "escape",
    () => {
      onCancelMode();
    },
    { enabled },
  );
  // Spec 21 §10 — Shift+1/2/3 select-mode bindings (#304).
  useHotkey(
    "shift+1",
    () => {
      onSelectionModeChange("paragraph");
    },
    { enabled },
  );
  useHotkey(
    "shift+2",
    () => {
      onSelectionModeChange("line");
    },
    { enabled },
  );
  useHotkey(
    "shift+3",
    () => {
      onSelectionModeChange("word");
    },
    { enabled },
  );
}

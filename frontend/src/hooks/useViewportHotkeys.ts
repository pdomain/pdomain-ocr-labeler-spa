// useViewportHotkeys.ts — viewport-scope hotkeys (#237)
// Spec: docs/specs/2026-05-12-hotkeys-a11y-design.md §Viewport scope
//
// Viewport hotkeys:
//   Shift+P/L/W  — toggle paragraph/line/word layer visibility
//   Shift+E      — toggle erase mode
//   Shift+A      — toggle add-word mode
//   Esc          — cancel current mode (reset to select)
//
// These fire at document scope (not limited to viewport focus) for now;
// M4 Konva integration will scope to the canvas element.

import { useHotkey } from "./useHotkey";
import type { LayerVisibility } from "../components/ImageTabsHeader";

interface UseViewportHotkeysOptions {
  /** Disable all viewport hotkeys (e.g. when a modal is open). */
  enabled?: boolean;
  layerVisibility: LayerVisibility;
  onLayerToggle: (layer: keyof LayerVisibility) => void;
  onEraseToggle: () => void;
  onAddWordToggle: () => void;
  onCancelMode: () => void;
}

/**
 * Register viewport-scope hotkeys.
 *
 * Call this hook inside the component that owns layer-visibility state
 * (the image-tabs pane, or the parent ProjectPage).
 */
export function useViewportHotkeys({
  enabled = true,
  onLayerToggle,
  onEraseToggle,
  onAddWordToggle,
  onCancelMode,
}: UseViewportHotkeysOptions): void {
  useHotkey("shift+p", () => onLayerToggle("paragraph"), { enabled });
  useHotkey("shift+l", () => onLayerToggle("line"), { enabled });
  useHotkey("shift+w", () => onLayerToggle("word"), { enabled });
  useHotkey("shift+e", () => onEraseToggle(), { enabled });
  useHotkey("shift+a", () => onAddWordToggle(), { enabled });
  useHotkey("escape", () => onCancelMode(), { enabled });
}

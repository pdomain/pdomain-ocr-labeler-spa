// useGlobalHotkeys.ts — global-scope hotkeys wired to page/project actions.
// Spec: docs/specs/2026-05-12-hotkeys-a11y-design.md §Global
// Issue #236
//
// Wires:
//   Mod+S         → onSavePage (non-destructive)
//   Mod+Shift+S   → onSaveProject (non-destructive)
//   Mod+L         → onLoadPage (destructive — confirm required by caller)
//   Mod+G         → onRematchGt (destructive — confirm required by caller)
//   Mod+E         → onExport
//   Mod+ArrowLeft → onPrevPage
//   Mod+ArrowRight → onNextPage
//   Mod+Home      → onFirstPage
//   Mod+End       → onLastPage
//
// The hook itself does NOT show the confirm dialog — callers should wrap
// onLoadPage / onRematchGt with a confirm-dialog state setter so the UX
// reads: hotkey fires → dialog opens → user confirms → mutation fires.

import { useHotkey } from "./useHotkey";

export interface GlobalHotkeyHandlers {
  /** Fired by Mod+S (Save Page). Non-destructive; no confirm needed. */
  onSavePage?: () => void;
  /** Fired by Mod+Shift+S (Save Project). Non-destructive. */
  onSaveProject?: () => void;
  /** Fired by Mod+L (Load Page). Destructive — caller should show confirm first. */
  onLoadPage?: () => void;
  /** Fired by Mod+G (Rematch GT). Destructive — caller should show confirm first. */
  onRematchGt?: () => void;
  /** Fired by Mod+E (Export dialog). */
  onExport?: () => void;
  /** Fired by Mod+ArrowLeft (Previous page). */
  onPrevPage?: () => void;
  /** Fired by Mod+ArrowRight (Next page). */
  onNextPage?: () => void;
  /** Fired by Mod+Home (First page). */
  onFirstPage?: () => void;
  /** Fired by Mod+End (Last page). */
  onLastPage?: () => void;
  /** When true, all hotkeys are suppressed (e.g., during a busy/loading state). */
  disabled?: boolean;
}

/**
 * Register global-scope keyboard shortcuts.
 *
 * Call this once at the top of the component tree (e.g., in ProjectPage or
 * AppShell). All handlers are optional; missing handlers are silently skipped.
 */
export function useGlobalHotkeys({
  onSavePage,
  onSaveProject,
  onLoadPage,
  onRematchGt,
  onExport,
  onPrevPage,
  onNextPage,
  onFirstPage,
  onLastPage,
  disabled = false,
}: GlobalHotkeyHandlers): void {
  const enabled = !disabled;

  useHotkey("mod+s", () => onSavePage?.(), { enabled });
  useHotkey("mod+shift+s", () => onSaveProject?.(), { enabled });
  useHotkey("mod+l", () => onLoadPage?.(), { enabled });
  useHotkey("mod+g", () => onRematchGt?.(), { enabled });
  useHotkey("mod+e", () => onExport?.(), { enabled });
  useHotkey("mod+arrowleft", () => onPrevPage?.(), { enabled });
  useHotkey("mod+arrowright", () => onNextPage?.(), { enabled });
  useHotkey("mod+home", () => onFirstPage?.(), { enabled });
  useHotkey("mod+end", () => onLastPage?.(), { enabled });
}

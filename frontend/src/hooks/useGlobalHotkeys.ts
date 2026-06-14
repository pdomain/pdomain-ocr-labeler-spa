// useGlobalHotkeys.ts — global-scope hotkeys wired to page/project actions.
// Spec: docs/specs/2026-05-12-hotkeys-a11y-design.md §Global
// Issue #236
//
// Wires:
//   Mod+S         → onSavePage (non-destructive)
//   Mod+Shift+S   → onSaveProject (non-destructive)
//   Mod+R         → onReloadOcr (destructive — confirm required by caller)
//   Mod+L         → onLoadPage ("Reload" — confirm required by caller)
//   Mod+G         → onRematchGt (destructive — confirm required by caller)
//   Mod+E         → onExport
//   Mod+ArrowLeft → onPrevPage
//   Mod+ArrowRight → onNextPage
//   Mod+Home      → onFirstPage
//   Mod+End       → onLastPage
//
// The hook itself does NOT show the confirm dialog — callers should wrap
// onReloadOcr / onLoadPage / onRematchGt with a confirm-dialog state setter
// so the UX reads: hotkey fires → dialog opens → user confirms → mutation fires.

import { useHotkey } from "./useHotkey";

export interface GlobalHotkeyHandlers {
  /** Fired by Mod+S (Save Page). Non-destructive; no confirm needed. */
  onSavePage?: () => void;
  /** Fired by Mod+Shift+S (Save Project). Non-destructive. */
  onSaveProject?: () => void;
  /** Fired by Mod+R (Reload OCR). Destructive — caller must show confirm first.
   *  U-6: re-OCR resets the page's undo history. */
  onReloadOcr?: () => void;
  /** Fired by Mod+L (Reload page). Caller shows the confirm first (U-7 copy). */
  onLoadPage?: () => void;
  /** Fired by Mod+G (Rematch GT). Destructive — caller should show confirm first. */
  onRematchGt?: () => void;
  /** Fired by Mod+E (Export dialog). */
  onExport?: () => void;
  /** Fired by Mod+Z (page undo — event-store undo spec U-1). Suppressed
   *  inside form fields by the useHotkey default (enableOnFormTags: false)
   *  so native text-field undo wins (U-10). */
  onUndo?: () => void;
  /** Fired by Mod+Shift+Z (page redo — spec U-2). Same form-field guard. */
  onRedo?: () => void;
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
  onReloadOcr,
  onLoadPage,
  onRematchGt,
  onExport,
  onUndo,
  onRedo,
  onPrevPage,
  onNextPage,
  onFirstPage,
  onLastPage,
  disabled = false,
}: GlobalHotkeyHandlers): void {
  const enabled = !disabled;

  useHotkey("mod+s", () => onSavePage?.(), { enabled });
  useHotkey("mod+shift+s", () => onSaveProject?.(), { enabled });
  useHotkey("mod+r", () => onReloadOcr?.(), { enabled });
  useHotkey("mod+l", () => onLoadPage?.(), { enabled });
  useHotkey("mod+g", () => onRematchGt?.(), { enabled });
  useHotkey("mod+e", () => onExport?.(), { enabled });
  // U-10: enableOnFormTags stays false (useHotkey default) so Mod+Z inside a
  // text input/textarea performs the NATIVE text undo, never the page undo.
  // mod+shift+z is registered first so the plain mod+z handler can't shadow it.
  useHotkey("mod+shift+z", () => onRedo?.(), { enabled });
  useHotkey(
    "mod+z",
    (e) => {
      if (e.shiftKey) return; // belt-and-braces: leave Mod+Shift+Z to redo
      onUndo?.();
    },
    { enabled },
  );
  useHotkey("mod+arrowleft", () => onPrevPage?.(), { enabled });
  useHotkey("mod+arrowright", () => onNextPage?.(), { enabled });
  useHotkey("mod+home", () => onFirstPage?.(), { enabled });
  useHotkey("mod+end", () => onLastPage?.(), { enabled });
}

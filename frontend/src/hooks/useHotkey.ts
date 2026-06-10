// useHotkey.ts — thin wrapper around react-hotkeys-hook.
// Spec: docs/specs/2026-05-12-hotkeys-a11y-design.md §Keymap structure
// Issue #235, #444
//
// Defaults:
//   - preventDefault: true (preempts browser defaults like Ctrl+S → Save As)
//   - enableOnFormTags: false (hotkeys must not fire while typing in inputs)
//   - dialog gate: page-scope hotkeys are suppressed when any dialog is open
//
// Per-call overrides are accepted via the options param.
// Dialog-scope hotkeys pass ignoreDialogGate: true to opt out of the gate.

import { useHotkeys, type Options } from "react-hotkeys-hook";
import { dialogStore } from "../stores/dialog-store";

export type HotkeyOptions = Pick<Options, "enableOnFormTags" | "enabled" | "scopes"> & {
  /**
   * When true, the dialog gate is bypassed and the handler fires even when
   * a dialog is open. Use for hotkeys that are intentionally active inside
   * a dialog.
   *
   * Default: false (hotkey is suppressed whenever any dialog is open).
   */
  ignoreDialogGate?: boolean;
};

/** Return true if any dialog in the dialog store is currently open. */
function isAnyDialogOpen(): boolean {
  const s = dialogStore.getState();
  return (
    s.ocrConfig.open || s.export.open || s.hotkeyHelp.open || s.sourceFolder.open || s.confirm.open
  );
}

/**
 * Register a hotkey with sensible SPA defaults.
 *
 * By default the handler is **suppressed** while any dialog is open (issue
 * #444). Dialog-internal hotkeys pass `ignoreDialogGate: true` to opt out of
 * this gate.
 *
 * @param combo   Key combo string (e.g. "mod+s", "ctrl+shift+r", "?")
 * @param handler Callback to invoke when the combo fires
 * @param options Optional overrides for react-hotkeys-hook Options
 */
export function useHotkey(
  combo: string,
  handler: (event: KeyboardEvent) => void,
  options?: HotkeyOptions,
): void {
  const { ignoreDialogGate = false, ...restOptions } = options ?? {};

  // Wrap handler with the dialog gate. react-hotkeys-hook internally stores
  // the callback in a ref so handler identity changes don't cause re-registrations;
  // this inline wrapper is re-created each render but that is fine.
  const gatedHandler = (event: KeyboardEvent) => {
    if (!ignoreDialogGate && isAnyDialogOpen()) return;
    handler(event);
  };

  useHotkeys(combo, gatedHandler, {
    preventDefault: true,
    enableOnFormTags: false,
    ...restOptions,
  });
}

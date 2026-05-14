// useDialogHotkeys.ts — word-edit dialog scope hotkeys (#237)
// Spec: docs/specs/2026-05-12-hotkeys-a11y-design.md §Word edit dialog
//
// Dialog hotkeys:
//   ArrowLeft/Right   — prev/next word (navigation without closing)
//   Shift+Enter       — apply + close (commit pending changes)
//   Esc               — close (discard)
//   R / Shift+R       — refine / expand+refine
//   Delete            — delete word (with confirm; caller owns the confirm dialog)
//
// Nudge (Shift+Arrow*) is registered here as stubs; the nudge accumulator
// will be wired in #212 and can override these handlers then.

import { useHotkey } from "./useHotkey";

interface UseDialogHotkeysOptions {
  /** False when the dialog is closed; suppresses all bindings. */
  enabled?: boolean;
  onPrevWord: () => void;
  onNextWord: () => void;
  /** Fire apply-and-close (Shift+Enter). */
  onApplyClose: () => void;
  /** Fire close/discard (Esc). */
  onClose: () => void;
  onRefine: () => void;
  onExpandRefine: () => void;
  /** Delete word; caller is responsible for showing confirm dialog. */
  onDelete: () => void;
}

/**
 * Register word-edit dialog scope hotkeys.
 *
 * Call this hook inside the `WordEditDialog` component, gated by `open`.
 *
 * #212 will extend this by adding Shift+Arrow nudge accumulator hooks.
 */
export function useDialogHotkeys({
  enabled = true,
  onPrevWord,
  onNextWord,
  onApplyClose,
  onClose,
  onRefine,
  onExpandRefine,
  onDelete,
}: UseDialogHotkeysOptions): void {
  useHotkey("arrowleft", () => onPrevWord(), { enabled });
  useHotkey("arrowright", () => onNextWord(), { enabled });
  useHotkey("shift+enter", () => onApplyClose(), { enabled });
  useHotkey("escape", () => onClose(), { enabled });
  useHotkey("r", () => onRefine(), { enabled });
  useHotkey("shift+r", () => onExpandRefine(), { enabled });
  useHotkey("delete", () => onDelete(), { enabled });
}

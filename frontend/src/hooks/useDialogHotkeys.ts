// useDialogHotkeys.ts — word-edit dialog scope hotkeys (#237, #212)
// Spec: docs/specs/2026-05-12-hotkeys-a11y-design.md §Word edit dialog
//      docs/architecture/07-word-edit-dialog.md §4.6
//
// Dialog hotkeys:
//   ArrowLeft/Right        — prev/next word (navigation without closing)
//   Shift+Enter            — apply + close (commit pending changes)
//   Esc                    — close (discard)
//   R / Shift+R            — refine / expand+refine
//   Delete                 — delete word (with confirm; caller owns the confirm dialog)
//   Shift+ArrowLeft/Right  — nudge left edge (shrink / expand)
//   Shift+ArrowUp/Down     — nudge top edge (expand / shrink)
//   Ctrl+ArrowLeft/Right   — nudge right edge (shrink / expand)
//   Ctrl+ArrowUp/Down      — nudge bottom edge (shrink / expand)

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
  /**
   * Nudge a bbox edge by one step. Wired to the nudge accumulator (#212).
   * edge: which bbox edge; delta: +1 (expand) or -1 (shrink).
   */
  onNudge?: (edge: "left" | "right" | "top" | "bottom", delta: 1 | -1) => void;
}

/**
 * Register word-edit dialog scope hotkeys.
 *
 * Call this hook inside the `WordEditDialog` component, gated by `open`.
 *
 * Shift+Arrow: nudge left/top edges.
 * Ctrl+Arrow: nudge right/bottom edges.
 * These mirror the legacy keybindings from docs/architecture/07-word-edit-dialog.md §4.6.
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
  onNudge,
}: UseDialogHotkeysOptions): void {
  useHotkey("arrowleft", () => onPrevWord(), { enabled });
  useHotkey("arrowright", () => onNextWord(), { enabled });
  useHotkey("shift+enter", () => onApplyClose(), { enabled });
  useHotkey("escape", () => onClose(), { enabled });
  useHotkey("r", () => onRefine(), { enabled });
  useHotkey("shift+r", () => onExpandRefine(), { enabled });
  useHotkey("delete", () => onDelete(), { enabled });

  // Nudge bindings — spec §4.6:
  //   Shift+← / Shift+→  — nudge left edge (shrink / expand)
  //   Shift+↑ / Shift+↓  — nudge top edge  (expand / shrink)
  //   Ctrl+← / Ctrl+→    — nudge right edge (shrink / expand)
  //   Ctrl+↑ / Ctrl+↓    — nudge bottom edge (shrink / expand)
  useHotkey("shift+arrowleft", () => onNudge?.("left", -1), { enabled });
  useHotkey("shift+arrowright", () => onNudge?.("left", 1), { enabled });
  useHotkey("shift+arrowup", () => onNudge?.("top", 1), { enabled });
  useHotkey("shift+arrowdown", () => onNudge?.("top", -1), { enabled });
  useHotkey("ctrl+arrowleft", () => onNudge?.("right", -1), { enabled });
  useHotkey("ctrl+arrowright", () => onNudge?.("right", 1), { enabled });
  useHotkey("ctrl+arrowup", () => onNudge?.("bottom", -1), { enabled });
  useHotkey("ctrl+arrowdown", () => onNudge?.("bottom", 1), { enabled });
}

// hotkeyMap.ts — static keymap for all hotkey scopes.
// Spec: docs/specs/2026-05-12-hotkeys-a11y-design.md §Keymap structure
// Issue #235
//
// Single source of truth for both registration (useHotkey) and the ? help modal.
// Scopes: global | viewport | matches | dialog | source-folder | gt-input
//
// Combo syntax: "mod+s", "mod+shift+r", "?" etc.
// "mod" maps to Ctrl on Windows/Linux and Cmd on Mac (react-hotkeys-hook convention).

export type Scope = "global" | "viewport" | "matches" | "dialog" | "source-folder" | "gt-input";

export interface HotkeyEntry {
  combo: string;
  scope: Scope;
  description: string;
}

export const HOTKEY_MAP: HotkeyEntry[] = [
  // ── Global ──────────────────────────────────────────────────────────────
  { combo: "mod+s", scope: "global", description: "Save Page" },
  { combo: "mod+shift+s", scope: "global", description: "Save Project" },
  { combo: "mod+r", scope: "global", description: "Reload OCR" },
  { combo: "mod+shift+r", scope: "global", description: "Reload OCR (Edited)" },
  { combo: "mod+l", scope: "global", description: "Load Page from disk" },
  { combo: "mod+g", scope: "global", description: "Rematch GT" },
  { combo: "mod+e", scope: "global", description: "Export…" },
  { combo: "mod+,", scope: "global", description: "OCR Config" },
  { combo: "mod+o", scope: "global", description: "Open Source Folder dialog" },
  { combo: "?", scope: "global", description: "Show hotkey help" },
  { combo: "escape", scope: "global", description: "Close modal / cancel" },
  // Navigation
  { combo: "mod+arrowleft", scope: "global", description: "Previous page" },
  { combo: "mod+arrowright", scope: "global", description: "Next page" },
  { combo: "mod+home", scope: "global", description: "First page" },
  { combo: "mod+end", scope: "global", description: "Last page" },
  { combo: "mod+j", scope: "global", description: "Jump to page…" },

  // ── Viewport ────────────────────────────────────────────────────────────
  { combo: "escape", scope: "viewport", description: "Cancel current mode" },
  { combo: "shift+p", scope: "viewport", description: "Toggle paragraphs layer" },
  { combo: "shift+l", scope: "viewport", description: "Toggle lines layer" },
  { combo: "shift+w", scope: "viewport", description: "Toggle words layer" },
  { combo: "shift+1", scope: "viewport", description: "Selection mode" },
  { combo: "shift+2", scope: "viewport", description: "Rebox mode" },
  { combo: "shift+3", scope: "viewport", description: "Erase mode" },
  { combo: "shift+e", scope: "viewport", description: "Erase mode (alternate)" },
  { combo: "shift+a", scope: "viewport", description: "Add Word mode" },

  // ── Matches ─────────────────────────────────────────────────────────────
  { combo: "j", scope: "matches", description: "Next line card" },
  { combo: "k", scope: "matches", description: "Previous line card" },
  { combo: "v", scope: "matches", description: "Validate line" },
  { combo: "u", scope: "matches", description: "Unvalidate line" },
  { combo: "d", scope: "matches", description: "Delete line (with confirm)" },
  { combo: "o", scope: "matches", description: "Copy OCR→GT for line" },
  { combo: "g", scope: "matches", description: "Copy GT→OCR for line" },
  { combo: "r", scope: "matches", description: "Refine" },
  { combo: "shift+r", scope: "matches", description: "Expand+Refine" },
  { combo: "m", scope: "matches", description: "Merge words" },

  // ── Word Edit Dialog ─────────────────────────────────────────────────────
  { combo: "enter", scope: "dialog", description: "Commit GT" },
  { combo: "escape", scope: "dialog", description: "Close dialog" },
  { combo: "shift+enter", scope: "dialog", description: "Apply and close" },
  { combo: "arrowleft", scope: "dialog", description: "Previous word" },
  { combo: "arrowright", scope: "dialog", description: "Next word" },
  { combo: "shift+arrowleft", scope: "dialog", description: "Nudge left edge" },
  { combo: "shift+arrowright", scope: "dialog", description: "Nudge right edge" },
  { combo: "shift+arrowup", scope: "dialog", description: "Nudge top edge (expand)" },
  { combo: "shift+arrowdown", scope: "dialog", description: "Nudge top edge (shrink)" },
  { combo: "ctrl+arrowleft", scope: "dialog", description: "Nudge right edge (shrink)" },
  { combo: "ctrl+arrowright", scope: "dialog", description: "Nudge right edge (expand)" },
  { combo: "ctrl+arrowup", scope: "dialog", description: "Nudge bottom edge (shrink)" },
  { combo: "ctrl+arrowdown", scope: "dialog", description: "Nudge bottom edge (expand)" },
  { combo: "r", scope: "dialog", description: "Refine" },
  { combo: "shift+r", scope: "dialog", description: "Expand+Refine" },
  { combo: "m", scope: "dialog", description: "Apply style" },
  { combo: "shift+m", scope: "dialog", description: "Apply component" },
  { combo: "delete", scope: "dialog", description: "Delete word (with confirm)" },

  // ── Source-folder dialog ─────────────────────────────────────────────────
  { combo: "enter", scope: "source-folder", description: "Open typed path" },
  { combo: "mod+enter", scope: "source-folder", description: "Apply source folder" },
  { combo: "escape", scope: "source-folder", description: "Cancel" },

  // ── GT Input ────────────────────────────────────────────────────────────
  { combo: "tab", scope: "gt-input", description: "Move to next GT input" },
  { combo: "shift+tab", scope: "gt-input", description: "Move to previous GT input" },
  { combo: "enter", scope: "gt-input", description: "Commit GT" },
  { combo: "escape", scope: "gt-input", description: "Revert GT" },
];

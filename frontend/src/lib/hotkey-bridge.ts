// hotkey-bridge.ts — bridge legacy hotkeyMap.ts entries into the hotkey registry.
// Issue #329 (FO-6).
//
// Converts HOTKEY_MAP combo strings to display-friendly keyCap arrays and maps
// Scope → HotkeyGroup. Called once at module load from hotkey-registry.ts so
// HotkeyHelpModal shows the complete set of registered hotkeys.
//
// Combo conversion: "mod+shift+s" → ["Ctrl","Shift","S"]
// Scope→Group:
//   global (page-nav combos)  → navigation
//   global (editor actions)   → editing
//   global (modal openers)    → view
//   viewport                  → selection
//   matches                   → editing
//   dialog                    → editing
//   source-folder             → other
//   gt-input                  → editing

import { HOTKEY_MAP, type Scope } from "./hotkeyMap";
import type { RegistryEntry, HotkeyGroup } from "./hotkey-registry";

// ─── Combo → keyCap conversion ────────────────────────────────────────────────

/** Token display map for special keys. */
const TOKEN_DISPLAY: Record<string, string> = {
  mod: "Ctrl",
  shift: "Shift",
  alt: "Alt",
  ctrl: "Ctrl",
  arrowleft: "←",
  arrowright: "→",
  arrowup: "↑",
  arrowdown: "↓",
  escape: "Esc",
  enter: "Enter",
  delete: "Del",
  backspace: "⌫",
  home: "Home",
  end: "End",
  tab: "Tab",
  space: "Space",
};

/**
 * Convert a react-hotkeys-hook combo string to an array of display tokens
 * suitable for a single KeyCap (i.e. one KeyCap component showing N pills).
 *
 * Examples:
 *   "mod+s"       → ["Ctrl", "S"]
 *   "shift+enter" → ["Shift", "Enter"]
 *   "?"           → ["?"]
 *   "j"           → ["J"]
 */
export function comboToKeyCap(combo: string): string[] {
  return combo.split("+").map((token) => {
    const lower = token.toLowerCase();
    if (TOKEN_DISPLAY[lower]) return TOKEN_DISPLAY[lower];
    // Single printable char → uppercase
    if (token.length === 1) return token.toUpperCase();
    // Unknown multi-char token → titlecase
    return token.charAt(0).toUpperCase() + token.slice(1);
  });
}

// ─── Scope → Group mapping ────────────────────────────────────────────────────

// Global combos that navigate pages map to "navigation" group.
const GLOBAL_NAV_COMBOS = new Set([
  "mod+arrowleft",
  "mod+arrowright",
  "mod+home",
  "mod+end",
  "mod+j",
]);

// Global combos that open modals/views map to "view" group.
const GLOBAL_VIEW_COMBOS = new Set(["?", "mod+,", "mod+o", "escape"]);

/**
 * Map a (scope, combo) pair to a HotkeyGroup.
 */
export function scopeToGroup(scope: Scope, combo: string): HotkeyGroup {
  switch (scope) {
    case "global":
      if (GLOBAL_NAV_COMBOS.has(combo)) return "navigation";
      if (GLOBAL_VIEW_COMBOS.has(combo)) return "view";
      return "editing";
    case "viewport":
      return "selection";
    case "matches":
      return "editing";
    case "dialog":
      return "editing";
    case "source-folder":
      return "other";
    case "gt-input":
      return "editing";
    default:
      return "other";
  }
}

// ─── Order hints ─────────────────────────────────────────────────────────────

// Base order for bridged entries (higher than static entries so they sort after).
const BRIDGE_ORDER_BASE = 100;

// ─── Bridge function ─────────────────────────────────────────────────────────

/**
 * Convert all HOTKEY_MAP entries into RegistryEntry objects.
 *
 * Used by hotkey-registry.ts to populate the registry at module load.
 * Callers that already have static entries should deduplicate by label
 * before adding (see hotkey-registry.ts).
 */
export function buildBridgedEntries(): RegistryEntry[] {
  return HOTKEY_MAP.map((entry, idx) => ({
    label: entry.description,
    keyCaps: [comboToKeyCap(entry.combo)],
    group: scopeToGroup(entry.scope, entry.combo),
    order: BRIDGE_ORDER_BASE + idx,
  }));
}

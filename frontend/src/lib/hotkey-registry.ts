// hotkey-registry.ts — runtime hotkey registry for the HotkeyHelpModal.
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 25.
// Issue #329 (FO-6): bridge legacy hotkeyMap.ts into registry for completeness.
//
// Purpose: each `useXHotkeys` hook registers its hotkeys here; the modal
// reads from the registry to build the grouped display with KeyCap components.
//
// Groups:
//   - Selection  (viewport mode keys, layer toggles)
//   - Navigation (←/→ pages, ⌥ arrows breadcrumb)
//   - Editing    (saves, reload, GT ops, word/line mutations, dialog hotkeys)
//   - View       (theme toggle, drawer collapse, hotkey help, OCR config)
//   - Other      (source-folder, gt-input helpers)
//
// Entries come from two sources:
//   1. `buildBridgedEntries()` — all HOTKEY_MAP entries, converted from combo
//      strings and scope-mapped to groups. Single source of truth for anything
//      in hotkeyMap.ts.
//   2. Static extras below — entries for hotkeys NOT in HOTKEY_MAP (breadcrumb
//      navigation, drawer toggle, theme cycle). These use human-friendly
//      display keyCaps that don't map 1:1 to a react-hotkeys-hook combo.

export type HotkeyGroup = "selection" | "navigation" | "editing" | "view" | "other";

export interface RegistryEntry {
  /** Display label (human-readable). */
  label: string;
  /**
   * Keys to render as KeyCap components.
   * Each element is one KeyCap; within a single KeyCap, use an array of
   * strings (rendered as pill+pill joined by "+").
   * Example: [["⌥", "→"]] → one KeyCap with two pills.
   *          ["?"] → one KeyCap with one pill.
   */
  keyCaps: (string | string[])[];
  group: HotkeyGroup;
  /** Optional sort weight within a group; lower = earlier. */
  order?: number;
}

export interface HotkeyGroupDef {
  id: HotkeyGroup;
  label: string;
  entries: RegistryEntry[];
}

import { buildBridgedEntries } from "./hotkey-bridge";

// ─── Static extras (entries NOT in HOTKEY_MAP) ────────────────────────────────
//
// These cover UI affordances that are registered via breadcrumb/Rail event
// handlers rather than useHotkey combos, so they don't appear in HOTKEY_MAP.

const STATIC_EXTRAS: RegistryEntry[] = [
  // Breadcrumb keyboard navigation (Alt+arrow, handled by BreadcrumbNav component)
  {
    group: "navigation",
    label: "Breadcrumb — up",
    keyCaps: [["⌥", "↑"]],
    order: 3,
  },
  {
    group: "navigation",
    label: "Breadcrumb — previous",
    keyCaps: [["⌥", "←"]],
    order: 4,
  },
  {
    group: "navigation",
    label: "Breadcrumb — next",
    keyCaps: [["⌥", "→"]],
    order: 5,
  },

  // Rail / drawer controls (handled by keyboard events on the Rail component)
  { group: "view", label: "Toggle drawer", keyCaps: [["["]], order: 1 },
  { group: "view", label: "Cycle theme", keyCaps: [["T"]], order: 3 },
];

// ─── Registry state ───────────────────────────────────────────────────────────
//
// Seeded with bridged HOTKEY_MAP entries + static extras (items not in the map).

const _entries: RegistryEntry[] = [...buildBridgedEntries(), ...STATIC_EXTRAS];

/** Group metadata (label + display order). */
export const HOTKEY_GROUP_DEFS: HotkeyGroupDef[] = [
  { id: "selection", label: "Selection", entries: [] },
  { id: "navigation", label: "Navigation", entries: [] },
  { id: "editing", label: "Editing", entries: [] },
  { id: "view", label: "View", entries: [] },
  { id: "other", label: "Other", entries: [] },
];

/** Listeners called when registry changes. */
type Listener = () => void;
const _listeners = new Set<Listener>();

/** Stable snapshot cache — invalidated on every notify(). */
let _snapshot: HotkeyGroupDef[] | null = null;

function notify() {
  _snapshot = null;
  _listeners.forEach((fn) => {
    fn();
  });
}

/**
 * Register additional hotkeys at runtime (e.g. from a hook on mount).
 * Returns a cleanup function that removes the entries.
 */
export function registerHotkeys(entries: RegistryEntry[]): () => void {
  _entries.push(...entries);
  notify();
  return () => {
    for (const entry of entries) {
      const idx = _entries.indexOf(entry);
      if (idx !== -1) _entries.splice(idx, 1);
    }
    notify();
  };
}

/**
 * Returns all registered entries for a given group, sorted by `order`.
 */
export function getGroupEntries(group: HotkeyGroup): RegistryEntry[] {
  return _entries
    .filter((e) => e.group === group)
    .sort((a, b) => (a.order ?? 99) - (b.order ?? 99));
}

/**
 * Returns all groups that have at least one entry, with entries populated.
 *
 * The result is cached and invalidated only when the registry changes.
 * This ensures `useSyncExternalStore` receives a stable reference across
 * renders when nothing has changed (required to avoid infinite loops).
 */
export function getPopulatedGroups(): HotkeyGroupDef[] {
  if (_snapshot !== null) return _snapshot;
  _snapshot = HOTKEY_GROUP_DEFS.map((g) => ({
    ...g,
    entries: getGroupEntries(g.id),
  })).filter((g) => g.entries.length > 0);
  return _snapshot;
}

/** Subscribe to registry changes. */
export function subscribeRegistry(listener: Listener): () => void {
  _listeners.add(listener);
  return () => _listeners.delete(listener);
}

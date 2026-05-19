// rail-store.ts — Rail target/mode selection store.
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 10.
//
// target: "block" | "line" | "word"
//   Governs canvas drag-select scope and right-panel context.
//   Persisted to localStorage under RAIL_TARGET_STORAGE_KEY.
//
// mode: "view" | "region" | "annotate" | "erase"
//   Selection interaction mode — not persisted (resets to "view" on reload).
//
// Phase 2.5 (cross-cut-design §7.5): migrated from hand-rolled reactive
// store to Zustand's vanilla `createStore`. External API preserved intact.
//
// GAP-4: Cannot use a pd-ui store factory for rail state.
//   No pd-ui factory covers the Rail tool-mode concept: labeler-specific
//   target (block/para/line/word) that persists to localStorage, and an
//   interaction mode (view/region/annotate/erase) that resets on reload.
//   This is labeler-domain UI state that pd-ui explicitly excludes per
//   §3 "What pd-ui does not include".

import { createStore } from "zustand/vanilla";

export type RailTarget = "block" | "para" | "line" | "word";
export type RailMode = "view" | "region" | "annotate" | "erase";

export const RAIL_TARGET_STORAGE_KEY = "pdl.rail.target";

const VALID_TARGETS = new Set<string>(["block", "para", "line", "word"]);
const VALID_MODES = new Set<string>(["view", "region", "annotate", "erase"]);

interface RailState {
  target: RailTarget;
  mode: RailMode;
  setTarget: (target: RailTarget) => void;
  setMode: (mode: RailMode) => void;
}

function readPersistedTarget(): RailTarget {
  try {
    const raw = localStorage.getItem(RAIL_TARGET_STORAGE_KEY);
    if (raw && VALID_TARGETS.has(raw)) return raw as RailTarget;
  } catch {
    // localStorage unavailable (SSR, private mode)
  }
  return "word";
}

const _store = createStore<RailState>((set) => ({
  target: readPersistedTarget(),
  mode: "view",
  setTarget(target: RailTarget) {
    if (!VALID_TARGETS.has(target)) return;
    try {
      localStorage.setItem(RAIL_TARGET_STORAGE_KEY, target);
    } catch {
      // ignore
    }
    set((s) => ({ ...s, target }));
  },
  setMode(mode: RailMode) {
    if (!VALID_MODES.has(mode)) return;
    set((s) => ({ ...s, mode }));
  },
}));

/**
 * Rail store — exposes Zustand's `getState`/`subscribe` for
 * `useSyncExternalStore` wiring, plus a `reset` helper for tests.
 */
export const railStore = {
  /** Current state snapshot. */
  getState: () => _store.getState(),
  /** Subscribe to changes (returns unsubscribe). */
  subscribe: (cb: () => void) => _store.subscribe(cb),
  /** Re-reads persisted state; used in tests to simulate a fresh page load. */
  reset() {
    _store.setState((s) => ({
      ...s,
      target: readPersistedTarget(),
      mode: "view",
    }));
  },
};

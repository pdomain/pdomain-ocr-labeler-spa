// worklist-store.ts — Worklist filter + bulk-selection state store.
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 11, Slice 23.
//
// activeFilter: the current MatchFilter for the worklist queue.
// selectedLineIndex: the currently-selected line index in the queue (null = none).
// selectedIds: set of line indices chosen for bulk actions (Slice 23).

import { type MatchFilter } from "./ui-prefs";

export type { MatchFilter };

/** Status values used in the Worklist chip row. */
export type WorklistStatus = "exact" | "fuzzy" | "mismatch" | "all";

export interface WorklistState {
  activeFilter: MatchFilter;
  selectedLineIndex: number | null;
  /** Bulk-selected line indices (Slice 23). */
  selectedIds: number[];
}

type Listener = () => void;

function createWorklistStore() {
  let state: WorklistState = {
    activeFilter: "unvalidated",
    selectedLineIndex: null,
    selectedIds: [],
  };
  const listeners = new Set<Listener>();

  function notify() {
    listeners.forEach((fn) => fn());
  }

  function setActiveFilter(filter: MatchFilter) {
    state = { ...state, activeFilter: filter };
    notify();
  }

  function setSelectedLineIndex(index: number | null) {
    state = { ...state, selectedLineIndex: index };
    notify();
  }

  function reset() {
    state = { activeFilter: "unvalidated", selectedLineIndex: null, selectedIds: [] };
    notify();
  }

  // ── Bulk selection helpers (Slice 23) ──────────────────────────────────

  /** Select all from the given list of line indices. */
  function selectAll(ids: number[]) {
    state = { ...state, selectedIds: [...ids] };
    notify();
  }

  /** Clear bulk selection. */
  function clearBulk() {
    state = { ...state, selectedIds: [] };
    notify();
  }

  /** Toggle a single line index in/out of bulk selection. */
  function toggle(id: number) {
    const has = state.selectedIds.includes(id);
    state = {
      ...state,
      selectedIds: has ? state.selectedIds.filter((x) => x !== id) : [...state.selectedIds, id],
    };
    notify();
  }

  return {
    getState: () => state,
    setActiveFilter,
    setSelectedLineIndex,
    reset,
    selectAll,
    clearBulk,
    toggle,
    subscribe: (cb: Listener) => {
      listeners.add(cb);
      return () => {
        listeners.delete(cb);
      };
    },
  };
}

export const worklistStore = createWorklistStore();

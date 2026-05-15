// worklist-store.ts — Worklist filter state store.
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 11.
//
// activeFilter: the current MatchFilter for the worklist queue.
// selectedLineIndex: the currently-selected line index in the queue (null = none).

import { type MatchFilter } from "./ui-prefs";

export type { MatchFilter };

/** Status values used in the Worklist chip row. */
export type WorklistStatus = "exact" | "fuzzy" | "mismatch" | "all";

export interface WorklistState {
  activeFilter: MatchFilter;
  selectedLineIndex: number | null;
}

type Listener = () => void;

function createWorklistStore() {
  let state: WorklistState = {
    activeFilter: "unvalidated",
    selectedLineIndex: null,
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
    state = { activeFilter: "unvalidated", selectedLineIndex: null };
    notify();
  }

  return {
    getState: () => state,
    setActiveFilter,
    setSelectedLineIndex,
    reset,
    subscribe: (cb: Listener) => {
      listeners.add(cb);
      return () => {
        listeners.delete(cb);
      };
    },
  };
}

export const worklistStore = createWorklistStore();

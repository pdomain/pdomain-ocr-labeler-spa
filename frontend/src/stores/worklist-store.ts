// worklist-store.ts — Worklist filter + bulk-selection state store.
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 11, Slice 23, P5.b.
//
// activeFilter: the current MatchFilter for the worklist queue.
// sort: current sort order for the queue (P5.b).
// selectedLineIndex: the currently-selected line index in the queue (null = none).
// selectedIds: set of line indices chosen for bulk actions (Slice 23).
//
// Phase 2.5 (cross-cut-design §7.5): migrated from hand-rolled reactive
// store to Zustand's vanilla `createStore`. External API preserved intact
// so all call sites compile unchanged.
//
// GAP-3: Cannot use pd-ui's `createWorklistStore()` factory.
//   pd-ui offers: `activeIndex: number|null, filter: string, setActiveIndex,
//   setFilter, clearFilter`.
//   This store needs: labeler-specific MatchFilter enum (unvalidated/
//   mismatched/all), WorklistSort (index/confidence/status), selectedIds for
//   bulk operations (Slice 23), and searchQuery for text filtering. The pd-ui
//   factory covers a generic "which item is active" pattern that does not
//   accommodate the labeler's domain-specific filter cycle or bulk-selection
//   semantics.

import { createStore } from "zustand/vanilla";
import { type MatchFilter } from "./ui-prefs";

export type { MatchFilter };

/** Sort order for the worklist queue (P5.b). */
export type WorklistSort = "index" | "confidence" | "status";

interface WorklistState {
  activeFilter: MatchFilter;
  /** Sort order for the worklist queue (P5.b). Default: "index". */
  sort: WorklistSort;
  selectedLineIndex: number | null;
  /** Bulk-selected line indices (Slice 23). */
  selectedIds: number[];
  /** Text filter applied to OCR/GT line text in the worklist. Empty string = no filter. */
  searchQuery: string;
}

const INITIAL_STATE: WorklistState = {
  activeFilter: "unvalidated",
  sort: "index",
  selectedLineIndex: null,
  selectedIds: [],
  searchQuery: "",
};

const _store = createStore<WorklistState>(() => ({ ...INITIAL_STATE }));

/**
 * Worklist store — exposes Zustand's `getState`/`subscribe` for
 * `useSyncExternalStore` wiring, plus imperative action methods used
 * from non-React contexts (hotkey handlers, mutations).
 */
export const worklistStore = {
  /** Current state snapshot — stable reference until next setState. */
  getState: () => _store.getState(),
  /** Subscribe to changes (returns unsubscribe). */
  subscribe: (cb: () => void) => _store.subscribe(cb),

  setActiveFilter(filter: MatchFilter) {
    _store.setState({ activeFilter: filter });
  },

  setSort(sort: WorklistSort) {
    _store.setState({ sort });
  },

  setSelectedLineIndex(index: number | null) {
    _store.setState({ selectedLineIndex: index });
  },

  setSearchQuery(query: string) {
    _store.setState({ searchQuery: query });
  },

  reset() {
    _store.setState({ ...INITIAL_STATE });
  },

  // ── Bulk selection helpers (Slice 23) ──────────────────────────────────

  /** Select all from the given list of line indices. */
  selectAll(ids: number[]) {
    _store.setState({ selectedIds: [...ids] });
  },

  /** Clear bulk selection. */
  clearBulk() {
    _store.setState({ selectedIds: [] });
  },

  /** Toggle a single line index in/out of bulk selection. */
  toggle(id: number) {
    const { selectedIds } = _store.getState();
    const has = selectedIds.includes(id);
    _store.setState({
      selectedIds: has ? selectedIds.filter((x) => x !== id) : [...selectedIds, id],
    });
  },
};

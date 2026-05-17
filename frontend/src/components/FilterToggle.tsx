// FilterToggle.tsx — three-state cycling toggle for the word-match filter.
//
// Spec: specs/22-page-surface-wireup.md §8 (FilterToggle).
// P5.i (Gap 52): use design token classes (accent, bg-bg-raised, etc.) instead
// of generic gray/gray-50 utilities so the toggle respects dark/light theme.
//
// Cycles through unvalidated → mismatched → all → unvalidated. State lives
// in `useUiPrefs.matchFilter` (spec calls this `usePrefsStore.matchFilter`;
// the store is named `useUiPrefs` in this repo).
//
// Driver-contract: `data-testid="match-filter-toggle"` is new (legacy
// NiceGUI used a `ui.toggle` widget without a stable testid).
//
// Issue #312 (spec-22-B3).

import { useSyncExternalStore } from "react";
import { useUiPrefs, type MatchFilter } from "../stores/ui-prefs";

const LABELS: Record<MatchFilter, string> = {
  unvalidated: "Unvalidated Lines",
  mismatched: "Mismatched Lines",
  all: "All Lines",
};

// ---------------------------------------------------------------------------
// Hand-rolled subscriber bridge — mirrors the Splitter pattern. The
// `useUiPrefs` store has no native `subscribe()` because it predates
// reactive consumers; we wire `useSyncExternalStore` on top of a Set
// so React 19 concurrent rendering stays consistent.
// ---------------------------------------------------------------------------

const subscribers = new Set<() => void>();
function notifySubscribers() {
  subscribers.forEach((fn) => {
    fn();
  });
}
function subscribe(cb: () => void): () => void {
  subscribers.add(cb);
  return () => {
    subscribers.delete(cb);
  };
}

function getMatchFilter(): MatchFilter {
  return useUiPrefs.getState().matchFilter;
}

function cycleMatchFilter() {
  useUiPrefs.cycleMatchFilter();
  notifySubscribers();
}

export function FilterToggle() {
  const filter = useSyncExternalStore(subscribe, getMatchFilter, getMatchFilter);

  return (
    <button
      type="button"
      data-testid="match-filter-toggle"
      data-filter={filter}
      onClick={cycleMatchFilter}
      aria-label={`Filter: ${LABELS[filter]} (click to cycle)`}
      className="text-xs px-2 py-1 border border-border-2 rounded bg-bg-raised text-ink-2 hover:bg-bg-raised/80 hover:text-ink-1 transition-colors"
    >
      {LABELS[filter]}
    </button>
  );
}

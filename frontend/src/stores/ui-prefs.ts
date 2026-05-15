// ui-prefs.ts — UI preferences store (line filter, layer visibility,
// splitter ratio, selection mode, match filter).
//
// Spec: specs/22-page-surface-wireup.md §8 (FilterToggle), §9 (Splitter),
// D-021 (UI prefs).
// `splitterRatio` is the canonical field name (matches spec 22). The
// legacy alias `splitterPosition` was renamed; no production callers
// exist yet — only the store + this test relied on the old name.

export interface LayerVisibility {
  paragraph: boolean;
  line: boolean;
  word: boolean;
}

/**
 * Match-filter mode for the word-match list — spec 22 §8.
 *
 * Mirrors legacy `pd-ocr-labeler` filter values
 * (`word_match_renderer.py:_filter_lines_for_display`):
 *   - "unvalidated" → only lines where `!is_fully_validated`
 *   - "mismatched" → only lines containing any non-exact word match
 *   - "all"        → no filtering
 */
export type MatchFilter = "unvalidated" | "mismatched" | "all";

/** Spec 22 §8 cycle order: unvalidated → mismatched → all → unvalidated. */
export const MATCH_FILTER_CYCLE: readonly MatchFilter[] = [
  "unvalidated",
  "mismatched",
  "all",
] as const;

export function nextMatchFilter(current: MatchFilter): MatchFilter {
  const idx = MATCH_FILTER_CYCLE.indexOf(current);
  // -1 (unknown value) falls through to index 0 → "unvalidated".
  const nextIdx = idx < 0 ? 0 : (idx + 1) % MATCH_FILTER_CYCLE.length;
  return MATCH_FILTER_CYCLE[nextIdx];
}

export type DrawerTab = "worklist" | "hierarchy";

export interface UiPrefsState {
  lineFilter: string | null;
  layerVisibility: LayerVisibility;
  /** Horizontal splitter ratio in [0.2, 0.8]. 0.5 = panes equal width. */
  splitterRatio: number;
  selectionMode: "paragraph" | "line" | "word";
  /** Word-match list filter (spec 22 §8). Default: "unvalidated". */
  matchFilter: MatchFilter;
  /** Whether the drawer panel is open. Spec: Slice 11. */
  drawerOpen: boolean;
  /** Active drawer tab. Spec: Slice 11. */
  drawerTab: DrawerTab;
}

type SetStateArg<T> = Partial<T> | ((state: T) => Partial<T>);

interface Store<T> {
  getState: () => T;
  setState: (arg: SetStateArg<T>) => void;
  /** Convenience setter for splitter ratio (clamps to [0.2, 0.8]). */
  setSplitterRatio: (ratio: number) => void;
  /** Set the word-match filter directly. */
  setMatchFilter: (filter: MatchFilter) => void;
  /** Cycle through unvalidated → mismatched → all → unvalidated. */
  cycleMatchFilter: () => void;
}

/** Clamp the splitter ratio to the spec-22 §9 range [0.2, 0.8]. */
export function clampSplitterRatio(ratio: number): number {
  if (Number.isNaN(ratio)) return 0.5;
  if (ratio < 0.2) return 0.2;
  if (ratio > 0.8) return 0.8;
  return ratio;
}

function createStore<T extends object>(initialState: T): Store<T> {
  let state = initialState;

  const setState = (arg: SetStateArg<T>) => {
    const newState = typeof arg === "function" ? (arg as (s: T) => Partial<T>)(state) : arg;
    state = { ...state, ...newState };
  };

  return {
    getState: () => state,
    setState,
    setSplitterRatio: (ratio: number) => {
      const clamped = clampSplitterRatio(ratio);
      setState({ splitterRatio: clamped } as unknown as SetStateArg<T>);
    },
    setMatchFilter: (filter: MatchFilter) => {
      setState({ matchFilter: filter } as unknown as SetStateArg<T>);
    },
    cycleMatchFilter: () => {
      const current = (state as unknown as UiPrefsState).matchFilter;
      setState({ matchFilter: nextMatchFilter(current) } as unknown as SetStateArg<T>);
    },
  };
}

export const useUiPrefs = createStore<UiPrefsState>({
  lineFilter: null,
  layerVisibility: {
    paragraph: true,
    line: true,
    word: true,
  },
  splitterRatio: 0.5,
  selectionMode: "paragraph",
  matchFilter: "unvalidated",
  drawerOpen: true,
  drawerTab: "worklist",
});

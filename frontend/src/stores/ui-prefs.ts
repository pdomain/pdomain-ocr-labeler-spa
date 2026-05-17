// ui-prefs.ts — UI preferences store (line filter, layer visibility,
// splitter ratio, selection mode, match filter, theme, match filter mode).
//
// Spec: specs/22-page-surface-wireup.md §8 (FilterToggle), §9 (Splitter),
//       D-021 (UI prefs).
//       docs/specs/2026-05-15-hifi-redesign-plan.md Slice 24 (theme toggle).
//       Issue #295 (matchFilterMode — Mismatches-only bbox overlay toggle).
// `splitterRatio` is the canonical field name (matches spec 22). The
// legacy alias `splitterPosition` was renamed; no production callers
// exist yet — only the store + this test relied on the old name.

import { useSyncExternalStore } from "react";

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
  // nextIdx is always in-bounds (computed via modulo) — non-null safe.
  // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
  return MATCH_FILTER_CYCLE[nextIdx]!;
}

export type DrawerTab = "worklist" | "hierarchy";

/** Slice 24 — theme preference. */
export type ThemePreference = "dark" | "light" | "system";

/** localStorage key for theme persistence. */
export const THEME_STORAGE_KEY = "pdl.ui.theme";

const VALID_THEME_VALUES = new Set<string>(["dark", "light", "system"]);

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
  /** IS-6: Whether the right panel is open. Default: true. */
  rightPanelOpen: boolean;
  /** Theme preference — Slice 24. Default: "system". */
  theme: ThemePreference;
  /**
   * Bbox overlay filter mode — Issue #295 (Option C).
   *
   * When "mismatches_only", the word bbox overlay dims exact/validated words
   * to 20% opacity so mismatch/fuzzy/unvalidated words stand out.
   * Default: "all" (no filtering).
   */
  matchFilterMode: "all" | "mismatches_only";
}

type SetStateArg<T> = Partial<T> | ((state: T) => Partial<T>);
type Listener = () => void;

interface Store<T> {
  getState: () => T;
  setState: (arg: SetStateArg<T>) => void;
  subscribe: (listener: Listener) => () => void;
  /** Convenience setter for splitter ratio (clamps to [0.2, 0.8]). */
  setSplitterRatio: (ratio: number) => void;
  /** Set the word-match filter directly. */
  setMatchFilter: (filter: MatchFilter) => void;
  /** Cycle through unvalidated → mismatched → all → unvalidated. */
  cycleMatchFilter: () => void;
  /** Set the theme preference — applies to documentElement immediately. */
  setTheme: (theme: ThemePreference) => void;
  /** Set the bbox overlay filter mode — Issue #295. */
  setMatchFilterMode: (mode: "all" | "mismatches_only") => void;
}

/** Clamp the splitter ratio to the spec-22 §9 range [0.2, 0.8]. */
export function clampSplitterRatio(ratio: number): number {
  if (Number.isNaN(ratio)) return 0.5;
  if (ratio < 0.2) return 0.2;
  if (ratio > 0.8) return 0.8;
  return ratio;
}

/** Read theme preference from localStorage; fall back to "system". */
function readPersistedTheme(): ThemePreference {
  try {
    const raw = localStorage.getItem(THEME_STORAGE_KEY);
    if (raw && VALID_THEME_VALUES.has(raw)) return raw as ThemePreference;
  } catch {
    // localStorage unavailable (SSR, private mode)
  }
  return "system";
}

/**
 * Returns the effective (dark|light) theme to apply to
 * `document.documentElement.dataset.theme`, resolving "system" via the
 * `prefers-color-scheme` media query.
 */
export function resolveEffectiveTheme(theme: ThemePreference): "dark" | "light" {
  if (theme === "system") {
    try {
      return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
    } catch {
      return "dark";
    }
  }
  return theme;
}

/** Apply the effective theme to `document.documentElement.dataset.theme`. */
function applyTheme(theme: ThemePreference) {
  try {
    document.documentElement.dataset["theme"] = resolveEffectiveTheme(theme);
  } catch {
    // no document in test env without jsdom — handled by tests separately
  }
}

function createStore<T extends object>(initialState: T): Store<T> {
  let state = initialState;
  const listeners = new Set<Listener>();

  function notify() {
    listeners.forEach((fn) => {
      fn();
    });
  }

  const setState = (arg: SetStateArg<T>) => {
    const newState = typeof arg === "function" ? arg(state) : arg;
    state = { ...state, ...newState };
    notify();
  };

  // ── Media-query listener for System mode ────────────────────────────────
  let mediaQueryCleanup: (() => void) | null = null;

  function setupSystemListener(theme: ThemePreference) {
    if (mediaQueryCleanup) {
      mediaQueryCleanup();
      mediaQueryCleanup = null;
    }
    if (theme === "system") {
      try {
        const mq = window.matchMedia("(prefers-color-scheme: light)");
        const handler = () => {
          applyTheme("system");
          notify();
        };
        mq.addEventListener("change", handler);
        mediaQueryCleanup = () => {
          mq.removeEventListener("change", handler);
        };
      } catch {
        // not available
      }
    }
  }

  return {
    getState: () => state,
    setState,
    subscribe: (listener: Listener) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
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
    setTheme: (theme: ThemePreference) => {
      try {
        localStorage.setItem(THEME_STORAGE_KEY, theme);
      } catch {
        // ignore
      }
      setState({ theme } as unknown as SetStateArg<T>);
      setupSystemListener(theme);
      applyTheme(theme);
    },
    setMatchFilterMode: (mode: "all" | "mismatches_only") => {
      setState({ matchFilterMode: mode } as unknown as SetStateArg<T>);
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
  rightPanelOpen: true,
  theme: readPersistedTheme(),
  matchFilterMode: "all",
});

// Apply initial theme on module load.
applyTheme(useUiPrefs.getState().theme);

/**
 * React hook — returns the current theme preference.
 * Uses `useSyncExternalStore` so it re-renders when theme changes.
 */
export function useThemePreference(): ThemePreference {
  return useSyncExternalStore(
    useUiPrefs.subscribe,
    () => useUiPrefs.getState().theme,
    () => "system",
  );
}

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
//
// Phase 2.5 (cross-cut-design §7.5): migrated from hand-rolled reactive
// store to Zustand's vanilla `createStore`. External API (`useUiPrefs`
// store object, `useThemePreference` hook) preserved intact.
//
// GAP-5: Cannot use pdomain-ui's `createUIPrefsStore()` factory.
//   pdomain-ui offers: async load/persist callbacks, theme/density/layerColors/
//   statusColors/accentColor with setTheme/setDensity/setAppPref.
//   This store needs: labeler-specific prefs (lineFilter, layerVisibility,
//   splitterRatio, selectionMode, matchFilter, drawerOpen/Tab, rightPanelOpen,
//   matchFilterMode) all managed synchronously in-memory with localStorage
//   persistence only for theme. The pdomain-ui factory's async load/persist
//   contract targets the future pdomain-suite prefs API (§3.2); that wiring is
//   deferred to when pdomain-ocr-ops routes are mounted (Phase 2.4+).
//   Replace with pdomain-ui factory when the pdomain-suite prefs API is wired and
//   the labeler-specific prefs schema is migrated into `UIPrefs.app`.

import { createStore } from "zustand/vanilla";
import { useSyncExternalStore } from "react";

export interface LayerVisibility {
  block: boolean;
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
const MATCH_FILTER_CYCLE: readonly MatchFilter[] = ["unvalidated", "mismatched", "all"] as const;

export function nextMatchFilter(current: MatchFilter): MatchFilter {
  const idx = MATCH_FILTER_CYCLE.indexOf(current);
  // -1 (unknown value) falls through to index 0 → "unvalidated".
  const nextIdx = idx < 0 ? 0 : (idx + 1) % MATCH_FILTER_CYCLE.length;
  // nextIdx is always in-bounds (computed via modulo) — non-null safe.
  // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
  return MATCH_FILTER_CYCLE[nextIdx]!;
}

/** S2.2: "text" tab added for the visible full-page GT/OCR read-only view. */
export type DrawerTab = "worklist" | "hierarchy" | "text";

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
  /**
   * GRID-1 (Slice C): whether the ToolbarActionGrid collapsible bar is
   * collapsed. Default: false (expanded/visible so CT sees it immediately).
   */
  toolbarGridCollapsed: boolean;
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

// ── Media-query listener for System mode ──────────────────────────────────
let mediaQueryCleanup: (() => void) | null = null;

function setupSystemListener(theme: ThemePreference, notifyFn: () => void) {
  if (mediaQueryCleanup) {
    mediaQueryCleanup();
    mediaQueryCleanup = null;
  }
  if (theme === "system") {
    try {
      const mq = window.matchMedia("(prefers-color-scheme: light)");
      const handler = () => {
        applyTheme("system");
        notifyFn();
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

const INITIAL_PREFS: UiPrefsState = {
  lineFilter: null,
  layerVisibility: {
    block: true,
    paragraph: true,
    line: true,
    word: true,
  },
  splitterRatio: 0.5,
  // SEL-3: default matches railStore.target default ("word") so both
  // controls agree on the initial granularity without localStorage reads.
  selectionMode: "word",
  matchFilter: "unvalidated",
  drawerOpen: true,
  drawerTab: "worklist",
  rightPanelOpen: true,
  theme: readPersistedTheme(),
  matchFilterMode: "all",
  // GRID-1: default expanded so CT sees the grid immediately on first load.
  toolbarGridCollapsed: false,
};

const _store = createStore<UiPrefsState>(() => ({ ...INITIAL_PREFS }));

/**
 * UI prefs store — exposes the same surface as the old hand-rolled store
 * (`getState`, `setState`, `subscribe`, `setSplitterRatio`, `setMatchFilter`,
 * `cycleMatchFilter`, `setTheme`, `setMatchFilterMode`) so all call sites
 * remain unchanged.
 *
 * Named `useUiPrefs` for historical reasons (originally a hook-like object).
 * It is NOT a React hook — it is an imperative store object that components
 * subscribe to via `useSyncExternalStore(useUiPrefs.subscribe, ...)`.
 */
export const useUiPrefs = {
  /** Current state snapshot. */
  getState: () => _store.getState(),
  /** Set partial state (merge). Accepts partial object or updater function. */
  setState: (arg: Partial<UiPrefsState> | ((s: UiPrefsState) => Partial<UiPrefsState>)) => {
    const patch = typeof arg === "function" ? arg(_store.getState()) : arg;
    _store.setState((s) => ({ ...s, ...patch }));
  },
  /** Subscribe to changes (returns unsubscribe). */
  subscribe: (listener: () => void) => _store.subscribe(listener),

  /** Convenience setter for splitter ratio (clamps to [0.2, 0.8]). */
  setSplitterRatio: (ratio: number) => {
    const clamped = clampSplitterRatio(ratio);
    _store.setState((s) => ({ ...s, splitterRatio: clamped }));
  },

  /** Set the word-match filter directly. */
  setMatchFilter: (filter: MatchFilter) => {
    _store.setState((s) => ({ ...s, matchFilter: filter }));
  },

  /** Cycle through unvalidated → mismatched → all → unvalidated. */
  cycleMatchFilter: () => {
    _store.setState((s) => ({ ...s, matchFilter: nextMatchFilter(s.matchFilter) }));
  },

  /** Set the theme preference — applies to documentElement immediately. */
  setTheme: (theme: ThemePreference) => {
    try {
      localStorage.setItem(THEME_STORAGE_KEY, theme);
    } catch {
      // ignore
    }
    _store.setState((s) => ({ ...s, theme }));
    setupSystemListener(theme, () => {
      // Trigger a re-render by updating a stable piece of state.
      // The theme value itself hasn't changed (still "system"), but
      // the DOM has been updated by applyTheme; nudge Zustand so
      // subscribers (e.g. useThemePreference) re-read getState().
      _store.setState((s) => ({ ...s }));
    });
    applyTheme(theme);
  },

  /** Set the bbox overlay filter mode — Issue #295. */
  setMatchFilterMode: (mode: "all" | "mismatches_only") => {
    _store.setState((s) => ({ ...s, matchFilterMode: mode }));
  },
};

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

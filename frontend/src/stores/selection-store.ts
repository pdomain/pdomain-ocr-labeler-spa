// selection-store.ts — optimistic selection state store.
// Spec: docs/specs/2026-05-12-image-viewport-design.md §Select mode (legacy fields)
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 15 (level/path layer)
// Issue #197 (legacy fields), Slice 15 (hierarchical layer)
//
// Maintains the current selection optimistically — updated immediately on
// mouse interaction, then confirmed/rolled-back based on POST response.
//
// State has two coexisting layers:
//
// 1. **Legacy multi-select arrays** (selectedParagraphs/Lines/Words):
//    consumed by ToolbarActionGrid, ProjectPage toolbar bindings, and the
//    server-side Selection model. These remain the canonical way to express
//    a multi-select set.
//
// 2. **Hierarchical single selection** (level + path): new in Slice 15.
//    Drives Breadcrumb, RightPanel routing, and Alt-arrow navigation.
//    Always reflects the deepest concrete leaf of the current selection.
//
// The two layers are kept in sync by the select*() / walk*() actions:
// selecting a line via `selectLine(pageIndex, 7)` sets `selectedLines=[7]`,
// `path={pageIndex, lineId:7}`, `level="line"`. Legacy call sites that
// mutate the arrays directly via setState are still supported, but won't
// update level/path automatically — call the action helpers for the new
// layer.
//
// P2-SELECTION-PAGE: a block/para/line/word `path` carries the page index it
// was made on. A consumer resolving a selection against a specific loaded
// page must go through `resolveSelectionForPage` / `useSelectionForPage`
// (bottom of this file) rather than reading `getState()` directly, so a
// selection from another page reads as no selection. A region/proposal path
// (`regionId`/`proposalId`) never carries `pageIndex` — that level clears on
// page change through ProjectPage's own, separate mechanism instead.
//
// Phase 2.5 (cross-cut-design §7.5): migrated from hand-rolled reactive
// store to Zustand's vanilla `createStore`.
//
// GAP-1: Cannot use pdomain-ui's `createSelectionStore()` factory.
//   pdomain-ui offers: `ids: ReadonlySet<string>, select, deselect, clearSelection`.
//   This store needs: hierarchical path/level navigation, multi-select tuples
//   (selectedParagraphs/Lines/Words), dragRect, walkSibling/walkLevel navigation
//   driven by PagePayload structure. These are labeler-specific concerns that
//   do not belong in pdomain-ui. Replace with pdomain-ui factory when pdomain-ui adds a
//   hierarchical-selection extension, or accept the local implementation as a
//   labeler-only store permanently.

import { createStore } from "zustand/vanilla";
import { useMemo, useSyncExternalStore } from "react";
import type { BBox } from "../lib/coords";
import {
  nextSibling,
  walkUp,
  walkDown,
  pathLevel,
  type SelectionPath,
  type SelectionLevel,
  type WalkDirection,
} from "../lib/selection-walk";
import type { components } from "../api/types";

type PagePayload = components["schemas"]["PagePayload"];

export interface SelectionState {
  // ── Legacy multi-select arrays ───────────────────────────────────────────
  /** Selected paragraph indices. */
  selectedParagraphs: number[];
  /** Selected line indices. */
  selectedLines: number[];
  /** Selected words as `[line_idx, word_idx]` tuples. */
  selectedWords: [number, number][];
  /** Current drag rect (display pixels), null when not dragging. */
  dragRect: BBox | null;

  // ── Hierarchical single-selection layer (Slice 15) ───────────────────────
  /** Deepest level currently selected, or "none". */
  level: SelectionLevel;
  /** Path identifying the selection at each level. */
  path: SelectionPath;
}

const INITIAL_STATE: SelectionState = {
  selectedParagraphs: [],
  selectedLines: [],
  selectedWords: [],
  dragRect: null,
  level: "none",
  path: {},
};

export const selectionStore = createStore<SelectionState>(() => ({ ...INITIAL_STATE }));

// ─── Mutators ────────────────────────────────────────────────────────────────

/** Clear all selection state, including drag rect, level, and path. */
export function clearSelection(): void {
  selectionStore.setState(() => ({ ...INITIAL_STATE }));
}

/** Set drag rect during box-select drag. */
export function setDragRect(rect: BBox | null): void {
  selectionStore.setState((s) => ({ ...s, dragRect: rect }));
}

/**
 * Select a block by opaque id. (No block layer exists in PagePayload yet;
 * the path is recorded for breadcrumb display, but `walkSibling` is a
 * no-op at block level.)
 *
 * `pageIndex` (0-based) is the page this selection belongs to — stamped
 * onto the path so a later page change can tell this selection apart from
 * one made on the page now loaded (P2-SELECTION-PAGE).
 */
export function selectBlock(pageIndex: number, blockId: string): void {
  selectionStore.setState((s) => ({
    ...s,
    selectedParagraphs: [],
    selectedLines: [],
    selectedWords: [],
    level: "block",
    path: { pageIndex, blockId },
  }));
}

/** Select a paragraph by paragraph_index (null bucket allowed). See `selectBlock` for `pageIndex`. */
export function selectPara(pageIndex: number, paraId: number | null): void {
  selectionStore.setState((s) => ({
    ...s,
    selectedParagraphs: paraId === null ? [] : [paraId],
    selectedLines: [],
    selectedWords: [],
    level: "para",
    path: { pageIndex, paraId },
  }));
}

/** Select a line by line_index. See `selectBlock` for `pageIndex`. */
export function selectLine(pageIndex: number, lineId: number): void {
  selectionStore.setState((s) => ({
    ...s,
    selectedParagraphs: [],
    selectedLines: [lineId],
    selectedWords: [],
    level: "line",
    path: { pageIndex, lineId },
  }));
}

export function applyLineSelection(
  pageIndex: number,
  lineIds: readonly number[],
  mode: "replace" | "toggle" | "remove",
): void {
  selectionStore.setState((s) => {
    const incoming = Array.from(new Set(lineIds));
    let next: number[];
    if (mode === "replace") {
      next = incoming;
    } else if (mode === "toggle") {
      const selected = new Set(s.selectedLines);
      for (const lineId of incoming) {
        if (selected.has(lineId)) {
          selected.delete(lineId);
        } else {
          selected.add(lineId);
        }
      }
      next = Array.from(selected);
    } else {
      const removing = new Set(incoming);
      next = s.selectedLines.filter((lineId) => !removing.has(lineId));
    }

    if (next.length === 0) {
      return { ...s, selectedLines: [], level: "none", path: {} };
    }
    const firstLineId = next[0];
    if (firstLineId === undefined) {
      return { ...s, selectedLines: [], level: "none", path: {} };
    }

    return {
      ...s,
      selectedParagraphs: [],
      selectedLines: next,
      selectedWords: [],
      level: "line",
      path: { pageIndex, lineId: firstLineId },
    };
  });
}

export function applyParagraphSelection(
  pageIndex: number,
  paragraphIds: readonly number[],
  mode: "replace" | "toggle" | "remove",
): void {
  selectionStore.setState((s) => {
    const incoming = Array.from(new Set(paragraphIds));
    let next: number[];
    if (mode === "replace") {
      next = incoming;
    } else if (mode === "toggle") {
      const selected = new Set(s.selectedParagraphs);
      for (const paragraphId of incoming) {
        if (selected.has(paragraphId)) {
          selected.delete(paragraphId);
        } else {
          selected.add(paragraphId);
        }
      }
      next = Array.from(selected);
    } else {
      const removing = new Set(incoming);
      next = s.selectedParagraphs.filter((paragraphId) => !removing.has(paragraphId));
    }

    if (next.length === 0) {
      return { ...s, selectedParagraphs: [], level: "none", path: {} };
    }
    const firstParaId = next[0];
    if (firstParaId === undefined) {
      return { ...s, selectedParagraphs: [], level: "none", path: {} };
    }

    return {
      ...s,
      selectedParagraphs: next,
      selectedLines: [],
      selectedWords: [],
      level: "para",
      path: { pageIndex, paraId: firstParaId },
    };
  });
}

/** Select a single word by (line_index, word_index). See `selectBlock` for `pageIndex`. */
export function selectWord(pageIndex: number, lineIdx: number, wordIdx: number): void {
  selectionStore.setState((s) => ({
    ...s,
    selectedParagraphs: [],
    selectedLines: [],
    selectedWords: [[lineIdx, wordIdx]],
    level: "word",
    path: { pageIndex, lineId: lineIdx, wordId: [lineIdx, wordIdx] },
  }));
}

/**
 * Select a confirmed region by id. (No sibling layer exists for regions;
 * `walkSibling` is a no-op at region level, same as at block level.)
 */
export function selectRegion(regionId: string): void {
  selectionStore.setState((s) => ({
    ...s,
    selectedParagraphs: [],
    selectedLines: [],
    selectedWords: [],
    level: "region",
    path: { regionId },
  }));
}

/** Select an undecided proposal by id. */
export function selectProposal(proposalId: string): void {
  selectionStore.setState((s) => ({
    ...s,
    selectedParagraphs: [],
    selectedLines: [],
    selectedWords: [],
    level: "region",
    path: { proposalId },
  }));
}

// ─── Navigation actions (Slice 15) ───────────────────────────────────────────

/**
 * Stamp `page.page_index` onto `path`, unless `path` carries no selection —
 * an empty path stays `{}` so `toEqual({})`-style comparisons and
 * `pathLevel` both keep reading it as "none".
 */
function withPageIndex(path: SelectionPath, page: PagePayload): SelectionPath {
  // A path that has collapsed to "none" (e.g. walkUp from the shallowest
  // level) may still carry a leftover `pageIndex` from the path it was
  // derived from — normalize to a clean `{}` so callers comparing against
  // "no selection" don't have to know about that leftover key.
  if (pathLevel(path) === "none") return {};
  return { ...path, pageIndex: page.page_index };
}

function applyPath(prev: SelectionState, path: SelectionPath, page: PagePayload): SelectionState {
  const stamped = withPageIndex(path, page);
  const lvl = pathLevel(stamped);
  // Sync the legacy arrays to the new path so existing consumers stay
  // coherent. Only one layer is filled per call.
  const next: SelectionState = {
    ...INITIAL_STATE,
    dragRect: prev.dragRect, // preserve in-flight drag
    level: lvl,
    path: stamped,
  };
  if (stamped.wordId !== undefined) {
    next.selectedWords = [stamped.wordId];
  } else if (stamped.lineId !== undefined) {
    next.selectedLines = [stamped.lineId];
  } else if (stamped.paraId !== undefined && stamped.paraId !== null) {
    next.selectedParagraphs = [stamped.paraId];
  }
  return next;
}

/**
 * A selection whose `path.pageIndex` disagrees with `page.page_index`
 * belongs to a page other than the one loaded — nothing on this page to
 * walk from (P2-SELECTION-PAGE).
 */
function belongsToOtherPage(path: SelectionPath, page: PagePayload): boolean {
  return path.pageIndex !== undefined && path.pageIndex !== page.page_index;
}

/**
 * Walk to the next/previous sibling at the deepest level of the current path.
 *
 * No-op when there is no current selection, no siblings at that level, or
 * the selection belongs to a page other than `page` — a stale-page
 * selection is nothing to act on, and this leaves it untouched so it is
 * still there if the person pages back to it.
 */
export function walkSibling(direction: WalkDirection, page: PagePayload): void {
  selectionStore.setState((s) => {
    if (s.level === "none") return s;
    if (belongsToOtherPage(s.path, page)) return s;
    const nextPath = nextSibling(s.path, page, direction);
    return applyPath(s, nextPath, page);
  });
}

export function promoteCompleteWordLines(page: PagePayload): void {
  selectionStore.setState((s) => {
    if (s.selectedWords.length === 0) return s;
    if (belongsToOtherPage(s.path, page)) return s;

    const selectedByLine = new Map<number, Set<number>>();
    for (const [lineIdx, wordIdx] of s.selectedWords) {
      const words = selectedByLine.get(lineIdx) ?? new Set<number>();
      words.add(wordIdx);
      selectedByLine.set(lineIdx, words);
    }

    const completedLines: number[] = [];
    const completedLineSet = new Set<number>();
    for (const line of page.line_matches ?? []) {
      const selectableWordIds = line.word_matches
        .map((word) => word.word_index)
        .filter((wordIndex): wordIndex is number => wordIndex !== null);
      if (selectableWordIds.length === 0) continue;
      const selected = selectedByLine.get(line.line_index);
      if (!selected) continue;
      if (selectableWordIds.every((wordIndex) => selected.has(wordIndex))) {
        completedLines.push(line.line_index);
        completedLineSet.add(line.line_index);
      }
    }

    if (completedLines.length === 0) return s;

    const remainingWords = s.selectedWords.filter(([lineIdx]) => !completedLineSet.has(lineIdx));
    const nextLines = Array.from(new Set([...s.selectedLines, ...completedLines]));
    const firstLineId = nextLines[0];
    if (firstLineId === undefined) return s;

    if (remainingWords.length > 0) {
      const last = remainingWords[remainingWords.length - 1];
      if (last === undefined) return s;
      return {
        ...s,
        selectedLines: nextLines,
        selectedWords: remainingWords,
        level: "word",
        path: { pageIndex: page.page_index, lineId: last[0], wordId: last },
      };
    }

    return {
      ...s,
      selectedLines: nextLines,
      selectedWords: [],
      level: "line",
      path: { pageIndex: page.page_index, lineId: firstLineId },
    };
  });
}

/**
 * Walk up (Alt+Up) or down (Alt+Down) one level in the hierarchy.
 *   "up"   → drop the deepest level.
 *   "down" → descend into the first child of the current level.
 *
 * No-op when the current selection belongs to a page other than `page` —
 * same reasoning as `walkSibling` above. This only guards a genuine
 * stale-page selection; walking down from no selection at all (fresh
 * `path.pageIndex === undefined`) still starts a new selection on `page`,
 * unaffected.
 */
export function walkLevel(direction: "up" | "down", page: PagePayload): void {
  selectionStore.setState((s) => {
    if (belongsToOtherPage(s.path, page)) return s;
    const nextPath = direction === "up" ? walkUp(s.path, page) : walkDown(s.path, page);
    return applyPath(s, nextPath, page);
  });
}

// ─── SEL-4 / SEL-5: Additive multi-select ────────────────────────────────────

/**
 * Add, remove, or toggle a word in the multi-select set.
 *
 * mode="replace" — discard prior selection, set this word as the sole selection.
 * mode="toggle"  — if the word is already selected, remove it; otherwise add it.
 *                  Enables cross-block accumulation (Ctrl/Cmd-click, SEL-4).
 * mode="remove"  — remove this word from the selection (Shift-click, SEL-5).
 *
 * level is always "word" while words are selected; drops to "none" when the
 * set becomes empty.
 *
 * `pageIndex` (0-based) is the page this word belongs to — see `selectBlock`.
 */
export function toggleWord(
  pageIndex: number,
  lineIdx: number,
  wordIdx: number,
  mode: "replace" | "toggle" | "remove",
): void {
  selectionStore.setState((s) => {
    const tuple: [number, number] = [lineIdx, wordIdx];
    const isPresent = s.selectedWords.some(([l, w]) => l === lineIdx && w === wordIdx);

    let next: [number, number][];
    if (mode === "replace") {
      next = [tuple];
    } else if (mode === "toggle") {
      next = isPresent
        ? s.selectedWords.filter(([l, w]) => !(l === lineIdx && w === wordIdx))
        : [...s.selectedWords, tuple];
    } else {
      // remove
      next = s.selectedWords.filter(([l, w]) => !(l === lineIdx && w === wordIdx));
    }

    const newLevel: SelectionLevel = next.length > 0 ? "word" : "none";
    // path: keep the most-recently-touched word, or clear if empty.
    const newPath: SelectionPath =
      next.length > 0 ? { pageIndex, lineId: lineIdx, wordId: tuple } : {};

    return {
      ...s,
      selectedParagraphs: [],
      selectedLines: [],
      selectedWords: next,
      level: newLevel,
      path: newPath,
    };
  });
}

// ─── Page-scoped resolution (P2-SELECTION-PAGE) ──────────────────────────────
//
// A block/para/line/word selection carries the page index it was made on
// (`path.pageIndex`, stamped by the select*/apply*/toggleWord/walk* actions
// above). Every consumer that resolves a selection against a specific loaded
// page — the right panel's line/word/paragraph/block views, the canvas
// highlight, and the breadcrumb — must read through `resolveSelectionForPage`
// (or the `useSelectionForPage` hook) rather than `selectionStore.getState()`
// directly, so a selection from another page reads as no selection instead
// of resolving against whichever page happens to be loaded.
//
// A region or proposal selection (`path.regionId`/`path.proposalId`) never
// carries `pageIndex` and so is never affected here — it clears on page
// change through ProjectPage's separate, pre-existing region-selection-
// scoping effect (whole-branch review defect 2).

/**
 * Resolve `state` against `pageIndex` (the page currently loaded, 0-based).
 *
 * Returns `state` unchanged when its path carries no `pageIndex` (no
 * selection, or a region/proposal selection) or when `path.pageIndex`
 * matches `pageIndex`. Otherwise returns a selection-cleared view — level
 * "none", empty path and legacy arrays — without touching the underlying
 * store, so the selection is exactly as it was if the person pages back to
 * where they made it.
 */
export function resolveSelectionForPage(
  state: SelectionState,
  pageIndex: number | undefined,
): SelectionState {
  if (state.path.pageIndex === undefined) return state;
  if (state.path.pageIndex === pageIndex) return state;
  return { ...INITIAL_STATE, dragRect: state.dragRect };
}

/**
 * React hook: the selection state as it applies to `pageIndex` (the page
 * currently loaded, 0-based, or `undefined` while no page has loaded yet).
 *
 * Subscribes to the raw store (referentially stable until the store itself
 * changes) and derives the page-scoped view in `useMemo`, so the returned
 * object is referentially stable across renders where neither the store nor
 * `pageIndex` changed — required for `useSyncExternalStore`-style
 * consumers built on top of this to avoid re-render loops.
 */
export function useSelectionForPage(pageIndex: number | undefined): SelectionState {
  const raw = useSyncExternalStore(
    selectionStore.subscribe,
    selectionStore.getState,
    selectionStore.getState,
  );
  return useMemo(() => resolveSelectionForPage(raw, pageIndex), [raw, pageIndex]);
}

// Re-export shared types so consumers can import them from one place.
export type { SelectionLevel, SelectionPath, WalkDirection };

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
// selecting a line via `selectLine(7)` sets `selectedLines=[7]`,
// `path={lineId:7}`, `level="line"`. Legacy call sites that mutate the
// arrays directly via setState are still supported, but won't update
// level/path automatically — call the action helpers for the new layer.
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
 */
export function selectBlock(blockId: string): void {
  selectionStore.setState((s) => ({
    ...s,
    selectedParagraphs: [],
    selectedLines: [],
    selectedWords: [],
    level: "block",
    path: { blockId },
  }));
}

/** Select a paragraph by paragraph_index (null bucket allowed). */
export function selectPara(paraId: number | null): void {
  selectionStore.setState((s) => ({
    ...s,
    selectedParagraphs: paraId === null ? [] : [paraId],
    selectedLines: [],
    selectedWords: [],
    level: "para",
    path: { paraId },
  }));
}

/** Select a line by line_index. */
export function selectLine(lineId: number): void {
  selectionStore.setState((s) => ({
    ...s,
    selectedParagraphs: [],
    selectedLines: [lineId],
    selectedWords: [],
    level: "line",
    path: { lineId },
  }));
}

export function applyLineSelection(
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
      path: { lineId: firstLineId },
    };
  });
}

export function applyParagraphSelection(
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
      path: { paraId: firstParaId },
    };
  });
}

/** Select a single word by (line_index, word_index). */
export function selectWord(lineIdx: number, wordIdx: number): void {
  selectionStore.setState((s) => ({
    ...s,
    selectedParagraphs: [],
    selectedLines: [],
    selectedWords: [[lineIdx, wordIdx]],
    level: "word",
    path: { lineId: lineIdx, wordId: [lineIdx, wordIdx] },
  }));
}

// ─── Navigation actions (Slice 15) ───────────────────────────────────────────

function applyPath(prev: SelectionState, path: SelectionPath): SelectionState {
  const lvl = pathLevel(path);
  // Sync the legacy arrays to the new path so existing consumers stay
  // coherent. Only one layer is filled per call.
  const next: SelectionState = {
    ...INITIAL_STATE,
    dragRect: prev.dragRect, // preserve in-flight drag
    level: lvl,
    path,
  };
  if (path.wordId !== undefined) {
    next.selectedWords = [path.wordId];
  } else if (path.lineId !== undefined) {
    next.selectedLines = [path.lineId];
  } else if (path.paraId !== undefined && path.paraId !== null) {
    next.selectedParagraphs = [path.paraId];
  }
  return next;
}

/**
 * Walk to the next/previous sibling at the deepest level of the current path.
 *
 * No-op when there is no current selection or no siblings at that level.
 */
export function walkSibling(direction: WalkDirection, page: PagePayload): void {
  selectionStore.setState((s) => {
    if (s.level === "none") return s;
    const nextPath = nextSibling(s.path, page, direction);
    return applyPath(s, nextPath);
  });
}

export function promoteCompleteWordLines(page: PagePayload): void {
  selectionStore.setState((s) => {
    if (s.selectedWords.length === 0) return s;

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
        path: { lineId: last[0], wordId: last },
      };
    }

    return {
      ...s,
      selectedLines: nextLines,
      selectedWords: [],
      level: "line",
      path: { lineId: firstLineId },
    };
  });
}

/**
 * Walk up (Alt+Up) or down (Alt+Down) one level in the hierarchy.
 *   "up"   → drop the deepest level.
 *   "down" → descend into the first child of the current level.
 */
export function walkLevel(direction: "up" | "down", page: PagePayload): void {
  selectionStore.setState((s) => {
    const nextPath = direction === "up" ? walkUp(s.path, page) : walkDown(s.path, page);
    return applyPath(s, nextPath);
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
 */
export function toggleWord(
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
    const newPath: SelectionPath = next.length > 0 ? { lineId: lineIdx, wordId: tuple } : {};

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

// Re-export shared types so consumers can import them from one place.
export type { SelectionLevel, SelectionPath, WalkDirection };

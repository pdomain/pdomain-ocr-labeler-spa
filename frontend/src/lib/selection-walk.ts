// selection-walk.ts — pure hierarchy navigation helpers.
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 15.
//
// Given a PagePayload and a SelectionPath (block/para/line/word ids), compute
// the next sibling at the deepest level (Alt+Left/Right) or the parent /
// first-child path one level up or down (Alt+Up/Down).
//
// IDs:
//   blockId  — opaque string (PagePayload has no explicit block layer yet, so
//              callers pass synthetic ids; navigation is a no-op when no
//              siblings exist).
//   paraId   — `paragraph_index` from LineMatch (can be null → "Unsorted"
//              bucket, represented here as the literal string "null").
//   lineId   — `line_index` from LineMatch (number).
//   wordId   — tuple `[line_index, word_index]`.
//
// All helpers are pure and side-effect-free. Missing levels (e.g. walkUp from
// "none") return the path unchanged.

import type { components } from "../api/types";

type PagePayload = components["schemas"]["PagePayload"];
type LineMatch = components["schemas"]["LineMatch"];

export type SelectionLevel = "none" | "block" | "para" | "line" | "word";

export interface SelectionPath {
  blockId?: string;
  paraId?: number | null;
  lineId?: number;
  wordId?: [number, number];
}

export type WalkDirection = "next" | "prev";

// ─── Index helpers ───────────────────────────────────────────────────────────

/** Sorted list of distinct paragraph indices (nulls bucketed together at end). */
function paraIds(page: PagePayload): Array<number | null> {
  const ids = new Set<number | null>();
  let hasNull = false;
  for (const lm of page.line_matches ?? []) {
    if (lm.paragraph_index === null || lm.paragraph_index === undefined) {
      hasNull = true;
    } else {
      ids.add(lm.paragraph_index);
    }
  }
  const sorted = Array.from(ids)
    .filter((v): v is number => typeof v === "number")
    .sort((a, b) => a - b);
  return hasNull ? [...sorted, null] : sorted;
}

/** Lines (sorted by line_index) belonging to the given paragraph_index (null bucket allowed). */
function linesInPara(page: PagePayload, paraId: number | null): LineMatch[] {
  return (page.line_matches ?? [])
    .filter((lm) => {
      const p = lm.paragraph_index ?? null;
      return p === paraId;
    })
    .slice()
    .sort((a, b) => a.line_index - b.line_index);
}

/** All lines sorted by line_index. */
function allLines(page: PagePayload): LineMatch[] {
  return (page.line_matches ?? []).slice().sort((a, b) => a.line_index - b.line_index);
}

function findLine(page: PagePayload, lineId: number): LineMatch | undefined {
  return (page.line_matches ?? []).find((lm) => lm.line_index === lineId);
}

function wordIdsInLine(page: PagePayload, lineId: number): Array<[number, number]> {
  const line = findLine(page, lineId);
  if (!line) return [];
  return line.word_matches
    .filter((wm) => typeof wm.word_index === "number")
    .slice()
    .sort((a, b) => (a.word_index ?? 0) - (b.word_index ?? 0))
    .map((wm) => [line.line_index, wm.word_index as number] as [number, number]);
}

// ─── Sibling navigation ──────────────────────────────────────────────────────

function step<T>(list: T[], idx: number, dir: WalkDirection): T | undefined {
  if (idx < 0) return undefined;
  const next = dir === "next" ? idx + 1 : idx - 1;
  return list[next];
}

/**
 * Compute the path for the next sibling at the deepest level of `path`.
 *
 * If at the first/last sibling, returns the same path unchanged.
 */
export function nextSibling(
  path: SelectionPath,
  page: PagePayload,
  dir: WalkDirection,
): SelectionPath {
  if (path.wordId !== undefined) {
    const [lineIdx] = path.wordId;
    const words = wordIdsInLine(page, lineIdx);
    const idx = words.findIndex((w) => w[0] === path.wordId![0] && w[1] === path.wordId![1]);
    const next = step(words, idx, dir);
    if (!next) return path;
    return { ...path, wordId: next };
  }
  if (path.lineId !== undefined) {
    // Siblings of a line are lines in the same paragraph (or all lines if paraId undef).
    const paraId =
      path.paraId !== undefined
        ? path.paraId
        : (findLine(page, path.lineId)?.paragraph_index ?? null);
    const lines = path.paraId !== undefined ? linesInPara(page, paraId ?? null) : allLines(page);
    const idx = lines.findIndex((lm) => lm.line_index === path.lineId);
    const next = step(lines, idx, dir);
    if (!next) return path;
    return { ...path, lineId: next.line_index };
  }
  if (path.paraId !== undefined) {
    const ids = paraIds(page);
    const idx = ids.findIndex((p) => p === path.paraId);
    const next = step(ids, idx, dir);
    if (next === undefined) return path;
    return { ...path, paraId: next };
  }
  // block-level or none — no siblings to compute from the page payload.
  return path;
}

// ─── Vertical navigation (up/down hierarchy) ─────────────────────────────────

export function walkUp(path: SelectionPath, _page: PagePayload): SelectionPath {
  if (path.wordId !== undefined) {
    const { wordId: _w, ...rest } = path;
    return rest;
  }
  if (path.lineId !== undefined) {
    const { lineId: _l, ...rest } = path;
    return rest;
  }
  if (path.paraId !== undefined) {
    const { paraId: _p, ...rest } = path;
    return rest;
  }
  if (path.blockId !== undefined) {
    const { blockId: _b, ...rest } = path;
    return rest;
  }
  return path;
}

/**
 * Walk down one level into the first child of `path`.
 *
 * - Block → first paragraph (no block layer in payload; descends into paras).
 * - Para  → first line in that paragraph.
 * - Line  → first word in that line.
 * - Word  → unchanged (already a leaf).
 * - None  → first paragraph in the page.
 */
export function walkDown(path: SelectionPath, page: PagePayload): SelectionPath {
  if (path.wordId !== undefined) return path;
  if (path.lineId !== undefined) {
    const words = wordIdsInLine(page, path.lineId);
    if (words.length === 0) return path;
    return { ...path, wordId: words[0] };
  }
  if (path.paraId !== undefined) {
    const lines = linesInPara(page, path.paraId ?? null);
    if (lines.length === 0) return path;
    return { ...path, lineId: lines[0].line_index };
  }
  // From block or none: descend into first paragraph.
  const ids = paraIds(page);
  if (ids.length === 0) return path;
  return { ...path, paraId: ids[0] };
}

// ─── Level inference ─────────────────────────────────────────────────────────

/** Pick the deepest non-undefined level present in `path`. */
export function pathLevel(path: SelectionPath): SelectionLevel {
  if (path.wordId !== undefined) return "word";
  if (path.lineId !== undefined) return "line";
  if (path.paraId !== undefined) return "para";
  if (path.blockId !== undefined) return "block";
  return "none";
}

// selection-expand.ts — pure helper mapping PagePayload.selection (indices)
// to BBoxItem arrays for paragraph / line / word overlay layers.
//
// Spec: specs/21-konva-renderer.md §8
// Issue #299 (spec-21-A4)
//
// Pure module: no React imports. Out-of-range indices are skipped defensively
// and reported via `console.warn` so the caller (and developers) can spot
// stale selection state without throwing.
//
// Paragraph / line bboxes are not surfaced separately on the wire — the
// helper computes them as the axis-aligned union of constituent word
// bboxes joined from `PagePayload.line_matches`. This matches the legacy
// labeler's behaviour (see `pd-ocr-labeler/pd_ocr_labeler/views/projects/
// pages/image_tabs.py:678-737` `_apply_box_selection`).

import type { components } from "../api/types";
import type { BBoxItem } from "../components/BBoxOverlay";
import type { BBox } from "./coords";

type PagePayload = components["schemas"]["PagePayload"];
type LineMatch = components["schemas"]["LineMatch"];
type WordMatch = components["schemas"]["WordMatch"];

export interface ExpandedSelection {
  paragraphs: BBoxItem[];
  lines: BBoxItem[];
  words: BBoxItem[];
}

/** Axis-aligned union of one or more bboxes. Returns null when the list is empty. */
function unionBBoxes(bboxes: readonly BBox[]): BBox | null {
  if (bboxes.length === 0) return null;
  let xMin = Infinity;
  let yMin = Infinity;
  let xMax = -Infinity;
  let yMax = -Infinity;
  for (const b of bboxes) {
    if (b.x < xMin) xMin = b.x;
    if (b.y < yMin) yMin = b.y;
    const right = b.x + b.width;
    const bottom = b.y + b.height;
    if (right > xMax) xMax = right;
    if (bottom > yMax) yMax = bottom;
  }
  return {
    x: xMin,
    y: yMin,
    width: xMax - xMin,
    height: yMax - yMin,
  };
}

/**
 * Expand selection-store state (selectedWords/Lines/Paragraphs) into BBoxItem
 * arrays for each overlay layer — the SEL-1 replacement for `expandSelection`.
 *
 * Unlike `expandSelection` which reads from `page.selection` (server state),
 * this reads from the local selectionStore so highlights appear with no
 * network round-trip.
 *
 * Pure: no DOM, no React, no side effects other than `console.warn`.
 */
export function expandFromStore(
  storeState: {
    selectedParagraphs: number[];
    selectedLines: number[];
    selectedWords: [number, number][];
  },
  page: PagePayload,
): ExpandedSelection {
  // Build a synthetic selection object that matches the shape expandSelection reads.
  const syntheticPage: PagePayload = {
    ...page,
    selection: {
      selection_mode: "word",
      selected_paragraphs: storeState.selectedParagraphs,
      selected_lines: storeState.selectedLines,
      selected_words: storeState.selectedWords,
    },
  };
  return expandSelection(syntheticPage);
}

/**
 * Expand a `PagePayload.selection` into BBoxItem arrays for each overlay layer.
 *
 * Pure: no DOM, no React, no side effects other than `console.warn` for
 * out-of-range indices.
 */
export function expandSelection(page: PagePayload): ExpandedSelection {
  const result: ExpandedSelection = { paragraphs: [], lines: [], words: [] };

  const selection = page.selection;
  if (!selection) return result;

  const lineMatches: LineMatch[] = page.line_matches ?? [];

  // Index lines by line_index for O(1) word/line lookups. Distinct from
  // array position because a filtered payload could omit lines, though
  // current backend emits them in order.
  const linesByIndex = new Map<number, LineMatch>();
  for (const line of lineMatches) {
    linesByIndex.set(line.line_index, line);
  }

  // Paragraphs known to the payload (set of paragraph_index values that
  // appear on any LineMatch).
  const knownParagraphs = new Set<number>();
  for (const line of lineMatches) {
    if (line.paragraph_index !== null && line.paragraph_index !== undefined) {
      knownParagraphs.add(line.paragraph_index);
    }
  }

  // ─── Words ──────────────────────────────────────────────────────────────────
  for (const [lineIdx, wordIdx] of selection.selected_words ?? []) {
    const line = linesByIndex.get(lineIdx);
    if (!line) {
      console.warn(
        `[selection-expand] word (line=${lineIdx}, word=${wordIdx}) skipped: line_index ${lineIdx} not found in line_matches`,
      );
      continue;
    }
    const word = line.word_matches.find((w) => w.word_index === wordIdx);
    if (!word) {
      console.warn(
        `[selection-expand] word (line=${lineIdx}, word=${wordIdx}) skipped: word_index ${wordIdx} not found in line`,
      );
      continue;
    }
    result.words.push({
      id: `${lineIdx}-${wordIdx}`,
      bbox: word.bbox,
    });
  }

  // ─── Lines ──────────────────────────────────────────────────────────────────
  for (const lineIdx of selection.selected_lines ?? []) {
    const line = linesByIndex.get(lineIdx);
    if (!line) {
      console.warn(
        `[selection-expand] line index ${lineIdx} out of range (page has ${lineMatches.length} lines)`,
      );
      continue;
    }
    const wordBoxes = line.word_matches.map((w: WordMatch) => w.bbox);
    const bbox = unionBBoxes(wordBoxes);
    if (bbox === null) {
      // Line has no words → cannot derive a bbox. Silently skip; this is
      // a normal page-shape edge case, not a stale-selection bug.
      continue;
    }
    result.lines.push({ id: String(lineIdx), bbox });
  }

  // ─── Paragraphs ─────────────────────────────────────────────────────────────
  for (const paragraphIdx of selection.selected_paragraphs ?? []) {
    if (!knownParagraphs.has(paragraphIdx)) {
      console.warn(
        `[selection-expand] paragraph index ${paragraphIdx} out of range (page has paragraphs [${[
          ...knownParagraphs,
        ]
          .sort((a, b) => a - b)
          .join(", ")}])`,
      );
      continue;
    }
    const wordBoxes: BBox[] = [];
    for (const line of lineMatches) {
      if (line.paragraph_index !== paragraphIdx) continue;
      for (const word of line.word_matches) {
        wordBoxes.push(word.bbox);
      }
    }
    const bbox = unionBBoxes(wordBoxes);
    if (bbox === null) continue;
    result.paragraphs.push({ id: String(paragraphIdx), bbox });
  }

  return result;
}

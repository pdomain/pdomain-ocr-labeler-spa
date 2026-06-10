// box-select-handler.ts — SEL-2: onBoxSelect intersection math.
//
// Pure helper: given a PagePayload, a drag rect (display pixels), and a
// rail target, return the intersecting paragraph ids, line ids, or word
// tuples. Replace/toggle/remove semantics are applied by the caller.

import type { components } from "../api/types";
import type { BBox } from "./coords";
import type { SelectionModifier } from "../components/PageImageCanvas";
import { rectsOverlap } from "./bbox-select";
import type { RailTarget } from "../stores/rail-store";

type PagePayload = components["schemas"]["PagePayload"];
type LineMatch = components["schemas"]["LineMatch"];

export interface BoxSelectResult {
  paragraphs: number[];
  lines: number[];
  words: [number, number][];
}

function emptyResult(): BoxSelectResult {
  return { paragraphs: [], lines: [], words: [] };
}

function unionBBoxes(bboxes: readonly BBox[]): BBox | null {
  if (bboxes.length === 0) return null;
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const bbox of bboxes) {
    minX = Math.min(minX, bbox.x);
    minY = Math.min(minY, bbox.y);
    maxX = Math.max(maxX, bbox.x + bbox.width);
    maxY = Math.max(maxY, bbox.y + bbox.height);
  }
  return { x: minX, y: minY, width: maxX - minX, height: maxY - minY };
}

function toDisplayBbox(bbox: BBox, scale: number): BBox {
  return {
    x: bbox.x * scale,
    y: bbox.y * scale,
    width: bbox.width * scale,
    height: bbox.height * scale,
  };
}

function lineDisplayBbox(line: LineMatch, scale: number): BBox | null {
  const bbox = unionBBoxes(
    line.word_matches.map((word) => word.bbox).filter((bbox) => bbox.width > 0 && bbox.height > 0),
  );
  return bbox ? toDisplayBbox(bbox, scale) : null;
}

/**
 * Compute which page targets intersect the drag rect (display pixels).
 *
 * Words with `word_index === null` are skipped (not labelable items).
 * When `encoded_dims` is absent, source bbox coords are used directly as
 * display coords (scale = 1).
 *
 * The `modifier` parameter is accepted for API compatibility; callers apply
 * replace/toggle/remove semantics after this hit-test result is returned.
 */
export function applyBoxSelect(
  page: PagePayload,
  rect: BBox,
  _modifier: SelectionModifier,
  target: RailTarget = "word",
): BoxSelectResult {
  const scale = page.encoded_dims?.scale ?? 1;
  const lineMatches = page.line_matches ?? [];
  const result = emptyResult();

  if (target === "line") {
    for (const line of lineMatches) {
      const displayBbox = lineDisplayBbox(line, scale);
      if (displayBbox && rectsOverlap(displayBbox, rect)) {
        result.lines.push(line.line_index);
      }
    }
    return result;
  }

  if (target === "para" || target === "block") {
    const paragraphBoxes = new Map<number, BBox[]>();
    for (const line of lineMatches) {
      if (line.paragraph_index === null) continue;
      const boxes = paragraphBoxes.get(line.paragraph_index) ?? [];
      boxes.push(...line.word_matches.map((word) => word.bbox));
      paragraphBoxes.set(line.paragraph_index, boxes);
    }
    for (const [paragraphIndex, boxes] of paragraphBoxes) {
      const bbox = unionBBoxes(boxes);
      if (bbox && rectsOverlap(toDisplayBbox(bbox, scale), rect)) {
        result.paragraphs.push(paragraphIndex);
      }
    }
    return result;
  }

  for (const line of lineMatches) {
    for (const word of line.word_matches) {
      if (word.word_index === null) continue;
      const displayBbox = toDisplayBbox(word.bbox, scale);
      if (rectsOverlap(displayBbox, rect)) {
        result.words.push([line.line_index, word.word_index]);
      }
    }
  }

  return result;
}

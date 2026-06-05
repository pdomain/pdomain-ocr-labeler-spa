// box-select-handler.ts — SEL-2: onBoxSelect intersection math.
//
// Pure helper: given a PagePayload, a drag rect (display pixels), and a
// SelectionModifier, return the [lineIdx, wordIdx][] tuples for words
// whose display bboxes overlap the drag rect.
//
// REPLACE semantics only (Slice A). Toggle/remove accumulation is Slice B.

import type { components } from "../api/types";
import type { BBox } from "./coords";
import type { SelectionModifier } from "../components/PageImageCanvas";
import { rectsOverlap } from "./bbox-select";

type PagePayload = components["schemas"]["PagePayload"];

/**
 * Compute which words in `page` intersect the drag rect (display pixels)
 * and return their [lineIdx, wordIdx] tuples.
 *
 * Words with `word_index === null` are skipped (not labelable items).
 * When `encoded_dims` is absent, source bbox coords are used directly as
 * display coords (scale = 1).
 *
 * Only REPLACE semantics are implemented here (Slice A). The `modifier`
 * parameter is accepted for API forward-compat but ignored until Slice B
 * wires toggle/remove accumulation.
 */
export function applyBoxSelect(
  page: PagePayload,
  rect: BBox,
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  _modifier: SelectionModifier,
): [number, number][] {
  const scale = page.encoded_dims?.scale ?? 1;
  const result: [number, number][] = [];

  for (const line of page.line_matches ?? []) {
    for (const word of line.word_matches) {
      if (word.word_index === null) continue;
      const displayBbox: BBox = {
        x: word.bbox.x * scale,
        y: word.bbox.y * scale,
        width: word.bbox.width * scale,
        height: word.bbox.height * scale,
      };
      if (rectsOverlap(displayBbox, rect)) {
        result.push([line.line_index, word.word_index]);
      }
    }
  }

  return result;
}

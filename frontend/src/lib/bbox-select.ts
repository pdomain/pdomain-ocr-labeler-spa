// bbox-select.ts — Pure helper: target-scoped bbox intersection for drag-select.
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 13.
//
// Given a drag rect, a Rail target, and the page's bbox items per layer,
// returns only the items from the active target layer that intersect the rect.
//
// "Intersect" here means the bounding box overlaps the drag rect (not just
// point-in-rect). We use the AABB overlap test: two rects overlap iff they
// are NOT separated on either axis.

import type { RailTarget } from "../stores/rail-store";
import type { BBoxItem } from "../components/BBoxOverlay";
import type { BBox } from "./coords";

export type { RailTarget, BBoxItem, BBox };

/**
 * Test whether two axis-aligned bounding boxes overlap.
 *
 * Returns `true` when the rects share any area (touching edges count as
 * overlapping with width/height 0 overlap, but we accept that for UX).
 */
export function rectsOverlap(a: BBox, b: BBox): boolean {
  // No overlap if one rect is entirely to the left/right/above/below the other.
  if (a.x + a.width < b.x) return false;
  if (b.x + b.width < a.x) return false;
  if (a.y + a.height < b.y) return false;
  if (b.y + b.height < a.y) return false;
  return true;
}

/**
 * Map a RailTarget to the BBoxItem array key in the per-layer record.
 */
export function targetToLayerKey(target: RailTarget): "paragraphs" | "lines" | "words" {
  switch (target) {
    case "block":
      return "paragraphs"; // block maps to paragraph layer (closest available)
    case "para":
      return "paragraphs"; // para maps to paragraph layer
    case "line":
      return "lines";
    case "word":
      return "words";
  }
}

/**
 * Filter BBoxItems to those whose bboxes overlap the drag rect.
 */
export function intersectBboxes(items: BBoxItem[], dragRect: BBox): BBoxItem[] {
  return items.filter((item) => rectsOverlap(item.bbox, dragRect));
}

/**
 * Target-scoped drag-select.
 *
 * Given the active Rail target and a record of BBoxItems per layer,
 * returns only the items from the active layer that intersect the drag rect.
 *
 * @param target   - active Rail target ("block" | "line" | "word")
 * @param layers   - per-layer BBoxItem arrays
 * @param dragRect - the drag rectangle in display pixels
 */
export function selectByTarget(
  target: RailTarget,
  layers: { paragraphs: BBoxItem[]; lines: BBoxItem[]; words: BBoxItem[] },
  dragRect: BBox,
): BBoxItem[] {
  const key = targetToLayerKey(target);
  return intersectBboxes(layers[key], dragRect);
}

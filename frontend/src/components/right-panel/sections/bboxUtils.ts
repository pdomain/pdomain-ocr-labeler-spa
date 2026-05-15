// bboxUtils.ts — Utility functions for BBoxSection (P3.a Gap 33).
// Kept in a separate file so BBoxSection.tsx only exports React components,
// satisfying the react-refresh/only-export-components ESLint rule.

import type { components } from "../../../api/types";

type BBox = components["schemas"]["BBox"];

/**
 * Format a bbox as a coordinate-readout string for the AccordionTrigger hint.
 * Shows "x,y → x2,y2" so users can read coords without opening the accordion.
 */
export function bboxHint(bbox: BBox): string {
  const x2 = bbox.x + bbox.width;
  const y2 = bbox.y + bbox.height;
  return `${bbox.x},${bbox.y} → ${x2},${y2}`;
}

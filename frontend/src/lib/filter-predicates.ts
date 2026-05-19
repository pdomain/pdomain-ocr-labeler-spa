// filter-predicates.ts — Pure filter predicates for word-match lists.
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 11.
//
// Extracted from FilterToggle.tsx so the Worklist and other consumers can
// share the filter logic without importing a React component.
//
// FilterToggle is marked legacy and retains its own useSyncExternalStore
// bridge for backwards compat.

import type { components } from "../api/types";
import type { MatchFilter } from "../stores/ui-prefs";

export type LineMatch = components["schemas"]["LineMatch"];

/**
 * Returns true when the line should be shown under the given MatchFilter.
 *
 * Mirrors legacy `pd-ocr-labeler` filter values
 * (`word_match_renderer.py:_filter_lines_for_display`):
 *   - "unvalidated" → only lines where `!is_fully_validated`
 *   - "mismatched"  → only lines containing any non-exact word match
 *   - "all"         → no filtering
 */
function linePassesFilter(line: LineMatch, filter: MatchFilter): boolean {
  switch (filter) {
    case "unvalidated":
      return !line.is_fully_validated;
    case "mismatched":
      return line.mismatch_count > 0 || line.unmatched_gt_count > 0 || line.unmatched_ocr_count > 0;
    case "all":
      return true;
  }
}

/**
 * Filter an array of LineMatch items by the given MatchFilter.
 * Convenience wrapper around `linePassesFilter`.
 */
export function filterLines(lines: LineMatch[], filter: MatchFilter): LineMatch[] {
  if (filter === "all") return lines;
  return lines.filter((l) => linePassesFilter(l, filter));
}

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
 *   - "unvalidated" → only lines with >=1 unvalidated word (D4). Derived from
 *     the words' validation state so it stays correct even when the line-level
 *     `is_fully_validated` flag is stale/missing; falls back to the
 *     validated/total counts, then the flag, when word data isn't present.
 *   - "mismatched"  → only lines containing any non-exact word match
 *   - "all"         → no filtering
 */
function hasUnvalidatedWord(line: LineMatch): boolean {
  const words = line.word_matches ?? [];
  // Word data is authoritative in BOTH directions when present. If we have
  // words, derive the answer directly from their validation state — this stays
  // correct even when the line-level is_fully_validated flag is stale/missing.
  if (words.length > 0) return words.some((w) => !w.is_validated);
  // No word data: fall back to the line-level flag (explicit signal), then the
  // validated/total counts.
  if (line.is_fully_validated !== undefined && line.is_fully_validated !== null) {
    return !line.is_fully_validated;
  }
  if (line.total_word_count !== undefined && line.validated_word_count !== undefined) {
    return line.validated_word_count < line.total_word_count;
  }
  return false;
}

function linePassesFilter(line: LineMatch, filter: MatchFilter): boolean {
  switch (filter) {
    case "unvalidated":
      return hasUnvalidatedWord(line);
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

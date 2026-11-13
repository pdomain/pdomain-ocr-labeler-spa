import type { components } from "../api/types";
import type { MatchFilter } from "../stores/ui-prefs";
type LineMatch = components["schemas"]["LineMatch"];
type WordMatch = components["schemas"]["WordMatch"];

export function lineMatchesFilter(line: LineMatch, filter: MatchFilter): boolean {
  if (filter === "all") return true;
  if (filter === "unvalidated") return !line.is_fully_validated;
  // "mismatched" — any word_match whose status != exact qualifies.
  return line.word_matches.some((wm: WordMatch) => wm.match_status !== "exact");
}

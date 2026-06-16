// WordHeader.tsx — Identity strip rendered above the accordion sections (P2.a, Gap 28).
//
// Shows:
//   - Mono-font ID label: "Line N · Word N" (1-based)
//   - StatusPip showing validation state
//   - Per-word inline pager: ◀ ▶ buttons for prev/next word in same line
//
// data-testids:
//   word-header             — outer container
//   word-header-id          — "Line N · Word N" label
//   word-header-prev        — ◀ prev-word button
//   word-header-next        — ▶ next-word button

import { StatusPip } from "@pdomain/pdomain-ui/primitives";
import type { components } from "../../api/types";

type WordMatch = components["schemas"]["WordMatch"];
type MatchStatus = components["schemas"]["MatchStatus"];

export interface WordHeaderProps {
  word: WordMatch;
  /** Whether a previous word exists in the same line. */
  hasPrev: boolean;
  /** Whether a next word exists in the same line. */
  hasNext: boolean;
  onPrev: () => void;
  onNext: () => void;
}

function matchToStatus(status: MatchStatus): "exact" | "fuzzy" | "mismatch" {
  if (status === "exact") return "exact";
  if (status === "fuzzy") return "fuzzy";
  return "mismatch";
}

export function WordHeader({ word, hasPrev, hasNext, onPrev, onNext }: WordHeaderProps) {
  const lineNum = word.line_index + 1;
  const wordNum = (word.word_index ?? 0) + 1;

  return (
    <div
      data-testid="word-header"
      className="flex items-center justify-between gap-2 px-3 py-2 border-b border-border-1 bg-bg-raised"
    >
      {/* ID label */}
      <span
        data-testid="word-header-id"
        className="font-mono text-[11px] text-ink-1 truncate shrink"
      >
        Line {lineNum} · Word {wordNum}
      </span>

      <div className="flex items-center gap-2 shrink-0">
        {/* Validation status pip */}
        <StatusPip
          status={matchToStatus(word.match_status)}
          {...(word.is_validated ? { label: "✓" } : {})}
        />

        {/* Word pager */}
        <div className="flex items-center gap-0.5">
          <button
            type="button"
            data-testid="word-header-prev"
            aria-label="Previous word"
            disabled={!hasPrev}
            onClick={onPrev}
            className="w-6 h-6 flex items-center justify-center rounded text-[11px] text-ink-2 hover:bg-bg-sunk disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            ◀
          </button>
          <button
            type="button"
            data-testid="word-header-next"
            aria-label="Next word"
            disabled={!hasNext}
            onClick={onNext}
            className="w-6 h-6 flex items-center justify-center rounded text-[11px] text-ink-2 hover:bg-bg-sunk disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            ▶
          </button>
        </div>
      </div>
    </div>
  );
}

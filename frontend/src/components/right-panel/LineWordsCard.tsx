// LineWordsCard.tsx — Per-word card inside the LineDetail Words tab.
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md P5.f (Gaps 44, 45).
//
// Shows: serif preview placeholder + OCR text / GT text stacked +
// per-word checkbox for bulk selection.
//
// data-testids:
//   line-words-card-{wordIndex}          — card outer
//   line-words-card-checkbox-{wordIndex} — bulk selection checkbox

import type { components } from "../../api/types";
import { StatusPip } from "../ui/StatusPip";

type WordMatch = components["schemas"]["WordMatch"];
type MatchStatus = components["schemas"]["MatchStatus"];

// Cast MatchStatus to StatusPip-compatible status.
function pipStatus(status: MatchStatus): "exact" | "fuzzy" | "mismatch" {
  if (status === "exact") return "exact";
  if (status === "fuzzy") return "fuzzy";
  return "mismatch";
}

interface LineWordsCardProps {
  word: WordMatch;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
}

export function LineWordsCard({ word, checked, onCheckedChange }: LineWordsCardProps) {
  const pip = pipStatus(word.match_status);
  const hasDiff = word.ground_truth_text && word.ground_truth_text !== word.ocr_text;
  const wordNum = (word.word_index ?? 0) + 1;

  return (
    <div
      data-testid={`line-words-card-${word.word_index}`}
      className="flex items-start gap-2 bg-bg-raised rounded px-2 py-1.5"
    >
      {/* Bulk selection checkbox */}
      <input
        type="checkbox"
        data-testid={`line-words-card-checkbox-${word.word_index}`}
        checked={checked}
        onChange={(e) => {
          onCheckedChange(e.target.checked);
        }}
        aria-label={`Select word ${wordNum}`}
        className="mt-0.5 accent-accent flex-shrink-0"
      />

      {/* Serif preview placeholder (word image would go here when available) */}
      <div className="w-12 h-8 bg-bg-surface rounded flex items-center justify-center flex-shrink-0 border border-border-1">
        <span className="text-[11px] text-ink-3 italic font-serif truncate px-0.5">
          {word.ocr_text || "·"}
        </span>
      </div>

      {/* OCR + GT stack */}
      <div className="flex-1 min-w-0 flex flex-col gap-0.5">
        <div className="flex items-center gap-1.5">
          <StatusPip status={pip} />
          <span className="font-mono text-[10px] text-ink-3">
            W-{String(wordNum).padStart(3, "0")}
          </span>
        </div>
        <span className="text-[11px] font-mono text-ink-1 truncate">
          {word.ocr_text || <span className="text-ink-4 italic">∅</span>}
        </span>
        {hasDiff && (
          <span className="text-[10px] font-mono text-status-fuzzy truncate">
            → {word.ground_truth_text}
          </span>
        )}
      </div>
    </div>
  );
}

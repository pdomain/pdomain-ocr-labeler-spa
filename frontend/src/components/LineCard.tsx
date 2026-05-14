// LineCard.tsx — collapsible card showing OCR-vs-GT comparison for one line.
//
// Spec: docs/specs/2026-05-12-word-matches-design.md §LineCard header
// Issues #201, #202
//
// Header background by overall_match_status:
//   exact         → bg-green-100
//   fuzzy         → bg-yellow-100
//   mismatch      → bg-red-100
//   unmatched_ocr → bg-gray-100
//   unmatched_gt  → bg-blue-100
//
// Count chips render only for nonzero counts.
// Validate / Unvalidate button flips based on is_fully_validated.
//
// data-testids:
//   line-card-{line_index}
//   line-card-{line_index}-header
//   line-validate-btn
//   count-chip-exact / count-chip-fuzzy / count-chip-mismatch /
//   count-chip-unmatched_gt / count-chip-unmatched_ocr

import type { components } from "../api/types";

type LineMatch = components["schemas"]["LineMatch"];
type MatchStatus = components["schemas"]["MatchStatus"];

const STATUS_BG: Record<MatchStatus, string> = {
  exact: "bg-green-100",
  fuzzy: "bg-yellow-100",
  mismatch: "bg-red-100",
  unmatched_ocr: "bg-gray-100",
  unmatched_gt: "bg-blue-100",
};

interface CountChipProps {
  kind: "exact" | "fuzzy" | "mismatch" | "unmatched_gt" | "unmatched_ocr";
  count: number;
  label: string;
  colorClass: string;
}

function CountChip({ kind, count, label, colorClass }: CountChipProps) {
  if (count === 0) return null;
  return (
    <span
      data-testid={`count-chip-${kind}`}
      className={`px-1.5 py-0.5 text-xs font-medium rounded ${colorClass}`}
      title={`${count} ${label}`}
    >
      {count}
    </span>
  );
}

export interface LineCardProps {
  line: LineMatch;
  /** Called when Validate / Unvalidate is clicked. */
  onValidate?: (lineIndex: number, validated: boolean) => void;
  /** Called when GT→OCR copy is clicked. */
  onCopyGtToOcr?: (lineIndex: number) => void;
  /** Called when OCR→GT copy is clicked. */
  onCopyOcrToGt?: (lineIndex: number) => void;
  /** Called when Delete is clicked. */
  onDelete?: (lineIndex: number) => void;
}

/**
 * Single line comparison card.
 *
 * Header background is derived from `overall_match_status`.
 * Count chips are rendered only for nonzero values.
 * Validate/Unvalidate label flips based on `is_fully_validated`.
 */
export function LineCard({
  line,
  onValidate,
  onCopyGtToOcr,
  onCopyOcrToGt,
  onDelete,
}: LineCardProps) {
  const bgClass = STATUS_BG[line.overall_match_status] ?? "bg-gray-50";
  const isExact = line.overall_match_status === "exact";

  return (
    <div
      data-testid={`line-card-${line.line_index}`}
      className="border border-gray-200 rounded mb-1 overflow-hidden"
    >
      {/* Header */}
      <div
        data-testid={`line-card-${line.line_index}-header`}
        className={`flex items-center gap-1 px-2 py-1 ${bgClass}`}
      >
        {/* Count chips */}
        <div className="flex items-center gap-0.5 flex-1">
          <CountChip
            kind="exact"
            count={line.exact_count}
            label="exact"
            colorClass="bg-green-200 text-green-800"
          />
          <CountChip
            kind="fuzzy"
            count={line.fuzzy_count}
            label="fuzzy"
            colorClass="bg-yellow-200 text-yellow-800"
          />
          <CountChip
            kind="mismatch"
            count={line.mismatch_count}
            label="mismatch"
            colorClass="bg-red-200 text-red-800"
          />
          <CountChip
            kind="unmatched_gt"
            count={line.unmatched_gt_count}
            label="unmatched GT"
            colorClass="bg-blue-200 text-blue-800"
          />
          <CountChip
            kind="unmatched_ocr"
            count={line.unmatched_ocr_count}
            label="unmatched OCR"
            colorClass="bg-gray-200 text-gray-800"
          />
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-1 shrink-0">
          {/* GT→OCR / OCR→GT: hidden when exact */}
          {!isExact && (
            <>
              <button
                data-testid={`line-card-${line.line_index}-gt-to-ocr`}
                className="px-1.5 py-0.5 text-xs border border-gray-300 rounded bg-white hover:bg-gray-50"
                onClick={() => onCopyGtToOcr?.(line.line_index)}
                title="Copy GT to OCR"
              >
                GT→OCR
              </button>
              <button
                data-testid={`line-card-${line.line_index}-ocr-to-gt`}
                className="px-1.5 py-0.5 text-xs border border-gray-300 rounded bg-white hover:bg-gray-50"
                onClick={() => onCopyOcrToGt?.(line.line_index)}
                title="Copy OCR to GT"
              >
                OCR→GT
              </button>
            </>
          )}

          <button
            data-testid="line-validate-btn"
            className="px-1.5 py-0.5 text-xs border border-gray-300 rounded bg-white hover:bg-gray-50"
            onClick={() => onValidate?.(line.line_index, !line.is_fully_validated)}
          >
            {line.is_fully_validated ? "Unvalidate" : "Validate"}
          </button>

          <button
            data-testid={`line-card-${line.line_index}-delete`}
            className="px-1.5 py-0.5 text-xs border border-red-300 text-red-600 rounded bg-white hover:bg-red-50"
            onClick={() => onDelete?.(line.line_index)}
            title="Delete line"
          >
            Delete
          </button>
        </div>
      </div>

      {/* OCR text preview */}
      <div className="px-2 py-1 text-xs font-mono text-gray-600 bg-white truncate">
        {line.ocr_line_text || <span className="text-gray-400 italic">(empty)</span>}
      </div>
    </div>
  );
}

// WordMatchView.tsx — virtualised list of LineCard rows for the word-match pane.
//
// Spec: docs/specs/2026-05-12-word-matches-design.md §Virtualisation
// Spec: specs/22-page-surface-wireup.md §8 (FilterToggle plumbing)
// Issues #201, #312
//
// Uses @tanstack/react-virtual with:
//   estimateSize: () => 80  (initial estimate; measureElement refines)
//   overscan: 3
//
// Only visible cards plus overscan mount in the DOM.
//
// data-testids:
//   word-match-view   — scroll container
//   word-match-empty  — shown when lines array is empty (after filtering)

import { useMemo, useRef } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import type { components } from "../api/types";
import { LineCard } from "./LineCard";
import type { MatchFilter } from "../stores/ui-prefs";

type LineMatch = components["schemas"]["LineMatch"];
type WordMatch = components["schemas"]["WordMatch"];

/**
 * Decide whether a line should render for the given filter mode.
 *
 * Mirrors legacy `pd-ocr-labeler/pd_ocr_labeler/views/projects/pages/
 * word_match_renderer.py:_filter_lines_for_display`:
 *   - "all"         → keep everything
 *   - "unvalidated" → keep lines where `!is_fully_validated`
 *   - "mismatched"  → keep lines containing any non-exact word match
 */
export function lineMatchesFilter(line: LineMatch, filter: MatchFilter): boolean {
  if (filter === "all") return true;
  if (filter === "unvalidated") return !line.is_fully_validated;
  // "mismatched" — any word_match whose status != exact qualifies.
  return line.word_matches.some((wm: WordMatch) => wm.match_status !== "exact");
}

export interface WordMatchViewProps {
  lines: LineMatch[];
  /**
   * Optional filter mode (spec 22 §8). When omitted, defaults to "all"
   * (back-compat with callers from #201). The FilterToggle component
   * subscribes to `useUiPrefs.matchFilter` and forwards the value here.
   */
  filter?: MatchFilter;
  /** Called when Validate / Unvalidate is clicked. */
  onValidate?: (lineIndex: number, validated: boolean) => void;
  /** Called when GT→OCR copy is clicked. */
  onCopyGtToOcr?: (lineIndex: number) => void;
  /** Called when OCR→GT copy is clicked. */
  onCopyOcrToGt?: (lineIndex: number) => void;
  /** Called when Delete is clicked. */
  onDelete?: (lineIndex: number) => void;
  /**
   * Called when a word's GT input is blurred and the value changed.
   * Forwarded to each LineCard → WordCell.
   * Signature: (wordId, lineIndex, wordIndex, newText) => void
   */
  onCommitGt?: (wordId: string, lineIndex: number, wordIndex: number, text: string) => void;
  /**
   * Called when the edit-word pencil button is clicked on a word row.
   * Forwarded to each LineCard → WordCell.
   * Signature: (lineIndex, wordIndex) => void
   */
  onEditWord?: (lineIndex: number, wordIndex: number) => void;
  /**
   * Base URL for page image slices.
   * Forwarded to each LineCard → WordCell for optional crop thumbnails.
   */
  imageBaseUrl?: string;
}

/**
 * Virtualised list of LineCard rows.
 *
 * Renders only the visible slice of the `lines` array using
 * `@tanstack/react-virtual`, so pages with 200+ lines don't mount
 * all cards at once.
 *
 * Scroll container: the outermost div (data-testid="word-match-view").
 */
export function WordMatchView({
  lines,
  filter = "all",
  onValidate,
  onCopyGtToOcr,
  onCopyOcrToGt,
  onDelete,
  onCommitGt,
  onEditWord,
  imageBaseUrl,
}: WordMatchViewProps) {
  const parentRef = useRef<HTMLDivElement>(null);

  // Spec 22 §8: filter lines before virtualisation so excluded rows
  // don't consume virtualiser slots (which would leave gaps in the scroll).
  const visibleLines = useMemo(
    () => (filter === "all" ? lines : lines.filter((line) => lineMatchesFilter(line, filter))),
    [lines, filter],
  );

  const virtualizer = useVirtualizer({
    count: visibleLines.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 80,
    overscan: 3,
    // measureElement lets the virtualiser refine heights after first render.
    // Omit on server (no DOM) — exactOptionalPropertyTypes disallows explicit undefined.
    ...(typeof window !== "undefined"
      ? { measureElement: (el: Element) => el.getBoundingClientRect().height }
      : {}),
  });

  const items = virtualizer.getVirtualItems();
  const totalSize = virtualizer.getTotalSize();

  // Compute which lines are the first in their paragraph (driver-contract §2.8).
  // A line is paragraph-first when its paragraph_index is not null and hasn't
  // been seen yet in the visible list.
  const paragraphFirstSet = useMemo(() => {
    const seen = new Set<number>();
    const result = new Set<number>();
    for (const line of visibleLines) {
      if (line.paragraph_index !== null && !seen.has(line.paragraph_index)) {
        seen.add(line.paragraph_index);
        result.add(line.line_index);
      }
    }
    return result;
  }, [visibleLines]);

  if (visibleLines.length === 0) {
    return (
      <div
        data-testid="word-match-view"
        role="region"
        aria-label="Word matches"
        className="flex-1 flex items-center justify-center text-sm text-ink-4 p-4"
      >
        <span data-testid="word-match-empty">No lines to display.</span>
      </div>
    );
  }

  return (
    <div
      ref={parentRef}
      data-testid="word-match-view"
      role="region"
      aria-label="Word matches"
      className="flex-1 overflow-auto"
      style={{ contain: "strict" }}
    >
      {/* Total-size spacer — required by react-virtual for correct scrollbar */}
      <div style={{ height: totalSize, width: "100%", position: "relative" }}>
        {items.map((virtualRow) => {
          // virtualRow.index is always within visibleLines bounds (virtualizer contract).
          const line = visibleLines[virtualRow.index]!;
          return (
            <div
              key={virtualRow.key}
              data-index={virtualRow.index}
              ref={virtualizer.measureElement}
              style={{
                position: "absolute",
                top: 0,
                left: 0,
                width: "100%",
                transform: `translateY(${virtualRow.start}px)`,
              }}
            >
              <LineCard
                line={line}
                paragraphFirst={paragraphFirstSet.has(line.line_index)}
                onValidate={onValidate}
                onCopyGtToOcr={onCopyGtToOcr}
                onCopyOcrToGt={onCopyOcrToGt}
                onDelete={onDelete}
                onCommitGt={onCommitGt}
                onEditWord={onEditWord}
                imageBaseUrl={imageBaseUrl}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}

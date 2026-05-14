// WordMatchView.tsx — virtualised list of LineCard rows for the word-match pane.
//
// Spec: docs/specs/2026-05-12-word-matches-design.md §Virtualisation
// Issue #201
//
// Uses @tanstack/react-virtual with:
//   estimateSize: () => 80  (initial estimate; measureElement refines)
//   overscan: 3
//
// Only visible cards plus overscan mount in the DOM.
//
// data-testids:
//   word-match-view   — scroll container
//   word-match-empty  — shown when lines array is empty

import { useRef } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import type { components } from "../api/types";
import { LineCard } from "./LineCard";

type LineMatch = components["schemas"]["LineMatch"];

export interface WordMatchViewProps {
  lines: LineMatch[];
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
  onValidate,
  onCopyGtToOcr,
  onCopyOcrToGt,
  onDelete,
}: WordMatchViewProps) {
  const parentRef = useRef<HTMLDivElement>(null);

  const virtualizer = useVirtualizer({
    count: lines.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 80,
    overscan: 3,
    // measureElement lets the virtualiser refine heights after first render.
    measureElement:
      typeof window !== "undefined" ? (el) => el.getBoundingClientRect().height : undefined,
  });

  const items = virtualizer.getVirtualItems();
  const totalSize = virtualizer.getTotalSize();

  if (lines.length === 0) {
    return (
      <div
        data-testid="word-match-view"
        className="flex-1 flex items-center justify-center text-sm text-gray-400 p-4"
      >
        <span data-testid="word-match-empty">No lines to display.</span>
      </div>
    );
  }

  return (
    <div
      ref={parentRef}
      data-testid="word-match-view"
      className="flex-1 overflow-auto"
      style={{ contain: "strict" }}
    >
      {/* Total-size spacer — required by react-virtual for correct scrollbar */}
      <div style={{ height: totalSize, width: "100%", position: "relative" }}>
        {items.map((virtualRow) => {
          const line = lines[virtualRow.index];
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
                onValidate={onValidate}
                onCopyGtToOcr={onCopyGtToOcr}
                onCopyOcrToGt={onCopyOcrToGt}
                onDelete={onDelete}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}

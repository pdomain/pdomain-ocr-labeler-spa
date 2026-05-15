// Worklist.tsx — Worklist tab inside the Drawer panel.
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 11.
//
// Shows filter chip row (Unvalidated / Mismatched / All) and a queue of
// line matches with StatusPip + label. State lives in worklist-store.
// Filter chips use Chip variant="static"; their selection drives
// worklistStore.activeFilter.

import { useSyncExternalStore } from "react";
import type { components } from "../../api/types";
import { cn } from "@/lib/utils";
import { worklistStore, type MatchFilter } from "../../stores/worklist-store";
import { filterLines } from "../../lib/filter-predicates";
import { StatusPip } from "../ui/StatusPip";

type LineMatch = components["schemas"]["LineMatch"];
type MatchStatus = components["schemas"]["MatchStatus"];

// ─── Filter chip helpers ───────────────────────────────────────────────────

interface FilterOption {
  value: MatchFilter;
  label: string;
  testid: string;
}

const FILTER_OPTIONS: FilterOption[] = [
  { value: "unvalidated", label: "Unvalidated", testid: "worklist-filter-unvalidated" },
  { value: "mismatched", label: "Mismatched", testid: "worklist-filter-mismatched" },
  { value: "all", label: "All", testid: "worklist-filter-all" },
];

/** Map MatchStatus → StatusPip status (best approximation). */
function statusForLine(status: MatchStatus): "exact" | "fuzzy" | "mismatch" {
  if (status === "exact") return "exact";
  if (status === "fuzzy") return "fuzzy";
  return "mismatch";
}

// ─── Component ────────────────────────────────────────────────────────────────

export interface WorklistProps {
  /** Page line matches to display. Pass undefined when page not loaded. */
  lineMatches?: LineMatch[];
}

export function Worklist({ lineMatches = [] }: WorklistProps) {
  // Subscribe to worklist store for reactive re-renders.
  const state = useSyncExternalStore(
    worklistStore.subscribe,
    worklistStore.getState,
    worklistStore.getState,
  );

  const { activeFilter, selectedLineIndex } = state;

  // Apply filter predicate to reduce the queue.
  const filtered = filterLines(lineMatches, activeFilter);

  return (
    <div data-testid="worklist" className="flex flex-col h-full">
      {/* Filter chip row */}
      <div
        data-testid="worklist-filter-row"
        className="flex gap-1 p-2 border-b border-border-1 flex-shrink-0"
      >
        {FILTER_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            type="button"
            data-testid={opt.testid}
            data-active={activeFilter === opt.value ? "true" : undefined}
            onClick={() => worklistStore.setActiveFilter(opt.value)}
            className={cn(
              "text-[11px] px-2 py-0.5 rounded-full border transition-colors select-none",
              activeFilter === opt.value
                ? "bg-accent text-accent-ink border-accent"
                : "bg-bg-raised text-ink-2 border-border-2 hover:border-accent hover:text-ink-1",
            )}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {/* Queue list */}
      <div
        data-testid="worklist-queue"
        className="flex-1 overflow-y-auto"
        role="listbox"
        aria-label="Line worklist queue"
      >
        {filtered.length === 0 ? (
          <div className="text-ink-3 text-[11px] p-3 text-center">
            No lines match current filter
          </div>
        ) : (
          filtered.map((line) => {
            const isSelected = selectedLineIndex === line.line_index;
            return (
              <button
                key={line.line_index}
                type="button"
                role="option"
                data-testid={`worklist-row-${line.line_index}`}
                data-selected={isSelected ? "true" : undefined}
                aria-selected={isSelected}
                onClick={() => worklistStore.setSelectedLineIndex(line.line_index)}
                className={cn(
                  "w-full flex items-center gap-2 px-3 py-1.5 text-left text-[11px] transition-colors",
                  isSelected
                    ? "bg-bg-raised text-ink-1"
                    : "text-ink-2 hover:bg-bg-raised/60 hover:text-ink-1",
                )}
              >
                <StatusPip status={statusForLine(line.overall_match_status)} />
                <span className="flex-1 truncate font-mono">
                  {line.ocr_line_text || `Line ${line.line_index + 1}`}
                </span>
                <span className="text-ink-3 text-[10px] tabular-nums">{line.line_index + 1}</span>
              </button>
            );
          })
        )}
      </div>
    </div>
  );
}

// Worklist.tsx — Worklist tab inside the Drawer panel.
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 11, P5.a, P5.b.
//
// P5.a (Gap 20): each row shows a 4px color bar + mono ID stamp + status pip +
//   confidence % + OCR→GT diff (inline or two-line).
// P5.b (Gap 19): status-count chip row + sort dropdown replace the original
//   active-filter selector.
//
// Regression guard: drawer width must remain 320px (Gap 17 — done).

import { useSyncExternalStore } from "react";
import type { components } from "../../api/types";
import { cn } from "@/lib/utils";
import { worklistStore, type MatchFilter, type WorklistSort } from "../../stores/worklist-store";
import { selectLine } from "../../stores/selection-store";
import { filterLines } from "../../lib/filter-predicates";
import { StatusPip } from "../ui/StatusPip";
import { BulkActions } from "./BulkActions";

type LineMatch = components["schemas"]["LineMatch"];
type MatchStatus = components["schemas"]["MatchStatus"];

// ─── Status color bar (4px left accent, P5.a) ─────────────────────────────

const STATUS_BAR_CLASS: Record<"exact" | "fuzzy" | "mismatch", string> = {
  exact: "bg-status-exact",
  fuzzy: "bg-status-fuzzy",
  mismatch: "bg-status-mismatch",
};

/** Map MatchStatus → pip status. */
function pipStatus(status: MatchStatus): "exact" | "fuzzy" | "mismatch" {
  if (status === "exact") return "exact";
  if (status === "fuzzy") return "fuzzy";
  return "mismatch";
}

/** Confidence percentage from validated / total (0–100). */
function confidencePct(line: LineMatch): number {
  if (!line.total_word_count) return 0;
  return Math.round((line.validated_word_count / line.total_word_count) * 100);
}

// ─── OCR→GT diff helpers (P5.a) ───────────────────────────────────────────

/** Returns true when ocr and gt differ (ignoring undefined/null). */
function hasDiff(ocr: string | null | undefined, gt: string | null | undefined): boolean {
  const o = ocr ?? "";
  const g = gt ?? "";
  return o !== g && (o.length > 0 || g.length > 0);
}

// ─── Sort helpers (P5.b) ──────────────────────────────────────────────────

const SORT_OPTIONS: { value: WorklistSort; label: string }[] = [
  { value: "index", label: "By ID" },
  { value: "confidence", label: "By confidence" },
  { value: "status", label: "By status" },
];

const STATUS_SORT_ORDER: Record<MatchStatus, number> = {
  mismatch: 0,
  fuzzy: 1,
  unmatched_gt: 2,
  unmatched_ocr: 3,
  exact: 4,
};

function sortLines(lines: LineMatch[], sort: WorklistSort): LineMatch[] {
  if (sort === "index") return lines;
  const copy = [...lines];
  if (sort === "confidence") {
    copy.sort((a, b) => confidencePct(a) - confidencePct(b));
  } else if (sort === "status") {
    copy.sort(
      (a, b) =>
        (STATUS_SORT_ORDER[a.overall_match_status] ?? 99) -
        (STATUS_SORT_ORDER[b.overall_match_status] ?? 99),
    );
  }
  return copy;
}

// ─── Count chips (P5.b) ───────────────────────────────────────────────────

interface StatusCounts {
  all: number;
  validated: number;
  unvalidated: number;
  error: number;
}

function computeCounts(lines: LineMatch[]): StatusCounts {
  let validated = 0;
  let unvalidated = 0;
  let error = 0;
  for (const l of lines) {
    if (l.overall_match_status === "mismatch") {
      error++;
    } else if (l.is_fully_validated) {
      validated++;
    } else {
      unvalidated++;
    }
  }
  return { all: lines.length, validated, unvalidated, error };
}

interface CountChipProps {
  label: string;
  count: number;
  active: boolean;
  testid: string;
  onClick: () => void;
}

function CountChip({ label, count, active, testid, onClick }: CountChipProps) {
  return (
    <button
      type="button"
      data-testid={testid}
      data-active={active ? "true" : undefined}
      onClick={onClick}
      className={cn(
        "flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full border transition-colors select-none whitespace-nowrap",
        active
          ? "bg-accent text-accent-ink border-accent"
          : "bg-bg-raised text-ink-2 border-border-2 hover:border-accent hover:text-ink-1",
      )}
    >
      <span>{label}</span>
      <span
        className={cn(
          "rounded-full px-1 font-mono tabular-nums",
          active ? "bg-accent-ink/20" : "bg-border-2/60",
        )}
      >
        {count}
      </span>
    </button>
  );
}

// ─── Filter row (P5.b) ────────────────────────────────────────────────────

interface FilterRowProps {
  counts: StatusCounts;
  activeFilter: MatchFilter;
  sort: WorklistSort;
  onFilter: (f: MatchFilter) => void;
  onSort: (s: WorklistSort) => void;
}

function FilterRow({ counts, activeFilter, sort, onFilter, onSort }: FilterRowProps) {
  return (
    <div
      data-testid="worklist-filter-row"
      className="flex flex-col gap-1.5 p-2 border-b border-border-1 flex-shrink-0"
    >
      {/* Status-count chip row */}
      <div className="flex gap-1 flex-wrap">
        <CountChip
          testid="worklist-filter-all"
          label="All"
          count={counts.all}
          active={activeFilter === "all"}
          onClick={() => onFilter("all")}
        />
        <CountChip
          testid="worklist-filter-unvalidated"
          label="Unvalidated"
          count={counts.unvalidated}
          active={activeFilter === "unvalidated"}
          onClick={() => onFilter("unvalidated")}
        />
        <CountChip
          testid="worklist-filter-mismatched"
          label="Error"
          count={counts.error}
          active={activeFilter === "mismatched"}
          onClick={() => onFilter("mismatched")}
        />
      </div>

      {/* Sort dropdown */}
      <div className="flex items-center gap-1.5">
        <span className="text-[10px] text-ink-3 flex-shrink-0">Sort:</span>
        <select
          data-testid="worklist-sort-select"
          value={sort}
          onChange={(e) => onSort(e.target.value as WorklistSort)}
          className="text-[10px] bg-bg-raised border border-border-2 rounded px-1 py-0.5 text-ink-2 hover:border-accent focus:outline-none focus:border-accent transition-colors"
        >
          {SORT_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}

// ─── Row (P5.a) ───────────────────────────────────────────────────────────

interface WorklistRowProps {
  line: LineMatch;
  isSelected: boolean;
  isChecked: boolean;
  onClick: () => void;
}

function WorklistRow({ line, isSelected, isChecked, onClick }: WorklistRowProps) {
  const pip = pipStatus(line.overall_match_status);
  const barClass = STATUS_BAR_CLASS[pip];
  const pct = confidencePct(line);
  const ocr = line.ocr_line_text ?? "";
  const gt = line.ground_truth_line_text ?? "";
  const diffVisible = hasDiff(ocr, gt);
  const lineNum = line.line_index + 1;
  const idStamp = `L-${String(lineNum).padStart(3, "0")}`;

  return (
    <button
      type="button"
      role="option"
      data-testid={`worklist-row-${line.line_index}`}
      data-selected={isSelected ? "true" : undefined}
      aria-selected={isSelected}
      onClick={onClick}
      className={cn(
        "w-full flex items-stretch text-left text-[11px] transition-colors border-b border-border-1/40",
        isSelected
          ? "bg-bg-raised text-ink-1"
          : "text-ink-2 hover:bg-bg-raised/60 hover:text-ink-1",
      )}
    >
      {/* Bulk-select checkbox */}
      <div className="flex items-center pl-1.5 pr-0.5 flex-shrink-0">
        <input
          type="checkbox"
          data-testid={`worklist-row-checkbox-${line.line_index}`}
          checked={isChecked}
          onChange={() => worklistStore.toggle(line.line_index)}
          // onClick stops the row-navigation handler; onChange drives the store toggle.
          onClick={(e) => e.stopPropagation()}
          className="w-3 h-3 cursor-pointer accent-accent"
          aria-label={`Select line ${line.line_index + 1} for bulk action`}
        />
      </div>

      {/* 4px status color bar */}
      <div className={cn("w-1 flex-shrink-0 rounded-sm my-0.5 ml-0.5", barClass)} />

      {/* Row body */}
      <div className="flex-1 flex flex-col gap-0.5 px-2 py-1.5 min-w-0">
        {/* Top row: mono ID + pip + confidence */}
        <div className="flex items-center gap-1.5">
          <span className="font-mono text-[10px] text-ink-3 flex-shrink-0">{idStamp}</span>
          <StatusPip status={pip} />
          <span className="ml-auto font-mono tabular-nums text-[10px] text-ink-3 flex-shrink-0">
            {pct}%
          </span>
        </div>

        {/* OCR text */}
        <span className="truncate font-mono text-[11px] text-ink-1">
          {ocr || <span className="text-ink-4 italic">∅ no OCR text</span>}
        </span>

        {/* GT diff line — only shown when OCR ≠ GT */}
        {diffVisible && (
          <span
            data-testid={`worklist-row-${line.line_index}-gt`}
            className="truncate font-mono text-[10px] text-status-fuzzy"
          >
            → {gt}
          </span>
        )}
      </div>
    </button>
  );
}

// ─── Search filter (Task 5) ───────────────────────────────────────────────────

function filterBySearch(lines: LineMatch[], query: string): LineMatch[] {
  const q = query.trim().toLowerCase();
  if (!q) return lines;
  return lines.filter(
    (l) =>
      (l.ocr_line_text ?? "").toLowerCase().includes(q) ||
      (l.ground_truth_line_text ?? "").toLowerCase().includes(q),
  );
}

// ─── Component ────────────────────────────────────────────────────────────────

export interface WorklistProps {
  /** Page line matches to display. Pass undefined when page not loaded. */
  lineMatches?: LineMatch[] | undefined;
  projectId: string;
  pageIndex: number;
}

export function Worklist({ lineMatches = [], projectId, pageIndex }: WorklistProps) {
  // Subscribe to worklist store for reactive re-renders.
  const state = useSyncExternalStore(
    worklistStore.subscribe,
    worklistStore.getState,
    worklistStore.getState,
  );

  const { activeFilter, selectedLineIndex, sort, searchQuery } = state;

  // Apply filter, then search, then sort.
  const filtered = sortLines(
    filterBySearch(filterLines(lineMatches, activeFilter), searchQuery),
    sort,
  );

  // Pre-build a Set so isChecked lookups are O(1) instead of O(n) per row.
  const checkedSet = new Set(state.selectedIds);

  // Counts are always computed from the full unfiltered list for the chip row.
  const counts = computeCounts(lineMatches);

  return (
    <div data-testid="worklist" className="flex flex-col h-full">
      {/* Filter + sort row (P5.b) */}
      <FilterRow
        counts={counts}
        activeFilter={activeFilter}
        sort={sort}
        onFilter={(f) => worklistStore.setActiveFilter(f)}
        onSort={(s) => worklistStore.setSort(s)}
      />

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
          filtered.map((line) => (
            <WorklistRow
              key={line.line_index}
              line={line}
              isSelected={selectedLineIndex === line.line_index}
              isChecked={checkedSet.has(line.line_index)}
              onClick={() => {
                worklistStore.setSelectedLineIndex(line.line_index);
                selectLine(line.line_index);
              }}
            />
          ))
        )}
      </div>

      {/* Bulk actions — always visible; page-level ops work without selection */}
      <BulkActions projectId={projectId} pageIndex={pageIndex} />
    </div>
  );
}

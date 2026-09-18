// PageKindsDialog.tsx — "Review page kinds": a book-wide list of every
// page's proposed and confirmed kind, with filters, selection, and bulk
// confirm.
//
// Spec: pdomain-ocr-synth's docs/specs/2026-09-17-page-kind-review-design.md
//   "A book-wide list reviews many pages at once"
//
// Follows the look of components/drawer/Worklist.tsx and BulkActions.tsx
// (filter row, checkbox rows, a selection bar) without reusing either —
// both are bound to one page's line matches, worklistStore, and page-scoped
// actions; this dialog keeps its own selection state and its own bar, over
// book-wide rows from usePageKinds.
//
// data-testids:
//   page-kinds-dialog                     — DialogContent wrapper
//   page-kinds-dialog-close                — header close button
//   page-kinds-filter-unreviewed           — "Unreviewed" filter button
//   page-kinds-filter-all                  — "All" filter button
//   page-kinds-kind-filter-select          — proposed-kind filter select
//   page-kinds-select-all-visible          — select-all-visible checkbox
//   page-kinds-loading                     — shown while the list loads
//   page-kinds-error                       — shown if the list fails to load
//   page-kinds-empty                       — shown when no row matches the filters
//   page-kinds-rows                        — row list container
//   page-kinds-row-{pageIndex}             — one row
//   page-kinds-row-checkbox-{pageIndex}    — row selection checkbox
//   page-kinds-row-page-link-{pageIndex}   — page-number link (navigates + closes)
//   page-kinds-row-proposed-{pageIndex}    — proposed kind + confidence text
//   page-kinds-row-confirmed-{pageIndex}   — confirmed kind / review-status text
//   page-kinds-bulk-bar                    — selection bar (always mounted)
//   page-kinds-bulk-count                  — "N selected" (shown once count > 0)
//   page-kinds-bulk-confirm-as-proposed    — "Confirm as proposed" button
//   page-kinds-bulk-excluded-note          — count excluded (unknown/no proposal)
//   page-kinds-bulk-set-kind-select        — "Set kind" select
//   page-kinds-bulk-set-kind-apply         — "Set kind" apply button
//   page-kinds-dialog-close-footer         — footer Close button

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@pdomain/pdomain-ui/primitives";
import {
  usePageKinds,
  useBulkConfirmPageKinds,
  type BulkConfirmPageKindItem,
  type PageKindsListItem,
} from "../hooks/usePageKinds";
import { pageNoUrl } from "../lib/routes";
import { PAGE_KINDS, type PageKind } from "../lib/pageKinds";

type ReviewFilter = "unreviewed" | "all";

// ─── Row formatting ─────────────────────────────────────────────────────────

function formatConfidence(confidence: number | null): string {
  return typeof confidence === "number" ? confidence.toFixed(2) : "—";
}

function proposedLabel(row: PageKindsListItem): string {
  if (row.proposed_kind === null) return "No proposal";
  return `${row.proposed_kind} (${formatConfidence(row.confidence)})`;
}

function confirmedLabel(row: PageKindsListItem): string {
  if (row.confirmed_kind !== null) return row.confirmed_kind;
  return row.reviewed ? "reviewed, kind not recorded" : "unreviewed";
}

/** A proposal a person can confirm as-is: present, and not `unknown`. */
function hasUsableProposal(
  row: PageKindsListItem,
): row is PageKindsListItem & { proposed_kind: PageKind } {
  return row.proposed_kind !== null && row.proposed_kind !== "unknown";
}

// ─── Row ────────────────────────────────────────────────────────────────────

interface PageKindsRowProps {
  row: PageKindsListItem;
  checked: boolean;
  onToggle: () => void;
  onNavigate: () => void;
}

function PageKindsRow({ row, checked, onToggle, onNavigate }: PageKindsRowProps) {
  return (
    <div
      data-testid={`page-kinds-row-${String(row.page_index)}`}
      className="flex items-center gap-2 px-2 py-1.5 text-[11px] border-b border-border-1/40 text-ink-2"
    >
      <input
        type="checkbox"
        data-testid={`page-kinds-row-checkbox-${String(row.page_index)}`}
        checked={checked}
        onChange={onToggle}
        aria-label={`Select page ${String(row.page_index + 1)}`}
        className="w-3 h-3 cursor-pointer accent-accent"
      />
      <button
        type="button"
        data-testid={`page-kinds-row-page-link-${String(row.page_index)}`}
        onClick={onNavigate}
        className="font-mono text-ink-1 hover:text-accent transition-colors shrink-0"
      >
        Page {row.page_index + 1}
      </button>
      <span
        data-testid={`page-kinds-row-proposed-${String(row.page_index)}`}
        className="flex-1 truncate"
      >
        {proposedLabel(row)}
      </span>
      <span
        data-testid={`page-kinds-row-confirmed-${String(row.page_index)}`}
        className="flex-1 truncate"
      >
        {confirmedLabel(row)}
      </span>
    </div>
  );
}

// ─── Dialog ─────────────────────────────────────────────────────────────────

export interface PageKindsDialogProps {
  open: boolean;
  projectId: string;
  onClose: () => void;
}

export function PageKindsDialog({ open, projectId, onClose }: PageKindsDialogProps) {
  const navigate = useNavigate();
  const pageKindsQ = usePageKinds(projectId);
  const bulkConfirm = useBulkConfirmPageKinds(projectId);

  const [reviewFilter, setReviewFilter] = useState<ReviewFilter>("unreviewed");
  const [kindFilter, setKindFilter] = useState<PageKind | "">("");
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [setKindValue, setSetKindValue] = useState<PageKind | "">("");

  const rows = pageKindsQ.data?.pages ?? [];

  // A plain filter, not useMemo: the list is at most a book's page count,
  // and `rows` is a fresh array every render (`?? []`), which would defeat
  // memoization anyway.
  const filtered = rows.filter((row) => {
    if (reviewFilter === "unreviewed" && row.reviewed) return false;
    if (kindFilter !== "" && row.proposed_kind !== kindFilter) return false;
    return true;
  });

  const visibleIndices = filtered.map((r) => r.page_index);
  const allVisibleSelected =
    visibleIndices.length > 0 && visibleIndices.every((i) => selected.has(i));

  /** The page indices a given filter pair would show, computed from `rows`. */
  function visibleIndicesFor(rf: ReviewFilter, kf: PageKind | ""): Set<number> {
    const visible = new Set<number>();
    for (const row of rows) {
      if (rf === "unreviewed" && row.reviewed) continue;
      if (kf !== "" && row.proposed_kind !== kf) continue;
      visible.add(row.page_index);
    }
    return visible;
  }

  /** Drop every selected page the given filter pair would hide. */
  function pruneSelectionTo(visible: Set<number>) {
    setSelected((prev) => {
      const next = new Set<number>();
      for (const i of prev) {
        if (visible.has(i)) next.add(i);
      }
      return next.size === prev.size ? prev : next;
    });
  }

  function handleReviewFilterChange(next: ReviewFilter) {
    setReviewFilter(next);
    pruneSelectionTo(visibleIndicesFor(next, kindFilter));
  }

  function handleKindFilterChange(next: PageKind | "") {
    setKindFilter(next);
    pruneSelectionTo(visibleIndicesFor(reviewFilter, next));
  }

  function toggleRow(pageIndex: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(pageIndex)) {
        next.delete(pageIndex);
      } else {
        next.add(pageIndex);
      }
      return next;
    });
  }

  function toggleSelectAllVisible() {
    setSelected((prev) => {
      const next = new Set(prev);
      if (allVisibleSelected) {
        for (const i of visibleIndices) next.delete(i);
      } else {
        for (const i of visibleIndices) next.add(i);
      }
      return next;
    });
  }

  function handleRowNavigate(pageIndex: number) {
    onClose();
    void navigate(pageNoUrl(projectId, pageIndex + 1));
  }

  // Built from `filtered`, not `rows`: a page the current filters hide must
  // never reach a bulk action, even if `selected` still names it.
  const selectedRows = filtered.filter((r) => selected.has(r.page_index));
  const confirmAsProposedItems: BulkConfirmPageKindItem[] = selectedRows
    .filter(hasUsableProposal)
    .map((r) => ({ page_index: r.page_index, kind: r.proposed_kind }));
  const excludedCount = selectedRows.length - confirmAsProposedItems.length;

  function handleConfirmAsProposed() {
    if (confirmAsProposedItems.length === 0) return;
    bulkConfirm.mutate(
      { items: confirmAsProposedItems },
      {
        onSuccess: () => {
          setSelected(new Set());
        },
      },
    );
  }

  function handleSetKindApply() {
    if (setKindValue === "" || selectedRows.length === 0) return;
    const kind = setKindValue;
    const items: BulkConfirmPageKindItem[] = selectedRows.map((r) => ({
      page_index: r.page_index,
      kind,
    }));
    bulkConfirm.mutate(
      { items },
      {
        onSuccess: () => {
          setSelected(new Set());
          setSetKindValue("");
        },
      },
    );
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(isOpen) => {
        if (!isOpen) onClose();
      }}
    >
      <DialogContent
        data-testid="page-kinds-dialog"
        className="rounded-lg border border-border-2 w-full max-w-2xl mx-4 flex flex-col overflow-hidden max-h-[85vh] p-0 gap-0"
      >
        <DialogHeader className="flex flex-row items-center justify-between px-4 py-3 border-b border-border-1 bg-bg-raised shrink-0">
          <DialogTitle className="text-sm font-semibold text-ink-1">Review page kinds</DialogTitle>
          <DialogClose
            onClick={onClose}
            data-testid="page-kinds-dialog-close"
            aria-label="Close review page kinds dialog"
            className="px-2 py-1.5 text-lg text-ink-3 hover:text-ink-1 hover:bg-bg-raised rounded-sm transition-colors"
          >
            x
          </DialogClose>
        </DialogHeader>

        <div className="flex flex-col gap-2 px-4 py-2 border-b border-border-1 shrink-0">
          <div className="flex items-center gap-2">
            <button
              type="button"
              data-testid="page-kinds-filter-unreviewed"
              data-active={reviewFilter === "unreviewed" ? "true" : undefined}
              onClick={() => {
                handleReviewFilterChange("unreviewed");
              }}
              className={`text-[11px] px-2 py-0.5 rounded-full border transition-colors ${
                reviewFilter === "unreviewed"
                  ? "bg-accent text-accent-ink border-accent"
                  : "bg-bg-raised text-ink-2 border-border-2 hover:border-accent"
              }`}
            >
              Unreviewed
            </button>
            <button
              type="button"
              data-testid="page-kinds-filter-all"
              data-active={reviewFilter === "all" ? "true" : undefined}
              onClick={() => {
                handleReviewFilterChange("all");
              }}
              className={`text-[11px] px-2 py-0.5 rounded-full border transition-colors ${
                reviewFilter === "all"
                  ? "bg-accent text-accent-ink border-accent"
                  : "bg-bg-raised text-ink-2 border-border-2 hover:border-accent"
              }`}
            >
              All
            </button>
            <select
              data-testid="page-kinds-kind-filter-select"
              aria-label="Filter by proposed kind"
              value={kindFilter}
              onChange={(e) => {
                handleKindFilterChange(e.target.value as PageKind | "");
              }}
              className="text-[11px] border border-border-2 rounded-sm px-1 py-0.5 bg-bg-sunk text-ink-2"
            >
              <option value="">All proposed kinds</option>
              {PAGE_KINDS.map((k) => (
                <option key={k} value={k}>
                  {k}
                </option>
              ))}
            </select>
          </div>
          <label className="flex items-center gap-1.5 text-[11px] text-ink-2 cursor-pointer">
            <input
              type="checkbox"
              data-testid="page-kinds-select-all-visible"
              checked={allVisibleSelected}
              onChange={toggleSelectAllVisible}
              className="w-3 h-3 cursor-pointer accent-accent"
            />
            Select all visible
          </label>
        </div>

        <div className="flex-1 overflow-y-auto min-h-0">
          {pageKindsQ.isLoading && (
            <div data-testid="page-kinds-loading" className="p-3 text-[11px] text-ink-3">
              Loading…
            </div>
          )}
          {pageKindsQ.isError && (
            <div data-testid="page-kinds-error" className="p-3 text-[11px] text-status-mismatch">
              Failed to load page kinds.
            </div>
          )}
          {!pageKindsQ.isLoading && filtered.length === 0 && (
            <div data-testid="page-kinds-empty" className="p-3 text-[11px] text-ink-3">
              No pages match the current filters.
            </div>
          )}
          <div data-testid="page-kinds-rows">
            {filtered.map((row) => (
              <PageKindsRow
                key={row.page_index}
                row={row}
                checked={selected.has(row.page_index)}
                onToggle={() => {
                  toggleRow(row.page_index);
                }}
                onNavigate={() => {
                  handleRowNavigate(row.page_index);
                }}
              />
            ))}
          </div>
        </div>

        <DialogFooter className="flex flex-col gap-2 px-4 py-3 border-t border-border-1 bg-bg-raised shrink-0">
          <div data-testid="page-kinds-bulk-bar" className="flex items-center gap-2 flex-wrap">
            {selectedRows.length > 0 && (
              <span data-testid="page-kinds-bulk-count" className="text-[11px] text-ink-2">
                {selectedRows.length} selected
              </span>
            )}
            <button
              type="button"
              data-testid="page-kinds-bulk-confirm-as-proposed"
              disabled={confirmAsProposedItems.length === 0 || bulkConfirm.isPending}
              onClick={handleConfirmAsProposed}
              className="text-[11px] px-2 py-1 rounded-sm border border-border-2 text-ink-2 hover:border-accent hover:text-ink-1 transition-colors disabled:opacity-40"
            >
              Confirm as proposed
            </button>
            {excludedCount > 0 && (
              <span data-testid="page-kinds-bulk-excluded-note" className="text-[10px] text-ink-3">
                {excludedCount} excluded (no usable proposal)
              </span>
            )}
            <span className="mx-1 text-ink-4">|</span>
            <select
              data-testid="page-kinds-bulk-set-kind-select"
              aria-label="Set kind for selected pages"
              value={setKindValue}
              onChange={(e) => {
                setSetKindValue(e.target.value as PageKind | "");
              }}
              disabled={bulkConfirm.isPending}
              className="text-[11px] border border-border-2 rounded-sm px-1 py-0.5 bg-bg-sunk text-ink-2"
            >
              <option value="" disabled>
                Choose a kind…
              </option>
              {PAGE_KINDS.map((k) => (
                <option key={k} value={k}>
                  {k}
                </option>
              ))}
            </select>
            <button
              type="button"
              data-testid="page-kinds-bulk-set-kind-apply"
              disabled={setKindValue === "" || selectedRows.length === 0 || bulkConfirm.isPending}
              onClick={handleSetKindApply}
              className="text-[11px] px-2 py-1 rounded-sm border border-border-2 text-ink-2 hover:border-accent hover:text-ink-1 transition-colors disabled:opacity-40"
            >
              Set kind
            </button>
          </div>
          <div className="flex justify-end">
            <button
              type="button"
              data-testid="page-kinds-dialog-close-footer"
              onClick={onClose}
              className="px-3 py-1.5 text-sm rounded-sm border border-border-2 bg-bg-surface text-ink-2 hover:bg-bg-raised transition-colors"
            >
              Close
            </button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

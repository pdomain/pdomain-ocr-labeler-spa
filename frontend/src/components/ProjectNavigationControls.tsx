// ProjectNavigationControls.tsx — inline pager bar for the project header.
//
// Spec: specs/22-page-surface-wireup.md §7 (Navigation controls).
//       docs/plans/hifi-gaps-plan.md P1.b (Gap 4, 7)
// Issue #311 (spec-22-B2).
//
// Visual layout (P1.b hi-fi): ◀ <page-number-input> ▶ /total
// The Prev/Next arrows replace "Prev"/"Next" text labels, the GoTo button is
// visually hidden (sr-only) while retaining its driver-contract testid.
//
// Behavior:
//   - Receives `projectId` + `pageNo` as props (passed from App.tsx AppShell).
//   - Reads `total_pages` from `useProject(projectId).data.image_paths.length`
//     (`ProjectResponse` includes a `total_pages` field but `image_paths.length`
//     is used intentionally for parity with the legacy labeler page-count logic).
//   - Prev / Next call
//     `navigate('/projects/${projectId}/pages/pageno/${newPageNo}')`, with
//     boundary disable (Prev at page 1; Next at last page).
//   - GoTo input is bound to local state. Enter on the input OR clicking
//     `nav-goto-button` parses the value and navigates to it — if the value
//     parses to an integer in [1, total_pages]. Out-of-range or non-numeric
//     values are silently rejected (no navigation, no toast — matches legacy
//     behavior in `pd-ocr-labeler/pd_ocr_labeler/views/projects/pages/page_view.py`).
//   - Total label: `/ ${total_pages}` (testid: nav-page-total-label).

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronLeft, ChevronRight } from "@concavetrillion/pd-ui/icons";
import { useProject } from "../hooks/useProject";
import { pageNoUrl } from "../lib/routes";

export interface ProjectNavigationControlsProps {
  projectId: string;
  pageNo: string;
}

export default function ProjectNavigationControls({
  projectId,
  pageNo,
}: ProjectNavigationControlsProps) {
  const navigate = useNavigate();
  const { data } = useProject(projectId);

  const currentPageNo = parsePositiveInt(pageNo) ?? 1;
  // data is the flat Project returned by GET /api/projects/{id}.
  // image_paths.length is the source of truth for page count
  // (spec 23 §2; Project also has a total_pages field but image_paths
  // is what the legacy labeler uses for nav bounds).
  const totalPages = data?.image_paths?.length ?? 0;

  const [gotoValue, setGotoValue] = useState<string>("");

  const canPrev = totalPages > 0 && currentPageNo > 1;
  const canNext = totalPages > 0 && currentPageNo < totalPages;

  function navigateToPage(n: number) {
    if (!projectId) return;
    if (!Number.isInteger(n)) return;
    if (n < 1 || n > totalPages) return;
    void navigate(pageNoUrl(projectId, n));
  }

  function onPrev() {
    navigateToPage(currentPageNo - 1);
  }

  function onNext() {
    navigateToPage(currentPageNo + 1);
  }

  function onGoTo() {
    // Use gotoValue if typed; fall back to currentPageNo (no-op re-navigate).
    const n = parsePositiveInt(gotoValue !== "" ? gotoValue : String(currentPageNo));
    if (n === null) return;
    navigateToPage(n);
  }

  function onInputKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter") {
      event.preventDefault();
      onGoTo();
      setGotoValue("");
    }
    if (event.key === "Escape") {
      setGotoValue("");
    }
  }

  // Button base classes for the compact header style.
  const btnBase =
    "flex items-center justify-center h-6 w-6 rounded text-ink-2 border border-border-2 bg-bg-raised hover:bg-bg-surface hover:text-ink-1 disabled:opacity-40 disabled:cursor-not-allowed transition-colors";

  return (
    <div
      data-testid="project-navigation-controls"
      className="flex items-center gap-1 px-1"
      aria-label="Page navigation"
    >
      {/* ◀ Prev arrow */}
      <button
        type="button"
        data-testid="nav-prev-button"
        aria-label="Previous page"
        disabled={!canPrev}
        onClick={onPrev}
        className={btnBase}
      >
        <ChevronLeft size={14} aria-hidden="true" />
      </button>

      {/* Page number input — shows current page; Enter navigates */}
      <input
        type="number"
        min={1}
        max={totalPages || undefined}
        data-testid="nav-page-input"
        aria-label="Page number"
        value={gotoValue !== "" ? gotoValue : String(currentPageNo)}
        onChange={(e) => {
          setGotoValue(e.target.value);
        }}
        onBlur={() => {
          setGotoValue("");
        }}
        onKeyDown={onInputKeyDown}
        className="w-10 h-6 px-1 text-center text-[11px] tabular-nums border border-border-2 rounded bg-bg-sunk text-ink-1 focus:outline-none focus:border-accent"
      />

      {/* ▶ Next arrow */}
      <button
        type="button"
        data-testid="nav-next-button"
        aria-label="Next page"
        disabled={!canNext}
        onClick={onNext}
        className={btnBase}
      >
        <ChevronRight size={14} aria-hidden="true" />
      </button>

      {/* / total label */}
      <span
        data-testid="nav-page-total-label"
        className="text-[11px] tabular-nums text-ink-3 pl-0.5"
      >
        / {totalPages}
      </span>

      {/* nav-goto-button: driver-contract testid preserved; sr-only (Enter key triggers GoTo) */}
      <button
        type="button"
        data-testid="nav-goto-button"
        aria-label="Go to page"
        onClick={onGoTo}
        className="sr-only"
      >
        Go
      </button>
    </div>
  );
}

/**
 * Parse `value` as a positive integer (>= 1). Returns null for non-numeric,
 * negative, zero, or non-integer values. Empty string → null.
 */
function parsePositiveInt(value: string | undefined | null): number | null {
  if (value === undefined || value === null) return null;
  const trimmed = String(value).trim();
  if (trimmed === "") return null;
  if (!/^\d+$/.test(trimmed)) return null;
  const n = parseInt(trimmed, 10);
  if (!Number.isFinite(n) || n < 1) return null;
  return n;
}

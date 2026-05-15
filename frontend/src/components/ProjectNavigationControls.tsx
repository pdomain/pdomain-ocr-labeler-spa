// ProjectNavigationControls.tsx — real Prev / Next / GoTo bar for ProjectPage.
//
// Spec: specs/22-page-surface-wireup.md §7 (Navigation controls).
// Issue #311 (spec-22-B2).
//
// Replaces the five `display:none` nav-control testids in `ProjectPage.tsx`
// (the actual removal of the stub block belongs to spec-22-C); this slice
// just ships the working component + tests.
//
// Behavior:
//   - Reads `projectId` + `pageNo` from the URL via `useParams`.
//   - Reads `total_pages` from `useProject(projectId).data.project.image_paths.length`
//     (project doesn't expose `total_pages` as a top-level field yet; spec 23 §2
//     keeps `image_paths` as the source of truth for page count).
//   - Prev / Next call
//     `navigate('/projects/${projectId}/pages/pageno/${newPageNo}')`, with
//     boundary disable (Prev at page 1; Next at last page).
//   - GoTo input is bound to local state. Enter on the input OR clicking
//     `nav-goto-button` parses the value and navigates to it — if the value
//     parses to an integer in [1, total_pages]. Out-of-range or non-numeric
//     values are silently rejected (no navigation, no toast — matches legacy
//     behavior in `pd-ocr-labeler/pd_ocr_labeler/views/projects/pages/page_view.py`).
//   - Total label: `${currentPageNo} / ${total_pages}`.

import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useProject } from "../hooks/useProject";
import { pageNoUrl } from "../lib/routes";

export default function ProjectNavigationControls() {
  const { projectId, pageNo } = useParams<{ projectId: string; pageNo: string }>();
  const navigate = useNavigate();
  const { data } = useProject(projectId);

  const currentPageNo = parsePositiveInt(pageNo) ?? 1;
  const totalPages = data?.project.image_paths.length ?? 0;

  const [gotoValue, setGotoValue] = useState<string>("");

  const canPrev = totalPages > 0 && currentPageNo > 1;
  const canNext = totalPages > 0 && currentPageNo < totalPages;

  function navigateToPage(n: number) {
    if (!projectId) return;
    if (!Number.isInteger(n)) return;
    if (n < 1 || n > totalPages) return;
    navigate(pageNoUrl(projectId, n));
  }

  function onPrev() {
    navigateToPage(currentPageNo - 1);
  }

  function onNext() {
    navigateToPage(currentPageNo + 1);
  }

  function onGoTo() {
    const n = parsePositiveInt(gotoValue);
    if (n === null) return;
    navigateToPage(n);
  }

  function onInputKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter") {
      event.preventDefault();
      onGoTo();
    }
  }

  return (
    <div data-testid="project-navigation-controls" className="flex items-center gap-2 px-2 py-1">
      <button
        type="button"
        data-testid="nav-prev-button"
        aria-label="Previous page"
        disabled={!canPrev}
        onClick={onPrev}
        className="px-2 py-1 text-sm border rounded disabled:opacity-50"
      >
        Prev
      </button>
      <button
        type="button"
        data-testid="nav-next-button"
        aria-label="Next page"
        disabled={!canNext}
        onClick={onNext}
        className="px-2 py-1 text-sm border rounded disabled:opacity-50"
      >
        Next
      </button>
      <input
        type="number"
        min={1}
        max={totalPages || undefined}
        data-testid="nav-page-input"
        aria-label="Page number"
        value={gotoValue}
        onChange={(e) => setGotoValue(e.target.value)}
        onKeyDown={onInputKeyDown}
        className="w-16 px-1 py-0.5 text-sm border rounded"
      />
      <button
        type="button"
        data-testid="nav-goto-button"
        aria-label="Go to page"
        onClick={onGoTo}
        className="px-2 py-1 text-sm border rounded"
      >
        Go
      </button>
      <span data-testid="nav-page-total-label" className="text-sm tabular-nums">
        {currentPageNo} / {totalPages}
      </span>
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

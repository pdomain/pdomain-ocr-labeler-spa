// TextTabs.tsx — tab switcher for Matches / Ground Truth / OCR views.
//
// Spec: docs/specs/2026-05-12-word-matches-design.md §Layout
// Issue #200
//
// Three tabs:
//   - "matches"       → <WordMatchView /> (placeholder until #201–#203)
//   - "ground-truth"  → plain readOnly textarea showing page_text_gt
//   - "ocr"           → plain readOnly textarea showing page_text_ocr
//
// Filter segmented control above the content area (for the "matches" tab):
//   Unvalidated Lines | Mismatched Lines | All Lines
//   State in lineFilter prop; parent updates it via onLineFilterChange.
//
// data-testids (driver-contract invariants):
//   text-tab-matches, text-tab-ground-truth, text-tab-ocr
//   match-filter-unvalidated, match-filter-mismatched, match-filter-all

import { useState } from "react";
import type { LineFilter } from "../hooks/usePage";

export type TabId = "matches" | "ground-truth" | "ocr";

interface FilterOption {
  value: LineFilter;
  label: string;
  testid: string;
}

const FILTER_OPTIONS: FilterOption[] = [
  { value: "unvalidated", label: "Unvalidated Lines", testid: "match-filter-unvalidated" },
  { value: "mismatched", label: "Mismatched Lines", testid: "match-filter-mismatched" },
  { value: "all", label: "All Lines", testid: "match-filter-all" },
];

interface TextTabsProps {
  /** Text content for the Ground Truth plain panel. */
  pageTextGt?: string | null;
  /** Text content for the OCR plain panel. */
  pageTextOcr?: string | null;
  /** Current server-side line filter (controls segmented control). */
  lineFilter?: LineFilter;
  /** Called when the user changes the line filter. */
  onLineFilterChange?: (filter: LineFilter) => void;
  /** Slot for the word-match list (rendered inside the "matches" tab). */
  children?: React.ReactNode;
}

/**
 * Three-tab layout for the right pane:
 *   Matches | Ground Truth | OCR
 *
 * The Matches tab shows a filter segmented control above the `children` slot.
 * The GT and OCR tabs show plain readOnly textareas.
 */
export function TextTabs({
  pageTextGt = "",
  pageTextOcr = "",
  lineFilter = "unvalidated",
  onLineFilterChange,
  children,
}: TextTabsProps) {
  const [activeTab, setActiveTab] = useState<TabId>("matches");

  return (
    <div data-testid="text-tabs" className="flex flex-col h-full">
      {/* Tab trigger row */}
      <div className="flex border-b border-gray-200 bg-white shrink-0" role="tablist">
        <button
          role="tab"
          aria-selected={activeTab === "matches"}
          aria-controls="panel-matches"
          data-testid="text-tab-matches"
          onClick={() => setActiveTab("matches")}
          className={[
            "px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors",
            activeTab === "matches"
              ? "border-blue-500 text-blue-600"
              : "border-transparent text-gray-600 hover:text-gray-900",
          ].join(" ")}
        >
          Matches
        </button>
        <button
          role="tab"
          aria-selected={activeTab === "ground-truth"}
          aria-controls="panel-ground-truth"
          data-testid="text-tab-ground-truth"
          onClick={() => setActiveTab("ground-truth")}
          className={[
            "px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors",
            activeTab === "ground-truth"
              ? "border-blue-500 text-blue-600"
              : "border-transparent text-gray-600 hover:text-gray-900",
          ].join(" ")}
        >
          Ground Truth
        </button>
        <button
          role="tab"
          aria-selected={activeTab === "ocr"}
          aria-controls="panel-ocr"
          data-testid="text-tab-ocr"
          onClick={() => setActiveTab("ocr")}
          className={[
            "px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors",
            activeTab === "ocr"
              ? "border-blue-500 text-blue-600"
              : "border-transparent text-gray-600 hover:text-gray-900",
          ].join(" ")}
        >
          OCR
        </button>
      </div>

      {/* Matches panel */}
      <div
        id="panel-matches"
        role="tabpanel"
        hidden={activeTab !== "matches"}
        className="flex flex-col flex-1 overflow-hidden"
      >
        {/* Filter segmented control — only visible in the matches tab */}
        <div className="flex gap-1 p-2 bg-gray-50 border-b border-gray-200 shrink-0">
          {FILTER_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              data-testid={opt.testid}
              onClick={() => onLineFilterChange?.(opt.value)}
              aria-pressed={lineFilter === opt.value}
              className={[
                "px-3 py-1 text-xs rounded font-medium transition-colors",
                lineFilter === opt.value
                  ? "bg-blue-500 text-white"
                  : "bg-white text-gray-600 border border-gray-300 hover:bg-gray-100",
              ].join(" ")}
            >
              {opt.label}
            </button>
          ))}
        </div>
        <div className="flex-1 overflow-auto">{children}</div>
      </div>

      {/* Ground Truth panel */}
      <div
        id="panel-ground-truth"
        role="tabpanel"
        hidden={activeTab !== "ground-truth"}
        className="flex flex-col flex-1 overflow-hidden p-2"
      >
        <textarea
          data-testid="text-panel-ground-truth"
          readOnly
          value={pageTextGt ?? ""}
          className="flex-1 resize-none font-mono text-sm p-2 border border-gray-200 rounded bg-gray-50 focus:outline-none"
          aria-label="Ground truth text"
        />
      </div>

      {/* OCR panel */}
      <div
        id="panel-ocr"
        role="tabpanel"
        hidden={activeTab !== "ocr"}
        className="flex flex-col flex-1 overflow-hidden p-2"
      >
        <textarea
          data-testid="text-panel-ocr"
          readOnly
          value={pageTextOcr ?? ""}
          className="flex-1 resize-none font-mono text-sm p-2 border border-gray-200 rounded bg-gray-50 focus:outline-none"
          aria-label="OCR text"
        />
      </div>
    </div>
  );
}

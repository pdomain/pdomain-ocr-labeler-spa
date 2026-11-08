// TextTabs.tsx — tab switcher for Matches, Working GT, source and OCR views.
//
// Spec: docs/specs/2026-05-12-word-matches-design.md §Layout
// Issue #200
//
// Tabs:
//   - "matches"       → <WordMatchView /> (placeholder until #201–#203)
//   - "ground-truth"  → plain readOnly textarea showing page_text_gt
//   - "p3" / "f2"    → prepared PGDP source text
//   - "consolidated"  → P3 wording with only exact F2 formatting projections
//   - "ocr"           → plain readOnly textarea showing page_text_ocr
//
// Filter segmented control above the content area (for the "matches" tab):
//   Unvalidated Lines | Mismatched Lines | All Lines
//   State in lineFilter prop; parent updates it via onLineFilterChange.
//
// data-testids (driver-contract invariants):
//   text-tab-matches, text-tab-ground-truth, text-tab-ocr
//   match-filter-unvalidated, match-filter-mismatched, match-filter-all

import { useId, useRef, useState, type KeyboardEvent } from "react";
import type { LineFilter } from "../hooks/usePage";
import type { SourceTextPreview } from "../api/source-text";

export type TabId = "matches" | "ground-truth" | "p3" | "f2" | "consolidated" | "ocr";

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

const TAB_IDS = ["matches", "ground-truth", "p3", "f2", "consolidated", "ocr"] as const;

interface TextTabsProps {
  /** Text content for the Ground Truth plain panel. */
  pageTextGt?: string | null | undefined;
  /** Text content for the OCR plain panel. */
  pageTextOcr?: string | null | undefined;
  /** Current server-side line filter (controls segmented control). */
  lineFilter?: LineFilter | undefined;
  /** Called when the user changes the line filter. */
  onLineFilterChange?: ((filter: LineFilter) => void) | undefined;
  /** Slot for the word-match list (rendered inside the "matches" tab). */
  children?: React.ReactNode;
  /** Read-only source preview for the current project page. */
  sourcePreview?: SourceTextPreview | undefined;
  /** The current source-preview request has not completed. */
  sourcePreviewPending?: boolean | undefined;
  /** The current source-preview request failed. */
  sourcePreviewError?: boolean | undefined;
}

interface TabButtonProps {
  readonly id: TabId;
  readonly label: string;
  readonly activeTab: TabId;
  readonly tabDomId: string;
  readonly panelDomId: string;
  readonly tabIndex: number;
  readonly onActivate: (tab: TabId) => void;
  readonly onKeyDown: (event: KeyboardEvent<HTMLButtonElement>, tab: TabId) => void;
  readonly buttonRef: (button: HTMLButtonElement | null) => void;
}

function TabButton({
  id,
  label,
  activeTab,
  tabDomId,
  panelDomId,
  tabIndex,
  onActivate,
  onKeyDown,
  buttonRef,
}: TabButtonProps) {
  return (
    <button
      ref={buttonRef}
      id={tabDomId}
      role="tab"
      aria-selected={activeTab === id}
      aria-controls={panelDomId}
      tabIndex={tabIndex}
      data-testid={`text-tab-${id}`}
      onClick={() => {
        onActivate(id);
      }}
      onKeyDown={(event) => {
        onKeyDown(event, id);
      }}
      className={[
        "px-3 py-2 text-sm font-medium border-b-2 -mb-px transition-colors",
        activeTab === id
          ? "border-accent text-accent"
          : "border-transparent text-ink-2 hover:text-ink-1",
      ].join(" ")}
    >
      {label}
    </button>
  );
}

function SourceUnavailable({
  preview,
  pending,
  error,
  tab,
}: {
  readonly preview: SourceTextPreview | undefined;
  readonly pending: boolean;
  readonly error: boolean;
  readonly tab: "p3" | "f2" | "consolidated";
}) {
  if (pending) return <p data-testid={`source-preview-loading-${tab}`}>Loading source preview…</p>;
  if (error)
    return <p data-testid={`source-preview-error-${tab}`}>Source preview could not be loaded.</p>;
  const warningText = preview?.warnings.join(" ");
  return (
    <p data-testid={`source-preview-unavailable-${tab}`}>
      {warningText === undefined || warningText === ""
        ? "This page has no prepared F2 and P3 source preview."
        : warningText}
    </p>
  );
}

function SourcePanel({
  tab,
  preview,
  pending,
  error,
}: {
  readonly tab: "p3" | "f2" | "consolidated";
  readonly preview: SourceTextPreview | undefined;
  readonly pending: boolean;
  readonly error: boolean;
}) {
  if (pending || error) {
    return <SourceUnavailable preview={preview} pending={pending} error={error} tab={tab} />;
  }
  const unavailable =
    preview === undefined ||
    !preview.available ||
    preview.f2 === null ||
    preview.p3 === null ||
    (tab === "consolidated" && preview.consolidated === null);
  const source = tab === "f2" ? preview?.f2 : preview?.p3;
  if (unavailable) {
    return <SourceUnavailable preview={preview} pending={pending} error={error} tab={tab} />;
  }
  if (tab === "consolidated" && preview.consolidated !== null) {
    return (
      <section
        data-testid="text-panel-consolidated"
        className="space-y-3 font-mono text-sm whitespace-pre-wrap"
      >
        <p className="font-sans text-xs text-ink-3">
          P3 wording with F2 formatting where the source mapping is exact.
        </p>
        <p>
          {preview.consolidated.runs.map((run, index) => (
            <span
              key={`${run.text}:${String(index)}`}
              className={
                [
                  run.styles.includes("italic") ? "italic" : "",
                  run.styles.includes("bold") ? "font-bold" : "",
                ]
                  .filter((style) => style !== "")
                  .join(" ") || undefined
              }
            >
              {run.text}
            </span>
          ))}
        </p>
        {preview.consolidated.layout_hints.map((hint) => (
          <details key={`${hint.kind}:${hint.source_ref}`} data-testid="consolidated-layout-hint">
            <summary className="font-sans text-xs text-ink-3">
              Source layout evidence: {hint.kind}
            </summary>
            <pre className="whitespace-pre-wrap">
              {hint.lines.map((line) => line.text).join("\n")}
            </pre>
          </details>
        ))}
        {preview.consolidated.unresolved.length > 0 && (
          <section data-testid="consolidated-unresolved">
            <p className="font-sans text-xs text-ink-3">Unresolved F2 formatting</p>
            <ul className="font-sans text-xs">
              {preview.consolidated.unresolved.map((item) => (
                <li key={`${item.source_kind}:${item.source_ref}:${item.source_text}`}>
                  {item.source_text}: {item.reason}
                </li>
              ))}
            </ul>
          </section>
        )}
      </section>
    );
  }
  return (
    <pre
      data-testid={`text-panel-${tab}`}
      className="flex-1 whitespace-pre-wrap font-mono text-sm p-2 border border-border-1 rounded-sm bg-bg-sunk"
    >
      {source?.raw_text}
    </pre>
  );
}

/**
 * Source-aware layout for the right pane:
 *   Matches | Working GT | P3 | F2 | Consolidated GT | OCR
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
  sourcePreview,
  sourcePreviewPending = false,
  sourcePreviewError = false,
}: TextTabsProps) {
  const [activeTab, setActiveTab] = useState<TabId>("matches");
  const instanceId = useId();
  const tabButtons = useRef<(HTMLButtonElement | null)[]>([]);
  const tabDomId = (tab: TabId) => `text-tabs-${instanceId}-tab-${tab}`;
  const panelDomId = (tab: TabId) => `text-tabs-${instanceId}-panel-${tab}`;
  const activateTab = (tab: TabId): void => {
    setActiveTab(tab);
  };
  const moveFocus = (tab: TabId): void => {
    const index = TAB_IDS.indexOf(tab);
    tabButtons.current[index]?.focus();
  };
  const handleTabKeyDown = (event: KeyboardEvent<HTMLButtonElement>, tab: TabId): void => {
    const currentIndex = TAB_IDS.indexOf(tab);
    const nextIndex =
      event.key === "ArrowRight"
        ? (currentIndex + 1) % TAB_IDS.length
        : event.key === "ArrowLeft"
          ? (currentIndex - 1 + TAB_IDS.length) % TAB_IDS.length
          : event.key === "Home"
            ? 0
            : event.key === "End"
              ? TAB_IDS.length - 1
              : undefined;
    if (nextIndex === undefined) return;
    event.preventDefault();
    const nextTab = TAB_IDS[nextIndex];
    if (nextTab === undefined) return;
    activateTab(nextTab);
    moveFocus(nextTab);
  };

  return (
    <div data-testid="text-tabs" className="flex flex-col h-full">
      {/* Tab trigger row */}
      <div className="flex border-b border-border-1 bg-bg-surface shrink-0" role="tablist">
        {TAB_IDS.map((tab, index) => (
          <TabButton
            key={tab}
            id={tab}
            label={
              tab === "matches"
                ? "Matches"
                : tab === "ground-truth"
                  ? "Working GT"
                  : tab === "p3"
                    ? "P3"
                    : tab === "f2"
                      ? "F2"
                      : tab === "consolidated"
                        ? "Consolidated GT"
                        : "OCR"
            }
            activeTab={activeTab}
            tabDomId={tabDomId(tab)}
            panelDomId={panelDomId(tab)}
            tabIndex={activeTab === tab ? 0 : -1}
            onActivate={activateTab}
            onKeyDown={handleTabKeyDown}
            buttonRef={(button) => {
              tabButtons.current[index] = button;
            }}
          />
        ))}
      </div>

      {/* Matches panel */}
      <div
        id={panelDomId("matches")}
        role="tabpanel"
        hidden={activeTab !== "matches"}
        aria-labelledby={tabDomId("matches")}
        className="flex flex-col flex-1 overflow-hidden"
      >
        {/* Filter segmented control — only visible in the matches tab */}
        <div
          data-testid="match-filter-toggle"
          className="flex gap-1 p-2 bg-bg-raised border-b border-border-1 shrink-0"
        >
          {FILTER_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              data-testid={opt.testid}
              onClick={() => onLineFilterChange?.(opt.value)}
              aria-pressed={lineFilter === opt.value}
              className={[
                "px-3 py-1 text-xs rounded-sm font-medium transition-colors",
                lineFilter === opt.value
                  ? "bg-accent text-accent-ink"
                  : "bg-bg-surface text-ink-2 border border-border-2 hover:bg-bg-raised",
              ].join(" ")}
            >
              {opt.label}
            </button>
          ))}
        </div>
        {/*
         * `children` (WordMatchView) renders directly here, not inside an
         * extra wrapper div. WordMatchView's own root already carries
         * className="flex-1 overflow-auto" plus style={{contain: "strict"}}
         * so @tanstack/react-virtual gets a definite height to measure
         * against — but `flex-1` only produces that height when its
         * *immediate* parent is a flex container, which this `#panel-matches`
         * div (className="flex flex-col flex-1 overflow-hidden") is. A
         * wrapper wasn't: it collapsed WordMatchView to zero height with
         * real word content, so the virtualizer mounted no rows (P0-CI-SOFT
         * follow-up). Matches the Ground Truth / OCR panels below, whose
         * textareas are direct flex children of their panels too.
         */}
        {children}
      </div>

      {(["p3", "f2", "consolidated"] as const).map((tab) => (
        <div
          key={tab}
          id={panelDomId(tab)}
          role="tabpanel"
          hidden={activeTab !== tab}
          aria-labelledby={tabDomId(tab)}
          className="flex flex-col flex-1 overflow-auto p-3"
        >
          {activeTab === tab && (
            <SourcePanel
              tab={tab}
              preview={sourcePreview}
              pending={sourcePreviewPending}
              error={sourcePreviewError}
            />
          )}
        </div>
      ))}

      {/* Ground Truth panel */}
      <div
        id={panelDomId("ground-truth")}
        role="tabpanel"
        hidden={activeTab !== "ground-truth"}
        aria-labelledby={tabDomId("ground-truth")}
        className="flex flex-col flex-1 overflow-hidden p-2"
      >
        <p className="shrink-0 pb-2 text-xs text-ink-3">Edit individual words in Matches.</p>
        <textarea
          data-testid="text-panel-ground-truth"
          readOnly
          value={pageTextGt ?? ""}
          className="flex-1 resize-none font-mono text-sm p-2 border border-border-1 rounded-sm bg-bg-sunk focus:outline-hidden"
          aria-label="Ground truth text"
        />
      </div>

      {/* OCR panel */}
      <div
        id={panelDomId("ocr")}
        role="tabpanel"
        hidden={activeTab !== "ocr"}
        aria-labelledby={tabDomId("ocr")}
        className="flex flex-col flex-1 overflow-hidden p-2"
      >
        <textarea
          data-testid="text-panel-ocr"
          readOnly
          value={pageTextOcr ?? ""}
          className="flex-1 resize-none font-mono text-sm p-2 border border-border-1 rounded-sm bg-bg-sunk focus:outline-hidden"
          aria-label="OCR text"
        />
      </div>
    </div>
  );
}

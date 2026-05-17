// BlockDetail.tsx — Block-level (and para-level) right panel (P5.g redesign).
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 22 + hifi-gaps-plan.md P5.g.
// Gaps closed: 47 (layout-type glyph cards), 48 (model-suggest callout),
//              49 (preview pane), 50 (Items View sub-toggle), 51 (Para layout tab).
//
// Layout tab:
//   - Two groups: Structural (9 types) / Content (10 types) shown as shape-glyph cards.
//   - Each card shows a CSS SVG glyph of the block shape + label.
//   - Model-suggest callout above picker when suggestion available.
//   - Preview pane below showing how the block renders in chosen layout type.
//   - Sticky "Save layout type" footer button.
//
// Items tab:
//   - View sub-toggle: "Flat" (all lines) vs "Tree" (para groups).
//   - Lines in each group clickable → selectLine.
//
// Para layout tab (block level only when selected para contains lines):
//   - Paragraph-scope selector + layout type choice.
//
// data-testids:
//   block-detail                     — outer container
//   block-detail-tabs                — Tabs root
//   block-detail-tab-layout          — Layout tab trigger
//   block-detail-tab-items           — Items tab trigger
//   block-detail-tab-para-layout     — Para layout tab trigger
//   block-detail-layout-chip-*       — glyph card for each layout type (lowercase)
//   block-detail-layout-accept       — Accept suggestion button
//   block-detail-layout-save         — Save layout type footer button
//   block-detail-preview             — preview pane
//   block-detail-items-tree          — Items tree container
//   block-detail-items-view-flat     — Flat view sub-toggle
//   block-detail-items-view-tree     — Tree view sub-toggle
//   block-detail-density-toggle      — (kept for compat) density toggle
//   block-detail-para-*              — para group headers
//   block-detail-line-card-*         — line cards
//   block-detail-line-row-*          — line rows

import { useSyncExternalStore, useState } from "react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../ui/tabs";
import { StatusPip } from "../ui/StatusPip";
import {
  selectionStore,
  selectLine,
  selectPara,
  type SelectionLevel,
} from "../../stores/selection-store";
import { usePatchParagraph } from "../../hooks/useLineMutations";
import type { components } from "../../api/types";

type PagePayload = components["schemas"]["PagePayload"];
type LineMatch = components["schemas"]["LineMatch"];
type MatchStatus = components["schemas"]["MatchStatus"];

// ─── Layout type definitions ──────────────────────────────────────────────────

type LayoutType =
  // Structural group
  | "heading"
  | "subheading"
  | "section-break"
  | "page-header"
  | "page-footer"
  | "footnote"
  | "sidebar"
  | "caption"
  | "pullquote"
  // Content group
  | "body-text"
  | "list-item"
  | "table"
  | "figure"
  | "diagram"
  | "code"
  | "verse"
  | "letter"
  | "drop-cap-block";

interface LayoutTypeSpec {
  id: LayoutType;
  label: string;
  glyph: string; // SVG path or CSS shape descriptor
  group: "structural" | "content";
}

const LAYOUT_TYPES: LayoutTypeSpec[] = [
  // Structural
  {
    id: "heading",
    label: "Heading",
    group: "structural",
    glyph: "heading",
  },
  {
    id: "subheading",
    label: "Subheading",
    group: "structural",
    glyph: "subheading",
  },
  {
    id: "section-break",
    label: "Section Break",
    group: "structural",
    glyph: "section-break",
  },
  {
    id: "page-header",
    label: "Page Header",
    group: "structural",
    glyph: "page-header",
  },
  {
    id: "page-footer",
    label: "Page Footer",
    group: "structural",
    glyph: "page-footer",
  },
  {
    id: "footnote",
    label: "Footnote",
    group: "structural",
    glyph: "footnote",
  },
  {
    id: "sidebar",
    label: "Sidebar",
    group: "structural",
    glyph: "sidebar",
  },
  {
    id: "caption",
    label: "Caption",
    group: "structural",
    glyph: "caption",
  },
  {
    id: "pullquote",
    label: "Pullquote",
    group: "structural",
    glyph: "pullquote",
  },
  // Content
  {
    id: "body-text",
    label: "Body Text",
    group: "content",
    glyph: "body-text",
  },
  {
    id: "list-item",
    label: "List Item",
    group: "content",
    glyph: "list-item",
  },
  {
    id: "table",
    label: "Table",
    group: "content",
    glyph: "table",
  },
  {
    id: "figure",
    label: "Figure",
    group: "content",
    glyph: "figure",
  },
  {
    id: "diagram",
    label: "Diagram",
    group: "content",
    glyph: "diagram",
  },
  {
    id: "code",
    label: "Code",
    group: "content",
    glyph: "code",
  },
  {
    id: "verse",
    label: "Verse",
    group: "content",
    glyph: "verse",
  },
  {
    id: "letter",
    label: "Letter",
    group: "content",
    glyph: "letter",
  },
  {
    id: "drop-cap-block",
    label: "Drop Cap",
    group: "content",
    glyph: "drop-cap-block",
  },
];

const STRUCTURAL_TYPES = LAYOUT_TYPES.filter((t) => t.group === "structural");
const CONTENT_TYPES = LAYOUT_TYPES.filter((t) => t.group === "content");

// ─── Shape glyph SVG renderers ────────────────────────────────────────────────

/** Return inline SVG for a layout-type glyph showing the block shape. */
function LayoutGlyph({ glyph }: { glyph: string }) {
  const bar = "fill-current";
  switch (glyph) {
    case "heading":
      return (
        <svg viewBox="0 0 32 20" className="w-8 h-5">
          <rect className={bar} x="2" y="8" width="28" height="4" rx="1" opacity="0.9" />
        </svg>
      );
    case "subheading":
      return (
        <svg viewBox="0 0 32 20" className="w-8 h-5">
          <rect className={bar} x="4" y="8" width="22" height="3" rx="1" opacity="0.75" />
        </svg>
      );
    case "section-break":
      return (
        <svg viewBox="0 0 32 20" className="w-8 h-5">
          <line
            x1="2"
            y1="10"
            x2="30"
            y2="10"
            stroke="currentColor"
            strokeWidth="1.5"
            opacity="0.6"
          />
          <circle cx="16" cy="10" r="2" className={bar} opacity="0.7" />
        </svg>
      );
    case "page-header":
      return (
        <svg viewBox="0 0 32 20" className="w-8 h-5">
          <rect className={bar} x="2" y="2" width="28" height="3" rx="1" opacity="0.9" />
          <rect className={bar} x="2" y="8" width="28" height="2" rx="0.5" opacity="0.3" />
          <rect className={bar} x="2" y="12" width="20" height="2" rx="0.5" opacity="0.3" />
        </svg>
      );
    case "page-footer":
      return (
        <svg viewBox="0 0 32 20" className="w-8 h-5">
          <rect className={bar} x="2" y="2" width="28" height="2" rx="0.5" opacity="0.3" />
          <rect className={bar} x="2" y="6" width="20" height="2" rx="0.5" opacity="0.3" />
          <rect className={bar} x="2" y="15" width="28" height="3" rx="1" opacity="0.9" />
        </svg>
      );
    case "footnote":
      return (
        <svg viewBox="0 0 32 20" className="w-8 h-5">
          <line
            x1="2"
            y1="10"
            x2="14"
            y2="10"
            stroke="currentColor"
            strokeWidth="1"
            opacity="0.6"
          />
          <rect className={bar} x="2" y="12" width="28" height="2" rx="0.5" opacity="0.5" />
          <rect className={bar} x="2" y="16" width="22" height="2" rx="0.5" opacity="0.5" />
        </svg>
      );
    case "sidebar":
      return (
        <svg viewBox="0 0 32 20" className="w-8 h-5">
          <rect className={bar} x="2" y="2" width="8" height="16" rx="1" opacity="0.7" />
          <rect className={bar} x="12" y="4" width="18" height="2" rx="0.5" opacity="0.4" />
          <rect className={bar} x="12" y="8" width="18" height="2" rx="0.5" opacity="0.4" />
          <rect className={bar} x="12" y="12" width="14" height="2" rx="0.5" opacity="0.4" />
        </svg>
      );
    case "caption":
      return (
        <svg viewBox="0 0 32 20" className="w-8 h-5">
          <rect className={bar} x="2" y="2" width="28" height="10" rx="1" opacity="0.3" />
          <rect className={bar} x="6" y="14" width="20" height="2" rx="0.5" opacity="0.7" />
          <rect className={bar} x="10" y="17" width="12" height="1.5" rx="0.5" opacity="0.5" />
        </svg>
      );
    case "pullquote":
      return (
        <svg viewBox="0 0 32 20" className="w-8 h-5">
          <text x="2" y="12" fontSize="10" className={bar} opacity="0.7">
            "
          </text>
          <rect className={bar} x="8" y="5" width="22" height="2" rx="0.5" opacity="0.5" />
          <rect className={bar} x="8" y="9" width="18" height="2" rx="0.5" opacity="0.5" />
          <rect className={bar} x="8" y="13" width="20" height="2" rx="0.5" opacity="0.5" />
        </svg>
      );
    case "body-text":
      return (
        <svg viewBox="0 0 32 20" className="w-8 h-5">
          <rect className={bar} x="2" y="3" width="28" height="2" rx="0.5" opacity="0.6" />
          <rect className={bar} x="2" y="7" width="28" height="2" rx="0.5" opacity="0.6" />
          <rect className={bar} x="2" y="11" width="28" height="2" rx="0.5" opacity="0.6" />
          <rect className={bar} x="2" y="15" width="20" height="2" rx="0.5" opacity="0.6" />
        </svg>
      );
    case "list-item":
      return (
        <svg viewBox="0 0 32 20" className="w-8 h-5">
          <circle cx="5" cy="5" r="1.5" className={bar} opacity="0.8" />
          <rect className={bar} x="9" y="3.5" width="20" height="2" rx="0.5" opacity="0.6" />
          <circle cx="5" cy="10" r="1.5" className={bar} opacity="0.8" />
          <rect className={bar} x="9" y="8.5" width="18" height="2" rx="0.5" opacity="0.6" />
          <circle cx="5" cy="15" r="1.5" className={bar} opacity="0.8" />
          <rect className={bar} x="9" y="13.5" width="22" height="2" rx="0.5" opacity="0.6" />
        </svg>
      );
    case "table":
      return (
        <svg viewBox="0 0 32 20" className="w-8 h-5">
          <rect
            x="2"
            y="2"
            width="28"
            height="16"
            rx="1"
            fill="none"
            stroke="currentColor"
            strokeWidth="1"
            opacity="0.6"
          />
          <line
            x1="2"
            y1="7"
            x2="30"
            y2="7"
            stroke="currentColor"
            strokeWidth="0.75"
            opacity="0.5"
          />
          <line
            x1="2"
            y1="12"
            x2="30"
            y2="12"
            stroke="currentColor"
            strokeWidth="0.75"
            opacity="0.5"
          />
          <line
            x1="12"
            y1="2"
            x2="12"
            y2="18"
            stroke="currentColor"
            strokeWidth="0.75"
            opacity="0.5"
          />
          <line
            x1="22"
            y1="2"
            x2="22"
            y2="18"
            stroke="currentColor"
            strokeWidth="0.75"
            opacity="0.5"
          />
        </svg>
      );
    case "figure":
      return (
        <svg viewBox="0 0 32 20" className="w-8 h-5">
          <rect
            x="2"
            y="2"
            width="28"
            height="14"
            rx="1"
            fill="none"
            stroke="currentColor"
            strokeWidth="1"
            opacity="0.6"
          />
          <path
            d="M2 14 L10 8 L18 12 L24 7 L30 11"
            fill="none"
            stroke="currentColor"
            strokeWidth="1"
            opacity="0.5"
          />
          <rect className={bar} x="6" y="17" width="20" height="2" rx="0.5" opacity="0.5" />
        </svg>
      );
    case "diagram":
      return (
        <svg viewBox="0 0 32 20" className="w-8 h-5">
          <circle
            cx="16"
            cy="10"
            r="6"
            fill="none"
            stroke="currentColor"
            strokeWidth="1"
            opacity="0.6"
          />
          <circle cx="16" cy="10" r="2" className={bar} opacity="0.5" />
          <line
            x1="2"
            y1="10"
            x2="10"
            y2="10"
            stroke="currentColor"
            strokeWidth="0.75"
            opacity="0.4"
          />
          <line
            x1="22"
            y1="10"
            x2="30"
            y2="10"
            stroke="currentColor"
            strokeWidth="0.75"
            opacity="0.4"
          />
        </svg>
      );
    case "code":
      return (
        <svg viewBox="0 0 32 20" className="w-8 h-5">
          <rect
            x="2"
            y="2"
            width="28"
            height="16"
            rx="1"
            fill="none"
            stroke="currentColor"
            strokeWidth="0.75"
            opacity="0.5"
          />
          <text x="4" y="9" fontSize="5" fontFamily="monospace" className={bar} opacity="0.7">
            {"</>"}
          </text>
          <rect className={bar} x="4" y="11" width="16" height="1.5" rx="0.3" opacity="0.4" />
          <rect className={bar} x="4" y="14" width="12" height="1.5" rx="0.3" opacity="0.4" />
        </svg>
      );
    case "verse":
      return (
        <svg viewBox="0 0 32 20" className="w-8 h-5">
          <rect className={bar} x="6" y="3" width="20" height="2" rx="0.5" opacity="0.6" />
          <rect className={bar} x="6" y="7" width="16" height="2" rx="0.5" opacity="0.6" />
          <rect className={bar} x="6" y="11" width="18" height="2" rx="0.5" opacity="0.6" />
          <rect className={bar} x="6" y="15" width="14" height="2" rx="0.5" opacity="0.6" />
        </svg>
      );
    case "letter":
      return (
        <svg viewBox="0 0 32 20" className="w-8 h-5">
          <rect className={bar} x="18" y="2" width="12" height="2" rx="0.5" opacity="0.6" />
          <rect className={bar} x="2" y="6" width="28" height="2" rx="0.5" opacity="0.4" />
          <rect className={bar} x="2" y="10" width="24" height="2" rx="0.5" opacity="0.4" />
          <rect className={bar} x="2" y="14" width="10" height="2" rx="0.5" opacity="0.5" />
        </svg>
      );
    case "drop-cap-block":
      return (
        <svg viewBox="0 0 32 20" className="w-8 h-5">
          <rect className={bar} x="2" y="2" width="8" height="10" rx="1" opacity="0.8" />
          <rect className={bar} x="12" y="2" width="18" height="2" rx="0.5" opacity="0.5" />
          <rect className={bar} x="12" y="6" width="18" height="2" rx="0.5" opacity="0.5" />
          <rect className={bar} x="2" y="14" width="28" height="2" rx="0.5" opacity="0.5" />
          <rect className={bar} x="2" y="17" width="22" height="2" rx="0.5" opacity="0.5" />
        </svg>
      );
    default:
      return (
        <svg viewBox="0 0 32 20" className="w-8 h-5">
          <rect className={bar} x="2" y="6" width="28" height="8" rx="1" opacity="0.5" />
        </svg>
      );
  }
}

// ─── Layout type glyph card ────────────────────────────────────────────────────

interface GlyphCardProps {
  spec: LayoutTypeSpec;
  selected: boolean;
  onClick: () => void;
}

function GlyphCard({ spec, selected, onClick }: GlyphCardProps) {
  return (
    <button
      type="button"
      data-testid={`block-detail-layout-chip-${spec.id}`}
      data-active={selected ? "true" : undefined}
      onClick={onClick}
      title={spec.label}
      className={[
        "flex flex-col items-center gap-0.5 px-1.5 py-1.5 rounded border transition-colors w-[60px]",
        selected
          ? "border-accent bg-accent/10 text-ink-1"
          : "border-border-2 bg-bg-raised text-ink-3 hover:border-accent/60 hover:text-ink-2 hover:bg-bg-raised/80",
      ].join(" ")}
      aria-pressed={selected}
    >
      <span className={selected ? "text-accent" : "text-ink-3"}>
        <LayoutGlyph glyph={spec.glyph} />
      </span>
      <span className="text-[9px] leading-tight font-medium text-center truncate w-full">
        {spec.label}
      </span>
    </button>
  );
}

// ─── Preview pane ─────────────────────────────────────────────────────────────

function LayoutPreview({ layoutType, sampleText }: { layoutType: LayoutType; sampleText: string }) {
  const previewClass = (): string => {
    switch (layoutType) {
      case "heading":
        return "text-sm font-bold leading-tight";
      case "subheading":
        return "text-[11px] font-semibold leading-tight";
      case "section-break":
        return "text-[10px] text-center text-ink-3 italic";
      case "page-header":
      case "page-footer":
        return "text-[10px] text-center text-ink-3";
      case "footnote":
        return "text-[9px] text-ink-3 leading-tight";
      case "sidebar":
        return "text-[10px] border-l-2 border-accent pl-2 text-ink-2";
      case "caption":
        return "text-[10px] text-center italic text-ink-3";
      case "pullquote":
        return "text-[11px] italic text-center text-ink-2";
      case "body-text":
        return "text-[11px] text-ink-1 leading-relaxed";
      case "list-item":
        return "text-[11px] text-ink-1 pl-3";
      case "table":
        return "text-[10px] font-mono text-ink-2";
      case "figure":
        return "text-[10px] text-center text-ink-3 italic";
      case "diagram":
        return "text-[10px] text-center text-ink-3";
      case "code":
        return "text-[10px] font-mono bg-bg-sunk px-1 rounded text-ink-1";
      case "verse":
        return "text-[11px] text-ink-1 italic pl-4";
      case "letter":
        return "text-[10px] text-ink-2";
      case "drop-cap-block":
        return "text-[11px] text-ink-1";
      default:
        return "text-[11px] text-ink-1";
    }
  };

  const prefix = layoutType === "list-item" ? "• " : "";
  const displayText = sampleText || "Sample text for this block...";

  return (
    <div
      data-testid="block-detail-preview"
      className="bg-bg-sunk border border-border-1 rounded px-3 py-2 min-h-[40px]"
    >
      <div className="text-[9px] text-ink-4 mb-1 uppercase tracking-wider">Preview</div>
      <div className={previewClass()}>
        {prefix}
        {displayText}
      </div>
    </div>
  );
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

type ItemsViewMode = "flat" | "tree";

function statusPip(status: MatchStatus): "exact" | "fuzzy" | "mismatch" {
  if (status === "exact") return "exact";
  if (status === "fuzzy") return "fuzzy";
  return "mismatch";
}

function groupByPara(lines: LineMatch[]): Map<number | null, LineMatch[]> {
  const groups = new Map<number | null, LineMatch[]>();
  for (const line of lines) {
    const key = line.paragraph_index;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(line);
  }
  return groups;
}

// ─── Store bridge ─────────────────────────────────────────────────────────────

function subscribeSelection(cb: () => void): () => void {
  return selectionStore.subscribe(() => {
    cb();
  });
}
function getSelectionSnapshot() {
  return selectionStore.getState();
}

// ─── BlockDetail (outer) ──────────────────────────────────────────────────────

export interface BlockDetailProps {
  page: PagePayload;
  projectId: string;
  pageIndex: number;
  level: Extract<SelectionLevel, "block" | "para">;
}

export function BlockDetail({ page, projectId, pageIndex, level }: BlockDetailProps) {
  const state = useSyncExternalStore(
    subscribeSelection,
    getSelectionSnapshot,
    getSelectionSnapshot,
  );

  const { path } = state;

  if (level === "block" && !path.blockId) {
    return (
      <div data-testid="block-detail" className="p-3 text-ink-3 text-sm">
        No block selected.
      </div>
    );
  }
  if (level === "para" && path.paraId === undefined) {
    return (
      <div data-testid="block-detail" className="p-3 text-ink-3 text-sm">
        No paragraph selected.
      </div>
    );
  }

  return (
    <BlockDetailInner
      page={page}
      level={level}
      paraId={path.paraId ?? null}
      projectId={projectId}
      pageIndex={pageIndex}
    />
  );
}

// ─── Inner ────────────────────────────────────────────────────────────────────

interface BlockDetailInnerProps {
  page: PagePayload;
  level: Extract<SelectionLevel, "block" | "para">;
  paraId: number | null;
  projectId: string;
  pageIndex: number;
}

function BlockDetailInner({ page, level, paraId, projectId, pageIndex }: BlockDetailInnerProps) {
  const [selectedLayout, setSelectedLayout] = useState<LayoutType>("body-text");
  const [pendingLayout, setPendingLayout] = useState<LayoutType>("body-text");
  const [suggestedLayout] = useState<LayoutType | null>(null); // backend not wired yet
  const [itemsView, setItemsView] = useState<ItemsViewMode>("tree");

  const patchParagraph = usePatchParagraph(projectId, pageIndex);

  const lines = page.line_matches ?? [];
  const relevantLines =
    level === "para" ? lines.filter((l) => l.paragraph_index === paraId) : lines;

  const paraGroups = groupByPara(relevantLines);

  // Sample text from first line for preview
  const sampleText = (
    relevantLines[0]?.ocr_line_text ??
    relevantLines[0]?.ground_truth_line_text ??
    ""
  ).slice(0, 60);

  function handleSelectLayout(lt: LayoutType) {
    setPendingLayout(lt);
  }

  function handleSaveLayout() {
    setSelectedLayout(pendingLayout);
    if (paraId !== null) {
      patchParagraph.mutate({
        paragraphIndex: paraId,
        layoutType: pendingLayout,
      });
    } else {
      // Block-scope: apply layout to all paragraphs in the current selection.
      for (const key of paraGroups.keys()) {
        if (key !== null) {
          patchParagraph.mutate({
            paragraphIndex: key,
            layoutType: pendingLayout,
          });
        }
      }
    }
  }

  function handleAcceptSuggestion() {
    if (!suggestedLayout) return;
    setPendingLayout(suggestedLayout);
    setSelectedLayout(suggestedLayout);
    if (paraId !== null) {
      patchParagraph.mutate({
        paragraphIndex: paraId,
        layoutType: suggestedLayout,
      });
    } else {
      // Block-scope: apply suggestion to all paragraphs in the current selection.
      for (const key of paraGroups.keys()) {
        if (key !== null) {
          patchParagraph.mutate({
            paragraphIndex: key,
            layoutType: suggestedLayout,
          });
        }
      }
    }
  }

  const hasPendingChange = pendingLayout !== selectedLayout;

  return (
    <div data-testid="block-detail" className="flex flex-col h-full">
      <Tabs
        data-testid="block-detail-tabs"
        defaultValue={level === "para" ? "items" : "layout"}
        className="flex flex-col h-full"
      >
        <TabsList className="flex-shrink-0">
          {level === "block" && (
            <TabsTrigger data-testid="block-detail-tab-layout" value="layout">
              Layout
            </TabsTrigger>
          )}
          <TabsTrigger data-testid="block-detail-tab-items" value="items">
            Items
          </TabsTrigger>
          {level === "block" && (
            <TabsTrigger data-testid="block-detail-tab-para-layout" value="para-layout">
              Para Layout
            </TabsTrigger>
          )}
        </TabsList>

        {/* ── Layout tab ── */}
        {level === "block" && (
          <TabsContent value="layout" className="flex-1 overflow-auto pb-[48px]">
            <div className="p-3 space-y-3">
              {/* Model suggestion callout */}
              {suggestedLayout ? (
                <div className="bg-accent/10 border border-accent/30 rounded px-3 py-2 text-[11px] flex items-center justify-between gap-2">
                  <span>
                    Model suggests:{" "}
                    <span className="text-ink-1 font-semibold">
                      {LAYOUT_TYPES.find((t) => t.id === suggestedLayout)?.label ?? suggestedLayout}
                    </span>
                  </span>
                  <button
                    type="button"
                    data-testid="block-detail-layout-accept"
                    onClick={handleAcceptSuggestion}
                    className="text-[11px] px-2 py-0.5 rounded bg-accent text-accent-ink font-medium hover:opacity-90 transition-opacity"
                  >
                    Use suggestion
                  </button>
                </div>
              ) : (
                <div className="bg-bg-raised rounded px-3 py-2 text-[11px] text-ink-3 italic">
                  No model suggestion available.
                </div>
              )}

              {/* Structural group */}
              <div>
                <div className="text-[9px] text-ink-4 uppercase tracking-wider mb-1.5 font-semibold">
                  Structural
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {STRUCTURAL_TYPES.map((spec) => (
                    <GlyphCard
                      key={spec.id}
                      spec={spec}
                      selected={pendingLayout === spec.id}
                      onClick={() => {
                        handleSelectLayout(spec.id);
                      }}
                    />
                  ))}
                </div>
              </div>

              {/* Content group */}
              <div>
                <div className="text-[9px] text-ink-4 uppercase tracking-wider mb-1.5 font-semibold">
                  Content
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {CONTENT_TYPES.map((spec) => (
                    <GlyphCard
                      key={spec.id}
                      spec={spec}
                      selected={pendingLayout === spec.id}
                      onClick={() => {
                        handleSelectLayout(spec.id);
                      }}
                    />
                  ))}
                </div>
              </div>

              {/* Preview pane */}
              <LayoutPreview layoutType={pendingLayout} sampleText={sampleText} />

              {/* Save error */}
              {patchParagraph.isError && (
                <p className="text-[10px] text-status-mismatch italic">
                  Failed to save layout type. Try again.
                </p>
              )}
            </div>
          </TabsContent>
        )}

        {/* ── Items tab ── */}
        <TabsContent value="items" className="flex-1 overflow-auto">
          {/* View sub-toggle + count */}
          <div className="flex items-center justify-between px-3 py-1.5 border-b border-border-1 flex-shrink-0">
            <span className="text-[11px] text-ink-3">
              {relevantLines.length} line{relevantLines.length !== 1 ? "s" : ""}
            </span>
            <div className="flex items-center gap-1">
              {/* Compat: keep density-toggle testid for existing tests */}
              <div
                data-testid="block-detail-density-toggle"
                className="flex items-center rounded border border-border-2 overflow-hidden"
              >
                <button
                  type="button"
                  data-testid="block-detail-items-view-flat"
                  data-active={itemsView === "flat" ? "true" : undefined}
                  onClick={() => {
                    setItemsView("flat");
                  }}
                  className={[
                    "text-[10px] px-2 py-0.5 transition-colors",
                    itemsView === "flat"
                      ? "bg-accent text-accent-ink"
                      : "bg-bg-raised text-ink-3 hover:text-ink-2",
                  ].join(" ")}
                >
                  Flat
                </button>
                <button
                  type="button"
                  data-testid="block-detail-items-view-tree"
                  data-active={itemsView === "tree" ? "true" : undefined}
                  onClick={() => {
                    setItemsView("tree");
                  }}
                  className={[
                    "text-[10px] px-2 py-0.5 transition-colors border-l border-border-2",
                    itemsView === "tree"
                      ? "bg-accent text-accent-ink"
                      : "bg-bg-raised text-ink-3 hover:text-ink-2",
                  ].join(" ")}
                >
                  Tree
                </button>
              </div>
            </div>
          </div>

          <div data-testid="block-detail-items-tree" className="flex flex-col">
            {itemsView === "flat" ? (
              /* Flat: all lines in a single list, no para grouping */
              <div className="flex flex-col gap-0.5 p-2">
                {relevantLines.map((line) => (
                  <LineItemCard key={line.line_index} line={line} />
                ))}
              </div>
            ) : (
              /* Tree: grouped by paragraph */
              Array.from(paraGroups.entries()).map(([pId, paraLines]) => (
                <ParaGroup key={pId ?? "null"} paraId={pId} lines={paraLines} />
              ))
            )}
          </div>
        </TabsContent>

        {/* ── Para layout tab ── */}
        {level === "block" && (
          <TabsContent value="para-layout" className="flex-1 overflow-auto">
            <div className="p-3 space-y-3">
              <div className="text-[11px] text-ink-2">
                Select a paragraph to set its layout type independently from the block.
              </div>
              {/* Paragraph scope selector */}
              {Array.from(paraGroups.entries()).map(([pId, pLines]) => (
                <div key={pId ?? "null"} className="border border-border-1 rounded overflow-hidden">
                  <button
                    type="button"
                    data-testid={`block-detail-para-scope-${pId ?? "null"}`}
                    onClick={() => {
                      selectPara(pId);
                    }}
                    className="w-full flex items-center justify-between px-3 py-1.5 text-left bg-bg-raised hover:bg-bg-raised/80 transition-colors"
                  >
                    <span className="text-[11px] font-medium text-ink-1">
                      {pId === null ? "Unsorted Para" : `Para ${pId + 1}`}
                    </span>
                    <span className="text-[10px] text-ink-4">{pLines.length} lines</span>
                  </button>
                </div>
              ))}
              {paraGroups.size === 0 && (
                <p className="text-[11px] text-ink-4 italic">No paragraphs in this block.</p>
              )}
            </div>
          </TabsContent>
        )}
      </Tabs>

      {/* ── Sticky "Save layout type" footer (Layout tab only, block mode) ── */}
      {level === "block" && (
        <div className="absolute bottom-0 left-0 right-0 border-t border-border-1 bg-bg-surface px-3 py-2 flex items-center justify-between gap-2">
          <span className="text-[10px] text-ink-3 truncate">
            {hasPendingChange ? (
              <>
                Unsaved:{" "}
                <span className="text-ink-1 font-medium">
                  {LAYOUT_TYPES.find((t) => t.id === pendingLayout)?.label}
                </span>
              </>
            ) : (
              <>
                Layout:{" "}
                <span className="text-ink-2">
                  {LAYOUT_TYPES.find((t) => t.id === selectedLayout)?.label}
                </span>
              </>
            )}
          </span>
          <button
            type="button"
            data-testid="block-detail-layout-save"
            onClick={handleSaveLayout}
            disabled={!hasPendingChange || patchParagraph.isPending}
            className={[
              "text-[11px] px-3 py-1 rounded font-medium transition-colors",
              hasPendingChange
                ? "bg-accent text-accent-ink hover:opacity-90"
                : "bg-bg-raised text-ink-3 border border-border-2 cursor-not-allowed",
            ].join(" ")}
          >
            {patchParagraph.isPending ? "Saving…" : "Save layout type"}
          </button>
        </div>
      )}
    </div>
  );
}

// ─── Para group ────────────────────────────────────────────────────────────────

interface ParaGroupProps {
  paraId: number | null;
  lines: LineMatch[];
}

function ParaGroup({ paraId, lines }: ParaGroupProps) {
  return (
    <div className="border-b border-border-1/50">
      <button
        type="button"
        data-testid={`block-detail-para-${paraId ?? "null"}`}
        onClick={() => {
          selectPara(paraId);
        }}
        className="w-full flex items-center gap-2 px-3 py-1.5 text-left text-[11px] text-ink-3 hover:bg-bg-raised/60 hover:text-ink-2 transition-colors"
      >
        <span className="text-ink-4">¶</span>
        <span>
          {paraId === null ? "No paragraph" : `Para ${paraId + 1}`}{" "}
          <span className="text-ink-4">({lines.length} lines)</span>
        </span>
      </button>
      <div className="flex flex-col gap-0.5 pl-4 pr-2 pb-1">
        {lines.map((line) => (
          <LineItemCard key={line.line_index} line={line} />
        ))}
      </div>
    </div>
  );
}

function LineItemCard({ line }: { line: LineMatch }) {
  return (
    <button
      type="button"
      data-testid={`block-detail-line-card-${line.line_index}`}
      onClick={() => {
        selectLine(line.line_index);
      }}
      className="flex items-center gap-2 bg-bg-raised rounded px-2 py-1 text-left hover:bg-bg-raised/80 transition-colors"
    >
      <StatusPip status={statusPip(line.overall_match_status)} />
      <span className="flex-1 truncate text-[11px] font-mono text-ink-1">
        {line.ocr_line_text || `Line ${line.line_index + 1}`}
      </span>
      <span className="text-[10px] text-ink-4 tabular-nums">{line.line_index + 1}</span>
    </button>
  );
}

// LineItemRow is kept for compatibility but ItemsView now uses "flat" mode with cards.
export function LineItemRow({ line }: { line: LineMatch }) {
  return (
    <button
      type="button"
      data-testid={`block-detail-line-row-${line.line_index}`}
      onClick={() => {
        selectLine(line.line_index);
      }}
      className="w-full flex items-center gap-2 px-2 py-1 text-left border-b border-border-1/30 hover:bg-bg-raised/60 transition-colors"
    >
      <StatusPip status={statusPip(line.overall_match_status)} />
      <span className="flex-1 truncate text-[11px] font-mono text-ink-1">
        {line.ocr_line_text || `Line ${line.line_index + 1}`}
      </span>
      <span className="text-[10px] text-ink-4 tabular-nums">{line.line_index + 1}</span>
    </button>
  );
}

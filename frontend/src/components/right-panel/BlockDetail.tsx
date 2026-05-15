// BlockDetail.tsx — Block-level (and para-level) right panel.
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 22.
//
// "Layout" tab: layout-type radio chips + model suggestion callout.
//   Layout-type saves via PATCH .../paragraphs/{pi} (FO-1).
// "Items" tab: tree of paras + lines, density toggle; click sets selection.
//
// Para mode: `level === "para"` — same Items rendering, no Layout tab header.
//
// data-testids:
//   block-detail                — outer container
//   block-detail-tabs           — Tabs root
//   block-detail-tab-layout     — Layout tab trigger
//   block-detail-tab-items      — Items tab trigger
//   block-detail-layout-chip-*  — chip for each layout type
//   block-detail-layout-accept  — Accept suggestion button
//   block-detail-items-tree     — Items tree container
//   block-detail-density-toggle — density toggle button

import { useSyncExternalStore, useState } from "react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../ui/tabs";
import { StatusPip } from "../ui/StatusPip";
import {
  selectionStore,
  selectLine,
  selectPara,
  type SelectionLevel,
} from "../../stores/selection-store";
import { useUiPrefs } from "../../stores/ui-prefs";
import { usePatchParagraph } from "../../hooks/useLineMutations";
import type { components } from "../../api/types";

type PagePayload = components["schemas"]["PagePayload"];
type LineMatch = components["schemas"]["LineMatch"];
type MatchStatus = components["schemas"]["MatchStatus"];

// ─── layout types ─────────────────────────────────────────────────────────

type LayoutType = "Body" | "Heading" | "Caption" | "Footnote" | "Quote" | "Other";

const LAYOUT_TYPES: LayoutType[] = ["Body", "Heading", "Caption", "Footnote", "Quote", "Other"];

// ─── helpers ───────────────────────────────────────────────────────────────

type WordDensity = "cards" | "rows";

function statusPip(status: MatchStatus): "exact" | "fuzzy" | "mismatch" {
  if (status === "exact") return "exact";
  if (status === "fuzzy") return "fuzzy";
  return "mismatch";
}

/** Group lines by paragraph_index, returning sorted para groups. */
function groupByPara(lines: LineMatch[]): Map<number | null, LineMatch[]> {
  const groups = new Map<number | null, LineMatch[]>();
  for (const line of lines) {
    const key = line.paragraph_index;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(line);
  }
  return groups;
}

// ─── store bridge ─────────────────────────────────────────────────────────

function subscribeSelection(cb: () => void): () => void {
  return selectionStore.subscribe(() => cb());
}
function getSelectionSnapshot() {
  return selectionStore.getState();
}

// ─── BlockDetail ──────────────────────────────────────────────────────────

export interface BlockDetailProps {
  page: PagePayload;
  projectId: string;
  pageIndex: number;
  /** "block" renders both tabs; "para" renders Items-only (no Layout tab). */
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

// ─── Inner ─────────────────────────────────────────────────────────────────

interface BlockDetailInnerProps {
  page: PagePayload;
  level: Extract<SelectionLevel, "block" | "para">;
  paraId: number | null;
  projectId: string;
  pageIndex: number;
}

function BlockDetailInner({ page, level, paraId, projectId, pageIndex }: BlockDetailInnerProps) {
  const [selectedLayout, setSelectedLayout] = useState<LayoutType>("Body");
  const [suggestedLayout] = useState<LayoutType | null>(null); // backend not wired yet

  const patchParagraph = usePatchParagraph(projectId, pageIndex);

  // Density pref — stored in ui-prefs as "blockItemsDensity".
  // Local state initialized from the store so the component is reactive.
  const [blockDensity, setBlockDensity] = useState<WordDensity>(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    () => ((useUiPrefs.getState() as any).blockItemsDensity as WordDensity) ?? "cards",
  );

  function toggleDensity() {
    const next: WordDensity = blockDensity === "cards" ? "rows" : "cards";
    setBlockDensity(next);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    useUiPrefs.setState({ blockItemsDensity: next } as any);
  }

  // For para mode: only lines in the selected para; for block: all lines.
  const lines = page.line_matches ?? [];
  const relevantLines =
    level === "para" ? lines.filter((l) => l.paragraph_index === paraId) : lines;

  const paraGroups = groupByPara(relevantLines);

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
        </TabsList>

        {/* Layout tab (block only) */}
        {level === "block" && (
          <TabsContent value="layout" className="flex-1 overflow-auto p-3">
            {/* Layout type radio chips */}
            <div className="mb-3">
              <div className="text-[11px] text-ink-3 mb-1.5">Layout type</div>
              <div className="flex flex-wrap gap-1">
                {LAYOUT_TYPES.map((lt) => (
                  <button
                    key={lt}
                    type="button"
                    data-testid={`block-detail-layout-chip-${lt.toLowerCase()}`}
                    data-active={selectedLayout === lt ? "true" : undefined}
                    onClick={() => {
                      setSelectedLayout(lt);
                      if (paraId !== null) {
                        patchParagraph.mutate({
                          paragraphIndex: paraId,
                          layoutType: lt,
                        });
                      }
                    }}
                    className={
                      selectedLayout === lt
                        ? "text-[11px] px-2 py-0.5 rounded-full border bg-accent text-accent-ink border-accent"
                        : "text-[11px] px-2 py-0.5 rounded-full border bg-bg-raised text-ink-2 border-border-2 hover:border-accent hover:text-ink-1 transition-colors"
                    }
                  >
                    {lt}
                  </button>
                ))}
              </div>
            </div>

            {/* Model suggestion callout */}
            {suggestedLayout ? (
              <div className="bg-bg-raised rounded px-3 py-2 text-[11px] text-ink-2 flex items-center justify-between gap-2">
                <span>
                  Model suggested: <span className="text-ink-1 font-medium">{suggestedLayout}</span>
                  <span className="text-ink-3 ml-1">(confidence —%)</span>
                </span>
                <button
                  type="button"
                  data-testid="block-detail-layout-accept"
                  onClick={() => {
                    setSelectedLayout(suggestedLayout);
                    if (paraId !== null) {
                      patchParagraph.mutate({
                        paragraphIndex: paraId,
                        layoutType: suggestedLayout,
                      });
                    }
                  }}
                  className="text-[11px] px-2 py-0.5 rounded bg-accent text-accent-ink"
                >
                  Accept
                </button>
              </div>
            ) : (
              <div className="bg-bg-raised rounded px-3 py-2 text-[11px] text-ink-3">
                No model suggestion available.
              </div>
            )}

            {/* Save feedback */}
            {patchParagraph.isError && (
              <p className="mt-3 text-[10px] text-red-500 italic">
                Failed to save layout type. Try again.
              </p>
            )}
          </TabsContent>
        )}

        {/* Items tab */}
        <TabsContent value="items" className="flex-1 overflow-auto">
          <div className="flex items-center justify-between px-3 py-1.5 border-b border-border-1">
            <span className="text-[11px] text-ink-3">
              {relevantLines.length} line{relevantLines.length !== 1 ? "s" : ""}
            </span>
            <button
              type="button"
              data-testid="block-detail-density-toggle"
              onClick={toggleDensity}
              className="text-[11px] px-2 py-0.5 rounded border border-border-2 text-ink-2 hover:border-accent hover:text-ink-1 transition-colors"
            >
              {blockDensity === "cards" ? "Cards" : "Rows"}
            </button>
          </div>
          <div data-testid="block-detail-items-tree" className="flex flex-col">
            {Array.from(paraGroups.entries()).map(([pId, paraLines]) => (
              <ParaGroup
                key={pId ?? "null"}
                paraId={pId}
                lines={paraLines}
                density={blockDensity}
              />
            ))}
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}

// ─── Para group ────────────────────────────────────────────────────────────

interface ParaGroupProps {
  paraId: number | null;
  lines: LineMatch[];
  density: WordDensity;
}

function ParaGroup({ paraId, lines, density }: ParaGroupProps) {
  return (
    <div className="border-b border-border-1/50">
      {/* Para header */}
      <button
        type="button"
        data-testid={`block-detail-para-${paraId ?? "null"}`}
        onClick={() => selectPara(paraId)}
        className="w-full flex items-center gap-2 px-3 py-1.5 text-left text-[11px] text-ink-3 hover:bg-bg-raised/60 hover:text-ink-2 transition-colors"
      >
        <span className="text-ink-4">¶</span>
        <span>
          {paraId === null ? "No paragraph" : `Para ${paraId + 1}`}{" "}
          <span className="text-ink-4">({lines.length} lines)</span>
        </span>
      </button>

      {/* Lines in this para */}
      {density === "cards" ? (
        <div className="flex flex-col gap-0.5 pl-4 pr-2 pb-1">
          {lines.map((line) => (
            <LineItemCard key={line.line_index} line={line} />
          ))}
        </div>
      ) : (
        <div className="flex flex-col pl-4">
          {lines.map((line) => (
            <LineItemRow key={line.line_index} line={line} />
          ))}
        </div>
      )}
    </div>
  );
}

function LineItemCard({ line }: { line: LineMatch }) {
  return (
    <button
      type="button"
      data-testid={`block-detail-line-card-${line.line_index}`}
      onClick={() => selectLine(line.line_index)}
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

function LineItemRow({ line }: { line: LineMatch }) {
  return (
    <button
      type="button"
      data-testid={`block-detail-line-row-${line.line_index}`}
      onClick={() => selectLine(line.line_index)}
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

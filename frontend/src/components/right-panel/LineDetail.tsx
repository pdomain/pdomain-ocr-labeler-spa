// LineDetail.tsx — Line-level right panel: Line tab + Words tab.
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 21.
//
// "Line" tab: LineCard content + merge-with-line affordance (useLineMutations).
// "Words" tab: word list using WordMatchView styling; density toggle via
//   useUiPrefs key "lineWordsDensity".
//
// data-testids:
//   line-detail              — outer container
//   line-detail-tabs         — Tabs root
//   line-detail-tab-line     — Line tab trigger
//   line-detail-tab-words    — Words tab trigger
//   line-detail-density-toggle — density toggle button

import { useSyncExternalStore, useState } from "react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../ui/tabs";
import { LineCard } from "../LineCard";
import { StatusPip } from "../ui/StatusPip";
import { selectionStore } from "../../stores/selection-store";
import { useUiPrefs } from "../../stores/ui-prefs";
import { useMergeLines, useValidateLine } from "../../hooks/useLineMutations";
import type { components } from "../../api/types";

type PagePayload = components["schemas"]["PagePayload"];
type LineMatch = components["schemas"]["LineMatch"];
type MatchStatus = components["schemas"]["MatchStatus"];

// ─── density toggle ───────────────────────────────────────────────────────

type WordDensity = "cards" | "rows";

function statusPip(status: MatchStatus): "exact" | "fuzzy" | "mismatch" {
  if (status === "exact") return "exact";
  if (status === "fuzzy") return "fuzzy";
  return "mismatch";
}

// ─── store bridge ─────────────────────────────────────────────────────────

function subscribeSelection(cb: () => void): () => void {
  return selectionStore.subscribe(() => cb());
}
function getSelectionSnapshot() {
  return selectionStore.getState();
}

// ─── LineDetail ───────────────────────────────────────────────────────────

export interface LineDetailProps {
  page: PagePayload;
  projectId: string;
  pageIndex: number;
}

export function LineDetail({ page, projectId, pageIndex }: LineDetailProps) {
  const state = useSyncExternalStore(
    subscribeSelection,
    getSelectionSnapshot,
    getSelectionSnapshot,
  );

  const { level, path } = state;

  if (level !== "line" || path.lineId === undefined) {
    return (
      <div data-testid="line-detail" className="p-3 text-ink-3 text-sm">
        No line selected.
      </div>
    );
  }

  const lineId = path.lineId;
  const line = page.line_matches?.find((l) => l.line_index === lineId) ?? null;

  if (!line) {
    return (
      <div data-testid="line-detail" className="p-3 text-ink-3 text-sm">
        Line not found in page data.
      </div>
    );
  }

  return <LineDetailInner line={line} projectId={projectId} pageIndex={pageIndex} />;
}

// ─── Inner (separated so it can read prefs without hook-order issues) ──────

interface LineDetailInnerProps {
  line: LineMatch;
  projectId: string;
  pageIndex: number;
}

function LineDetailInner({ line, projectId, pageIndex }: LineDetailInnerProps) {
  // Density pref — stored in ui-prefs as "lineWordsDensity".
  // Local state initialized from the store so the component is reactive.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [densityPref, setDensityPref] = useState<WordDensity>(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    () => ((useUiPrefs.getState() as any).lineWordsDensity as WordDensity) ?? "cards",
  );

  const validateLine = useValidateLine(projectId, pageIndex);
  const mergeLines = useMergeLines(projectId, pageIndex);

  function toggleDensity() {
    const next: WordDensity = densityPref === "cards" ? "rows" : "cards";
    setDensityPref(next);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    useUiPrefs.setState({ lineWordsDensity: next } as any);
  }

  return (
    <div data-testid="line-detail" className="flex flex-col h-full">
      <Tabs data-testid="line-detail-tabs" defaultValue="line" className="flex flex-col h-full">
        <TabsList className="flex-shrink-0">
          <TabsTrigger data-testid="line-detail-tab-line" value="line">
            Line
          </TabsTrigger>
          <TabsTrigger data-testid="line-detail-tab-words" value="words">
            Words
          </TabsTrigger>
        </TabsList>

        {/* Line tab: LineCard + merge affordance */}
        <TabsContent value="line" className="flex-1 overflow-auto p-0">
          <LineCard
            line={line}
            onValidate={(li, validated) => {
              validateLine.mutate({ lineIndex: li, validated });
            }}
          />
          {/* Merge-with-adjacent-line affordance (FO-3) */}
          <div className="px-3 py-2 flex gap-2 border-t border-border-1">
            <button
              type="button"
              data-testid="line-detail-merge-prev"
              className="text-[11px] px-2 py-1 rounded border border-border-2 text-ink-2 hover:text-ink-1 hover:border-accent transition-colors disabled:opacity-40"
              disabled={line.line_index === 0 || mergeLines.isPending}
              title={line.line_index === 0 ? "No previous line" : "Merge with previous line"}
              onClick={() => mergeLines.mutate({ lineIndex: line.line_index, direction: "prev" })}
            >
              ↑ Merge prev
            </button>
            <button
              type="button"
              data-testid="line-detail-merge-next"
              className="text-[11px] px-2 py-1 rounded border border-border-2 text-ink-2 hover:text-ink-1 hover:border-accent transition-colors disabled:opacity-40"
              disabled={mergeLines.isPending}
              title="Merge with next line"
              onClick={() => mergeLines.mutate({ lineIndex: line.line_index, direction: "next" })}
            >
              ↓ Merge next
            </button>
          </div>
        </TabsContent>

        {/* Words tab: word list + density toggle */}
        <TabsContent value="words" className="flex-1 overflow-auto">
          <div className="flex items-center justify-between px-3 py-1.5 border-b border-border-1">
            <span className="text-[11px] text-ink-3">
              {line.word_matches.length} word{line.word_matches.length !== 1 ? "s" : ""}
            </span>
            <button
              type="button"
              data-testid="line-detail-density-toggle"
              onClick={toggleDensity}
              className="text-[11px] px-2 py-0.5 rounded border border-border-2 text-ink-2 hover:border-accent hover:text-ink-1 transition-colors"
            >
              {densityPref === "cards" ? "Cards" : "Rows"}
            </button>
          </div>

          {densityPref === "cards" ? <WordCardsView line={line} /> : <WordRowsView line={line} />}
        </TabsContent>
      </Tabs>
    </div>
  );
}

// ─── Word sub-views ───────────────────────────────────────────────────────

function WordCardsView({ line }: { line: LineMatch }) {
  return (
    <div className="flex flex-col gap-1 p-2">
      {line.word_matches.map((wm) => (
        <div
          key={wm.word_index}
          data-testid={`line-detail-word-card-${wm.word_index}`}
          className="bg-bg-raised rounded px-2 py-1.5 flex items-center gap-2"
        >
          <StatusPip status={statusPip(wm.match_status)} />
          <span className="flex-1 truncate text-[11px] font-mono text-ink-1">
            {wm.ocr_text || <span className="text-ink-4 italic">∅</span>}
          </span>
          {wm.ground_truth_text && wm.ground_truth_text !== wm.ocr_text && (
            <span className="text-[10px] text-ink-3 font-mono truncate max-w-[8ch]">
              {wm.ground_truth_text}
            </span>
          )}
        </div>
      ))}
    </div>
  );
}

function WordRowsView({ line }: { line: LineMatch }) {
  return (
    <div className="flex flex-col">
      {line.word_matches.map((wm) => (
        <div
          key={wm.word_index}
          data-testid={`line-detail-word-row-${wm.word_index}`}
          className="flex items-center gap-2 px-3 py-1 border-b border-border-1/50 hover:bg-bg-raised/60 transition-colors"
        >
          <StatusPip status={statusPip(wm.match_status)} />
          <span className="flex-1 truncate text-[11px] font-mono text-ink-1">
            {wm.ocr_text || <span className="text-ink-4 italic">∅</span>}
          </span>
        </div>
      ))}
    </div>
  );
}

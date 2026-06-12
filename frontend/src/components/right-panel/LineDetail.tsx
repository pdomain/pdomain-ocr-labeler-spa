// LineDetail.tsx — Line-level right panel: Line tab + Words tab.
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 21, P5.e, P5.f.
//
// P5.e (Gaps 42, 43): "Line" tab redesign:
//   - Structure box (line ID, paragraph context, validation status, word count)
//   - Consolidated GT row: editable input for full line GT text
//   - Validate-all footer button
//
// P5.f (Gaps 44, 45): "Words" tab redesign:
//   - Group header with word count summary
//   - Per-word LineWordsCard with checkbox for bulk selection
//   - Bulk action bar when any words checked
//
// data-testids:
//   line-detail              — outer container
//   line-detail-tabs         — Tabs root
//   line-detail-tab-line     — Line tab trigger
//   line-detail-tab-words    — Words tab trigger
//   line-detail-density-toggle — density toggle button
//   line-detail-structure-box  — structure context (P5.e)
//   line-detail-gt-input       — GT editable input (P5.e)
//   line-detail-validate-all   — validate-all footer button (P5.e)
//   line-detail-bulk-bar       — bulk action bar (P5.f)

import { useSyncExternalStore, useState, useEffect } from "react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../ui/tabs";
import { LineCard } from "../LineCard";
import { StatusPip } from "../ui/StatusPip";
import { LineWordsCard } from "./LineWordsCard";
import { selectionStore, selectWord } from "../../stores/selection-store";
import { useUiPrefs } from "../../stores/ui-prefs";
import {
  useMergeLines,
  useValidateLine,
  useSetLineGt,
  useValidateWords,
  useCopyLineGt,
  useSplitLineAfterWord,
  useSplitLineByWords,
  useDeleteLine,
  useUpdateWordGt,
} from "../../hooks/useLineMutations";
import { useApplyStyle, useApplyComponent } from "../../hooks/useWordMutations";
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
  return selectionStore.subscribe(() => {
    cb();
  });
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

// ─── Structure box (P5.e) ─────────────────────────────────────────────────

interface StructureBoxProps {
  line: LineMatch;
}

function StructureBox({ line }: StructureBoxProps) {
  const pip = statusPip(line.overall_match_status);
  const validatedCount = line.validated_word_count ?? 0;
  const totalCount = line.total_word_count ?? line.word_matches.length;
  const lineNum = line.line_index + 1;
  const paraNum =
    line.paragraph_index !== null && line.paragraph_index !== undefined
      ? line.paragraph_index + 1
      : null;

  return (
    <div
      data-testid="line-detail-structure-box"
      className="flex items-center gap-2 px-3 py-2 border-b border-border-1 bg-bg-raised/50 flex-shrink-0"
    >
      <StatusPip status={pip} />
      <div className="flex flex-col min-w-0">
        <span className="font-mono text-[11px] text-ink-1">
          Line {lineNum}
          {paraNum !== null && <span className="text-ink-3"> · Para {paraNum}</span>}
        </span>
        <span className="text-[10px] text-ink-3">
          {validatedCount}/{totalCount} validated
        </span>
      </div>
    </div>
  );
}

// ─── GT input row (P5.e) ──────────────────────────────────────────────────

interface GTRowProps {
  line: LineMatch;
  projectId: string;
  pageIndex: number;
}

function GTRow({ line, projectId, pageIndex }: GTRowProps) {
  const [gtText, setGtText] = useState(line.ground_truth_line_text ?? "");
  const setLineGt = useSetLineGt(projectId, pageIndex);

  // Sync local state when the server refreshes the line (after a save).
  useEffect(() => {
    setGtText(line.ground_truth_line_text ?? "");
  }, [line.ground_truth_line_text]);

  function commit() {
    const trimmed = gtText.trim();
    const original = (line.ground_truth_line_text ?? "").trim();
    if (trimmed !== original) {
      setLineGt.mutate({ lineIndex: line.line_index, text: trimmed });
    }
  }

  return (
    <div className="px-3 py-2 border-b border-border-1 flex-shrink-0">
      <label
        htmlFor="line-detail-gt-input"
        className="block text-[10px] text-ink-3 mb-1 uppercase tracking-wide"
      >
        Ground Truth
      </label>
      <input
        id="line-detail-gt-input"
        type="text"
        data-testid="line-detail-gt-input"
        value={gtText}
        onChange={(e) => {
          setGtText(e.target.value);
        }}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.currentTarget.blur();
          }
          if (e.key === "Escape") {
            setGtText(line.ground_truth_line_text ?? "");
          }
        }}
        placeholder="Enter ground truth text…"
        className="w-full text-[11px] font-mono bg-bg-surface border border-border-2 rounded px-2 py-1 text-ink-1 focus:outline-none focus:border-accent transition-colors"
        aria-label="Line ground truth text"
      />
      {line.ocr_line_text && (
        <p className="text-[10px] text-ink-3 mt-1 truncate">
          OCR: <span className="font-mono">{line.ocr_line_text}</span>
        </p>
      )}
    </div>
  );
}

// ─── Inner (separated so it can read prefs without hook-order issues) ──────

interface LineDetailInnerProps {
  line: LineMatch;
  projectId: string;
  pageIndex: number;
}

function LineDetailInner({ line, projectId, pageIndex }: LineDetailInnerProps) {
  // Density pref — stored in ui-prefs as "lineWordsDensity".

  const [densityPref, setDensityPref] = useState<WordDensity>(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    () => ((useUiPrefs.getState() as any).lineWordsDensity as WordDensity) ?? "cards",
  );

  // Bulk-selected word indices (P5.f).
  const [checkedWords, setCheckedWords] = useState<Set<number>>(() => new Set());

  const validateLine = useValidateLine(projectId, pageIndex);
  const mergeLines = useMergeLines(projectId, pageIndex);
  const validateWords = useValidateWords(projectId, pageIndex);
  // D2: line-scope copy + split actions.
  const copyLineGt = useCopyLineGt(projectId, pageIndex);
  const splitAfterWord = useSplitLineAfterWord(projectId, pageIndex);
  const splitByWords = useSplitLineByWords(projectId, pageIndex);
  // STB-3: delete action for the embedded LineCard.
  const deleteLine = useDeleteLine(projectId, pageIndex);
  // P1.4 (B-43): tag-chip x removal for the embedded LineCard's WordCells.
  const applyStyle = useApplyStyle(projectId, pageIndex);
  const applyComponent = useApplyComponent(projectId, pageIndex);
  // P1.6 (B-22): per-word GT commit for the embedded LineCard's WordCells.
  const updateWordGt = useUpdateWordGt(projectId, pageIndex);

  function toggleDensity() {
    const next: WordDensity = densityPref === "cards" ? "rows" : "cards";
    setDensityPref(next);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any, @typescript-eslint/no-unsafe-argument
    useUiPrefs.setState({ lineWordsDensity: next } as any);
  }

  function toggleWordCheck(wordIndex: number, checked: boolean) {
    setCheckedWords((prev) => {
      const next = new Set(prev);
      if (checked) next.add(wordIndex);
      else next.delete(wordIndex);
      return next;
    });
  }

  function clearChecked() {
    setCheckedWords(new Set());
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

        {/* Line tab: structure box + GT row + LineCard + validate-all footer + merge */}
        <TabsContent value="line" className="flex-1 overflow-auto p-0 flex flex-col">
          {/* P5.e: structure context box */}
          <StructureBox line={line} />

          {/* P5.e: consolidated GT row */}
          <GTRow line={line} projectId={projectId} pageIndex={pageIndex} />

          {/* Existing line content — STB-3: pass all action handlers */}
          <div className="flex-1 overflow-auto">
            <LineCard
              line={line}
              onValidate={(li, validated) => {
                validateLine.mutate({ lineIndex: li, validated });
              }}
              onCopyGtToOcr={(li) => {
                copyLineGt.mutate({ lineIndex: li, direction: "gt_to_ocr" });
              }}
              onCopyOcrToGt={(li) => {
                copyLineGt.mutate({ lineIndex: li, direction: "ocr_to_gt" });
              }}
              onDelete={(li) => {
                deleteLine.mutate({ lineIndex: li });
              }}
              onEditWord={(li, wi) => {
                selectWord(li, wi);
              }}
              onValidateWord={(li, wi, validated) => {
                // P1.6 (B-21): per-word validate toggle — same mutation the
                // bulk bar and MultiLineDetail word grid use.
                validateWords.mutate({ wordPairs: [[li, wi]], validated });
              }}
              onCommitGt={(_wordId, li, wi, text) => {
                // P1.6 (B-22): per-word GT commit — same mutation the
                // MultiLineDetail word grid uses.
                updateWordGt.mutate({ lineIndex: li, wordIndex: wi, text });
              }}
              onClearWordTag={(li, wi, label, kind) => {
                // P1.4 (B-43): remove the clicked tag for real. Styles go
                // through the style route's enabled:false (remove_style_label);
                // components already supported enabled:false.
                if (kind === "style") {
                  applyStyle.mutate({
                    lineIndex: li,
                    wordIndex: wi,
                    style: label,
                    scope: "whole",
                    enabled: false,
                  });
                } else {
                  applyComponent.mutate({
                    lineIndex: li,
                    wordIndex: wi,
                    component: label,
                    enabled: false,
                  });
                }
              }}
            />
          </div>

          {/* P5.e: validate-all footer + merge */}
          <div className="flex-shrink-0 border-t border-border-1">
            <div className="px-3 py-2">
              <button
                type="button"
                data-testid="line-detail-validate-all"
                onClick={() => {
                  validateLine.mutate({ lineIndex: line.line_index, validated: true });
                }}
                disabled={validateLine.isPending || line.is_fully_validated}
                className="w-full text-[11px] py-1.5 rounded border border-status-exact/60 text-status-exact hover:bg-status-exact/10 transition-colors disabled:opacity-40"
              >
                {line.is_fully_validated
                  ? "All words validated ✓"
                  : "Validate all words in this line"}
              </button>
            </div>

            {/* Merge-with-adjacent-line affordance (FO-3) */}
            <div className="px-3 pb-2 flex gap-2">
              <button
                type="button"
                data-testid="line-detail-merge-prev"
                className="text-[11px] px-2 py-1 rounded border border-border-2 text-ink-2 hover:text-ink-1 hover:border-accent transition-colors disabled:opacity-40"
                disabled={line.line_index === 0 || mergeLines.isPending}
                title={line.line_index === 0 ? "No previous line" : "Merge with previous line"}
                onClick={() => {
                  mergeLines.mutate({ lineIndex: line.line_index, direction: "prev" });
                }}
              >
                ↑ Merge prev
              </button>
              <button
                type="button"
                data-testid="line-detail-merge-next"
                className="text-[11px] px-2 py-1 rounded border border-border-2 text-ink-2 hover:text-ink-1 hover:border-accent transition-colors disabled:opacity-40"
                disabled={mergeLines.isPending}
                title="Merge with next line"
                onClick={() => {
                  mergeLines.mutate({ lineIndex: line.line_index, direction: "next" });
                }}
              >
                ↓ Merge next
              </button>
            </div>
            {mergeLines.isError && (
              <p className="text-[10px] text-status-mismatch italic px-3 pb-2">
                Merge failed. Try again.
              </p>
            )}

            {/* D2: line-scope copy + split actions (backend routes already exist). */}
            <div className="px-3 pb-2 grid grid-cols-2 gap-2">
              <button
                type="button"
                data-testid="line-copy-gt-to-ocr"
                className="text-[11px] px-2 py-1 rounded border border-border-2 text-ink-2 hover:text-ink-1 hover:border-accent transition-colors disabled:opacity-40"
                disabled={copyLineGt.isPending}
                title="Copy ground truth → OCR for every word in this line"
                onClick={() => {
                  copyLineGt.mutate({ lineIndex: line.line_index, direction: "gt_to_ocr" });
                }}
              >
                Copy GT → OCR
              </button>
              <button
                type="button"
                data-testid="line-copy-ocr-to-gt"
                className="text-[11px] px-2 py-1 rounded border border-border-2 text-ink-2 hover:text-ink-1 hover:border-accent transition-colors disabled:opacity-40"
                disabled={copyLineGt.isPending}
                title="Copy OCR → ground truth for every word in this line"
                onClick={() => {
                  copyLineGt.mutate({ lineIndex: line.line_index, direction: "ocr_to_gt" });
                }}
              >
                Copy OCR → GT
              </button>
              <button
                type="button"
                data-testid="line-split-after-word"
                className="text-[11px] px-2 py-1 rounded border border-border-2 text-ink-2 hover:text-ink-1 hover:border-accent transition-colors disabled:opacity-40"
                disabled={splitAfterWord.isPending || line.word_matches.length < 2}
                title="Split this line after its first word"
                onClick={() => {
                  splitAfterWord.mutate({ lineIndex: line.line_index, wordIndex: 0 });
                }}
              >
                Split after word
              </button>
              <button
                type="button"
                data-testid="line-split-by-words"
                className="text-[11px] px-2 py-1 rounded border border-border-2 text-ink-2 hover:text-ink-1 hover:border-accent transition-colors disabled:opacity-40"
                disabled={splitByWords.isPending || line.word_matches.length < 2}
                title="Extract this line's first word into a new line"
                onClick={() => {
                  splitByWords.mutate({ wordKeys: [[line.line_index, 0]] });
                }}
              >
                Split by words
              </button>
            </div>
          </div>
        </TabsContent>

        {/* Words tab: group header + word list + density toggle + bulk action bar */}
        <TabsContent value="words" className="flex-1 overflow-auto flex flex-col">
          {/* P5.f: bulk action bar (shown when any words checked) */}
          {checkedWords.size > 0 && (
            <div
              data-testid="line-detail-bulk-bar"
              className="flex items-center gap-1.5 px-3 py-1.5 border-b border-accent/40 bg-accent/5 flex-shrink-0"
            >
              <span className="text-[10px] text-ink-2 flex-shrink-0">
                {checkedWords.size} selected
              </span>
              <button
                type="button"
                data-testid="line-detail-bulk-validate"
                className="text-[10px] px-1.5 py-0.5 rounded border border-status-exact/60 text-status-exact hover:bg-status-exact/10 transition-colors"
                onClick={() => {
                  const pairs: [number, number][] = Array.from(checkedWords).map(
                    (wi) => [line.line_index, wi] as [number, number],
                  );
                  validateWords.mutate({ wordPairs: pairs, validated: true });
                  clearChecked();
                }}
              >
                Validate selected
              </button>
              <button
                type="button"
                data-testid="line-detail-bulk-skip"
                className="text-[10px] px-1.5 py-0.5 rounded border border-status-fuzzy/60 text-status-fuzzy hover:bg-status-fuzzy/10 transition-colors"
                onClick={() => {
                  const pairs: [number, number][] = Array.from(checkedWords).map(
                    (wi) => [line.line_index, wi] as [number, number],
                  );
                  validateWords.mutate({ wordPairs: pairs, validated: false });
                  clearChecked();
                }}
              >
                Skip selected
              </button>
              <button
                type="button"
                className="ml-auto text-[10px] px-1.5 py-0.5 rounded border border-border-2 text-ink-3 hover:text-ink-1 transition-colors"
                onClick={clearChecked}
                aria-label="Clear selection"
              >
                ✕
              </button>
            </div>
          )}

          {/* Group header */}
          <div className="flex items-center justify-between px-3 py-1.5 border-b border-border-1 flex-shrink-0">
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

          {/* Word list */}
          {densityPref === "cards" ? (
            <WordCardsView
              line={line}
              checkedWords={checkedWords}
              onToggleCheck={toggleWordCheck}
            />
          ) : (
            <WordRowsView line={line} />
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}

// ─── Word sub-views ───────────────────────────────────────────────────────

interface WordCardsViewProps {
  line: LineMatch;
  checkedWords: Set<number>;
  onToggleCheck: (wordIndex: number, checked: boolean) => void;
}

function WordCardsView({ line, checkedWords, onToggleCheck }: WordCardsViewProps) {
  return (
    <div className="flex flex-col gap-1 p-2 overflow-auto flex-1">
      {line.word_matches.map((wm) => (
        <LineWordsCard
          key={wm.word_index}
          word={wm}
          checked={checkedWords.has(wm.word_index ?? 0)}
          onCheckedChange={(checked) => {
            onToggleCheck(wm.word_index ?? 0, checked);
          }}
        />
      ))}
    </div>
  );
}

function WordRowsView({ line }: { line: LineMatch }) {
  return (
    <div className="flex flex-col overflow-auto flex-1">
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

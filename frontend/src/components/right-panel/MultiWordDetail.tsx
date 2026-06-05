// MultiWordDetail.tsx — MUL-1, MUL-2, MUL-3: multi-word selection view grouped by block.
// Spec: docs/specs/2026-06-05-selection-operations-parity.md rows MUL-1/2/3.
//
// Shows all selected words grouped first by block, then by line.
// Provides bulk operations (validate/unvalidate/delete/applyStyle/applyComponent)
// that act on ALL selected words — reusing the same mutation hooks as BulkWordActions.
//
// data-testids:
//   multi-word-detail
//   multi-word-block-{blockIndex}
//   multi-word-block-{blockIndex}-header
//   multi-word-item-{lineIndex}-{wordIndex}
//   multi-word-validate, multi-word-unvalidate, multi-word-delete
//   multi-word-style-select, multi-word-style-apply
//   multi-word-component-select, multi-word-component-apply

import { useState } from "react";
import { useValidateWords, useDeleteWordsBatch } from "../../hooks/useLineMutations";
import { useApplyStyle, useApplyComponent } from "../../hooks/useWordMutations";
import { useLabelVocabulary } from "../../hooks/useLabelVocabulary";
import type { components } from "../../api/types";

type PagePayload = components["schemas"]["PagePayload"];
type LineMatch = components["schemas"]["LineMatch"];

export interface MultiWordDetailProps {
  page: PagePayload;
  projectId: string;
  pageIndex: number;
  selectedWords: [number, number][];
}

// ─── helpers ──────────────────────────────────────────────────────────────────

/** Group [lineIndex, wordIndex] pairs by block_index, preserving insertion order. */
function groupByBlock(
  selectedWords: [number, number][],
  lineMatches: LineMatch[],
): Map<number | null, { lineMatch: LineMatch; wordIndices: number[] }[]> {
  // Map lineIndex → LineMatch for fast lookup
  const lineByIndex = new Map<number, LineMatch>();
  for (const lm of lineMatches) {
    lineByIndex.set(lm.line_index, lm);
  }

  // blockKey → Map<lineIndex, wordIndices[]>
  // Use null for lines without a block_index.
  const blockOrder: (number | null)[] = [];
  const blockMap = new Map<
    number | null,
    Map<number, { lineMatch: LineMatch; wordIndices: number[] }>
  >();

  for (const [lineIdx, wordIdx] of selectedWords) {
    const lm = lineByIndex.get(lineIdx);
    if (!lm) continue;

    const blockKey: number | null = lm.block_index ?? null;

    if (!blockMap.has(blockKey)) {
      blockMap.set(blockKey, new Map());
      blockOrder.push(blockKey);
    }
    const lineMap = blockMap.get(blockKey)!;

    if (!lineMap.has(lineIdx)) {
      lineMap.set(lineIdx, { lineMatch: lm, wordIndices: [] });
    }
    lineMap.get(lineIdx)!.wordIndices.push(wordIdx);
  }

  // Convert inner Map → array in line_index order
  const result = new Map<number | null, { lineMatch: LineMatch; wordIndices: number[] }[]>();
  for (const blockKey of blockOrder) {
    const lineMap = blockMap.get(blockKey)!;
    const lines = Array.from(lineMap.values()).sort(
      (a, b) => a.lineMatch.line_index - b.lineMatch.line_index,
    );
    result.set(blockKey, lines);
  }
  return result;
}

// ─── Component ────────────────────────────────────────────────────────────────

export function MultiWordDetail({
  page,
  projectId,
  pageIndex,
  selectedWords,
}: MultiWordDetailProps) {
  const validateWords = useValidateWords(projectId, pageIndex);
  const deleteWords = useDeleteWordsBatch(projectId, pageIndex);
  const applyStyle = useApplyStyle(projectId, pageIndex);
  const applyComponent = useApplyComponent(projectId, pageIndex);

  const { textStyleLabels, wordComponents } = useLabelVocabulary();
  const styleLabels = textStyleLabels.filter((s) => s !== "regular");

  const [style, setStyle] = useState("");
  const [component, setComponent] = useState("");

  const grouped = groupByBlock(selectedWords, page.line_matches ?? []);

  const btn =
    "text-[11px] px-2 py-1 rounded border border-border-2 text-ink-2 hover:text-ink-1 " +
    "hover:border-accent transition-colors disabled:opacity-40";

  const isPending =
    validateWords.isPending ||
    deleteWords.isPending ||
    applyStyle.isPending ||
    applyComponent.isPending;

  return (
    <div data-testid="multi-word-detail" className="flex flex-col gap-3 p-3 text-xs">
      {/* ── Word groups (by block then by line) ── */}
      {Array.from(grouped.entries()).map(([blockKey, lines]) => {
        const blockTestId =
          blockKey !== null ? `multi-word-block-${blockKey}` : "multi-word-block-null";

        return (
          <div
            key={blockKey ?? "null"}
            data-testid={blockTestId}
            className="flex flex-col gap-1.5 border border-border-1 rounded p-2"
          >
            {/* Block header */}
            <div
              data-testid={`${blockTestId}-header`}
              className="text-[9px] text-ink-4 uppercase tracking-wider font-semibold"
            >
              {blockKey !== null ? `Block ${blockKey}` : "Block (unassigned)"}
            </div>

            {/* Lines within this block */}
            {lines.map(({ lineMatch, wordIndices }) => (
              <div key={lineMatch.line_index} className="flex flex-col gap-0.5 pl-1">
                {/* Line context */}
                <div className="text-[10px] text-ink-3 italic">{lineMatch.ocr_line_text}</div>

                {/* Selected words from this line */}
                <div className="flex flex-wrap gap-1">
                  {wordIndices.map((wordIdx) => {
                    const wordMatch = lineMatch.word_matches.find((w) => w.word_index === wordIdx);
                    return (
                      <span
                        key={wordIdx}
                        data-testid={`multi-word-item-${lineMatch.line_index}-${wordIdx}`}
                        className="px-1.5 py-0.5 rounded bg-bg-raised text-ink-1 border border-border-2 text-[11px]"
                        title={
                          wordMatch?.ground_truth_text &&
                          wordMatch.ground_truth_text !== wordMatch?.ocr_text
                            ? `GT: ${wordMatch.ground_truth_text}`
                            : undefined
                        }
                      >
                        {wordMatch?.ocr_text ?? `[${lineMatch.line_index}:${wordIdx}]`}
                      </span>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        );
      })}

      {/* ── Bulk operations ── */}
      <div className="flex flex-col gap-2 border-t border-border-1 pt-2">
        <span className="text-[9px] text-ink-4 uppercase tracking-wider">
          {selectedWords.length} word{selectedWords.length !== 1 ? "s" : ""} selected
        </span>

        {/* Validate / Unvalidate */}
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            data-testid="multi-word-validate"
            className={btn + " border-status-exact/60 text-status-exact hover:bg-status-exact/10"}
            disabled={isPending}
            title="Validate all selected words"
            onClick={() => {
              validateWords.mutate({ wordPairs: selectedWords, validated: true });
            }}
          >
            Validate
          </button>
          <button
            type="button"
            data-testid="multi-word-unvalidate"
            className={btn}
            disabled={isPending}
            title="Unvalidate all selected words"
            onClick={() => {
              validateWords.mutate({ wordPairs: selectedWords, validated: false });
            }}
          >
            Unvalidate
          </button>
        </div>

        {/* Delete */}
        <button
          type="button"
          data-testid="multi-word-delete"
          className={
            btn + " border-status-mismatch/50 text-status-mismatch hover:bg-status-mismatch/10"
          }
          disabled={isPending}
          title="Delete all selected words"
          onClick={() => {
            deleteWords.mutate({ wordIndices: selectedWords });
          }}
        >
          Delete selected
        </button>

        {/* Apply style */}
        <div className="flex items-center gap-1.5">
          <select
            data-testid="multi-word-style-select"
            aria-label="Text style"
            className="text-[11px] border border-border-2 rounded px-1 py-0.5 bg-bg-sunk flex-1"
            value={style}
            onChange={(e) => {
              setStyle(e.target.value);
            }}
          >
            <option value="" disabled>
              Style…
            </option>
            {styleLabels.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <button
            type="button"
            data-testid="multi-word-style-apply"
            className={btn}
            disabled={!style || isPending}
            title="Apply this style to every selected word"
            onClick={() => {
              if (!style) return;
              for (const [lineIndex, wordIndex] of selectedWords) {
                applyStyle.mutate({ lineIndex, wordIndex, style, scope: "whole" });
              }
            }}
          >
            Apply
          </button>
        </div>

        {/* Apply component */}
        <div className="flex items-center gap-1.5">
          <select
            data-testid="multi-word-component-select"
            aria-label="Word component"
            className="text-[11px] border border-border-2 rounded px-1 py-0.5 bg-bg-sunk flex-1"
            value={component}
            onChange={(e) => {
              setComponent(e.target.value);
            }}
          >
            <option value="" disabled>
              Component…
            </option>
            {wordComponents.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          <button
            type="button"
            data-testid="multi-word-component-apply"
            className={btn}
            disabled={!component || isPending}
            title="Set this component on every selected word"
            onClick={() => {
              if (!component) return;
              for (const [lineIndex, wordIndex] of selectedWords) {
                applyComponent.mutate({ lineIndex, wordIndex, component, enabled: true });
              }
            }}
          >
            Apply
          </button>
        </div>
      </div>
    </div>
  );
}

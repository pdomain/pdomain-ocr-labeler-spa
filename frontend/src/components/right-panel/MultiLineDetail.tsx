// MultiLineDetail.tsx — ML-2 through ML-8: multi-line selection right-panel view.
// Spec: docs/specs/2026-06-10-multi-line-detail.md
//
// Rendered by RightPanel when level === "line" && selectedLines.length > 1.
// Shows one card per selected line (ascending line_index), each with:
//   - Line identity (line index, block/para badge, validated count, ocr_line_text)
//   - Word grid: per-word GT text input, validate button (reused testids from LineDetail)
//   - Per-line ops: Validate-all, Copy GT→OCR, Copy OCR→GT, Delete (ConfirmDialog)
// Plus a sticky bulk bar across all selected lines.
//
// data-testids:
//   multi-line-detail
//   multi-line-card-{lineIndex}       (also data-line-index={lineIndex})
//   multi-line-bulk-bar
//   multi-line-bulk-validate
//   multi-line-bulk-unvalidate
//   multi-line-bulk-copy-ocr-to-gt
//   multi-line-bulk-delete
//   gt-text-input-{lineIndex}-{wordIndex}
//   word-validate-button-{lineIndex}-{wordIndex}
//   line-validate-button-{lineIndex}
//   line-gt-to-ocr-button-{lineIndex}
//   line-ocr-to-gt-button-{lineIndex}
//   line-delete-button-{lineIndex}

import { useState, useEffect, useCallback, useRef } from "react";
import { StatusPip } from "@pdomain/pdomain-ui/primitives";
import {
  useValidateLine,
  useCopyLineGt,
  useDeleteLine,
  useUpdateWordGt,
  useValidateWords,
} from "../../hooks/useLineMutations";
import { dialogStore } from "../../stores/dialog-store";
import { applyLineSelection } from "../../stores/selection-store";
import type { components } from "../../api/types";

type PagePayload = components["schemas"]["PagePayload"];
type LineMatch = components["schemas"]["LineMatch"];
type WordMatch = components["schemas"]["WordMatch"];
type MatchStatus = components["schemas"]["MatchStatus"];

function pipStatus(status: MatchStatus): "exact" | "fuzzy" | "mismatch" {
  if (status === "exact") return "exact";
  if (status === "fuzzy") return "fuzzy";
  return "mismatch";
}

// ─── MultiLineDetail (exported) ──────────────────────────────────────────────

export interface MultiLineDetailProps {
  page: PagePayload;
  projectId: string;
  pageIndex: number;
  selectedLines: number[];
}

export function MultiLineDetail({
  page,
  projectId,
  pageIndex,
  selectedLines,
}: MultiLineDetailProps) {
  const lineMatches = page.line_matches ?? [];
  // Sort lines ascending by line_index for stable card order (ML-2)
  const sortedLineIds = [...selectedLines].sort((a, b) => a - b);
  const selectedLineMatches = sortedLineIds
    .map((id) => lineMatches.find((l) => l.line_index === id))
    .filter((l): l is LineMatch => l !== undefined);

  // ML-5: flat ordered list of all GT inputs for cross-card Tab traversal.
  // Each WordRow registers its input element here on mount.
  const allInputsRef = useRef<HTMLInputElement[]>([]);

  // Bulk mutations
  const validateLine = useValidateLine(projectId, pageIndex);
  const copyLineGt = useCopyLineGt(projectId, pageIndex);
  const deleteLineMut = useDeleteLine(projectId, pageIndex);
  const validateWords = useValidateWords(projectId, pageIndex);

  const isPending =
    validateLine.isPending ||
    copyLineGt.isPending ||
    deleteLineMut.isPending ||
    validateWords.isPending;

  const btn =
    "text-[11px] px-2 py-1 rounded border border-border-2 text-ink-2 hover:text-ink-1 " +
    "hover:border-accent transition-colors disabled:opacity-40";

  function handleBulkValidate(validated: boolean) {
    for (const lineId of sortedLineIds) {
      validateLine.mutate({ lineIndex: lineId, validated });
    }
  }

  function handleBulkCopyOcrToGt() {
    for (const lineId of sortedLineIds) {
      copyLineGt.mutate({ lineIndex: lineId, direction: "ocr_to_gt" });
    }
  }

  function handleBulkDelete() {
    dialogStore.openConfirm({
      title: "Delete lines?",
      body: `This will permanently remove ${sortedLineIds.length} selected lines. This action cannot be undone.`,
      onConfirm: () => {
        for (const lineId of sortedLineIds) {
          deleteLineMut.mutate({ lineIndex: lineId });
        }
        // Remove deleted lines from selection
        applyLineSelection(sortedLineIds, "remove");
      },
    });
  }

  return (
    <div data-testid="multi-line-detail" className="flex flex-col h-full">
      {/* Sticky bulk bar (ML-7) */}
      <div
        data-testid="multi-line-bulk-bar"
        className="flex items-center gap-1.5 px-3 py-1.5 border-b border-accent/40 bg-accent/5 flex-shrink-0 flex-wrap"
      >
        <span className="text-[10px] text-ink-2 flex-shrink-0 font-medium">
          {sortedLineIds.length} line{sortedLineIds.length !== 1 ? "s" : ""} selected
        </span>
        <button
          type="button"
          data-testid="multi-line-bulk-validate"
          className={btn + " border-status-exact/60 text-status-exact hover:bg-status-exact/10"}
          disabled={isPending}
          title="Validate all words in all selected lines"
          onClick={() => {
            handleBulkValidate(true);
          }}
        >
          Validate all
        </button>
        <button
          type="button"
          data-testid="multi-line-bulk-unvalidate"
          className={btn}
          disabled={isPending}
          title="Unvalidate all words in all selected lines"
          onClick={() => {
            handleBulkValidate(false);
          }}
        >
          Unvalidate all
        </button>
        <button
          type="button"
          data-testid="multi-line-bulk-copy-ocr-to-gt"
          className={btn}
          disabled={isPending}
          title="Copy OCR → GT for all selected lines"
          onClick={handleBulkCopyOcrToGt}
        >
          OCR → GT
        </button>
        <button
          type="button"
          data-testid="multi-line-bulk-delete"
          className={
            btn + " border-status-mismatch/50 text-status-mismatch hover:bg-status-mismatch/10"
          }
          disabled={isPending}
          title="Delete all selected lines"
          onClick={handleBulkDelete}
        >
          Delete
        </button>
      </div>

      {/* Line cards (scrollable) */}
      <div className="flex-1 overflow-auto flex flex-col gap-2 p-2">
        {selectedLineMatches.map((line) => (
          <LineCard
            key={line.line_index}
            line={line}
            projectId={projectId}
            pageIndex={pageIndex}
            allInputsRef={allInputsRef}
          />
        ))}
      </div>
    </div>
  );
}

// ─── LineCard (per selected line) ─────────────────────────────────────────────

interface LineCardProps {
  line: LineMatch;
  projectId: string;
  pageIndex: number;
  // ML-5: flat ordered list of all GT inputs across all cards for Tab traversal.
  allInputsRef: React.RefObject<HTMLInputElement[]>;
}

function LineCard({ line, projectId, pageIndex, allInputsRef }: LineCardProps) {
  const validateLine = useValidateLine(projectId, pageIndex);
  const copyLineGt = useCopyLineGt(projectId, pageIndex);
  const deleteLineMut = useDeleteLine(projectId, pageIndex);

  const validatedCount = line.validated_word_count ?? 0;
  const totalCount = line.total_word_count ?? line.word_matches.length;
  const lineNum = line.line_index + 1;
  const paraNum =
    line.paragraph_index !== null && line.paragraph_index !== undefined
      ? line.paragraph_index + 1
      : null;
  const blockNum =
    line.block_index !== null && line.block_index !== undefined ? line.block_index : null;

  function handleDelete() {
    dialogStore.openConfirm({
      title: "Delete line?",
      body: "This will permanently remove the selected line from the page. This action cannot be undone.",
      onConfirm: () => {
        deleteLineMut.mutate({ lineIndex: line.line_index });
        applyLineSelection([line.line_index], "remove");
      },
    });
  }

  const isPending = validateLine.isPending || copyLineGt.isPending || deleteLineMut.isPending;
  const pip = pipStatus(line.overall_match_status);

  return (
    <div
      data-testid={`multi-line-card-${line.line_index}`}
      data-line-index={line.line_index}
      className="flex flex-col border border-border-1 rounded bg-bg-raised/30"
    >
      {/* Card header: line identity */}
      <div className="flex items-center justify-between gap-2 px-3 py-1.5 border-b border-border-1/60">
        <div className="flex items-center gap-2 min-w-0">
          <StatusPip status={pip} />
          <span className="font-mono text-[11px] text-ink-1 flex-shrink-0">Line {lineNum}</span>
          {paraNum !== null && (
            <span className="text-[10px] text-ink-3 flex-shrink-0">· Para {paraNum}</span>
          )}
          {blockNum !== null && (
            <span className="text-[10px] text-ink-3 flex-shrink-0">· Block {blockNum}</span>
          )}
          <span className="text-[10px] text-ink-3 flex-shrink-0">
            {validatedCount}/{totalCount} validated
          </span>
        </div>
        {/* Per-line ops */}
        <div className="flex items-center gap-1 flex-shrink-0">
          <button
            type="button"
            data-testid={`line-validate-button-${line.line_index}`}
            title="Validate all words in this line"
            disabled={isPending || line.is_fully_validated}
            onClick={() => {
              validateLine.mutate({ lineIndex: line.line_index, validated: true });
            }}
            className="text-[10px] px-1.5 py-0.5 rounded border border-status-exact/60 text-status-exact hover:bg-status-exact/10 transition-colors disabled:opacity-40"
          >
            ✓ Val
          </button>
          <button
            type="button"
            data-testid={`line-gt-to-ocr-button-${line.line_index}`}
            title="Copy GT → OCR for this line"
            disabled={isPending}
            onClick={() => {
              copyLineGt.mutate({ lineIndex: line.line_index, direction: "gt_to_ocr" });
            }}
            className="text-[10px] px-1.5 py-0.5 rounded border border-border-2 text-ink-3 hover:text-ink-1 hover:border-accent transition-colors disabled:opacity-40"
          >
            GT→OCR
          </button>
          <button
            type="button"
            data-testid={`line-ocr-to-gt-button-${line.line_index}`}
            title="Copy OCR → GT for this line"
            disabled={isPending}
            onClick={() => {
              copyLineGt.mutate({ lineIndex: line.line_index, direction: "ocr_to_gt" });
            }}
            className="text-[10px] px-1.5 py-0.5 rounded border border-border-2 text-ink-3 hover:text-ink-1 hover:border-accent transition-colors disabled:opacity-40"
          >
            OCR→GT
          </button>
          <button
            type="button"
            data-testid={`line-delete-button-${line.line_index}`}
            title="Delete this line"
            disabled={isPending}
            onClick={handleDelete}
            className="text-[10px] px-1.5 py-0.5 rounded border border-status-mismatch/50 text-status-mismatch hover:bg-status-mismatch/10 transition-colors disabled:opacity-40"
          >
            Del
          </button>
        </div>
      </div>

      {/* OCR text reference */}
      {line.ocr_line_text && (
        <div className="px-3 py-1 text-[10px] text-ink-3 truncate border-b border-border-1/40 font-mono">
          {line.ocr_line_text}
        </div>
      )}

      {/* Word grid (ML-3, ML-4, ML-5) */}
      <div className="flex flex-col gap-0.5 p-2">
        {line.word_matches.map((word) => (
          <WordRow
            key={word.word_index}
            word={word}
            lineIndex={line.line_index}
            projectId={projectId}
            pageIndex={pageIndex}
            allInputsRef={allInputsRef}
          />
        ))}
      </div>
    </div>
  );
}

// ─── WordRow — per-word inline edit row ───────────────────────────────────────

interface WordRowProps {
  word: WordMatch;
  lineIndex: number;
  projectId: string;
  pageIndex: number;
  /** ML-5: flat ordered list of all GT inputs for cross-card Tab traversal. */
  allInputsRef: React.RefObject<HTMLInputElement[]>;
}

function WordRow({ word, lineIndex, projectId, pageIndex, allInputsRef }: WordRowProps) {
  const updateGt = useUpdateWordGt(projectId, pageIndex);
  const validateWords = useValidateWords(projectId, pageIndex);

  const [gtText, setGtText] = useState(word.ground_truth_text ?? "");
  const pip = pipStatus(word.match_status);
  // ML-5: ref for this input — registered in allInputsRef on mount.
  const inputRef = useRef<HTMLInputElement>(null);

  // Sync when server refreshes
  useEffect(() => {
    setGtText(word.ground_truth_text ?? "");
  }, [word.ground_truth_text]);

  // ML-5: register/unregister this input in the flat traversal list.
  useEffect(() => {
    const el = inputRef.current;
    const list = allInputsRef.current;
    if (!el || !list) return;
    // Append to the flat list (render order = DOM order since cards are sorted ascending).
    list.push(el);
    return () => {
      const list2 = allInputsRef.current;
      if (!list2) return;
      const idx = list2.indexOf(el);
      if (idx !== -1) list2.splice(idx, 1);
    };
  }, [allInputsRef]);

  const commit = useCallback(() => {
    const trimmed = gtText.trim();
    const original = (word.ground_truth_text ?? "").trim();
    if (trimmed !== original && word.word_index !== null) {
      updateGt.mutate({ lineIndex, wordIndex: word.word_index, text: trimmed });
    }
  }, [gtText, word.ground_truth_text, word.word_index, lineIndex, updateGt]);

  const wordIdx = word.word_index ?? 0;

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      e.currentTarget.blur();
      return;
    }
    if (e.key === "Escape") {
      setGtText(word.ground_truth_text ?? "");
      return;
    }
    // ML-5: intercept Tab/Shift-Tab to traverse across card boundaries.
    if (e.key === "Tab") {
      const inputs = allInputsRef.current;
      if (!inputs) return;
      const current = e.currentTarget;
      const idx = inputs.indexOf(current);
      if (idx === -1) return;
      const target = e.shiftKey ? inputs[idx - 1] : inputs[idx + 1];
      if (target) {
        e.preventDefault();
        target.focus();
      }
    }
  }

  return (
    <div
      data-testid={`word-image-cell-${lineIndex}-${wordIdx}`}
      className="flex items-center gap-2 py-0.5"
    >
      {/* Status + OCR label */}
      <StatusPip status={pip} />
      <span
        data-testid={`ocr-text-label-${lineIndex}-${wordIdx}`}
        className="text-[10px] font-mono text-ink-3 w-16 truncate flex-shrink-0"
        title={word.ocr_text ?? ""}
      >
        {word.ocr_text || <span className="italic">∅</span>}
      </span>

      {/* GT input (ML-4) */}
      <input
        ref={inputRef}
        type="text"
        data-testid={`gt-text-input-${lineIndex}-${wordIdx}`}
        value={gtText}
        onChange={(e) => {
          setGtText(e.target.value);
        }}
        onBlur={commit}
        onKeyDown={handleKeyDown}
        className="flex-1 min-w-0 text-[11px] font-mono bg-bg-surface border border-border-2 rounded px-1.5 py-0.5 text-ink-1 focus:outline-none focus:border-accent transition-colors"
        aria-label={`GT for word ${wordIdx + 1} in line ${lineIndex + 1}`}
      />

      {/* Validate button */}
      <button
        type="button"
        data-testid={`word-validate-button-${lineIndex}-${wordIdx}`}
        title={word.is_validated ? "Word validated" : "Validate this word"}
        disabled={validateWords.isPending}
        onClick={() => {
          if (word.word_index !== null) {
            validateWords.mutate({
              wordPairs: [[lineIndex, word.word_index]],
              validated: !word.is_validated,
            });
          }
        }}
        className={
          word.is_validated
            ? "text-[10px] px-1.5 py-0.5 rounded border border-status-exact/80 text-status-exact bg-status-exact/10 transition-colors disabled:opacity-40 flex-shrink-0"
            : "text-[10px] px-1.5 py-0.5 rounded border border-border-2 text-ink-3 hover:text-status-exact hover:border-status-exact/60 transition-colors disabled:opacity-40 flex-shrink-0"
        }
      >
        {word.is_validated ? "✓" : "Val"}
      </button>
    </div>
  );
}

// WordEditDialog.tsx — word-edit dialog (#209, #210, #211, #212)
// Spec: docs/specs/2026-05-12-word-edit-dialog-design.md
//
// Slice 20 status: DEMOTED to Esc-fallback. Primary per-character editing
// now lives in CharFixerSection (right-panel). The dialog remains
// mountable via dialogStore.openWordEdit for legacy hotkey paths and the
// driver-contract testids it owns (dialog-*).
//
// Shell (#209): header (Apply&Close + Close), 3-column preview row, prev/next nav.
// Konva image (#210): interactive Stage at 1x/2x/5x/10x zoom, click marker,
//   hover guide, staged erase rects.
// Action rows (#211): Merge/Split/Delete/Crop
// Refine/Nudge/Tag rows (#212): Refine + nudge accumulator + Style/Component tag row
//   + dialog hotkeys (Shift+Arrow nudge).
//
// data-testids (driver-contract):
//   dialog-backdrop, dialog-header-label
//   dialog-apply-close-button, dialog-close-button
//   dialog-prev-button, dialog-next-button
//   dialog-prev-word, dialog-current-word, dialog-next-word
//   dialog-current-zoom-toggle, dialog-current-marker, dialog-hover-guide
//   dialog-erase-rect, dialog-word-stage
//   dialog-refine-button, dialog-expand-refine-button
//   dialog-nudge-{left|right|top|bottom}-{minus|plus}
//   dialog-nudge-display, dialog-reset-button, dialog-apply-button, dialog-apply-refine-button
//   dialog-style-select, dialog-scope-select, dialog-component-select
//   dialog-apply-style-button, dialog-apply-component-button, dialog-clear-component-button

import { useRef, useState } from "react";
import { WordActionRows } from "./WordActionRows";
import type { WordActionCallbacks } from "./WordActionRows";
import { WordImageCanvas } from "./WordImageCanvas";
import type { EraseRect, MarkerPoint } from "./WordImageCanvas";
import { WordRefineNudgeRows } from "./WordRefineNudgeRows";
import type { PendingNudge, WordRefineNudgeRowsHandle } from "./WordRefineNudgeRows";
import { WordTagRow } from "./WordTagRow";

export interface DialogTarget {
  lineIndex: number;
  wordIndex: number;
}

interface WordEditDialogProps extends WordActionCallbacks {
  /** Whether the dialog is visible. */
  open: boolean;
  /** Current word target (line/word indices, 0-based). */
  target: DialogTarget;
  /** OCR text of each word in the current line (for 3-column preview). */
  lineWords: string[];
  /** URL of the current word's image slice (for the Konva canvas). */
  wordImageUrl?: string | undefined;
  /** Whether erase mode is active (toggles Konva drag-erase). */
  eraseMode?: boolean | undefined;
  /** Available style labels for the tag row. */
  styleOptions?: string[] | undefined;
  /** Available component labels for the tag row. */
  componentOptions?: string[] | undefined;
  /** Called when prev/next navigation is requested. */
  onNavigate: (target: DialogTarget) => void;
  /**
   * Called when Apply & Close is clicked (commits pending changes).
   * Passes erase rects, marker position, and accumulated nudge.
   */
  onApply: (eraseRects: EraseRect[], marker: MarkerPoint | null, nudge: PendingNudge) => void;
  /** Called when x Close or backdrop is clicked (discards pending changes). */
  onClose: () => void;
  /** Called when Refine is clicked. */
  onRefine?: () => Promise<void>;
  /** Called when Expand+Refine is clicked. */
  onExpandRefine?: () => Promise<void>;
  /** Called when Apply (nudge only) is clicked. */
  onApplyNudge?: (nudge: PendingNudge, refineAfter: boolean) => Promise<void>;
  /** Called with style + scope when Apply Style is clicked. */
  onApplyStyle?: (style: string, scope: "whole" | "part") => Promise<void>;
  /** Called with component + enabled when Apply/Clear Component is clicked. */
  onApplyComponent?: (component: string, enabled: boolean) => Promise<void>;
}

/**
 * Word-edit dialog shell.
 *
 * Displays a modal with:
 * - Header: title ("Edit Line N, Word M"), Apply & Close button, x Close button.
 * - 3-column preview row: previous word | current word (highlighted) | next word.
 * - Prev/Next navigation within the same line.
 * - Interactive Konva Stage for the current word (#210).
 * - Merge/Split/Delete/Crop rows (#211).
 * - Refine/Nudge/Tag rows + dialog hotkeys (#212).
 *
 * Apply & Close fires onApply (with pending erase rects, marker, and nudge) then onClose.
 * x Close fires onClose only (discards).
 * Backdrop click fires onClose (discards).
 */
export function WordEditDialog({
  open,
  target,
  lineWords,
  wordImageUrl,
  eraseMode = false,
  styleOptions,
  componentOptions,
  onNavigate,
  onApply,
  onClose,
  onMerge,
  onSplit,
  onDelete,
  onCrop,
  onRefine,
  onExpandRefine,
  onApplyNudge,
  onApplyStyle,
  onApplyComponent,
}: WordEditDialogProps) {
  const [eraseRects, setEraseRects] = useState<EraseRect[]>([]);
  const [marker, setMarker] = useState<MarkerPoint | null>(null);
  const nudgeRef = useRef<WordRefineNudgeRowsHandle>(null);

  if (!open) return null;

  const { lineIndex, wordIndex } = target;
  const hasPrev = wordIndex > 0;
  const hasNext = wordIndex < lineWords.length - 1;

  const prevWord = hasPrev ? lineWords[wordIndex - 1] : null;
  const currentWord = lineWords[wordIndex] ?? "";
  const nextWord = hasNext ? lineWords[wordIndex + 1] : null;

  const zeroNudge: PendingNudge = { left: 0, right: 0, top: 0, bottom: 0 };

  function handleApplyClose() {
    const nudge = nudgeRef.current?.getPendingNudge() ?? zeroNudge;
    onApply(eraseRects, marker, nudge);
    onClose();
  }

  function handleEraseRectAdd(rect: EraseRect) {
    setEraseRects((prev) => [...prev, rect]);
  }

  function handlePrev() {
    if (hasPrev) onNavigate({ lineIndex, wordIndex: wordIndex - 1 });
  }

  function handleNext() {
    if (hasNext) onNavigate({ lineIndex, wordIndex: wordIndex + 1 });
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`Edit Line ${lineIndex}, Word ${wordIndex}`}
      data-testid="dialog-backdrop"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="bg-bg-surface rounded-lg border border-border-2 w-full max-w-2xl mx-4 flex flex-col overflow-hidden"
        onClick={(e) => {
          e.stopPropagation();
        }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border-1 bg-bg-raised shrink-0">
          <span data-testid="dialog-header-label" className="text-sm font-semibold text-ink-1">
            Edit Line {lineIndex}, Word {wordIndex}
          </span>
          <div className="flex items-center gap-2">
            <button
              data-testid="dialog-apply-close-button"
              onClick={handleApplyClose}
              title="Apply changes and close (Shift+Enter)"
              className="flex items-center gap-1 px-3 py-1.5 text-sm rounded bg-accent text-accent-ink hover:opacity-90 transition-opacity"
            >
              <span aria-hidden="true">✓</span>
              Apply &amp; Close
            </button>
            <button
              data-testid="dialog-close-button"
              onClick={onClose}
              title="Discard changes and close"
              aria-label="Close dialog"
              className="px-2 py-1.5 text-lg text-ink-3 hover:text-ink-1 hover:bg-bg-raised rounded transition-colors"
            >
              ×
            </button>
          </div>
        </div>

        {/* 3-column preview row */}
        <div className="flex items-stretch gap-2 px-4 py-3 border-b border-border-1 shrink-0">
          {/* Prev word */}
          <div className="flex flex-col items-center gap-1 flex-1">
            <button
              data-testid="dialog-prev-button"
              disabled={!hasPrev}
              onClick={handlePrev}
              title="Previous word (←)"
              className={[
                "px-2 py-1 text-xs rounded border transition-colors",
                hasPrev
                  ? "border-border-2 bg-bg-surface hover:bg-bg-raised text-ink-2"
                  : "border-border-1 bg-bg-raised text-ink-4 cursor-default",
              ].join(" ")}
            >
              ← Prev
            </button>
            <div
              data-testid="dialog-prev-word"
              className={[
                "w-full min-h-[3rem] flex items-center justify-center rounded border p-2 text-sm font-mono",
                "bg-bg-raised text-ink-3 border-border-1",
                !hasPrev ? "opacity-30" : "",
              ].join(" ")}
            >
              {prevWord ?? "–"}
            </div>
          </div>

          {/* Current word (highlighted) */}
          <div className="flex flex-col items-center gap-1 flex-[2]">
            <div className="text-xs text-ink-4 font-medium">Current</div>
            <div
              data-testid="dialog-current-word"
              className="w-full min-h-[3rem] flex items-center justify-center rounded border-2 border-accent p-2 text-sm font-mono font-semibold text-ink-1"
              style={{ background: "color-mix(in srgb, var(--status-ocr) 8%, var(--bg-surface))" }}
            >
              {currentWord}
            </div>
          </div>

          {/* Next word */}
          <div className="flex flex-col items-center gap-1 flex-1">
            <button
              data-testid="dialog-next-button"
              disabled={!hasNext}
              onClick={handleNext}
              title="Next word (→)"
              className={[
                "px-2 py-1 text-xs rounded border transition-colors",
                hasNext
                  ? "border-border-2 bg-bg-surface hover:bg-bg-raised text-ink-2"
                  : "border-border-1 bg-bg-raised text-ink-4 cursor-default",
              ].join(" ")}
            >
              Next →
            </button>
            <div
              data-testid="dialog-next-word"
              className={[
                "w-full min-h-[3rem] flex items-center justify-center rounded border p-2 text-sm font-mono",
                "bg-bg-raised text-ink-3 border-border-1",
                !hasNext ? "opacity-30" : "",
              ].join(" ")}
            >
              {nextWord ?? "–"}
            </div>
          </div>
        </div>

        {/* Konva interactive word image — #210 */}
        <div
          data-testid="dialog-action-rows"
          className="flex-1 p-4 flex flex-col items-center gap-3"
        >
          <WordImageCanvas
            imageUrl={wordImageUrl}
            eraseMode={eraseMode}
            eraseRects={eraseRects}
            onEraseRectAdd={handleEraseRectAdd}
            onMarkerPlace={(pt) => {
              setMarker(pt);
            }}
          />
          {/* Merge/Split/Delete/Crop rows — #211 */}
          <WordActionRows
            hasPrev={wordIndex > 0}
            hasNext={wordIndex < lineWords.length - 1}
            splitFraction={marker ? marker.x / 200 : 0.5}
            onMerge={onMerge}
            onSplit={onSplit}
            onDelete={onDelete}
            onCrop={onCrop}
          />
          {/* Refine/Nudge/Tag rows — #212 */}
          <WordRefineNudgeRows
            ref={nudgeRef}
            onRefine={onRefine}
            onExpandRefine={onExpandRefine}
            onApply={onApplyNudge}
            onReset={() => {
              setEraseRects([]);
            }}
          />
          <WordTagRow
            styleOptions={styleOptions}
            componentOptions={componentOptions}
            onApplyStyle={onApplyStyle}
            onApplyComponent={onApplyComponent}
          />
        </div>
      </div>
    </div>
  );
}

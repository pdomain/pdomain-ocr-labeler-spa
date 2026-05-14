// WordEditDialog.tsx — word-edit dialog shell (#209)
// Spec: docs/specs/2026-05-12-word-edit-dialog-design.md §Header §Preview row
//
// Shell covers: header (Apply&Close + Close), 3-column preview row, prev/next nav.
// Later issues (#210–#212) add Konva image, action rows, hotkeys.
//
// data-testids (driver-contract):
//   dialog-backdrop, dialog-header-label
//   dialog-apply-close-button, dialog-close-button
//   dialog-prev-button, dialog-next-button
//   dialog-prev-word, dialog-current-word, dialog-next-word

export interface DialogTarget {
  lineIndex: number;
  wordIndex: number;
}

interface WordEditDialogProps {
  /** Whether the dialog is visible. */
  open: boolean;
  /** Current word target (line/word indices, 0-based). */
  target: DialogTarget;
  /** OCR text of each word in the current line (for 3-column preview). */
  lineWords: string[];
  /** Called when prev/next navigation is requested. */
  onNavigate: (target: DialogTarget) => void;
  /** Called when Apply & Close is clicked (commits pending changes). */
  onApply: () => void;
  /** Called when × Close or backdrop is clicked (discards pending changes). */
  onClose: () => void;
}

/**
 * Word-edit dialog shell.
 *
 * Displays a modal with:
 * - Header: title ("Edit Line N, Word M"), Apply & Close button, × Close button.
 * - 3-column preview row: previous word | current word (highlighted) | next word.
 * - Prev/Next navigation within the same line.
 *
 * Apply & Close fires onApply then onClose.
 * × Close fires onClose only (discards).
 * Backdrop click fires onClose (discards).
 *
 * #210 will add the interactive Konva Stage for the current word.
 * #211 will add Merge/Split/Delete/Crop rows.
 * #212 will add Refine/Nudge/Tag rows and dialog hotkeys.
 */
export function WordEditDialog({
  open,
  target,
  lineWords,
  onNavigate,
  onApply,
  onClose,
}: WordEditDialogProps) {
  if (!open) return null;

  const { lineIndex, wordIndex } = target;
  const hasPrev = wordIndex > 0;
  const hasNext = wordIndex < lineWords.length - 1;

  const prevWord = hasPrev ? lineWords[wordIndex - 1] : null;
  const currentWord = lineWords[wordIndex] ?? "";
  const nextWord = hasNext ? lineWords[wordIndex + 1] : null;

  function handleApplyClose() {
    onApply();
    onClose();
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
        className="bg-white rounded-lg shadow-xl w-full max-w-2xl mx-4 flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 bg-gray-50 shrink-0">
          <span data-testid="dialog-header-label" className="text-sm font-semibold text-gray-800">
            Edit Line {lineIndex}, Word {wordIndex}
          </span>
          <div className="flex items-center gap-2">
            <button
              data-testid="dialog-apply-close-button"
              onClick={handleApplyClose}
              title="Apply changes and close (Shift+Enter)"
              className="flex items-center gap-1 px-3 py-1.5 text-sm rounded bg-blue-600 text-white hover:bg-blue-700 transition-colors"
            >
              <span aria-hidden="true">✓</span>
              Apply &amp; Close
            </button>
            <button
              data-testid="dialog-close-button"
              onClick={onClose}
              title="Discard changes and close"
              aria-label="Close dialog"
              className="px-2 py-1.5 text-lg text-gray-500 hover:text-gray-800 hover:bg-gray-200 rounded transition-colors"
            >
              ×
            </button>
          </div>
        </div>

        {/* 3-column preview row */}
        <div className="flex items-stretch gap-2 px-4 py-3 border-b border-gray-200 shrink-0">
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
                  ? "border-gray-300 bg-white hover:bg-gray-50 text-gray-700"
                  : "border-gray-200 bg-gray-50 text-gray-300 cursor-default",
              ].join(" ")}
            >
              ← Prev
            </button>
            <div
              data-testid="dialog-prev-word"
              className={[
                "w-full min-h-[3rem] flex items-center justify-center rounded border p-2 text-sm font-mono",
                "bg-gray-50 text-gray-500 border-gray-200",
                !hasPrev ? "opacity-30" : "",
              ].join(" ")}
            >
              {prevWord ?? "–"}
            </div>
          </div>

          {/* Current word (highlighted) */}
          <div className="flex flex-col items-center gap-1 flex-[2]">
            <div className="text-xs text-gray-400 font-medium">Current</div>
            <div
              data-testid="dialog-current-word"
              className="w-full min-h-[3rem] flex items-center justify-center rounded border-2 border-blue-500 bg-blue-50 p-2 text-sm font-mono font-semibold text-blue-900 shadow-sm"
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
                  ? "border-gray-300 bg-white hover:bg-gray-50 text-gray-700"
                  : "border-gray-200 bg-gray-50 text-gray-300 cursor-default",
              ].join(" ")}
            >
              Next →
            </button>
            <div
              data-testid="dialog-next-word"
              className={[
                "w-full min-h-[3rem] flex items-center justify-center rounded border p-2 text-sm font-mono",
                "bg-gray-50 text-gray-500 border-gray-200",
                !hasNext ? "opacity-30" : "",
              ].join(" ")}
            >
              {nextWord ?? "–"}
            </div>
          </div>
        </div>

        {/* Action rows slot — populated by #210 (Konva image), #211, #212 */}
        <div
          data-testid="dialog-action-rows"
          className="flex-1 min-h-[8rem] p-4 text-sm text-gray-400 text-center flex items-center justify-center"
        >
          {/* Action rows will be added in #210–#212 */}
          <span>Action rows (coming in #210–#212)</span>
        </div>
      </div>
    </div>
  );
}

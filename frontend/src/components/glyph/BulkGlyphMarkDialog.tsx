// BulkGlyphMarkDialog.tsx — page-scope bulk glyph-mark recipe dialog.
// Spec: specs/20-glyph-annotations.md §5.5
// Issue #270
//
// data-testids (spec §7):
//   bulk-glyph-mark-dialog         — outer dialog container
//   bulk-glyph-recipe-select       — recipe dropdown
//   bulk-glyph-skip-annotated-checkbox — "Skip already annotated"
//   bulk-glyph-accept-predictions-checkbox — "Also confirm matching predictions"
//   bulk-glyph-dry-run-button      — Preview button
//   bulk-glyph-apply-button        — Apply button
//   bulk-glyph-preview-count       — span containing "N words will be modified"

import { useState } from "react";

export interface BulkGlyphMarkDialogProps {
  open: boolean;
  projectId: string;
  pageIndex: number;
  onClose: () => void;
}

type Recipe = "ct_substring" | "st_substring" | "long_s_typeset_era";

const RECIPE_LABELS: Record<Recipe, string> = {
  ct_substring: 'CT auto-mark (GT contains "ct")',
  st_substring: 'ST auto-mark (GT contains "st")',
  long_s_typeset_era: "Long-s by typeset-era (heuristic)",
};

/**
 * Modal dialog for bulk-marking glyph annotations across all words on a page.
 * Supports three recipes. Shows a dry-run preview count before applying.
 */
export function BulkGlyphMarkDialog({
  open,
  projectId,
  pageIndex,
  onClose,
}: BulkGlyphMarkDialogProps) {
  const [recipe, setRecipe] = useState<Recipe>("ct_substring");
  const [skipAnnotated, setSkipAnnotated] = useState(true);
  const [acceptPredictions, setAcceptPredictions] = useState(false);
  const [previewCount, setPreviewCount] = useState<number | null>(null);
  const [isApplying, setIsApplying] = useState(false);
  const [isPreviewing, setIsPreviewing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  async function callBulkMark(dryRun: boolean) {
    const url = `/api/projects/${projectId}/pages/${pageIndex}/glyph-bulk-mark`;
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        recipe,
        skip_already_annotated: skipAnnotated,
        accept_predictions: acceptPredictions,
        dry_run: dryRun,
      }),
    });
    if (!resp.ok) {
      throw new Error(`Bulk mark failed: ${resp.status}`);
    }
    return resp.json() as Promise<{
      affected_word_ids: string[];
      skipped_word_ids: string[];
      page: unknown;
    }>;
  }

  async function handlePreview() {
    setIsPreviewing(true);
    setError(null);
    try {
      const result = await callBulkMark(true);
      setPreviewCount(result.affected_word_ids.length);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Preview failed");
    } finally {
      setIsPreviewing(false);
    }
  }

  async function handleApply() {
    setIsApplying(true);
    setError(null);
    try {
      await callBulkMark(false);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Apply failed");
    } finally {
      setIsApplying(false);
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Bulk-mark glyphs"
      className="fixed inset-0 z-50 flex items-center justify-center"
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/40" onClick={onClose} aria-hidden="true" />

      {/* Dialog panel */}
      <div
        data-testid="bulk-glyph-mark-dialog"
        className="relative z-10 bg-bg-base border border-border-1 rounded-lg shadow-xl p-5 w-[400px] max-w-[90vw] flex flex-col gap-4"
      >
        <div className="font-semibold text-ink-1 text-sm">Bulk-mark glyphs</div>

        {/* Recipe select */}
        <div className="flex flex-col gap-1">
          <label htmlFor="bulk-glyph-recipe" className="text-xs text-ink-3">
            Recipe
          </label>
          <select
            id="bulk-glyph-recipe"
            data-testid="bulk-glyph-recipe-select"
            value={recipe}
            onChange={(e) => {
              setRecipe(e.target.value as Recipe);
              setPreviewCount(null);
            }}
            className="text-xs border border-border-1 rounded px-2 py-1 bg-surface-1 text-ink-1"
          >
            {(Object.keys(RECIPE_LABELS) as Recipe[]).map((r) => (
              <option key={r} value={r}>
                {RECIPE_LABELS[r]}
              </option>
            ))}
          </select>
        </div>

        {/* Options */}
        <div className="flex flex-col gap-2">
          <label className="flex items-center gap-2 text-xs cursor-pointer">
            <input
              data-testid="bulk-glyph-skip-annotated-checkbox"
              type="checkbox"
              checked={skipAnnotated}
              onChange={(e) => {
                setSkipAnnotated(e.target.checked);
                setPreviewCount(null);
              }}
            />
            Skip already-annotated words
          </label>
          <label className="flex items-center gap-2 text-xs cursor-pointer">
            <input
              data-testid="bulk-glyph-accept-predictions-checkbox"
              type="checkbox"
              checked={acceptPredictions}
              onChange={(e) => {
                setAcceptPredictions(e.target.checked);
                setPreviewCount(null);
              }}
            />
            Also confirm matching predictions
          </label>
        </div>

        {/* Preview count */}
        {previewCount !== null && (
          <div className="text-xs text-ink-2 bg-surface-2 rounded px-3 py-2">
            Preview:{" "}
            <span data-testid="bulk-glyph-preview-count">
              {previewCount} word{previewCount !== 1 ? "s" : ""} will be modified
            </span>
          </div>
        )}

        {/* Error */}
        {error && <div className="text-xs text-red-500">{error}</div>}

        {/* Footer buttons */}
        <div className="flex items-center justify-between gap-2 pt-1 border-t border-border-1">
          <button
            data-testid="bulk-glyph-dry-run-button"
            type="button"
            onClick={() => void handlePreview()}
            disabled={isPreviewing || isApplying}
            className="text-xs px-3 py-1.5 border border-border-1 rounded hover:bg-surface-2 disabled:opacity-40"
          >
            {isPreviewing ? "Previewing…" : "Preview"}
          </button>

          <div className="flex gap-2">
            <button
              type="button"
              onClick={onClose}
              className="text-xs px-3 py-1.5 border border-border-1 rounded hover:bg-surface-2"
            >
              Cancel
            </button>
            <button
              data-testid="bulk-glyph-apply-button"
              type="button"
              onClick={() => void handleApply()}
              disabled={isApplying || isPreviewing}
              className="text-xs px-3 py-1.5 bg-accent text-white rounded hover:opacity-90 disabled:opacity-40"
            >
              {isApplying ? "Applying…" : "Apply"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

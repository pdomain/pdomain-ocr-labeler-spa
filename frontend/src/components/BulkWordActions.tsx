// BulkWordActions.tsx — page-scope + word-bulk operations (Lane D / Task D3).
// Spec: docs/plans/2026-06-03-labeler-spa-legacy-parity.md Lane D / D3.
//
// Always-available page controls:
//   - validate all / unvalidate all words on the page (validate-batch scope=page)
//
// When one or more words are multi-selected (selection-store.selectedWords):
//   - delete the selected words (words/delete-batch — Lane A2)
//   - apply a text style to every selected word (words/{li}/{wi}/style)
//   - apply a component to every selected word (words/{li}/{wi}/component)
//
// data-testids (driver-contract):
//   bulk-word-actions
//   page-validate-all, page-unvalidate-all
//   bulk-word-delete
//   bulk-word-style-select, bulk-word-style-apply
//   bulk-word-component-select, bulk-word-component-apply

import { useState, useSyncExternalStore } from "react";
import { selectionStore } from "../stores/selection-store";
import { useValidatePage, useDeleteWordsBatch } from "../hooks/useLineMutations";
import { useApplyStyle, useApplyComponent } from "../hooks/useWordMutations";
import { useLabelVocabulary } from "../hooks/useLabelVocabulary";

function subscribeSelection(cb: () => void): () => void {
  return selectionStore.subscribe(() => {
    cb();
  });
}
function getSelectionSnapshot() {
  return selectionStore.getState();
}

export interface BulkWordActionsProps {
  projectId: string;
  pageIndex: number;
}

export function BulkWordActions({ projectId, pageIndex }: BulkWordActionsProps) {
  const selection = useSyncExternalStore(
    subscribeSelection,
    getSelectionSnapshot,
    getSelectionSnapshot,
  );
  const selectedWords = selection.selectedWords;

  const validatePage = useValidatePage(projectId, pageIndex);
  const deleteWords = useDeleteWordsBatch(projectId, pageIndex);
  const applyStyle = useApplyStyle(projectId, pageIndex);
  const applyComponent = useApplyComponent(projectId, pageIndex);

  // Q-B2: source label vocab from backend so we never drift from book-tools'
  // canonical ALLOWED_TEXT_STYLE_LABELS / ALLOWED_COMPONENTS sets.
  // "regular" = clear-style sentinel — not a meaningful bulk-apply target, omit.
  const { textStyleLabels, wordComponents } = useLabelVocabulary();
  const styleLabels = textStyleLabels.filter((s) => s !== "regular");

  const [style, setStyle] = useState("");
  const [component, setComponent] = useState("");

  const btn =
    "text-[11px] px-2 py-1 rounded border border-border-2 text-ink-2 hover:text-ink-1 " +
    "hover:border-accent transition-colors disabled:opacity-40";

  return (
    <div data-testid="bulk-word-actions" className="flex flex-col gap-2 p-2 text-xs">
      {/* Page-scope validate-all / unvalidate-all */}
      <div className="flex items-center gap-2">
        <span className="text-[9px] text-ink-4 uppercase tracking-wider">Page</span>
        <button
          type="button"
          data-testid="page-validate-all"
          className={btn + " border-status-exact/60 text-status-exact hover:bg-status-exact/10"}
          disabled={validatePage.isPending}
          title="Validate every word on the page"
          onClick={() => {
            validatePage.mutate({ validated: true });
          }}
        >
          Validate all
        </button>
        <button
          type="button"
          data-testid="page-unvalidate-all"
          className={btn}
          disabled={validatePage.isPending}
          title="Unvalidate every word on the page"
          onClick={() => {
            validatePage.mutate({ validated: false });
          }}
        >
          Unvalidate all
        </button>
      </div>

      {/* Multi-select word controls — only when words are selected */}
      {selectedWords.length > 0 && (
        <div className="flex flex-col gap-1.5 border-t border-border-1 pt-2">
          <span className="text-[9px] text-ink-4 uppercase tracking-wider">
            {selectedWords.length} word{selectedWords.length !== 1 ? "s" : ""} selected
          </span>

          {/* Delete */}
          <button
            type="button"
            data-testid="bulk-word-delete"
            className={
              btn + " border-status-mismatch/50 text-status-mismatch hover:bg-status-mismatch/10"
            }
            disabled={deleteWords.isPending}
            title="Delete the selected words"
            onClick={() => {
              deleteWords.mutate({ wordIndices: selectedWords });
            }}
          >
            Delete selected words
          </button>

          {/* Apply style */}
          <div className="flex items-center gap-1.5">
            <select
              data-testid="bulk-word-style-select"
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
              data-testid="bulk-word-style-apply"
              className={btn}
              disabled={!style || applyStyle.isPending}
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
              data-testid="bulk-word-component-select"
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
              data-testid="bulk-word-component-apply"
              className={btn}
              disabled={!component || applyComponent.isPending}
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
      )}
    </div>
  );
}

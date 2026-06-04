// ParagraphDetail.tsx — Paragraph-scope right-panel actions (Lane D / Task D1).
// Spec: docs/plans/2026-06-03-labeler-spa-legacy-parity.md Lane D / D1.
//
// Surfaces the paragraph mutation routes that have a backend but had no UI:
//   - merge with next paragraph         → paragraphs/merge
//   - delete paragraph                  → paragraphs/{pi}/delete
//   - split after first line            → paragraphs/{pi}/split-after-line
//   - copy GT→OCR / OCR→GT              → paragraphs/{pi}/copy-gt-to-ocr|copy-ocr-to-gt
//   - validate / unvalidate all words   → words/validate-batch scope=paragraph
//
// Rendered when selection-store.level === "para".
//
// data-testids (driver-contract):
//   paragraph-detail            — outer container
//   para-merge, para-delete, para-split-after-line,
//   para-copy-gt-to-ocr, para-copy-ocr-to-gt,
//   para-validate, para-unvalidate

import { useSyncExternalStore } from "react";
import { selectionStore } from "../../stores/selection-store";
import {
  useMergeParagraphs,
  useDeleteParagraph,
  useSplitParagraphAfterLine,
  useCopyParagraphGt,
  useValidateParagraph,
} from "../../hooks/useLineMutations";
import type { components } from "../../api/types";

type PagePayload = components["schemas"]["PagePayload"];

function subscribeSelection(cb: () => void): () => void {
  return selectionStore.subscribe(() => {
    cb();
  });
}
function getSelectionSnapshot() {
  return selectionStore.getState();
}

export interface ParagraphDetailProps {
  page: PagePayload;
  projectId: string;
  pageIndex: number;
}

export function ParagraphDetail({ page, projectId, pageIndex }: ParagraphDetailProps) {
  const state = useSyncExternalStore(
    subscribeSelection,
    getSelectionSnapshot,
    getSelectionSnapshot,
  );

  const { level, path } = state;
  const paraId = path.paraId ?? null;

  if (level !== "para" || paraId === null) {
    return (
      <div data-testid="paragraph-detail" className="p-3 text-ink-3 text-sm">
        No paragraph selected.
      </div>
    );
  }

  return (
    <ParagraphDetailInner page={page} projectId={projectId} pageIndex={pageIndex} paraId={paraId} />
  );
}

interface ParagraphDetailInnerProps {
  page: PagePayload;
  projectId: string;
  pageIndex: number;
  paraId: number;
}

function ParagraphDetailInner({ page, projectId, pageIndex, paraId }: ParagraphDetailInnerProps) {
  const mergeParas = useMergeParagraphs(projectId, pageIndex);
  const deletePara = useDeleteParagraph(projectId, pageIndex);
  const splitAfterLine = useSplitParagraphAfterLine(projectId, pageIndex);
  const copyGt = useCopyParagraphGt(projectId, pageIndex);
  const validatePara = useValidateParagraph(projectId, pageIndex);

  const lines = (page.line_matches ?? []).filter((l) => l.paragraph_index === paraId);
  const lineCount = lines.length;
  const paraNum = paraId + 1;

  const anyPending =
    mergeParas.isPending ||
    deletePara.isPending ||
    splitAfterLine.isPending ||
    copyGt.isPending ||
    validatePara.isPending;

  const btn =
    "text-[11px] px-2 py-1 rounded border border-border-2 text-ink-2 hover:text-ink-1 " +
    "hover:border-accent transition-colors disabled:opacity-40 text-left";

  return (
    <div data-testid="paragraph-detail" className="flex flex-col gap-2 p-3">
      {/* Structure context */}
      <div className="flex flex-col gap-0.5 border-b border-border-1 pb-2">
        <span className="font-mono text-[11px] text-ink-1">Paragraph {paraNum}</span>
        <span className="text-[10px] text-ink-3">
          {lineCount} line{lineCount !== 1 ? "s" : ""}
        </span>
      </div>

      {/* Structural actions */}
      <div className="flex flex-col gap-1">
        <span className="text-[9px] text-ink-4 uppercase tracking-wider">Structure</span>
        <button
          type="button"
          data-testid="para-merge"
          className={btn}
          disabled={anyPending}
          title="Merge this paragraph with the next paragraph"
          onClick={() => {
            mergeParas.mutate({ paragraphIndices: [paraId, paraId + 1] });
          }}
        >
          Merge with next paragraph
        </button>
        <button
          type="button"
          data-testid="para-split-after-line"
          className={btn}
          disabled={anyPending || lineCount < 2}
          title="Split this paragraph after its first line"
          onClick={() => {
            splitAfterLine.mutate({ paragraphIndex: paraId, afterLineIndex: 0 });
          }}
        >
          Split after first line
        </button>
        <button
          type="button"
          data-testid="para-delete"
          className={
            btn + " border-status-mismatch/50 text-status-mismatch hover:bg-status-mismatch/10"
          }
          disabled={anyPending}
          title="Delete this paragraph"
          onClick={() => {
            deletePara.mutate({ paragraphIndex: paraId });
          }}
        >
          Delete paragraph
        </button>
      </div>

      {/* Content actions */}
      <div className="flex flex-col gap-1">
        <span className="text-[9px] text-ink-4 uppercase tracking-wider">Ground truth</span>
        <button
          type="button"
          data-testid="para-copy-gt-to-ocr"
          className={btn}
          disabled={anyPending}
          title="Copy ground truth → OCR for every word in this paragraph"
          onClick={() => {
            copyGt.mutate({ paragraphIndex: paraId, direction: "gt_to_ocr" });
          }}
        >
          Copy GT → OCR
        </button>
        <button
          type="button"
          data-testid="para-copy-ocr-to-gt"
          className={btn}
          disabled={anyPending}
          title="Copy OCR → ground truth for every word in this paragraph"
          onClick={() => {
            copyGt.mutate({ paragraphIndex: paraId, direction: "ocr_to_gt" });
          }}
        >
          Copy OCR → GT
        </button>
      </div>

      {/* Validation actions */}
      <div className="flex flex-col gap-1">
        <span className="text-[9px] text-ink-4 uppercase tracking-wider">Validation</span>
        <button
          type="button"
          data-testid="para-validate"
          className={btn + " border-status-exact/60 text-status-exact hover:bg-status-exact/10"}
          disabled={anyPending}
          title="Validate every word in this paragraph"
          onClick={() => {
            validatePara.mutate({ paragraphIndex: paraId, validated: true });
          }}
        >
          Validate all words
        </button>
        <button
          type="button"
          data-testid="para-unvalidate"
          className={btn}
          disabled={anyPending}
          title="Unvalidate every word in this paragraph"
          onClick={() => {
            validatePara.mutate({ paragraphIndex: paraId, validated: false });
          }}
        >
          Unvalidate all words
        </button>
      </div>
    </div>
  );
}

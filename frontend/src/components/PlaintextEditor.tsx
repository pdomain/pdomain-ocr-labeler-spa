// PlaintextEditor.tsx — read-only textarea showing PagePayload.page_text_gt
// or PagePayload.page_text_ocr.
//
// Spec: specs/22-page-surface-wireup.md §3.
// Issue #313 (spec-22-B4).
//
// Read-only in v1 (legacy doesn't allow editing raw text either;
// per-word edit is the canonical path).
//
// data-testid: plaintext-editor-{source}

import type { components } from "../api/types";

type PagePayload = components["schemas"]["PagePayload"];

export type PlaintextSource = "gt" | "ocr";

interface PlaintextEditorProps {
  source: PlaintextSource;
  page?: PagePayload | null;
}

/**
 * Read-only textarea over `page.page_text_gt` or `page.page_text_ocr`.
 *
 * If `page` is null/undefined, or the chosen field is null, renders an
 * empty textarea (no crash).
 */
export function PlaintextEditor({ source, page }: PlaintextEditorProps) {
  const value = (source === "gt" ? page?.page_text_gt : page?.page_text_ocr) ?? "";
  const ariaLabel = source === "gt" ? "Ground truth text" : "OCR text";

  return (
    <textarea
      data-testid={`plaintext-editor-${source}`}
      readOnly
      value={value}
      aria-label={ariaLabel}
      className="flex-1 w-full h-full resize-none font-mono text-sm p-2 border border-gray-200 rounded bg-gray-50 focus:outline-none"
    />
  );
}

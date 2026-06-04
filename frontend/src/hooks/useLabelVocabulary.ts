// useLabelVocabulary.ts — TanStack Query hook for GET /api/label-vocabulary.
//
// Q-B2-STYLE-LABELS option (b): sources text-style and word-component label
// vocabularies from the backend so the frontend can never drift from book-tools'
// canonical ALLOWED_TEXT_STYLE_LABELS / ALLOWED_COMPONENTS sets.
//
// CONTRACT:
//   - Applied values (sent to the backend) MUST be canonical strings from
//     these lists (e.g. "small caps", "drop cap", "italics", "superscript").
//   - superscript / subscript are COMPONENTS, not styles. They are in
//     word_components, not text_style_labels.
//   - FALLBACK_STYLES and FALLBACK_COMPONENTS mirror the book-tools canonical
//     sets exactly. They are used when the query has not yet resolved so the
//     UI never renders an empty palette and never sends a non-canonical value.

import { useQuery } from "@tanstack/react-query";
import type { components } from "../api/types";

export type LabelVocabularyResponse = components["schemas"]["LabelVocabularyResponse"];

// ── Fallback lists (canonical book-tools values, used before query resolves) ──
//
// These must exactly match pdomain_book_tools.ocr.label_normalization:
//   ALLOWED_TEXT_STYLE_LABELS = {
//     regular, all caps, small caps, italics, bold, blackletter,
//     underline, strikethrough, monospace, handwritten
//   }
//   ALLOWED_COMPONENTS = {
//     superscript, subscript, footnote marker, drop cap, drop cap unrecovered
//   }
//
// Sorted to match the backend's deterministic ordering.
export const FALLBACK_STYLES: string[] = [
  "all caps",
  "blackletter",
  "bold",
  "handwritten",
  "italics",
  "monospace",
  "regular",
  "small caps",
  "strikethrough",
  "underline",
];

export const FALLBACK_COMPONENTS: string[] = [
  "drop cap",
  "drop cap unrecovered",
  "footnote marker",
  "subscript",
  "superscript",
];

async function fetchLabelVocabulary(): Promise<LabelVocabularyResponse> {
  const res = await fetch("/api/label-vocabulary");
  if (!res.ok) {
    throw new Error(`label-vocabulary fetch failed: ${res.statusText}`);
  }
  return res.json() as Promise<LabelVocabularyResponse>;
}

/**
 * Fetch the canonical text-style and word-component label vocabulary from
 * the backend. Values are sourced from pdomain_book_tools so this can never
 * drift from the server's validation logic.
 *
 * Returns `{ textStyleLabels, wordComponents }` — always non-empty
 * (falls back to the canonical hardcoded sets until the query resolves).
 */
export function useLabelVocabulary() {
  const query = useQuery<LabelVocabularyResponse>({
    queryKey: ["label-vocabulary"],
    queryFn: fetchLabelVocabulary,
    // Vocab is static within a server process — never stale.
    staleTime: Infinity,
    // No retry: on server error the fallback list is immediately available.
    retry: false,
  });

  return {
    textStyleLabels: query.data?.text_style_labels ?? FALLBACK_STYLES,
    wordComponents: query.data?.word_components ?? FALLBACK_COMPONENTS,
    isLoading: query.isLoading,
    isError: query.isError,
  };
}

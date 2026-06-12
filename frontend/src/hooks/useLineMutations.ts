// useLineMutations.ts — TanStack Query mutations for line- and word-level actions.
// Spec: docs/specs/2026-05-12-word-matches-design.md §LineCard header, §GT editing
// Issues #202 (line header mutations), #203 (word GT update)
// FO-3: useMergeLines — wire LineDetail merge-with-prev/next buttons.
//
// Endpoints:
//   POST /api/projects/{pid}/pages/{idx}/words/validate-batch   → ValidateBatchResponse
//   POST /api/projects/{pid}/pages/{idx}/lines/{li}/copy-gt     → PagePayload
//   POST /api/projects/{pid}/pages/{idx}/lines/delete-batch     → PagePayload (P1.3)
//   POST /api/projects/{pid}/pages/{idx}/words/{li}/{wi}/gt     → WordMatch
//   POST /api/projects/{pid}/pages/{idx}/lines/merge            → PagePayload  (FO-3)
//   POST /api/projects/{pid}/pages/{idx}/lines/{li}/set-gt      → PagePayload  (Task 3)

import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { components } from "../api/types";

type PagePayload = components["schemas"]["PagePayload"];
type WordMatch = components["schemas"]["WordMatch"];
type ValidateBatchRequest = components["schemas"]["ValidateBatchRequest"];
type CopyLineGtRequest = components["schemas"]["CopyLineGtRequest"];
type UpdateWordGroundTruthRequest = components["schemas"]["UpdateWordGroundTruthRequest"];
type MergeLinesRequest = components["schemas"]["MergeLinesRequest"];
type PatchParagraphRequest = components["schemas"]["PatchParagraphRequest"];
type SetLineGtRequest = components["schemas"]["SetLineGtRequest"];

// ─── internal helpers ─────────────────────────────────────────────────────

async function apiPost<T>(url: string, body: unknown, method = "POST"): Promise<T> {
  const res = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    let message = res.statusText;
    try {
      const parsed = JSON.parse(text) as { message?: string };
      if (parsed.message) message = parsed.message;
    } catch {
      if (text) message = text;
    }
    throw Object.assign(new Error(message), { status: res.status });
  }
  return res.json() as Promise<T>;
}

function pageBase(projectId: string, pageIndex: number): string {
  return `/api/projects/${encodeURIComponent(projectId)}/pages/${encodeURIComponent(String(pageIndex))}`;
}

// ─── useValidateLine (#202) ───────────────────────────────────────────────

/** Toggle validated state for a single line (all words in that line). */
export function useValidateLine(projectId: string, pageIndex: number) {
  const qc = useQueryClient();
  return useMutation<unknown, Error, { lineIndex: number; validated: boolean }>({
    mutationFn: ({ lineIndex, validated }) => {
      const body: ValidateBatchRequest = {
        scope: "line",
        line_indices: [lineIndex],
        word_indices: [],
        paragraph_indices: [],
        validated,
      };
      return apiPost<unknown>(`${pageBase(projectId, pageIndex)}/words/validate-batch`, body);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
    },
  });
}

// ─── useCopyLineGt (#202) ─────────────────────────────────────────────────

/**
 * Copy GT text to/from OCR for a single line.
 *
 * direction: "gt_to_ocr" | "ocr_to_gt"
 */
export function useCopyLineGt(projectId: string, pageIndex: number) {
  const qc = useQueryClient();
  return useMutation<
    PagePayload,
    Error,
    { lineIndex: number; direction: CopyLineGtRequest["direction"] }
  >({
    mutationFn: ({ lineIndex, direction }) =>
      apiPost<PagePayload>(
        `${pageBase(projectId, pageIndex)}/lines/${encodeURIComponent(String(lineIndex))}/copy-gt`,
        {
          direction,
        } satisfies CopyLineGtRequest,
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
    },
  });
}

// ─── useDeleteLine (#202, repointed P1.3 / B-62) ──────────────────────────

/**
 * Delete a single line from the page.
 *
 * Uses the real ``lines/delete-batch`` route (Lane A / A2). The legacy
 * page-scope ``POST .../delete`` endpoint is an intentionally
 * unimplemented 501 stub — pointing here at it made every line-delete
 * surface (LineDetail card, MultiLineDetail card + bulk) silently
 * delete nothing (parity finding F5, B-62/65).
 */
export function useDeleteLine(projectId: string, pageIndex: number) {
  const qc = useQueryClient();
  return useMutation<PagePayload, Error, { lineIndex: number }>({
    mutationFn: ({ lineIndex }) =>
      apiPost<PagePayload>(`${pageBase(projectId, pageIndex)}/lines/delete-batch`, {
        scope: "line",
        line_indices: [lineIndex],
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
    },
  });
}

// ─── useUpdateWordGt (#203) ───────────────────────────────────────────────

/** Update ground-truth text for a single word (blur-commit). */
export function useUpdateWordGt(projectId: string, pageIndex: number) {
  const qc = useQueryClient();
  return useMutation<WordMatch, Error, { lineIndex: number; wordIndex: number; text: string }>({
    mutationFn: ({ lineIndex, wordIndex, text }) => {
      const body: UpdateWordGroundTruthRequest = { text };
      return apiPost<WordMatch>(
        `${pageBase(projectId, pageIndex)}/words/${encodeURIComponent(String(lineIndex))}/${encodeURIComponent(String(wordIndex))}/gt`,
        body,
      );
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
    },
  });
}

// ─── usePatchParagraph (FO-1) ─────────────────────────────────────────────

/**
 * PATCH a paragraph's layout_type (FO-1 — BlockDetail layout save).
 *
 * PATCH /api/projects/{pid}/pages/{idx}/paragraphs/{pi}
 */
export function usePatchParagraph(projectId: string, pageIndex: number) {
  const qc = useQueryClient();
  return useMutation<
    PagePayload,
    Error,
    { paragraphIndex: number; layoutType: PatchParagraphRequest["layout_type"] }
  >({
    mutationFn: ({ paragraphIndex, layoutType }) => {
      const body: PatchParagraphRequest = { layout_type: layoutType };
      return apiPost<PagePayload>(
        `${pageBase(projectId, pageIndex)}/paragraphs/${encodeURIComponent(String(paragraphIndex))}`,
        body,
        "PATCH",
      );
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
    },
  });
}

// ─── useMergeLines (FO-3) ─────────────────────────────────────────────────

/**
 * Merge two adjacent lines.
 *
 * direction: "prev" merges lineIndex with lineIndex - 1.
 *            "next" merges lineIndex with lineIndex + 1.
 * Both are sent as a two-element `line_indices` array to
 * POST /api/projects/{pid}/pages/{idx}/lines/merge.
 */
export function useMergeLines(projectId: string, pageIndex: number) {
  const qc = useQueryClient();
  return useMutation<PagePayload, Error, { lineIndex: number; direction: "prev" | "next" }>({
    mutationFn: ({ lineIndex, direction }) => {
      const adjacent = direction === "prev" ? lineIndex - 1 : lineIndex + 1;
      const indices = direction === "prev" ? [adjacent, lineIndex] : [lineIndex, adjacent];
      const body: MergeLinesRequest = { line_indices: indices };
      return apiPost<PagePayload>(`${pageBase(projectId, pageIndex)}/lines/merge`, body);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
    },
  });
}

// ─── useSetLineGt (Task 3) ────────────────────────────────────────────────

/** Set full-line ground-truth text (blur-commit from LineDetail GT input). */
export function useSetLineGt(projectId: string, pageIndex: number) {
  const qc = useQueryClient();
  return useMutation<PagePayload, Error, { lineIndex: number; text: string }>({
    mutationFn: ({ lineIndex, text }) => {
      const body: SetLineGtRequest = { text };
      return apiPost<PagePayload>(
        `${pageBase(projectId, pageIndex)}/lines/${encodeURIComponent(String(lineIndex))}/set-gt`,
        body,
      );
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
    },
  });
}

// ─── Page-scope + word-batch mutations (Lane D / D3) ──────────────────────

/** Validate / unvalidate every word on the page via validate-batch scope=page. */
export function useValidatePage(projectId: string, pageIndex: number) {
  const qc = useQueryClient();
  return useMutation<unknown, Error, { validated: boolean }>({
    mutationFn: ({ validated }) => {
      const body: ValidateBatchRequest = {
        scope: "page",
        line_indices: [],
        paragraph_indices: [],
        word_indices: [],
        validated,
      };
      return apiPost<unknown>(`${pageBase(projectId, pageIndex)}/words/validate-batch`, body);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
    },
  });
}

/** Delete a set of words via the words/delete-batch route (Lane A2). */
export function useDeleteWordsBatch(projectId: string, pageIndex: number) {
  const qc = useQueryClient();
  return useMutation<PagePayload, Error, { wordIndices: [number, number][] }>({
    mutationFn: ({ wordIndices }) =>
      apiPost<PagePayload>(`${pageBase(projectId, pageIndex)}/words/delete-batch`, {
        scope: "word",
        word_indices: wordIndices,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
    },
  });
}

// ─── Line split mutations (Lane D / D2) ───────────────────────────────────

/** Split a line after the given word boundary. */
export function useSplitLineAfterWord(projectId: string, pageIndex: number) {
  const qc = useQueryClient();
  return useMutation<PagePayload, Error, { lineIndex: number; wordIndex: number }>({
    mutationFn: ({ lineIndex, wordIndex }) =>
      apiPost<PagePayload>(
        `${pageBase(projectId, pageIndex)}/lines/${encodeURIComponent(String(lineIndex))}/split-after-word`,
        { word_index: wordIndex },
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
    },
  });
}

/** Extract selected words into a new line via the collective split-by-words route. */
export function useSplitLineByWords(projectId: string, pageIndex: number) {
  const qc = useQueryClient();
  return useMutation<PagePayload, Error, { wordKeys: [number, number][] }>({
    mutationFn: ({ wordKeys }) =>
      apiPost<PagePayload>(`${pageBase(projectId, pageIndex)}/lines/split-by-words`, {
        word_keys: wordKeys,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
    },
  });
}

// ─── Paragraph-scope mutations (Lane D / D1) ──────────────────────────────
//
// Endpoints (all real per api/lines_paragraphs.py):
//   POST .../paragraphs/merge                          → PagePayload
//   POST .../paragraphs/{pi}/delete                    → PagePayload
//   POST .../paragraphs/{pi}/split-after-line          → PagePayload
//   POST .../paragraphs/{pi}/copy-gt-to-ocr|copy-ocr-to-gt → PagePayload
//   POST .../words/validate-batch  scope=paragraph     → ValidateBatchResponse

/** Merge a paragraph with the next one. Sends a two-element index array. */
export function useMergeParagraphs(projectId: string, pageIndex: number) {
  const qc = useQueryClient();
  return useMutation<PagePayload, Error, { paragraphIndices: number[] }>({
    mutationFn: ({ paragraphIndices }) =>
      apiPost<PagePayload>(`${pageBase(projectId, pageIndex)}/paragraphs/merge`, {
        paragraph_indices: paragraphIndices,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
    },
  });
}

/** Delete a single paragraph from the page. */
export function useDeleteParagraph(projectId: string, pageIndex: number) {
  const qc = useQueryClient();
  return useMutation<PagePayload, Error, { paragraphIndex: number }>({
    mutationFn: ({ paragraphIndex }) =>
      apiPost<PagePayload>(
        `${pageBase(projectId, pageIndex)}/paragraphs/${encodeURIComponent(String(paragraphIndex))}/delete`,
        {},
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
    },
  });
}

/** Split a paragraph after the given within-paragraph line index. */
export function useSplitParagraphAfterLine(projectId: string, pageIndex: number) {
  const qc = useQueryClient();
  return useMutation<PagePayload, Error, { paragraphIndex: number; afterLineIndex: number }>({
    mutationFn: ({ paragraphIndex, afterLineIndex }) =>
      apiPost<PagePayload>(
        `${pageBase(projectId, pageIndex)}/paragraphs/${encodeURIComponent(String(paragraphIndex))}/split-after-line`,
        { paragraph_index: paragraphIndex, after_line_index: afterLineIndex },
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
    },
  });
}

/** Copy GT↔OCR for every word in a paragraph (direction selects the way). */
export function useCopyParagraphGt(projectId: string, pageIndex: number) {
  const qc = useQueryClient();
  return useMutation<
    PagePayload,
    Error,
    { paragraphIndex: number; direction: "gt_to_ocr" | "ocr_to_gt" }
  >({
    mutationFn: ({ paragraphIndex, direction }) => {
      const verb = direction === "gt_to_ocr" ? "copy-gt-to-ocr" : "copy-ocr-to-gt";
      return apiPost<PagePayload>(
        `${pageBase(projectId, pageIndex)}/paragraphs/${encodeURIComponent(String(paragraphIndex))}/${verb}`,
        {},
      );
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
    },
  });
}

/** Validate / unvalidate every word in a paragraph via validate-batch scope=paragraph. */
export function useValidateParagraph(projectId: string, pageIndex: number) {
  const qc = useQueryClient();
  return useMutation<unknown, Error, { paragraphIndex: number; validated: boolean }>({
    mutationFn: ({ paragraphIndex, validated }) => {
      const body: ValidateBatchRequest = {
        scope: "paragraph",
        line_indices: [],
        paragraph_indices: [paragraphIndex],
        word_indices: [],
        validated,
      };
      return apiPost<unknown>(`${pageBase(projectId, pageIndex)}/words/validate-batch`, body);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
    },
  });
}

// ─── useValidateWords (Q5) ────────────────────────────────────────────────

/**
 * Bulk validate/skip a set of words selected via the LineDetail bulk bar.
 *
 * wordPairs: array of [lineIndex, wordIndex] tuples corresponding to the
 * checked words. Sent as scope="word" to validate-batch.
 */
export function useValidateWords(projectId: string, pageIndex: number) {
  const qc = useQueryClient();
  return useMutation<unknown, Error, { wordPairs: [number, number][]; validated: boolean }>({
    mutationFn: ({ wordPairs, validated }) => {
      const body: ValidateBatchRequest = {
        scope: "word",
        line_indices: [],
        paragraph_indices: [],
        word_indices: wordPairs,
        validated,
      };
      return apiPost<unknown>(`${pageBase(projectId, pageIndex)}/words/validate-batch`, body);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
    },
  });
}

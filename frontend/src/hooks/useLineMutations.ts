// useLineMutations.ts — TanStack Query mutations for line- and word-level actions.
// Spec: docs/specs/2026-05-12-word-matches-design.md §LineCard header, §GT editing
// Issues #202 (line header mutations), #203 (word GT update)
//
// Endpoints:
//   POST /api/projects/{pid}/pages/{idx}/words/validate-batch   → ValidateBatchResponse
//   POST /api/projects/{pid}/pages/{idx}/lines/{li}/copy-gt     → PagePayload
//   POST /api/projects/{pid}/pages/{idx}/delete                 → PagePayload
//   POST /api/projects/{pid}/pages/{idx}/words/{li}/{wi}/gt     → WordMatch

import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { components } from "../api/types";

type PagePayload = components["schemas"]["PagePayload"];
type WordMatch = components["schemas"]["WordMatch"];
type ValidateBatchRequest = components["schemas"]["ValidateBatchRequest"];
type CopyLineGtRequest = components["schemas"]["CopyLineGtRequest"];
type DeleteScopeRequest = components["schemas"]["DeleteScopeRequest"];
type UpdateWordGroundTruthRequest = components["schemas"]["UpdateWordGroundTruthRequest"];

// ─── internal helpers ─────────────────────────────────────────────────────

async function apiPost<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: "POST",
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
  return `/api/projects/${projectId}/pages/${pageIndex}`;
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
      apiPost<PagePayload>(`${pageBase(projectId, pageIndex)}/lines/${lineIndex}/copy-gt`, {
        direction,
      } satisfies CopyLineGtRequest),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
    },
  });
}

// ─── useDeleteLine (#202) ─────────────────────────────────────────────────

/** Delete a single line from the page. */
export function useDeleteLine(projectId: string, pageIndex: number) {
  const qc = useQueryClient();
  return useMutation<PagePayload, Error, { lineIndex: number }>({
    mutationFn: ({ lineIndex }) => {
      const body: DeleteScopeRequest = {
        scope: "line",
        paragraph_indices: [],
        line_indices: [lineIndex],
        word_indices: [],
      };
      return apiPost<PagePayload>(`${pageBase(projectId, pageIndex)}/delete`, body);
    },
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
        `${pageBase(projectId, pageIndex)}/words/${lineIndex}/${wordIndex}/gt`,
        body,
      );
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
    },
  });
}

// useToolbarDispatch.ts — Lane B / Task B1.
//
// Resolves a ToolbarActionGrid cell click (a `ButtonStates` key such as
// `line_validate`) into a concrete API mutation:
//
//   1. translate the `ButtonStates` key → the matching `toolbarMapping` key
//      (`line-validate`, `paragraph-delete`, `word-word-to-line`, …);
//   2. look up the route + base body in `toolbarMapping.ts`;
//   3. fill the URL template placeholders (`{projectId}`, `{pageIndex}`,
//      `{lineIndex}`, `{paragraphIndex}`) from the route + current selection;
//   4. augment the body with the selection-derived index arrays the
//      scope-batch routes expect (`line_indices`, `paragraph_indices`,
//      `word_indices`) plus any per-route fields (split-after, group);
//   5. fire the POST through TanStack Query, invalidate the page on success,
//      and surface failures via toast.
//
// The grid is wireup-only; every route it points at already exists on the
// backend (Lane A scope-batch routes + the pre-existing validate/style/
// component/add routes).

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { toast } from "../lib/toast";
import { toolbarMapping } from "../lib/toolbarMapping";
import type { ButtonStates, Selection } from "./useToolbarButtonStates";

// ─── ButtonStates key → toolbarMapping key ──────────────────────────────────
//
// ButtonStates keys use `para_*` and snake_case actions; toolbarMapping keys
// use `paragraph-*` and hyphenated actions, with three irregular `to-para` /
// `w-to-l` columns. A plain `_`→`-` swap is wrong for those, so we keep an
// explicit table. Every present (non-stub) grid cell has an entry here.

const STATE_KEY_TO_MAPPING_KEY: Record<keyof ButtonStates, string> = {
  // Page row
  page_refine: "page-refine",
  page_expand_refine: "page-expand-refine",
  page_expand: "page-expand",
  page_gt_to_ocr: "page-gt-to-ocr",
  page_ocr_to_gt: "page-ocr-to-gt",
  page_validate: "page-validate",
  page_unvalidate: "page-unvalidate",
  // Paragraph row
  para_merge: "paragraph-merge",
  para_refine: "paragraph-refine",
  para_expand_refine: "paragraph-expand-refine",
  para_expand: "paragraph-expand",
  para_split_after: "paragraph-split-after",
  para_split_selected: "paragraph-split-selected",
  para_gt_to_ocr: "paragraph-gt-to-ocr",
  para_ocr_to_gt: "paragraph-ocr-to-gt",
  para_validate: "paragraph-validate",
  para_unvalidate: "paragraph-unvalidate",
  para_delete: "paragraph-delete",
  // Line row
  line_merge: "line-merge",
  line_refine: "line-refine",
  line_expand_refine: "line-expand-refine",
  line_expand: "line-expand",
  line_split_after: "line-split-after",
  line_split_selected: "line-split-selected",
  line_to_para: "line-word-to-para",
  line_gt_to_ocr: "line-gt-to-ocr",
  line_ocr_to_gt: "line-ocr-to-gt",
  line_validate: "line-validate",
  line_unvalidate: "line-unvalidate",
  line_delete: "line-delete",
  // Word row
  word_refine: "word-refine",
  word_expand_refine: "word-expand-refine",
  word_expand: "word-expand",
  word_w_to_l: "word-word-to-line",
  word_to_para: "word-word-to-para",
  word_gt_to_ocr: "word-gt-to-ocr",
  word_ocr_to_gt: "word-ocr-to-gt",
  word_validate: "word-validate",
  word_unvalidate: "word-unvalidate",
  word_delete: "word-delete",
};

interface ResolvedRequest {
  url: string;
  method: string;
  body: Record<string, unknown>;
}

/**
 * Resolve a grid cell click into a concrete `{ url, method, body }`.
 *
 * Returns `null` when the cell maps to a disabled (`null`) toolbarMapping
 * entry, or when a required selection index is missing for a route that
 * templates `{lineIndex}` / `{paragraphIndex}`.
 */
/** Exported for unit-testing — not part of the public hook API. */
export function resolveToolbarRequest(
  stateKey: keyof ButtonStates,
  projectId: string,
  pageIndex: number,
  selection: Selection,
): ResolvedRequest | null {
  const mappingKey = STATE_KEY_TO_MAPPING_KEY[stateKey];
  const mapping = toolbarMapping[mappingKey];
  if (!mapping) return null;

  const firstLine = selection.selected_lines[0];
  const firstPara = selection.selected_paragraphs[0];

  let url = mapping.endpoint
    .replace("{projectId}", encodeURIComponent(projectId))
    .replace("{pageIndex}", encodeURIComponent(String(pageIndex)));

  if (url.includes("{lineIndex}")) {
    if (firstLine === undefined) return null;
    url = url.replace("{lineIndex}", encodeURIComponent(String(firstLine)));
  }
  if (url.includes("{paragraphIndex}")) {
    if (firstPara === undefined) return null;
    url = url.replace("{paragraphIndex}", encodeURIComponent(String(firstPara)));
  }

  // Base body from the mapping (scope / direction / mode / validated).
  const body: Record<string, unknown> = { ...(mapping.body ?? {}) };

  // Augment with selection-derived index sets so the scope-batch routes
  // (validate / copy-gt / delete / group) can resolve their targets.
  body["paragraph_indices"] = selection.selected_paragraphs;
  body["line_indices"] = selection.selected_lines;
  body["word_indices"] = selection.selected_words;

  // Routes that template {lineIndex} also accept a top-level echo.
  if (firstLine !== undefined) body["line_index"] = firstLine;

  // split-after-line needs an after_line_index; split-after-word needs a
  // word_index. The grid only enables these for a single selection, so the
  // first selected child is the split point.
  if (mappingKey.endsWith("split-after")) {
    if (mappingKey.startsWith("paragraph")) {
      const afterLine = selection.selected_lines[0];
      if (afterLine !== undefined) body["after_line_index"] = afterLine;
    } else if (mappingKey.startsWith("line")) {
      const afterWord = selection.selected_words[0];
      if (afterWord !== undefined) body["word_index"] = afterWord[1];
    }
  }

  // S4.2: word-word-to-line sends word_keys (list of [line_idx, word_idx] tuples)
  // so the backend `split_line_with_selected_words` route can resolve the words.
  // The static body in toolbarMapping is intentionally empty for this action.
  if (mappingKey === "word-word-to-line") {
    body["word_keys"] = selection.selected_words;
  }

  return { url, method: mapping.method, body };
}

async function apiSend(req: ResolvedRequest): Promise<unknown> {
  const res = await fetch(req.url, {
    method: req.method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req.body),
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
  // Some routes (202 + job) return JSON; tolerate empty bodies.
  const text = await res.text();
  return text ? (JSON.parse(text) as unknown) : null;
}

/**
 * TanStack-Query mutation that dispatches a toolbar grid action.
 *
 * Usage:
 *   const dispatch = useToolbarDispatch(projectId, pageIndex, selection);
 *   <ToolbarActionGrid onAction={dispatch} ... />
 *
 * On success the page query (`["page", projectId, pageIndex]`) is
 * invalidated so the canvas + worklist re-fetch. On failure a toast is
 * shown. Cells that resolve to a disabled mapping are a no-op.
 */
export function useToolbarDispatch(
  projectId: string,
  pageIndex: number,
  selection: Selection,
): (stateKey: keyof ButtonStates) => void {
  const qc = useQueryClient();
  const mutation = useMutation<unknown, Error, keyof ButtonStates>({
    mutationFn: (stateKey) => {
      const req = resolveToolbarRequest(stateKey, projectId, pageIndex, selection);
      if (!req) return Promise.resolve(null);
      return apiSend(req);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
    },
    onError: (err) => {
      toast.error(err.message || "Toolbar action failed");
    },
  });

  return (stateKey: keyof ButtonStates) => {
    mutation.mutate(stateKey);
  };
}

// useWordMutations.ts — TanStack Query mutations for word-level actions.
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 16 (BBoxSection).
// FO-2: useSetCharRanges — positioned char-range styles endpoint.
//
// Endpoints:
//   POST /api/projects/{pid}/pages/{idx}/words/{li}/{wi}/rebox         → PagePayload
//   POST /api/projects/{pid}/pages/{idx}/words/{li}/{wi}/merge         → PagePayload
//   POST /api/projects/{pid}/pages/{idx}/words/{li}/{wi}/split         → PagePayload
//   POST /api/projects/{pid}/pages/{idx}/words/{li}/{wi}/char-ranges   → PagePayload (FO-2)

import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { components } from "../api/types";

type PagePayload = components["schemas"]["PagePayload"];
type BBox = components["schemas"]["BBox"];
type ReboxWordRequest = components["schemas"]["ReboxWordRequest"];
type MergeWordsRequest = components["schemas"]["MergeWordsRequest"];
type SplitWordRequest = components["schemas"]["SplitWordRequest"];
type ApplyStyleRequest = components["schemas"]["ApplyStyleRequest"];
type ApplyComponentRequest = components["schemas"]["ApplyComponentRequest"];
type UpdateWordGroundTruthRequest = components["schemas"]["UpdateWordGroundTruthRequest"];
type SetCharRangesRequest = components["schemas"]["SetCharRangesRequest"];
type CharRange = components["schemas"]["CharRange"];

// ─── internal helpers ──────────────────────────────────────────────────────

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

function wordBase(
  projectId: string,
  pageIndex: number,
  lineIndex: number,
  wordIndex: number,
): string {
  return `/api/projects/${projectId}/pages/${pageIndex}/words/${lineIndex}/${wordIndex}`;
}

// ─── useReboxWord ──────────────────────────────────────────────────────────

/**
 * Replace the bounding box of a single word.
 *
 * Invalidates the page query on success so the canvas and word cells
 * re-render with the updated bbox.
 */
export function useReboxWord(projectId: string, pageIndex: number) {
  const qc = useQueryClient();
  return useMutation<PagePayload, Error, { lineIndex: number; wordIndex: number; bbox: BBox }>({
    mutationFn: ({ lineIndex, wordIndex, bbox }) => {
      const body: ReboxWordRequest = { bbox };
      return apiPost<PagePayload>(
        `${wordBase(projectId, pageIndex, lineIndex, wordIndex)}/rebox`,
        body,
      );
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
    },
  });
}

// ─── useMergeWord ──────────────────────────────────────────────────────────

/**
 * Merge a word with its left ("prev") or right ("next") neighbour.
 *
 * The API takes `direction: "left" | "right"`:
 *   "left"  ↔ merge with previous word
 *   "right" ↔ merge with next word
 */
export function useMergeWord(projectId: string, pageIndex: number) {
  const qc = useQueryClient();
  return useMutation<
    PagePayload,
    Error,
    { lineIndex: number; wordIndex: number; direction: MergeWordsRequest["direction"] }
  >({
    mutationFn: ({ lineIndex, wordIndex, direction }) => {
      const body: MergeWordsRequest = { direction };
      return apiPost<PagePayload>(
        `${wordBase(projectId, pageIndex, lineIndex, wordIndex)}/merge`,
        body,
      );
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
    },
  });
}

// ─── useSplitWord ──────────────────────────────────────────────────────────

/**
 * Split a word at a horizontal fraction.
 *
 * `direction` is always "horizontal" for now (vertical returns 400 from
 * the server per the API comment).
 */
export function useSplitWord(projectId: string, pageIndex: number) {
  const qc = useQueryClient();
  return useMutation<
    PagePayload,
    Error,
    {
      lineIndex: number;
      wordIndex: number;
      xFraction: number;
      direction?: SplitWordRequest["direction"];
    }
  >({
    mutationFn: ({ lineIndex, wordIndex, xFraction, direction = "horizontal" }) => {
      const body: SplitWordRequest = { x_fraction: xFraction, direction };
      return apiPost<PagePayload>(
        `${wordBase(projectId, pageIndex, lineIndex, wordIndex)}/split`,
        body,
      );
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
    },
  });
}

// ─── useApplyStyle ─────────────────────────────────────────────────────────

/**
 * Apply a text style label to a word (Slice 19 — Char Ranges).
 *
 * Backend endpoint accepts ``scope: "whole" | "part"``. Char-range
 * position metadata is held as local state in ``CharRangesSection``
 * until the backend grows positioned ranges; for now we send the
 * style label with ``scope: "part"`` to signal partial application.
 */
export function useApplyStyle(projectId: string, pageIndex: number) {
  const qc = useQueryClient();
  return useMutation<
    PagePayload,
    Error,
    { lineIndex: number; wordIndex: number; style: string; scope?: ApplyStyleRequest["scope"] }
  >({
    mutationFn: ({ lineIndex, wordIndex, style, scope = "whole" }) => {
      const body: ApplyStyleRequest = { style, scope };
      return apiPost<PagePayload>(
        `${wordBase(projectId, pageIndex, lineIndex, wordIndex)}/style`,
        body,
      );
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
    },
  });
}

// ─── useUpdateWordGroundTruth ──────────────────────────────────────────────

/**
 * Update the ground-truth text for a word (Slice 20 — Char Fixer).
 *
 * Endpoint: ``POST /api/projects/{pid}/pages/{idx}/words/{li}/{wi}/gt``
 */
export function useUpdateWordGroundTruth(projectId: string, pageIndex: number) {
  const qc = useQueryClient();
  return useMutation<PagePayload, Error, { lineIndex: number; wordIndex: number; text: string }>({
    mutationFn: ({ lineIndex, wordIndex, text }) => {
      const body: UpdateWordGroundTruthRequest = { text };
      return apiPost<PagePayload>(
        `${wordBase(projectId, pageIndex, lineIndex, wordIndex)}/gt`,
        body,
      );
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
    },
  });
}

// ─── useApplyComponent ────────────────────────────────────────────────────

/**
 * Toggle a word component flag (P2.e).
 *
 * Backend endpoint: ``POST /api/projects/{pid}/pages/{idx}/words/{li}/{wi}/component``
 * Body: ``ApplyComponentRequest { component, enabled }``
 */
export function useApplyComponent(projectId: string, pageIndex: number) {
  const qc = useQueryClient();
  return useMutation<
    PagePayload,
    Error,
    { lineIndex: number; wordIndex: number; component: string; enabled: boolean }
  >({
    mutationFn: ({ lineIndex, wordIndex, component, enabled }) => {
      const body: ApplyComponentRequest = { component, enabled };
      return apiPost<PagePayload>(
        `${wordBase(projectId, pageIndex, lineIndex, wordIndex)}/component`,
        body,
      );
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
    },
  });
}

// ─── useSetCharRanges (FO-2) ──────────────────────────────────────────────

/**
 * Set positioned character-range styles for a word (FO-2).
 *
 * Replaces all char-range annotations for the word in a single atomic
 * operation.  An empty ``ranges`` list clears all existing ranges.
 *
 * Endpoint: ``POST /api/projects/{pid}/pages/{idx}/words/{li}/{wi}/char-ranges``
 */
export function useSetCharRanges(projectId: string, pageIndex: number) {
  const qc = useQueryClient();
  return useMutation<
    PagePayload,
    Error,
    { lineIndex: number; wordIndex: number; ranges: CharRange[] }
  >({
    mutationFn: ({ lineIndex, wordIndex, ranges }) => {
      const body: SetCharRangesRequest = { ranges };
      return apiPost<PagePayload>(
        `${wordBase(projectId, pageIndex, lineIndex, wordIndex)}/char-ranges`,
        body,
      );
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
    },
  });
}

// ─── useErasePixels ───────────────────────────────────────────────────────────

/** Shape sent to the backend for each erase op. */
type EraseShape = "rect" | "circle";

/**
 * Erase pixels in a region of a word's image slice.
 *
 * The API takes one `ErasePixelsRequest = { bbox, fill_value, shape }` per call.
 * The caller passes a list of erase operations (from ErasePixelsSection);
 * this hook maps each op to a bounding bbox + shape and fires one POST per op,
 * sequentially.
 *
 * - Brush ops send `shape: "circle"` so the backend uses a cv2 ellipse mask
 *   inscribed within the AABB — corners of the bounding square are NOT erased.
 * - Rect ops send `shape: "rect"` (solid rectangle fill).
 * - Lasso ops also send `shape: "rect"` (AABB approximation; polygon fill not
 *   yet implemented on the backend).
 *
 * Endpoint: `POST /api/projects/{pid}/pages/{idx}/words/{li}/{wi}/erase-pixels`
 */
export function useErasePixels(projectId: string, pageIndex: number) {
  const qc = useQueryClient();
  return useMutation<
    void,
    Error,
    {
      lineIndex: number;
      wordIndex: number;
      ops: Array<
        | { tool: "brush"; x: number; y: number; radius: number }
        | { tool: "lasso"; points: Array<[number, number]> }
        | { tool: "rect"; x: number; y: number; width: number; height: number }
      >;
    }
  >({
    mutationFn: async ({ lineIndex, wordIndex, ops }) => {
      const base = `${wordBase(projectId, pageIndex, lineIndex, wordIndex)}/erase-pixels`;
      for (const op of ops) {
        let bbox: BBox;
        let shape: EraseShape;
        if (op.tool === "rect") {
          bbox = { x: op.x, y: op.y, width: op.width, height: op.height };
          shape = "rect";
        } else if (op.tool === "brush") {
          const r = Math.round(op.radius);
          bbox = {
            x: Math.round(op.x - r),
            y: Math.round(op.y - r),
            width: r * 2,
            height: r * 2,
          };
          // Tell the backend to use a circular (ellipse) mask so the corners
          // of the AABB are not erased — only the circle the user painted.
          shape = "circle";
        } else {
          // lasso — compute axis-aligned bounding box from points
          const xs = op.points.map(([x]) => x);
          const ys = op.points.map(([, y]) => y);
          const minX = Math.min(...xs);
          const minY = Math.min(...ys);
          const maxX = Math.max(...xs);
          const maxY = Math.max(...ys);
          bbox = { x: minX, y: minY, width: maxX - minX, height: maxY - minY };
          // Lasso uses AABB approximation; polygon fill not yet implemented.
          shape = "rect";
        }
        await apiPost<void>(base, { bbox, fill_value: 255, shape });
      }
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
    },
  });
}

// ─── useSetCharBboxes ─────────────────────────────────────────────────────────

/**
 * Persist per-character bounding boxes for a word (CharFixer Apply button).
 *
 * Stores the bboxes in the SPA's word-attributes sidecar so they survive
 * page reloads.  The response is a full ``PagePayload`` that includes the
 * updated ``WordMatch.char_bboxes`` for the affected word.
 *
 * Endpoint: ``POST /api/projects/{pid}/pages/{idx}/words/{li}/{wi}/char-bboxes``
 */
export function useSetCharBboxes(projectId: string, pageIndex: number) {
  const qc = useQueryClient();
  return useMutation<
    PagePayload,
    Error,
    { lineIndex: number; wordIndex: number; charBboxes: BBox[] }
  >({
    mutationFn: ({ lineIndex, wordIndex, charBboxes }) =>
      apiPost<PagePayload>(`${wordBase(projectId, pageIndex, lineIndex, wordIndex)}/char-bboxes`, {
        char_bboxes: charBboxes,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
    },
  });
}

// ─── useAdjustWordGap (P3.d) ──────────────────────────────────────────────────

/**
 * Adjust the inter-word gap by shifting the next word's bbox via rebox.
 *
 * The gap between word `wi` and word `wi+1` is:
 *   gap = word[wi+1].bbox.x − (word[wi].bbox.x + word[wi].bbox.width)
 *
 * Adjusting by `deltaX` pixels shifts word `wi+1` left (negative) or right
 * (positive), widening or narrowing the gap.  The caller is responsible for
 * clamping `deltaX` so the resulting gap stays non-negative.
 *
 * Delegates to ``useReboxWord`` on word ``wi+1``.
 */
export function useAdjustWordGap(projectId: string, pageIndex: number) {
  const reboxMutation = useReboxWord(projectId, pageIndex);

  return {
    mutate: ({
      lineIndex,
      wordIndex,
      nextWordBbox,
      deltaX,
    }: {
      lineIndex: number;
      wordIndex: number;
      /** The next word's (wi+1) current bounding box. */
      nextWordBbox: BBox;
      /** Pixels to shift the next word. Positive = increase gap, negative = decrease. */
      deltaX: number;
    }) => {
      if (Math.round(deltaX) === 0) return;
      reboxMutation.mutate({
        lineIndex,
        wordIndex: wordIndex + 1, // rebox the NEXT word
        bbox: {
          x: nextWordBbox.x + deltaX,
          y: nextWordBbox.y,
          width: nextWordBbox.width,
          height: nextWordBbox.height,
        },
      });
    },
    isPending: reboxMutation.isPending,
  };
}

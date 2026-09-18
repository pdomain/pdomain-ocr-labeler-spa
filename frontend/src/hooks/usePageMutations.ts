// usePageMutations.ts — TanStack Query mutations for page-level actions.
//
// Spec: docs/specs/2026-05-12-page-actions-design.md
// Issues #215 (Reload OCR / Reload OCR Edited), #216 (Save/Load/Rematch)
//
// All mutations use the shared page URL base:
//   /api/projects/{projectId}/pages/{pageIndex}/<action>
//
// Reload OCR variants: 202+job_id response.
// Save Project: 202+job_id at the project level.
// Save Page, Load Page, Rematch GT: synchronous, return PagePayload or SavePageResponse.

import { useIsMutating, useMutation, useQueryClient } from "@tanstack/react-query";
import type { components } from "../api/types";

export type ReloadOCRResponse = components["schemas"]["ReloadOCRResponse"];
export type SavePageResponse = components["schemas"]["SavePageResponse"];
export type SaveProjectResponse = components["schemas"]["SaveProjectResponse"];
export type PagePayload = components["schemas"]["PagePayload"];
export type RotatePageResponse = components["schemas"]["RotatePageResponse"];
export type AutoRotateAllResponse = components["schemas"]["AutoRotateAllResponse"];
export type PageKind = components["schemas"]["PageKind"];
export type BBox = components["schemas"]["BBox"];
export type ErasePixelsRequest = components["schemas"]["ErasePixelsRequest"];
export type EraseShape = ErasePixelsRequest["shape"];

// ─── internal helpers ──────────────────────────────────────────────────────

async function apiPost<T>(url: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: signal ?? null,
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

/** The `mutationKey` `useErasePagePixels` registers under (see its docstring). */
function erasePagePixelsMutationKey(projectId: string, pageIndex: number): readonly unknown[] {
  return ["erase-page-pixels", projectId, pageIndex];
}

/**
 * Client-side timeout for the erase-pixels POST (reviewer finding 2,
 * P1-CANVAS-ERASE follow-up).
 *
 * The route does a synchronous page-image write: clamp + fill the bbox,
 * `finalize_page_structure`, cv2-encode the whole page to PNG and persist it
 * as a blob, an event-store write, then build and return the full
 * `PagePayload` (see `_erase_pixels_on_page_image` / `erase_page_pixels` in
 * `api/pages.py`). All of that is normally sub-second, but a large archival
 * scan's cv2 encode + full-payload serialization can take a few seconds
 * under load. 20s is generous headroom over that worst case while still
 * failing well before an indefinite hang — without a timeout, `apiPost`'s
 * bare `fetch` had no bound at all, so a request that never settled left
 * `ProjectPage`'s in-flight erase guard stuck for the life of the mount,
 * with no toast and no way back (the caller's `mutate` promise just never
 * resolved or rejected).
 */
export const ERASE_PAGE_PIXELS_TIMEOUT_MS = 20_000;

// ─── useReloadOcr (#215) ───────────────────────────────────────────────────

/**
 * Trigger OCR reload for a page (use_edited_image: false).
 * Returns a 202 response with job_id; caller uses useJobProgress to track.
 */
export function useReloadOcr(projectId: string, pageIndex: number) {
  return useMutation<ReloadOCRResponse>({
    mutationFn: () =>
      apiPost<ReloadOCRResponse>(`${pageBase(projectId, pageIndex)}/reload-ocr`, {
        use_edited_image: false,
      }),
    onSuccess: () => {
      // Page data will update when the job completes — invalidate then.
      // Callers are responsible for watching useJobProgress and invalidating.
    },
  });
}

// ─── useReloadOcrEdited (#215) ────────────────────────────────────────────

/** The `mutationKey` `useReloadOcrEdited` registers under (see its docstring). */
function reloadOcrEditedMutationKey(projectId: string, pageIndex: number): readonly unknown[] {
  return ["reload-ocr-edited", projectId, pageIndex];
}

/**
 * True while a Reload OCR (Edited) request for this page is in flight,
 * regardless of which component instance started it.
 *
 * `ProjectPage.tsx` (Mod+Shift+R hotkey gate) and `PageActionsCompact.tsx`
 * (the "Reload OCR (Edited)" button) each hold their own
 * `useReloadOcrEdited(...)` instance. Without a shared `mutationKey`,
 * clicking the button doesn't stop the hotkey's own `isPending` — which only
 * ever sees mutations *it* started — from staying false, so the hotkey
 * re-opens the confirm dialog and can fire a second re-OCR while the first
 * is still running. Re-OCR resets the page's undo history, so that's real
 * data loss, not a harmless double click. Same pattern as
 * useRegionMutations.ts's `useRegionDecisionPending`.
 */
export function useReloadOcrEditedPending(projectId: string, pageIndex: number): boolean {
  return useIsMutating({ mutationKey: reloadOcrEditedMutationKey(projectId, pageIndex) }) > 0;
}

/**
 * Trigger OCR reload for a page using the edited image (use_edited_image: true).
 * Returns 202 + job_id; same job-tracking pattern as useReloadOcr.
 */
export function useReloadOcrEdited(projectId: string, pageIndex: number) {
  return useMutation<ReloadOCRResponse>({
    mutationKey: reloadOcrEditedMutationKey(projectId, pageIndex),
    mutationFn: () =>
      apiPost<ReloadOCRResponse>(`${pageBase(projectId, pageIndex)}/reload-ocr`, {
        use_edited_image: true,
      }),
  });
}

// ─── useSavePage (#216) ───────────────────────────────────────────────────

/**
 * Save the current page to the filesystem (labeled lane).
 * Synchronous: returns SavePageResponse with saved:true and the new page_source.
 * On success, invalidate the page query so the source badge refreshes.
 */
export function useSavePage(projectId: string, pageIndex: number) {
  const qc = useQueryClient();
  return useMutation<SavePageResponse>({
    mutationFn: () => apiPost<SavePageResponse>(`${pageBase(projectId, pageIndex)}/save`, {}),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
    },
  });
}

// ─── useSaveProject (#216) ────────────────────────────────────────────────

/**
 * Save all pages in the project (202+job_id).
 * Long-running; caller uses useJobProgress to show progress overlay.
 */
export function useSaveProject(projectId: string) {
  return useMutation<SaveProjectResponse>({
    mutationFn: () =>
      apiPost<SaveProjectResponse>(`/api/projects/${encodeURIComponent(projectId)}/save-all`, {}),
  });
}

// ─── useLoadPage (#216) ───────────────────────────────────────────────────

/**
 * Re-load the page from disk, discarding any in-memory edits.
 * Synchronous; returns the refreshed PagePayload.
 * On success, invalidate the page query to sync UI state.
 */
export function useLoadPage(projectId: string, pageIndex: number) {
  const qc = useQueryClient();
  return useMutation<PagePayload>({
    mutationFn: () => apiPost<PagePayload>(`${pageBase(projectId, pageIndex)}/load`, {}),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
    },
  });
}

// ─── useRematchGt (#216) ─────────────────────────────────────────────────

/**
 * Re-run GT alignment for the current page.
 * Synchronous; returns the updated PagePayload.
 * On success, invalidate the page query.
 */
export function useRematchGt(projectId: string, pageIndex: number) {
  const qc = useQueryClient();
  return useMutation<PagePayload>({
    mutationFn: () => apiPost<PagePayload>(`${pageBase(projectId, pageIndex)}/rematch-gt`, {}),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
    },
  });
}

// ─── useRotatePage (S8.2 + S8.4) ─────────────────────────────────────────

/**
 * Rotate a page image by a given number of degrees.
 *
 * POST .../rotate with {degrees, manual: true} → 202 + job_id.
 * Caller uses useJobProgress to track completion and then invalidate the page.
 */
export function useRotatePage(projectId: string, pageIndex: number) {
  return useMutation<RotatePageResponse, Error, { degrees: number }>({
    mutationFn: ({ degrees }) =>
      apiPost<RotatePageResponse>(`${pageBase(projectId, pageIndex)}/rotate`, {
        degrees,
        manual: true,
      }),
  });
}

// ─── useAutoRotateAll (P2 / C29) ──────────────────────────────────────────

/**
 * Trigger the batch auto-rotate job for every page in the project.
 *
 * POST /api/projects/{id}/auto-rotate-all with {} → 202 + job_id.
 * The backend uses the configured auto-rotate method (OCR config) when no
 * method is supplied, and skips manually-rotated pages
 * (overwrite_manual defaults to false server-side).
 * Returns 503 when the rotation module is unavailable.
 */
export function useAutoRotateAll(projectId: string) {
  return useMutation<AutoRotateAllResponse>({
    mutationFn: () =>
      apiPost<AutoRotateAllResponse>(
        `/api/projects/${encodeURIComponent(projectId)}/auto-rotate-all`,
        {},
      ),
  });
}

// ─── useUndoPage / useRedoPage (event-store undo H-C) ──────────────────────

/**
 * Undo the last page mutation via blob-version restore.
 *
 * POST .../undo → 200 PagePayload (restored state + refreshed `history`
 * flags) or 409 when nothing is undoable. On success, invalidate the page
 * query so canvas/worklist/right-panel refetch the restored content, and
 * the `["page-kinds", projectId]` prefix — pdomain-ocr-synth's
 * 2026-09-17-page-kind-review-design.md "A proposal run and page history
 * both refresh the list": an undo can restore an earlier page blob that
 * carries a different (or no) confirmed kind, so any book-wide list must
 * refetch too.
 *
 * Spec: docs/specs/2026-06-12-event-store-undo.md (U-1).
 */
export function useUndoPage(projectId: string, pageIndex: number) {
  const qc = useQueryClient();
  return useMutation<PagePayload>({
    mutationFn: () => apiPost<PagePayload>(`${pageBase(projectId, pageIndex)}/undo`, {}),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
      void qc.invalidateQueries({ queryKey: ["page-kinds", projectId] });
    },
  });
}

/**
 * Re-apply the next undone version (symmetric to useUndoPage).
 *
 * POST .../redo → 200 PagePayload or 409 at the newest version. Also
 * invalidates the `["page-kinds", projectId]` prefix — see useUndoPage.
 *
 * Spec: docs/specs/2026-06-12-event-store-undo.md (U-2).
 */
export function useRedoPage(projectId: string, pageIndex: number) {
  const qc = useQueryClient();
  return useMutation<PagePayload>({
    mutationFn: () => apiPost<PagePayload>(`${pageBase(projectId, pageIndex)}/redo`, {}),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
      void qc.invalidateQueries({ queryKey: ["page-kinds", projectId] });
    },
  });
}

// ─── useConfirmPageKind (page-kind review) ─────────────────────────────────

/**
 * Confirm the current page's kind — the single-page half of
 * pdomain-ocr-synth's 2026-09-17-page-kind-review-design.md "The page
 * toolbar shows and confirms the current page's kind".
 *
 * POST .../page-kind → 200 PagePayload. On success, invalidate the page
 * query and the `["page-kinds", projectId]` prefix so a book-wide list
 * reflects the new confirmation.
 */
export function useConfirmPageKind(projectId: string, pageIndex: number) {
  const qc = useQueryClient();
  return useMutation<PagePayload, Error, { kind: PageKind; note?: string | null }>({
    mutationFn: ({ kind, note }) =>
      apiPost<PagePayload>(`${pageBase(projectId, pageIndex)}/page-kind`, {
        kind,
        note: note ?? null,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
      void qc.invalidateQueries({ queryKey: ["page-kinds", projectId] });
    },
  });
}

// ─── useErasePagePixels (P1-CANVAS-ERASE) ──────────────────────────────────

/**
 * Erase pixels directly against the page image from a page-space bbox.
 *
 * The page-scoped counterpart to `useErasePixels` (useWordMutations.ts). The
 * word-scoped route anchors an erase op onto a `(line_index, word_index)`
 * purely for selection feedback — the erase rect always comes from
 * `body.bbox` in page-image coordinates. Canvas erase-mode drags
 * (`PageImageCanvas` "erase" mode) have no word to anchor to, so they call
 * this route instead: `POST /api/projects/{pid}/pages/{idx}/erase-pixels`.
 *
 * Registers under a shared `mutationKey` (like `useRegionMutations.ts`'s
 * `decisionMutationKey`) so `useIsMutating` could see an in-flight erase from
 * any hook instance. ProjectPage's canvas drag handler actually guards
 * duplicate drags with its own synchronous ref rather than this key (see
 * `handleErasePixels`'s docstring for why), but the shared key keeps a
 * cross-instance guard available if a second call site (e.g. a future erase
 * toolbar button) starts sharing the mode.
 *
 * On success, invalidates the page query so the canvas re-renders with the
 * erased pixels.
 *
 * The request is bounded by `ERASE_PAGE_PIXELS_TIMEOUT_MS` via an
 * `AbortController`: a request that never settles aborts and the returned
 * promise rejects with a clear timeout `Error` instead of hanging forever
 * (reviewer finding 2). Callers already route mutation errors to a toast and
 * release any in-flight guard from `onError`/`onSettled` (`ProjectPage`'s
 * `handleErasePixels`), so a timeout surfaces the same way any other erase
 * failure does.
 */
export function useErasePagePixels(projectId: string, pageIndex: number) {
  const qc = useQueryClient();
  return useMutation<PagePayload, Error, { bbox: BBox; fillValue?: number; shape?: EraseShape }>({
    mutationKey: erasePagePixelsMutationKey(projectId, pageIndex),
    mutationFn: async ({ bbox, fillValue = 255, shape = "rect" }) => {
      const body: ErasePixelsRequest = { bbox, fill_value: fillValue, shape };
      const controller = new AbortController();
      const timeoutId = setTimeout(() => {
        controller.abort();
      }, ERASE_PAGE_PIXELS_TIMEOUT_MS);
      try {
        return await apiPost<PagePayload>(
          `${pageBase(projectId, pageIndex)}/erase-pixels`,
          body,
          controller.signal,
        );
      } catch (err) {
        if (controller.signal.aborted) {
          throw new Error(
            `Erase timed out after ${String(ERASE_PAGE_PIXELS_TIMEOUT_MS / 1000)}s — the page image write took too long.`,
            { cause: err },
          );
        }
        throw err;
      } finally {
        clearTimeout(timeoutId);
      }
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
    },
  });
}

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

import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { components } from "../api/types";

export type ReloadOCRResponse = components["schemas"]["ReloadOCRResponse"];
export type SavePageResponse = components["schemas"]["SavePageResponse"];
export type SaveProjectResponse = components["schemas"]["SaveProjectResponse"];
export type PagePayload = components["schemas"]["PagePayload"];
export type RotatePageResponse = components["schemas"]["RotatePageResponse"];

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

function pageBase(projectId: string, pageIndex: number): string {
  return `/api/projects/${encodeURIComponent(projectId)}/pages/${encodeURIComponent(String(pageIndex))}`;
}

// ─── useReloadOcr (#215) ───────────────────────────────────────────────────

/**
 * Trigger OCR reload for a page (use_edited_image: false).
 * Returns a 202 response with job_id; caller uses useJobProgress to track.
 */
export function useReloadOcr(projectId: string, pageIndex: number) {
  const qc = useQueryClient();
  return useMutation<ReloadOCRResponse>({
    mutationFn: () =>
      apiPost<ReloadOCRResponse>(`${pageBase(projectId, pageIndex)}/reload-ocr`, {
        use_edited_image: false,
      }),
    onSuccess: () => {
      // Page data will update when the job completes — invalidate then.
      // Callers are responsible for watching useJobProgress and invalidating.
      void qc;
    },
  });
}

// ─── useReloadOcrEdited (#215) ────────────────────────────────────────────

/**
 * Trigger OCR reload for a page using the edited image (use_edited_image: true).
 * Returns 202 + job_id; same job-tracking pattern as useReloadOcr.
 */
export function useReloadOcrEdited(projectId: string, pageIndex: number) {
  return useMutation<ReloadOCRResponse>({
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

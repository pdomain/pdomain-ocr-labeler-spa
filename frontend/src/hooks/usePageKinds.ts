// usePageKinds.ts — TanStack Query hooks for the book-wide page-kinds list
// and bulk confirm.
//
// Spec: pdomain-ocr-synth's docs/specs/2026-09-17-page-kind-review-design.md
//   "One route lists every page's kind" — GET .../page-kinds
//   "One route confirms many pages" — POST .../page-kinds/confirm
//   "The route stays synchronous, and the SPA sends at most 25 pages per
//    request" — batches of 25, a progress toast between batches, and the
//    request stops (and reports) on an outright failure.
//
// `useBulkConfirmPageKinds` invalidates the `["page-kinds", projectId]`
// prefix and the `["page", projectId]` prefix on success, because any page
// in the book may have changed ("A book-wide list reviews many pages at
// once").

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { components } from "../api/types";
import { toast } from "../lib/toast";

export type PageKind = components["schemas"]["PageKind"];
export type PageKindsListResponse = components["schemas"]["PageKindsListResponse"];
export type PageKindsListItem = components["schemas"]["PageKindsListItem"];
export type ConfirmPageKindsBulkResponse = components["schemas"]["ConfirmPageKindsBulkResponse"];
export type ConfirmPageKindsResultItem = components["schemas"]["ConfirmPageKindsResultItem"];

/** The SPA sends at most this many pages per bulk-confirm request. */
const BULK_BATCH_SIZE = 25;

// ─── internal helpers ──────────────────────────────────────────────────────

async function apiGet<T>(url: string): Promise<T> {
  const res = await fetch(url);
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

// ─── usePageKinds ───────────────────────────────────────────────────────────

/** The `["page-kinds", projectId]` cache key `usePageKinds` registers under. */
export function pageKindsKey(projectId: string | undefined): readonly unknown[] {
  return ["page-kinds", projectId];
}

/**
 * Fetch the book-wide page-kinds list: every page, in page order, with its
 * proposed and confirmed kind.
 *
 * Disabled while `projectId` is undefined or empty, matching `usePage` and
 * `useReviewQueue`.
 */
export function usePageKinds(projectId: string | undefined) {
  return useQuery<PageKindsListResponse>({
    queryKey: pageKindsKey(projectId),
    queryFn: () =>
      apiGet<PageKindsListResponse>(
        `/api/projects/${encodeURIComponent(String(projectId))}/page-kinds`,
      ),
    enabled: projectId !== undefined && projectId !== "",
  });
}

// ─── useBulkConfirmPageKinds ────────────────────────────────────────────────

export interface BulkConfirmPageKindItem {
  page_index: number;
  kind: PageKind;
}

export interface BulkConfirmPageKindsVariables {
  items: BulkConfirmPageKindItem[];
  note?: string | null;
}

export interface BulkConfirmPageKindsSummary {
  confirmedCount: number;
  results: ConfirmPageKindsResultItem[];
}

/** Group non-`confirmed` results by status, e.g. "2 not_loaded, 1 store_unavailable". */
function summarizeUnconfirmed(results: ConfirmPageKindsResultItem[]): string {
  const byStatus = new Map<string, number>();
  for (const r of results) {
    if (r.status === "confirmed") continue;
    byStatus.set(r.status, (byStatus.get(r.status) ?? 0) + 1);
  }
  return Array.from(byStatus.entries())
    .map(([status, count]) => `${String(count)} ${status}`)
    .join(", ");
}

/**
 * Confirm many pages' kinds in one action, batching at most
 * `BULK_BATCH_SIZE` pages per request (design: "the SPA sends at most 25
 * pages per request").
 *
 * A loading toast reports how many pages are done after each batch. If a
 * batch fails outright, an error toast reports how many pages were
 * confirmed before the failure and the mutation stops — no later batch is
 * sent. On completion, a success toast reports the total confirmed and
 * names any pages not confirmed, by status.
 */
export function useBulkConfirmPageKinds(projectId: string) {
  const qc = useQueryClient();
  return useMutation<BulkConfirmPageKindsSummary, Error, BulkConfirmPageKindsVariables>({
    mutationFn: async ({ items, note }) => {
      const allResults: ConfirmPageKindsResultItem[] = [];
      let confirmedCount = 0;
      let doneCount = 0;

      for (let i = 0; i < items.length; i += BULK_BATCH_SIZE) {
        const batch = items.slice(i, i + BULK_BATCH_SIZE);
        let response: ConfirmPageKindsBulkResponse;
        try {
          response = await apiPost<ConfirmPageKindsBulkResponse>(
            `/api/projects/${encodeURIComponent(projectId)}/page-kinds/confirm`,
            { pages: batch, note: note ?? null },
          );
        } catch (err) {
          toast.error(
            `Confirming page kinds failed. ${String(doneCount)} page(s) were confirmed before the error.`,
          );
          throw err;
        }
        const results = response.results ?? [];
        allResults.push(...results);
        confirmedCount += response.confirmed_count;
        doneCount += batch.length;
        toast.info(`Confirmed ${String(doneCount)} of ${String(items.length)} page(s)…`, {
          id: "bulk-page-kind-confirm",
        });
      }

      const unconfirmedSummary = summarizeUnconfirmed(allResults);
      toast.success(
        unconfirmedSummary
          ? `Confirmed ${String(confirmedCount)} page(s). Not confirmed: ${unconfirmedSummary}.`
          : `Confirmed ${String(confirmedCount)} page(s).`,
        { id: "bulk-page-kind-confirm" },
      );

      return { confirmedCount, results: allResults };
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["page-kinds", projectId] });
      void qc.invalidateQueries({ queryKey: ["page", projectId] });
    },
  });
}

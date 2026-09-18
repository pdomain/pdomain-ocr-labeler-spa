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
// prefix and the `["page", projectId]` prefix on settle — success or error
// — because a batch already confirmed before a later batch fails outright
// still changed pages ("A book-wide list reviews many pages at once").

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { invalidateBookReviewQueue } from "./useBookReviewQueue";
// `PageKind` is already declared and exported from usePageMutations.ts
// (the alias every other `PageKind`-typed consumer — PageActionsCompact.tsx,
// PageKindsDialog.tsx — imports); reuse it here rather than redeclaring a
// second, unimported copy of the same generated schema alias.
import type { PageKind } from "./usePageMutations";
import type { components } from "../api/types";
import { toast } from "../lib/toast";

export type PageKindsListResponse = components["schemas"]["PageKindsListResponse"];
export type PageKindsListItem = components["schemas"]["PageKindsListItem"];
export type ConfirmPageKindsBulkResponse = components["schemas"]["ConfirmPageKindsBulkResponse"];
// Not exported: nothing outside this file needs the per-item result shape —
// callers of `useBulkConfirmPageKinds` consume its `BulkConfirmPageKindsSummary`
// (below), not `ConfirmPageKindsResultItem[]` directly.
type ConfirmPageKindsResultItem = components["schemas"]["ConfirmPageKindsResultItem"];

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

/**
 * The `["page-kinds", projectId]` cache key `usePageKinds` registers under.
 * Not exported: unlike `reviewQueueKey`/`bookReviewQueueKey`, nothing reads
 * this key outside a render (e.g. via `getQueryData`) today, and every
 * invalidation call site in this codebase hand-rolls the two-element prefix
 * array directly (see `useRegionMutations.ts`, `PageActionsCompact.tsx`) —
 * so there is no current external caller for this builder.
 */
function pageKindsKey(projectId: string | undefined): readonly unknown[] {
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
            `Confirming page kinds failed. ${String(confirmedCount)} page(s) were confirmed before the error.`,
          );
          throw err;
        }
        const results = response.results ?? [];
        allResults.push(...results);
        confirmedCount += response.confirmed_count;
        toast.info(`Confirmed ${String(confirmedCount)} of ${String(items.length)} page(s)…`, {
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
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ["page-kinds", projectId] });
      void qc.invalidateQueries({ queryKey: ["page", projectId] });
      // One-answer-to-what-to-review-next: same reasoning as
      // useConfirmPageKind (usePageMutations.ts) — a bulk confirm changes
      // page_kind's own count and can unblock region.
      invalidateBookReviewQueue(qc, projectId);
    },
  });
}

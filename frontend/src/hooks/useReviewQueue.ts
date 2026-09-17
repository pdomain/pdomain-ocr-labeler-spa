// useReviewQueue.ts — TanStack Query hook for GET .../regions/review-queue.
// Spec: docs/specs/2026-09-17-book-review-queue-design.md
//   "One route answers the question for people and agents alike" (the route)
//   "Two keys move between pages that have work" / "A count stays visible"
//   (this hook's consumers: useRegionReviewHotkeys.ts, Rail.tsx)
//
// `order` defaults to "reading" (page order, then top-to-bottom, then
// left-to-right) — the order the bracket-key navigation in
// useRegionReviewHotkeys.ts reads `pages` in. `limit` defaults to 0: neither
// the bracket keys nor the Rail badge need `items`, only `total_undecided`
// and the per-page `pages` summary, which is always present regardless of
// `limit`.
//
// Invalidated by the `["review-queue", projectId]` prefix from every region
// decision (useRegionMutations.ts) and from both proposal runs completing
// (PageActionsCompact.tsx) — TanStack Query's default `invalidateQueries`
// match is a prefix match, so invalidating `["review-queue", projectId]`
// covers every `order`/`limit` variant cached under this key.

import { useQuery } from "@tanstack/react-query";
import type { components } from "../api/types";

export type RegionReviewQueueResponse = components["schemas"]["RegionReviewQueueResponse"];
export type ReviewQueueOrder = "reading" | "confidence";

export interface UseReviewQueueOptions {
  order?: ReviewQueueOrder;
  limit?: number;
}

/**
 * The `["review-queue", projectId, order, limit]` cache key `useReviewQueue`
 * registers under. Exported so a caller that needs the *current* cached
 * value at a specific instant (rather than this render's possibly-stale
 * reactive read) can read it straight from the `QueryClient` with
 * `getQueryData(reviewQueueKey(...))` — see the "book's undecided count"
 * comment in useRegionReviewHotkeys.ts.
 */
export function reviewQueueKey(
  projectId: string | undefined,
  order: ReviewQueueOrder = "reading",
  limit = 0,
): readonly unknown[] {
  return ["review-queue", projectId, order, limit];
}

/**
 * Throw on non-2xx; return parsed JSON on success. Mirrors usePage.ts.
 *
 * `projectId` is `string | undefined` here (not asserted non-null) because
 * this only ever runs while `enabled` is true — the same pattern usePage.ts
 * uses for its own possibly-undefined `pageIndex`.
 */
async function fetchReviewQueue(
  projectId: string | undefined,
  order: ReviewQueueOrder,
  limit: number,
): Promise<RegionReviewQueueResponse> {
  const params = new URLSearchParams({ order, limit: String(limit) });
  const response = await fetch(
    `/api/projects/${encodeURIComponent(String(projectId))}/regions/review-queue?${params.toString()}`,
  );
  if (!response.ok) {
    const text = await response.text();
    let message = response.statusText;
    try {
      const body = JSON.parse(text) as { message?: string };
      if (body.message) message = body.message;
    } catch {
      if (text) message = text;
    }
    throw Object.assign(new Error(message), { status: response.status });
  }
  return response.json() as Promise<RegionReviewQueueResponse>;
}

/**
 * Fetch the book-level review queue: `total_undecided` and the per-page
 * `pages` summary (bounded by the book's page count, always in page order),
 * plus up to `limit` `items` ordered by `order`.
 *
 * Disabled while `projectId` is undefined or empty, matching `usePage`.
 *
 * @param projectId - project identifier
 * @param options.order - "reading" (default) or "confidence"; affects only `items`
 * @param options.limit - item cap, default 0 (the UI never needs `items`)
 */
export function useReviewQueue(projectId: string | undefined, options?: UseReviewQueueOptions) {
  const order: ReviewQueueOrder = options?.order ?? "reading";
  const limit = options?.limit ?? 0;

  return useQuery<RegionReviewQueueResponse>({
    queryKey: reviewQueueKey(projectId, order, limit),
    queryFn: () => fetchReviewQueue(projectId, order, limit),
    enabled: projectId !== undefined && projectId !== "",
  });
}

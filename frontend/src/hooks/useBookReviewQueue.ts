// useBookReviewQueue.ts — TanStack Query hook for GET .../review-queue, the
// one-answer-per-kind book review queue.
// Spec: pdomain-ocr-synth's docs/specs/2026-09-18-one-answer-to-what-to-
//   review-next.md "One route, in the order the work happens" / "How the SPA
//   uses the new route".
//
// Modeled on useReviewQueue.ts (the region-only route this generalizes):
// same fetch-and-throw-on-non-2xx shape, same exported query-key builder so
// a caller that needs the *current* cached value outside a render (e.g. a
// hotkey handler) can read it straight from the `QueryClient`.
//
// This route answers for every kind in one response — there is no
// order/limit variant to key by, so the cache key is just
// `["review-queue-kinds", projectId]`.

import { useQuery } from "@tanstack/react-query";
import type { QueryClient } from "@tanstack/react-query";
import type { components } from "../api/types";

export type ReviewQueueKindEntry = components["schemas"]["ReviewQueueKindEntry"];
export type ReviewQueueKindName = ReviewQueueKindEntry["kind"];
export type BookReviewQueueResponse = components["schemas"]["ReviewQueueResponse"];

/** The order the backend returns kinds in — the order the work happens. */
export const REVIEW_QUEUE_KIND_ORDER: readonly ReviewQueueKindName[] = [
  "page_kind",
  "region",
  "word",
  "typography",
  "glyph",
] as const;

/** Human label for a kind, used everywhere one is shown to a person. */
export const REVIEW_QUEUE_KIND_LABELS: Record<ReviewQueueKindName, string> = {
  page_kind: "Page kind",
  region: "Region",
  word: "Word",
  typography: "Typography",
  glyph: "Glyph",
};

/**
 * The `["review-queue-kinds", projectId]` cache key `useBookReviewQueue`
 * registers under — see useReviewQueue.ts's `reviewQueueKey` for why this is
 * exported (a caller outside a render, e.g. a hotkey handler, reading the
 * *current* cached value via `getQueryData`).
 */
export function bookReviewQueueKey(projectId: string | undefined): readonly unknown[] {
  return ["review-queue-kinds", projectId];
}

/** Throw on non-2xx; return parsed JSON on success. Mirrors useReviewQueue.ts. */
async function fetchBookReviewQueue(
  projectId: string | undefined,
): Promise<BookReviewQueueResponse> {
  const response = await fetch(
    `/api/projects/${encodeURIComponent(String(projectId))}/review-queue`,
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
  return response.json() as Promise<BookReviewQueueResponse>;
}

/**
 * Fetch the book-level, per-kind review queue: one `ReviewQueueKindEntry`
 * per kind, in the order the work happens (page_kind, region, word,
 * typography, glyph).
 *
 * Disabled while `projectId` is undefined or empty, matching `useReviewQueue`.
 *
 * @param projectId - project identifier
 */
export function useBookReviewQueue(projectId: string | undefined) {
  return useQuery<BookReviewQueueResponse>({
    queryKey: bookReviewQueueKey(projectId),
    queryFn: () => fetchBookReviewQueue(projectId),
    enabled: projectId !== undefined && projectId !== "",
  });
}

/**
 * The kind the SPA should act on by default: pdomain-ocr-synth's design,
 * "How the SPA uses the new route" — "the first kind in the returned order
 * with outstanding work and no `blocked_by`". A kind with work but a
 * `blocked_by` value is waiting on something else, not the thing to do next.
 *
 * Picks by `REVIEW_QUEUE_KIND_ORDER` rather than the array's own order: the
 * backend happens to serialize `kinds` in that same sequence today
 * (`api/review_queue.py`'s `get_review_queue` builds the list in exactly
 * this order), but nothing about the wire format guarantees it, and this is
 * the one place "first" is priority-sensitive — silently trusting response
 * order would make a future backend reordering a silent misprioritization
 * here instead of a loud type error.
 *
 * Returns `undefined` when every kind is either done, unavailable, or
 * blocked — there is nothing to default to.
 */
export function firstActionableKind(
  kinds: readonly ReviewQueueKindEntry[],
): ReviewQueueKindEntry | undefined {
  const byKind = new Map(kinds.map((entry) => [entry.kind, entry]));
  for (const kind of REVIEW_QUEUE_KIND_ORDER) {
    const entry = byKind.get(kind);
    if (entry !== undefined && entry.outstanding > 0 && entry.blocked_by === null) {
      return entry;
    }
  }
  return undefined;
}

/** Invalidates the `["review-queue-kinds", projectId]` cache — every `useBookReviewQueue` variant for this project. */
export function invalidateBookReviewQueue(qc: QueryClient, projectId: string): void {
  void qc.invalidateQueries({ queryKey: bookReviewQueueKey(projectId) });
}

/**
 * "Waiting on X to be reviewed first." — the one sentence every surface
 * that shows `blocked_by` uses (Queue drawer banner, bracket-key toast).
 * Reviewer finding (low): the drawer and the keys used to say this two
 * different ways; a shared string keeps them from drifting apart again.
 */
export function blockedByMessage(blockedBy: ReviewQueueKindName): string {
  return `Waiting on ${REVIEW_QUEUE_KIND_LABELS[blockedBy]} to be reviewed first.`;
}

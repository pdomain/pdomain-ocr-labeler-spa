// useRegionMutations.ts — TanStack Query mutations for the region review surface.
// Spec: docs/specs/2026-09-17-region-review-surface-design.md
// Plan: docs/plans/2026-09-17-region-review-surface.md — Task 3
//
// Endpoints (all real per api/regions.py, mounted under /api/projects):
//   POST   /api/projects/{pid}/pages/{idx}/regions/proposals/{proposalId}/accept   → PagePayload
//   POST   /api/projects/{pid}/pages/{idx}/regions/proposals/{proposalId}/reject   → PagePayload
//   POST   /api/projects/{pid}/pages/{idx}/regions/proposals/{proposalId}/unreject → PagePayload
//   PATCH  /api/projects/{pid}/pages/{idx}/regions/{regionId}                      → PagePayload
//   DELETE /api/projects/{pid}/pages/{idx}/regions/{regionId}                      → PagePayload
//
// Every mutation invalidates ["page", projectId, pageIndex] on success and never
// writes the cache directly, matching every other mutation in hooks/useLineMutations.ts —
// the routes return a full PagePayload, but this file deliberately never calls
// setQueryData with it.
//
// Design: docs/specs/2026-09-17-book-review-queue-design.md "A count stays
// visible" — every decision also invalidates the ["review-queue", projectId]
// prefix, so the Rail badge and any future queue-driven navigation see the
// updated count and page summary once they next refetch.
//
// Whole-branch review defect 1 (a decision can be sent twice): `RegionDetail`
// and `useRegionReviewHotkeys` each create their own instances of these four
// mutations, so one instance's `isPending` never sees the other's in-flight
// request. All four share the `mutationKey` below — a held or double-tapped
// key, or a key pressed mid-panel-click, would otherwise fire a second
// request while the first is still in flight. `useRegionDecisionPending`
// reads that shared key through `useIsMutating`, whose mutation-key filter
// does a `partialMatchKey` (query-core's `matchMutation`/`utils.ts`) — the
// same prefix-match semantics `useIsFetching`/query filters use — so any
// hook instance sees a mutation any other instance started.

import { useIsMutating, useMutation, useQueryClient } from "@tanstack/react-query";
import { invalidateBookReviewQueue } from "./useBookReviewQueue";
import type { components } from "../api/types";

type PagePayload = components["schemas"]["PagePayload"];
type RegionRole = components["schemas"]["RegionRole"];
type AcceptRegionProposalRequest = components["schemas"]["AcceptRegionProposalRequest"];
type EditRegionRequest = components["schemas"]["EditRegionRequest"];

// ─── internal helpers ─────────────────────────────────────────────────────

/** The shared `mutationKey` every region-decision mutation below registers under. */
function decisionMutationKey(projectId: string, pageIndex: number): readonly unknown[] {
  return ["region-decision", projectId, pageIndex];
}

/**
 * True while any accept, reject, edit or delete mutation for this page is
 * in flight, regardless of which component instance started it.
 */
export function useRegionDecisionPending(projectId: string, pageIndex: number): boolean {
  return useIsMutating({ mutationKey: decisionMutationKey(projectId, pageIndex) }) > 0;
}

async function apiRequest<T>(url: string, method: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method };
  if (body !== undefined) {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(body);
  }
  const res = await fetch(url, init);
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

/**
 * Invalidate both the decided page and the book-level review queue.
 *
 * The queue key is invalidated by its `["review-queue", projectId]` prefix
 * (TanStack Query's default `invalidateQueries` match), which covers every
 * `order`/`limit` variant `useReviewQueue` may have cached.
 */
function invalidateAfterDecision(
  qc: ReturnType<typeof useQueryClient>,
  projectId: string,
  pageIndex: number,
): void {
  void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
  void qc.invalidateQueries({ queryKey: ["review-queue", projectId] });
  // One-answer-to-what-to-review-next: the Rail's next-kind badge and the
  // Queue panel's default both read useBookReviewQueue, whose region
  // outstanding count must stay in step with every decision the same way
  // the region-only route above does.
  invalidateBookReviewQueue(qc, projectId);
}

// ─── useAcceptProposal ─────────────────────────────────────────────────────

/**
 * Accept a region proposal, optionally overriding its role.
 *
 * Sends exactly `{}` with no override and exactly `{ role }` with one — never a
 * `role: undefined` key. The backend records disposition `edited` whenever an
 * override is present, so a stray key would mislabel every plain accept.
 */
export function useAcceptProposal(projectId: string, pageIndex: number) {
  const qc = useQueryClient();
  return useMutation<PagePayload, Error, { proposalId: string; role?: RegionRole }>({
    mutationKey: decisionMutationKey(projectId, pageIndex),
    mutationFn: ({ proposalId, role }) => {
      const body: AcceptRegionProposalRequest = role === undefined ? {} : { role };
      return apiRequest<PagePayload>(
        `${pageBase(projectId, pageIndex)}/regions/proposals/${encodeURIComponent(proposalId)}/accept`,
        "POST",
        body,
      );
    },
    onSuccess: () => {
      invalidateAfterDecision(qc, projectId, pageIndex);
    },
  });
}

// ─── useRejectProposal ─────────────────────────────────────────────────────

/** Reject a region proposal. No body. */
export function useRejectProposal(projectId: string, pageIndex: number) {
  const qc = useQueryClient();
  return useMutation<PagePayload, Error, { proposalId: string }>({
    mutationKey: decisionMutationKey(projectId, pageIndex),
    mutationFn: ({ proposalId }) =>
      apiRequest<PagePayload>(
        `${pageBase(projectId, pageIndex)}/regions/proposals/${encodeURIComponent(proposalId)}/reject`,
        "POST",
      ),
    onSuccess: () => {
      invalidateAfterDecision(qc, projectId, pageIndex);
    },
  });
}

// ─── useUnrejectProposal ────────────────────────────────────────────────────

/**
 * Bring a rejected proposal — a person's own, or one carried forward from an
 * earlier rejection — back to undecided. No body.
 *
 * Same shared `mutationKey` as accept/reject/edit/delete: a carried-rejection
 * "Bring back" click while another region decision for this page is in
 * flight is disabled, exactly as those already are.
 */
export function useUnrejectProposal(projectId: string, pageIndex: number) {
  const qc = useQueryClient();
  return useMutation<PagePayload, Error, { proposalId: string }>({
    mutationKey: decisionMutationKey(projectId, pageIndex),
    mutationFn: ({ proposalId }) =>
      apiRequest<PagePayload>(
        `${pageBase(projectId, pageIndex)}/regions/proposals/${encodeURIComponent(proposalId)}/unreject`,
        "POST",
      ),
    onSuccess: () => {
      invalidateAfterDecision(qc, projectId, pageIndex);
    },
  });
}

// ─── useEditRegion ──────────────────────────────────────────────────────────

/** Change a confirmed region's role. */
export function useEditRegion(projectId: string, pageIndex: number) {
  const qc = useQueryClient();
  return useMutation<PagePayload, Error, { regionId: string; role: RegionRole }>({
    mutationKey: decisionMutationKey(projectId, pageIndex),
    mutationFn: ({ regionId, role }) => {
      const body: EditRegionRequest = { role };
      return apiRequest<PagePayload>(
        `${pageBase(projectId, pageIndex)}/regions/${encodeURIComponent(regionId)}`,
        "PATCH",
        body,
      );
    },
    onSuccess: () => {
      invalidateAfterDecision(qc, projectId, pageIndex);
    },
  });
}

// ─── useDeleteRegion ────────────────────────────────────────────────────────

/** Delete a confirmed region. No body. */
export function useDeleteRegion(projectId: string, pageIndex: number) {
  const qc = useQueryClient();
  return useMutation<PagePayload, Error, { regionId: string }>({
    mutationKey: decisionMutationKey(projectId, pageIndex),
    mutationFn: ({ regionId }) =>
      apiRequest<PagePayload>(
        `${pageBase(projectId, pageIndex)}/regions/${encodeURIComponent(regionId)}`,
        "DELETE",
      ),
    onSuccess: () => {
      invalidateAfterDecision(qc, projectId, pageIndex);
    },
  });
}

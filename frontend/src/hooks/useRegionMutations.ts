// useRegionMutations.ts — TanStack Query mutations for the region review surface.
// Spec: docs/specs/2026-09-17-region-review-surface-design.md
// Plan: docs/plans/2026-09-17-region-review-surface.md — Task 3
//
// Endpoints (all real per api/regions.py, mounted under /api/projects):
//   POST   /api/projects/{pid}/pages/{idx}/regions/proposals/{proposalId}/accept → PagePayload
//   POST   /api/projects/{pid}/pages/{idx}/regions/proposals/{proposalId}/reject → PagePayload
//   PATCH  /api/projects/{pid}/pages/{idx}/regions/{regionId}                    → PagePayload
//   DELETE /api/projects/{pid}/pages/{idx}/regions/{regionId}                    → PagePayload
//
// Every mutation invalidates ["page", projectId, pageIndex] on success and never
// writes the cache directly, matching every other mutation in hooks/useLineMutations.ts —
// the routes return a full PagePayload, but this file deliberately never calls
// setQueryData with it.

import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { components } from "../api/types";

type PagePayload = components["schemas"]["PagePayload"];
type RegionRole = components["schemas"]["RegionRole"];
type AcceptRegionProposalRequest = components["schemas"]["AcceptRegionProposalRequest"];
type EditRegionRequest = components["schemas"]["EditRegionRequest"];

// ─── internal helpers ─────────────────────────────────────────────────────

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
    mutationFn: ({ proposalId, role }) => {
      const body: AcceptRegionProposalRequest = role === undefined ? {} : { role };
      return apiRequest<PagePayload>(
        `${pageBase(projectId, pageIndex)}/regions/proposals/${encodeURIComponent(proposalId)}/accept`,
        "POST",
        body,
      );
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
    },
  });
}

// ─── useRejectProposal ─────────────────────────────────────────────────────

/** Reject a region proposal. No body. */
export function useRejectProposal(projectId: string, pageIndex: number) {
  const qc = useQueryClient();
  return useMutation<PagePayload, Error, { proposalId: string }>({
    mutationFn: ({ proposalId }) =>
      apiRequest<PagePayload>(
        `${pageBase(projectId, pageIndex)}/regions/proposals/${encodeURIComponent(proposalId)}/reject`,
        "POST",
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
    },
  });
}

// ─── useEditRegion ──────────────────────────────────────────────────────────

/** Change a confirmed region's role. */
export function useEditRegion(projectId: string, pageIndex: number) {
  const qc = useQueryClient();
  return useMutation<PagePayload, Error, { regionId: string; role: RegionRole }>({
    mutationFn: ({ regionId, role }) => {
      const body: EditRegionRequest = { role };
      return apiRequest<PagePayload>(
        `${pageBase(projectId, pageIndex)}/regions/${encodeURIComponent(regionId)}`,
        "PATCH",
        body,
      );
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
    },
  });
}

// ─── useDeleteRegion ────────────────────────────────────────────────────────

/** Delete a confirmed region. No body. */
export function useDeleteRegion(projectId: string, pageIndex: number) {
  const qc = useQueryClient();
  return useMutation<PagePayload, Error, { regionId: string }>({
    mutationFn: ({ regionId }) =>
      apiRequest<PagePayload>(
        `${pageBase(projectId, pageIndex)}/regions/${encodeURIComponent(regionId)}`,
        "DELETE",
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
    },
  });
}

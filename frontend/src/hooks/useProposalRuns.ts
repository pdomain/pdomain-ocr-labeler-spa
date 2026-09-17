// useProposalRuns.ts — TanStack Query mutations that start the page-kind and
// region proposal runs.
// Spec: docs/specs/2026-09-17-region-review-surface-design.md
// Plan: docs/plans/2026-09-17-region-review-surface.md — Task 3
//
// Endpoints:
//   POST /api/projects/{pid}/propose-page-kinds → 202 { job_id }, no request body
//   POST /api/projects/{pid}/regions/propose     → 202 { job_id }, body {}
//
// Neither hook invalidates anything on success. Task 6's job-completion handler
// invalidates the affected queries once the run actually finishes.

import { useMutation } from "@tanstack/react-query";
import type { components } from "../api/types";

type ProposePageKindsResponse = components["schemas"]["ProposePageKindsResponse"];
type StartRegionProposalRunResponse = components["schemas"]["StartRegionProposalRunResponse"];

// ─── internal helpers ─────────────────────────────────────────────────────

async function apiPost<T>(url: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method: "POST" };
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

// ─── useProposePageKinds ────────────────────────────────────────────────────

/**
 * Start the book-scoped page-kind proposal run.
 *
 * The route takes no request body — sends none, matching its OpenAPI contract.
 */
export function useProposePageKinds(projectId: string) {
  // TError and TVariables are left to their defaults (Error, void):
  // @typescript-eslint/no-invalid-void-type forbids spelling `void` out as an
  // explicit generic argument, and no-unnecessary-type-arguments flags
  // `Error` as redundant once `void` is omitted — useMutation's own defaults
  // already produce the same UseMutationResult type either way.
  return useMutation<ProposePageKindsResponse>({
    mutationFn: () =>
      apiPost<ProposePageKindsResponse>(
        `/api/projects/${encodeURIComponent(projectId)}/propose-page-kinds`,
      ),
  });
}

// ─── useProposeRegions ──────────────────────────────────────────────────────

/**
 * Start the book-scoped region proposal run.
 *
 * Sends an empty body: `StartRegionProposalRunRequest.model_id` and
 * `.model_version` are both defaulted server-side (`null-detector` / `0.0.0`),
 * so `{}` is a valid request even though the generated OpenAPI type marks
 * both fields required — a generator quirk around Pydantic field defaults,
 * not a real constraint on the wire.
 */
export function useProposeRegions(projectId: string) {
  return useMutation<StartRegionProposalRunResponse>({
    mutationFn: () =>
      apiPost<StartRegionProposalRunResponse>(
        `/api/projects/${encodeURIComponent(projectId)}/regions/propose`,
        {},
      ),
  });
}

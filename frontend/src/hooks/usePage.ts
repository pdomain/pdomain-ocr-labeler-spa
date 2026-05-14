// usePage.ts — TanStack Query hook for GET /api/projects/{id}/pages/{idx}.
//
// Spec: docs/specs/2026-05-12-frontend-shell-design.md §Hooks
// Issue #192
//
// `pageIndex` is 0-based (internal idx0). The public URL uses 1-based
// /page/{n} — the caller is responsible for the conversion.
//
// `lineFilter` maps to the ?line_filter query param; null means "all".

import { useQuery } from "@tanstack/react-query";
import type { components } from "../api/types";

export type PagePayload = components["schemas"]["PagePayload"];
export type LineFilter = components["schemas"]["LineFilter"];

/** Throw on non-2xx; return parsed JSON on success. */
async function apiFetch<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) {
    const text = await response.text();
    let message = response.statusText;
    try {
      const body = JSON.parse(text) as { message?: string };
      if (body.message) message = body.message;
    } catch {
      if (text) message = text;
    }
    const err = Object.assign(new Error(message), { status: response.status });
    throw err;
  }
  return response.json() as Promise<T>;
}

/**
 * Fetch the page payload for a project page.
 *
 * @param projectId  - project identifier
 * @param pageIndex  - 0-based page index (idx0)
 * @param lineFilter - optional server-side line filter; defaults to "all"
 */
export function usePage(
  projectId: string | undefined,
  pageIndex: number | undefined,
  lineFilter?: LineFilter | null,
) {
  const filter: LineFilter = lineFilter ?? "all";

  return useQuery<PagePayload>({
    queryKey: ["page", projectId, pageIndex, filter],
    queryFn: () => {
      const params = new URLSearchParams({ line_filter: filter });
      return apiFetch<PagePayload>(
        `/api/projects/${projectId}/pages/${pageIndex}?${params.toString()}`,
      );
    },
    enabled:
      projectId !== undefined && projectId !== "" && pageIndex !== undefined && pageIndex >= 0,
    staleTime: 30_000,
  });
}

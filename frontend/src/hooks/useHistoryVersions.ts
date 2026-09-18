// useHistoryVersions.ts — TanStack Query hook for GET .../history/versions.
//
// U-M7 (docs/specs/2026-06-12-event-store-undo.md "history panel +
// jump-to-version"): the read-only version list backing the Drawer's
// History tab. Mirrors useReviewQueue.ts's fetch/error-shape convention.
//
// Disabled until `projectId` is non-empty, matching useReviewQueue/usePage.
// The query key is scoped by page — switching pages must never show the
// previous page's version rows while the new page's list loads.

import { useQuery } from "@tanstack/react-query";
import type { components } from "../api/types";

export type HistoryVersionInfo = components["schemas"]["HistoryVersionInfo"];

export function historyVersionsKey(
  projectId: string | undefined,
  pageIndex: number | undefined,
): readonly unknown[] {
  return ["page-history-versions", projectId, pageIndex];
}

async function fetchHistoryVersions(
  projectId: string | undefined,
  pageIndex: number | undefined,
): Promise<HistoryVersionInfo[]> {
  const response = await fetch(
    `/api/projects/${encodeURIComponent(String(projectId))}/pages/${encodeURIComponent(String(pageIndex))}/history/versions`,
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
  return response.json() as Promise<HistoryVersionInfo[]>;
}

/**
 * Fetch the active version chain for one page (oldest first), each row
 * carrying `node_id`, `label`, `timestamp` (nullable — see
 * `core/page_history.py` `VersionEntry`), and `is_current`.
 *
 * Enabled only while `projectId` is non-empty and `pageIndex` is defined —
 * the Drawer mounts every tab's component regardless of which is active, so
 * this hook must not fire a request before the History tab is actually open
 * in a caller that gates `enabled` on tab visibility too.
 */
export function useHistoryVersions(
  projectId: string | undefined,
  pageIndex: number | undefined,
  options?: { enabled?: boolean },
) {
  const enabled =
    (options?.enabled ?? true) &&
    projectId !== undefined &&
    projectId !== "" &&
    pageIndex !== undefined;
  return useQuery<HistoryVersionInfo[]>({
    queryKey: historyVersionsKey(projectId, pageIndex),
    queryFn: () => fetchHistoryVersions(projectId, pageIndex),
    enabled,
  });
}

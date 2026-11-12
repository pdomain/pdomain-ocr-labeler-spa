import { useQuery } from "@tanstack/react-query";
import type { components } from "../api/types";

export type SavedExport = components["schemas"]["ExportManifest"];

async function fetchExportHistory(projectId: string): Promise<SavedExport[]> {
  const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/exports`);
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
  return response.json() as Promise<SavedExport[]>;
}

export function useExportHistory(projectId: string, completedRuns: number) {
  return useQuery({
    // A finished run rewrites the manifest, so each run count is its own read.
    queryKey: ["export-history", projectId, completedRuns],
    queryFn: () => fetchExportHistory(projectId),
    staleTime: 0,
    retry: false,
  });
}

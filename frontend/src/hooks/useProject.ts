// useProject.ts — TanStack Query hook for GET /api/projects/{projectId}.
//
// Spec: docs/specs/2026-05-12-frontend-shell-design.md §Hooks
// Issue #192
//
// Returns the LoadProjectResponse for the currently-loaded project.
// The endpoint returns 404 when no project is open or the requested id
// doesn't match the loaded one — in that case `data` is undefined and
// `error` carries an ApiError with status 404.

import { useQuery } from "@tanstack/react-query";

// Interim type matching the slice-5 LoadProjectResponse (M3 will swap
// current_page_index → current_page: PagePayload).
export interface ProjectResponse {
  project: {
    project_id: string;
    project_root: string;
    image_paths: string[];
    ground_truth_map: Record<string, unknown>;
    [key: string]: unknown;
  };
  current_page_index: number;
  generation: number;
}

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
 * Fetch the currently-loaded project by id.
 *
 * Returns `undefined` data when no project is open (404). Components that
 * need to react to the missing-project case should check `isError` with a
 * guard on `(error as { status: number }).status === 404`.
 */
export function useProject(projectId: string | undefined) {
  return useQuery<ProjectResponse>({
    queryKey: ["project", projectId],
    queryFn: () => apiFetch<ProjectResponse>(`/api/projects/${projectId}`),
    enabled: projectId !== undefined && projectId !== "",
    staleTime: 30_000,
  });
}

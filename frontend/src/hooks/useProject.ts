// useProject.ts — TanStack Query hook for GET /api/projects/{projectId}.
//
// Spec: docs/specs/2026-05-12-frontend-shell-design.md §Hooks
// Issue #192
//
// Returns the flat Project object for the currently-loaded project.
// The endpoint returns 404 when no project is open or the requested id
// doesn't match the loaded one — in that case `data` is undefined and
// `error` carries an ApiError with status 404.
//
// Shape note: GET /api/projects/{id} returns the flat Project model —
// NOT the LoadProjectResponse wrapper (which is only returned by
// POST /api/projects/load). See api/projects.py:get_project_by_id
// which does `project.model_dump(mode="json")` directly.

import { useQuery } from "@tanstack/react-query";

/**
 * The flat Project type returned by GET /api/projects/{project_id}.
 * Identical to components["schemas"]["Project"] but that schema is
 * typed as `unknown` in the generated types.ts (the FastAPI handler
 * returns a raw JSONResponse rather than a typed response_model).
 * This interface is hand-written to match the Python Project model.
 */
export interface ProjectResponse {
  project_id: string;
  project_root: string;
  image_paths: string[];
  ground_truth_map: Record<string, string>;
  version: string;
  source_lib: string;
  total_pages: number;
  saved_pages: number;
  current_page_index: number;
  include_images: boolean;
  copied_images: boolean;
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
 *
 * The returned `data` is the flat Project model (NOT the LoadProjectResponse
 * wrapper — that's only returned by POST /api/projects/load).
 */
export function useProject(projectId: string | undefined) {
  return useQuery<ProjectResponse>({
    queryKey: ["project", projectId],
    queryFn: () => apiFetch<ProjectResponse>(`/api/projects/${projectId}`),
    enabled: projectId !== undefined && projectId !== "",
    staleTime: 30_000,
  });
}

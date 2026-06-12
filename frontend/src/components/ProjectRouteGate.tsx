// ProjectRouteGate.tsx — deep-link auto-load gate for project routes.
//
// P4.3 (parity F14 / C57): the legacy labeler resolved AND loaded a project
// straight from the URL (`_initialize_from_url`). The SPA bounced any deep
// link to a not-yet-loaded project back to the RootPage grid, because
// GET /api/projects/{id} only answers for the project held in server memory.
//
// This gate wraps the ProjectPage route element (App.tsx). It shares the
// ["project", projectId] query with ProjectPage (same useProject hook), and:
//
//   - query success            → render children (ProjectPage).
//   - query 404                → resolve the project_root from
//                                GET /api/projects (disk scan) and fire
//                                POST /api/projects/load ONCE per projectId;
//                                show a loading overlay meanwhile. On load
//                                success the query is invalidated and
//                                refetches to success → children render.
//   - auto-load failure        → toast + navigate to "/" with
//                                skipSessionRedirect (the pre-existing
//                                not-found UX, formerly in ProjectPage).
//   - non-404 query error      → render children; ProjectPage owns the UX
//                                for other error shapes (unchanged).
//
// ProjectPage's own 404-bounce effect never fires for unloaded-but-existing
// projects because ProjectPage only mounts once the query has succeeded.

import { useEffect, useRef } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { components } from "../api/types";
import { useProject } from "../hooks/useProject";
import { toast } from "../lib/toast";

type ListProjectsResponse = components["schemas"]["ListProjectsResponse"];

/** Resolve project_root from the disk scan, then POST /api/projects/load. */
async function autoLoadProject(projectId: string): Promise<void> {
  const listRes = await fetch("/api/projects");
  if (!listRes.ok) throw new Error(`GET /api/projects failed: ${listRes.status}`);
  const list = (await listRes.json()) as ListProjectsResponse;
  const match = list.projects.find((p) => p.project_id === projectId);
  if (!match) throw new Error(`project not found on disk: ${projectId}`);

  const res = await fetch("/api/projects/load", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_root: match.project_root, initial_page_index: 0 }),
  });
  if (!res.ok) throw new Error(`POST /api/projects/load failed: ${res.status}`);
}

export function ProjectRouteGate({ children }: { children: React.ReactNode }) {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const projectQ = useProject(projectId);

  const status = (projectQ.error as { status?: number } | null)?.status;
  const notFound = projectQ.isError && status === 404;

  // One auto-load attempt per projectId (per mount) — prevents a load loop
  // when the server keeps answering 404 after a "successful" load.
  const attemptedRef = useRef<string | null>(null);

  const loadMutation = useMutation({
    mutationFn: (id: string) => autoLoadProject(id),
    onSuccess: async () => {
      // Refetch the shared project query; only bounce if it STILL 404s
      // (pathological — load succeeded but the project query disagrees).
      const result = await projectQ.refetch();
      if (result.error) {
        bounceHome();
        return;
      }
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      void queryClient.invalidateQueries({ queryKey: ["session-state"] });
    },
    onError: () => {
      bounceHome();
    },
  });

  function bounceHome() {
    toast.warn("Project not found — returning to project list.");
    void navigate("/", { replace: true, state: { skipSessionRedirect: true } });
  }

  useEffect(() => {
    if (!notFound || !projectId) return;
    if (attemptedRef.current === projectId) return;
    attemptedRef.current = projectId;
    loadMutation.mutate(projectId);
    // loadMutation.mutate is stable; including the mutation object would
    // re-fire the effect on every state change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [notFound, projectId]);

  if (projectQ.isSuccess) return <>{children}</>;

  // Non-404 errors: ProjectPage owns the error UX (unchanged behavior).
  if (projectQ.isError && !notFound) return <>{children}</>;

  // Initial query load, 404-with-autoload-in-flight, or post-load refetch.
  return (
    <div
      data-testid="project-autoload-overlay"
      className="flex h-full items-center justify-center text-ink-3 text-sm"
    >
      Loading project…
    </div>
  );
}

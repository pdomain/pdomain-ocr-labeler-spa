// RootPage.tsx — route element for "/".
// Issue #84 (EmptyProjectState) + Issue #274 (RootPage + session-state fetch) + Slice 27.
// Spec: docs/specs/2026-05-12-root-page-design.md + 2026-05-15-hifi-redesign-plan.md Slice 27
//
// On mount: calls GET /api/session-state.
// - If last_project_path is set  → navigate (replace) to project+page URL.
// - If null / error / loading    → render project list with HeaderBar + open-folder button.
// - In-flight loading            → render blank <div /> (HeaderBar stays above).

import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import type { components } from "../api/types";
import { Button } from "../components/ui/button";
import { StatusPip } from "../components/ui/StatusPip";
import { dialogStore } from "../stores/dialog-store";

type SessionStateResponse = components["schemas"]["SessionStateResponse"];
type ListProjectsResponse = components["schemas"]["ListProjectsResponse"];
type ProjectKey = components["schemas"]["ProjectKey"];

const API_BASE = typeof window !== "undefined" ? window.location.origin : "http://localhost:8000";

async function fetchSessionState(): Promise<SessionStateResponse> {
  const res = await fetch(`${API_BASE}/api/session-state`);
  if (!res.ok) throw new Error(`GET /api/session-state failed: ${res.status}`);
  return res.json() as Promise<SessionStateResponse>;
}

async function fetchProjects(): Promise<ListProjectsResponse> {
  const res = await fetch(`${API_BASE}/api/projects`);
  if (!res.ok) throw new Error(`GET /api/projects failed: ${res.status}`);
  return res.json() as Promise<ListProjectsResponse>;
}

/** Derive the project ID from an absolute project-directory path.
 *
 * Matches how AppState.discover_projects registers project IDs:
 * the basename of the directory path.
 *
 * e.g. "/data/my-project" → "my-project"
 */
function deriveProjectId(projectPath: string): string {
  return projectPath.split("/").filter(Boolean).pop() ?? projectPath;
}

// --- EmptyProjectState ---

/** Centred placeholder shown when no project is loaded.
 *
 * Spec: docs/specs/2026-05-12-root-page-design.md §EmptyProjectState
 * testid: "empty-project-state" (driver-contract invariant — do not rename).
 * Issue: #84
 */
export function EmptyProjectState() {
  return (
    <div
      data-testid="empty-project-state"
      className="flex flex-col items-center justify-center h-full text-gray-500 text-sm"
    >
      <p>No project loaded. Select a project from the dropdown above to get started.</p>
    </div>
  );
}

// --- ProjectListView ---

/** Project card component.
 *
 * Spec: Slice 27 — project cards with aggregate StatusPip.
 */
function ProjectCard({ project }: { project: ProjectKey }) {
  const navigate = useNavigate();

  const handleClick = () => {
    navigate(`/projects/${project.project_id}/pages/pageno/1`);
  };

  return (
    <button
      onClick={handleClick}
      className="flex flex-col gap-2 p-4 rounded-lg bg-surface border border-border-1 hover:bg-raised transition-colors text-left"
      data-testid={`project-card-${project.project_id}`}
    >
      <div className="font-semibold text-ink-1">{project.label || project.project_id}</div>
      <div className="text-xs text-ink-3">{project.project_root}</div>
      {/* Placeholder for aggregate StatusPip — future phase */}
      <div className="flex gap-1 pt-2">
        <StatusPip status="exact" label="82%" />
      </div>
    </button>
  );
}

/** Project list view shown when no session project is selected.
 *
 * Spec: Slice 27 — project cards with open-folder button.
 * Note: HeaderBar is rendered by App.tsx; this component handles only the content area.
 */
function ProjectListView({ projects }: { projects: ProjectKey[] }) {
  const handleOpenFolder = () => {
    dialogStore.open("sourceFolder");
  };

  return (
    <div className="flex flex-col h-full bg-page">
      <div className="flex-1 overflow-auto p-6">
        <div className="max-w-4xl mx-auto">
          {/* Header section */}
          <div className="mb-8">
            <h1 className="text-heading font-semibold text-ink-1 mb-2">Projects</h1>
            <p className="text-body text-ink-2">Select a project to start labeling</p>
          </div>

          {/* Projects grid */}
          {projects.length > 0 ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-6">
              {projects.map((project) => (
                <ProjectCard key={project.project_id} project={project} />
              ))}
            </div>
          ) : (
            <div className="text-center py-12">
              <p className="text-body text-ink-3 mb-4">No projects found</p>
            </div>
          )}

          {/* Open folder button */}
          <div className="mt-8">
            <Button variant="primary" onClick={handleOpenFolder}>
              Open source folder
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

// --- RootPage ---

/** Route element for "/".
 *
 * Fetches session state on mount. Redirects (replace mode) to the last-viewed
 * page if a prior session exists. Falls back to ProjectListView (Slice 27) otherwise.
 * Loading state renders a blank content area.
 *
 * Spec: docs/specs/2026-05-12-root-page-design.md + Slice 27
 * Issue: #274
 */
export default function RootPage() {
  const navigate = useNavigate();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["session-state"],
    queryFn: fetchSessionState,
    retry: false,
  });

  const { data: projects } = useQuery({
    queryKey: ["projects"],
    queryFn: fetchProjects,
    retry: false,
  });

  useEffect(() => {
    if (!data?.last_project_path) return;
    const projectId = deriveProjectId(data.last_project_path);
    const pageNo = (data.last_page_index ?? 0) + 1;
    navigate(`/projects/${projectId}/pages/pageno/${pageNo}`, { replace: true });
  }, [data, navigate]);

  // In-flight: blank content area (no spinner — sub-100ms local fetch).
  if (isLoading) return <div />;

  // Error or null last_project_path: show project list (Slice 27).
  if (isError || !data?.last_project_path) {
    return <ProjectListView projects={projects?.projects ?? []} />;
  }

  // Project found: redirect is pending (useEffect fires next tick).
  // Render blank while the navigation resolves.
  return <div />;
}

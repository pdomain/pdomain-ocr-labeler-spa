// RootPage.tsx — route element for "/".
// Issue #84 (EmptyProjectState) + Issue #274 (RootPage + session-state fetch).
// Spec: docs/specs/2026-05-12-root-page-design.md
//
// On mount: calls GET /api/session-state.
// - If last_project_path is set  → navigate (replace) to project+page URL.
// - If null / error / loading    → render EmptyProjectState.
// - In-flight loading            → render blank <div /> (HeaderBar stays above).

import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import type { components } from "../api/types";

type SessionStateResponse = components["schemas"]["SessionStateResponse"];

const API_BASE = typeof window !== "undefined" ? window.location.origin : "http://localhost:8000";

async function fetchSessionState(): Promise<SessionStateResponse> {
  const res = await fetch(`${API_BASE}/api/session-state`);
  if (!res.ok) throw new Error(`GET /api/session-state failed: ${res.status}`);
  return res.json() as Promise<SessionStateResponse>;
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

// --- RootPage ---

/** Route element for "/".
 *
 * Fetches session state on mount. Redirects (replace mode) to the last-viewed
 * page if a prior session exists. Falls back to EmptyProjectState otherwise.
 * Loading state renders a blank content area (HeaderBar stays visible above).
 *
 * Spec: docs/specs/2026-05-12-root-page-design.md
 * Issue: #274
 */
export default function RootPage() {
  const navigate = useNavigate();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["session-state"],
    queryFn: fetchSessionState,
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

  // Error or null last_project_path: show empty state.
  if (isError || !data?.last_project_path) {
    return <EmptyProjectState />;
  }

  // Project found: redirect is pending (useEffect fires next tick).
  // Render blank while the navigation resolves.
  return <div />;
}

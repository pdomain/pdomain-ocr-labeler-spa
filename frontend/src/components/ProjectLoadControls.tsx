// ProjectLoadControls.tsx — project selector for the header.
// Issue #272 (initial), #326 (hi-fi redesign: breadcrumb + icon when project known).
// Spec: docs/specs/2026-05-12-header-bar-design.md, docs/architecture/13-driver-contract.md §HeaderBar.
//
// Two display modes:
//   - "breadcrumb" (projectName prop set): show project label + compact FolderOpen icon.
//     Used on project routes where the current project is known.
//   - "select" (no projectName): show the standard project dropdown + LOAD button.
//     Used on the root route where no project is loaded yet.
//
// Driver-contract testids preserved in both modes:
//   project-select       — always in DOM (hidden in breadcrumb mode)
//   load-project-button  — always in DOM (hidden in breadcrumb mode)
//   source-folder-button — always visible
//   change-project-button — breadcrumb mode only (triggers dialogStore.open("sourceFolder"))

import { useState, useEffect } from "react";
import { FolderOpen } from "@/icons/local-shims";
import type { components } from "../api/types";
import { dialogStore } from "../stores/dialog-store";

type ProjectKey = components["schemas"]["ProjectKey"];
type ListProjectsResponse = components["schemas"]["ListProjectsResponse"];

const API_BASE = typeof window !== "undefined" ? window.location.origin : "http://localhost:8000";

async function fetchProjects(): Promise<ListProjectsResponse> {
  const res = await fetch(`${API_BASE}/api/projects`);
  if (!res.ok) throw new Error(`GET /api/projects failed: ${res.status}`);
  return res.json() as Promise<ListProjectsResponse>;
}

async function postLoadProject(projectRoot: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/projects/load`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_root: projectRoot, initial_page_index: 0 }),
  });
  if (!res.ok) throw new Error(`POST /api/projects/load failed: ${res.status}`);
}

export interface ProjectLoadControlsProps {
  /**
   * When provided, the component renders in "breadcrumb" mode:
   * project name + compact icon button instead of the full select+LOAD.
   * The driver-contract select/load testids remain in the DOM (hidden) for
   * backward compatibility with automated tooling.
   */
  projectName?: string;
}

export default function ProjectLoadControls({ projectName }: ProjectLoadControlsProps = {}) {
  const [projects, setProjects] = useState<ProjectKey[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [isMutating, setIsMutating] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchProjects()
      .then((data) => {
        if (cancelled) return;
        setProjects(data.projects);
        if (data.selected) {
          setSelectedId(data.selected);
        }
      })
      .catch(() => {
        // ignore — empty list is the fallback state
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleLoad = () => {
    const project = projects.find((p) => p.project_id === selectedId);
    if (!project || isMutating) return;
    setIsMutating(true);
    postLoadProject(project.project_root)
      .catch(() => {
        // surface error in a future milestone; for now just reset mutating state
      })
      .finally(() => {
        setIsMutating(false);
      });
  };

  const loadDisabled = !selectedId || isMutating;

  const isBreadcrumbMode = !!projectName;

  return (
    <div data-testid="project-load-controls" className="flex items-center gap-2 min-w-0">
      {/* ── Breadcrumb mode (project route): name + change icon ─────────────── */}
      {isBreadcrumbMode && (
        <>
          <span
            data-testid="project-breadcrumb"
            className="flex items-center gap-1 text-body text-ink-2 truncate max-w-[220px] select-none"
            title={projectName}
          >
            <span className="text-ink-3 shrink-0">Projects</span>
            <span className="text-ink-3 shrink-0" aria-hidden="true">
              /
            </span>
            <span className="text-ink-1 font-medium truncate">{projectName}</span>
          </span>
          <button
            type="button"
            data-testid="change-project-button"
            aria-label="Change project"
            onClick={() => {
              dialogStore.open("sourceFolder");
            }}
            className="flex items-center justify-center w-6 h-6 rounded text-ink-3 hover:text-ink-1 hover:bg-bg-raised transition-colors"
          >
            <FolderOpen size={13} aria-hidden />
          </button>
        </>
      )}

      {/* ── Select mode (root route): dropdown + LOAD ─────────────────────── */}
      {/* Always in DOM for driver-contract testids; hidden in breadcrumb mode. */}
      <select
        data-testid="project-select"
        value={selectedId}
        onChange={(e) => {
          setSelectedId(e.target.value);
        }}
        className={isBreadcrumbMode ? "sr-only" : "border rounded px-2 py-1 text-sm"}
        aria-hidden={isBreadcrumbMode}
        tabIndex={isBreadcrumbMode ? -1 : undefined}
      >
        {projects.length === 0 ? (
          <option value="" disabled>
            No projects found
          </option>
        ) : (
          <>
            <option value="" disabled>
              Select a project
            </option>
            {projects.map((p) => (
              <option key={p.project_id} value={p.project_id}>
                {p.label}
              </option>
            ))}
          </>
        )}
      </select>

      <button
        data-testid="load-project-button"
        disabled={loadDisabled}
        onClick={handleLoad}
        className={
          isBreadcrumbMode ? "sr-only" : "px-3 py-1 text-sm border rounded disabled:opacity-50"
        }
        aria-hidden={isBreadcrumbMode}
        tabIndex={isBreadcrumbMode ? -1 : undefined}
      >
        LOAD
      </button>

      <button
        type="button"
        data-testid="source-folder-button"
        aria-label="Browse source folder"
        onClick={() => {
          dialogStore.open("sourceFolder");
        }}
        className={isBreadcrumbMode ? "sr-only" : "px-2 py-1 text-sm border rounded"}
        aria-hidden={isBreadcrumbMode}
        tabIndex={isBreadcrumbMode ? -1 : undefined}
      >
        {/* FolderIcon placeholder */}
        &#128193;
      </button>
      {/*
       * Note: `ocr-config-trigger-button` moved to HeaderBar (spec 22 §6,
       * issue #309). All dialog-trigger buttons live on the HeaderBar now.
       */}
    </div>
  );
}

// ProjectLoadControls.tsx — project dropdown + LOAD button + icon triggers.
// Issue #272. Spec: docs/specs/2026-05-12-header-bar-design.md.
//
// No zustand/react-query yet (not in package.json). Uses useState + useEffect
// with the raw ApiClient and reports loading/mutation state via local state.
// When those libraries are added in a later milestone this component can be
// upgraded to useQuery / useProjectStore.

import { useState, useEffect } from "react";
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

export default function ProjectLoadControls() {
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

  return (
    <div data-testid="project-load-controls" className="flex items-center gap-2">
      <select
        data-testid="project-select"
        value={selectedId}
        onChange={(e) => setSelectedId(e.target.value)}
        className="border rounded px-2 py-1 text-sm"
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
        className="px-3 py-1 text-sm border rounded disabled:opacity-50"
      >
        LOAD
      </button>

      <button
        type="button"
        data-testid="source-folder-button"
        aria-label="Browse source folder"
        onClick={() => dialogStore.open("sourceFolder")}
        className="px-2 py-1 text-sm border rounded"
      >
        {/* FolderIcon placeholder — icon library added in a later milestone */}
        &#128193;
      </button>
      {/*
       * Note: `ocr-config-trigger-button` moved to HeaderBar (spec 22 §6,
       * issue #309). All dialog-trigger buttons live on the HeaderBar now.
       */}
    </div>
  );
}

// RootPage.tsx — route element for "/".
// Issue #84 (EmptyProjectState) + Issue #274 (RootPage + session-state fetch) + Slice 27.
// Issue #327 (auto-resume after server restart: POST /api/projects/load before navigate).
// P5.h redesign: project cards with thumbnail + progress + search + filter chips + hero band.
// Spec: docs/specs/2026-05-12-root-page-design.md + 2026-05-15-hifi-redesign-plan.md Slice 27 + P5.h
// Gaps closed: 59 (project cards redesign), 60 (search field + filter chips + hero band)
//
// On mount: calls GET /api/session-state.
// - If last_project_path is set AND project exists in disk list:
//     → POST /api/projects/load to hydrate memory, then navigate to project+page URL.
//     → If load POST fails → fall through to project list (graceful degradation).
// - If null / error / loading    → render project list with hero band + open-folder button.
// - In-flight loading            → render blank <div /> (HeaderBar stays above).

import { useEffect, useRef, useState, useMemo } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Search, ChevronDown } from "@pdomain/pdomain-ui/icons";
import { FolderOpen } from "@/icons/local-shims";
import type { components } from "../api/types";
import { Button } from "../components/ui/button";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { toast } from "../lib/toast";
import { dialogStore, useDialogStore } from "../stores/dialog-store";

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

async function postLoadProject(projectPath: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/projects/load`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_root: projectPath, initial_page_index: 0 }),
  });
  if (!res.ok) throw new Error(`POST /api/projects/load failed: ${res.status}`);
}

/** DELETE /api/projects/{id} — permanently removes the project (P4.2). */
async function deleteProject(projectId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/projects/${encodeURIComponent(projectId)}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(`DELETE /api/projects/${projectId} failed: ${res.status}`);
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

// ─── Filter chip types ────────────────────────────────────────────────────────

type ProjectFilter = "all" | "active" | "complete" | "archived";

const FILTER_LABELS: Record<ProjectFilter, string> = {
  all: "All",
  active: "Active",
  complete: "Complete",
  archived: "Archived",
};

// ─── EmptyProjectState (kept for backward compat) ─────────────────────────────

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
      className="flex flex-col items-center justify-center h-full text-ink-3 text-sm"
    >
      <p>No project loaded. Select a project from the dropdown above to get started.</p>
    </div>
  );
}

// ─── Hero band ────────────────────────────────────────────────────────────────

/** Branded header band at the very top of the root page. */
function HeroBand() {
  return (
    <div
      data-testid="root-hero-band"
      className="bg-bg-surface border-b border-border-1 px-6 py-4 flex items-center gap-4"
    >
      {/* Logo mark — orange "O" badge (Gap 2 preview) */}
      <div className="relative flex-shrink-0">
        <div className="w-10 h-10 rounded-lg bg-accent flex items-center justify-center">
          <span className="text-accent-ink font-bold text-xl leading-none select-none">O</span>
        </div>
        {/* Small orange badge dot */}
        <span className="absolute -top-1 -right-1 w-3 h-3 rounded-full bg-accent border-2 border-bg-surface" />
      </div>

      <div className="flex-1 min-w-0">
        <h1
          className="text-[15px] font-bold text-ink-1 leading-tight"
          data-testid="root-hero-title"
        >
          OCR Labeler
        </h1>
        <p className="text-[11px] text-ink-3 mt-0.5">
          Review and correct OCR output for book digitisation
        </p>
      </div>
    </div>
  );
}

// ─── Progress bar ─────────────────────────────────────────────────────────────

/** Simple horizontal progress bar using accent token. */
function ProgressBar({ percent }: { percent: number }) {
  const clamped = Math.min(100, Math.max(0, percent));
  return (
    <div className="h-1 w-full bg-bg-raised rounded-full overflow-hidden">
      <div
        className="h-full bg-accent transition-all duration-300"
        style={{ width: `${clamped}%` }}
        aria-valuenow={clamped}
        aria-valuemin={0}
        aria-valuemax={100}
        role="progressbar"
      />
    </div>
  );
}

// ─── Project card ─────────────────────────────────────────────────────────────

/** Project card with thumbnail + page count + progress bar + action menu. */
function ProjectCard({ project }: { project: ProjectKey }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [menuOpen, setMenuOpen] = useState(false);

  const openMutation = useMutation({
    mutationFn: () => postLoadProject(String(project.project_root)),
    onSuccess: () => {
      // Navigate only when the load succeeded — do not navigate on error.
      void navigate(`/projects/${encodeURIComponent(project.project_id)}/pages/pageno/1`);
    },
    // onError: mutation.isError state is sufficient — no extra action needed here.
  });

  const handleOpen = () => {
    openMutation.mutate();
  };

  // P4.2 (parity F13 / C14): per-card Delete — confirm → DELETE → refresh.
  const deleteMutation = useMutation({
    mutationFn: () => deleteProject(project.project_id),
    onSuccess: () => {
      toast.success(`Project "${project.label || project.project_id}" deleted`);
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      void queryClient.invalidateQueries({ queryKey: ["session-state"] });
    },
    onError: (error: Error) => {
      toast.error(`Failed to delete project: ${error.message}`);
    },
  });

  const handleDelete = () => {
    setMenuOpen(false);
    dialogStore.openConfirm({
      title: "Delete project?",
      body:
        `This will permanently delete "${project.label || project.project_id}" from disk — ` +
        "source images, OCR data, and labeled work. This action cannot be undone.",
      onConfirm: () => {
        deleteMutation.mutate();
      },
    });
  };

  // Placeholder values — these will be populated when the backend exposes them.
  // For now we display meaningful placeholders so the card structure is visible.
  const pageCount: number | null = null; // not yet in ProjectKey API
  const progressPercent: number | null = null; // not yet in ProjectKey API

  const isLoadError = openMutation.isError;

  return (
    <div
      data-testid={`project-card-${project.project_id}`}
      className={[
        "flex flex-col rounded-lg bg-bg-surface border overflow-hidden transition-colors",
        isLoadError ? "border-red-500" : "border-border-1 hover:border-border-2",
      ].join(" ")}
    >
      {/* Thumbnail area — placeholder until API exposes first-page image */}
      <div
        data-testid={`project-card-thumbnail-${project.project_id}`}
        className="h-24 bg-bg-raised flex items-center justify-center border-b border-border-1 flex-shrink-0"
        aria-label={`Thumbnail for ${project.label || project.project_id}`}
      >
        <svg viewBox="0 0 48 48" className="w-10 h-10 text-ink-4" fill="none">
          <rect x="8" y="6" width="32" height="38" rx="2" stroke="currentColor" strokeWidth="1.5" />
          <line x1="14" y1="16" x2="34" y2="16" stroke="currentColor" strokeWidth="1.5" />
          <line x1="14" y1="22" x2="34" y2="22" stroke="currentColor" strokeWidth="1.5" />
          <line x1="14" y1="28" x2="28" y2="28" stroke="currentColor" strokeWidth="1.5" />
        </svg>
      </div>

      {/* Card body */}
      <div className="flex flex-col gap-2 p-3">
        {/* Project name */}
        <div
          className="font-semibold text-[13px] text-ink-1 leading-tight truncate"
          title={project.label || project.project_id}
        >
          {project.label || project.project_id}
        </div>

        {/* Page count */}
        <div className="text-[11px] text-ink-3">
          {pageCount !== null ? `${pageCount} pages` : "— pages"}
        </div>

        {/* Progress bar */}
        <div className="space-y-1">
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-ink-4">Validation</span>
            <span className="text-[10px] text-ink-3">
              {progressPercent !== null ? `${progressPercent}%` : "—%"}
            </span>
          </div>
          <ProgressBar percent={progressPercent ?? 0} />
        </div>

        {/* Source path */}
        <div className="text-[10px] text-ink-4 truncate font-mono" title={project.project_root}>
          {project.project_root}
        </div>

        {/* Error indicator — shown when POST /api/projects/load fails (F-043) */}
        {isLoadError && (
          <div
            data-testid={`project-card-error-${project.project_id}`}
            role="alert"
            className="text-[11px] text-red-600 bg-red-50 border border-red-200 rounded px-2 py-1"
          >
            Failed to open project. Please try again.
          </div>
        )}

        {/* Action row */}
        <div className="flex items-center gap-1 mt-1">
          <button
            type="button"
            data-testid={`project-card-open-${project.project_id}`}
            onClick={handleOpen}
            disabled={openMutation.isPending || isLoadError}
            aria-disabled={isLoadError ? "true" : undefined}
            className="flex-1 text-[11px] font-medium px-2 py-1.5 rounded bg-accent text-accent-ink hover:opacity-90 transition-opacity disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {openMutation.isPending ? "Loading…" : "Open"}
          </button>

          {/* Action menu ▾ */}
          <div className="relative">
            <button
              type="button"
              data-testid={`project-card-menu-${project.project_id}`}
              onClick={() => {
                setMenuOpen((o) => !o);
              }}
              aria-label="More actions"
              className="p-1.5 rounded border border-border-2 text-ink-3 hover:text-ink-1 hover:border-border-1 transition-colors"
            >
              <ChevronDown size={12} />
            </button>
            {menuOpen && (
              <div className="absolute right-0 top-full mt-1 w-32 bg-bg-raised border border-border-2 rounded shadow-lg z-10">
                {/* P4.2: Delete is wired (confirm → DELETE → list refresh).
                 * The former "Archive" stub was REMOVED — there is no archive
                 * endpoint or project-status field in the API; re-add it once
                 * the semantics are specced (needs-spec, parity C14). */}
                <button
                  type="button"
                  data-testid={`project-card-delete-${project.project_id}`}
                  onClick={handleDelete}
                  disabled={deleteMutation.isPending}
                  className="w-full text-left text-[11px] text-ink-2 px-3 py-1.5 hover:bg-bg-sunk transition-colors disabled:opacity-60"
                >
                  {deleteMutation.isPending ? "Deleting…" : "Delete"}
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── ProjectListView ──────────────────────────────────────────────────────────

/** Project list view — hero band + search + filter chips + card grid. */
function ProjectListView({ projects }: { projects: ProjectKey[] }) {
  const [searchQuery, setSearchQuery] = useState("");
  const [activeFilter, setActiveFilter] = useState<ProjectFilter>("all");
  // P4.2: confirm dialog for destructive card actions (delete). Same
  // dialogStore-driven pattern as ProjectPage — the store holds
  // title/body/onConfirm; this view renders the single dialog instance.
  const confirmState = useDialogStore((s) => s.confirm);

  const handleOpenFolder = () => {
    dialogStore.open("sourceFolder");
  };

  // Filter by search query (case-insensitive match on label + project_id).
  const filteredProjects = useMemo(() => {
    let list = projects;
    // Text search
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      list = list.filter(
        (p) =>
          (p.label || "").toLowerCase().includes(q) ||
          p.project_id.toLowerCase().includes(q) ||
          p.project_root.toLowerCase().includes(q),
      );
    }
    // Status filter — "active" / "complete" / "archived" are metadata not yet exposed
    // by the API, so all non-"all" filters show all projects for now.
    // When the API gains a `status` field, add filtering here.
    return list;
  }, [projects, searchQuery, activeFilter]);

  return (
    <div className="flex flex-col h-full bg-bg-page">
      {/* Hero band */}
      <HeroBand />

      {/* Search + filter bar */}
      <div
        data-testid="root-search-filter-bar"
        className="flex items-center gap-3 px-6 py-3 bg-bg-surface border-b border-border-1 flex-wrap"
      >
        {/* Search field */}
        <div className="relative flex-1 min-w-[200px] max-w-[360px]">
          <Search
            size={14}
            className="absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-4 pointer-events-none"
          />
          <input
            type="search"
            data-testid="root-search-input"
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
            }}
            placeholder="Search projects…"
            aria-label="Search projects"
            className="w-full pl-8 pr-3 py-1.5 text-[12px] bg-bg-sunk border border-border-2 rounded focus:outline-none focus:border-accent text-ink-1 placeholder:text-ink-4 transition-colors"
          />
        </div>

        {/* Filter chips */}
        <div
          data-testid="root-filter-chips"
          className="flex items-center gap-1 flex-wrap"
          role="group"
          aria-label="Filter projects"
        >
          {(Object.keys(FILTER_LABELS) as ProjectFilter[]).map((f) => (
            <button
              key={f}
              type="button"
              data-testid={`root-filter-chip-${f}`}
              data-active={activeFilter === f ? "true" : undefined}
              onClick={() => {
                setActiveFilter(f);
              }}
              style={
                activeFilter === f
                  ? { background: "color-mix(in srgb, var(--accent) 10%, transparent)" }
                  : undefined
              }
              className={[
                "text-[11px] px-2.5 py-1 rounded-full border transition-colors",
                activeFilter === f
                  ? "border-accent text-ink-1 font-medium"
                  : "border-border-2 bg-bg-raised text-ink-3 hover:border-border-1 hover:text-ink-2",
              ].join(" ")}
            >
              {FILTER_LABELS[f]}
            </button>
          ))}
        </div>
      </div>

      {/* Content area */}
      <div className="flex-1 overflow-auto p-6">
        <div className="max-w-5xl mx-auto">
          {/* Results count */}
          <div className="mb-4 flex items-center justify-between">
            <span className="text-[11px] text-ink-3">
              {filteredProjects.length} project
              {filteredProjects.length !== 1 ? "s" : ""}
            </span>
            <Button variant="primary" size="sm" onClick={handleOpenFolder}>
              <FolderOpen size={13} className="mr-1.5" />
              Open source folder
            </Button>
          </div>

          {/* Projects grid */}
          {filteredProjects.length > 0 ? (
            <div
              data-testid="root-projects-grid"
              className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4"
            >
              {filteredProjects.map((project) => (
                <ProjectCard key={project.project_id} project={project} />
              ))}
            </div>
          ) : searchQuery ? (
            <div
              data-testid="root-empty-search"
              className="text-center py-16 text-ink-3 text-[13px]"
            >
              No projects match &ldquo;{searchQuery}&rdquo;
            </div>
          ) : (
            <div
              data-testid="root-empty-projects"
              className="text-center py-16 text-ink-3 text-[13px]"
            >
              No projects found. Open a source folder to get started.
            </div>
          )}
        </div>
      </div>

      {/* P4.2: ConfirmDialog — opened from ProjectCard delete via dialogStore. */}
      <ConfirmDialog
        open={confirmState.open}
        message={confirmState.body ?? ""}
        title={confirmState.title}
        confirmLabel="Delete"
        onConfirm={() => {
          confirmState.onConfirm?.();
          dialogStore.close("confirm");
        }}
        onCancel={() => {
          dialogStore.close("confirm");
        }}
      />
    </div>
  );
}

// ─── RootPage ────────────────────────────────────────────────────────────────

/** Route element for "/".
 *
 * Fetches session state on mount. When the last project exists on disk, fires
 * POST /api/projects/load to hydrate it in memory (handles the server-restart
 * case where the project is on disk but not in memory), then redirects (replace
 * mode) to the last-viewed page.
 *
 * Falls back to ProjectListView (P5.h) when:
 *   - No prior session / no saved project path.
 *   - Project no longer exists on disk.
 *   - The load POST fails.
 *   - skipSessionRedirect flag is set (set by 404-redirect logic).
 *
 * Loading state renders a blank content area.
 *
 * Spec: docs/specs/2026-05-12-root-page-design.md + Slice 27 + P5.h
 * Issue: #274, #327
 */
export default function RootPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const skipSessionRedirect = !!(location.state as { skipSessionRedirect?: boolean } | null)
    ?.skipSessionRedirect;

  const { data, isLoading, isError } = useQuery({
    queryKey: ["session-state"],
    queryFn: fetchSessionState,
    retry: false,
  });

  const { data: projects, isLoading: isProjectsLoading } = useQuery({
    queryKey: ["projects"],
    queryFn: fetchProjects,
    retry: false,
  });

  const derivedProjectId = data?.last_project_path ? deriveProjectId(data.last_project_path) : null;
  const lastProjectPath = data?.last_project_path ?? null;

  const projectExists =
    derivedProjectId !== null &&
    (projects?.projects ?? []).some((p) => p.project_id === derivedProjectId);

  // #327: POST /api/projects/load before navigating so the project is hydrated
  // in server memory even after a restart. On success → navigate; on error →
  // fall through to project list (onError sets loadFailed state).
  //
  // Use a ref to track fired/failed state so the effect fires exactly once per
  // mount (not every time loadMutation state changes).
  const loadStateRef = useRef<"idle" | "pending" | "success" | "failed">("idle");

  const loadMutation = useMutation({
    mutationFn: (projectPath: string) => postLoadProject(projectPath),
    onSuccess: () => {
      loadStateRef.current = "success";
      if (!derivedProjectId || !data) return;
      const pageNo = (data.last_page_index ?? 0) + 1;
      void navigate(
        `/projects/${encodeURIComponent(derivedProjectId)}/pages/pageno/${encodeURIComponent(String(pageNo))}`,
        { replace: true },
      );
    },
    onError: () => {
      loadStateRef.current = "failed";
    },
  });

  useEffect(() => {
    if (!projectExists || !derivedProjectId || !lastProjectPath || skipSessionRedirect) return;
    if (loadStateRef.current !== "idle") return;
    loadStateRef.current = "pending";
    loadMutation.mutate(lastProjectPath);
    // Intentionally not including loadMutation in deps — mutate is stable.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectExists, derivedProjectId, lastProjectPath, skipSessionRedirect]);

  const loadFailed = loadStateRef.current === "failed";

  // In-flight: blank content area while either query is loading or load POST is pending.
  if (
    isLoading ||
    isProjectsLoading ||
    (projectExists && !skipSessionRedirect && loadMutation.isPending)
  )
    return <div />;

  // Session error, no saved path, project gone, skipRedirect, or load failed: show project list.
  if (isError || !data?.last_project_path || !projectExists || skipSessionRedirect || loadFailed) {
    return <ProjectListView projects={projects?.projects ?? []} />;
  }

  // Load mutation succeeded: navigation is pending.
  return <div />;
}

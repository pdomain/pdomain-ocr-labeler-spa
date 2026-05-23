// App.tsx — SPA root: router, QueryClient provider, and route table.
// Spec: docs/specs/2026-05-12-frontend-shell-design.md §Routing
// Issue #240
// Phase 2.4: replaced local AppShell wrapper with pd-ui AppShell (issue #262).
//
// Route table (from routes.ts):
//   /                                              → RootPage (session-state redirect or EmptyProjectState)
//   /projects/:projectId                           → redirect to pageno/1
//   /projects/:projectId/pages/pageno/:pageNo      → ProjectPage (main labeling surface)
//   /projects/:projectId/pages/index/:idx0         → redirect to pageno equivalent
//   *                                              → 404 fallback (redirect to /)
//
// GAP-1: GET /api/ui-prefs backend endpoint not yet implemented — uiPrefsConfig
//        load() returns localStorage-seeded defaults; persist callbacks are no-ops.
//        Full wiring deferred to Phase 2.5 (reactive stores migration).
// GAP-2: POST /api/ui-prefs backend endpoint not yet implemented — same as GAP-1.
// GAP-3: GET /api/suite/installed + POST /api/suite/launch backend endpoints not
//        yet implemented. SuiteSiblingsProvider fetchInstalled returns [] (no-op);
//        postLaunch returns requires-host-config. Real wiring blocked on pd-ocr-ops
//        mounting /api/suite/* routes in the FastAPI app.

import { BrowserRouter, Routes, Route, Navigate, useParams, useMatch } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "sonner";

import { Suspense, lazy } from "react";
import {
  AppShell,
  SuiteSiblingsProvider,
  type UIPrefsConfig,
  type InstalledApp,
  type LaunchResult,
} from "@concavetrillion/pd-ui/shell";
import HeaderBar from "./components/HeaderBar";
import type { PageMetrics } from "./components/HeaderBar";
import ProjectNavigationControls from "./components/ProjectNavigationControls";
import { PageActionsCompact } from "./components/PageActionsCompact";
import RootPage from "./pages/RootPage";
import ProjectPage from "./pages/ProjectPage";
import { ROUTES } from "./lib/routes";
import { useThemePreference } from "./stores/ui-prefs";
import { useProject } from "./hooks/useProject";
import { usePage } from "./hooks/usePage";

// Lazy-load the perf-bench page so the heavy react-konva module graph
// (and its Node-canvas dependency in jsdom test environments) is only
// pulled in when /__perf-test is actually visited. ProjectPage also
// transitively imports react-konva (via PageImageCanvas) but is NOT
// lazy-loaded — splitting the chunk caused a Suspense fallback to be
// visible during E2E navigation, which break tests that look for
// `[data-testid="project-page"]` immediately after page.goto.
// App.test.tsx mocks react-konva (module-level vi.mock) instead of
// relying on lazy-loading to keep canvas out of jsdom.
const PerfTestPage = lazy(() => import("./pages/PerfTestPage"));
import { useNotificationStream } from "./hooks/useNotificationStream";
import { OCRConfigModal } from "./components/OCRConfigModal";
import { ExportDialog } from "./components/ExportDialog";
import { HotkeyHelpModal } from "./components/HotkeyHelpModal";
import { SourceFolderDialog } from "./components/SourceFolderDialog";
import { dialogStore, useDialogStore } from "./stores/dialog-store";

// One QueryClient for the app.
// staleTime: 30 000 ms — spec §Server state.
// refetchOnWindowFocus: false — avoids spurious re-fetches on tab switch.
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    },
  },
});

/** Redirect /projects/:id → /projects/:id/pages/pageno/1 */
function ProjectRootRedirect() {
  const { projectId } = useParams<{ projectId: string }>();
  return <Navigate to={`/projects/${projectId}/pages/pageno/1`} replace />;
}

/** Redirect /projects/:id/pages/index/:idx0 → pageno equivalent */
function ProjectPageIndexRedirect() {
  const { projectId, idx0 } = useParams<{ projectId: string; idx0: string }>();
  const pageNo = (parseInt(idx0 ?? "0", 10) + 1).toString();
  return <Navigate to={`/projects/${projectId}/pages/pageno/${pageNo}`} replace />;
}

/** Read projectId + 0-based pageIndex from the URL (best effort).
 *
 * Returns `null` for projectId when no project route is active — the
 * Export dialog uses this to short-circuit (it's mounted globally but
 * only meaningful inside a project route).
 */
function useRouteProjectContext(): { projectId: string | null; pageIndex: number } {
  const matchPageNo = useMatch("/projects/:projectId/pages/pageno/:pageNo");
  const matchPageIdx = useMatch("/projects/:projectId/pages/index/:idx0");
  const matchProject = useMatch("/projects/:projectId");

  const projectId =
    matchPageNo?.params.projectId ??
    matchPageIdx?.params.projectId ??
    matchProject?.params.projectId ??
    null;

  let pageIndex = 0;
  if (matchPageNo?.params.pageNo) {
    const n = parseInt(matchPageNo.params.pageNo, 10);
    pageIndex = Number.isFinite(n) && n > 0 ? n - 1 : 0;
  } else if (matchPageIdx?.params.idx0) {
    const n = parseInt(matchPageIdx.params.idx0, 10);
    pageIndex = Number.isFinite(n) && n >= 0 ? n : 0;
  }

  return { projectId, pageIndex };
}

/** Inner component so hooks (useNotificationStream) run inside providers. */
function AppInner() {
  useNotificationStream();

  // Dialog open-state slices — re-render only when these change.
  const ocrConfigOpen = useDialogStore((s) => s.ocrConfig.open);
  const exportOpen = useDialogStore((s) => s.export.open);
  const sourceFolderOpen = useDialogStore((s) => s.sourceFolder.open);
  const { projectId, pageIndex } = useRouteProjectContext();

  // IS-2: Inject nav + actions slots into HeaderBar when on a project route.
  const onProjectRoute = projectId !== null;
  const pageNo = String(pageIndex + 1);

  // P1.a: Fetch project name + page metrics for header breadcrumb + strip.
  // Both hooks are guarded via enabled:false when projectId is null/undefined.
  const projectIdOrUndef = projectId ?? undefined;
  const projectQ = useProject(projectIdOrUndef);
  const pageQ = usePage(projectIdOrUndef, pageIndex);

  // Prefer using a display name; fall back to project_id as identifier.
  // The ProjectResponse shape has no separate display-name field, so we
  // use project_id as the breadcrumb label for now.
  const headerProjectName: string | null = projectQ.data ? projectQ.data.project_id : null;

  const pageMetrics: PageMetrics | null = (() => {
    const lineMatches = pageQ.data?.line_matches ?? null;
    if (!lineMatches) return null;
    const words = lineMatches.flatMap((l) => l.word_matches);
    const total = words.length;
    if (total === 0) return null;
    const glyphsReviewedCount = words.filter((w) => w.glyph_annotations != null).length;
    return {
      total,
      exact: words.filter((w) => w.match_status === "exact").length,
      fuzzy: words.filter((w) => w.match_status === "fuzzy").length,
      mismatch: words.filter((w) => w.match_status === "mismatch").length,
      validated: words.filter((w) => w.is_validated).length,
      glyphs_reviewed: glyphsReviewedCount,
    };
  })();

  return (
    /*
     * Phase 2.4: pd-ui AppShell replaces the local layout wrapper.
     *
     * The outer div preserves data-testid="app-shell" for Playwright driver
     * contract compatibility (specs/13-driver-contract.md). pd-ui AppShell
     * does not inject its own data-testid so the wrapper is the stable anchor.
     *
     * Slot mapping vs former local layout:
     *   header   ← HeaderBar (was top-level before main)
     *   main     ← Routes block + accessible live regions
     *   children ← modal dialogs (AppShell renders children outside grid)
     *
     * rail / drawer / rightPanel are not used at the App level — they are
     * filled by StudioShell inside ProjectPage for the per-page layout.
     * StudioShell continues to manage the 5-zone canvas grid.
     *
     * launcherSlot="header": pd-ui AppShell injects LauncherSlot into the
     * header zone. The SuiteSiblingsProvider (wrapped in App()) supplies the
     * sibling list via fetchInstalled / postLaunch callbacks.
     */
    <div data-testid="app-shell" className="h-screen w-full">
      <AppShell
        appId="pd-ocr-labeler-spa"
        appDisplayName="OCR Labeler"
        appIconUrl="/static/icon.svg"
        launcherSlot="header"
        deployMode="local"
        uiPrefsConfig={UI_PREFS_CONFIG}
        header={
          <>
            <HeaderBar
              navSlot={
                onProjectRoute ? (
                  <ProjectNavigationControls projectId={projectId} pageNo={pageNo} />
                ) : undefined
              }
              actionsSlot={
                onProjectRoute ? (
                  <PageActionsCompact projectId={projectId} pageIndex={pageIndex} />
                ) : undefined
              }
              projectName={headerProjectName}
              pageMetrics={pageMetrics}
            />
            {/*
             * Accessible live regions — spec #238.
             * Placed here (inside header slot) so they are always present in
             * the DOM regardless of route. The header div is always rendered.
             */}
            <div
              id="status-announcer"
              role="status"
              aria-live="polite"
              aria-atomic="true"
              className="sr-only"
            />
            <div
              id="error-announcer"
              role="alert"
              aria-live="assertive"
              aria-atomic="true"
              className="sr-only"
            />
          </>
        }
        main={
          <main className="h-full min-h-0 overflow-hidden">
            <Routes>
              <Route path={ROUTES.ROOT} element={<RootPage />} />
              <Route path={ROUTES.PROJECT} element={<ProjectRootRedirect />} />
              <Route path={ROUTES.PROJECT_PAGE_NO} element={<ProjectPage />} />
              <Route path={ROUTES.PROJECT_PAGE_IDX} element={<ProjectPageIndexRedirect />} />
              {/* Dev/test-only Konva viewport perf-bench page (#305, spec §11).
                  Lazy-loaded so the react-konva module graph stays out of the
                  root route's bundle (and out of jsdom App.test.tsx).
                  Production-mode renders the disabled stub from PerfTestPage. */}
              <Route
                path="/__perf-test"
                element={
                  <Suspense fallback={<div data-testid="perf-test-loading" />}>
                    <PerfTestPage />
                  </Suspense>
                }
              />
              {/* Catch-all: redirect unknown routes to root */}
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </main>
        }
      >
        {/*
         * Dialogs mounted as AppShell children (spec 22 §3).
         *
         * `HotkeyHelpModal` subscribes to the dialog store itself (it also
         * listens to the `?` key globally). `OCRConfigModal` + `ExportDialog`
         * read their open-state via their `open` prop. Export dialog only
         * shows when a project is loaded (no `projectId` → skip render).
         *
         * AppShell renders children outside the grid zones so dialogs (which
         * use portals / fixed positioning) are unaffected by the layout.
         */}
        <OCRConfigModal
          open={ocrConfigOpen}
          onClose={() => {
            dialogStore.close("ocrConfig");
          }}
        />
        {projectId && (
          <ExportDialog
            open={exportOpen}
            projectId={projectId}
            currentPageIndex={pageIndex}
            onClose={() => {
              dialogStore.close("export");
            }}
          />
        )}
        <HotkeyHelpModal />
        <SourceFolderDialog
          open={sourceFolderOpen}
          onClose={() => {
            dialogStore.close("sourceFolder");
          }}
        />
      </AppShell>
    </div>
  );
}

/**
 * Toaster wrapper that respects the theme preference.
 * Spec: Slice 26 — position bottom-right, theme from data-theme.
 */
function ThemedToaster() {
  const theme = useThemePreference();
  // Resolve "system" to actual dark/light for Sonner theme prop.
  let effectiveTheme: "light" | "dark" = "dark";
  if (theme === "system") {
    try {
      effectiveTheme = window.matchMedia("(prefers-color-scheme: light)").matches
        ? "light"
        : "dark";
    } catch {
      // Test environments may not have matchMedia; default to dark.
    }
  } else {
    effectiveTheme = theme;
  }

  return <Toaster richColors position="bottom-right" theme={effectiveTheme} />;
}

// ── Phase 2.4: UIPrefsConfig shim (GAP-1, GAP-2) ───────────────────────────
//
// The backend does not yet expose GET/POST /api/ui-prefs endpoints.
// `load` returns a baseline UIPrefs object seeded from localStorage theme;
// `persistCommon` and `persistApp` write to localStorage as a stopgap.
// Full server-side persistence is deferred to Phase 2.5 (reactive stores).
const UI_PREFS_CONFIG: UIPrefsConfig = {
  load: async () => {
    // Seed theme from localStorage (matches the local ui-prefs.ts logic).
    let theme: "dark" | "light" = "dark";
    try {
      const raw = localStorage.getItem("pdl.ui.theme");
      if (raw === "light") theme = "light";
    } catch {
      // localStorage unavailable
    }
    let fontScale = 1;
    try {
      const rawFs = localStorage.getItem("pdl.ui.fontScale");
      if (rawFs !== null) {
        const parsed = parseFloat(rawFs);
        if (Number.isFinite(parsed) && parsed > 0) fontScale = parsed;
      }
    } catch {
      // localStorage unavailable
    }
    return { theme, density: "normal", fontScale };
  },
  persistCommon: async (prefs) => {
    // GAP-1: no backend — write theme + fontScale to localStorage only.
    try {
      localStorage.setItem("pdl.ui.theme", prefs.theme);
      localStorage.setItem("pdl.ui.fontScale", String(prefs.fontScale));
    } catch {
      // ignore
    }
  },
  persistApp: async (_appPrefs) => {
    // GAP-2: no backend — no-op until Phase 2.5.
  },
};

// ── Phase 2.4: SuiteSiblings fetch/launch shims (GAP-3) ─────────────────────
//
// The backend does not yet expose /api/suite/installed or /api/suite/launch.
// fetchInstalled returns an empty list (no siblings shown in launcher).
// postLaunch returns requires-host-config so the launcher shows an error
// rather than a crash if somehow invoked.
async function fetchInstalled(): Promise<InstalledApp[]> {
  // GAP-3: when pd-ocr-ops mounts /api/suite/* in FastAPI, replace with:
  //   const res = await fetch("/api/suite/installed");
  //   if (!res.ok) return [];
  //   return (await res.json()) as InstalledApp[];
  return [];
}

async function postLaunch(id: string): Promise<LaunchResult> {
  // GAP-3: when pd-ocr-ops mounts /api/suite/* in FastAPI, replace with:
  //   const res = await fetch(`/api/suite/launch`, {
  //     method: "POST", body: JSON.stringify({ id }),
  //     headers: { "Content-Type": "application/json" },
  //   });
  //   return (await res.json()) as LaunchResult;
  return { kind: "requires-host-config", siblingId: id };
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        {/*
         * Phase 2.4: SuiteSiblingsProvider supplies the launcher context
         * that pd-ui AppShell's LauncherSlot reads via useSuiteSiblingsContext().
         * fetchInstalled / postLaunch are shims (GAP-3) until pd-ocr-ops
         * mounts /api/suite/* in the FastAPI app.
         */}
        <SuiteSiblingsProvider value={{ fetchInstalled, postLaunch }}>
          <AppInner />
          {/* Single Toaster instance — all toasts routed through sonner.
              Position: bottom-right (Slice 26).
              Theme matches data-theme preference. */}
          <ThemedToaster />
        </SuiteSiblingsProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

// App.tsx — SPA root: router, QueryClient provider, and route table.
// Spec: docs/specs/2026-05-12-frontend-shell-design.md §Routing
// Issue #240
//
// Route table (from routes.ts):
//   /                                              → RootPage (session-state redirect or EmptyProjectState)
//   /projects/:projectId                           → redirect to pageno/1
//   /projects/:projectId/pages/pageno/:pageNo      → ProjectPage (main labeling surface)
//   /projects/:projectId/pages/index/:idx0         → redirect to pageno equivalent
//   *                                              → 404 fallback (redirect to /)

import { BrowserRouter, Routes, Route, Navigate, useParams, useMatch } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "sonner";

import { Suspense, lazy } from "react";
import HeaderBar from "./components/HeaderBar";
import RootPage from "./pages/RootPage";
import ProjectPage from "./pages/ProjectPage";
import { ROUTES } from "./lib/routes";
import { useThemePreference } from "./stores/ui-prefs";

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
function AppShell() {
  useNotificationStream();

  // Dialog open-state slices — re-render only when these change.
  const ocrConfigOpen = useDialogStore((s) => s.ocrConfig.open);
  const exportOpen = useDialogStore((s) => s.export.open);
  const sourceFolderOpen = useDialogStore((s) => s.sourceFolder.open);
  const { projectId, pageIndex } = useRouteProjectContext();

  return (
    <div data-testid="app-shell" className="flex flex-col h-screen">
      <HeaderBar />
      {/*
       * Accessible live regions — spec #238.
       * status-announcer: polite — announces bulk action completions
       *   (e.g. "Validated 5 words") without interrupting the user.
       * error-announcer: assertive — announces critical errors
       *   (e.g. "OCR failed") immediately.
       * Both are visually hidden; text is injected by bulk-action hooks.
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
      <main className="flex-1 min-h-0 overflow-hidden">
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

      {/*
       * Dialogs mounted at AppShell (spec 22 §3).
       *
       * `HotkeyHelpModal` subscribes to the dialog store itself (it also
       * listens to the `?` key globally). `OCRConfigModal` + `ExportDialog`
       * read their open-state via their `open` prop. Export dialog only
       * shows when a project is loaded (no `projectId` → skip render).
       */}
      <OCRConfigModal open={ocrConfigOpen} onClose={() => dialogStore.close("ocrConfig")} />
      {projectId && (
        <ExportDialog
          open={exportOpen}
          projectId={projectId}
          currentPageIndex={pageIndex}
          onClose={() => dialogStore.close("export")}
        />
      )}
      <HotkeyHelpModal />
      <SourceFolderDialog
        open={sourceFolderOpen}
        onClose={() => dialogStore.close("sourceFolder")}
      />
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

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppShell />
        {/* Single Toaster instance — all toasts routed through sonner.
            Position: bottom-right (Slice 26).
            Theme matches data-theme preference. */}
        <ThemedToaster />
      </BrowserRouter>
    </QueryClientProvider>
  );
}

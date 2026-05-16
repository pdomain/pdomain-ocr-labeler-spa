// ProjectPage.tsx — real labeling shell.
//
// Spec: specs/22-page-surface-wireup.md §3 (Layout), §4 (Data flow),
//       §10 (Driver-contract preservation), §11 (Notifications).
// Issue #314 (spec-22-C).
//
// Replaces the 76-line `display:none`-stub page with the full §3 layout:
//
//   <ProjectPage>
//     <ProjectLoadingOverlay />
//     <PageHeader>
//       <ProjectNavigationControls />
//       <PageActions />
//     </PageHeader>
//     <ToolbarActionGrid />
//     <Splitter direction="horizontal">
//       <LeftPane data-testid="image-pane">
//         <ImageTabsHeader />
//         <BusyOverlay />
//         <PageImageCanvas />
//         <InlineBanners />
//       </LeftPane>
//       <RightPane data-testid="text-pane">
//         <TextTabs>
//           <FilterToggle /> + <WordMatchView />   // matches sub-tab
//           <PlaintextEditor source="gt" />        // ground-truth sub-tab
//           <PlaintextEditor source="ocr" />       // ocr sub-tab
//         </TextTabs>
//       </RightPane>
//     </Splitter>
//     <WordEditDialog />
//     <ConfirmDialog />
//   </ProjectPage>
//
// The legacy `display:none` testid stubs (nav-* and source-folder-*) moved
// to HeaderBar so they remain reachable from every route while the real
// ProjectNavigationControls renders here without `data-testid-stub`.
//
// Data flow:
//   - `useProject(projectId)` and `usePage(projectId, idx0)` drive the surface.
//   - Mutation hooks (page actions, word edits, …) invalidate
//     `["page", projectId, idx0]` so usePage re-fetches.
//   - `useJobProgress` feeds the BusyOverlay.
//
// Hook-order discipline: ALL hooks are called unconditionally at the top
// before any early return, matching the Rules of Hooks.

import { useMemo, useState, useSyncExternalStore, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "../lib/toast";

import { useProject } from "../hooks/useProject";
import { usePage } from "../hooks/usePage";
import { useJobProgress } from "../hooks/useJobProgress";
import {
  useReloadOcr,
  useReloadOcrEdited,
  useSavePage,
  useSaveProject,
  useLoadPage,
  useRematchGt,
} from "../hooks/usePageMutations";
import {
  useValidateLine,
  useCopyLineGt,
  useDeleteLine,
  useMergeLines,
} from "../hooks/useLineMutations";
import { useGlobalHotkeys } from "../hooks/useGlobalHotkeys";
import { useMatchesHotkeys } from "../hooks/useMatchesHotkeys";
import { useUiPrefs, type DrawerTab, type MatchFilter } from "../stores/ui-prefs";
import { dialogStore, useDialogStore } from "../stores/dialog-store";
import { selectionStore, type SelectionState } from "../stores/selection-store";
import { viewportStore, toggleEraseMode, setCanvasZoom } from "../stores/viewport-store";
import { worklistStore } from "../stores/worklist-store";
import { pageNoUrl } from "../lib/routes";

import { PageActions } from "../components/PageActions";
import { Drawer } from "../components/shell/Drawer";
import { ToolbarActionGrid } from "../components/ToolbarActionGrid";
import { ImageTabsHeader } from "../components/ImageTabsHeader";
import { BusyOverlay, ProjectLoadingOverlay } from "../components/BusyOverlay";
import PageImageCanvas from "../components/PageImageCanvas";
import { OcrFailedBanner, ImageDriftBanner } from "../components/InlineBanners";
import { TextTabs } from "../components/TextTabs";
import { WordMatchView } from "../components/WordMatchView";
import { PlaintextEditor } from "../components/PlaintextEditor";
import { WordEditDialog, type DialogTarget } from "../components/WordEditDialog";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { StudioShell } from "../components/shell/StudioShell";
import { Rail } from "../components/shell/Rail";
import { RightPanel } from "../components/shell/RightPanel";
import { WordDetail } from "../components/right-panel/WordDetail";
import { useBreadcrumbHotkeys } from "../hooks/useBreadcrumbHotkeys";

import type {
  Selection as ToolbarSelection,
  PageData,
  ButtonStates,
} from "../hooks/useToolbarButtonStates";
import type { components } from "../api/types";

type PagePayload = components["schemas"]["PagePayload"];
type LineMatch = components["schemas"]["LineMatch"];

// ─── ui-prefs subscriber bridge ─────────────────────────────────────────────
// The hand-rolled `useUiPrefs` store has no native `subscribe()`. We bridge
// to React via `useSyncExternalStore` so the page re-renders when prefs
// change (match filter, layer visibility, selection mode, …). Mirrors the
// pattern used in `Splitter.tsx` and `FilterToggle.tsx`.

const uiPrefsListeners = new Set<() => void>();
function notifyUiPrefs() {
  uiPrefsListeners.forEach((fn) => fn());
}
function subscribeUiPrefs(cb: () => void): () => void {
  uiPrefsListeners.add(cb);
  return () => {
    uiPrefsListeners.delete(cb);
  };
}

function setMatchFilter(filter: MatchFilter) {
  useUiPrefs.setMatchFilter(filter);
  notifyUiPrefs();
}

function setLayerVisibility(layer: "paragraph" | "line" | "word", visible: boolean) {
  const current = useUiPrefs.getState().layerVisibility;
  useUiPrefs.setState({ layerVisibility: { ...current, [layer]: visible } });
  notifyUiPrefs();
}

function setSelectionMode(mode: "paragraph" | "line" | "word") {
  useUiPrefs.setState({ selectionMode: mode });
  notifyUiPrefs();
}

function getUiPrefsSnapshot() {
  return useUiPrefs.getState();
}

// ─── drawerOpen subscriber — uses useUiPrefs.subscribe directly ─────────────
// IS-3: Subscribe to the store's native subscribe so Drawer's internal
// setDrawerOpen (which calls useUiPrefs.setState) is reflected here.
// The local `notifyUiPrefs` pattern only covers mutations made via the
// local helper functions defined above; Drawer mutates the store directly.

function subscribeDrawerOpen(cb: () => void): () => void {
  return useUiPrefs.subscribe(cb);
}
function getDrawerOpenSnapshot(): boolean {
  return useUiPrefs.getState().drawerOpen;
}

// ─── rightPanelOpen subscriber — IS-6 ────────────────────────────────────────

function subscribeRightPanelOpen(cb: () => void): () => void {
  return useUiPrefs.subscribe(cb);
}
function getRightPanelOpenSnapshot(): boolean {
  return useUiPrefs.getState().rightPanelOpen;
}

// ─── selection-store subscriber ─────────────────────────────────────────────

function subscribeSelection(cb: () => void): () => void {
  return selectionStore.subscribe(() => cb());
}
function getSelectionSnapshot(): SelectionState {
  return selectionStore.getState();
}

// ─── viewport-store subscriber (erase mode) ─────────────────────────────────

function subscribeViewport(cb: () => void): () => void {
  return viewportStore.subscribe(() => cb());
}
function getViewportModeSnapshot(): string {
  return viewportStore.getState().mode;
}

// ─── Derived data helpers ───────────────────────────────────────────────────

/** Build the `PageData` shape needed by ToolbarActionGrid from a payload.
 *
 * `WordMatch.word_index` is nullable in the wire schema (unmatched-GT rows
 * carry `null`) but `WordValidationInfo.word_index` is required-int. We
 * drop the null entries — they're already non-targetable for word-scope
 * toolbar actions.
 */
function toToolbarPageData(payload: PagePayload | undefined | null): PageData {
  const lines = payload?.line_matches ?? [];
  return {
    lines: lines.map((line: LineMatch) => ({
      line_index: line.line_index,
      paragraph_index: line.paragraph_index ?? null,
      validated_word_count: line.validated_word_count,
      total_word_count: line.total_word_count,
      words: line.word_matches
        .filter((w): w is typeof w & { word_index: number } => w.word_index !== null)
        .map((w) => ({
          line_index: w.line_index,
          word_index: w.word_index,
          is_validated: w.is_validated,
        })),
    })),
  };
}

// ─── Component ──────────────────────────────────────────────────────────────

export default function ProjectPage() {
  // ── URL params (1-based pageNo → 0-based idx0) ──────────────────────────
  const { projectId, pageNo } = useParams<{ projectId: string; pageNo: string }>();
  const navigate = useNavigate();
  const idx0 = useMemo(() => {
    const n = parseInt(pageNo ?? "1", 10);
    return Number.isFinite(n) && n > 0 ? n - 1 : 0;
  }, [pageNo]);

  // ── Top-level data hooks — always called before any early return ────────
  const projectQ = useProject(projectId);
  const pageQ = usePage(projectId, idx0);
  // Active job tracking — fed by mutation hooks when they return job_ids.
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const jobProgress = useJobProgress(activeJobId);

  // ── Store subscribers ──────────────────────────────────────────────────
  const uiPrefs = useSyncExternalStore(subscribeUiPrefs, getUiPrefsSnapshot, getUiPrefsSnapshot);
  // IS-3: drawerOpen via store's native subscribe (catches Drawer's own setState).
  const drawerOpen = useSyncExternalStore(
    subscribeDrawerOpen,
    getDrawerOpenSnapshot,
    getDrawerOpenSnapshot,
  );
  // IS-6: rightPanelOpen via store's native subscribe.
  const rightPanelOpen = useSyncExternalStore(
    subscribeRightPanelOpen,
    getRightPanelOpenSnapshot,
    getRightPanelOpenSnapshot,
  );
  const selection = useSyncExternalStore(
    subscribeSelection,
    getSelectionSnapshot,
    getSelectionSnapshot,
  );
  const selectionLevel = useSyncExternalStore(
    selectionStore.subscribe,
    () => selectionStore.getState().level,
    () => "none" as const,
  );
  const vpMode = useSyncExternalStore(
    subscribeViewport,
    getViewportModeSnapshot,
    getViewportModeSnapshot,
  );
  const wordEditState = useDialogStore((s) => s.wordEdit);
  const confirmState = useDialogStore((s) => s.confirm);

  // ── QueryClient (for explicit invalidation after job-completion / saves) ─
  const qc = useQueryClient();

  // ── Mutations ──────────────────────────────────────────────────────────
  // `projectId` may be undefined on first render before the URL resolves;
  // mutations are stable hooks so we pass "" — the user can't trigger them
  // until the URL is real (PageActions is disabled while isBusy).
  const pid = projectId ?? "";
  const reloadOcr = useReloadOcr(pid, idx0);
  const reloadOcrEdited = useReloadOcrEdited(pid, idx0);
  const savePage = useSavePage(pid, idx0);
  const saveProject = useSaveProject(pid);
  const loadPage = useLoadPage(pid, idx0);
  const rematchGt = useRematchGt(pid, idx0);

  // ── Line mutations for useMatchesHotkeys (BUG-KBD-3) ──────────────────
  const validateLine = useValidateLine(pid, idx0);
  const copyLineGt = useCopyLineGt(pid, idx0);
  const deleteLine = useDeleteLine(pid, idx0);
  const mergeLines = useMergeLines(pid, idx0);

  // ── Derived view state ─────────────────────────────────────────────────
  const pagePayload = pageQ.data ?? null;
  const pageRecord = pagePayload?.page_record ?? null;
  const lines: LineMatch[] = pagePayload?.line_matches ?? [];

  // ── Breadcrumb / hierarchy hotkeys (Alt+arrows) ────────────────────────
  // Registered at the page level so they work anywhere on the project page.
  useBreadcrumbHotkeys({ page: pagePayload ?? undefined });

  // ── Global hotkeys (BUG-KBD-2) ─────────────────────────────────────────
  // Wired here at the page level so Mod+S, Mod+ArrowLeft/Right, etc. are
  // active whenever the project page is mounted. Page-navigation handlers
  // read projectQ.data so they stay current without needing state.
  // `isAnyMutationPending` is computed here (before isMutating below) from
  // the already-declared mutation hooks so useGlobalHotkeys receives a value
  // in the same render pass.
  const isAnyMutationPending =
    reloadOcr.isPending ||
    reloadOcrEdited.isPending ||
    savePage.isPending ||
    saveProject.isPending ||
    loadPage.isPending ||
    rematchGt.isPending;
  const totalPages = projectQ.data?.image_paths?.length ?? 0;
  const currentPageNo = idx0 + 1;
  useGlobalHotkeys({
    disabled: isAnyMutationPending,
    onSavePage: handleSavePage,
    onSaveProject: handleSaveProject,
    onLoadPage: handleLoadPage,
    onRematchGt: handleRematchGt,
    onExport: handleExport,
    onPrevPage: () => {
      if (projectId && currentPageNo > 1) navigate(pageNoUrl(projectId, currentPageNo - 1));
    },
    onNextPage: () => {
      if (projectId && currentPageNo < totalPages)
        navigate(pageNoUrl(projectId, currentPageNo + 1));
    },
    onFirstPage: () => {
      if (projectId && totalPages > 0 && currentPageNo !== 1) navigate(pageNoUrl(projectId, 1));
    },
    onLastPage: () => {
      if (projectId && totalPages > 0 && currentPageNo !== totalPages)
        navigate(pageNoUrl(projectId, totalPages));
    },
  });

  // ── Matches hotkeys (BUG-KBD-3) ─────────────────────────────────────────
  // Wired at the page level — operates on worklistStore.selectedLineIndex to
  // know which line is "current" for all action hotkeys (V/U/D/O/G/M/R).
  useMatchesHotkeys({
    onLineNav: (delta) => {
      const { selectedLineIndex } = worklistStore.getState();
      const nextIdx = (selectedLineIndex ?? -1) + delta;
      const clampedIdx = Math.max(0, Math.min(lines.length - 1, nextIdx));
      worklistStore.setSelectedLineIndex(clampedIdx);
    },
    onValidate: () => {
      const { selectedLineIndex } = worklistStore.getState();
      if (selectedLineIndex !== null)
        validateLine.mutate({ lineIndex: selectedLineIndex, validated: true });
    },
    onUnvalidate: () => {
      const { selectedLineIndex } = worklistStore.getState();
      if (selectedLineIndex !== null)
        validateLine.mutate({ lineIndex: selectedLineIndex, validated: false });
    },
    onDelete: () => {
      const { selectedLineIndex } = worklistStore.getState();
      if (selectedLineIndex !== null) deleteLine.mutate({ lineIndex: selectedLineIndex });
    },
    onRefine: () => {
      // Refine is not yet a line-level mutation; no-op placeholder.
    },
    onExpandRefine: () => {
      // Expand+refine is not yet a line-level mutation; no-op placeholder.
    },
    onMerge: () => {
      const { selectedLineIndex } = worklistStore.getState();
      if (selectedLineIndex !== null && selectedLineIndex > 0)
        mergeLines.mutate({ lineIndex: selectedLineIndex, direction: "prev" });
    },
    onOcrToGt: () => {
      const { selectedLineIndex } = worklistStore.getState();
      if (selectedLineIndex !== null)
        copyLineGt.mutate({ lineIndex: selectedLineIndex, direction: "ocr_to_gt" });
    },
    onGtToOcr: () => {
      const { selectedLineIndex } = worklistStore.getState();
      if (selectedLineIndex !== null)
        copyLineGt.mutate({ lineIndex: selectedLineIndex, direction: "gt_to_ocr" });
    },
  });

  // Project not found vs other errors — only the 404 case triggers the redirect.
  const projectStatus = (projectQ.error as { status?: number } | null)?.status;
  const projectNotFound = projectQ.isError && projectStatus === 404;

  // IS-1: Auto-redirect to / when the project is not found.
  useEffect(() => {
    if (projectNotFound) {
      toast.warn("Project not found — returning to project list.");
      navigate("/", { replace: true, state: { skipSessionRedirect: true } });
    }
  }, [projectNotFound, navigate]);

  // GAP-3: Persist page cursor on navigation (debounced 300 ms, fire-and-forget).
  // The backend stores the cursor in session_state.json so the project reopens
  // on the same page.  We skip the call when projectId is not yet resolved.
  useEffect(() => {
    if (!projectId) return;
    const timer = setTimeout(() => {
      void fetch(`/api/projects/${projectId}/current-page-index`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ page_index: idx0 }),
      });
    }, 300);
    return () => clearTimeout(timer);
  }, [projectId, idx0]);

  // Show ProjectLoadingOverlay during the initial page fetch.
  const isPageLoading = pageQ.isLoading;

  // Busy state — any mutation in flight OR an active job.
  const isMutating =
    reloadOcr.isPending ||
    reloadOcrEdited.isPending ||
    savePage.isPending ||
    saveProject.isPending ||
    loadPage.isPending ||
    rematchGt.isPending;

  // Pseudo-Job object for BusyOverlay. BusyOverlay accepts the full
  // `components.schemas.Job` shape but only branches on `type` / `status`;
  // we synthesize the minimal shape from the SSE progress event. The
  // `id` / `project_id` / `created_at` / `updated_at` fields are required
  // by the type but not consumed by the overlay — placeholder values keep
  // tsc happy without inventing data.
  const nowIso = new Date(0).toISOString();
  const activeJob: components["schemas"]["Job"] | null =
    jobProgress && jobProgress.status !== "complete" && jobProgress.status !== "error"
      ? {
          id: jobProgress.job_id,
          project_id: projectId ?? null,
          type: "reload_ocr_page" as components["schemas"]["JobType"],
          status: jobProgress.status,
          progress: jobProgress.progress,
          error_message: jobProgress.error_message ?? null,
          created_at: nowIso,
          updated_at: nowIso,
        }
      : null;

  // ToolbarActionGrid plumbing
  const toolbarSelection: ToolbarSelection = useMemo(
    () => ({
      selection_mode: uiPrefs.selectionMode,
      selected_paragraphs: selection.selectedParagraphs,
      selected_lines: selection.selectedLines,
      selected_words: selection.selectedWords,
    }),
    [
      uiPrefs.selectionMode,
      selection.selectedParagraphs,
      selection.selectedLines,
      selection.selectedWords,
    ],
  );
  const toolbarPageData: PageData = useMemo(() => toToolbarPageData(pagePayload), [pagePayload]);
  const [addWordActive, setAddWordActive] = useState(false);

  // WordEditDialog `target` requires both line/word indices; default to 0/0
  // when the store hasn't been populated (dialog is closed in that case).
  const dialogTarget: DialogTarget = {
    lineIndex: wordEditState.lineIdx ?? 0,
    wordIndex: wordEditState.wordIdx ?? 0,
  };

  // Words list passed to the dialog for the 3-column preview row.
  const dialogLine = lines.find((l) => l.line_index === dialogTarget.lineIndex) ?? null;
  const dialogLineWords = dialogLine?.word_matches.map((w) => w.ocr_text) ?? [];

  // ── Action callbacks ───────────────────────────────────────────────────
  // Mutations return job_ids for async actions; we route those into
  // useJobProgress and invalidate on completion. Synchronous mutations
  // invalidate the page query directly.

  function invalidatePage() {
    void qc.invalidateQueries({ queryKey: ["page", projectId, idx0] });
  }

  function trackJob<T extends { job_id?: string | null } | undefined | null>(result: T) {
    const jobId = result?.job_id ?? null;
    if (jobId) setActiveJobId(jobId);
  }

  function handleReloadOcr() {
    reloadOcr.mutate(undefined, {
      onSuccess: (data) => trackJob(data),
      onSettled: () => invalidatePage(),
    });
  }
  function handleReloadOcrEdited() {
    reloadOcrEdited.mutate(undefined, {
      onSuccess: (data) => trackJob(data),
      onSettled: () => invalidatePage(),
    });
  }
  function handleSavePage() {
    savePage.mutate(undefined, { onSettled: () => invalidatePage() });
  }
  function handleSaveProject() {
    saveProject.mutate(undefined, {
      onSuccess: (data) => trackJob(data),
      onSettled: () => invalidatePage(),
    });
  }
  function handleLoadPage() {
    loadPage.mutate(undefined, { onSettled: () => invalidatePage() });
  }
  function handleRematchGt() {
    rematchGt.mutate(undefined, { onSettled: () => invalidatePage() });
  }
  function handleExport() {
    dialogStore.open("export");
  }

  function handleToolbarAction(_key: keyof ButtonStates) {
    // Spec 22 §2 (non-goals): wireup-only. Toolbar action POSTs are wired
    // by the per-scope mutation hooks listed in spec 22 §4 — those are
    // either shipped (line mutations, page mutations) or pending (paragraph
    // batch, word-scope batch). Hooking them up belongs to follow-up slices
    // that already track each row individually. For now the buttons fire
    // this callback but invalidate the page so any out-of-band server-side
    // mutation that lands during the click is reflected.
    invalidatePage();
  }
  function handleApplyStyle() {
    invalidatePage();
  }
  function handleClearStyle() {
    invalidatePage();
  }
  function handleAddWordToggle() {
    setAddWordActive((v) => !v);
  }

  // ── Render ─────────────────────────────────────────────────────────────

  // ── Slot content ──────────────────────────────────────────────────────
  // IS-2: The App-level HeaderBar now handles the full top chrome via
  // navSlot (ProjectNavigationControls) and actionsSlot (PageActionsCompact).
  // The StudioShell header zone is left empty so it occupies 0 visual space.
  //
  // PageActions is kept mounted as a hidden div to preserve all driver-
  // contract testids (§2.5: reload-ocr-button, save-page-button, etc.).
  // The driver selects these via [data-testid="..."] — the hidden wrapper
  // does not prevent selection.

  // IS-2: Empty StudioShell header zone — App-level HeaderBar handles chrome.
  const headerSlot = <></>;

  // IS-2: PageActions kept hidden for driver-contract testid preservation.
  // Driver contract §2.5: all page-action testids must be reachable in DOM.
  const hiddenPageActions = (
    <div style={{ display: "none" }} data-testid-stub="page-actions-hidden">
      <PageActions
        isBusy={isMutating || activeJob !== null}
        hasEditedImage={false}
        pageSource={pageRecord?.page_source}
        pageName={pageRecord?.image_path?.split("/").pop() ?? null}
        rotationDegrees={pageRecord?.rotation_degrees ?? 0}
        rotationSource={pageRecord?.rotation_source ?? null}
        onReloadOcr={handleReloadOcr}
        onReloadOcrEdited={handleReloadOcrEdited}
        onSavePage={handleSavePage}
        onSaveProject={handleSaveProject}
        onLoadPage={handleLoadPage}
        onRematchGt={handleRematchGt}
        onExport={handleExport}
      />
    </div>
  );

  // Rail slot — wired in Slice 10.
  const railSlot = <Rail />;

  // IS-3: Drawer wired with real Drawer component.
  // lineMatches is already computed above; page is pagePayload.
  // Gap 18: tabCounts populated so count badges render in the drawer header.
  const worklistCount = lines.filter(
    (l) => l.overall_match_status !== "exact" || !l.is_fully_validated,
  ).length;
  const drawerTabCounts: Partial<Record<DrawerTab, number>> = {
    worklist: worklistCount,
    hierarchy: lines.length,
  };
  const drawerSlot = (
    <Drawer lineMatches={lines} page={pagePayload ?? undefined} tabCounts={drawerTabCounts} />
  );

  // IS-4: Canvas slot stripped to image-only layout.
  // ToolbarActionGrid, Splitter, TextTabs, WordMatchView removed from visible
  // canvas. TextTabs/WordMatchView and ToolbarActionGrid kept as hidden stubs
  // to preserve driver-contract testids (§2.7, §2.8, §2.9, §2.10).
  const canvasSlot = (
    <div className="flex flex-col h-full min-h-0">
      <ImageTabsHeader
        layerVisibility={uiPrefs.layerVisibility}
        selectionMode={uiPrefs.selectionMode}
        eraseActive={vpMode === "erase"}
        onLayerToggle={(layer) => setLayerVisibility(layer, !uiPrefs.layerVisibility[layer])}
        onSelectionModeChange={(mode) => setSelectionMode(mode)}
        onEraseToggle={toggleEraseMode}
        onZoomFit={() => setCanvasZoom(0)}
        onZoom100={() => setCanvasZoom(1.0)}
        matchFilterMode={uiPrefs.matchFilterMode}
        onMatchFilterModeToggle={() => {
          useUiPrefs.setMatchFilterMode(
            uiPrefs.matchFilterMode === "all" ? "mismatches_only" : "all",
          );
          notifyUiPrefs();
        }}
      />
      <div data-testid="image-pane" className="relative flex-1 min-h-0">
        <BusyOverlay activeJob={activeJob} isMutating={isMutating} />
        <PageImageCanvas
          imageUrl={pagePayload?.image_url ?? ""}
          encoded={pagePayload?.encoded_dims ?? null}
          page={pagePayload}
          projectId={projectId}
          pageIndex={idx0}
        />
      </div>
      <div data-testid="inline-banners" className="flex flex-col gap-1 p-1">
        <OcrFailedBanner ocrFailed={pageRecord?.ocr_failed === true} />
        <ImageDriftBanner imageDrift={false} />
      </div>

      {/*
       * IS-4: Driver-contract testid preservation stubs.
       *
       * §2.9/§2.10: ToolbarActionGrid testids (toolbar-{scope}-{action},
       *   apply-style-select, etc.) must remain in DOM.
       * §2.7: TextTabs testids (text-tab-*, match-filter-*) must remain.
       * §2.8: WordMatchView per-line/per-word testids must remain.
       *
       * All kept hidden; drivers select by data-testid not visibility.
       */}
      <div style={{ display: "none" }} data-testid-stub="canvas-hidden-stubs">
        <ToolbarActionGrid
          selection={toolbarSelection}
          pageData={toolbarPageData}
          onAction={handleToolbarAction}
          onApplyStyle={handleApplyStyle}
          onClearStyle={handleClearStyle}
          addWordActive={addWordActive}
          onAddWordToggle={handleAddWordToggle}
        />
        <div data-testid="text-pane">
          <TextTabs
            pageTextGt={pagePayload?.page_text_gt}
            pageTextOcr={pagePayload?.page_text_ocr}
            lineFilter={uiPrefs.matchFilter}
            onLineFilterChange={(f) => setMatchFilter(f as MatchFilter)}
          >
            <WordMatchView lines={lines} filter={uiPrefs.matchFilter} />
          </TextTabs>
          <PlaintextEditor source="gt" page={pagePayload} />
          <PlaintextEditor source="ocr" page={pagePayload} />
        </div>
      </div>
    </div>
  );

  // Right panel slot — RightPanel routes on selection-store.level.
  // Word-level content is WordDetail (Slice 16). WordMatchView stays in the
  // canvas TextTabs.
  // IS-6: onCollapse wired to useUiPrefs.setState({ rightPanelOpen: false }).
  const wordDetailSlot =
    pagePayload && projectId ? (
      <WordDetail page={pagePayload} projectId={projectId} pageIndex={idx0} />
    ) : undefined;
  const rightSlot = rightPanelOpen ? (
    <RightPanel
      page={pagePayload ?? undefined}
      projectId={projectId ?? undefined}
      pageIndex={idx0}
      wordSlot={wordDetailSlot}
      onCollapse={() => useUiPrefs.setState({ rightPanelOpen: false })}
    />
  ) : null;

  return (
    <div data-testid="project-page" className="h-full">
      <ProjectLoadingOverlay isLoading={isPageLoading} />

      <StudioShell
        headerHeight={0}
        header={headerSlot}
        rail={railSlot}
        drawer={drawerSlot}
        canvas={canvasSlot}
        right={rightSlot}
        drawerCollapsed={!drawerOpen}
        rightWidth={selectionLevel === "line" || selectionLevel === "block" ? 640 : 520}
      />

      {/* IS-2: hidden PageActions for driver-contract testid preservation §2.5 */}
      {hiddenPageActions}

      {/* WordEditDialog — opens from per-word pencil click via dialogStore.
          Returns null when open=false, so the dialog testids only appear
          when the user opens it. */}
      <WordEditDialog
        open={wordEditState.open}
        target={dialogTarget}
        lineWords={dialogLineWords}
        wordImageUrl={undefined}
        onNavigate={(t) => dialogStore.openWordEdit({ lineIdx: t.lineIndex, wordIdx: t.wordIndex })}
        onApply={() => {
          invalidatePage();
          dialogStore.close("wordEdit");
        }}
        onClose={() => dialogStore.close("wordEdit")}
      />

      {/* ConfirmDialog — opens from useConfirm() via dialogStore. */}
      <ConfirmDialog
        open={confirmState.open}
        message={confirmState.body ?? ""}
        title={confirmState.title}
        onConfirm={() => {
          confirmState.onConfirm?.();
          dialogStore.close("confirm");
        }}
        onCancel={() => dialogStore.close("confirm")}
      />
    </div>
  );
}

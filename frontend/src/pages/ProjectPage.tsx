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
import { useJobCompletionInvalidation } from "../hooks/useJobCompletionInvalidation";
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
import {
  useApplyStyle,
  useApplyComponent,
  useAddWord,
  useMergeWord,
  useSplitWord,
  useDeleteWord,
  useReboxWord,
  useNudgeWord,
  useUpdateWordGroundTruth,
} from "../hooks/useWordMutations";
// Lane D reuses `toggleAddWordMode` / `exitToSelectMode` (viewport-store
// helpers) + the `handleAddWord` handler below to add an add-word button
// outside the toolbar grid without duplicating the mutation wiring.
import {
  viewportStore,
  toggleAddWordMode,
  toggleEraseMode,
  setCanvasZoom,
} from "../stores/viewport-store";
import { displayToSrc } from "../lib/coords";
import { applyBoxSelect } from "../lib/box-select-handler";
import { findWordByIndex } from "../lib/word-order";
import type { SelectionModifier } from "../components/PageImageCanvas";
import { railStore } from "../stores/rail-store";
import { useGlobalHotkeys } from "../hooks/useGlobalHotkeys";
import { useToolbarDispatch } from "../hooks/useToolbarDispatch";
import { useMatchesHotkeys } from "../hooks/useMatchesHotkeys";
import { useUiPrefs, type DrawerTab, type MatchFilter } from "../stores/ui-prefs";
import { dialogStore, useDialogStore } from "../stores/dialog-store";
import {
  selectionStore,
  clearSelection,
  toggleWord,
  type SelectionState,
} from "../stores/selection-store";
import { worklistStore } from "../stores/worklist-store";
import { pageNoUrl } from "../lib/routes";

import { PageActions } from "../components/PageActions";
import {
  ImageTabsHeader,
  type LayerVisibility as HeaderLayerVisibility,
} from "../components/ImageTabsHeader";
import { Drawer } from "../components/shell/Drawer";
import { ToolbarActionGrid } from "../components/ToolbarActionGrid";
import { BulkWordActions } from "../components/BulkWordActions";
import { BusyOverlay, ProjectLoadingOverlay } from "../components/BusyOverlay";
import PageImageCanvas from "../components/PageImageCanvas";
import { OcrFailedBanner, ImageDriftBanner } from "../components/InlineBanners";
import { TextTabs } from "../components/TextTabs";
import { WordMatchView } from "../components/WordMatchView";
import { PlaintextEditor } from "../components/PlaintextEditor";
import { WordEditDialog, type DialogTarget } from "../components/WordEditDialog";
import { ConfirmDialog } from "../components/ConfirmDialog";
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
  uiPrefsListeners.forEach((fn) => {
    fn();
  });
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
  return selectionStore.subscribe(() => {
    cb();
  });
}
function getSelectionSnapshot(): SelectionState {
  return selectionStore.getState();
}

// ─── viewport add-word mode subscriber (B2) ─────────────────────────────────
// `addWordActive` is derived from viewportStore.mode so the grid toggle, the
// Rail annotate button, and any Lane D add-word button share one source of
// truth. The canvas already drives its draw behaviour from viewportStore.

function subscribeViewportMode(cb: () => void): () => void {
  return viewportStore.subscribe(cb);
}
function getAddWordActiveSnapshot(): boolean {
  return viewportStore.getState().mode === "add-word";
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
  // B2: add-word mode mirrors viewportStore (single source of truth).
  const addWordActive = useSyncExternalStore(
    subscribeViewportMode,
    getAddWordActiveSnapshot,
    getAddWordActiveSnapshot,
  );
  // C1: viewport interaction mode — drives the ImageTabsHeader Erase toggle's
  // active state so the header and the Rail stay in sync on one source of truth
  // (viewportStore). The Rail's "erase" mode is mirrored into viewportStore by
  // PageImageCanvas; reading it here keeps both chrome surfaces consistent.
  const viewportMode = useSyncExternalStore(
    viewportStore.subscribe,
    () => viewportStore.getState().mode,
    () => "select" as const,
  );
  const wordEditState = useDialogStore((s) => s.wordEdit);
  const confirmState = useDialogStore((s) => s.confirm);

  // ── QueryClient (for explicit invalidation after job-completion / saves) ─
  const qc = useQueryClient();

  // ── Terminal-status invalidation (#377) ────────────────────────────────
  // Mutations such as `useReloadOcr` / `useReloadOcrEdited` / `useSaveProject`
  // return a 202 + `job_id`; their `onSettled` fires on that 202 — long before
  // OCR has actually run. The shared hook watches `jobProgress.status` and
  // re-invalidates the page query once the SSE terminal event arrives, so
  // the worklist / canvas refresh when the job actually completes.
  useJobCompletionInvalidation({
    activeJobId,
    jobProgress,
    setActiveJobId,
    invalidationKey: ["page", projectId, idx0],
  });

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

  // ── Word mutations for the Apply-Style / Component / Add-Word controls (B2) ─
  const applyStyle = useApplyStyle(pid, idx0);
  const applyComponent = useApplyComponent(pid, idx0);
  const addWord = useAddWord(pid, idx0);

  // ── Word mutations for WordEditDialog (S1.2 — dialog wiring) ──────────────
  // These are also used by S3 (reboxWord shared for canvas rebox).
  const mergeWord = useMergeWord(pid, idx0);
  const splitWord = useSplitWord(pid, idx0);
  const deleteWord = useDeleteWord(pid, idx0);
  const reboxWord = useReboxWord(pid, idx0);
  const nudgeWord = useNudgeWord(pid, idx0);
  const updateGtWord = useUpdateWordGroundTruth(pid, idx0);

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
      if (projectId && currentPageNo > 1) void navigate(pageNoUrl(projectId, currentPageNo - 1));
    },
    onNextPage: () => {
      if (projectId && currentPageNo < totalPages)
        void navigate(pageNoUrl(projectId, currentPageNo + 1));
    },
    onFirstPage: () => {
      if (projectId && totalPages > 0 && currentPageNo !== 1)
        void navigate(pageNoUrl(projectId, 1));
    },
    onLastPage: () => {
      if (projectId && totalPages > 0 && currentPageNo !== totalPages)
        void navigate(pageNoUrl(projectId, totalPages));
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
    // F-035: D key is destructive — route through confirm dialog before mutating.
    onDelete: () => {
      const { selectedLineIndex } = worklistStore.getState();
      if (selectedLineIndex !== null) {
        dialogStore.openConfirm({
          title: "Delete line?",
          body: "This will permanently remove the selected line from the page. This action cannot be undone.",
          onConfirm: () => {
            deleteLine.mutate({ lineIndex: selectedLineIndex });
          },
        });
      }
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
      void navigate("/", { replace: true, state: { skipSessionRedirect: true } });
    }
  }, [projectNotFound, navigate]);

  // GAP-3: Persist page cursor on navigation (debounced 300 ms, fire-and-forget).
  // The backend stores the cursor in session_state.json so the project reopens
  // on the same page.  We skip the call when projectId is not yet resolved.
  useEffect(() => {
    if (!projectId) return;
    const timer = setTimeout(() => {
      void fetch(`/api/projects/${encodeURIComponent(projectId)}/current-page-index`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ page_index: idx0 }),
      });
    }, 300);
    return () => {
      clearTimeout(timer);
    };
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
  // B1: resolve grid cell clicks → real mutations against the scope-batch
  // routes (Lane A) + existing validate/style/component routes.
  const dispatchToolbarAction = useToolbarDispatch(pid, idx0, toolbarSelection);

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

  function trackJob(result: { job_id?: string | null } | undefined | null) {
    const jobId = result?.job_id ?? null;
    if (jobId) setActiveJobId(jobId);
  }

  function handleReloadOcr() {
    reloadOcr.mutate(undefined, {
      onSuccess: (data) => {
        trackJob(data);
      },
      onSettled: () => {
        invalidatePage();
      },
    });
  }
  function handleReloadOcrEdited() {
    reloadOcrEdited.mutate(undefined, {
      onSuccess: (data) => {
        trackJob(data);
      },
      onSettled: () => {
        invalidatePage();
      },
    });
  }
  function handleSavePage() {
    savePage.mutate(undefined, {
      onSuccess: (data) => {
        // Glyph-review gate: surface backend warnings as toasts (AC #270).
        if (data.warnings && data.warnings.length > 0) {
          data.warnings.forEach((w) => toast.warn(w));
        }
      },
      onSettled: () => {
        invalidatePage();
      },
    });
  }
  function handleSaveProject() {
    saveProject.mutate(undefined, {
      onSuccess: (data) => {
        trackJob(data);
      },
      onSettled: () => {
        invalidatePage();
      },
    });
  }
  // F-035: Route destructive hotkeys (Mod+L, Mod+G) through the confirm dialog
  // so accidental keypresses cannot discard or recompute page data without
  // the user explicitly confirming.
  function handleLoadPage() {
    dialogStore.openConfirm({
      title: "Load page?",
      body: "This will discard any unsaved changes and reload the page from the last saved state. This action cannot be undone.",
      onConfirm: () => {
        loadPage.mutate(undefined, {
          onSettled: () => {
            invalidatePage();
          },
        });
      },
    });
  }
  function handleRematchGt() {
    dialogStore.openConfirm({
      title: "Rematch GT?",
      body: "This will re-run ground-truth matching for the current page, overwriting any manual GT edits. This action cannot be undone.",
      onConfirm: () => {
        rematchGt.mutate(undefined, {
          onSettled: () => {
            invalidatePage();
          },
        });
      },
    });
  }
  function handleExport() {
    dialogStore.open("export");
  }

  function handleToolbarAction(key: keyof ButtonStates) {
    // B1 (Lane B): dispatch the real mutation for the clicked grid cell.
    // useToolbarDispatch resolves the route + body from toolbarMapping +
    // the current selection, fires the POST, invalidates the page on
    // success, and surfaces errors via toast.
    dispatchToolbarAction(key);
  }
  // B2: style / component apply over the current word selection. Each is a
  // per-word route (`words/{li}/{wi}/style|component`); we fire one mutation
  // per selected word. Falls back to the breadcrumb word path when the
  // multi-select array is empty but a single word is the active selection.
  function selectedWordTargets(): [number, number][] {
    const fromArray = selection.selectedWords;
    if (fromArray.length > 0) return fromArray;
    const wp = selection.path.wordId;
    return wp ? [wp] : [];
  }

  function handleApplyStyle(style: string, scope: string) {
    if (!style) return;
    const targets = selectedWordTargets();
    if (targets.length === 0) {
      toast.warn("Select one or more words before applying a style.");
      return;
    }
    const applyScope = scope === "part" ? "part" : "whole";
    for (const [lineIndex, wordIndex] of targets) {
      applyStyle.mutate({ lineIndex, wordIndex, style, scope: applyScope });
    }
  }
  // Clearing a style maps to applying the "regular" style — pdomain-book-tools'
  // `apply_style_scope` discards "regular", so the word reverts to plain text.
  function handleClearStyle(_style: string, scope: string) {
    const targets = selectedWordTargets();
    if (targets.length === 0) {
      toast.warn("Select one or more words before clearing a style.");
      return;
    }
    const applyScope = scope === "part" ? "part" : "whole";
    for (const [lineIndex, wordIndex] of targets) {
      applyStyle.mutate({ lineIndex, wordIndex, style: "regular", scope: applyScope });
    }
  }
  function handleApplyComponent(component: string) {
    if (!component) return;
    const targets = selectedWordTargets();
    if (targets.length === 0) {
      toast.warn("Select one or more words before setting a component.");
      return;
    }
    for (const [lineIndex, wordIndex] of targets) {
      applyComponent.mutate({ lineIndex, wordIndex, component, enabled: true });
    }
  }
  function handleClearComponent(component: string) {
    if (!component) return;
    const targets = selectedWordTargets();
    if (targets.length === 0) {
      toast.warn("Select one or more words before clearing a component.");
      return;
    }
    for (const [lineIndex, wordIndex] of targets) {
      applyComponent.mutate({ lineIndex, wordIndex, component, enabled: false });
    }
  }
  // SEL-2: drag-box select handler. Receives the drag rect (display pixels)
  // from PageImageCanvas after a non-trivial drag in select mode. Computes
  // which words intersect the rect and sets selectedWords in selectionStore
  // SEL-2 / Slice B: onBoxSelect with modifier-aware accumulation.
  // replace → set all intersecting words (discard prior selection).
  // toggle  → add words not yet selected, remove words already selected.
  // remove  → remove all intersecting words from current selection.
  function handleBoxSelect(
    rect: { x: number; y: number; width: number; height: number },
    modifier: SelectionModifier,
  ) {
    if (!pagePayload) return;
    const words = applyBoxSelect(pagePayload, rect, modifier);
    if (words.length === 0) {
      if (modifier === "replace") clearSelection();
      return;
    }
    // Apply toggleWord per word so accumulation logic is consistent with
    // single-click (SEL-4/SEL-5 uses the same toggleWord primitive).
    if (modifier === "replace") {
      // First word replaces, subsequent words toggle-in (all new → add).
      const [firstLine, firstWord] = words[0]!;
      toggleWord(firstLine, firstWord, "replace");
      for (let i = 1; i < words.length; i++) {
        toggleWord(words[i]![0], words[i]![1], "toggle");
      }
    } else {
      for (const [lineIdx, wordIdx] of words) {
        toggleWord(lineIdx, wordIdx, modifier);
      }
    }
    useUiPrefs.setState({ rightPanelOpen: true });
  }

  // B2: toggle add-word mode through viewportStore so the canvas, Rail, and
  // any Lane D add-word button stay in sync. Lane D's button calls the same
  // toggle + clear handler (handleClearAddWord).
  function handleAddWordToggle() {
    toggleAddWordMode();
  }
  // B2: a completed add-word draw. `rect` is in display (page-space) pixels;
  // convert to source pixels with the encoded scale before POSTing. Lane D
  // reuses this handler via the same `onAddWord` canvas prop.
  function handleAddWord(rect: { x: number; y: number; width: number; height: number }) {
    const scale = pagePayload?.encoded_dims?.scale ?? 1;
    const srcBbox = displayToSrc(rect, scale);
    addWord.mutate({ bbox: srcBbox });
  }

  // S3: a completed rebox draw. `rect` is in display pixels; convert to source
  // pixels before POSTing to .../words/{li}/{wi}/rebox. The pending target is
  // read from viewportStore (set by WordDetail rebox accordion).
  function handleRebox(rect: { x: number; y: number; width: number; height: number }) {
    const t = viewportStore.getState().pendingReboxTarget;
    if (!t) return;
    const scale = pagePayload?.encoded_dims?.scale ?? 1;
    const srcBbox = displayToSrc(rect, scale);
    reboxWord.mutate({ lineIndex: t.lineIndex, wordIndex: t.wordIndex, bbox: srcBbox });
  }

  // ── Render ─────────────────────────────────────────────────────────────

  // ── Slot content ──────────────────────────────────────────────────────
  // IS-2: The App-level HeaderBar now handles the full top chrome via
  // navSlot (ProjectNavigationControls) and actionsSlot (PageActionsCompact).
  //
  // PageActions is kept mounted as a hidden div to preserve all driver-
  // contract testids (§2.5: reload-ocr-button, save-page-button, etc.).
  // The driver selects these via [data-testid="..."] — the hidden wrapper
  // does not prevent selection.

  // IS-2: PageActions kept hidden for driver-contract testid preservation.
  // Driver contract §2.5: all page-action testids must be reachable in DOM.
  const hiddenPageActions = (
    <div style={{ display: "none" }} data-testid-stub="page-actions-hidden">
      <PageActions
        isBusy={isMutating || activeJob !== null}
        // C2: bind to the real edited-image signal (labeler extension flag set
        // by the erase-pixels path / Lane A4) instead of the hardcoded false.
        hasEditedImage={pageRecord?.extensions?.["labeler"]?.["has_edited_image"] === true}
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        pageSource={pageRecord?.extensions?.["labeler"]?.["page_source"] as any}
        // C2: surface the backend-assembled provenance one-liner so the source
        // badge tooltip is no longer blank (audit row 26).
        provenanceSummary={pageRecord?.provenance_summary ?? null}
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
    <Drawer
      lineMatches={lines}
      page={pagePayload ?? undefined}
      projectId={pid}
      pageIndex={idx0}
      className="border-l border-r-0"
      tabCounts={drawerTabCounts}
      pageTextGt={pagePayload?.page_text_gt}
      pageTextOcr={pagePayload?.page_text_ocr}
    />
  );

  const topToolbarSlot = (
    <div
      data-testid="project-top-toolbar"
      className="flex h-9 shrink-0 items-center justify-between gap-2 border-b border-border-1 bg-bg-surface px-2 text-xs"
      role="toolbar"
      aria-label="Page toolbar"
    >
      {/* C1: the mismatches-only toggle now lives in ImageTabsHeader (single
          source of truth); this slot keeps only the page indicator. */}
      <div className="flex items-center gap-2" />
      <div className="text-[11px] tabular-nums text-ink-3" data-testid="project-toolbar-page">
        Page {currentPageNo} / {Math.max(totalPages, 1)}
      </div>
    </div>
  );

  // IS-4: Canvas slot stripped to image-only layout.
  // ToolbarActionGrid, Splitter, TextTabs, WordMatchView removed from visible
  // canvas. TextTabs/WordMatchView and ToolbarActionGrid kept as hidden stubs
  // to preserve driver-contract testids (§2.7, §2.8, §2.9, §2.10).
  // C1: ImageTabsHeader viewport chrome — layer toggles, selection-mode radios,
  // Erase Pixels toggle, color legend, mismatches-only toggle, zoom buttons.
  // Bound to the SAME useUiPrefs (layer visibility + selection mode) and
  // viewportStore (erase mode) the Rail uses so the two chrome surfaces share
  // a single source of truth. (Previously built but never mounted — only
  // commented out at the top of this file.)
  const headerLayerVisibility: HeaderLayerVisibility = {
    paragraph: uiPrefs.layerVisibility.paragraph,
    line: uiPrefs.layerVisibility.line,
    word: uiPrefs.layerVisibility.word,
  };
  const imageTabsHeaderSlot = (
    <ImageTabsHeader
      layerVisibility={headerLayerVisibility}
      selectionMode={uiPrefs.selectionMode}
      eraseActive={viewportMode === "erase"}
      onLayerToggle={(layer) => {
        useUiPrefs.setState((prefs) => ({
          layerVisibility: {
            ...prefs.layerVisibility,
            [layer]: !prefs.layerVisibility[layer],
          },
        }));
        // The page's `uiPrefs` snapshot is bridged through the local
        // `notifyUiPrefs` listener set (see top of file), not the store's
        // native subscribe. Without this notify the controlled checkbox
        // `checked={layerVisibility[layer]}` never re-renders. (M-Final V4.)
        notifyUiPrefs();
      }}
      onSelectionModeChange={(mode) => {
        useUiPrefs.setState({ selectionMode: mode });
        // SEL-3: keep railStore.target in sync so the canvas reads the same
        // granularity as the header radios. "paragraph" maps to "para" since
        // the rail uses the canonical RailTarget names.
        const railTarget = mode === "paragraph" ? "para" : (mode as "line" | "word");
        railStore.getState().setTarget(railTarget);
        // Same bridge as onLayerToggle: notify so the selection-mode radio
        // re-renders to reflect the new mode. (M-Final V4.)
        notifyUiPrefs();
      }}
      onEraseToggle={() => {
        toggleEraseMode();
      }}
      onZoomFit={() => {
        setCanvasZoom(0);
      }}
      onZoom100={() => {
        setCanvasZoom(1);
      }}
      matchFilterMode={uiPrefs.matchFilterMode}
      onMatchFilterModeToggle={() => {
        useUiPrefs.setMatchFilterMode(
          uiPrefs.matchFilterMode === "all" ? "mismatches_only" : "all",
        );
        notifyUiPrefs();
      }}
      // D5: add-word affordance outside the grid. Reuses Lane B's wiring —
      // handleAddWordToggle calls viewportStore.toggleAddWordMode(), and the
      // draw→words/add handler (handleAddWord) is already bound on the canvas.
      addWordActive={addWordActive}
      onAddWordToggle={handleAddWordToggle}
    />
  );

  const canvasSlot = (
    <div className="flex flex-col h-full min-h-0">
      {topToolbarSlot}
      {imageTabsHeaderSlot}
      {/* D3: page validate-all/unvalidate-all + multi-select word bulk ops. */}
      <div className="shrink-0 border-b border-border-1 bg-bg-surface">
        <BulkWordActions projectId={pid} pageIndex={idx0} />
      </div>
      <div data-testid="image-pane" className="relative flex-1 min-h-0">
        <BusyOverlay activeJob={activeJob} isMutating={isMutating} />
        <PageImageCanvas
          imageUrl={pagePayload?.image_url ?? ""}
          encoded={pagePayload?.encoded_dims ?? null}
          page={pagePayload}
          projectId={projectId}
          pageIndex={idx0}
          onBoxSelect={handleBoxSelect}
          onAddWord={handleAddWord}
          onRebox={handleRebox}
        />
      </div>
      <div data-testid="inline-banners" className="flex flex-col gap-1 p-1">
        <OcrFailedBanner ocrFailed={pageRecord?.ocr_failed === true} />
        <ImageDriftBanner imageDrift={false} />
      </div>

      {/*
       * GRID-1 (Slice C): ToolbarActionGrid — visible collapsible bar.
       *
       * Previously hidden inside canvas-hidden-stubs. Now mounted visibly
       * above the image-pane. All existing data-testids are preserved per
       * driver-contract §2.9/§2.10. Collapsed state persisted in uiPrefs
       * (toolbarGridCollapsed, default = false = expanded).
       */}
      <div className="shrink-0 border-b border-border-1 bg-bg-surface">
        <div className="flex items-center justify-between px-2 py-0.5">
          <span className="text-[11px] font-medium text-ink-2">Actions</span>
          <button
            data-testid="toolbar-grid-collapse"
            aria-label={uiPrefs.toolbarGridCollapsed ? "Expand actions" : "Collapse actions"}
            aria-expanded={!uiPrefs.toolbarGridCollapsed}
            className="flex items-center justify-center rounded p-0.5 text-ink-3 hover:bg-bg-1 hover:text-ink-1"
            onClick={() => {
              useUiPrefs.setState({ toolbarGridCollapsed: !uiPrefs.toolbarGridCollapsed });
              notifyUiPrefs();
            }}
          >
            {uiPrefs.toolbarGridCollapsed ? (
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <polyline points="6 9 12 15 18 9" />
              </svg>
            ) : (
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <polyline points="18 15 12 9 6 15" />
              </svg>
            )}
          </button>
        </div>
        {!uiPrefs.toolbarGridCollapsed && (
          <div data-testid="toolbar-grid-body" className="px-1 pb-1">
            <ToolbarActionGrid
              selection={toolbarSelection}
              pageData={toolbarPageData}
              onAction={handleToolbarAction}
              onApplyStyle={handleApplyStyle}
              onClearStyle={handleClearStyle}
              onApplyComponent={handleApplyComponent}
              onClearComponent={handleClearComponent}
              addWordActive={addWordActive}
              onAddWordToggle={handleAddWordToggle}
            />
          </div>
        )}
      </div>

      {/*
       * IS-4: Driver-contract testid preservation stubs.
       *
       * §2.7: TextTabs testids (text-tab-*, match-filter-*) must remain.
       * §2.8: WordMatchView per-line/per-word testids must remain.
       *
       * ToolbarActionGrid (§2.9/§2.10) is now visible above — no longer
       * needs to live in this hidden container.
       */}
      <div style={{ display: "none" }} data-testid-stub="canvas-hidden-stubs">
        <div data-testid="text-pane">
          <TextTabs
            pageTextGt={pagePayload?.page_text_gt}
            pageTextOcr={pagePayload?.page_text_ocr}
            lineFilter={uiPrefs.matchFilter}
            onLineFilterChange={(f) => {
              setMatchFilter(f);
            }}
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
      onCollapse={() => {
        useUiPrefs.setState({ rightPanelOpen: false });
      }}
    />
  ) : null;
  const rightWidth = selectionLevel === "line" || selectionLevel === "block" ? 640 : 520;

  return (
    <div data-testid="project-page" className="h-full">
      <ProjectLoadingOverlay isLoading={isPageLoading} />

      <div
        data-testid="project-workspace"
        className="grid h-full min-h-0 bg-bg-page"
        style={{
          gridTemplateColumns: `minmax(0, 1fr) ${drawerOpen ? "320px" : "32px"} ${
            rightPanelOpen ? `${rightWidth}px` : "0px"
          }`,
        }}
      >
        <div data-testid="project-canvas-column" className="min-w-0 min-h-0 overflow-hidden">
          {canvasSlot}
        </div>
        <div data-testid="project-worklist-column" className="min-w-0 min-h-0 overflow-hidden">
          {drawerSlot}
        </div>
        <div data-testid="project-detail-column" className="min-w-0 min-h-0 overflow-hidden">
          {rightSlot}
        </div>
      </div>

      {/* IS-2: hidden PageActions for driver-contract testid preservation §2.5 */}
      {hiddenPageActions}

      {/* WordEditDialog — opens from per-word pencil click via dialogStore.
          Returns null when open=false, so the dialog testids only appear
          when the user opens it.
          S1.2: All mutation callbacks wired (WED-1..WED-9). */}
      <WordEditDialog
        open={wordEditState.open}
        target={dialogTarget}
        lineWords={dialogLineWords}
        wordImageUrl={pagePayload?.image_url ?? undefined}
        wordBBox={
          pagePayload
            ? (findWordByIndex(pagePayload, dialogTarget.lineIndex, dialogTarget.wordIndex)?.bbox ??
              undefined)
            : undefined
        }
        encodedScale={pagePayload?.encoded_dims?.scale ?? undefined}
        gtText={
          pagePayload
            ? (findWordByIndex(pagePayload, dialogTarget.lineIndex, dialogTarget.wordIndex)
                ?.ground_truth_text ?? "")
            : ""
        }
        onGtChange={() => {}}
        onGtCommit={(text) => {
          updateGtWord.mutate({
            lineIndex: dialogTarget.lineIndex,
            wordIndex: dialogTarget.wordIndex,
            text,
          });
        }}
        onMerge={(dir) =>
          mergeWord
            .mutateAsync({
              lineIndex: dialogTarget.lineIndex,
              wordIndex: dialogTarget.wordIndex,
              direction: dir === "prev" ? "left" : "right",
            })
            .then(() => {})
        }
        onSplit={(fraction, axis) => {
          if (axis === "v") return Promise.resolve(); // backend returns 400 for v-split (words.py:1080)
          return splitWord
            .mutateAsync({
              lineIndex: dialogTarget.lineIndex,
              wordIndex: dialogTarget.wordIndex,
              xFraction: fraction,
              direction: "horizontal",
            })
            .then(() => {});
        }}
        onDelete={() =>
          deleteWord
            .mutateAsync({
              lineIndex: dialogTarget.lineIndex,
              wordIndex: dialogTarget.wordIndex,
            })
            .then(() => {
              dialogStore.close("wordEdit");
            })
        }
        onCrop={(dir, padding) => {
          const w = pagePayload
            ? findWordByIndex(pagePayload, dialogTarget.lineIndex, dialogTarget.wordIndex)
            : null;
          if (!w) return Promise.resolve();
          const b = { ...w.bbox };
          if (dir === "left") {
            b.x += padding;
            b.width -= padding;
          }
          if (dir === "right") {
            b.width -= padding;
          }
          if (dir === "above") {
            b.y += padding;
            b.height -= padding;
          }
          if (dir === "below") {
            b.height -= padding;
          }
          return reboxWord
            .mutateAsync({
              lineIndex: dialogTarget.lineIndex,
              wordIndex: dialogTarget.wordIndex,
              bbox: b,
            })
            .then(() => {});
        }}
        onRefine={() =>
          nudgeWord
            .mutateAsync({
              lineIndex: dialogTarget.lineIndex,
              wordIndex: dialogTarget.wordIndex,
              left: 0,
              right: 0,
              top: 0,
              bottom: 0,
              refineAfter: true,
            })
            .then(() => {})
        }
        onExpandRefine={() =>
          nudgeWord
            .mutateAsync({
              lineIndex: dialogTarget.lineIndex,
              wordIndex: dialogTarget.wordIndex,
              left: 4,
              right: 4,
              top: 4,
              bottom: 4,
              refineAfter: true,
            })
            .then(() => {})
        }
        onApplyNudge={(n, refineAfter) =>
          nudgeWord
            .mutateAsync({
              lineIndex: dialogTarget.lineIndex,
              wordIndex: dialogTarget.wordIndex,
              left: n.left,
              right: n.right,
              top: n.top,
              bottom: n.bottom,
              refineAfter,
            })
            .then(() => {})
        }
        onApplyStyle={(style, scope) =>
          applyStyle
            .mutateAsync({
              lineIndex: dialogTarget.lineIndex,
              wordIndex: dialogTarget.wordIndex,
              style,
              scope,
            })
            .then(() => {})
        }
        onApplyComponent={(component, enabled) =>
          applyComponent
            .mutateAsync({
              lineIndex: dialogTarget.lineIndex,
              wordIndex: dialogTarget.wordIndex,
              component,
              enabled,
            })
            .then(() => {})
        }
        onNavigate={(t) => {
          dialogStore.openWordEdit({ lineIdx: t.lineIndex, wordIdx: t.wordIndex });
        }}
        onApply={() => {
          invalidatePage();
          dialogStore.close("wordEdit");
        }}
        onClose={() => {
          dialogStore.close("wordEdit");
        }}
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
        onCancel={() => {
          dialogStore.close("confirm");
        }}
      />
    </div>
  );
}

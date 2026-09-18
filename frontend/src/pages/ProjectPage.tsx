// ProjectPage.tsx — real labeling shell.
//
// Spec: specs/22-page-surface-wireup.md §3 (Layout), §4 (Data flow),
//       §10 (Driver-contract preservation), §11 (Notifications).
// Issue #314 (spec-22-C).
//
// Implements the full §3 layout:
//
//   <ProjectPage>
//     <ProjectLoadingOverlay />
//     <PageHeader>
//       <ProjectNavigationControls />
//     </PageHeader>
//     <ToolbarActionGrid />
//     <Splitter direction="horizontal">
//       <LeftPane data-testid="image-pane">
//         (ImageTabsHeader retired D-050/D-053)
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
//     <ConfirmDialog />
//   </ProjectPage>
//
// The legacy `display:none` testid stubs (nav-* and source-folder-*) moved
// to HeaderBar so they remain reachable from every route while the real
// ProjectNavigationControls renders here without `data-testid-stub`.
//
// Data flow:
//   - `useProject(projectId)` and `usePage(projectId, idx0)` drive the surface.
//   - Mutation hooks (page actions, right-panel word edits, …) invalidate
//     `["page", projectId, idx0]` so usePage re-fetches.
//   - `useJobProgress` feeds the BusyOverlay.
//
// Hook-order discipline: ALL hooks are called unconditionally at the top
// before any early return, matching the Rules of Hooks.

import { useMemo, useRef, useState, useSyncExternalStore, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "../lib/toast";

import { useProject } from "../hooks/useProject";
import { usePage } from "../hooks/usePage";
import { useJobProgress } from "../hooks/useJobProgress";
import { useJobCompletionInvalidation } from "../hooks/useJobCompletionInvalidation";
import { useBboxRefineTracking } from "../hooks/useBboxRefineTracking";
import {
  useReloadOcr,
  useReloadOcrEdited,
  useReloadOcrEditedPending,
  useSavePage,
  useSaveProject,
  useLoadPage,
  useRematchGt,
  useRotatePage,
  useUndoPage,
  useRedoPage,
  useErasePagePixels,
} from "../hooks/usePageMutations";
import {
  useValidateLine,
  useCopyLineGt,
  useDeleteLine,
  useMergeLines,
} from "../hooks/useLineMutations";
import { useApplyComponent, useAddWord, useReboxWord } from "../hooks/useWordMutations";
// Lane D reuses `toggleAddWordMode` / `exitToSelectMode` (viewport-store
// helpers) + the `handleAddWord` handler below to add an add-word button
// outside the toolbar grid without duplicating the mutation wiring.
import { viewportStore, toggleAddWordMode } from "../stores/viewport-store";
import { displayToSrc } from "../lib/coords";
import { applyBoxSelect } from "../lib/box-select-handler";
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
  applyLineSelection,
  applyParagraphSelection,
  promoteCompleteWordLines,
  selectProposal,
  useSelectionForPage,
  selectWord,
} from "../stores/selection-store";
import {
  reviewSelectionIntentStore,
  clearReviewSelectionIntent,
} from "../stores/review-selection-intent-store";
import { worklistStore } from "../stores/worklist-store";
import { focusWorklistLine } from "../stores/worklist-focus";
import { pageNoUrl } from "../lib/routes";
import { getLabelerExtension } from "../lib/labelerExtension";

import { PageActionsCompact } from "../components/PageActionsCompact";
import ProjectNavigationControls, {
  type ProjectNavigationControlsHandle,
} from "../components/ProjectNavigationControls";
import { Drawer } from "../components/shell/Drawer";
import { WorkspaceToolbar } from "../components/shell/WorkspaceToolbar";
import { WorkspaceMetrics, type PageMetrics } from "../components/shell/WorkspaceMetrics";
import { QuickSearch, type QuickSearchHandle } from "../components/shell/QuickSearch";
import { useHotkey } from "../hooks/useHotkey";
import { ToolbarActionGrid } from "../components/ToolbarActionGrid";
import { BulkWordActions } from "../components/BulkWordActions";
import { BusyOverlay, ProjectLoadingOverlay } from "../components/BusyOverlay";
import { PageLoadStatus } from "../components/PageLoadStatus";
import PageImageCanvas from "../components/PageImageCanvas";
import { OcrFailedBanner, ImageDriftBanner } from "../components/InlineBanners";
import { TextTabs } from "../components/TextTabs";
import { WordMatchView } from "../components/WordMatchView";
import { PlaintextEditor } from "../components/PlaintextEditor";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { RightPanel } from "../components/shell/RightPanel";
import { WordDetail } from "../components/right-panel/WordDetail";
import { useBreadcrumbHotkeys } from "../hooks/useBreadcrumbHotkeys";
import { useRegionReviewHotkeys } from "../hooks/useRegionReviewHotkeys";
import { useReviewQueue } from "../hooks/useReviewQueue";

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
  // Wave 3a / P1-JOB-TYPE: every SSE frame is now the full public `Job`
  // model, so `jobProgress.type` is the real job kind straight from the
  // backend — no need to separately track or guess it for BusyOverlay's
  // cancel policy (previously synthesized as a hard-coded placeholder).
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const jobProgress = useJobProgress(activeJobId);

  // ── On-demand page-OCR job (2026-08-08-page-load-progress) ──────────────
  // A store miss on `GET .../pages/{idx}` no longer blocks the request: the
  // response returns immediately with `page_load_job_id` set and a
  // `load_page` job running. `pageLoadJobId` is derived straight from the
  // fetched payload (not component state) — a store hit never sets the
  // field, so this is null (and `useJobProgress` opens no EventSource) on
  // the ordinary warm-page path. `PageLoadStatus` renders the stages in the
  // page region only; see its module doc for why it must not reuse
  // `BusyOverlay`'s full-viewport treatment.
  const pageLoadJobId = pageQ.data?.page_load_job_id ?? null;
  const pageLoadJob = useJobProgress(pageLoadJobId);

  // ── BBoxSection's refine_bboxes job tracker (review finding 3) ──────────
  // Owned here, not inside WordDetail/BBoxSection: BBoxSection's own
  // Accordion.Content unmounts when the "Bounding Box" item collapses, and
  // WordDetail itself unmounts whenever the selection drops back to "none"
  // (deselecting the word) — either would drop the terminal SSE event if
  // the tracker lived there. ProjectPage is the only component in this
  // subtree that stays mounted for the whole project-page session, matching
  // how it already owns `activeJobId` above for every other job type here.
  // A dedicated slot (not reusing `activeJobId`): bbox refine is scoped to
  // a dynamic word rather than a fixed action type, and `activeJobId` is
  // already a single shared slot several unrelated toolbar actions use —
  // reusing it here would let one steal the slot from the other mid-run.
  const bboxRefine = useBboxRefineTracking(projectId, idx0);

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
  // P2-SELECTION-PAGE: resolved against `idx0` (the loaded page) — a
  // block/para/line/word selection made on another page must not feed
  // ToolbarActionGrid batch actions or the style/component-apply buttons
  // below (`selectedWordTargets`) against the CURRENTLY loaded page's data.
  // Before this fix those read `selectionStore.getState()` directly, so a
  // toolbar action taken after paging away from where the selection was
  // made could silently mutate the wrong page's lines/words.
  const selection = useSelectionForPage(idx0);
  const selectionLevel = selection.level;
  // B2: add-word mode mirrors viewportStore (single source of truth).
  const addWordActive = useSyncExternalStore(
    subscribeViewportMode,
    getAddWordActiveSnapshot,
    getAddWordActiveSnapshot,
  );
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

  // ── Page-load job completion → refetch the page (2026-08-08) ───────────
  // `pageLoadJobId` is derived from the fetched payload rather than tracked
  // component state (see its declaration above), so it is not a fit for
  // `useJobCompletionInvalidation`'s `setActiveJobId` contract — there is no
  // local state to clear. Once the job's terminal `complete` event arrives,
  // the words it produced only exist in the store; refetching is what makes
  // them appear (design acceptance criterion "re-fetch the page when the job
  // completes"). Deliberately does NOT invalidate on `error` /
  // `cancelled` — `PageLoadStatus` renders the terminal error in place, and
  // a refetch would just reproduce the same store miss and submit a fresh
  // job.
  useEffect(() => {
    if (pageLoadJobId && pageLoadJob?.status === "complete") {
      void qc.invalidateQueries({ queryKey: ["page", projectId, idx0] });
    }
  }, [pageLoadJobId, pageLoadJob?.status, projectId, idx0, qc]);

  // ── Mutations ──────────────────────────────────────────────────────────
  // `projectId` may be undefined on first render before the URL resolves;
  // mutations are stable hooks so we pass "" — the user can't trigger them
  // until the URL is real (PageActions is disabled while isBusy).
  const pid = projectId ?? "";
  const reloadOcr = useReloadOcr(pid, idx0);
  const reloadOcrEdited = useReloadOcrEdited(pid, idx0);
  // Shared across this instance and PageActionsCompact's own
  // useReloadOcrEdited instance — see the hook's docstring.
  const reloadOcrEditedPending = useReloadOcrEditedPending(pid, idx0);
  const savePage = useSavePage(pid, idx0);
  const saveProject = useSaveProject(pid);
  const loadPage = useLoadPage(pid, idx0);
  const rematchGt = useRematchGt(pid, idx0);
  const rotatePage = useRotatePage(pid, idx0);
  const undoPage = useUndoPage(pid, idx0);
  const redoPage = useRedoPage(pid, idx0);

  // ── Line mutations for useMatchesHotkeys (BUG-KBD-3) ──────────────────
  const validateLine = useValidateLine(pid, idx0);
  const copyLineGt = useCopyLineGt(pid, idx0);
  const deleteLine = useDeleteLine(pid, idx0);
  const mergeLines = useMergeLines(pid, idx0);

  // ── Word mutations for the Apply-Style / Component / Add-Word controls (B2) ─
  const applyComponent = useApplyComponent(pid, idx0);
  const addWord = useAddWord(pid, idx0);

  // ── Word mutations shared by canvas and right-panel controls ─────────────
  const reboxWord = useReboxWord(pid, idx0);

  // ── Canvas erase mode (P1-CANVAS-ERASE) ───────────────────────────────
  const erasePagePixels = useErasePagePixels(pid, idx0);
  // In-flight guard for handleErasePixels, scoped to the (projectId,
  // pageIndex) it targets — see its docstring for why a page-agnostic
  // boolean is wrong here.
  const erasingTargetRef = useRef<{ projectId: string; pageIndex: number } | null>(null);

  // ── Derived view state ─────────────────────────────────────────────────
  const pagePayload = pageQ.data ?? null;
  const lines: LineMatch[] = pagePayload?.line_matches ?? [];
  // Event-store undo (spec 2026-06-12): availability flags from the payload.
  const undoAvailable = pagePayload?.history?.undo_available === true;
  const redoAvailable = pagePayload?.history?.redo_available === true;

  // D-047: per-page match metrics for the WorkspaceToolbar rightSlot (moved
  // out of the chrome header). Derived from the page payload's word matches.
  const pageMetrics: PageMetrics | null = useMemo(() => {
    const lineMatches = pagePayload?.line_matches ?? null;
    if (!lineMatches) return null;
    const words = lineMatches.flatMap((l) => l.word_matches);
    const total = words.length;
    if (total === 0) return null;
    return {
      total,
      exact: words.filter((w) => w.match_status === "exact").length,
      fuzzy: words.filter((w) => w.match_status === "fuzzy").length,
      mismatch: words.filter((w) => w.match_status === "mismatch").length,
      validated: words.filter((w) => w.is_validated).length,
      glyphs_reviewed: words.filter((w) => w.glyph_annotations != null).length,
    };
  }, [pagePayload]);

  // ── Breadcrumb / hierarchy hotkeys (Alt+arrows) ────────────────────────
  // Registered at the page level so they work anywhere on the project page.
  useBreadcrumbHotkeys({ page: pagePayload ?? undefined });

  // ── Region review hotkeys (n/p/enter/x/delete) ──────────────────────────
  // Registered at the page level, same as useBreadcrumbHotkeys above. A
  // proposal or confirmed region can only be selected once a page has
  // loaded, so the `projectId ?? ""` fallback below is never exercised by
  // an actual mutation — it only keeps the hook's required `string` prop
  // satisfied before the route param resolves.
  useRegionReviewHotkeys({
    page: pagePayload ?? undefined,
    projectId: projectId ?? "",
    pageIndex: idx0,
    navigate,
  });

  // Book review queue design ("A count stays visible" / Queue drawer tab):
  // limit=0 so this carries only total_undecided and the page summary — the
  // Queue tab's own count badge, same shape Rail.tsx's badge reads. The
  // Queue tab's item list is fetched separately, by ReviewQueuePanel itself.
  const reviewQueueQ = useReviewQueue(projectId);

  // ── Region selection scoping (whole-branch review defect 2) ────────────
  // A region or proposal id belongs to the page it was selected on. Nothing
  // else cleared it on navigation, so `enter` on a new page could fire an
  // accept against the new page's URL carrying the old page's proposal id.
  // Clear only the region level on a page-index change — word, line,
  // paragraph and block selections predate this fix, and whether they share
  // the same latent problem is a separate question this fix does not
  // resolve (see the region review guards report).
  const prevPageIndexRef = useRef(idx0);
  useEffect(() => {
    if (prevPageIndexRef.current !== idx0) {
      if (selectionStore.getState().level === "region") {
        clearSelection();
      }
      prevPageIndexRef.current = idx0;
    }
  }, [idx0]);

  // ── Review-queue selection intent (book review queue design: "Selecting
  // after navigation needs an intent, not a direct call") ─────────────────
  // '['/']' in useRegionReviewHotkeys record {pageIndex, proposalId} in
  // reviewSelectionIntentStore before navigating — a store the page-change
  // clear above does not touch, since the destination page's payload has
  // not loaded at the moment the key fires and there is nothing to select
  // against yet. This effect applies the intent once the current page's
  // payload matches it.
  //
  // Ordering: this effect is declared AFTER the page-change clear above, so
  // React flushes both in source order within one commit. That matters for
  // the case where the destination page's payload is already cached (e.g. a
  // revisited page) — both effects then run in the SAME render, and if the
  // clear ran second it would wipe the selection this effect just made. With
  // it declared first, the clear always resolves before the intent is
  // applied, so it never undoes it. Moving this effect above the clear (or
  // merging them) would reintroduce that bug — keep this order.
  // ProjectPage.pageChange.test.tsx's "same-commit ordering" test fails if
  // this effect is moved above the clear — verified while writing it.
  //
  // Abandoning the intent (finding 1, medium): the intent used to be
  // consumed only when idx0 happened to equal intent.pageIndex, and was
  // never cleared otherwise. So pressing ']' (intent for page 7), then
  // navigating elsewhere with ordinary prev/next before page 7 loaded, left
  // the intent pending indefinitely — later reaching page 7 through normal
  // navigation silently auto-selected that proposal. `prevIdx0Ref` tracks
  // the previous idx0 so this effect can tell a genuine navigation (idx0
  // actually changed) apart from a re-run triggered only by `pagePayload`
  // changing at the same idx0 (e.g. the destination page's fetch resolving).
  // Only a genuine navigation that lands somewhere other than the intent's
  // own pageIndex abandons it — the navigation ']' itself triggers (which
  // changes idx0 TO intent.pageIndex) must not clear the intent it just set.
  const prevIdx0Ref = useRef(idx0);
  useEffect(() => {
    const idx0Changed = prevIdx0Ref.current !== idx0;
    prevIdx0Ref.current = idx0;

    const intent = reviewSelectionIntentStore.getState().intent;
    if (!intent) return;

    if (idx0Changed && intent.pageIndex !== idx0) {
      clearReviewSelectionIntent();
      return;
    }
    if (intent.pageIndex !== idx0) return;
    if (!pagePayload) return; // destination page not loaded yet — wait
    const isUndecided = (pagePayload.regions ?? []).some(
      (r) => !r.confirmed && r.proposal_id === intent.proposalId,
    );
    if (isUndecided) {
      selectProposal(intent.proposalId);
    }
    clearReviewSelectionIntent();
  }, [idx0, pagePayload]);

  // ── ⌘K QuickSearch (D-047) ─────────────────────────────────────────────
  // QuickSearch relocated from the chrome header into the Drawer worklist
  // header (it filters the worklist, which lives in the drawer). The Mod+K
  // global hotkey still focuses the input — behavior preserved exactly.
  const quickSearchRef = useRef<QuickSearchHandle>(null);
  useHotkey("mod+k", () => {
    quickSearchRef.current?.focusInput();
  });

  // BUG-KBD-5 (docs/plans/2026-07-21-open-findings-fixes.md): Mod+J focuses
  // the page-number input, same forwardRef pattern as Mod+K/QuickSearch above.
  // Wired via useGlobalHotkeys below (onJumpToPage).
  const navControlsRef = useRef<ProjectNavigationControlsHandle>(null);

  // ── Global hotkeys (BUG-KBD-2) ─────────────────────────────────────────
  // Wired here at the page level so Mod+S, Mod+ArrowLeft/Right, etc. are
  // active whenever the project page is mounted. Page-navigation handlers
  // read projectQ.data so they stay current without needing state.
  // `isAnyMutationPending` is computed here (before isMutating below) from
  // the already-declared mutation hooks so useGlobalHotkeys receives a value
  // in the same render pass.
  //
  // 2026-09-17 review finding: while a `load_page` job is in flight,
  // `pagePayload` has no `page_record` / `line_matches` yet (see
  // `pageLoadJobId` above) — the same "nothing to act on" state any other
  // pending mutation represents. Without `pageLoadJobId` here, Mod+S / Mod+R
  // etc. stayed live and fired against that empty payload. Gated the same
  // way as every other in-flight mutation.
  const isAnyMutationPending =
    reloadOcr.isPending ||
    reloadOcrEditedPending ||
    savePage.isPending ||
    saveProject.isPending ||
    loadPage.isPending ||
    rematchGt.isPending ||
    undoPage.isPending ||
    redoPage.isPending ||
    pageLoadJobId !== null;
  const totalPages = projectQ.data?.image_paths?.length ?? 0;
  const currentPageNo = idx0 + 1;
  useGlobalHotkeys({
    disabled: isAnyMutationPending,
    onSavePage: handleSavePage,
    onSaveProject: handleSaveProject,
    onReloadOcr: handleReloadOcr,
    onReloadOcrEdited: handleReloadOcrEdited,
    onLoadPage: handleLoadPage,
    onRematchGt: handleRematchGt,
    onExport: handleExport,
    onJumpToPage: () => navControlsRef.current?.focusPageInput(),
    onUndo: handleUndo,
    onRedo: handleRedo,
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

  // ── Matches hotkeys (BUG-KBD-3, P1-MATCH-NAV) ───────────────────────────
  // Wired at the page level — operates on worklistStore.selectedLineIndex to
  // know which line is "current" for all action hotkeys (V/U/D/O/G/M/R).
  // onLineNav calls the same `focusWorklistLine` helper a Worklist row click
  // uses, so J/K keep the canvas / breadcrumb / right panel (selectionStore)
  // in sync with the worklist highlight instead of moving only the queue
  // pointer (P1-MATCH-NAV). With no lines on the page there is nothing to
  // navigate to or select, so J/K are a no-op rather than focusing a line
  // index that does not exist.
  useMatchesHotkeys({
    onLineNav: (delta) => {
      if (lines.length === 0) return;
      const { selectedLineIndex } = worklistStore.getState();
      const nextIdx = (selectedLineIndex ?? -1) + delta;
      const clampedIdx = Math.max(0, Math.min(lines.length - 1, nextIdx));
      focusWorklistLine(idx0, clampedIdx);
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
      dispatchToolbarAction("line_refine");
    },
    onExpandRefine: () => {
      dispatchToolbarAction("line_expand_refine");
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

  // Show ProjectLoadingOverlay only while the PROJECT itself is loading
  // (2026-08-08-page-load-progress defect 3). It used to track
  // `pageQ.isLoading`, which kept the full-viewport "Loading project"
  // overlay up for the entire page fetch — including the up-to-30s OCR
  // wait that now runs as a `load_page` job — mislabelling that wait and
  // blocking the whole shell (rail, page list, panels) for it. Project open
  // is genuinely a whole-view wait (design "Project open is a whole-view
  // wait, and it is over in milliseconds"), so it keeps the full-overlay
  // treatment; the page-load wait gets `PageLoadStatus` in the page region
  // instead (see its render below).
  const isProjectLoading = projectQ.isLoading;

  // Busy state — any mutation in flight OR an active job. Drives
  // `BusyOverlay`, which is `fixed inset-0` (full viewport). Deliberately
  // does NOT include `pageLoadJobId`, unlike `isAnyMutationPending` above:
  // folding it in here would put the full-viewport overlay back up for the
  // page-load wait, which is exactly the shell-blocking behavior
  // `PageLoadStatus` (scoped to `image-pane` only) replaced — see
  // `isProjectLoading`'s comment. The hotkey gate and the overlay gate serve
  // different ends: one guards against acting on an empty payload, the
  // other is a visibility choice about how much of the shell a wait covers.
  const isMutating =
    reloadOcr.isPending ||
    reloadOcrEditedPending ||
    savePage.isPending ||
    saveProject.isPending ||
    loadPage.isPending ||
    rematchGt.isPending ||
    rotatePage.isPending ||
    undoPage.isPending ||
    redoPage.isPending;

  // `jobProgress` is now every SSE frame's full public `Job` model plus the
  // `event` field (see useJobProgress.ts) — structurally a `Job` already, so
  // BusyOverlay's `activeJob` needs no synthesis (previously a hard-coded
  // placeholder type — P1-JOB-TYPE). `null` once the job reaches a terminal
  // status.
  const activeJob: components["schemas"]["Job"] | null =
    jobProgress &&
    jobProgress.status !== "complete" &&
    jobProgress.status !== "error" &&
    jobProgress.status !== "cancelled"
      ? jobProgress
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

  // ── Action callbacks ───────────────────────────────────────────────────
  // Mutations return job_ids for async actions; we route those into
  // useJobProgress and invalidate on completion. Synchronous mutations
  // invalidate the page query directly.

  function invalidatePage() {
    void qc.invalidateQueries({ queryKey: ["page", projectId, idx0] });
  }

  function trackJob(result: { job_id?: string | null } | undefined | null) {
    const jobId = result?.job_id ?? null;
    if (jobId) {
      setActiveJobId(jobId);
    }
  }

  // U-6 (spec 2026-06-12-event-store-undo): re-OCR creates a NEW page
  // aggregate, so the undo history restarts. The confirm dialog must warn.
  // Mod+R wires to this via useGlobalHotkeys (D-050: button is in
  // PageActionsCompact; hotkey is retained here so keyboard shortcut works
  // globally even without the button in focus).
  const reloadOcrConfirmBody =
    "This will re-run OCR for the current page and the page's edit history resets — Undo will not step back across this reload.";
  function handleReloadOcr() {
    dialogStore.openConfirm({
      title: "Reload OCR?",
      body: reloadOcrConfirmBody,
      onConfirm: () => {
        reloadOcr.mutate(undefined, {
          onSuccess: (data) => {
            trackJob(data as { job_id?: string | null } | undefined | null);
          },
          onSettled: () => {
            invalidatePage();
          },
        });
      },
    });
  }
  // BUG-KBD-1 sibling (docs/plans/2026-07-21-open-findings-fixes.md): Mod+Shift+R
  // wires to this via useGlobalHotkeys, same "hotkey works globally, button
  // lives in PageActionsCompact" reasoning as Mod+R above. `hasEditedImage`
  // mirrors PageActionsCompact.tsx's own gate on the "Reload OCR (Edited)"
  // overflow-menu item (`disabled={disabled || !hasEditedImage}`) — firing
  // this with no edited image to reload would re-run plain OCR under a
  // misleading "(edited)" confirm, so the hotkey is a no-op instead.
  const hasEditedImage = getLabelerExtension(pagePayload?.page_record).has_edited_image === true;
  function handleReloadOcrEdited() {
    if (!hasEditedImage) return;
    dialogStore.openConfirm({
      title: "Reload OCR (edited image)?",
      body: reloadOcrConfirmBody,
      onConfirm: () => {
        reloadOcrEdited.mutate(undefined, {
          onSuccess: (data) => {
            trackJob(data);
          },
          onSettled: () => {
            invalidatePage();
          },
        });
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
  //
  // U-7 (spec 2026-06-12-event-store-undo): "Load Page" is now "Reload" —
  // every mutation auto-persists to the event-store head, so there are no
  // unsaved edits to discard; the confirm copy must not claim otherwise.
  function handleLoadPage() {
    dialogStore.openConfirm({
      title: "Reload page?",
      body: "This will refresh the page from the latest stored version. Edits are saved automatically — use Undo to step back through page history.",
      onConfirm: () => {
        loadPage.mutate(undefined, {
          onSettled: () => {
            invalidatePage();
          },
        });
      },
    });
  }
  // Event-store undo (U-1/U-2): guard on the payload's availability flags so
  // the Mod+Z/Mod+Shift+Z hotkeys are no-ops at the history bounds (U-3).
  function handleUndo() {
    if (!undoAvailable) return;
    undoPage.mutate(undefined, {
      onSettled: () => {
        invalidatePage();
      },
    });
  }
  function handleRedo() {
    if (!redoAvailable) return;
    redoPage.mutate(undefined, {
      onSettled: () => {
        invalidatePage();
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

  // P1.4 (B-39): clearing REMOVES the selected style via enabled:false.
  // The old behavior applied "regular" — a silent no-op, because
  // pdomain-book-tools' `apply_style_scope` is add-only and discards "regular".
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
    const boxSelection = applyBoxSelect(pagePayload, rect, modifier, railStore.getState().target);
    const hasHits =
      boxSelection.words.length > 0 ||
      boxSelection.lines.length > 0 ||
      boxSelection.paragraphs.length > 0;
    if (!hasHits) {
      if (modifier === "replace") clearSelection();
      return;
    }

    if (boxSelection.lines.length > 0) {
      applyLineSelection(pagePayload.page_index, boxSelection.lines, modifier);
      useUiPrefs.setState({ rightPanelOpen: true });
      return;
    }

    if (boxSelection.paragraphs.length > 0) {
      applyParagraphSelection(pagePayload.page_index, boxSelection.paragraphs, modifier);
      useUiPrefs.setState({ rightPanelOpen: true });
      return;
    }

    // Apply toggleWord per word so accumulation logic is consistent with
    // single-click (SEL-4/SEL-5 uses the same toggleWord primitive).
    if (modifier === "replace") {
      // First word replaces, subsequent words toggle-in (all new → add).
      const [first, ...rest] = boxSelection.words;
      if (!first) return;
      const [firstLine, firstWord] = first;
      toggleWord(pagePayload.page_index, firstLine, firstWord, "replace");
      for (const [lineIdx, wordIdx] of rest) {
        toggleWord(pagePayload.page_index, lineIdx, wordIdx, "toggle");
      }
    } else {
      for (const [lineIdx, wordIdx] of boxSelection.words) {
        toggleWord(pagePayload.page_index, lineIdx, wordIdx, modifier);
      }
    }
    promoteCompleteWordLines(pagePayload);
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

  // P1-CANVAS-ERASE: a completed erase draw. `rect` is in display pixels;
  // convert to source pixels before POSTing to .../pages/{idx}/erase-pixels.
  // Uses the same fill value (255) and "rect" shape the right-panel
  // ErasePixelsSection sends for its rect tool (useErasePixels,
  // useWordMutations.ts).
  //
  // Guarded by `erasingTargetRef` — a ref holding the {projectId, pageIndex}
  // of the in-flight request, flipped synchronously before `mutate()` and
  // cleared in `onSettled` — rather than `erasePagePixels.isPending`:
  // PageImageCanvas resets to "select" mode as soon as the drag ends (not
  // once the request settles), so a user can re-enter erase mode and start
  // a second drag before the first request's pending state has propagated
  // back through a re-render. The ref reads and writes synchronously within
  // this handler, so it can never race a second call the way a value drawn
  // from React state could.
  //
  // The ref is scoped to a target, not a plain boolean (reviewer finding 1,
  // P1-CANVAS-ERASE follow-up): `pid`/`idx0` change on navigation but this
  // component does not remount, so a bare boolean would keep blocking every
  // page's erase forever once one request outlived the page it was fired
  // from. Only a drag that targets the SAME (projectId, pageIndex) as the
  // request already in flight is blocked; a drag on a different page always
  // proceeds. `onSettled` only clears the ref if it still holds the exact
  // target object this call set — a still-open request from a page the user
  // has since left must not clear the guard for whatever NEW request the
  // current page has since started.
  function handleErasePixels(rect: { x: number; y: number; width: number; height: number }) {
    const target = { projectId: pid, pageIndex: idx0 };
    const inFlight = erasingTargetRef.current;
    if (inFlight?.projectId === target.projectId && inFlight.pageIndex === target.pageIndex) {
      return;
    }
    erasingTargetRef.current = target;
    const scale = pagePayload?.encoded_dims?.scale ?? 1;
    const srcBbox = displayToSrc(rect, scale);
    erasePagePixels.mutate(
      { bbox: srcBbox, fillValue: 255, shape: "rect" },
      {
        onSuccess: () => {
          toast.success("Erased.");
        },
        onError: (err) => {
          toast.error(err.message || "Erase failed.");
        },
        onSettled: () => {
          if (erasingTargetRef.current === target) {
            erasingTargetRef.current = null;
          }
        },
      },
    );
  }

  // ── Render ─────────────────────────────────────────────────────────────

  // ── Slot content ──────────────────────────────────────────────────────
  // D-050 (2026-06-14): hidden PageActions stub removed. Driver-contract
  // §2.5 testids (reload-ocr-button, save-page-button, etc.) are now the
  // canonical testids on the visible PageActionsCompact buttons and
  // page-actions-bar wrapper.

  // IS-3: Drawer wired with real Drawer component.
  // lineMatches is already computed above; page is pagePayload.
  // Gap 18: tabCounts populated so count badges render in the drawer header.
  const worklistCount = lines.filter(
    (l) => l.overall_match_status !== "exact" || !l.is_fully_validated,
  ).length;
  const drawerTabCounts: Partial<Record<DrawerTab, number>> = {
    worklist: worklistCount,
    hierarchy: lines.length,
    queue: reviewQueueQ.data?.total_undecided ?? 0,
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
      // D-047: ⌘K QuickSearch lives in the worklist header (it filters the
      // worklist). Mod+K focuses it via quickSearchRef (focus preserved).
      worklistHeader={<QuickSearch ref={quickSearchRef} />}
    />
  );

  // D-047: full-width workspace toolbar band — mounts at the top of the
  // project route body (where today's nav/actions appeared), leaving the
  // AppShell chrome header free of document/page-scoped controls.
  //   leftSlot   = ProjectNavigationControls (page nav)
  //   centerSlot = PageActionsCompact        (page actions)
  //   rightSlot  = WorkspaceMetrics          (per-page match metrics)
  const workspaceToolbar = (
    <WorkspaceToolbar
      leftSlot={
        projectId ? (
          <ProjectNavigationControls
            ref={navControlsRef}
            projectId={projectId}
            pageNo={String(idx0 + 1)}
          />
        ) : undefined
      }
      centerSlot={
        projectId ? <PageActionsCompact projectId={projectId} pageIndex={idx0} /> : undefined
      }
      rightSlot={<WorkspaceMetrics pageMetrics={pageMetrics} />}
    />
  );

  // IS-4: Canvas slot stripped to the active review surface. The duplicate
  // ImageTabsHeader viewport chrome was removed; target/layer controls now
  // live in the app rail.
  const canvasSlot = (
    <div className="flex flex-col h-full min-h-0">
      {/* D3: page validate-all/unvalidate-all + multi-select word bulk ops. */}
      <div className="shrink-0 border-b border-border-1 bg-bg-surface">
        <BulkWordActions projectId={pid} pageIndex={idx0} />
      </div>
      <div data-testid="image-pane" className="relative flex-1 min-h-0">
        <BusyOverlay activeJob={activeJob} isMutating={isMutating} />
        <PageLoadStatus pageLoadJobId={pageLoadJobId} jobEvent={pageLoadJob} />
        <PageImageCanvas
          imageUrl={pagePayload?.image_url ?? ""}
          encoded={pagePayload?.encoded_dims ?? null}
          page={pagePayload}
          projectId={projectId}
          pageIndex={idx0}
          onBoxSelect={handleBoxSelect}
          onAddWord={handleAddWord}
          onRebox={handleRebox}
          onErasePixels={handleErasePixels}
        />
      </div>
      <div data-testid="inline-banners" className="flex flex-col gap-1 p-1">
        <OcrFailedBanner
          ocrFailed={pagePayload?.page_load_error != null}
          message={pagePayload?.page_load_error?.message ?? null}
        />
        <ImageDriftBanner
          imageDrift={pagePayload?.image_drift != null}
          message={pagePayload?.image_drift?.message ?? null}
        />
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
            className="flex items-center justify-center rounded-sm p-0.5 text-ink-3 hover:bg-bg-1 hover:text-ink-1"
            onClick={() => {
              useUiPrefs.setState({ toolbarGridCollapsed: !uiPrefs.toolbarGridCollapsed });
              notifyUiPrefs();
            }}
          >
            {uiPrefs.toolbarGridCollapsed ? (
              // Collapsed (closed) — UP chevron; click to expand and reveal content below.
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
            ) : (
              // Open — DOWN chevron; points toward the visible content below.
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
            )}
          </button>
        </div>
        {!uiPrefs.toolbarGridCollapsed && (
          <div data-testid="toolbar-grid-body" className="px-1 pb-1">
            <ToolbarActionGrid
              selection={toolbarSelection}
              pageData={toolbarPageData}
              onAction={handleToolbarAction}
              onApplyComponent={handleApplyComponent}
              onClearComponent={handleClearComponent}
              addWordActive={addWordActive}
              onAddWordToggle={handleAddWordToggle}
            />
          </div>
        )}
      </div>
    </div>
  );

  // P2-WORD-EDIT: WordCell's own docstring says the pencil "Should select
  // the word in the selection store and open the right panel." There is no
  // dialog to open (driver-contract §2.11 retired) — WordDetail in the right
  // panel already covers the same ground the old modal did.
  function handleEditWord(lineIndex: number, wordIndex: number) {
    selectWord(idx0, lineIndex, wordIndex);
    useUiPrefs.setState({ rightPanelOpen: true });
  }

  // Right panel slot — RightPanel routes on selection-store.level.
  // Word-level content is WordDetail (Slice 16).
  // D-051 (2026-06-14): TextTabs + WordMatchView are now mounted visibly in
  // the RightPanel textTabsSlot (level="none"), replacing the
  // canvas-hidden-stubs display:none container.
  // IS-6: onCollapse wired to useUiPrefs.setState({ rightPanelOpen: false }).
  const textTabsContent = (
    <div data-testid="text-pane" className="flex flex-col h-full min-h-0">
      <TextTabs
        pageTextGt={pagePayload?.page_text_gt}
        pageTextOcr={pagePayload?.page_text_ocr}
        lineFilter={uiPrefs.matchFilter}
        onLineFilterChange={(f) => {
          setMatchFilter(f);
        }}
      >
        <WordMatchView lines={lines} filter={uiPrefs.matchFilter} onEditWord={handleEditWord} />
      </TextTabs>
      <PlaintextEditor source="gt" page={pagePayload} />
      <PlaintextEditor source="ocr" page={pagePayload} />
    </div>
  );
  const wordDetailSlot =
    pagePayload && projectId ? (
      <WordDetail
        page={pagePayload}
        projectId={projectId}
        pageIndex={idx0}
        bboxRefine={bboxRefine}
      />
    ) : undefined;
  const rightSlot = rightPanelOpen ? (
    <RightPanel
      page={pagePayload ?? undefined}
      projectId={projectId ?? undefined}
      pageIndex={idx0}
      wordSlot={wordDetailSlot}
      textTabsSlot={textTabsContent}
      onCollapse={() => {
        useUiPrefs.setState({ rightPanelOpen: false });
      }}
    />
  ) : (
    // IS-6: when the right panel is collapsed, render a narrow 32px re-open tab
    // so the user always has a visible control to restore the panel.
    <button
      data-testid="right-panel-expand-btn"
      type="button"
      aria-label="Expand detail panel"
      onClick={() => {
        useUiPrefs.setState({ rightPanelOpen: true });
      }}
      className="flex flex-col items-center justify-center w-full h-full text-ink-3 hover:text-ink-1 hover:bg-bg-1 border-l border-border-1 bg-bg-surface"
    >
      {/* ChevronLeft — detail panel is to the right, so left-chevron = "expand leftward" */}
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
        <polyline points="15 18 9 12 15 6" />
      </svg>
    </button>
  );
  const rightWidth = selectionLevel === "line" || selectionLevel === "block" ? 640 : 520;

  return (
    <div data-testid="project-page" className="flex flex-col h-full min-h-0">
      <ProjectLoadingOverlay isLoading={isProjectLoading} />

      {/* D-047: workspace toolbar band — full width, top of the project body. */}
      <div className="shrink-0">{workspaceToolbar}</div>

      <div
        data-testid="project-workspace"
        className="grid flex-1 min-h-0 bg-bg-page"
        style={{
          gridTemplateColumns: `minmax(0, 1fr) ${drawerOpen ? "320px" : "32px"} ${
            rightPanelOpen ? `${rightWidth}px` : "32px"
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

// PageActionsCompact.tsx — compact header action buttons for the header slot.
//
// IS-2: Lives in HeaderBar's actionsSlot when on a project route.
// P1.b (Gap 4, 7): Shows Reload OCR | Rematch GT | ✓ Save page | Export ▾
// styled as labelled header buttons (design-token classes, 28px height).
//
// Receives projectId + pageIndex as props (resolved by AppShell via
// useRouteProjectContext / useMatch, which works outside <Routes>).
// D-050 (2026-06-14): page-actions-bar wrapper added + page-name-label +
// page-source-badge; testids renamed to driver-contract §2.5 canonical names.
// D-049/D-050: hidden PageActions stub removed; this component is the sole
// source of truth for §2.5 page-action testids.

import { useState } from "react";
import {
  ButtonGroup,
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "@pdomain/pdomain-ui/primitives";
import { useQueryClient } from "@tanstack/react-query";
import {
  useReloadOcr,
  useReloadOcrEdited,
  useSavePage,
  useSaveProject,
  useLoadPage,
  useRematchGt,
  useRotatePage,
  useAutoRotateAll,
  useUndoPage,
  useRedoPage,
  useConfirmPageKind,
  type PagePayload,
  type PageKind,
} from "../hooks/usePageMutations";
import { useProposePageKinds, useProposeRegions } from "../hooks/useProposalRuns";
import { usePage } from "../hooks/usePage";
import { useJobProgress } from "../hooks/useJobProgress";
import { useJobCompletionInvalidation } from "../hooks/useJobCompletionInvalidation";
import { useCancelJob, type UseCancelJobResult } from "../hooks/useCancelJob";
import { dialogStore } from "../stores/dialog-store";
import { toast } from "../lib/toast";
import { PAGE_KINDS } from "../lib/pageKinds";
import { BulkGlyphMarkDialog } from "./glyph/BulkGlyphMarkDialog";

export interface PageActionsCompactProps {
  projectId: string;
  pageIndex: number;
}

// ─── cancellable run toasts (P1-CANCEL reachability) ────────────────────────
//
// Every job type this component tracks — Reload OCR, Save Project, and the
// three book-scoped runs (Propose page kinds / Propose regions / Auto-rotate
// all) — shows its progress through its own toast here, never through
// BusyOverlay (it blocks the page; several of these are meant to be worked
// through). BusyOverlay owns the only *other* Cancel button in the app; its
// CANCELLABLE / BEST_EFFORT_CANCEL policy sets (BusyOverlay.tsx) already
// list every one of these job types as backend-cancellable
// (docs/issues/2026-07-21-job-cancel-incomplete.md). This gives each toast
// the same Cancel action, via the same POST (useCancelJob.ts) BusyOverlay's
// button fires — so the button a person actually clicks can cancel, not
// just the equivalent keyboard shortcut that happens to route through
// ProjectPage's own BusyOverlay-tracked job.

/**
 * reload_ocr is in BusyOverlay's BEST_EFFORT_CANCEL set, not its
 * CANCELLABLE set: reload_ocr.py never polls `runner.is_cancelled` between
 * its stages, so a cancel request only flips the job's status — OCR keeps
 * running in its background thread and may still complete. Matches
 * BusyOverlay's own BEST_EFFORT_CANCEL title wording (BusyOverlay.tsx)
 * rather than inventing new copy for this surface.
 */
const BEST_EFFORT_CANCEL_NOTE = "best-effort — OCR may not stop immediately";

/**
 * Loading toast for a cancellable run.
 *
 * Once `cancelJob.cancel(jobId)` has fired for this job id, later progress
 * ticks keep the toast in a "Cancelling…" state with no action —
 * `wasRequested` is the same guard `cancel()` uses to dedupe the POST, so a
 * second click, or a progress tick racing the terminal event, can't
 * reintroduce the button or repeat the request.
 *
 * `description`, when given, renders as a secondary line under the message
 * — used only for the best-effort caveat on Reload OCR's toast; every
 * other caller omits it.
 */
function showCancellableLoadingToast(
  jobId: string,
  message: string,
  cancelJob: UseCancelJobResult,
  description?: string,
): void {
  const cancelling = cancelJob.wasRequested(jobId);
  void import("sonner").then(({ toast: sonnerToast }) => {
    sonnerToast.loading(cancelling ? "Cancelling…" : message, {
      id: jobId,
      ...(cancelling
        ? {}
        : {
            ...(description ? { description } : {}),
            action: {
              label: "Cancel",
              onClick: () => {
                cancelJob.cancel(jobId);
                void import("sonner").then(({ toast: t }) => {
                  t.loading("Cancelling…", { id: jobId });
                });
              },
            },
          }),
    });
  });
}

// ─── page-kind control (page-kind review design) ───────────────────────────
//
// Spec: pdomain-ocr-synth's docs/specs/2026-09-17-page-kind-review-design.md
//   "The page toolbar shows and confirms the current page's kind".

/** The kind a fresh control should preselect: confirmed, else proposed, else none. */
function defaultKindSelection(page: PagePayload | undefined): PageKind | "" {
  if (!page) return "";
  if (page.page_kind_reviewed && page.page_kind) return page.page_kind;
  if (page.page_kind_proposal) return page.page_kind_proposal.kind;
  return "";
}

interface PageKindControlProps {
  page: PagePayload | undefined;
  confirmPageKind: ReturnType<typeof useConfirmPageKind>;
}

/**
 * Shows the current page's kind — confirmed, proposed, or nothing yet — and,
 * once opened, a native select of all fourteen kinds plus a Confirm button.
 *
 * The select's value is derived every render from `page` (confirmed, else
 * proposed, else none) unless the person has picked something else in this
 * open session — `override` holds only that pick, not a copy of server
 * state, so a page payload that loads or refreshes after mount (the usual
 * case: `usePage` is still fetching when this first renders) is picked up
 * without an effect. `override` resets to `null` each time the control is
 * opened, and keyed by `pageIndex` at the call site so navigating to a
 * different page remounts this component and drops any stale pick.
 */
function PageKindControl({ page, confirmPageKind }: PageKindControlProps) {
  const [open, setOpen] = useState(false);
  const [override, setOverride] = useState<PageKind | "" | null>(null);
  const selected = override ?? defaultKindSelection(page);

  const proposal = page?.page_kind_proposal ?? null;
  const confirmed = page?.page_kind_reviewed === true ? (page.page_kind ?? null) : null;

  let statusLabel: string;
  if (confirmed) {
    statusLabel = `Confirmed: ${confirmed}`;
  } else if (proposal) {
    statusLabel =
      proposal.kind === "unknown"
        ? "Kind unknown"
        : `Proposed: ${proposal.kind} (${typeof proposal.confidence === "number" ? proposal.confidence.toFixed(2) : "—"})`;
  } else {
    statusLabel = "No page kind";
  }

  // Let this control shrink (min-w-0, no shrink-0) and truncate with an
  // ellipsis, rather than capping statusLabel to a fixed max-width:
  // page-actions-bar's other buttons already fill nearly all of the
  // toolbar's fixed-width center slot on its own, so any uncapped label
  // here overflows past the slot's edge — with real word content, the
  // toolbar's right slot (WorkspaceMetrics) renders a nonzero-width "N
  // exact" strip that then sits, later in DOM order, on top of that
  // overflow and steals its clicks (P0-CI-SOFT follow-up). A *fixed* cap
  // would ellipsis ordinary confirmed/proposed labels ("Proposed: chapter
  // opening (0.87)") behind a hover too, hiding the kind and confidence for
  // sighted non-hovering users. Flex-shrink + truncate instead only clips
  // when the row is genuinely too narrow to fit the full text — every other
  // button in this group keeps its natural size (this is the one child
  // that gives way) — and shows the complete label whenever there's room.
  // Clicking/tapping the button opens the kind select regardless of whether
  // the hint is fully visible, so keyboard and touch users reach the same
  // information (which kind to pick) without relying on hover; only the
  // "try Propose page kinds instead" suggestion may need a click to fully
  // read, via the `title` tooltip. The full hint text is still in the DOM
  // (toHaveTextContent assertions pass).
  return (
    <div data-testid="page-kind-control" className="flex items-center gap-1 min-w-0">
      <button
        type="button"
        data-testid="page-kind-status-button"
        aria-expanded={open}
        onClick={() => {
          setOverride(null);
          setOpen((v) => !v);
        }}
        title={proposal ? undefined : "No page kind — run Propose page kinds to get one"}
        className="px-2 py-0.5 text-[11px] rounded-sm border border-border-2 bg-bg-raised text-ink-2 hover:text-ink-1 hover:border-accent transition-colors truncate min-w-0"
      >
        {statusLabel}
        {!confirmed && !proposal && (
          <span className="ml-1 text-ink-4">— run Propose page kinds</span>
        )}
      </button>
      {open && (
        <>
          <select
            data-testid="page-kind-select"
            aria-label="Page kind"
            value={selected}
            disabled={confirmPageKind.isPending}
            onChange={(e) => {
              setOverride(e.target.value as PageKind | "");
            }}
            className="text-[11px] border border-border-2 rounded-sm px-1 py-0.5 bg-bg-sunk text-ink-2"
          >
            <option value="" disabled>
              Choose a kind…
            </option>
            {PAGE_KINDS.map((kind) => (
              <option key={kind} value={kind}>
                {kind}
              </option>
            ))}
          </select>
          <button
            type="button"
            data-testid="page-kind-confirm-button"
            disabled={selected === "" || confirmPageKind.isPending}
            onClick={() => {
              if (selected === "") return;
              confirmPageKind.mutate(
                { kind: selected },
                {
                  onSuccess: () => {
                    setOpen(false);
                    setOverride(null);
                  },
                  onError: () => {
                    toast.error("Confirm page kind failed");
                  },
                },
              );
            }}
            className="px-2 py-0.5 text-[11px] rounded-sm border border-accent/60 text-accent hover:bg-accent/10 transition-colors disabled:opacity-40"
          >
            Confirm
          </button>
        </>
      )}
    </div>
  );
}

/** Inline spinner — shown while a button's job is running. */
function Spinner() {
  return (
    <svg
      className="animate-spin h-3 w-3 shrink-0"
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
      />
    </svg>
  );
}

export function PageActionsCompact({ projectId, pageIndex }: PageActionsCompactProps) {
  const qc = useQueryClient();

  // OCR job tracking (Reload OCR / Reload OCR Edited)
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  // Save-project job tracking — kept separate to avoid conflating with OCR jobs.
  const [saveProjectJobId, setSaveProjectJobId] = useState<string | null>(null);
  // Rotate / auto-rotate job tracking (P2 / C28+C29) — separate so the
  // completion toast can say "rotated" rather than "OCR complete".
  const [rotateJobId, setRotateJobId] = useState<string | null>(null);
  // Which action started the currently-tracked rotate job: only
  // auto_rotate_all is in BusyOverlay's CANCELLABLE policy set — a single
  // manual rotate (rotate_page) is not, so its toast stays plain. Tracked
  // separately from rotateJobId so the toast callbacks below can tell them
  // apart without threading the job type through useJobProgress.
  const [rotateJobType, setRotateJobType] = useState<"rotate_page" | "auto_rotate_all" | null>(
    null,
  );
  const [bulkGlyphOpen, setBulkGlyphOpen] = useState(false);
  const jobProgress = useJobProgress(activeJobId);
  const saveProjectProgress = useJobProgress(saveProjectJobId);
  const rotateProgress = useJobProgress(rotateJobId);

  // Task 6 (region review surface): Propose page kinds / Propose regions job
  // tracking — each gets its own active-job-id state so the two book-scoped
  // runs can be in flight together without clobbering each other's toast.
  const [pageKindsJobId, setPageKindsJobId] = useState<string | null>(null);
  const [regionsJobId, setRegionsJobId] = useState<string | null>(null);
  const pageKindsProgress = useJobProgress(pageKindsJobId);
  const regionsProgress = useJobProgress(regionsJobId);

  // P1-CANCEL: one cancel POST, shared by every cancellable toast in this
  // component (see useCancelJob.ts — the same hook backs BusyOverlay's
  // Cancel button).
  const cancelJob = useCancelJob();

  // C2: read the page payload so the restored "Reload OCR (Edited)" button can
  // be gated on the real edited-image signal (labeler extension flag set by the
  // erase-pixels path / Lane A4) and the source badge can show provenance.
  const pageQ = usePage(projectId || undefined, projectId ? pageIndex : undefined);
  const labelerExt = (pageQ.data?.page_record?.extensions?.["labeler"] ?? null) as {
    has_edited_image?: boolean;
  } | null;
  const hasEditedImage = labelerExt?.has_edited_image === true;

  // P2 / C28: durable rotation metadata for the rotation badge.
  const rotationDegrees = pageQ.data?.page_record?.rotation_degrees ?? 0;
  const rotationSource = pageQ.data?.page_record?.rotation_source ?? "none";
  const isRotated = rotationDegrees !== 0;
  // Undo/redo availability — PagePayload.history (event-store undo, U-3).
  const history = pageQ.data?.history ?? null;
  const undoAvailable = history?.undo_available === true;
  const redoAvailable = history?.redo_available === true;

  // Toast lifecycle: react to OCR job progress transitions.
  // Rematch GT is synchronous (no SSE job) so it uses onSuccess/onError directly.
  //
  // Invalidation + activeJobId reset are handled by the shared hook; toast
  // text + loading-toast updates remain call-site-specific.
  useJobCompletionInvalidation({
    activeJobId,
    jobProgress,
    setActiveJobId,
    invalidationKey: ["page", projectId, pageIndex],
    onComplete: (jobId) => {
      toast.success("OCR complete", { id: jobId });
    },
    onError: (jobId) => {
      toast.error("OCR failed", { id: jobId });
    },
    // P1-CANCEL: reload_ocr is best-effort only (BusyOverlay's
    // BEST_EFFORT_CANCEL, not CANCELLABLE) — reload_ocr.py never polls
    // is_cancelled between its stages, so the terminal "cancelled" event's
    // own progress message is just whatever OCR stage happened to be in
    // flight, not a summary of what canceling did. Say what to expect
    // instead of echoing that stage label as if it explained the outcome.
    onCancelled: (jobId) => {
      toast.warn(`Cancel requested (${BEST_EFFORT_CANCEL_NOTE}).`, { id: jobId });
    },
    onRunning: (jobId, event) => {
      const msg = event.progress?.message ?? "Running OCR…";
      showCancellableLoadingToast(jobId, msg, cancelJob, `Cancel is ${BEST_EFFORT_CANCEL_NOTE}.`);
    },
  });

  // Save-project completion: fetch the job's `result` to check
  // skipped_pages, then show a warning (if any pages were skipped) or
  // success toast. `result` is the public Job model's field for
  // handler-specific output (core.models.Job.result;
  // docs/issues/2026-07-21-jobs-api-openapi-mismatch.md, P1-JOBS-API) —
  // save_project writes skipped_pages/skipped_indices/failures there.
  useJobCompletionInvalidation({
    activeJobId: saveProjectJobId,
    jobProgress: saveProjectProgress,
    setActiveJobId: setSaveProjectJobId,
    invalidationKey: ["page", projectId, pageIndex],
    onComplete: (jobId) => {
      void fetch(`/api/jobs/${encodeURIComponent(jobId)}`)
        .then((r) => r.json())
        .then((job: { result?: { skipped_pages?: number; skipped_indices?: number[] } | null }) => {
          const skipped = job.result?.skipped_pages ?? 0;
          if (skipped > 0) {
            const indices = job.result?.skipped_indices ?? [];
            toast.warn(
              `Project saved. ${skipped} page(s) not saved (unregistered): ${indices.join(", ")}`,
              {
                id: jobId,
              },
            );
          } else {
            toast.success("Project saved", { id: jobId });
          }
        })
        .catch(() => {
          // Fallback if the job fetch fails — at least dismiss the loading toast.
          toast.success("Project saved", { id: jobId });
        });
    },
    onError: (jobId) => {
      toast.error("Save project failed", { id: jobId });
    },
    // P1-CANCEL: save_project is in BusyOverlay's CANCELLABLE policy set —
    // it checks is_cancelled between pages and every page saved before the
    // cancel took effect is already durably persisted
    // (save_project.py), so the page query is worth refreshing here.
    onCancelled: (jobId, event) => {
      void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
      const msg = event.progress.message || "Save project cancelled";
      toast.warn(msg, { id: jobId });
    },
    onRunning: (jobId, event) => {
      const msg = event.progress?.message ?? "Saving project…";
      showCancellableLoadingToast(jobId, msg, cancelJob);
    },
  });

  // P2 / C28+C29: rotate + auto-rotate jobs share one tracker (only one can
  // run at a time from this surface). Page query invalidation on completion
  // refreshes the image, words, and rotation badge in one pass.
  useJobCompletionInvalidation({
    activeJobId: rotateJobId,
    jobProgress: rotateProgress,
    setActiveJobId: setRotateJobId,
    invalidationKey: ["page", projectId, pageIndex],
    onComplete: (jobId) => {
      toast.success("Rotate complete", { id: jobId });
    },
    onError: (jobId) => {
      toast.error("Rotate failed", { id: jobId });
    },
    // P1-CANCEL: only auto_rotate_all is in BusyOverlay's CANCELLABLE
    // policy set — pages already rotated before the cancel took effect are
    // durably persisted (auto_rotate_all.py checks cancellation between
    // pages, not mid-page), so the page query is worth refreshing here.
    onCancelled: (jobId, event) => {
      void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
      const msg = event.progress.message || "Rotate cancelled";
      toast.warn(msg, { id: jobId });
    },
    onRunning: (jobId, event) => {
      const msg = event.progress?.message ?? "Rotating…";
      if (rotateJobType === "auto_rotate_all") {
        showCancellableLoadingToast(jobId, msg, cancelJob);
      } else {
        void import("sonner").then(({ toast: sonnerToast }) => {
          sonnerToast.loading(msg, { id: jobId });
        });
      }
    },
  });

  // Task 6 (region review surface): Propose page kinds completion.
  //
  // Invalidates the page query the same as every other mutation here — the
  // page toolbar's kind control (below) reads `page_kind_proposal` off that
  // query, so a completed run refreshes what it shows.
  useJobCompletionInvalidation({
    activeJobId: pageKindsJobId,
    jobProgress: pageKindsProgress,
    setActiveJobId: setPageKindsJobId,
    invalidationKey: ["page", projectId, pageIndex],
    onComplete: (jobId, event) => {
      // Book review queue design ("A count stays visible"): a page-kinds
      // run can change which pages a later region run touches, so the queue
      // is invalidated here too — cheap at limit=0, and correct even though
      // this run alone never changes `total_undecided`.
      void qc.invalidateQueries({ queryKey: ["review-queue", projectId] });
      // Page-kind review design ("A proposal run and page history both
      // refresh the list"): the book-wide Review page kinds dialog must see
      // this run's fresh proposals too.
      void qc.invalidateQueries({ queryKey: ["page-kinds", projectId] });
      const msg = event.progress.message || "Page kind proposals complete";
      toast.success(msg, { id: jobId });
    },
    onError: (jobId) => {
      toast.error("Page kind proposals failed", { id: jobId });
    },
    // P1-CANCEL: propose_page_kinds cancels during its measurement pass —
    // classification and recording only happen after that pass completes
    // (propose_page_kinds.py), so a cancelled run leaves nothing new to
    // invalidate; the backend's own message says as much ("nothing
    // recorded").
    onCancelled: (jobId, event) => {
      const msg = event.progress.message || "Page kind proposals cancelled";
      toast.warn(msg, { id: jobId });
    },
    onRunning: (jobId, event) => {
      // The normalized message is "" when the backend sent none, so fall back
      // with ||, not ??, or the loading toast would go blank.
      const msg = event.progress.message || "Proposing page kinds…";
      showCancellableLoadingToast(jobId, msg, cancelJob);
    },
  });

  // Task 6 (region review surface): Propose regions completion. A run that
  // skipped every page for having no page kind still returns "complete" —
  // the terminal message says so, and that message is shown as a warning
  // (not success) because nothing useful happened and a person needs to act.
  useJobCompletionInvalidation({
    activeJobId: regionsJobId,
    jobProgress: regionsProgress,
    setActiveJobId: setRegionsJobId,
    invalidationKey: ["page", projectId, pageIndex],
    onComplete: (jobId, event) => {
      // Book review queue design ("A count stays visible"): a completed
      // region run is exactly what fills or empties the queue, so the Rail
      // badge and bracket-key navigation must see the fresh count and page
      // summary once this invalidation's refetch lands.
      void qc.invalidateQueries({ queryKey: ["review-queue", projectId] });
      const msg = event.progress.message || "Region proposals complete";
      if (msg.toLowerCase().includes("propose page kinds first")) {
        toast.warn(msg, { id: jobId });
      } else {
        toast.success(msg, { id: jobId });
      }
    },
    onError: (jobId) => {
      toast.error("Region proposals failed", { id: jobId });
    },
    // P1-CANCEL: propose_regions journals proposals per page as it goes
    // (propose_regions.py), so pages already proposed before the cancel
    // took effect are durable — both the page query and the review queue
    // are worth refreshing here, same as on a normal completion.
    onCancelled: (jobId, event) => {
      void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
      void qc.invalidateQueries({ queryKey: ["review-queue", projectId] });
      const msg = event.progress.message || "Region proposals cancelled";
      toast.warn(msg, { id: jobId });
    },
    onRunning: (jobId, event) => {
      const msg = event.progress.message || "Proposing regions…";
      showCancellableLoadingToast(jobId, msg, cancelJob);
    },
  });

  const reloadOcr = useReloadOcr(projectId, pageIndex);
  const reloadOcrEdited = useReloadOcrEdited(projectId, pageIndex);
  const savePage = useSavePage(projectId, pageIndex);
  const saveProject = useSaveProject(projectId);
  const loadPage = useLoadPage(projectId, pageIndex);
  const rematchGt = useRematchGt(projectId, pageIndex);
  const rotatePage = useRotatePage(projectId, pageIndex);
  const autoRotateAll = useAutoRotateAll(projectId);
  const undoPage = useUndoPage(projectId, pageIndex);
  const redoPage = useRedoPage(projectId, pageIndex);
  const proposePageKinds = useProposePageKinds(projectId);
  const proposeRegions = useProposeRegions(projectId);
  const confirmPageKind = useConfirmPageKind(projectId, pageIndex);

  const isBusy =
    reloadOcr.isPending ||
    reloadOcrEdited.isPending ||
    savePage.isPending ||
    saveProject.isPending ||
    loadPage.isPending ||
    rematchGt.isPending ||
    rotatePage.isPending ||
    autoRotateAll.isPending ||
    undoPage.isPending ||
    redoPage.isPending ||
    (jobProgress !== null && jobProgress.status !== "complete" && jobProgress.status !== "error") ||
    (saveProjectProgress !== null &&
      saveProjectProgress.status !== "complete" &&
      saveProjectProgress.status !== "error") ||
    (rotateProgress !== null &&
      rotateProgress.status !== "complete" &&
      rotateProgress.status !== "error");

  // Task 6 (region review surface): Propose page kinds / Propose regions are
  // book-scoped background jobs that don't touch the current page directly,
  // so — unlike the trackers folded into `isBusy` above — they gate only
  // their own button rather than the whole toolbar.
  const pageKindsRunning =
    proposePageKinds.isPending ||
    (pageKindsProgress !== null &&
      pageKindsProgress.status !== "complete" &&
      pageKindsProgress.status !== "error");
  const regionsRunning =
    proposeRegions.isPending ||
    (regionsProgress !== null &&
      regionsProgress.status !== "complete" &&
      regionsProgress.status !== "error");

  // U-6 (spec 2026-06-12-event-store-undo): re-OCR creates a NEW page
  // aggregate — the undo history resets. Confirm before enqueueing.
  const reloadOcrConfirmBody =
    "This will re-run OCR for the current page and the page's edit history resets — Undo will not step back across this reload.";

  function handleReloadOcr() {
    dialogStore.openConfirm({
      title: "Reload OCR?",
      body: reloadOcrConfirmBody,
      onConfirm: () => {
        reloadOcr.mutate(undefined, {
          onSuccess: (data) => {
            if (data?.job_id) {
              setActiveJobId(data.job_id);
              // Show initial loading toast immediately while SSE stream opens.
              showCancellableLoadingToast(
                data.job_id,
                "Running OCR…",
                cancelJob,
                `Cancel is ${BEST_EFFORT_CANCEL_NOTE}.`,
              );
            }
          },
          onError: () => {
            toast.error("Failed to start OCR");
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
        } else {
          toast.success("Page saved");
        }
      },
      onError: () => {
        toast.error("Save failed");
      },
      onSettled: () => {
        void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
      },
    });
  }

  function handleRematchGt() {
    rematchGt.mutate(undefined, {
      onSuccess: () => {
        // Rematch GT is synchronous — no job_id, just a direct page payload.
        toast.success("Rematch GT complete");
        void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
      },
      onError: () => {
        toast.error("Rematch GT failed");
      },
    });
  }

  // C2: restored "Reload OCR (Edited)" — re-runs OCR against the persisted
  // post-erase image (use_edited_image: true; the field exists in types.ts from
  // Lane A4). Same SSE/job lifecycle as a plain reload.
  function handleReloadOcrEdited() {
    dialogStore.openConfirm({
      title: "Reload OCR (edited image)?",
      body: reloadOcrConfirmBody,
      onConfirm: () => {
        reloadOcrEdited.mutate(undefined, {
          onSuccess: (data) => {
            if (data?.job_id) {
              setActiveJobId(data.job_id);
              showCancellableLoadingToast(
                data.job_id,
                "Running OCR (edited)…",
                cancelJob,
                `Cancel is ${BEST_EFFORT_CANCEL_NOTE}.`,
              );
            }
          },
          onError: () => {
            toast.error("Failed to start OCR (edited)");
          },
        });
      },
    });
  }

  // C2: restored "Save Project" — persists every page (202 + job_id).
  // S5.2: on completion, reads result.skipped_pages and shows warning if > 0.
  function handleSaveProject() {
    saveProject.mutate(undefined, {
      onSuccess: (data) => {
        if (data?.job_id) {
          setSaveProjectJobId(data.job_id);
          showCancellableLoadingToast(data.job_id, "Saving project…", cancelJob);
        } else {
          toast.success("Project saved");
        }
      },
      onError: () => {
        toast.error("Save project failed");
      },
    });
  }

  // "Reload" (formerly "Load Page", U-7): refreshes the page from the
  // event-store head. Every mutation auto-persists, so there are no
  // "unsaved edits" to discard — use Undo to step back through history.
  function handleLoadPage() {
    dialogStore.openConfirm({
      title: "Reload page?",
      body: "This will refresh the page from the latest stored version. Edits are saved automatically — use Undo to step back through page history.",
      onConfirm: () => {
        loadPage.mutate(undefined, {
          onSuccess: () => {
            toast.success("Page reloaded");
          },
          onError: () => {
            toast.error("Reload failed");
          },
          onSettled: () => {
            void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
          },
        });
      },
    });
  }

  // P2 / C28: manual rotate — pixels rotate on disk, page re-OCRs, rotation
  // metadata persists. 202 + job_id; tracked by the rotate job hook above.
  function handleRotate(degrees: number) {
    rotatePage.mutate(
      { degrees },
      {
        onSuccess: (data) => {
          if (data?.job_id) {
            setRotateJobId(data.job_id);
            setRotateJobType("rotate_page");
            void import("sonner").then(({ toast: sonnerToast }) => {
              sonnerToast.loading("Rotating page…", { id: data.job_id });
            });
          }
        },
        onError: () => {
          toast.error("Failed to start rotate");
        },
      },
    );
  }

  // P2 / C29: batch auto-rotate. Uses the configured auto-rotate method
  // (OCR config dialog) server-side; manually-rotated pages are skipped.
  // P1-CANCEL: auto_rotate_all is in BusyOverlay's CANCELLABLE policy set —
  // its loading toast gets a Cancel action (showCancellableLoadingToast),
  // unlike the single-page rotate above.
  function handleAutoRotateAll() {
    autoRotateAll.mutate(undefined, {
      onSuccess: (data) => {
        if (data?.job_id) {
          setRotateJobId(data.job_id);
          setRotateJobType("auto_rotate_all");
          showCancellableLoadingToast(data.job_id, "Auto-rotating pages…", cancelJob);
        }
      },
      onError: (err) => {
        const status = (err as { status?: number }).status;
        toast.error(
          status === 503
            ? "Auto-rotate unavailable (rotation module missing)"
            : "Auto-rotate failed",
        );
      },
    });
  }

  // Task 6 (region review surface): book-scoped runs that must run in this
  // order — a region run skips any page whose kind was never proposed or
  // confirmed, so Propose page kinds must run first.
  function handleProposePageKinds() {
    proposePageKinds.mutate(undefined, {
      onSuccess: (data) => {
        if (data.job_id) {
          setPageKindsJobId(data.job_id);
          showCancellableLoadingToast(data.job_id, "Proposing page kinds…", cancelJob);
        }
      },
      onError: () => {
        toast.error("Failed to start page kind proposals");
      },
    });
  }

  function handleProposeRegions() {
    proposeRegions.mutate(undefined, {
      onSuccess: (data) => {
        if (data.job_id) {
          setRegionsJobId(data.job_id);
          showCancellableLoadingToast(data.job_id, "Proposing regions…", cancelJob);
        }
      },
      onError: () => {
        toast.error("Failed to start region proposals");
      },
    });
  }

  // Event-store undo (U-1/U-2): the mutation hooks invalidate the page query
  // on success, which refetches PagePayload.history and refreshes both
  // buttons' disabled state.
  function handleUndo() {
    undoPage.mutate(undefined, {
      onError: () => {
        toast.error("Undo failed");
      },
    });
  }

  function handleRedo() {
    redoPage.mutate(undefined, {
      onError: () => {
        toast.error("Redo failed");
      },
    });
  }

  function handleExport() {
    dialogStore.open("export");
  }

  function handleOcrConfig() {
    dialogStore.open("ocrConfig");
  }

  const base =
    "flex items-center gap-1 h-7 px-2.5 rounded-sm border text-[11px] font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed";
  const normal = "border-border-2 bg-bg-raised text-ink-2 hover:bg-bg-surface hover:text-ink-1";
  const accentBtn =
    "border-border-2 bg-bg-raised text-accent hover:border-accent hover:text-accent-ink hover:bg-accent";

  const disabled = isBusy || !projectId;

  // Spinner is shown on the Reload OCR button while the SSE job is in flight.
  const ocrRunning = activeJobId !== null && isBusy;
  // Rematch is synchronous — show spinner while the mutation is pending.
  const rematchRunning = rematchGt.isPending;

  // D-050: page metadata for name label and source badge.
  const pageName = pageQ.data?.page_record?.image_path?.split("/").pop() ?? null;
  const pageSource =
    (
      pageQ.data?.page_record?.extensions?.["labeler"] as
        { page_source?: string } | null | undefined
    )?.page_source ?? null;
  const provenanceSummary = pageQ.data?.page_record?.provenance_summary ?? null;

  return (
    // overflow-hidden: the primary fix for the toolbar collision is
    // PageKindControl's own truncation (min-w-0 + truncate) giving way
    // before anything overflows page-actions-bar at all — verified this
    // *is* load-bearing, not just PageKindControl's truncation alone:
    // removing overflow-hidden with truncation still in place reintroduces
    // the click failure on page-kind-status-button (confirmed by hand,
    // P0-CI-SOFT follow-up). It is a hard clip, not a graceful one — at a
    // narrow enough viewport, page-actions-bar's other buttons alone can
    // already consume nearly all of the toolbar's fixed-width center slot,
    // so even PageKindControl's shortest label ("No page kind", no hint)
    // can still be a few pixels wider than the remaining room. This is the
    // backstop for that residual case: it keeps whatever doesn't fit from
    // ever painting on top of the metrics slot to the right, rather than
    // guaranteeing PageKindControl is always fully visible (that would need
    // shrinking the other, pre-existing buttons in this row too, out of
    // scope here).
    <div data-testid="page-actions-bar" className="flex overflow-hidden">
      <ButtonGroup
        data-testid="page-actions-compact"
        // Not shrink-0 (unlike its individual buttons): page-actions-bar's
        // fixed-width center slot needs *something* here able to give way
        // when the row is too wide for the slot (P0-CI-SOFT follow-up —
        // see PageKindControl below, the one child that actually shrinks).
        className="flex items-center gap-1 min-w-0"
        aria-label="Page actions"
      >
        {/* D-050: driver-contract §2.5 canonical testids on visible buttons */}
        <button
          type="button"
          data-testid="reload-ocr-button"
          aria-label="Reload OCR"
          disabled={disabled}
          onClick={handleReloadOcr}
          title="Reload OCR (Ctrl+R)"
          className={`${base} ${normal}`}
        >
          {ocrRunning && <Spinner />}
          Reload OCR
        </button>

        <button
          type="button"
          data-testid="rematch-gt-button"
          aria-label="Rematch GT"
          disabled={disabled}
          onClick={handleRematchGt}
          title="Rematch GT (Ctrl+G)"
          className={`${base} ${normal}`}
        >
          {rematchRunning && <Spinner />}
          Rematch
        </button>

        <button
          type="button"
          data-testid="save-page-button"
          aria-label="Save page (Ctrl+S)"
          disabled={disabled}
          onClick={handleSavePage}
          title="Save page (Ctrl+S)"
          className={`${base} ${accentBtn}`}
        >
          <span aria-hidden="true">✓</span>
          <span>Save page</span>
        </button>

        {/* Undo/redo — event-store undo (spec 2026-06-12). Canonical driver
            testids live HERE on the visible controls (the legacy labeler had no
            undo surface, so these are new testids per the driver contract). */}
        <button
          type="button"
          data-testid="undo-button"
          aria-label="Undo"
          disabled={disabled || !undoAvailable}
          onClick={handleUndo}
          title="Undo (Ctrl+Z)"
          className={`${base} ${normal}`}
        >
          Undo
        </button>

        <button
          type="button"
          data-testid="redo-button"
          aria-label="Redo"
          disabled={disabled || !redoAvailable}
          onClick={handleRedo}
          title="Redo (Ctrl+Shift+Z)"
          className={`${base} ${normal}`}
        >
          Redo
        </button>

        <button
          type="button"
          data-testid="export-button"
          aria-label="Export"
          disabled={disabled}
          onClick={handleExport}
          title="Export (E)"
          className={`${base} ${normal}`}
        >
          Export
          <span aria-hidden="true" className="text-[9px] opacity-70">
            ▾
          </span>
        </button>

        {/* #405: OCR-config trigger restored in project-page context (was removed from HeaderBar by D-046).
            Driver contract §2.3: testid "ocr-config-trigger-button" preserved. */}
        <button
          type="button"
          data-testid="ocr-config-trigger-button"
          aria-label="OCR Config"
          disabled={disabled}
          onClick={handleOcrConfig}
          title="OCR Config (Mod+,)"
          className={`${base} ${normal}`}
        >
          OCR Config
        </button>

        {/* C2: overflow menu (Radix DropdownMenu) — Reload OCR (Edited), Save
            Project, Load Page, rotate actions. D-050: adopted pdomain-ui
            DropdownMenu replacing the hand-rolled open/close state. */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              data-testid="page-actions-compact-overflow"
              aria-label="More page actions"
              aria-haspopup="menu"
              disabled={!projectId}
              title="More actions"
              className={`${base} ${normal}`}
            >
              <span aria-hidden="true">⋯</span>
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="min-w-48">
            <DropdownMenuItem
              data-testid="reload-ocr-edited-button"
              disabled={disabled || !hasEditedImage}
              onSelect={handleReloadOcrEdited}
            >
              Reload OCR (Edited)
            </DropdownMenuItem>
            <DropdownMenuItem
              data-testid="save-project-button"
              disabled={disabled}
              onSelect={handleSaveProject}
            >
              Save Project
            </DropdownMenuItem>
            <DropdownMenuItem
              data-testid="load-page-button"
              disabled={disabled}
              onSelect={handleLoadPage}
            >
              Reload
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              data-testid="rotate-cw-button"
              disabled={disabled}
              onSelect={() => {
                handleRotate(90);
              }}
            >
              <span aria-hidden="true">↻</span> Rotate CW
            </DropdownMenuItem>
            <DropdownMenuItem
              data-testid="rotate-ccw-button"
              disabled={disabled}
              onSelect={() => {
                handleRotate(-90);
              }}
            >
              <span aria-hidden="true">↺</span> Rotate CCW
            </DropdownMenuItem>
            <DropdownMenuItem
              data-testid="rotate-180-button"
              disabled={disabled}
              onSelect={() => {
                handleRotate(180);
              }}
            >
              <span aria-hidden="true">⟳</span> Rotate 180°
            </DropdownMenuItem>
            <DropdownMenuItem
              data-testid="auto-rotate-all-button"
              disabled={disabled}
              onSelect={handleAutoRotateAll}
            >
              Auto-rotate all pages
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            {/* Task 6 (region review surface): book actions that start the
                page-kind and region proposal runs. Propose page kinds must
                run first — a region run skips any page whose kind was never
                proposed or confirmed. Neither blocks the rest of the
                toolbar, so each is gated on its own job rather than the
                shared `disabled`. */}
            <DropdownMenuItem
              data-testid="propose-page-kinds-button"
              disabled={!projectId || pageKindsRunning}
              onSelect={handleProposePageKinds}
            >
              Propose page kinds
            </DropdownMenuItem>
            <DropdownMenuItem
              data-testid="propose-regions-button"
              disabled={!projectId || regionsRunning}
              onSelect={handleProposeRegions}
            >
              Propose regions
            </DropdownMenuItem>
            {/* Page-kind review design: "A book-wide list reviews many pages
                at once" — opens the Review page kinds dialog. */}
            <DropdownMenuItem
              data-testid="review-page-kinds-button"
              disabled={!projectId}
              onSelect={() => {
                dialogStore.open("pageKinds");
              }}
            >
              Review page kinds
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        {/* P2 / C28: rotation badge — always in DOM (driver contract), visible
            only when the page carries a non-zero durable rotation. Blue for
            manual, gray for auto.
            Spec §19: clicking an AUTO badge reverts the auto-rotation. */}
        <button
          type="button"
          data-testid="rotation-badge"
          style={!isRotated ? { display: "none" } : undefined}
          onClick={
            rotationSource === "auto"
              ? () => {
                  // Inverse quarter-turn within the API's accepted set
                  // (-90 / 90 / 180): 90→-90, 180→180, 270→90.
                  handleRotate(rotationDegrees === 180 ? 180 : rotationDegrees === 270 ? 90 : -90);
                }
              : undefined
          }
          disabled={rotationSource !== "auto" || isBusy}
          aria-label={
            rotationSource === "auto"
              ? `Auto-rotated ${String(rotationDegrees)}° clockwise. Click to revert.`
              : `Manually rotated ${String(rotationDegrees)}° clockwise.`
          }
          title={
            rotationSource === "auto"
              ? `Auto-rotated ${String(rotationDegrees)}° clockwise. Click to revert.`
              : `Manually rotated ${String(rotationDegrees)}° clockwise.`
          }
          className={[
            "px-2 py-0.5 text-[11px] font-semibold rounded-sm bg-bg-raised",
            rotationSource === "manual" ? "text-accent" : "text-ink-3",
            "disabled:cursor-default",
          ].join(" ")}
        >
          ↻ {rotationDegrees}° {rotationSource === "none" ? "" : rotationSource}
        </button>

        <button
          type="button"
          data-testid="bulk-glyph-mark-button"
          aria-label="Bulk-mark glyphs"
          disabled={disabled}
          onClick={() => setBulkGlyphOpen(true)}
          title="Bulk-mark glyphs"
          className={`${base} ${normal}`}
        >
          Bulk glyphs
        </button>

        {/* D-050: page-name-label and page-source-badge — visible in the actions
            bar (previously only in the hidden PageActions stub). */}
        {pageName && (
          <span
            data-testid="page-name-label"
            className="px-2 text-[11px] text-ink-3 font-mono truncate max-w-[180px] shrink-0"
            title={pageName}
          >
            {pageName}
          </span>
        )}
        <span
          data-testid="page-source-badge"
          className="px-2 py-0.5 text-[11px] text-ink-3 truncate shrink-0"
          title={provenanceSummary ?? pageSource ?? ""}
        >
          {pageSource ?? ""}
        </span>

        {/* Page-kind review design: "The page toolbar shows and confirms the
            current page's kind" — keyed by pageIndex so the control's local
            open/selected state resets on navigation (see PageKindControl). */}
        <PageKindControl key={pageIndex} page={pageQ.data} confirmPageKind={confirmPageKind} />

        {bulkGlyphOpen && (
          <BulkGlyphMarkDialog
            open={bulkGlyphOpen}
            projectId={projectId}
            pageIndex={pageIndex}
            onClose={() => setBulkGlyphOpen(false)}
          />
        )}
      </ButtonGroup>
    </div>
  );
}

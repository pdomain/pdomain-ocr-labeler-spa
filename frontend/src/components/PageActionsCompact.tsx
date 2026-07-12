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
} from "../hooks/usePageMutations";
import { usePage } from "../hooks/usePage";
import { useJobProgress } from "../hooks/useJobProgress";
import { useJobCompletionInvalidation } from "../hooks/useJobCompletionInvalidation";
import { dialogStore } from "../stores/dialog-store";
import { toast } from "../lib/toast";
import { BulkGlyphMarkDialog } from "./glyph/BulkGlyphMarkDialog";

export interface PageActionsCompactProps {
  projectId: string;
  pageIndex: number;
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
  const [bulkGlyphOpen, setBulkGlyphOpen] = useState(false);
  const jobProgress = useJobProgress(activeJobId);
  const saveProjectProgress = useJobProgress(saveProjectJobId);
  const rotateProgress = useJobProgress(rotateJobId);

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
    onRunning: (jobId, event) => {
      const msg = event.progress?.message ?? "Running OCR…";
      void import("sonner").then(({ toast: sonnerToast }) => {
        sonnerToast.loading(msg, { id: jobId });
      });
    },
  });

  // Save-project completion: fetch the job payload to check skipped_pages,
  // then show a warning (if any pages were skipped) or success toast.
  useJobCompletionInvalidation({
    activeJobId: saveProjectJobId,
    jobProgress: saveProjectProgress,
    setActiveJobId: setSaveProjectJobId,
    invalidationKey: ["page", projectId, pageIndex],
    onComplete: (jobId) => {
      void fetch(`/api/jobs/${encodeURIComponent(jobId)}`)
        .then((r) => r.json())
        .then((job: { payload?: { skipped_pages?: number; skipped_indices?: number[] } }) => {
          const skipped = job.payload?.skipped_pages ?? 0;
          if (skipped > 0) {
            const indices = job.payload?.skipped_indices ?? [];
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
    onRunning: (jobId, event) => {
      const msg = event.progress?.message ?? "Saving project…";
      void import("sonner").then(({ toast: sonnerToast }) => {
        sonnerToast.loading(msg, { id: jobId });
      });
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
    onRunning: (jobId, event) => {
      const msg = event.progress?.message ?? "Rotating…";
      void import("sonner").then(({ toast: sonnerToast }) => {
        sonnerToast.loading(msg, { id: jobId });
      });
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
              void import("sonner").then(({ toast: sonnerToast }) => {
                sonnerToast.loading("Running OCR…", { id: data.job_id });
              });
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
              void import("sonner").then(({ toast: sonnerToast }) => {
                sonnerToast.loading("Running OCR (edited)…", { id: data.job_id });
              });
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
  // S5.2: on completion, reads payload.skipped_pages and shows warning if > 0.
  function handleSaveProject() {
    saveProject.mutate(undefined, {
      onSuccess: (data) => {
        if (data?.job_id) {
          setSaveProjectJobId(data.job_id);
          void import("sonner").then(({ toast: sonnerToast }) => {
            sonnerToast.loading("Saving project…", { id: data.job_id });
          });
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
  function handleAutoRotateAll() {
    autoRotateAll.mutate(undefined, {
      onSuccess: (data) => {
        if (data?.job_id) {
          setRotateJobId(data.job_id);
          void import("sonner").then(({ toast: sonnerToast }) => {
            sonnerToast.loading("Auto-rotating pages…", { id: data.job_id });
          });
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
    "flex items-center gap-1 h-7 px-2.5 rounded border text-[11px] font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed";
  const normal = "border-border-2 bg-bg-raised text-ink-2 hover:bg-bg-surface hover:text-ink-1";
  const accentBtn =
    "border-border-2 bg-bg-raised text-accent hover:border-accent hover:text-accent-ink hover:bg-accent";

  const disabled = isBusy || !projectId;

  /** Inline spinner — shown while this button's job is running. */
  const Spinner = () => (
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
    <div data-testid="page-actions-bar" className="flex">
      <ButtonGroup
        data-testid="page-actions-compact"
        className="flex items-center gap-1 shrink-0"
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
          <DropdownMenuContent align="end" className="min-w-[12rem]">
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
            "px-2 py-0.5 text-[11px] font-semibold rounded bg-bg-raised",
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

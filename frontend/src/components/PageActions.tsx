// PageActions.tsx — horizontal action bar below project navigation controls.
//
// Spec: docs/specs/2026-05-12-page-actions-design.md
// Spec: docs/specs/2026-05-12-auto-rotation-design.md §Manual rotate (M9.1)
// Issues #214, #217, #263
//
// Button layout (left to right):
//   Reload OCR | Reload OCR (Edited) | Save Page | Save Project | Reload |
//   Undo | Redo | Rematch GT | Rotate CCW (↺) | Rotate CW (↻) | Export…
//
// "Load Page" was renamed "Reload" (testid load-page-button unchanged) —
// every mutation auto-persists to the event-store head, so there are no
// "unsaved edits" to discard (spec 2026-06-12-event-store-undo, U-7).
//
// Right side: page-name label, source badge, rotation badge.
//   rotation-badge: always in DOM; visible only when rotation_degrees != 0.
//   Shows "↻ {deg}° {source}" — gray for auto, blue for manual.
//   Clicking auto badge fires onRotateRevert (reverse rotation POST).
//
// All buttons are disabled while isBusy=true.
// "Reload OCR (Edited)" is additionally disabled when hasEditedImage=false.
//
// Hotkeys (#217):
//   Mod+R  → Reload OCR  (skipped when isBusy)
//   Mod+Shift+R → Reload OCR Edited (skipped when isBusy or !hasEditedImage)
//   E      → Export dialog (skipped when isBusy)
//
// data-testids (driver-contract invariants):
//   reload-ocr-button, reload-ocr-edited-button, save-page-button,
//   save-project-button, load-page-button, undo-button, redo-button,
//   rematch-gt-button, export-button,
//   page-source-badge, page-name-label, rotation-badge,
//   rotate-ccw-button, rotate-cw-button, rotate-180-button

import { useHotkey } from "../hooks/useHotkey";
import type { components } from "../api/types";

/** ops PageRecord uses source: string; kept for label lookup */
type PageSource = "ocr" | "cached_ocr" | "filesystem" | "fallback";
type RotationSource = components["schemas"]["RotationSource"];

/** Human-readable labels for each PageSource value. */
const PAGE_SOURCE_LABELS: Record<PageSource, string> = {
  ocr: "OCR",
  cached_ocr: "CACHED",
  filesystem: "LABELED",
  fallback: "FALLBACK",
};

/** Tailwind color classes per source value. */
const PAGE_SOURCE_COLORS: Record<PageSource, string> = {
  ocr: "text-status-ocr",
  cached_ocr: "text-ink-3",
  filesystem: "text-status-exact",
  fallback: "text-status-mismatch",
};

interface PageActionsProps {
  /** True while any page mutation or background job is active. */
  isBusy?: boolean | undefined;
  /** Whether an edited image exists for this page (gates Reload OCR Edited). */
  hasEditedImage?: boolean | undefined;
  /** Source lane for the current page data. */
  pageSource?: PageSource | null | undefined;
  /** Human-readable provenance one-liner shown as the source badge tooltip.
   *  Assembled by the backend from saved_at + OCR engine + model names.
   *  When absent, the badge has no tooltip. */
  provenanceSummary?: string | null | undefined;
  /** Display name for the current page (e.g. "page_001.png"). */
  pageName?: string | null | undefined;
  /** Cumulative rotation applied to the current page (0 = original). */
  rotationDegrees?: number | undefined;
  /** How the current rotation was determined. */
  rotationSource?: RotationSource | null | undefined;

  /** Callback: user clicked Reload OCR. */
  onReloadOcr?: (() => void) | undefined;
  /** Callback: user clicked Reload OCR (Edited). */
  onReloadOcrEdited?: (() => void) | undefined;
  /** Callback: user clicked Save Page. */
  onSavePage?: (() => void) | undefined;
  /** Callback: user clicked Save Project. */
  onSaveProject?: (() => void) | undefined;
  /** Callback: user clicked Reload (testid load-page-button, U-7). */
  onLoadPage?: (() => void) | undefined;
  /** Whether a previous version exists to undo to (PagePayload.history). */
  undoAvailable?: boolean | undefined;
  /** Whether an undone version exists to redo to. */
  redoAvailable?: boolean | undefined;
  /** Callback: user clicked Undo (or Mod+Z). */
  onUndo?: (() => void) | undefined;
  /** Callback: user clicked Redo (or Mod+Shift+Z). */
  onRedo?: (() => void) | undefined;
  /** Callback: user clicked Rematch GT. */
  onRematchGt?: (() => void) | undefined;
  /** Callback: user clicked Export. */
  onExport?: (() => void) | undefined;
  /** Callback: user clicked Rotate CW (+90°). */
  onRotateCw?: (() => void) | undefined;
  /** Callback: user clicked Rotate CCW (-90°). */
  onRotateCcw?: (() => void) | undefined;
  /** Callback: user clicked Rotate 180°. */
  onRotate180?: (() => void) | undefined;
  /** Callback: user clicked the rotation badge (revert auto rotation). */
  onRotateRevert?: (() => void) | undefined;
}

/**
 * Horizontal action bar for page-level operations.
 *
 * All action buttons are disabled while `isBusy` is true.
 * "Reload OCR (Edited)" is also disabled when `hasEditedImage` is false.
 * Rotate buttons wired in M9.1 (#263); rotation-badge always in DOM.
 */
export function PageActions({
  isBusy = false,
  hasEditedImage = false,
  pageSource,
  provenanceSummary,
  pageName,
  rotationDegrees = 0,
  rotationSource = null,
  onReloadOcr,
  onReloadOcrEdited,
  onSavePage,
  onSaveProject,
  onLoadPage,
  undoAvailable = false,
  redoAvailable = false,
  onUndo,
  onRedo,
  onRematchGt,
  onExport,
  onRotateCw,
  onRotateCcw,
  onRotate180,
  onRotateRevert,
}: PageActionsProps) {
  const source: PageSource = pageSource ?? "ocr";
  const isRotated = rotationDegrees !== 0;

  // Hotkeys #217 — fire only when the corresponding button would be enabled
  useHotkey("mod+r", () => {
    if (!isBusy) onReloadOcr?.();
  });
  useHotkey("mod+shift+r", () => {
    if (!isBusy && hasEditedImage) onReloadOcrEdited?.();
  });
  useHotkey("e", () => {
    if (!isBusy) onExport?.();
  });

  return (
    <div
      data-testid="page-actions-bar"
      className="flex items-center gap-1 px-2 py-1 bg-bg-raised border-b border-border-1 flex-wrap"
    >
      {/* Left: action buttons */}
      <div className="flex items-center gap-1 flex-wrap">
        <ActionButton
          testid="reload-ocr-button"
          disabled={isBusy}
          onClick={onReloadOcr}
          title="Reload OCR"
        >
          Reload OCR
        </ActionButton>

        <ActionButton
          testid="reload-ocr-edited-button"
          disabled={isBusy || !hasEditedImage}
          onClick={onReloadOcrEdited}
          title={hasEditedImage ? "Reload OCR using edited image" : "No edited image available"}
        >
          Reload OCR (Edited)
        </ActionButton>

        <Separator />

        <ActionButton
          testid="save-page-button"
          disabled={isBusy}
          onClick={onSavePage}
          title="Save Page (Ctrl+S)"
        >
          Save Page
        </ActionButton>

        <ActionButton
          testid="save-project-button"
          disabled={isBusy}
          onClick={onSaveProject}
          title="Save Project"
        >
          Save Project
        </ActionButton>

        <ActionButton
          testid="load-page-button"
          disabled={isBusy}
          onClick={onLoadPage}
          title="Reload page from the stored version"
        >
          Reload
        </ActionButton>

        {/* Undo/redo — event-store undo (spec 2026-06-12, U-1..U-3). */}
        <ActionButton
          testid="undo-button"
          disabled={isBusy || !undoAvailable}
          onClick={onUndo}
          title="Undo (Ctrl+Z)"
          aria-label="Undo"
        >
          Undo
        </ActionButton>
        <ActionButton
          testid="redo-button"
          disabled={isBusy || !redoAvailable}
          onClick={onRedo}
          title="Redo (Ctrl+Shift+Z)"
          aria-label="Redo"
        >
          Redo
        </ActionButton>

        <ActionButton
          testid="rematch-gt-button"
          disabled={isBusy}
          onClick={onRematchGt}
          title="Re-run GT alignment"
        >
          Rematch GT
        </ActionButton>

        {/* Rotate buttons — M9.1 (#263) */}
        <ActionButton
          testid="rotate-ccw-button"
          disabled={isBusy}
          onClick={onRotateCcw}
          title="Rotate counter-clockwise (-90°)"
          aria-label="Rotate counter-clockwise"
        >
          ↺
        </ActionButton>
        <ActionButton
          testid="rotate-cw-button"
          disabled={isBusy}
          onClick={onRotateCw}
          title="Rotate clockwise (+90°)"
          aria-label="Rotate clockwise"
        >
          ↻
        </ActionButton>
        <ActionButton
          testid="rotate-180-button"
          disabled={isBusy}
          onClick={onRotate180}
          title="Rotate 180°"
          aria-label="Rotate 180 degrees"
        >
          180°
        </ActionButton>

        <Separator />

        <ActionButton
          testid="export-button"
          disabled={isBusy}
          onClick={onExport}
          title="Export… (E)"
        >
          Export…
        </ActionButton>
      </div>

      {/* Right: page name + source badge */}
      <div className="ml-auto flex items-center gap-2">
        {pageName && (
          <span
            data-testid="page-name-label"
            className="text-xs text-ink-2 font-mono"
            title={pageName}
          >
            {pageName}
          </span>
        )}

        <span
          data-testid="page-source-badge"
          title={provenanceSummary ?? undefined}
          className={[
            "px-2 py-0.5 text-xs font-semibold rounded bg-bg-raised",
            PAGE_SOURCE_COLORS[source],
          ].join(" ")}
        >
          {PAGE_SOURCE_LABELS[source]}
        </span>

        {/* rotation-badge: always in DOM; visible only when rotated.
            Spec §19: gray for auto, blue for manual.
            Clicking auto badge reverts (fires onRotateRevert). */}
        <button
          data-testid="rotation-badge"
          style={
            !isRotated
              ? { display: "none" }
              : rotationSource === "manual"
                ? { background: "color-mix(in srgb, var(--status-ocr) 8%, var(--bg-surface))" }
                : { background: "var(--bg-raised)" }
          }
          onClick={rotationSource === "auto" ? onRotateRevert : undefined}
          disabled={rotationSource !== "auto" || isBusy}
          aria-label={
            rotationSource === "auto"
              ? `Auto-rotated ${rotationDegrees}° clockwise. Click to revert.`
              : `Manually rotated ${rotationDegrees}° clockwise.`
          }
          title={
            rotationSource === "auto"
              ? `Auto-rotated ${rotationDegrees}° clockwise. Click to revert.`
              : `Manually rotated ${rotationDegrees}° clockwise.`
          }
          className={[
            "px-2 py-0.5 text-xs font-semibold rounded",
            rotationSource === "manual" ? "text-accent" : "text-ink-3",
            "disabled:cursor-default",
          ].join(" ")}
        >
          ↻ {rotationDegrees}° {rotationSource ?? ""}
        </button>
      </div>
    </div>
  );
}

// ─── Internal helpers ──────────────────────────────────────────────────────

interface ActionButtonProps {
  testid: string;
  disabled: boolean;
  onClick: (() => void) | undefined;
  title?: string;
  /** For icon-only buttons: exposed as aria-label to screen readers. */
  "aria-label"?: string;
  style?: React.CSSProperties;
  children: React.ReactNode;
}

function ActionButton({
  testid,
  disabled,
  onClick,
  title,
  "aria-label": ariaLabel,
  style,
  children,
}: ActionButtonProps) {
  return (
    <button
      data-testid={testid}
      disabled={disabled}
      onClick={onClick}
      title={title}
      aria-label={ariaLabel}
      style={style}
      className="px-2 py-1 text-xs rounded border border-border-2 bg-bg-surface hover:bg-bg-raised disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
    >
      {children}
    </button>
  );
}

function Separator() {
  return <div className="w-px h-5 bg-border-2 mx-1" aria-hidden="true" />;
}

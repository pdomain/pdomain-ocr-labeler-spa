// PageActions.tsx — horizontal action bar below project navigation controls.
//
// Spec: docs/specs/2026-05-12-page-actions-design.md
// Spec: docs/specs/2026-05-12-auto-rotation-design.md §Manual rotate (M9.1)
// Issues #214, #217, #263
//
// Button layout (left to right):
//   Reload OCR | Reload OCR (Edited) | Save Page | Save Project | Load Page |
//   Rematch GT | Rotate CCW (↺) | Rotate CW (↻) | Export…
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
//   save-project-button, load-page-button, rematch-gt-button, export-button,
//   page-source-badge, page-name-label, rotation-badge,
//   rotate-ccw-button, rotate-cw-button

import { useHotkey } from "../hooks/useHotkey";
import type { components } from "../api/types";

type PageSource = components["schemas"]["PageSource"];
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
  ocr: "bg-blue-100 text-blue-800",
  cached_ocr: "bg-purple-100 text-purple-800",
  filesystem: "bg-green-100 text-green-800",
  fallback: "bg-red-100 text-red-800",
};

interface PageActionsProps {
  /** True while any page mutation or background job is active. */
  isBusy?: boolean;
  /** Whether an edited image exists for this page (gates Reload OCR Edited). */
  hasEditedImage?: boolean;
  /** Source lane for the current page data. */
  pageSource?: PageSource | null;
  /** Display name for the current page (e.g. "page_001.png"). */
  pageName?: string | null;
  /** Cumulative rotation applied to the current page (0 = original). */
  rotationDegrees?: number;
  /** How the current rotation was determined. */
  rotationSource?: RotationSource | null;

  /** Callback: user clicked Reload OCR. */
  onReloadOcr?: () => void;
  /** Callback: user clicked Reload OCR (Edited). */
  onReloadOcrEdited?: () => void;
  /** Callback: user clicked Save Page. */
  onSavePage?: () => void;
  /** Callback: user clicked Save Project. */
  onSaveProject?: () => void;
  /** Callback: user clicked Load Page. */
  onLoadPage?: () => void;
  /** Callback: user clicked Rematch GT. */
  onRematchGt?: () => void;
  /** Callback: user clicked Export. */
  onExport?: () => void;
  /** Callback: user clicked Rotate CW (+90°). */
  onRotateCw?: () => void;
  /** Callback: user clicked Rotate CCW (-90°). */
  onRotateCcw?: () => void;
  /** Callback: user clicked the rotation badge (revert auto rotation). */
  onRotateRevert?: () => void;
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
  pageName,
  rotationDegrees = 0,
  rotationSource = null,
  onReloadOcr,
  onReloadOcrEdited,
  onSavePage,
  onSaveProject,
  onLoadPage,
  onRematchGt,
  onExport,
  onRotateCw,
  onRotateCcw,
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
      className="flex items-center gap-1 px-2 py-1 bg-gray-100 border-b border-gray-200 flex-wrap"
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
          title="Load Page from disk"
        >
          Load Page
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
        >
          ↺
        </ActionButton>
        <ActionButton
          testid="rotate-cw-button"
          disabled={isBusy}
          onClick={onRotateCw}
          title="Rotate clockwise (+90°)"
        >
          ↻
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
            className="text-xs text-gray-600 font-mono"
            title={pageName}
          >
            {pageName}
          </span>
        )}

        <span
          data-testid="page-source-badge"
          className={["px-2 py-0.5 text-xs font-semibold rounded", PAGE_SOURCE_COLORS[source]].join(
            " ",
          )}
        >
          {PAGE_SOURCE_LABELS[source]}
        </span>

        {/* rotation-badge: always in DOM; visible only when rotated.
            Spec §19: gray for auto, blue for manual.
            Clicking auto badge reverts (fires onRotateRevert). */}
        <button
          data-testid="rotation-badge"
          style={isRotated ? undefined : { display: "none" }}
          onClick={rotationSource === "auto" ? onRotateRevert : undefined}
          disabled={rotationSource !== "auto" || isBusy}
          title={
            rotationSource === "auto"
              ? `Auto-rotated ${rotationDegrees}° clockwise. Click to revert.`
              : `Manually rotated ${rotationDegrees}° clockwise.`
          }
          className={[
            "px-2 py-0.5 text-xs font-semibold rounded",
            rotationSource === "manual" ? "bg-blue-100 text-blue-800" : "bg-gray-100 text-gray-800",
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
  style?: React.CSSProperties;
  children: React.ReactNode;
}

function ActionButton({ testid, disabled, onClick, title, style, children }: ActionButtonProps) {
  return (
    <button
      data-testid={testid}
      disabled={disabled}
      onClick={onClick}
      title={title}
      style={style}
      className="px-2 py-1 text-xs rounded border border-gray-300 bg-white hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
    >
      {children}
    </button>
  );
}

function Separator() {
  return <div className="w-px h-5 bg-gray-300 mx-1" aria-hidden="true" />;
}

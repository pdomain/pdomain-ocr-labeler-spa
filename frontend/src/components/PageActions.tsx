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
  /** Callback: user clicked Load Page. */
  onLoadPage?: (() => void) | undefined;
  /** Callback: user clicked Rematch GT. */
  onRematchGt?: (() => void) | undefined;
  /** Callback: user clicked Export. */
  onExport?: (() => void) | undefined;
  /** Callback: user clicked Rotate CW (+90°). */
  onRotateCw?: (() => void) | undefined;
  /** Callback: user clicked Rotate CCW (-90°). */
  onRotateCcw?: (() => void) | undefined;
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

// ─── PageActionsCompact ────────────────────────────────────────────────────────
//
// P1.b (Gap 4, 7): compact header action row — Reload OCR, Rematch GT,
// ✓ Save Page, Export ▾. Uses design-token classes matching the hi-fi header.
// The full PageActions bar remains rendered (hidden) for driver-contract
// testid preservation (§2.5).
//
// These compact buttons do NOT carry driver-contract testids — the real
// testids live on the hidden PageActions instance. The compact buttons exist
// purely as visible UI affordances.

export interface PageActionsCompactProps {
  isBusy?: boolean;
  onReloadOcr?: () => void;
  onRematchGt?: () => void;
  onSavePage?: () => void;
  onExport?: () => void;
}

/**
 * Compact header action buttons (P1.b hi-fi).
 * Reload OCR | Rematch | ✓ Save | Export ▾
 * Visible affordances only; driver-contract testids live on the hidden
 * full PageActions instance.
 */
export function PageActionsCompact({
  isBusy = false,
  onReloadOcr,
  onRematchGt,
  onSavePage,
  onExport,
}: PageActionsCompactProps) {
  const base =
    "flex items-center gap-1 h-7 px-2.5 rounded border text-[11px] font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed";
  const normal = "border-border-2 bg-bg-raised text-ink-2 hover:bg-bg-surface hover:text-ink-1";
  const accent = "border-accent bg-bg-raised text-accent hover:bg-accent hover:text-accent-ink";

  return (
    <div
      data-testid="page-actions-compact"
      className="flex items-center gap-1 shrink-0"
      aria-label="Page actions"
    >
      <button
        type="button"
        aria-label="Reload OCR"
        title="Reload OCR (Ctrl+R)"
        disabled={isBusy}
        onClick={onReloadOcr}
        className={`${base} ${normal}`}
      >
        Reload OCR
      </button>

      <button
        type="button"
        aria-label="Rematch GT"
        title="Rematch GT (Ctrl+G)"
        disabled={isBusy}
        onClick={onRematchGt}
        className={`${base} ${normal}`}
      >
        Rematch
      </button>

      <button
        type="button"
        aria-label="Save page (Ctrl+S)"
        title="Save page (Ctrl+S)"
        disabled={isBusy}
        onClick={onSavePage}
        className={`${base} ${accent}`}
      >
        <span aria-hidden="true">✓</span>
        <span>Save page</span>
      </button>

      <button
        type="button"
        aria-label="Export"
        title="Export (E)"
        disabled={isBusy}
        onClick={onExport}
        className={`${base} ${normal}`}
      >
        Export
        <span aria-hidden="true" className="text-[9px] opacity-70">
          ▾
        </span>
      </button>
    </div>
  );
}

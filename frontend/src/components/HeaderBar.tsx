// HeaderBar.tsx — 56px top chrome, present on every route.
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 9.
//       specs/22-page-surface-wireup.md §3, §6 (issue #309)
//       docs/plans/hifi-gaps-plan.md P1.a (Gaps 1, 3, 5)
// IS-2: added navSlot + actionsSlot props for project-route header wiring.
// P1.a: added projectName breadcrumb + pageMetrics strip.
//
// Layout:
//   Left:   logo glyph + "Projects" link back to / [+ "/" + project-name chip]
//   Center: [navSlot] + [actionsSlot] (project-route injected content)
//   Right:  [metrics strip (project route only)] + theme toggle (Dark/Light/System chips)
//
// 56px height (`h-14`), `bg-bg-page`, `border-b border-border-1`.
// Gap 1: header height 40→56px (DONE).

import type * as React from "react";
import { Link } from "react-router-dom";

import { useThemePreference, useUiPrefs, type ThemePreference } from "../stores/ui-prefs";

// ─── ThemeChips ──────────────────────────────────────────────────────────────

const THEME_CHIPS: { value: ThemePreference; label: string }[] = [
  { value: "dark", label: "Dark" },
  { value: "light", label: "Light" },
  { value: "system", label: "System" },
];

const CHIP_ACTIVE: Record<ThemePreference, string> = {
  dark: "bg-accent text-accent-ink border-accent",
  light: "bg-accent text-accent-ink border-accent",
  system: "bg-accent text-accent-ink border-accent",
};

const CHIP_INACTIVE = "bg-bg-sunk text-ink-2 border-border-2 hover:bg-bg-raised hover:text-ink-1";

function ThemeChips() {
  const theme = useThemePreference();
  return (
    <div
      data-testid="theme-chips"
      className="flex items-center gap-1"
      role="radiogroup"
      aria-label="Theme"
    >
      {THEME_CHIPS.map(({ value, label }) => {
        const active = theme === value;
        return (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={active}
            data-testid={`theme-chip-${value}`}
            onClick={() => {
              useUiPrefs.setTheme(value);
            }}
            className={`px-1.5 py-0.5 rounded border text-[10px] font-medium transition-colors ${active ? CHIP_ACTIVE[value] : CHIP_INACTIVE}`}
          >
            {label}
          </button>
        );
      })}
    </div>
  );
}

// ─── HeaderBar ───────────────────────────────────────────────────────────────

/** Computed per-page word-match metrics passed from AppShell. */
export interface PageMetrics {
  total: number;
  exact: number;
  fuzzy: number;
  mismatch: number;
  validated: number;
  /** Number of words with glyph_annotations !== null (spec §8). Optional — only shown when present. */
  glyphs_reviewed?: number | undefined;
}

export interface HeaderBarProps {
  /**
   * IS-2: Optional slot rendered in the center-left area (after logo).
   * Used to inject ProjectNavigationControls when on a project route.
   */
  navSlot?: React.ReactNode;
  /**
   * IS-2: Optional slot rendered in the center-right area (before the
   * theme toggle). Used to inject PageActionsCompact when on a project route.
   */
  actionsSlot?: React.ReactNode;
  /**
   * P1.a: Project name displayed as a breadcrumb chip after "Projects" link.
   * Only rendered when non-null and truthy.
   */
  projectName?: string | null;
  /**
   * P1.a: Per-page word-match metrics displayed in the header right area.
   * Only rendered when non-null and total > 0.
   */
  pageMetrics?: PageMetrics | null;
  /**
   * S6.2: Resolved project_root path, shown as a visible mono label next to
   * the project breadcrumb on project routes. Only rendered when non-null/truthy.
   */
  projectRoot?: string | null;
}

export default function HeaderBar({
  navSlot,
  actionsSlot,
  projectName,
  pageMetrics,
  projectRoot,
}: HeaderBarProps = {}) {
  return (
    <header
      data-testid="header-bar"
      className="h-14 flex items-center gap-2 px-3 bg-bg-page border-b border-border-1"
    >
      {/* Left: logo + "Projects" link */}
      <Link
        to="/"
        data-testid="header-logo"
        aria-label="OCR Labeler home"
        className="flex items-center gap-1.5 text-ink-1 no-underline shrink-0"
      >
        {/* Gap 2: orange "O" logo badge using --accent token */}
        <span
          aria-hidden
          data-testid="header-logo-badge"
          className="inline-flex items-center justify-center w-6 h-6 rounded bg-accent text-white font-bold text-[13px] select-none leading-none"
        >
          O
        </span>
        <span className="text-heading font-semibold text-ink-1 hidden sm:inline">OCR Labeler</span>
      </Link>

      {/* "Projects" breadcrumb link — always visible, navigates back to / */}
      <Link
        to="/"
        data-testid="projects-home-link"
        className="text-body text-ink-2 hover:text-ink-1 no-underline shrink-0 transition-colors"
      >
        Projects
      </Link>

      {/* P1.a: project name breadcrumb chip — only when on a project route */}
      {projectName && (
        <>
          <span className="text-ink-3 text-[11px] shrink-0">/</span>
          <span
            data-testid="header-project-name"
            className="text-[11px] text-ink-1 font-medium truncate max-w-[200px] shrink-0"
          >
            {projectName}
          </span>
        </>
      )}

      {/* S6.2: resolved project_root path label — only on project routes */}
      {projectRoot && (
        <span
          data-testid="project-root-label"
          className="text-[11px] text-ink-3 font-mono truncate max-w-[260px] shrink-0"
          title={projectRoot}
        >
          {projectRoot}
        </span>
      )}

      {/* Center-left: navigation slot (project route only) */}
      {navSlot}

      {/* Spacer */}
      <div className="flex-1 min-w-0" />

      {/* Center-right: actions slot (project route only) */}
      {actionsSlot}

      {/* P1.a: metrics strip — only when on a project route with loaded words */}
      {pageMetrics && pageMetrics.total > 0 && (
        <div
          data-testid="header-metrics-strip"
          className="flex items-center gap-1.5 text-[10px] text-ink-3 shrink-0"
        >
          <span>{pageMetrics.total} words</span>
          <span>·</span>
          <span className="text-status-exact">{pageMetrics.exact} exact</span>
          <span>·</span>
          <span className="text-status-fuzzy">{pageMetrics.fuzzy} fuzzy</span>
          <span>·</span>
          <span className="text-status-mismatch">{pageMetrics.mismatch} ✗</span>
          <span>·</span>
          <span>
            {pageMetrics.validated}/{pageMetrics.total} validated
          </span>
          {pageMetrics.glyphs_reviewed !== undefined && (
            <>
              <span>·</span>
              <span>
                {pageMetrics.glyphs_reviewed}/{pageMetrics.total} glyphs
              </span>
            </>
          )}
        </div>
      )}

      {/* Right: theme toggle */}
      {/* D-046: ocr-config-trigger-button removed from HeaderBar; restored in PageActionsCompact (#405) */}
      <div className="shrink-0">
        <ThemeChips />
      </div>

      {/*
       * Spec 22 §10 — driver-contract preservation.
       *
       * Nav-control stubs live here so the testids are reachable on every
       * route (including the root route). The block remains `display:none`
       * and carries `data-testid-stub="true"` so the driver pre-pass can
       * distinguish them from the real controls. The real
       * ProjectNavigationControls is rendered inside ProjectPage and does NOT
       * carry `data-testid-stub` — drivers select it via
       * `[data-testid="nav-prev-button"]:not([data-testid-stub])`.
       *
       * Source-folder stubs removed (#294): the real SourceFolderDialog is
       * now mounted in App.tsx and the source-folder-button in
       * ProjectLoadControls opens it.
       */}
      <div style={{ display: "none" }}>
        {/*
         * D-046 (2026-05-21): project-select, load-project-button, source-folder-button,
         * and ocr-config-trigger-button stubs REMOVED from HeaderBar. These controls
         * now live at their real locations:
         *   project-select / load-project-button → ProjectLoadControls (RootPage)
         *   source-folder-button → ProjectLoadControls (breadcrumb mode)
         *   ocr-config-trigger-button → dialogStore.open("ocrConfig") from project-page context
         * See specs/17-decisions.md D-046 and docs/architecture/13-driver-contract.md §2.1.
         */}

        {/* Source-folder dialog stubs — always present in DOM, even when dialog is closed */}
        <span
          data-testid="source-folder-current-path-label"
          data-testid-stub="true"
          aria-label="Current folder path (stub)"
        />
        <input
          data-testid="source-folder-path-input"
          data-testid-stub="true"
          aria-label="Folder path (stub)"
          readOnly
        />
        <button
          type="button"
          data-testid="source-folder-home-button"
          data-testid-stub="true"
          aria-label="Go to home folder (stub)"
        />
        <button
          type="button"
          data-testid="source-folder-up-button"
          data-testid-stub="true"
          aria-label="Go up one folder (stub)"
        />
        <button
          type="button"
          data-testid="source-folder-open-typed-button"
          data-testid-stub="true"
          aria-label="Open typed path (stub)"
        />
        <button
          type="button"
          data-testid="source-folder-use-current-button"
          data-testid-stub="true"
          aria-label="Use current folder (stub)"
        />
        <button
          type="button"
          data-testid="source-folder-cancel-button"
          data-testid-stub="true"
          aria-label="Cancel source folder dialog (stub)"
        />
        <button
          type="button"
          data-testid="source-folder-apply-button"
          data-testid-stub="true"
          aria-label="Apply source folder selection (stub)"
        />

        {/* OCR config modal stubs — always present in DOM, even when modal is closed */}
        <select
          data-testid="ocr-detection-model-select"
          data-testid-stub="true"
          aria-label="OCR detection model (stub)"
        />
        <select
          data-testid="ocr-recognition-model-select"
          data-testid-stub="true"
          aria-label="OCR recognition model (stub)"
        />
        <input
          data-testid="ocr-hf-revision-input"
          data-testid-stub="true"
          aria-label="HuggingFace model revision (stub)"
          readOnly
        />
        <button
          type="button"
          data-testid="ocr-rescan-models-button"
          data-testid-stub="true"
          aria-label="Rescan available models (stub)"
        />
        <button
          type="button"
          data-testid="ocr-config-cancel-button"
          data-testid-stub="true"
          aria-label="Cancel OCR config (stub)"
        />
        <button
          type="button"
          data-testid="ocr-config-apply-button"
          data-testid-stub="true"
          aria-label="Apply OCR config (stub)"
        />

        {/* Nav stubs — always present in DOM */}
        <button
          data-testid="nav-prev-button"
          data-testid-stub="true"
          aria-label="Previous page (stub)"
        >
          Prev
        </button>
        <button data-testid="nav-next-button" data-testid-stub="true" aria-label="Next page (stub)">
          Next
        </button>
        <button
          data-testid="nav-goto-button"
          data-testid-stub="true"
          aria-label="Go to page (stub)"
        >
          Go
        </button>
        <input
          data-testid="nav-page-input"
          data-testid-stub="true"
          aria-label="Page number (stub)"
        />
        <span data-testid="nav-page-total-label" data-testid-stub="true">
          / 0
        </span>
      </div>
    </header>
  );
}

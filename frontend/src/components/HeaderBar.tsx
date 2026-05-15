// HeaderBar.tsx — 56px top chrome, present on every route.
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 9.
//       specs/22-page-surface-wireup.md §3, §6 (issue #309)
//       docs/plans/hifi-gaps-plan.md P1.a (Gaps 1, 3, 5)
// IS-2: added navSlot + actionsSlot props for project-route header wiring.
//
// Layout:
//   Left:   logo glyph + Projects / <project-name> breadcrumb chip (project routes)
//   Center: [navSlot] metrics strip + [actionsSlot] dialog trigger buttons
//   Right:  UserMenu (avatar + caret) — Theme stub + Sign out
//
// 56px height (`h-14`), `bg-bg-page`, `border-b border-border-1`.
// Gap 1: header height 40→56px (DONE).
// Gap 3: Projects / <name> breadcrumb in left area.
// Gap 5: metrics strip pill row (N words · N exact · N fuzzy · N ✗ · N/M validated).

import type * as React from "react";
import { Link, useMatch } from "react-router-dom";
import { ChevronDown } from "lucide-react";

import ProjectLoadControls from "./ProjectLoadControls";
import { useProject } from "../hooks/useProject";
import { usePage } from "../hooks/usePage";
import { dialogStore } from "../stores/dialog-store";
import { useThemePreference, useUiPrefs, type ThemePreference } from "../stores/ui-prefs";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "./ui/dropdown-menu";

// ─── project-route hook ──────────────────────────────────────────────────────

interface ProjectRouteInfo {
  /** True when no project is loaded or the project query is pending/errored. */
  controlsDisabled: boolean;
  /**
   * Human-readable project name (last path segment of project_root) when a
   * project is loaded; undefined otherwise. Drives breadcrumb mode in
   * ProjectLoadControls.
   */
  projectName: string | undefined;
  /** 0-based page index when on a page route; undefined otherwise. */
  pageIndex: number | undefined;
  /** Project identifier string when on a project route; undefined otherwise. */
  projectId: string | undefined;
}

function useProjectRouteInfo(): ProjectRouteInfo {
  // Match either page-no or page-idx variants and the project root.
  const matchPageNo = useMatch("/projects/:projectId/pages/pageno/:pageNo");
  const matchPageIdx = useMatch("/projects/:projectId/pages/index/:idx0");
  const matchProject = useMatch("/projects/:projectId");
  const projectId =
    matchPageNo?.params.projectId ??
    matchPageIdx?.params.projectId ??
    matchProject?.params.projectId;

  // Derive 0-based page index from URL.
  const pageNo = matchPageNo?.params.pageNo;
  const idx0Raw = matchPageIdx?.params.idx0;
  let pageIndex: number | undefined;
  if (pageNo !== undefined) {
    const n = parseInt(pageNo, 10);
    if (Number.isFinite(n) && n >= 1) pageIndex = n - 1;
  } else if (idx0Raw !== undefined) {
    const n = parseInt(idx0Raw, 10);
    if (Number.isFinite(n) && n >= 0) pageIndex = n;
  }

  const { data, isLoading, isError } = useProject(projectId);

  if (!projectId || isLoading || isError || !data) {
    return { controlsDisabled: true, projectName: undefined, pageIndex, projectId };
  }

  // Derive display label: last path segment of project_root, or project_id.
  const label = data.project_root.split("/").filter(Boolean).pop() ?? projectId;

  return { controlsDisabled: false, projectName: label, pageIndex, projectId };
}

// ─── MetricsStrip ─────────────────────────────────────────────────────────────

interface PageMetrics {
  totalWords: number;
  exactCount: number;
  fuzzyCount: number;
  mismatchCount: number;
  validatedCount: number;
}

function usePageMetrics(
  projectId: string | undefined,
  pageIndex: number | undefined,
): PageMetrics | null {
  const { data } = usePage(projectId, pageIndex);
  if (!data?.line_matches?.length) return null;

  let totalWords = 0;
  let exactCount = 0;
  let fuzzyCount = 0;
  let mismatchCount = 0;
  let validatedCount = 0;

  for (const lm of data.line_matches) {
    totalWords += lm.total_word_count;
    exactCount += lm.exact_count;
    fuzzyCount += lm.fuzzy_count;
    mismatchCount += lm.mismatch_count;
    validatedCount += lm.validated_word_count;
  }

  return { totalWords, exactCount, fuzzyCount, mismatchCount, validatedCount };
}

interface MetricsPillProps {
  label: string;
  value: number;
  colorClass: string;
}

function MetricsPill({ label, value, colorClass }: MetricsPillProps) {
  return (
    <span
      className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium ${colorClass}`}
    >
      <span className="tabular-nums">{value}</span>
      <span className="text-[9px] opacity-70">{label}</span>
    </span>
  );
}

interface MetricsStripProps {
  projectId: string | undefined;
  pageIndex: number | undefined;
}

export function MetricsStrip({ projectId, pageIndex }: MetricsStripProps) {
  const metrics = usePageMetrics(projectId, pageIndex);
  if (!metrics) return null;

  const { totalWords, exactCount, fuzzyCount, mismatchCount, validatedCount } = metrics;

  return (
    <div
      data-testid="metrics-strip"
      className="flex items-center gap-1 shrink-0"
      aria-label={`Page metrics: ${totalWords} words, ${exactCount} exact, ${fuzzyCount} fuzzy, ${mismatchCount} mismatched, ${validatedCount} of ${totalWords} validated`}
    >
      <MetricsPill
        label="words"
        value={totalWords}
        colorClass="bg-bg-raised text-ink-2 border border-border-2"
      />
      <MetricsPill
        label="exact"
        value={exactCount}
        colorClass="text-status-exact border border-border-2 bg-bg-raised"
      />
      <MetricsPill
        label="fuzzy"
        value={fuzzyCount}
        colorClass="text-status-fuzzy border border-border-2 bg-bg-raised"
      />
      <MetricsPill
        label="✗"
        value={mismatchCount}
        colorClass="text-status-mismatch border border-border-2 bg-bg-raised"
      />
      <span
        data-testid="metrics-validated-pill"
        className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium text-accent border border-border-2 bg-bg-raised"
      >
        <span className="tabular-nums">
          {validatedCount}/{totalWords}
        </span>
        <span className="text-[9px] opacity-70">validated</span>
      </span>
    </div>
  );
}

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
            onClick={() => useUiPrefs.setTheme(value)}
            className={`px-1.5 py-0.5 rounded border text-[10px] font-medium transition-colors ${active ? CHIP_ACTIVE[value] : CHIP_INACTIVE}`}
          >
            {label}
          </button>
        );
      })}
    </div>
  );
}

// ─── UserMenu ────────────────────────────────────────────────────────────────

function UserMenu() {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          data-testid="user-menu-trigger"
          aria-label="User menu"
          className="flex items-center gap-1 h-7 px-2 rounded-md bg-bg-raised border border-border-2 text-ink-2 text-body hover:bg-bg-surface transition-colors"
        >
          {/* Avatar circle placeholder */}
          <span
            aria-hidden
            className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-accent text-accent-ink text-[9px] font-bold select-none"
          >
            U
          </span>
          <ChevronDown className="w-3 h-3 shrink-0" aria-hidden />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="bg-bg-surface border-border-2 text-ink-1">
        {/* Theme row — Slice 24: 3-state selector */}
        <DropdownMenuItem
          data-testid="user-menu-theme-item"
          className="text-body text-ink-1 focus:bg-bg-raised focus:text-ink-1 flex items-center justify-between gap-2"
          onSelect={(e) => e.preventDefault()}
        >
          <span className="text-ink-2 text-[10px] uppercase tracking-wide shrink-0">Theme</span>
          <ThemeChips />
        </DropdownMenuItem>
        <DropdownMenuSeparator className="bg-border-1" />
        <DropdownMenuItem
          data-testid="user-menu-signout-item"
          className="text-body text-ink-1 focus:bg-bg-raised focus:text-ink-1"
        >
          Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

// ─── HeaderBar ───────────────────────────────────────────────────────────────

export interface HeaderBarProps {
  /**
   * IS-2: Optional slot rendered in the center-left area (after logo, before
   * ProjectLoadControls). Used to inject ProjectNavigationControls when on a
   * project route.
   */
  navSlot?: React.ReactNode;
  /**
   * IS-2: Optional slot rendered in the center-right area (before the
   * UserMenu divider). Used to inject PageActionsCompact when on a project
   * route.
   */
  actionsSlot?: React.ReactNode;
}

export default function HeaderBar({ navSlot, actionsSlot }: HeaderBarProps = {}) {
  const {
    controlsDisabled: isControlsDisabled,
    projectName,
    pageIndex,
    projectId,
  } = useProjectRouteInfo();

  return (
    <header
      data-testid="header-bar"
      className="h-14 flex items-center gap-2 px-3 bg-bg-page border-b border-border-1"
    >
      {/* Left: logo */}
      <Link
        to="/"
        data-testid="header-logo"
        aria-label="OCR Labeler home"
        className="flex items-center gap-1.5 text-ink-1 no-underline shrink-0"
      >
        {/* Glyph placeholder — real asset in a later slice */}
        <span aria-hidden className="text-accent font-bold text-heading select-none">
          &#9673;
        </span>
        <span className="text-heading font-semibold text-ink-1 hidden sm:inline">OCR Labeler</span>
      </Link>

      {/* Center-left: navigation slot (project route only) */}
      {navSlot}

      {/* Center: load controls + metrics strip + dialog triggers */}
      <div className="flex items-center gap-2 flex-1 min-w-0">
        <ProjectLoadControls projectName={projectName} />

        {/* Metrics strip — Gap 5: visible when on a page route */}
        {projectId !== undefined && pageIndex !== undefined && (
          <MetricsStrip projectId={projectId} pageIndex={pageIndex} />
        )}

        {/* Center-right: actions slot (project route only) */}
        {actionsSlot}

        <button
          type="button"
          data-testid="ocr-config-trigger-button"
          aria-label="OCR configuration"
          disabled={isControlsDisabled}
          onClick={() => dialogStore.open("ocrConfig")}
          className="px-2 py-1 text-sm border rounded disabled:opacity-50"
        >
          {/* SlidersIcon placeholder */}
          &#9881;
        </button>

        <button
          type="button"
          data-testid="export-trigger-button"
          aria-label="Export"
          disabled={isControlsDisabled}
          onClick={() => dialogStore.open("export")}
          className="px-2 py-1 text-sm border rounded disabled:opacity-50"
        >
          {/* file_download glyph placeholder */}
          &#11015;
        </button>

        <button
          type="button"
          data-testid="hotkey-help-trigger-button"
          aria-label="Hotkey help (?)"
          onClick={() => dialogStore.open("hotkeyHelp")}
          className="px-2 py-1 text-sm border rounded"
        >
          {/* keyboard glyph placeholder */}
          &#9000;
        </button>
      </div>

      {/* Right: UserMenu */}
      <div className="shrink-0">
        <UserMenu />
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

// HeaderBar.tsx — chrome-only top bar, present on every route.
// Spec: docs/specs/2026-06-14-labeler-spa-header-to-workspace-toolbar-design.md
//       specs/17-decisions.md D-047 (header → workspace-toolbar move),
//       D-048 (theme-chip relocation to SettingsModal Appearance panel)
//
// M1 of the header→workspace-toolbar realignment slims HeaderBar to pure
// pdomain-ui-style chrome. The document/page-scoped controls (navSlot,
// searchSlot, actionsSlot, the metrics strip, the theme chips) were moved out:
//   - page navigation / page actions / metrics → WorkspaceToolbar band
//     (StageToolbar at the top of the project route body).
//   - ⌘K QuickSearch → Drawer worklist-header slot.
//   - theme → pdomain-ui SettingsModal Appearance panel (UIPrefs owns theme;
//     the AppShell ⚙ gear opens it). Local ThemeChips removed (D-048).
//
// Visible layout (chrome only):
//   Left:   logo glyph + "OCR Labeler" + "Projects" link [+ "/" + project-name
//           breadcrumb] [+ resolved project-root path label]
//   (The AppShell injects the LauncherSlot + SettingsSlot ⚙ into its header zone
//   alongside this bar; HeaderBar carries no document-scoped controls.)
//
// The `display:none` driver-contract stub div is retained (D-046): the
// source-folder and OCR-config field stubs, plus the nav stubs, must stay
// reachable on every route (including the root route) for the Playwright driver.

import { Link } from "react-router-dom";

// ─── HeaderBar ───────────────────────────────────────────────────────────────

export interface HeaderBarProps {
  /**
   * P1.a: Project name displayed as a breadcrumb chip after "Projects" link.
   * Only rendered when non-null and truthy.
   */
  projectName?: string | null;
  /**
   * S6.2: Resolved project_root path, shown as a visible mono label next to
   * the project breadcrumb on project routes. Only rendered when non-null/truthy.
   */
  projectRoot?: string | null;
}

export default function HeaderBar({ projectName, projectRoot }: HeaderBarProps = {}) {
  return (
    <header
      data-testid="header-bar"
      className="h-14 flex items-center gap-2 px-3 bg-bg-page border-b border-border-1"
    >
      {/* Left: logo + "Projects" link.
       *
       * P4.1 (parity F12 / A-02 / C13): both home links carry
       * skipSessionRedirect so RootPage renders the project grid instead of
       * session-redirecting straight back to the loaded project. Without
       * this, the grid is unreachable while a session exists and the user
       * cannot switch projects from the UI. */}
      <Link
        to="/"
        state={{ skipSessionRedirect: true }}
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

      {/* "Projects" breadcrumb link — always visible, navigates back to /
       * with skipSessionRedirect so the project grid actually renders (P4.1). */}
      <Link
        to="/"
        state={{ skipSessionRedirect: true }}
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

      {/* Spacer — pushes the AppShell-injected LauncherSlot + SettingsSlot ⚙
       * (rendered by pdomain-ui AppShell into the header zone) to the right. */}
      <div className="flex-1 min-w-0" />

      {/*
       * Spec 22 §10 — driver-contract preservation (D-046).
       *
       * D-046 (2026-05-21): project-select / load-project-button /
       * source-folder-button / ocr-config-trigger-button stubs REMOVED — those
       * controls live at their real locations. The source-folder + OCR-config
       * field stubs below are KEPT (driver-contract §2.2/§2.3).
       *
       * D-049 (2026-06-14): nav-* stubs REMOVED. The real
       * ProjectNavigationControls in WorkspaceToolbar leftSlot is the single
       * source of truth; the `:not([data-testid-stub])` selector convention
       * is retired for nav testids.
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
      </div>
    </header>
  );
}

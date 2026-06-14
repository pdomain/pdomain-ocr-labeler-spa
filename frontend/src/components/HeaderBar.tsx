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
// D-052 (2026-06-14): the last `display:none` stub block is removed. Source-folder
// dialog and OCR-config modal fields now live exclusively on their real, visible
// controls inside the respective modals. To reach them, the driver must first
// OPEN the modal (click `source-folder-button` / `ocr-config-trigger-button`).

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
    </header>
  );
}

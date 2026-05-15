// HeaderBar.tsx — persistent top-chrome, present on every route.
// Spec: specs/22-page-surface-wireup.md §3 (Layout), §6 (Header trigger buttons)
// Issues: #272 (initial), #309 (spec-22-A — trigger buttons)
//
// Contains ProjectLoadControls + three dialog-trigger icon buttons.
// No app title or logo — controls-only, matching the legacy pd-ocr-labeler.
//
// `isControlsDisabled` mirrors legacy `ProjectStateViewModel.is_controls_disabled`
// (no project loaded / mid-load). At header-bar level we don't know the
// current project from a React context, so we read it from the URL via
// react-router's `useMatch` and feed it to `useProject(projectId)`. When no
// projectId is on the URL or the query is still loading / errored, treat
// the project as "not loaded" — controls disabled.

import { useMatch } from "react-router-dom";
import ProjectLoadControls from "./ProjectLoadControls";
import { useProject } from "../hooks/useProject";
import { dialogStore } from "../stores/dialog-store";

function useIsControlsDisabled(): boolean {
  // Match either page-no or page-idx variants and the project root.
  const matchPageNo = useMatch("/projects/:projectId/pages/pageno/:pageNo");
  const matchPageIdx = useMatch("/projects/:projectId/pages/index/:idx0");
  const matchProject = useMatch("/projects/:projectId");
  const projectId =
    matchPageNo?.params.projectId ??
    matchPageIdx?.params.projectId ??
    matchProject?.params.projectId;

  const { data, isLoading, isError } = useProject(projectId);

  // Disabled when no projectId on URL, query still loading, errored, or
  // returned no project.
  if (!projectId) return true;
  if (isLoading || isError) return true;
  if (!data) return true;
  return false;
}

export default function HeaderBar() {
  const isControlsDisabled = useIsControlsDisabled();

  return (
    <header data-testid="header-bar" className="flex items-center gap-2 px-4 py-2 border-b">
      <ProjectLoadControls />

      <button
        type="button"
        data-testid="ocr-config-trigger-button"
        aria-label="OCR configuration"
        disabled={isControlsDisabled}
        onClick={() => dialogStore.open("ocrConfig")}
        className="px-2 py-1 text-sm border rounded disabled:opacity-50"
      >
        {/* SlidersIcon placeholder — icon library added in a later milestone */}
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

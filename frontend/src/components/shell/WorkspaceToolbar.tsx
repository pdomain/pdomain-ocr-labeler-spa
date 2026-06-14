// WorkspaceToolbar.tsx — full-width in-body document/page toolbar band.
//
// Spec: docs/specs/2026-06-14-labeler-spa-header-to-workspace-toolbar-design.md
//       specs/17-decisions.md D-047 (header → workspace-toolbar move)
//
// M1 of the header→workspace-toolbar realignment moves the document/page-scoped
// controls (page navigation, page actions, metrics) out of the AppShell chrome
// header into this band, which mounts at the top of the project route body —
// exactly where today's nav/actions appear. The AppShell header is left as pure
// pdomain-ui chrome ([icon] [name] [breadcrumb] [spacer] [launcher] [⚙]).
//
// This is a thin wrapper over the pdomain-ui `StageToolbar` primitive (the
// documented convention for an in-app document toolbar, used elsewhere as
// FileToolbar / CropToolbar). Slot composition for the project route:
//   leftSlot   = ProjectNavigationControls (page nav)
//   centerSlot = PageActionsCompact        (page actions)
//   rightSlot  = WorkspaceMetrics          (per-page match metrics)
//
// StageToolbar returns null when every slot is empty (WS7 ARIA contract), so the
// real content must be wired by the caller for the band to appear.

import type * as React from "react";
import { StageToolbar } from "@pdomain/pdomain-ui/primitives";

export interface WorkspaceToolbarProps {
  /** Left slot — page navigation (ProjectNavigationControls). */
  leftSlot?: React.ReactNode;
  /** Center slot — page actions (PageActionsCompact). */
  centerSlot?: React.ReactNode;
  /** Right slot — per-page match metrics (WorkspaceMetrics). */
  rightSlot?: React.ReactNode;
}

export function WorkspaceToolbar({ leftSlot, centerSlot, rightSlot }: WorkspaceToolbarProps) {
  return (
    <StageToolbar
      data-testid="workspace-toolbar"
      aria-label="Workspace toolbar"
      leftSlot={leftSlot}
      centerSlot={centerSlot}
      rightSlot={rightSlot}
    />
  );
}

WorkspaceToolbar.displayName = "WorkspaceToolbar";

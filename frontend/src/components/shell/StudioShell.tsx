// StudioShell.tsx — 5-zone CSS grid layout for the Studio shell.
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 8.
//
// Grid template:
//   "header header header header"
//   "rail   drawer  canvas right"
//
// Columns: 64px | var(--drawer-w, 320px) | 1fr | var(--right-w, 520px)
// Rows:    56px | 1fr
//
// The `drawerCollapsed` prop sets --drawer-w to 0px.
// The `rightWidth` prop overrides --right-w (default 520px for word-view).

import type * as React from "react";

export interface StudioShellProps {
  /** Content for the top header zone. */
  header: React.ReactNode;
  /**
   * Height in px for the top header row. Pass 0 when the App-level header
   * handles the top chrome — collapses the row and hides the header div.
   * Defaults to 56.
   */
  headerHeight?: number;
  /** Content for the 64px wide left rail. */
  rail: React.ReactNode;
  /** Content for the collapsible drawer panel. */
  drawer: React.ReactNode;
  /** Content for the main canvas area. */
  canvas: React.ReactNode;
  /** Content for the right panel (word-view: 520px default; block/line: 640px). */
  right: React.ReactNode;
  /** When true, collapses the drawer to 0 width. */
  drawerCollapsed?: boolean;
  /** Override right panel width in px. Defaults to 520 (word-view). Use 640 for block/line views. */
  rightWidth?: number;
}

export function StudioShell({
  header,
  headerHeight = 56,
  rail,
  drawer,
  canvas,
  right,
  drawerCollapsed = false,
  rightWidth,
}: StudioShellProps) {
  const rightWVar = rightWidth !== undefined ? `${rightWidth}px` : undefined;
  return (
    <div
      data-testid="studio-shell"
      className="h-full w-full bg-bg-page"
      style={
        {
          display: "grid",
          gridTemplateAreas: '"header header header header" "rail drawer canvas right"',
          gridTemplateColumns: `64px ${drawerCollapsed ? "0px" : "var(--drawer-w, 320px)"} 1fr var(--right-w, 520px)`,
          gridTemplateRows: `${headerHeight}px 1fr`,
          ...(rightWVar ? { "--right-w": rightWVar } : {}),
        } as React.CSSProperties
      }
    >
      {/* Header zone */}
      <div
        data-testid="studio-shell-header"
        style={{ gridArea: "header" }}
        className={["min-w-0 overflow-hidden", headerHeight === 0 ? "hidden" : ""].join(" ").trim()}
      >
        {header}
      </div>

      {/* Rail zone */}
      <div
        data-testid="studio-shell-rail"
        style={{ gridArea: "rail" }}
        className="min-w-0 overflow-hidden"
      >
        {rail}
      </div>

      {/* Drawer zone */}
      <div
        data-testid="studio-shell-drawer"
        data-collapsed={drawerCollapsed ? "true" : undefined}
        style={{ gridArea: "drawer" }}
        className="min-w-0 overflow-hidden"
      >
        {drawer}
      </div>

      {/* Canvas zone */}
      <div
        data-testid="studio-shell-canvas"
        style={{ gridArea: "canvas" }}
        className="min-w-0 min-h-0 overflow-hidden"
      >
        {canvas}
      </div>

      {/* Right panel zone */}
      <div
        data-testid="studio-shell-right"
        style={{ gridArea: "right" }}
        className="min-w-0 overflow-hidden"
      >
        {right}
      </div>
    </div>
  );
}

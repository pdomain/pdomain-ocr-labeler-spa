/**
 * Local icon shims for icons not yet in @pdomain/pdomain-ui/icons.
 *
 * These are thin inline-SVG wrappers that match the lucide-react prop API
 * (size + className + ...rest). When these icons are upstreamed into pdomain-ui,
 * remove the corresponding shim and update the import site.
 *
 * Gaps to report upstream (see issue comments on #264):
 *   - Square          — used as "region" mode indicator in Rail
 *   - Keyboard        — used as hotkeys-button icon in Rail
 *   - LayoutList      — used as bulk-actions icon in Rail
 *   - List            — used as worklist tab icon in Drawer
 *   - GitBranch       — used as hierarchy tab icon in Drawer
 *   - PanelRightClose — used as right-panel collapse icon in RightPanel
 *   - FolderOpen      — used as open-folder / change-project icon
 */

import React from "react";

interface IconProps extends React.SVGProps<SVGSVGElement> {
  size?: number;
}

const BASE_SVG_PROPS = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

/** Empty square — used for "region / refine" mode in Rail. */
export function Square({ size = 24, className, ...rest }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      {...BASE_SVG_PROPS}
      className={className}
      {...rest}
    >
      <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
    </svg>
  );
}

/** Keyboard — used for hotkeys button in Rail. */
export function Keyboard({ size = 24, className, ...rest }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      {...BASE_SVG_PROPS}
      className={className}
      {...rest}
    >
      <rect x="2" y="7" width="20" height="14" rx="2" ry="2" />
      <line x1="6" y1="11" x2="6" y2="11" strokeLinecap="round" strokeWidth={2.5} />
      <line x1="10" y1="11" x2="10" y2="11" strokeLinecap="round" strokeWidth={2.5} />
      <line x1="14" y1="11" x2="14" y2="11" strokeLinecap="round" strokeWidth={2.5} />
      <line x1="18" y1="11" x2="18" y2="11" strokeLinecap="round" strokeWidth={2.5} />
      <line x1="6" y1="15" x2="18" y2="15" />
    </svg>
  );
}

/** Layout list — used for bulk-actions in Rail. */
export function LayoutList({ size = 24, className, ...rest }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      {...BASE_SVG_PROPS}
      className={className}
      {...rest}
    >
      <rect x="3" y="5" width="7" height="5" rx="1" />
      <rect x="3" y="14" width="7" height="5" rx="1" />
      <line x1="14" y1="7" x2="21" y2="7" />
      <line x1="14" y1="16" x2="21" y2="16" />
      <line x1="14" y1="11" x2="21" y2="11" />
      <line x1="14" y1="20" x2="21" y2="20" />
    </svg>
  );
}

/** List — used for worklist tab in Drawer. */
export function List({ size = 24, className, ...rest }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      {...BASE_SVG_PROPS}
      className={className}
      {...rest}
    >
      <line x1="8" y1="6" x2="21" y2="6" />
      <line x1="8" y1="12" x2="21" y2="12" />
      <line x1="8" y1="18" x2="21" y2="18" />
      <line x1="3" y1="6" x2="3.01" y2="6" strokeWidth={2.5} />
      <line x1="3" y1="12" x2="3.01" y2="12" strokeWidth={2.5} />
      <line x1="3" y1="18" x2="3.01" y2="18" strokeWidth={2.5} />
    </svg>
  );
}

/** Git branch — used for hierarchy tab in Drawer. */
export function GitBranch({ size = 24, className, ...rest }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      {...BASE_SVG_PROPS}
      className={className}
      {...rest}
    >
      <line x1="6" y1="3" x2="6" y2="15" />
      <circle cx="18" cy="6" r="3" />
      <circle cx="6" cy="18" r="3" />
      <path d="M18 9a9 9 0 0 1-9 9" />
    </svg>
  );
}

/** Panel right close — used for collapsing the right panel. */
export function PanelRightClose({ size = 24, className, ...rest }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      {...BASE_SVG_PROPS}
      className={className}
      {...rest}
    >
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <line x1="15" y1="3" x2="15" y2="21" />
      <polyline points="19 8 17 12 19 16" />
    </svg>
  );
}

/** FileText — used for the Text tab in Drawer (S2.2). */
export function FileText({ size = 24, className, ...rest }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      {...BASE_SVG_PROPS}
      className={className}
      {...rest}
    >
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="16" y1="13" x2="8" y2="13" />
      <line x1="16" y1="17" x2="8" y2="17" />
      <polyline points="10 9 9 9 8 9" />
    </svg>
  );
}

/** Folder open — used for open-source-folder and change-project buttons. */
export function FolderOpen({ size = 24, className, ...rest }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      {...BASE_SVG_PROPS}
      className={className}
      {...rest}
    >
      <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
      <polyline points="22 13 16 13 14 16 8 16 6 13 2 13" />
    </svg>
  );
}

// routes.ts — typed route table for pdomain-ocr-labeler-spa.
// Spec: docs/specs/2026-05-12-frontend-shell-design.md §Routing
// Issue #240

/** Canonical route paths used throughout the SPA. */
export const ROUTES = {
  /** Root: checks session-state and redirects or shows EmptyProjectState. */
  ROOT: "/",

  /** Project landing: redirects to page 1 of the project. */
  PROJECT: "/projects/:projectId",

  /** Primary labeling route (1-based page number, human-friendly). */
  PROJECT_PAGE_NO: "/projects/:projectId/pages/pageno/:pageNo",

  /** Geometry-free typography review for producer-supplied stable words. */
  PROJECT_TYPOGRAPHY_PAGE_NO: "/projects/:projectId/pages/pageno/:pageNo/typography",

  /** 0-based index variant — used by internal navigation after redirect. */
  PROJECT_PAGE_IDX: "/projects/:projectId/pages/index/:idx0",
} as const;

/** Build a page URL from project ID and 1-based page number. */
export function pageNoUrl(projectId: string, pageNo: number): string {
  return `/projects/${encodeURIComponent(projectId)}/pages/pageno/${encodeURIComponent(String(pageNo))}`;
}

/** Build the geometry-free typography-review URL for a 1-based page number. */
export function typographyPageNoUrl(projectId: string, pageNo: number): string {
  return `${pageNoUrl(projectId, pageNo)}/typography`;
}

// routes.ts — typed route table for pd-ocr-labeler-spa.
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

  /** 0-based index variant — used by internal navigation after redirect. */
  PROJECT_PAGE_IDX: "/projects/:projectId/pages/index/:idx0",
} as const;

/** Build a page URL from project ID and 1-based page number. */
export function pageNoUrl(projectId: string, pageNo: number): string {
  return `/projects/${projectId}/pages/pageno/${pageNo}`;
}

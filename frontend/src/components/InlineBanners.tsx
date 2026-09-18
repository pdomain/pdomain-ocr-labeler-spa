// InlineBanners.tsx — sticky inline error banners for persistent page-level issues.
//
// Spec: docs/specs/2026-05-12-notifications-design.md §inline banners
// Issue #233
//
// Four distinct banners:
//   - OcrFailedBanner: shown when pageRecord.ocr_failed === true
//   - ProjectNotFoundBanner: shown when routing to a missing project_id
//   - ImageDriftBanner: shown when PagePayload.image_drift is set (the page's
//     source image changed on disk since it was OCR'd)
//   - EmptyOcrBanner: shown when OCR completed for this page and found zero
//     words (BUG-RELOAD-1, docs/context/open-findings.md) — the SPA cannot
//     tell that apart from a genuinely blank page without a person's
//     confirmation, so it surfaces the ambiguity rather than rendering a
//     silent, apparently-finished page.
//
// These are NOT toasts — they are rendered inline in the page content area.
// Uses pdomain-ui Banner primitive (tone mapping: error→danger, warning→warning, info→info).
// CSS layout for .banner is in frontend/src/styles/primitives.css.

import { Banner } from "@pdomain/pdomain-ui/primitives";

// --- Public banner components ---

interface OcrFailedBannerProps {
  /** True when the current page's OCR run failed. */
  ocrFailed?: boolean;
  /**
   * Optional detail from `PagePayload.page_load_error.message` (issue
   * 2026-08-08-get-page-hides-ocr-failures) — shown alongside the generic
   * headline when the backend reported a specific loader failure.
   */
  message?: string | null;
}

/**
 * Inline banner shown when `pageRecord.ocr_failed === true` or when the
 * backend stamped `PagePayload.page_load_error` (a loader failure on the
 * on-demand OCR trigger — issue 2026-08-08-get-page-hides-ocr-failures).
 * Spec: "OCR failed for this page" sticky error.
 */
export function OcrFailedBanner({ ocrFailed, message }: OcrFailedBannerProps) {
  if (!ocrFailed) return null;
  return (
    <Banner tone="danger" data-testid="banner-ocr-failed" role="alert">
      OCR failed for this page. Try reloading OCR from the toolbar.
      {message ? ` (${message})` : ""}
    </Banner>
  );
}

interface ProjectNotFoundBannerProps {
  /** The project ID that was not found. */
  projectId?: string;
  /** True when the project could not be resolved. */
  notFound?: boolean;
}

/**
 * Inline banner shown when routing to a project_id that doesn't resolve.
 * Spec: "Project not found" sticky error.
 */
export function ProjectNotFoundBanner({ projectId, notFound }: ProjectNotFoundBannerProps) {
  if (!notFound) return null;
  return (
    <Banner tone="danger" data-testid="banner-project-not-found" role="alert">
      Project not found{projectId ? `: "${projectId}"` : ""}. Go back to the project list to select
      a valid project.
    </Banner>
  );
}

interface ImageDriftBannerProps {
  /** True when the current page's source image changed on disk since OCR. */
  imageDrift?: boolean;
  /**
   * Optional detail from `PagePayload.image_drift.message` (issue
   * 2026-07-21-image-drift-banner-hard-off) — shown alongside the generic
   * headline when the backend named what changed.
   */
  message?: string | null;
}

/**
 * Inline banner shown when the backend stamped `PagePayload.image_drift`
 * (the page's source image on disk no longer matches the bytes it was
 * OCR'd from). Points at the existing Reload OCR toolbar action, the same
 * recovery path `OcrFailedBanner` points at for a loader failure.
 * Spec: "Image on disk has changed. Reload page to continue."
 */
export function ImageDriftBanner({ imageDrift, message }: ImageDriftBannerProps) {
  if (!imageDrift) return null;
  return (
    <Banner tone="warning" data-testid="banner-image-drift" role="alert">
      Image on disk has changed. Reload OCR from the toolbar to continue editing.
      {message ? ` (${message})` : ""}
    </Banner>
  );
}

interface EmptyOcrBannerProps {
  /** True when OCR ran for this page and found zero words. */
  emptyOcr?: boolean;
}

/**
 * Inline banner shown when OCR completed for this page and found no text at
 * all — the same zero-word result a genuinely blank page produces
 * (BUG-RELOAD-1, `docs/context/open-findings.md`). Nothing recorded at OCR
 * time distinguishes "this page is blank" from "OCR failed to find text a
 * person can plainly see", so rather than guess, the SPA surfaces the
 * ambiguity: look at the page image, then either confirm its kind as Blank
 * or reload OCR. Never shown once a person has confirmed the page's kind as
 * Blank (`PagePayload.page_kind === "blank"`) — see the caller.
 * Spec: "OCR found no text on this page" sticky warning.
 */
export function EmptyOcrBanner({ emptyOcr }: EmptyOcrBannerProps) {
  if (!emptyOcr) return null;
  return (
    <Banner tone="warning" data-testid="banner-empty-ocr" role="alert">
      OCR found no text on this page. If the page is genuinely blank, confirm its kind as Blank;
      otherwise, reload OCR from the toolbar.
    </Banner>
  );
}

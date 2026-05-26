// InlineBanners.tsx — sticky inline error banners for persistent page-level issues.
//
// Spec: docs/specs/2026-05-12-notifications-design.md §inline banners
// Issue #233
//
// Three distinct banners:
//   - OcrFailedBanner: shown when pageRecord.ocr_failed === true
//   - ProjectNotFoundBanner: shown when routing to a missing project_id
//   - ImageDriftBanner: shown after a 409 image_drift save response
//
// These are NOT toasts — they are rendered inline in the page content area.
// Uses pd-ui Banner primitive (tone mapping: error→danger, warning→warning, info→info).
// CSS layout for .banner is in frontend/src/styles/primitives.css.

import { Banner } from "@concavetrillion/pd-ui/primitives";

// --- Public banner components ---

interface OcrFailedBannerProps {
  /** True when the current page's OCR run failed. */
  ocrFailed?: boolean;
}

/**
 * Inline banner shown when `pageRecord.ocr_failed === true`.
 * Spec: "OCR failed for this page" sticky error.
 */
export function OcrFailedBanner({ ocrFailed }: OcrFailedBannerProps) {
  if (!ocrFailed) return null;
  return (
    <Banner tone="danger" data-testid="banner-ocr-failed" role="alert">
      OCR failed for this page. Try reloading OCR from the toolbar.
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
  /** True after a 409 image_drift save response. */
  imageDrift?: boolean;
}

/**
 * Inline banner shown after a 409 `image_drift` save response.
 * Spec: "Image on disk has changed. Reload page to continue."
 */
export function ImageDriftBanner({ imageDrift }: ImageDriftBannerProps) {
  if (!imageDrift) return null;
  return (
    <Banner tone="warning" data-testid="banner-image-drift" role="alert">
      Image on disk has changed. Reload the page to continue editing.
    </Banner>
  );
}

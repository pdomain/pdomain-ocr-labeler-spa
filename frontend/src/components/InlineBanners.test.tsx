// InlineBanners.test.tsx — tests for sticky inline error banners.
// Spec: docs/specs/2026-05-12-notifications-design.md §inline banners
// Issue #233

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import {
  OcrFailedBanner,
  ProjectNotFoundBanner,
  ImageDriftBanner,
  EmptyOcrBanner,
} from "./InlineBanners";

describe("OcrFailedBanner", () => {
  it("renders when ocrFailed is true", () => {
    render(<OcrFailedBanner ocrFailed />);
    expect(screen.getByTestId("banner-ocr-failed")).toBeInTheDocument();
    expect(screen.getByText(/OCR failed/i)).toBeInTheDocument();
  });

  it("does NOT render when ocrFailed is false", () => {
    const { container } = render(<OcrFailedBanner ocrFailed={false} />);
    expect(container.querySelector("[data-testid='banner-ocr-failed']")).toBeNull();
  });

  it("does NOT render when ocrFailed is undefined", () => {
    const { container } = render(<OcrFailedBanner />);
    expect(container.querySelector("[data-testid='banner-ocr-failed']")).toBeNull();
  });

  it("includes the loader message when provided (issue 2026-08-08-get-page-hides-ocr-failures)", () => {
    render(<OcrFailedBanner ocrFailed message="doctr predictor unavailable" />);
    const banner = screen.getByTestId("banner-ocr-failed");
    expect(banner.textContent).toContain("doctr predictor unavailable");
  });

  it("renders without a parenthetical when no message is provided", () => {
    render(<OcrFailedBanner ocrFailed />);
    const banner = screen.getByTestId("banner-ocr-failed");
    expect(banner.textContent).not.toContain("(");
  });
});

describe("ProjectNotFoundBanner", () => {
  it("renders when projectId is missing", () => {
    render(<ProjectNotFoundBanner projectId="unknown-id" notFound />);
    expect(screen.getByTestId("banner-project-not-found")).toBeInTheDocument();
    expect(screen.getByText(/project not found/i)).toBeInTheDocument();
  });

  it("does NOT render when notFound is false", () => {
    const { container } = render(<ProjectNotFoundBanner projectId="p-1" notFound={false} />);
    expect(container.querySelector("[data-testid='banner-project-not-found']")).toBeNull();
  });
});

describe("ImageDriftBanner", () => {
  it("renders when imageDrift is true", () => {
    render(<ImageDriftBanner imageDrift />);
    expect(screen.getByTestId("banner-image-drift")).toBeInTheDocument();
    expect(screen.getByText(/image.*changed/i)).toBeInTheDocument();
  });

  it("does NOT render when imageDrift is false", () => {
    const { container } = render(<ImageDriftBanner imageDrift={false} />);
    expect(container.querySelector("[data-testid='banner-image-drift']")).toBeNull();
  });

  it("does NOT render when imageDrift is undefined", () => {
    const { container } = render(<ImageDriftBanner />);
    expect(container.querySelector("[data-testid='banner-image-drift']")).toBeNull();
  });

  it("points at the Reload OCR toolbar action", () => {
    render(<ImageDriftBanner imageDrift />);
    expect(screen.getByText(/reload ocr/i)).toBeInTheDocument();
  });

  it("includes the backend detail when provided (issue 2026-07-21-image-drift-banner-hard-off)", () => {
    render(
      <ImageDriftBanner
        imageDrift
        message="The source image changed on disk after this page was OCR'd (001.png)."
      />,
    );
    const banner = screen.getByTestId("banner-image-drift");
    expect(banner.textContent).toContain("001.png");
  });

  it("renders without a parenthetical when no message is provided", () => {
    render(<ImageDriftBanner imageDrift />);
    const banner = screen.getByTestId("banner-image-drift");
    expect(banner.textContent).not.toContain("(");
  });

  it("banners are NOT toasts (rendered inline, not via sonner)", () => {
    // Inline banners must be rendered in the DOM directly, not via toast API.
    // This test just confirms the element is a regular DOM node, not a portal.
    const { container } = render(<ImageDriftBanner imageDrift />);
    const banner = container.querySelector("[data-testid='banner-image-drift']");
    expect(banner).not.toBeNull();
    // It's a direct child of the render container, not a portal/toast
    expect(container.contains(banner)).toBe(true);
  });
});

describe("EmptyOcrBanner", () => {
  // BUG-RELOAD-1 (docs/context/open-findings.md): a page where OCR found no
  // text must not render as an ordinary, apparently-finished empty page.
  it("renders when emptyOcr is true", () => {
    render(<EmptyOcrBanner emptyOcr />);
    expect(screen.getByTestId("banner-empty-ocr")).toBeInTheDocument();
    expect(screen.getByText(/OCR found no text/i)).toBeInTheDocument();
  });

  it("does NOT render when emptyOcr is false", () => {
    const { container } = render(<EmptyOcrBanner emptyOcr={false} />);
    expect(container.querySelector("[data-testid='banner-empty-ocr']")).toBeNull();
  });

  it("does NOT render when emptyOcr is undefined", () => {
    const { container } = render(<EmptyOcrBanner />);
    expect(container.querySelector("[data-testid='banner-empty-ocr']")).toBeNull();
  });

  it("points at both the page-kind confirmation and Reload OCR toolbar action", () => {
    render(<EmptyOcrBanner emptyOcr />);
    expect(screen.getByText(/blank/i)).toBeInTheDocument();
    expect(screen.getByText(/reload ocr/i)).toBeInTheDocument();
  });
});

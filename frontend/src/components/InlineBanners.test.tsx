// InlineBanners.test.tsx — tests for sticky inline error banners.
// Spec: docs/specs/2026-05-12-notifications-design.md §inline banners
// Issue #233

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { OcrFailedBanner, ProjectNotFoundBanner, ImageDriftBanner } from "./InlineBanners";

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

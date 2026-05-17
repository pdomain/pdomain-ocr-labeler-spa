// PageImage.test.tsx — Konva image wrapper (spec-21-A1, #296)
// Spec: specs/21-konva-renderer.md §5 (Image loading)
//
// Acceptance:
//   - While the image is loading (useImage returns undefined), renders a
//     grey fallback Rect at the supplied display dimensions.
//   - When the image is loaded (useImage returns an HTMLImageElement),
//     renders a Konva <Image> at the supplied display dimensions.
//   - When loading fails (useImage returns [undefined, "failed"]),
//     renders the same grey fallback Rect. (image-load-failed notification
//     emission is deferred to the spec-21-A integration slice; this slice
//     only asserts fallback rendering.)

import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

// use-image mock — default export is the hook, returning [image | undefined, status].
// vi.hoisted so the mock state is in-scope for the vi.mock factory below.
const mockUseImageState = vi.hoisted(() => ({
  image: undefined as HTMLImageElement | undefined,
  status: "loading",
}));

vi.mock("use-image", () => ({
  default: () => [mockUseImageState.image, mockUseImageState.status] as const,
}));

// react-konva mock — render simple divs so jsdom can probe rendered output.
// Forwards width/height/fill so we can assert dimensions and grey fallback colour.
vi.mock("react-konva", () => ({
  Image: ({
    width,
    height,
    image,
    "data-testid": testId,
  }: {
    width?: number;
    height?: number;
    image?: HTMLImageElement;
    "data-testid"?: string;
  }) => (
    <div
      data-testid={testId ?? "konva-image"}
      data-width={width}
      data-height={height}
      data-has-image={image ? "true" : "false"}
    />
  ),
  Rect: ({
    width,
    height,
    fill,
    "data-testid": testId,
  }: {
    width?: number;
    height?: number;
    fill?: string;
    "data-testid"?: string;
  }) => (
    <div
      data-testid={testId ?? "konva-rect"}
      data-width={width}
      data-height={height}
      data-fill={fill}
    />
  ),
}));

import { PageImage } from "./PageImage";

describe("PageImage (#296)", () => {
  beforeEach(() => {
    mockUseImageState.image = undefined;
    mockUseImageState.status = "loading";
  });

  it("renders a grey fallback Rect while the image is loading", () => {
    mockUseImageState.image = undefined;
    mockUseImageState.status = "loading";

    render(<PageImage url="/image-cache/page-001.png" width={800} height={600} />);

    const rect = screen.getByTestId("page-image-fallback");
    expect(rect.getAttribute("data-fill")).toBe("#1d1d24");
    expect(Number(rect.getAttribute("data-width"))).toBe(800);
    expect(Number(rect.getAttribute("data-height"))).toBe(600);
    expect(screen.queryByTestId("page-image")).toBeNull();
  });

  it("renders a Konva Image at the supplied dimensions once loaded", () => {
    // Stand-in image element — value identity is what matters here.
    const img = { width: 1600, height: 1200 } as unknown as HTMLImageElement;
    mockUseImageState.image = img;
    mockUseImageState.status = "loaded";

    render(<PageImage url="/image-cache/page-001.png" width={800} height={600} />);

    const konvaImage = screen.getByTestId("page-image");
    expect(konvaImage.getAttribute("data-has-image")).toBe("true");
    expect(Number(konvaImage.getAttribute("data-width"))).toBe(800);
    expect(Number(konvaImage.getAttribute("data-height"))).toBe(600);
    expect(screen.queryByTestId("page-image-fallback")).toBeNull();
  });

  it("renders the grey fallback Rect when the image load fails", () => {
    mockUseImageState.image = undefined;
    mockUseImageState.status = "failed";

    render(<PageImage url="/image-cache/page-001.png" width={800} height={600} />);

    const rect = screen.getByTestId("page-image-fallback");
    expect(rect.getAttribute("data-fill")).toBe("#1d1d24");
    expect(Number(rect.getAttribute("data-width"))).toBe(800);
    expect(Number(rect.getAttribute("data-height"))).toBe(600);
    expect(screen.queryByTestId("page-image")).toBeNull();
  });
});

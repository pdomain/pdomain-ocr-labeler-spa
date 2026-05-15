// PageImage.tsx — Konva image wrapper for the page-image canvas.
// Spec: specs/21-konva-renderer.md §5 (Image loading).
// Issue: #296 (spec-21-A1).
//
// Loads `url` via the `use-image` hook with `anonymous` CORS mode (required
// so Konva can read pixels for any future toDataURL exports — the backend
// image-cache route serves `Access-Control-Allow-Origin: *` per spec 02).
//
// While the image is loading (or if loading fails), a grey fallback Rect at
// the supplied display dimensions is rendered in its place. The
// `image-load-failed` notification — see specs/21-konva-renderer.md §5 — is
// emitted by the integration slice (spec-21-A), not here.
//
// PageImage is meant to be rendered INSIDE an existing react-konva <Layer>
// owned by the caller (e.g. PageImageCanvas at spec-21-A2). It does not
// wrap its output in a Layer.

import { Image as KonvaImage, Rect } from "react-konva";
import useImage from "use-image";

export interface PageImageProps {
  /** URL to load; passed through to use-image. */
  url: string;
  /** Display width in stage pixels. */
  width: number;
  /** Display height in stage pixels. */
  height: number;
}

/** Fallback fill colour for the loading / failed-load state (Tailwind gray-100). */
const FALLBACK_FILL = "#f3f4f6";

/**
 * PageImage — Konva <Image> with a grey loading/failure fallback Rect.
 *
 * Must be rendered inside a parent react-konva <Layer>. Renders nothing
 * outside Konva's scene graph; safe to drop in alongside overlay rects.
 */
export function PageImage({ url, width, height }: PageImageProps) {
  const [img] = useImage(url, "anonymous");
  if (!img) {
    return (
      <Rect data-testid="page-image-fallback" width={width} height={height} fill={FALLBACK_FILL} />
    );
  }
  return <KonvaImage data-testid="page-image" image={img} width={width} height={height} />;
}

import { useRef } from "react";
import { getStageDimensions, type EncodedDims } from "../lib/canvas-utils";

interface PageImageCanvasProps {
  imageUrl: string;
  encoded: EncodedDims;
}

export default function PageImageCanvas({
  imageUrl: _imageUrl,
  encoded,
}: PageImageCanvasProps) {
  const stageRef = useRef<HTMLDivElement>(null);
  const dims = getStageDimensions(encoded);

  // Konva canvas not yet implemented; stub renders dimensions for testing.
  return (
    <div
      ref={stageRef}
      className="page-image-canvas"
      data-width={dims.width}
      data-height={dims.height}
      data-testid="image-viewport"
    />
  );
}

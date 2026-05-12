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

  // Placeholder component structure for M4 Konva implementation
  // Stage will be implemented after D-020 research spike confirms Konva choice
  return (
    <div
      ref={stageRef}
      className="page-image-canvas"
      data-width={dims.width}
      data-height={dims.height}
      data-testid="canvas"
    >
      {/* Konva Stage and Layers to be implemented in M4 */}
    </div>
  );
}

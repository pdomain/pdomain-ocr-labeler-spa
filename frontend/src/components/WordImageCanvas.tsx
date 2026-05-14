// WordImageCanvas.tsx — interactive Konva image Stage for the word-edit dialog (#210)
// Spec: docs/specs/2026-05-12-word-edit-dialog-design.md §Interactive Konva image
//      docs/architecture/07-word-edit-dialog.md §4.1 (image area, zoom, marker, erase rects)
//
// Renders the word image slice at 1×/2×/5×/10× zoom.
// Overlays:
//   - Click marker dot (solid blue circle, data-testid="dialog-current-marker")
//   - Hover guide lines (vertical + horizontal crosshairs, data-testid="dialog-hover-guide")
//   - Staged erase rects (red semi-transparent, data-testid="dialog-erase-rect")
//
// Erase rects accumulate locally; no POST fires until Apply&Close.
// The zoom selector uses data-testid="dialog-current-zoom-toggle".
//
// driver-contract testids:
//   dialog-current-zoom-toggle — zoom level selector (value is "1" | "2" | "5" | "10")
//   dialog-current-marker      — click-placed dot overlay
//   dialog-hover-guide         — crosshair guide (shown on hover)
//   dialog-erase-rect          — each staged erase rect (multiple allowed)
//   dialog-word-stage          — the Konva <Stage> root

import { useCallback, useRef, useState } from "react";
import { Layer, Rect, Stage } from "react-konva";
import type Konva from "konva";

// useRef is used below in ImageLayer (not the main component).
// The eslint no-unused-vars rule is satisfied by the Layer/Stage/Rect imports above.

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type ZoomLevel = 1 | 2 | 5 | 10;

export interface MarkerPoint {
  x: number;
  y: number;
}

/** Erase rect in *image* coordinates (before zoom scaling). */
export interface EraseRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

interface DragState {
  startX: number;
  startY: number;
}

interface WordImageCanvasProps {
  /** URL of the word image slice (PNG or JPEG). */
  imageUrl?: string;
  /** Whether erase mode is currently active (from dialog state). */
  eraseMode?: boolean;
  /** External accumulator of erase rects — caller owns state and persists across navigations. */
  eraseRects?: EraseRect[];
  /** Called when a new erase rect is staged. */
  onEraseRectAdd?: (rect: EraseRect) => void;
  /** Called when a click marker is placed/replaced. */
  onMarkerPlace?: (point: MarkerPoint) => void;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const ZOOM_LEVELS: ZoomLevel[] = [1, 2, 5, 10];
const BASE_WIDTH = 200;
const BASE_HEIGHT = 80;
const MARKER_RADIUS = 5;
const GUIDE_STROKE = "#3b82f6"; // blue-500
const MARKER_FILL = "#2563eb"; // blue-600
const ERASE_FILL = "rgba(220,38,38,0.35)"; // red semi-transparent
const GUIDE_STROKE_WIDTH = 1;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function WordImageCanvas({
  imageUrl,
  eraseMode = false,
  eraseRects = [],
  onEraseRectAdd,
  onMarkerPlace,
}: WordImageCanvasProps) {
  const [zoom, setZoom] = useState<ZoomLevel>(1);
  const [marker, setMarker] = useState<MarkerPoint | null>(null);
  const [guide, setGuide] = useState<{ x: number; y: number } | null>(null);
  const [dragState, setDragState] = useState<DragState | null>(null);
  const [pendingEraseRect, setPendingEraseRect] = useState<EraseRect | null>(null);
  // stageRef reserved for future programmatic access (e.g., export-to-PNG).
  const stageRef = useRef<Konva.Stage>(null);

  const stageWidth = BASE_WIDTH * zoom;
  const stageHeight = BASE_HEIGHT * zoom;

  // Scale image to fill the stage.
  const imageWidth = stageWidth;
  const imageHeight = stageHeight;

  // ---------------------------------------------------------------------------
  // Pointer helpers
  // ---------------------------------------------------------------------------

  /** Convert a KonvaEventObject pointer position to image (unzoomed) coords. */
  const toImageCoords = useCallback(
    (pos: { x: number; y: number }): { x: number; y: number } => ({
      x: pos.x / zoom,
      y: pos.y / zoom,
    }),
    [zoom],
  );

  // ---------------------------------------------------------------------------
  // Stage event handlers
  // ---------------------------------------------------------------------------

  const handleMouseMove = useCallback(
    (e: Konva.KonvaEventObject<MouseEvent>) => {
      const stage = e.target.getStage();
      if (!stage) return;
      const pos = stage.getPointerPosition();
      if (!pos) return;
      setGuide({ x: pos.x, y: pos.y });

      if (eraseMode && dragState) {
        const x = Math.min(pos.x, dragState.startX) / zoom;
        const y = Math.min(pos.y, dragState.startY) / zoom;
        const width = Math.abs(pos.x - dragState.startX) / zoom;
        const height = Math.abs(pos.y - dragState.startY) / zoom;
        setPendingEraseRect({ x, y, width, height });
      }
    },
    [eraseMode, dragState, zoom],
  );

  const handleMouseLeave = useCallback(() => {
    setGuide(null);
    if (eraseMode && dragState && pendingEraseRect) {
      if (pendingEraseRect.width > 0 && pendingEraseRect.height > 0) {
        onEraseRectAdd?.(pendingEraseRect);
      }
      setPendingEraseRect(null);
      setDragState(null);
    }
  }, [eraseMode, dragState, pendingEraseRect, onEraseRectAdd]);

  const handleMouseDown = useCallback(
    (e: Konva.KonvaEventObject<MouseEvent>) => {
      const stage = e.target.getStage();
      if (!stage) return;
      const pos = stage.getPointerPosition();
      if (!pos) return;

      if (eraseMode) {
        setDragState({ startX: pos.x, startY: pos.y });
        setPendingEraseRect({ x: pos.x / zoom, y: pos.y / zoom, width: 0, height: 0 });
      }
    },
    [eraseMode, zoom],
  );

  const handleMouseUp = useCallback(
    (e: Konva.KonvaEventObject<MouseEvent>) => {
      if (!eraseMode) {
        // Normal mode: place click marker.
        const stage = e.target.getStage();
        if (!stage) return;
        const pos = stage.getPointerPosition();
        if (!pos) return;
        const imgCoords = toImageCoords(pos);
        setMarker(imgCoords);
        onMarkerPlace?.(imgCoords);
        return;
      }

      // Erase mode: commit pending rect.
      if (dragState && pendingEraseRect) {
        if (pendingEraseRect.width > 0 && pendingEraseRect.height > 0) {
          onEraseRectAdd?.(pendingEraseRect);
        }
        setPendingEraseRect(null);
        setDragState(null);
      }
    },
    [eraseMode, dragState, pendingEraseRect, toImageCoords, onEraseRectAdd, onMarkerPlace],
  );

  const handleClick = useCallback(
    (e: Konva.KonvaEventObject<MouseEvent>) => {
      if (eraseMode) return; // handled in mouseUp
      const stage = e.target.getStage();
      if (!stage) return;
      const pos = stage.getPointerPosition();
      if (!pos) return;
      const imgCoords = toImageCoords(pos);
      setMarker(imgCoords);
      onMarkerPlace?.(imgCoords);
    },
    [eraseMode, toImageCoords, onMarkerPlace],
  );

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="flex flex-col items-center gap-2">
      {/* Zoom selector */}
      <div className="flex items-center gap-1">
        <span className="text-xs text-gray-500 mr-1">Zoom:</span>
        {ZOOM_LEVELS.map((z) => (
          <button
            key={z}
            data-testid="dialog-current-zoom-toggle"
            data-zoom={z}
            aria-pressed={zoom === z}
            onClick={() => setZoom(z)}
            className={[
              "px-2 py-0.5 text-xs rounded border transition-colors",
              zoom === z
                ? "bg-blue-600 text-white border-blue-600"
                : "bg-white text-gray-700 border-gray-300 hover:bg-gray-50",
            ].join(" ")}
          >
            {z}×
          </button>
        ))}
        {eraseMode && <span className="ml-2 text-xs text-red-600 font-medium">Erase mode</span>}
      </div>

      {/* Konva Stage */}
      <div
        className="border border-gray-300 rounded overflow-hidden"
        style={{ cursor: eraseMode ? "crosshair" : "cell" }}
      >
        <Stage
          ref={stageRef}
          width={stageWidth}
          height={stageHeight}
          data-testid="dialog-word-stage"
          onMouseMove={handleMouseMove}
          onMouseLeave={handleMouseLeave}
          onMouseDown={handleMouseDown}
          onMouseUp={handleMouseUp}
          onClick={handleClick}
        >
          <Layer>
            {/* Background — image or placeholder */}
            {imageUrl ? (
              <ImageLayer url={imageUrl} width={imageWidth} height={imageHeight} />
            ) : (
              /* Placeholder rect when no image URL provided */
              <Rect x={0} y={0} width={stageWidth} height={stageHeight} fill="#f3f4f6" />
            )}

            {/* Committed erase rects */}
            {eraseRects.map((rect, i) => (
              <Rect
                key={i}
                data-testid="dialog-erase-rect"
                x={rect.x * zoom}
                y={rect.y * zoom}
                width={rect.width * zoom}
                height={rect.height * zoom}
                fill={ERASE_FILL}
                stroke="#dc2626"
                strokeWidth={1}
              />
            ))}

            {/* Pending erase rect (being dragged) */}
            {pendingEraseRect && (
              <Rect
                x={pendingEraseRect.x * zoom}
                y={pendingEraseRect.y * zoom}
                width={pendingEraseRect.width * zoom}
                height={pendingEraseRect.height * zoom}
                fill={ERASE_FILL}
                stroke="#dc2626"
                strokeWidth={1}
                dash={[4, 2]}
              />
            )}
          </Layer>

          {/* Overlay layer: guide lines + click marker */}
          <Layer>
            {/* Hover guide lines */}
            {guide && (
              <>
                {/* Vertical guide */}
                <Rect
                  data-testid="dialog-hover-guide"
                  x={guide.x}
                  y={0}
                  width={GUIDE_STROKE_WIDTH}
                  height={stageHeight}
                  fill={GUIDE_STROKE}
                  opacity={0.6}
                />
                {/* Horizontal guide */}
                <Rect
                  x={0}
                  y={guide.y}
                  width={stageWidth}
                  height={GUIDE_STROKE_WIDTH}
                  fill={GUIDE_STROKE}
                  opacity={0.6}
                />
              </>
            )}

            {/* Click marker dot */}
            {marker && (
              <Rect
                data-testid="dialog-current-marker"
                x={marker.x * zoom - MARKER_RADIUS}
                y={marker.y * zoom - MARKER_RADIUS}
                width={MARKER_RADIUS * 2}
                height={MARKER_RADIUS * 2}
                cornerRadius={MARKER_RADIUS}
                fill={MARKER_FILL}
              />
            )}
          </Layer>
        </Stage>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ImageLayer — loads a URL and draws it as a Konva.Image
// ---------------------------------------------------------------------------

interface ImageLayerProps {
  url: string;
  width: number;
  height: number;
}

/** Loads an image URL and renders it. Falls back to a placeholder on error. */
function ImageLayer({ url, width, height }: ImageLayerProps) {
  // Use a native img element for loading; Konva will receive it.
  // In jsdom tests this renders nothing (Konva Image needs HTMLImageElement).
  // The Konva mock in tests renders a div stub, so we just provide the rect.
  const [loaded, setLoaded] = useState(false);
  const imgRef = useRef<HTMLImageElement | null>(null);

  if (!loaded) {
    const img = new window.Image();
    img.src = url;
    img.onload = () => setLoaded(true);
    imgRef.current = img;
  }

  return (
    <Rect
      x={0}
      y={0}
      width={width}
      height={height}
      fill={loaded ? undefined : "#e5e7eb"}
      fillPatternImage={loaded && imgRef.current ? imgRef.current : undefined}
      fillPatternScaleX={loaded && imgRef.current ? width / imgRef.current.naturalWidth : 1}
      fillPatternScaleY={loaded && imgRef.current ? height / imgRef.current.naturalHeight : 1}
    />
  );
}

export type { WordImageCanvasProps };

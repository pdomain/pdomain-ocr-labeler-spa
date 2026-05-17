// CharFixerCanvas.tsx — Konva per-char bbox visualisation for the Char Fixer
// section (P4.b, Gap 39).
// Spec: docs/plans/hifi-gaps-plan.md slice P4.b.
//
// Renders a fixed ~240×120 px Konva Stage that shows the word's cropped image
// (when an imageUrl is wired) as the background, then overlays one labelled
// coloured rectangle per char-range bbox. Each rectangle carries 8 drag
// handles (4 corners + 4 midpoints). Dragging a handle reports a new bbox
// for that range through onChange. Clicking a rectangle selects it (parent
// renders an accent border + detail strip).
//
// The component is deliberately self-contained — it does NOT import from
// ReboxCanvas (a parallel slice owns that). A future cleanup pass can hoist
// the shared HandleDef table into a common helper.
//
// Coordinate spaces:
//   - charBboxes are reported in *image-pixel* coords (same convention as
//     WordMatch.bbox / BBox schema).
//   - The Stage shows a scaled-to-fit view; the parent CharFixerSection
//     owns the canonical bbox state.
//
// data-testids (P4.b):
//   charfixer-canvas             — outer Konva Stage
//   charfixer-range-{N}          — bbox <Rect> overlay per range
//   charfixer-range-{N}-handle-{pos} — per-range drag handles
//                                       (pos ∈ nw|n|ne|e|se|s|sw|w)

import { useCallback, useMemo } from "react";
import { Layer, Rect, Stage } from "react-konva";
import type Konva from "konva";
import type { components } from "../../../api/types";
import { readCssToken, hexToRgba } from "../../../hooks/useLayerColors";

type BBox = components["schemas"]["BBox"];

/** Per-range bbox shown on the canvas (P4.b local state). */
export interface CharRangeBBox {
  /** Inclusive char index range start (matches CharRange.start). */
  start: number;
  /** Inclusive char index range end (matches CharRange.end). */
  end: number;
  /** Bounding box in image-pixel coords. */
  bbox: BBox;
}

export interface CharFixerCanvasProps {
  /** Source word bbox (image-pixel coords) — used to fit the Stage view. */
  wordBbox: BBox;
  /** Current per-range bboxes (image-pixel coords). */
  charBboxes: CharRangeBBox[];
  /** Optional URL of the cropped word image; falls back to a neutral fill. */
  imageUrl?: string | undefined;
  /** Index of the currently-selected range (or null). */
  selectedIndex: number | null;
  /** Called when the user clicks a range rectangle (or its handles). */
  onSelect: (index: number) => void;
  /** Called when a drag-handle move finishes / fires; index + new bbox. */
  onChange: (index: number, next: BBox) => void;
}

/** Width/height of the Konva Stage in CSS pixels. */
const CANVAS_WIDTH = 240;
const CANVAS_HEIGHT = 120;
/** Side length (px) of each drag handle. */
const HANDLE_SIZE = 8;
const SELECTED_STROKE_WIDTH = 2.5;
const UNSELECTED_STROKE_WIDTH = 1.25;

function buildRangePalette(): Array<{ stroke: string; fill: string }> {
  const tokens = [
    readCssToken("--status-ocr", "#5d9fdf"),
    readCssToken("--status-exact", "#5fbf6a"),
    readCssToken("--status-mismatch", "#dc6555"),
    readCssToken("--status-gt", "#a888d4"),
    readCssToken("--status-fuzzy", "#e8a83a"),
    readCssToken("--layer-line", "#d088a8"),
  ];
  return tokens.map((stroke) => ({ stroke, fill: hexToRgba(stroke, 0.18) }));
}

function buildHandleColors() {
  return {
    fill: readCssToken("--bg-sunk", "#08080c"),
    stroke: readCssToken("--ink-1", "#f0f0f2"),
  };
}

type HandlePos = "nw" | "n" | "ne" | "e" | "se" | "s" | "sw" | "w";

interface HandleDef {
  pos: HandlePos;
  centre: (b: BBox) => { x: number; y: number };
  apply: (b: BBox, x: number, y: number) => BBox;
}

const HANDLES: HandleDef[] = [
  {
    pos: "nw",
    centre: (b) => ({ x: b.x, y: b.y }),
    apply: (b, x, y) => ({
      x,
      y,
      width: b.x + b.width - x,
      height: b.y + b.height - y,
    }),
  },
  {
    pos: "n",
    centre: (b) => ({ x: b.x + b.width / 2, y: b.y }),
    apply: (b, _x, y) => ({ x: b.x, y, width: b.width, height: b.y + b.height - y }),
  },
  {
    pos: "ne",
    centre: (b) => ({ x: b.x + b.width, y: b.y }),
    apply: (b, x, y) => ({ x: b.x, y, width: x - b.x, height: b.y + b.height - y }),
  },
  {
    pos: "e",
    centre: (b) => ({ x: b.x + b.width, y: b.y + b.height / 2 }),
    apply: (b, x, _y) => ({ x: b.x, y: b.y, width: x - b.x, height: b.height }),
  },
  {
    pos: "se",
    centre: (b) => ({ x: b.x + b.width, y: b.y + b.height }),
    apply: (b, x, y) => ({ x: b.x, y: b.y, width: x - b.x, height: y - b.y }),
  },
  {
    pos: "s",
    centre: (b) => ({ x: b.x + b.width / 2, y: b.y + b.height }),
    apply: (b, _x, y) => ({ x: b.x, y: b.y, width: b.width, height: y - b.y }),
  },
  {
    pos: "sw",
    centre: (b) => ({ x: b.x, y: b.y + b.height }),
    apply: (b, x, y) => ({ x, y: b.y, width: b.x + b.width - x, height: y - b.y }),
  },
  {
    pos: "w",
    centre: (b) => ({ x: b.x, y: b.y + b.height / 2 }),
    apply: (b, x, _y) => ({ x, y: b.y, width: b.x + b.width - x, height: b.height }),
  },
];

/** Normalize bbox so width/height are positive (≥1 px). */
function normalize(b: BBox): BBox {
  let { x, y, width, height } = b;
  if (width < 0) {
    x += width;
    width = -width;
  }
  if (height < 0) {
    y += height;
    height = -height;
  }
  return { x, y, width: Math.max(1, width), height: Math.max(1, height) };
}

export function CharFixerCanvas({
  wordBbox,
  charBboxes,
  imageUrl,
  selectedIndex,
  onSelect,
  onChange,
}: CharFixerCanvasProps) {
  const rangePalette = buildRangePalette();
  const handleColors = buildHandleColors();

  // Fit the *word* bbox into the canvas. Sizing around the parent bbox keeps
  // the visible scale stable as the user nudges per-char bboxes around.
  const fit = useMemo(() => {
    const margin = Math.max(8, Math.round(wordBbox.height * 0.25));
    const viewW = Math.max(1, wordBbox.width + 2 * margin);
    const viewH = Math.max(1, wordBbox.height + 2 * margin);
    const scale = Math.min(CANVAS_WIDTH / viewW, CANVAS_HEIGHT / viewH);
    const originX = wordBbox.x - margin;
    const originY = wordBbox.y - margin;
    return { scale, originX, originY };
  }, [wordBbox]);

  /** Image-coords → canvas-coords. */
  const toCanvas = useCallback(
    (px: number, py: number): { x: number; y: number } => ({
      x: (px - fit.originX) * fit.scale,
      y: (py - fit.originY) * fit.scale,
    }),
    [fit],
  );

  /** Canvas-coords → image-coords. */
  const toImage = useCallback(
    (cx: number, cy: number): { x: number; y: number } => ({
      x: cx / fit.scale + fit.originX,
      y: cy / fit.scale + fit.originY,
    }),
    [fit],
  );

  const handleHandleDragMove = useCallback(
    (rangeIndex: number, pos: HandlePos) => (e: Konva.KonvaEventObject<DragEvent>) => {
      const stage = e.target.getStage?.();
      if (!stage) return;
      const ptr = stage.getPointerPosition();
      if (!ptr) return;
      const img = toImage(ptr.x, ptr.y);
      const def = HANDLES.find((h) => h.pos === pos);
      if (!def) return;
      const current = charBboxes[rangeIndex];
      if (!current) return;
      const next = normalize(def.apply(current.bbox, img.x, img.y));
      onChange(rangeIndex, next);
    },
    [charBboxes, onChange, toImage],
  );

  return (
    <div
      className="rounded border border-border-2 overflow-hidden bg-sunk"
      style={{
        backgroundImage: imageUrl ? `url(${imageUrl})` : undefined,
        backgroundSize: "cover",
        backgroundPosition: "center",
      }}
    >
      <Stage width={CANVAS_WIDTH} height={CANVAS_HEIGHT} data-testid="charfixer-canvas">
        <Layer>
          {/* Background fill — only when no image URL is wired. The Konva
              stage is transparent on top of the parent div's bg-image. */}
          {!imageUrl && (
            <Rect
              x={0}
              y={0}
              width={CANVAS_WIDTH}
              height={CANVAS_HEIGHT}
              fill={readCssToken("--bg-raised", "#1d1d24")}
              listening={false}
              data-testid="charfixer-canvas-background"
            />
          )}
        </Layer>
        <Layer>
          {charBboxes.map((cb, i) => {
            // i % rangePalette.length is always in-bounds — non-null safe.
            const palette = rangePalette[i % rangePalette.length]!;
            const tl = toCanvas(cb.bbox.x, cb.bbox.y);
            const br = toCanvas(cb.bbox.x + cb.bbox.width, cb.bbox.y + cb.bbox.height);
            const overlayX = Math.min(tl.x, br.x);
            const overlayY = Math.min(tl.y, br.y);
            const overlayW = Math.abs(br.x - tl.x);
            const overlayH = Math.abs(br.y - tl.y);
            const isSelected = selectedIndex === i;
            return (
              <Rect
                key={`rect-${i}`}
                data-testid={`charfixer-range-${i}`}
                x={overlayX}
                y={overlayY}
                width={overlayW}
                height={overlayH}
                stroke={palette.stroke}
                strokeWidth={isSelected ? SELECTED_STROKE_WIDTH : UNSELECTED_STROKE_WIDTH}
                fill={palette.fill}
                onClick={() => onSelect(i)}
                onTap={() => onSelect(i)}
              />
            );
          })}
        </Layer>
        <Layer>
          {/* Drag handles for the selected range only — keeps the canvas
              uncluttered when many ranges are present. */}
          {selectedIndex !== null &&
            charBboxes[selectedIndex] &&
            HANDLES.map((h) => {
              // charBboxes[selectedIndex] is truthy (checked above in && chain).
              const cb = charBboxes[selectedIndex]!;
              const c = h.centre(cb.bbox);
              const can = toCanvas(c.x, c.y);
              return (
                <Rect
                  key={`handle-${selectedIndex}-${h.pos}`}
                  data-testid={`charfixer-range-${selectedIndex}-handle-${h.pos}`}
                  x={can.x - HANDLE_SIZE / 2}
                  y={can.y - HANDLE_SIZE / 2}
                  width={HANDLE_SIZE}
                  height={HANDLE_SIZE}
                  fill={handleColors.fill}
                  stroke={handleColors.stroke}
                  strokeWidth={1}
                  draggable
                  onDragMove={handleHandleDragMove(selectedIndex, h.pos)}
                />
              );
            })}
        </Layer>
      </Stage>
    </div>
  );
}

/**
 * Synthesize an initial per-range bbox table from a word bbox + char count.
 * Each char range gets a uniform horizontal slice of the word bbox. Caller
 * passes in the char-range start/end pairs; this helper just computes a
 * sensible default bbox to display until the user moves a handle.
 */
export function initialCharBboxes(
  wordBbox: BBox,
  ranges: ReadonlyArray<{ start: number; end: number }>,
  totalChars: number,
): CharRangeBBox[] {
  if (totalChars <= 0 || ranges.length === 0) return [];
  const charW = wordBbox.width / totalChars;
  return ranges.map((r) => {
    const startIdx = Math.max(0, Math.min(totalChars - 1, r.start));
    const endIdx = Math.max(startIdx, Math.min(totalChars - 1, r.end));
    const x = wordBbox.x + charW * startIdx;
    const width = Math.max(1, charW * (endIdx - startIdx + 1));
    return {
      start: r.start,
      end: r.end,
      bbox: { x, y: wordBbox.y, width, height: wordBbox.height },
    };
  });
}

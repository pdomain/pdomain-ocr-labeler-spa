import type { BBox } from "./coords";

export type ResizeHandle = "n" | "s" | "e" | "w" | "ne" | "nw" | "se" | "sw";

const CORNERS: readonly {
  handle: ResizeHandle;
  x: (box: BBox) => number;
  y: (box: BBox) => number;
}[] = [
  { handle: "nw", x: (box) => box.x, y: (box) => box.y },
  { handle: "ne", x: (box) => box.x + box.width, y: (box) => box.y },
  { handle: "sw", x: (box) => box.x, y: (box) => box.y + box.height },
  { handle: "se", x: (box) => box.x + box.width, y: (box) => box.y + box.height },
];

function near(value: number, target: number, slop: number): boolean {
  return Math.abs(value - target) <= slop;
}

/** Corners win over edges. `slop` is in the same pixel space as `box`. */
export function hitResizeHandle(box: BBox, x: number, y: number, slop = 6): ResizeHandle | null {
  for (const corner of CORNERS) {
    if (near(x, corner.x(box), slop) && near(y, corner.y(box), slop)) {
      return corner.handle;
    }
  }
  const withinX = x >= box.x - slop && x <= box.x + box.width + slop;
  const withinY = y >= box.y - slop && y <= box.y + box.height + slop;
  if (near(y, box.y, slop) && withinX) return "n";
  if (near(y, box.y + box.height, slop) && withinX) return "s";
  if (near(x, box.x, slop) && withinY) return "w";
  if (near(x, box.x + box.width, slop) && withinY) return "e";
  return null;
}

/**
 * Move the named edge to `pointer`, then normalize so width and height stay
 * at least 1. Coordinates are rounded to whole pixels.
 */
export function resizeBox(
  box: BBox,
  handle: ResizeHandle,
  pointer: { x: number; y: number },
): BBox {
  let left = box.x;
  let top = box.y;
  let right = box.x + box.width;
  let bottom = box.y + box.height;
  if (handle.includes("w")) left = pointer.x;
  if (handle.includes("e")) right = pointer.x;
  if (handle.includes("n")) top = pointer.y;
  if (handle.includes("s")) bottom = pointer.y;
  const x1 = Math.min(left, right);
  const y1 = Math.min(top, bottom);
  const x2 = Math.max(left, right);
  const y2 = Math.max(top, bottom);
  return {
    x: Math.round(x1),
    y: Math.round(y1),
    width: Math.max(1, Math.round(x2 - x1)),
    height: Math.max(1, Math.round(y2 - y1)),
  };
}

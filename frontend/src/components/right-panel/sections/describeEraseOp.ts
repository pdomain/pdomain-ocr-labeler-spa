import type { EraseOp } from "./EraseCanvas";

export function describeOp(op: EraseOp, index: number): string {
  if (op.tool === "brush") {
    return `Op ${String(index + 1)}: brush at (${String(Math.round(op.x))},${String(Math.round(op.y))}) r=${String(op.radius)}`;
  }
  if (op.tool === "rect") {
    return `Op ${String(index + 1)}: rect at (${String(Math.round(op.x))},${String(Math.round(op.y))}) ${String(Math.round(op.width))}×${String(Math.round(op.height))}`;
  }
  return `Op ${String(index + 1)}: lasso (${String(op.points.length)} pts)`;
}

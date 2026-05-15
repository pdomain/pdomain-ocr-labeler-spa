// rafSchedule.ts — single-flight requestAnimationFrame scheduler.
// Spec: specs/21-konva-renderer.md §7
// Issue #301
//
// Used to throttle Konva Stage `mousemove` handlers: at 60 Hz a drag can
// fire dozens of mousemove events per frame, but we only want one React
// state update per animation frame. `scheduleDragUpdate(fn)` registers
// `fn` to run on the next animation frame; subsequent calls in the same
// frame are no-ops (the first fn wins — standard rAF-throttle pattern).
// After the frame fires, the scheduler re-arms so the next call schedules
// another frame.
//
// Pure helper — no React imports.

let pending: (() => void) | null = null;

export function scheduleDragUpdate(fn: () => void): void {
  if (pending !== null) {
    // A frame is already scheduled; this call is coalesced.
    return;
  }
  pending = fn;
  requestAnimationFrame(() => {
    const toRun = pending;
    pending = null;
    if (toRun) toRun();
  });
}

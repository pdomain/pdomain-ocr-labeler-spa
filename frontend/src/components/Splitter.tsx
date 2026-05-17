// Splitter.tsx — controlled horizontal splitter with a draggable divider.
//
// Spec: specs/22-page-surface-wireup.md §3 (Layout), §9 (Splitter).
// State persisted in `usePrefsStore.splitterRatio` (D-021). Range clamped
// to [0.2, 0.8]; double-click on the divider resets to 0.5.
//
// Driver-contract note: testids `splitter`, `splitter-left`,
// `splitter-right`, `splitter-divider` are new (legacy NiceGUI labeler
// used a NiceGUI `splitter` widget without testid hooks).
//
// Issue #310 (spec-22-B1).

import React, { useCallback, useEffect, useRef, useSyncExternalStore } from "react";
import { useUiPrefs, clampSplitterRatio } from "../stores/ui-prefs";

export interface SplitterProps {
  /** Currently only horizontal (left/right) is supported per spec 22 §9. */
  direction: "horizontal";
  left: React.ReactNode;
  right: React.ReactNode;
  /** Optional class for the outer container — caller controls layout. */
  className?: string;
}

// ---------------------------------------------------------------------------
// Tiny subscriber for the hand-rolled store. The store doesn't expose a
// real `subscribe`, so we poll via a microtask after every setState. For
// the splitter that's fine — the component re-reads on user interaction
// and on initial mount. We still wire useSyncExternalStore so React 19
// concurrent rendering stays consistent.
// ---------------------------------------------------------------------------

const subscribers = new Set<() => void>();
function notifySubscribers() {
  subscribers.forEach((fn) => {
    fn();
  });
}
function subscribe(cb: () => void): () => void {
  subscribers.add(cb);
  return () => {
    subscribers.delete(cb);
  };
}

function setSplitterRatio(ratio: number) {
  useUiPrefs.setSplitterRatio(ratio);
  notifySubscribers();
}

function getSplitterRatio(): number {
  return useUiPrefs.getState().splitterRatio;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function Splitter({ direction, left, right, className }: SplitterProps) {
  // direction is reserved for future "vertical" support; currently always horizontal
  void direction;

  const ratio = useSyncExternalStore(subscribe, getSplitterRatio, getSplitterRatio);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const draggingRef = useRef(false);

  const onMouseDown = useCallback((event: React.MouseEvent<HTMLDivElement>) => {
    event.preventDefault();
    draggingRef.current = true;
  }, []);

  useEffect(() => {
    function onMove(event: MouseEvent) {
      if (!draggingRef.current) return;
      const container = containerRef.current;
      if (!container) return;
      const rect = container.getBoundingClientRect();
      if (rect.width <= 0) return;
      const next = (event.clientX - rect.left) / rect.width;
      setSplitterRatio(clampSplitterRatio(next));
    }
    function onUp() {
      draggingRef.current = false;
    }
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, []);

  const onDoubleClick = useCallback(() => {
    setSplitterRatio(0.5);
  }, []);

  const leftPct = `${(ratio * 100).toFixed(4).replace(/\.?0+$/, "")}%`;
  const rightPct = `${((1 - ratio) * 100).toFixed(4).replace(/\.?0+$/, "")}%`;

  return (
    <div
      ref={containerRef}
      data-testid="splitter"
      className={className ?? "flex h-full w-full select-none"}
      style={{ display: "flex", width: "100%", height: "100%" }}
    >
      <div
        data-testid="splitter-left"
        style={{ width: leftPct, height: "100%", overflow: "hidden" }}
      >
        {left}
      </div>
      <div
        data-testid="splitter-divider"
        role="separator"
        aria-orientation="vertical"
        aria-valuenow={Math.round(ratio * 100)}
        aria-valuemin={20}
        aria-valuemax={80}
        onMouseDown={onMouseDown}
        onDoubleClick={onDoubleClick}
        style={{
          width: 6,
          cursor: "col-resize",
          background: "var(--border-1)",
          flex: "0 0 6px",
        }}
      />
      <div
        data-testid="splitter-right"
        style={{ width: rightPct, height: "100%", overflow: "hidden" }}
      >
        {right}
      </div>
    </div>
  );
}

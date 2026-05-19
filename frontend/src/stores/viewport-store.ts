// viewport-store.ts — viewport interaction mode store
// Spec: docs/specs/2026-05-12-image-viewport-design.md §Interaction modes
// Issue #197
//
// Tracks the current viewport interaction mode and rebox target.
// Mode is mutually exclusive: select | rebox | add-word | erase
//
// Phase 2.5 (cross-cut-design §7.5): migrated from hand-rolled reactive
// store to Zustand's vanilla `createStore`.
//
// GAP-2: Cannot use pd-ui's `createViewportStore()` factory.
//   pd-ui offers: `scale: number, pan: {x,y}, setScale, setPan, reset`.
//   This store needs: labeler-specific interaction modes (select/rebox/
//   add-word/erase), pendingReboxTarget, and canvasZoom (0 = fit-to-
//   container). These are labeler domain concerns that pd-ui deliberately
//   excludes per §3 "What pd-ui does not include".

import { createStore } from "zustand/vanilla";

export type ViewportMode = "select" | "rebox" | "add-word" | "erase";

interface ReboxTarget {
  lineIndex: number;
  wordIndex: number;
}

export interface ViewportStoreState {
  mode: ViewportMode;
  /** Set when mode === "rebox": identifies which word is being reboxed. */
  pendingReboxTarget: ReboxTarget | null;
  /**
   * Canvas zoom level.
   * 0 = fit-to-container (scale to fill viewport without overflow).
   * 1.0 = 100% natural size (display_width × display_height from server).
   */
  canvasZoom: number;
}

export const viewportStore = createStore<ViewportStoreState>(() => ({
  mode: "select",
  pendingReboxTarget: null,
  canvasZoom: 0, // 0 = fit-to-container (default on page load)
}));

/** Reset mode to select, clearing any pending rebox target. */
export function exitToSelectMode(): void {
  viewportStore.setState({ mode: "select", pendingReboxTarget: null });
}

/** Toggle add-word mode. */
export function toggleAddWordMode(): void {
  viewportStore.setState((s) => ({
    mode: s.mode === "add-word" ? "select" : "add-word",
    pendingReboxTarget: null,
  }));
}

/** Toggle erase mode. */
export function toggleEraseMode(): void {
  viewportStore.setState((s) => ({
    mode: s.mode === "erase" ? "select" : "erase",
    pendingReboxTarget: null,
  }));
}

/**
 * Set canvas zoom level.
 * 0 = fit-to-container; 1.0 = 100% natural size.
 */
export function setCanvasZoom(zoom: number): void {
  viewportStore.setState({ canvasZoom: zoom });
}

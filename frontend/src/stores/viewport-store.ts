// viewport-store.ts — viewport interaction mode store
// Spec: docs/specs/2026-05-12-image-viewport-design.md §Interaction modes
// Issue #197
//
// Tracks the current viewport interaction mode and rebox target.
// Mode is mutually exclusive: select | rebox | add-word | erase

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

type SetStateArg<T> = Partial<T> | ((state: T) => Partial<T>);

interface Store<T> {
  getState: () => T;
  setState: (arg: SetStateArg<T>) => void;
  subscribe: (listener: (state: T) => void) => () => void;
}

function createReactiveStore<T>(initialState: T): Store<T> {
  let state = initialState;
  const listeners = new Set<(state: T) => void>();

  return {
    getState: () => state,
    setState: (arg: SetStateArg<T>) => {
      const patch = typeof arg === "function" ? arg(state) : arg;
      state = { ...state, ...patch };
      listeners.forEach((l) => {
        l(state);
      });
    },
    subscribe: (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}

export const viewportStore = createReactiveStore<ViewportStoreState>({
  mode: "select",
  pendingReboxTarget: null,
  canvasZoom: 0, // 0 = fit-to-container (default on page load)
});

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

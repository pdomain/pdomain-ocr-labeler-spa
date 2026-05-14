// selection-store.ts — optimistic selection state store
// Spec: docs/specs/2026-05-12-image-viewport-design.md §Select mode
// Issue #197
//
// Maintains the current selection optimistically — updated immediately on
// mouse interaction, then confirmed/rolled-back based on POST response.

import type { BBox } from "../lib/coords";

export type SelectionModifier = "replace" | "remove" | "toggle";

export interface SelectionState {
  /** Selected bbox indices for each layer scope. */
  selectedParagraphs: number[];
  selectedLines: number[];
  selectedWords: [number, number][]; // [line_idx, word_idx]
  /** Current drag rect (display pixels), null when not dragging. */
  dragRect: BBox | null;
}

type SetStateArg<T> = T | ((state: T) => T);

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
      const newState = typeof arg === "function" ? (arg as (s: T) => T)(state) : arg;
      state = { ...state, ...newState };
      listeners.forEach((l) => l(state));
    },
    subscribe: (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}

export const selectionStore = createReactiveStore<SelectionState>({
  selectedParagraphs: [],
  selectedLines: [],
  selectedWords: [],
  dragRect: null,
});

/** Clear all selection. */
export function clearSelection(): void {
  selectionStore.setState({
    selectedParagraphs: [],
    selectedLines: [],
    selectedWords: [],
    dragRect: null,
  });
}

/** Set drag rect during box-select drag. */
export function setDragRect(rect: BBox | null): void {
  selectionStore.setState((s) => ({ ...s, dragRect: rect }));
}

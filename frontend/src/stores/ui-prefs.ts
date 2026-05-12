/**
 * Cross-page UI preferences store.
 * Persists within a browser session (not localStorage):
 * - Line filter selection
 * - Layer visibility toggles (paragraph/line/word)
 * - Panel split position
 * - Selection mode
 *
 * Implements a zustand-like API (getState/setState) for testing until zustand is added.
 */

export interface LayerVisibility {
  paragraph: boolean;
  line: boolean;
  word: boolean;
}

export interface UiPrefsState {
  lineFilter: string | null;
  layerVisibility: LayerVisibility;
  splitterPosition: number;
  selectionMode: "box" | "line" | "word";
}

type SetStateArg<T> = T | ((state: T) => T);

interface Store<T> {
  getState: () => T;
  setState: (arg: SetStateArg<T>) => void;
}

function createStore<T>(initialState: T): Store<T> {
  let state = initialState;

  return {
    getState: () => state,
    setState: (arg: SetStateArg<T>) => {
      const newState = typeof arg === "function" ? (arg as Function)(state) : arg;
      state = { ...state, ...newState };
    },
  };
}

export const useUiPrefs = createStore<UiPrefsState>({
  lineFilter: null,
  layerVisibility: {
    paragraph: true,
    line: true,
    word: true,
  },
  splitterPosition: 0.5,
  selectionMode: "box",
});

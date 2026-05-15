export interface LayerVisibility {
  paragraph: boolean;
  line: boolean;
  word: boolean;
}

export interface UiPrefsState {
  lineFilter: string | null;
  layerVisibility: LayerVisibility;
  splitterPosition: number;
  selectionMode: "paragraph" | "line" | "word";
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
      const newState = typeof arg === "function" ? (arg as (s: T) => T)(state) : arg;
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
  selectionMode: "paragraph",
});

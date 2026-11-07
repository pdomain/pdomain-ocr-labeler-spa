// A region drag starts on the canvas and is confirmed in the right panel.
// Those two surfaces do not share a parent that already owns this box, and
// the box is not a server record until Create is pressed. This store is the
// one place that holds that unsaved rectangle, in source pixels.

import { createStore } from "zustand/vanilla";
import type { BBox } from "../lib/coords";

interface RegionDraftState {
  box: BBox | null;
  setBox: (box: BBox) => void;
  clear: () => void;
}

const _store = createStore<RegionDraftState>((set) => ({
  box: null,
  setBox(box: BBox) {
    set({ box });
  },
  clear() {
    set({ box: null });
  },
}));

export const regionDraftStore = {
  getState: () => _store.getState(),
  subscribe: (cb: () => void) => _store.subscribe(cb),
  reset() {
    _store.setState({ box: null });
  },
};

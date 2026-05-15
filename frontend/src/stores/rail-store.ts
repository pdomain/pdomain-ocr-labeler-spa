// rail-store.ts — Rail target/mode selection store.
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 10.
//
// target: "block" | "line" | "word"
//   Governs canvas drag-select scope and right-panel context.
//   Persisted to localStorage under RAIL_TARGET_STORAGE_KEY.
//
// mode: "view" | "region" | "annotate" | "erase"
//   Selection interaction mode — not persisted (resets to "view" on reload).

export type RailTarget = "block" | "para" | "line" | "word";
export type RailMode = "view" | "region" | "annotate" | "erase";

export const RAIL_TARGET_STORAGE_KEY = "pdl.rail.target";

const VALID_TARGETS = new Set<string>(["block", "para", "line", "word"]);
const VALID_MODES = new Set<string>(["view", "region", "annotate", "erase"]);

export interface RailState {
  target: RailTarget;
  mode: RailMode;
  setTarget: (target: RailTarget) => void;
  setMode: (mode: RailMode) => void;
}

type Listener = () => void;

function readPersistedTarget(): RailTarget {
  try {
    const raw = localStorage.getItem(RAIL_TARGET_STORAGE_KEY);
    if (raw && VALID_TARGETS.has(raw)) return raw as RailTarget;
  } catch {
    // localStorage unavailable (SSR, private mode)
  }
  return "word";
}

function makeInitialState(
  setTarget: RailState["setTarget"],
  setMode: RailState["setMode"],
): RailState {
  return {
    target: readPersistedTarget(),
    mode: "view",
    setTarget,
    setMode,
  };
}

function createRailStore() {
  let state: RailState;
  const listeners = new Set<Listener>();

  function notify() {
    listeners.forEach((fn) => fn());
  }

  function setTarget(target: RailTarget) {
    if (!VALID_TARGETS.has(target)) return;
    try {
      localStorage.setItem(RAIL_TARGET_STORAGE_KEY, target);
    } catch {
      // ignore
    }
    state = { ...state, target };
    notify();
  }

  function setMode(mode: RailMode) {
    if (!VALID_MODES.has(mode)) return;
    state = { ...state, mode };
    notify();
  }

  // Initial state built with the action references
  state = makeInitialState(setTarget, setMode);

  return {
    getState: () => state,
    subscribe: (cb: Listener) => {
      listeners.add(cb);
      return () => {
        listeners.delete(cb);
      };
    },
    /** Re-reads persisted state; used in tests to simulate a fresh page load. */
    reset: () => {
      state = {
        ...makeInitialState(setTarget, setMode),
        setTarget,
        setMode,
      };
      notify();
    },
  };
}

export const railStore = createRailStore();

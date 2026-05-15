// dialog-store.ts — central dialog state for OCR-config, export, hotkey-help,
// word-edit, and confirm dialogs.
// Spec: specs/22-page-surface-wireup.md §5 (Dialog launchers)
// Issue #309 (spec-22-A)
//
// No `zustand` package is installed; this module exports a hand-rolled
// reactive store matching the same shape used by `selection-store.ts`,
// plus a `useDialogStore` React hook backed by `useSyncExternalStore`.
//
// Why a single shared store: keeping each dialog's open-flag in its own
// `useState` would force every launcher (HeaderBar trigger buttons,
// global hotkeys, mutation hooks that ask for confirmation) to reach
// into the component owning that flag. A single store lets any caller
// open or close any dialog without prop drilling.

import { useSyncExternalStore } from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Dialog keys with a plain `{ open: boolean }` shape. */
export type SimpleDialogKey = "ocrConfig" | "export" | "hotkeyHelp" | "sourceFolder";

export interface WordEditDialogState {
  open: boolean;
  lineIdx?: number;
  wordIdx?: number;
}

export interface ConfirmDialogState {
  open: boolean;
  title?: string;
  body?: string;
  onConfirm?: () => void;
}

export interface DialogStoreState {
  ocrConfig: { open: boolean };
  export: { open: boolean };
  hotkeyHelp: { open: boolean };
  sourceFolder: { open: boolean };
  wordEdit: WordEditDialogState;
  confirm: ConfirmDialogState;
}

export interface DialogStoreApi {
  /** Open a simple dialog by key. */
  open: (key: SimpleDialogKey) => void;
  /** Close any dialog (simple keys + wordEdit + confirm).
   *  Note: SimpleDialogKey already includes "sourceFolder". */
  close: (key: SimpleDialogKey | "wordEdit" | "confirm") => void;
  /** Open the word-edit dialog with the target line/word indices. */
  openWordEdit: (params: { lineIdx: number; wordIdx: number }) => void;
  /** Open the confirm dialog with title/body/onConfirm. */
  openConfirm: (params: { title: string; body: string; onConfirm: () => void }) => void;
}

// ---------------------------------------------------------------------------
// Store implementation
// ---------------------------------------------------------------------------

const INITIAL_STATE: DialogStoreState = {
  ocrConfig: { open: false },
  export: { open: false },
  hotkeyHelp: { open: false },
  sourceFolder: { open: false },
  wordEdit: { open: false },
  confirm: { open: false },
};

let state: DialogStoreState = INITIAL_STATE;
const listeners = new Set<() => void>();

function notify() {
  listeners.forEach((l) => l());
}

function getState(): DialogStoreState {
  return state;
}

function setState(next: DialogStoreState): void {
  state = next;
  notify();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

const api: DialogStoreApi = {
  open(key) {
    setState({ ...state, [key]: { open: true } });
  },
  close(key) {
    if (key === "wordEdit") {
      setState({ ...state, wordEdit: { open: false } });
    } else if (key === "confirm") {
      setState({ ...state, confirm: { open: false } });
    } else {
      setState({ ...state, [key]: { open: false } });
    }
  },
  openWordEdit({ lineIdx, wordIdx }) {
    setState({ ...state, wordEdit: { open: true, lineIdx, wordIdx } });
  },
  openConfirm({ title, body, onConfirm }) {
    setState({ ...state, confirm: { open: true, title, body, onConfirm } });
  },
};

// ---------------------------------------------------------------------------
// Public surface
// ---------------------------------------------------------------------------

const identity = (s: DialogStoreState) => s;

/**
 * Subscribe to the dialog store from a React component.
 *
 * Without a selector, returns the entire state object. With a selector,
 * returns the selected slice. Selectors must be stable references (or
 * inline simple readers) — `useSyncExternalStore` will re-render on
 * any state change, so prefer the selector form to scope re-renders.
 *
 * Outside of React (e.g. from hotkey handlers or mutation hooks), use
 * `dialogStore.open(...)` / `dialogStore.close(...)` etc. directly.
 */
export function useDialogStore(): DialogStoreState;
export function useDialogStore<T>(selector: (state: DialogStoreState) => T): T;
export function useDialogStore<T>(selector?: (state: DialogStoreState) => T): T | DialogStoreState {
  const sel = (selector ?? identity) as (s: DialogStoreState) => T;
  return useSyncExternalStore(
    subscribe,
    () => sel(getState()),
    () => sel(INITIAL_STATE),
  );
}

/** Imperative API — usable from non-React code (hotkey handlers, mutations). */
export const dialogStore = {
  ...api,
  /** Snapshot of current state. */
  getState,
  /** Subscribe to changes (returns unsubscribe). */
  subscribe,
  /** Reset to initial state — primarily for tests. */
  reset(): void {
    setState(INITIAL_STATE);
  },
};

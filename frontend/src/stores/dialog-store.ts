// dialog-store.ts — central dialog state for OCR-config, export, hotkey-help,
// word-edit, and confirm dialogs.
// Spec: specs/22-page-surface-wireup.md §5 (Dialog launchers)
// Issue #309 (spec-22-A)
//
// Phase 2.5 (cross-cut-design §7.5): migrated from hand-rolled module-level
// listener store to Zustand's vanilla `createStore`. External API preserved
// (`useDialogStore` React hook, `dialogStore` imperative API).
//
// GAP-6: No pd-ui factory covers labeler-specific dialog orchestration.
//   The dialogs managed here (OCR config, export, hotkey help, source folder,
//   word-edit, confirm) are all labeler-specific features. pd-ui ships
//   Radix-based dialog primitives but no store abstraction for domain-level
//   dialog management. This store is kept local permanently.
//
// Why a single shared store: keeping each dialog's open-flag in its own
// `useState` would force every launcher (HeaderBar trigger buttons,
// global hotkeys, mutation hooks that ask for confirmation) to reach
// into the component owning that flag. A single store lets any caller
// open or close any dialog without prop drilling.

import { createStore } from "zustand/vanilla";
import { useSyncExternalStore } from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Dialog keys with a plain `{ open: boolean }` shape. */
type SimpleDialogKey = "ocrConfig" | "export" | "hotkeyHelp" | "sourceFolder";

interface WordEditDialogState {
  open: boolean;
  lineIdx?: number;
  wordIdx?: number;
}

interface ConfirmDialogState {
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

interface DialogStoreApi {
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

const _store = createStore<DialogStoreState>(() => ({ ...INITIAL_STATE }));

const api: DialogStoreApi = {
  open(key) {
    _store.setState((s) => ({ ...s, [key]: { open: true } }));
  },
  close(key) {
    if (key === "wordEdit") {
      _store.setState((s) => ({ ...s, wordEdit: { open: false } }));
    } else if (key === "confirm") {
      _store.setState((s) => ({ ...s, confirm: { open: false } }));
    } else {
      _store.setState((s) => ({ ...s, [key]: { open: false } }));
    }
  },
  openWordEdit({ lineIdx, wordIdx }) {
    _store.setState((s) => ({ ...s, wordEdit: { open: true, lineIdx, wordIdx } }));
  },
  openConfirm({ title, body, onConfirm }) {
    _store.setState((s) => ({ ...s, confirm: { open: true, title, body, onConfirm } }));
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
    (cb) => _store.subscribe(cb),
    () => sel(_store.getState()),
    () => sel(INITIAL_STATE),
  );
}

/** Imperative API — usable from non-React code (hotkey handlers, mutations). */
export const dialogStore = {
  ...api,
  /** Snapshot of current state. */
  getState: () => _store.getState(),
  /** Subscribe to changes (returns unsubscribe). */
  subscribe: (cb: () => void) => _store.subscribe(cb),
  /** Reset to initial state — primarily for tests. */
  reset(): void {
    _store.setState({ ...INITIAL_STATE });
  },
};

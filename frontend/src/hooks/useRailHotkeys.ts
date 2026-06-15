// useRailHotkeys.ts — Keyboard shortcuts for the Rail target/mode selectors.
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 10.
//
// Shortcuts (active when no input/textarea is focused):
//   1 → target=block
//   2 → target=para
//   3 → target=line
//   4 → target=word
//   v/V → mode=view
//   r/R → mode=region
//   a/A → mode=annotate
//   e/E → mode=erase
//
// SEL-3: target hotkeys (2/3/4) also sync uiPrefs.selectionMode.
// Key 1 (block) leaves selectionMode unchanged — block has no counterpart.

import { useEffect } from "react";
import { railStore, type RailTarget, type RailMode } from "../stores/rail-store";
import { useUiPrefs } from "../stores/ui-prefs";

const TARGET_KEYS: Record<string, RailTarget> = {
  "1": "block",
  "2": "para",
  "3": "line",
  "4": "word",
};

const MODE_KEYS: Record<string, RailMode> = {
  v: "view",
  V: "view",
  r: "region",
  R: "region",
  a: "annotate",
  A: "annotate",
  e: "erase",
  E: "erase",
};

function isInputFocused(): boolean {
  const el = document.activeElement;
  if (!el) return false;
  const tag = el.tagName.toLowerCase();
  return tag === "input" || tag === "textarea" || (el as HTMLElement).isContentEditable;
}

export function useRailHotkeys() {
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      // Don't steal keystrokes when the user is typing in an input.
      if (isInputFocused()) return;
      // Don't act on modified keys (Ctrl+R shouldn't trigger region mode).
      if (e.ctrlKey || e.metaKey || e.altKey) return;

      const { setTarget, setMode } = railStore.getState();

      // Shift+digit belongs to the viewport selection-mode hotkeys
      // (useViewportHotkeys "shift+1/2/3", spec 21 §10). Some browser/layout
      // combinations still report key="1" for Shift+1, which would let the
      // plain-digit rail binding hijack the selection-mode hotkey and
      // overwrite railStore.target (observed in the SEL-3 e2e). Mode keys
      // (v/V, r/R, …) intentionally accept Shift for their uppercase forms.
      const target = e.shiftKey ? undefined : TARGET_KEYS[e.key];
      if (target) {
        e.preventDefault();
        setTarget(target);
        // SEL-3: sync selectionMode so the header radio stays consistent.
        if (target === "para") {
          useUiPrefs.setState({ selectionMode: "paragraph" });
        } else if (target === "line" || target === "word") {
          useUiPrefs.setState({ selectionMode: target });
        }
        // target === "block": no selectionMode update (no radio counterpart).
        return;
      }

      const mode = MODE_KEYS[e.key];
      if (mode) {
        e.preventDefault();
        setMode(mode);
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, []);
}

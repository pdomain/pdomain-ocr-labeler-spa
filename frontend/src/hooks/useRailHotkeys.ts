// useRailHotkeys.ts — Keyboard shortcuts for the Rail target/mode selectors.
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 10.
//
// Shortcuts (active when no input/textarea is focused):
//   1 → target=block
//   2 → target=line
//   3 → target=word
//   v/V → mode=view
//   r/R → mode=region
//   a/A → mode=annotate
//   e/E → mode=erase

import { useEffect } from "react";
import { railStore, type RailTarget, type RailMode } from "../stores/rail-store";

const TARGET_KEYS: Record<string, RailTarget> = {
  "1": "block",
  "2": "line",
  "3": "word",
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

      const target = TARGET_KEYS[e.key];
      if (target) {
        e.preventDefault();
        setTarget(target);
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

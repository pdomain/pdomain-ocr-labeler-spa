// useRailHotkeys.ts — Keyboard shortcuts for the Rail target/mode selectors.
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 10.
//
// Shortcuts (active when no input/textarea is focused):
//   1 → target=block
//   2 → target=para
//   3 → target=line
//   4 → target=word
//   5 → target=region
//   v/V → mode=view
//   r/R → mode=region
//   a/A → mode=annotate (unless the Shift modifier is held — see below)
//   e/E → mode=erase    (unless the Shift modifier is held — see below)
//
// SEL-3: target hotkeys (2/3/4) also sync uiPrefs.selectionMode.
// Keys 1 (block) and 5 (region) leave selectionMode unchanged — neither has a
// selectionMode counterpart.
//
// P1-CANVAS-ERASE follow-up (reviewer finding 3): Shift+E and Shift+A belong
// to the viewport's own hotkeys (useViewportHotkeys "shift+e" toggle-erase,
// "shift+a" add-word — spec 21 §10). Both this hook and useViewportHotkeys
// listen at document scope, so a single Shift+E keypress used to fire BOTH:
// this hook's own MODE_KEYS entry for "E" set railStore.mode = "erase",
// which PageImageCanvas's rail→viewport sync effect mirrors onto
// viewportStore — then useViewportHotkeys' own toggle ran too and flipped
// viewportStore right back to "select", netting a no-op the user could never
// get out of by pressing the key again. The exact rule already applied to
// Shift+digit below (the viewport owns Shift+1/2/3 selection-mode hotkeys
// too) now extends to the two letters the viewport owns, E and A: while
// Shift is held, "e"/"E" and "a"/"A" no longer drive rail mode at all,
// leaving the viewport hotkey as the sole handler. Un-shifted "e"/"E" (e.g.
// typed with caps lock, no Shift modifier) still work exactly as before — it
// is specifically the Shift modifier the viewport owns for these two
// letters, not the uppercase character. V and R are NOT viewport hotkeys, so
// Shift+V / Shift+R still drive rail mode exactly as before — nothing else
// claims them.

import { useEffect } from "react";
import { railStore, type RailTarget, type RailMode } from "../stores/rail-store";
import { useUiPrefs } from "../stores/ui-prefs";

const TARGET_KEYS: Record<string, RailTarget> = {
  "1": "block",
  "2": "para",
  "3": "line",
  "4": "word",
  "5": "region",
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

/**
 * Mode keys the viewport's own Shift-prefixed hotkeys own (Shift+E toggles
 * viewport erase mode, Shift+A toggles add-word mode — useViewportHotkeys,
 * spec 21 §10). While Shift is held, these must not also drive rail mode —
 * see the module docstring's P1-CANVAS-ERASE follow-up note.
 */
const SHIFT_OWNED_BY_VIEWPORT = new Set(["e", "E", "a", "A"]);

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
      // overwrite railStore.target (observed in the SEL-3 e2e). V/v and R/r
      // still accept Shift for their uppercase forms — the viewport does not
      // own Shift+V or Shift+R; E/e and A/a do not (see SHIFT_OWNED_BY_
      // VIEWPORT and the module docstring's P1-CANVAS-ERASE follow-up note).
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

      const mode = e.shiftKey && SHIFT_OWNED_BY_VIEWPORT.has(e.key) ? undefined : MODE_KEYS[e.key];
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

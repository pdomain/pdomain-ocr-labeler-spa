// hotkeyMap.undo.test.ts — undo/redo hotkeys advertised in the keymap (H-C).
//
// Spec: docs/specs/2026-06-12-event-store-undo.md §"Driver-contract testids":
// Mod+Z / Mod+Shift+Z are registered via the real useHotkey path AND listed
// in the hotkey map + help modal (F20 lesson: never advertise unbound
// hotkeys, never bind unadvertised ones). The HotkeyHelpModal completeness
// invariant bridges HOTKEY_MAP into the modal, so listing here is what makes
// the modal show them.

import { describe, it, expect } from "vitest";
import { HOTKEY_MAP } from "./hotkeyMap";

describe("HOTKEY_MAP: undo/redo entries (H-C)", () => {
  it("lists mod+z (global undo)", () => {
    const entry = HOTKEY_MAP.find((e) => e.combo === "mod+z" && e.scope === "global");
    expect(entry).toBeDefined();
    expect(entry?.description).toMatch(/undo/i);
  });

  it("lists mod+shift+z (global redo)", () => {
    const entry = HOTKEY_MAP.find((e) => e.combo === "mod+shift+z" && e.scope === "global");
    expect(entry).toBeDefined();
    expect(entry?.description).toMatch(/redo/i);
  });

  it("mod+l description reflects the Reload rename (U-7)", () => {
    const entry = HOTKEY_MAP.find((e) => e.combo === "mod+l" && e.scope === "global");
    expect(entry).toBeDefined();
    expect(entry?.description).toMatch(/reload/i);
    // The stale "Load Page from disk" copy is gone (the head blob is the
    // source, not a disk envelope).
    expect(entry?.description ?? "").not.toMatch(/from disk/i);
  });
});

// hotkey-bridge.test.ts — unit tests for the HOTKEY_MAP → registry bridge.
// Issue #329 (FO-6).
//
// Acceptance:
//   - comboToKeyCap correctly converts combo strings to display tokens
//   - scopeToGroup maps every Scope value to a defined HotkeyGroup
//   - buildBridgedEntries returns one entry per HOTKEY_MAP entry
//   - No bridged entry is missing a label or keyCap
//   - Key combos from all scopes are represented in the output

import { describe, it, expect } from "vitest";
import { comboToKeyCap, scopeToGroup, buildBridgedEntries } from "./hotkey-bridge";
import { HOTKEY_MAP } from "./hotkeyMap";

// ─── comboToKeyCap ────────────────────────────────────────────────────────────

describe("comboToKeyCap", () => {
  it("converts 'mod+s' to ['Ctrl', 'S']", () => {
    expect(comboToKeyCap("mod+s")).toEqual(["Ctrl", "S"]);
  });

  it("converts 'mod+shift+s' to ['Ctrl', 'Shift', 'S']", () => {
    expect(comboToKeyCap("mod+shift+s")).toEqual(["Ctrl", "Shift", "S"]);
  });

  it("converts '?' to ['?']", () => {
    expect(comboToKeyCap("?")).toEqual(["?"]);
  });

  it("converts 'escape' to ['Esc']", () => {
    expect(comboToKeyCap("escape")).toEqual(["Esc"]);
  });

  it("converts 'enter' to ['Enter']", () => {
    expect(comboToKeyCap("enter")).toEqual(["Enter"]);
  });

  it("converts 'shift+enter' to ['Shift', 'Enter']", () => {
    expect(comboToKeyCap("shift+enter")).toEqual(["Shift", "Enter"]);
  });

  it("converts 'mod+arrowleft' to ['Ctrl', '←']", () => {
    expect(comboToKeyCap("mod+arrowleft")).toEqual(["Ctrl", "←"]);
  });

  it("converts 'mod+arrowright' to ['Ctrl', '→']", () => {
    expect(comboToKeyCap("mod+arrowright")).toEqual(["Ctrl", "→"]);
  });

  it("converts 'mod+home' to ['Ctrl', 'Home']", () => {
    expect(comboToKeyCap("mod+home")).toEqual(["Ctrl", "Home"]);
  });

  it("converts 'shift+p' to ['Shift', 'P']", () => {
    expect(comboToKeyCap("shift+p")).toEqual(["Shift", "P"]);
  });

  it("converts 'delete' to ['Del']", () => {
    expect(comboToKeyCap("delete")).toEqual(["Del"]);
  });

  it("converts 'tab' to ['Tab']", () => {
    expect(comboToKeyCap("tab")).toEqual(["Tab"]);
  });

  it("converts 'j' to ['J']", () => {
    expect(comboToKeyCap("j")).toEqual(["J"]);
  });

  it("converts 'v' to ['V']", () => {
    expect(comboToKeyCap("v")).toEqual(["V"]);
  });
});

// ─── scopeToGroup ─────────────────────────────────────────────────────────────

describe("scopeToGroup", () => {
  it("maps global page-nav combos to 'navigation'", () => {
    expect(scopeToGroup("global", "mod+arrowleft")).toBe("navigation");
    expect(scopeToGroup("global", "mod+arrowright")).toBe("navigation");
    expect(scopeToGroup("global", "mod+home")).toBe("navigation");
    expect(scopeToGroup("global", "mod+end")).toBe("navigation");
    expect(scopeToGroup("global", "mod+j")).toBe("navigation");
  });

  it("maps global modal-opener combos to 'view'", () => {
    expect(scopeToGroup("global", "?")).toBe("view");
    expect(scopeToGroup("global", "mod+,")).toBe("view");
    expect(scopeToGroup("global", "mod+o")).toBe("view");
    expect(scopeToGroup("global", "escape")).toBe("view");
  });

  it("maps global editing combos to 'editing'", () => {
    expect(scopeToGroup("global", "mod+s")).toBe("editing");
    expect(scopeToGroup("global", "mod+shift+s")).toBe("editing");
    expect(scopeToGroup("global", "mod+r")).toBe("editing");
    expect(scopeToGroup("global", "mod+e")).toBe("editing");
  });

  it("maps viewport scope to 'selection'", () => {
    expect(scopeToGroup("viewport", "shift+1")).toBe("selection");
    expect(scopeToGroup("viewport", "shift+p")).toBe("selection");
    expect(scopeToGroup("viewport", "escape")).toBe("selection");
  });

  it("maps matches scope to 'editing'", () => {
    expect(scopeToGroup("matches", "v")).toBe("editing");
    expect(scopeToGroup("matches", "j")).toBe("editing");
  });

  it("maps dialog scope to 'editing'", () => {
    expect(scopeToGroup("dialog", "enter")).toBe("editing");
    expect(scopeToGroup("dialog", "arrowleft")).toBe("editing");
  });

  it("maps source-folder scope to 'other'", () => {
    expect(scopeToGroup("source-folder", "enter")).toBe("other");
    expect(scopeToGroup("source-folder", "escape")).toBe("other");
  });

  it("maps gt-input scope to 'editing'", () => {
    expect(scopeToGroup("gt-input", "tab")).toBe("editing");
    expect(scopeToGroup("gt-input", "enter")).toBe("editing");
  });
});

// ─── buildBridgedEntries ──────────────────────────────────────────────────────

describe("buildBridgedEntries", () => {
  const entries = buildBridgedEntries();

  it("returns one entry per HOTKEY_MAP entry", () => {
    expect(entries).toHaveLength(HOTKEY_MAP.length);
  });

  it("every entry has a non-empty label", () => {
    for (const entry of entries) {
      expect(entry.label, `entry missing label`).toBeTruthy();
    }
  });

  it("every entry has at least one keyCap", () => {
    for (const entry of entries) {
      expect(entry.keyCaps.length, `entry "${entry.label}" has no keyCaps`).toBeGreaterThan(0);
      expect(entry.keyCaps[0].length, `entry "${entry.label}" keyCap is empty`).toBeGreaterThan(0);
    }
  });

  it("every entry has a defined group", () => {
    const validGroups = new Set(["selection", "navigation", "editing", "view", "other"]);
    for (const entry of entries) {
      expect(validGroups, `unknown group "${entry.group}" for "${entry.label}"`).toContain(
        entry.group,
      );
    }
  });

  it("includes Save Page (mod+s global) in editing group", () => {
    const entry = entries.find((e) => e.label === "Save Page");
    expect(entry).toBeDefined();
    expect(entry!.group).toBe("editing");
    expect(entry!.keyCaps[0]).toEqual(["Ctrl", "S"]);
  });

  it("includes Previous page (mod+arrowleft) in navigation group", () => {
    const entry = entries.find((e) => e.label === "Previous page");
    expect(entry).toBeDefined();
    expect(entry!.group).toBe("navigation");
    expect(entry!.keyCaps[0]).toContain("←");
  });

  it("includes viewport selection mode entries in selection group", () => {
    const selectionEntries = entries.filter((e) => e.group === "selection");
    expect(selectionEntries.length).toBeGreaterThanOrEqual(3);
  });

  it("includes matches hotkeys (j/k/v) in editing group", () => {
    const jEntry = entries.find((e) => e.label === "Next line card");
    const vEntry = entries.find((e) => e.label === "Validate line");
    expect(jEntry).toBeDefined();
    expect(jEntry!.group).toBe("editing");
    expect(vEntry).toBeDefined();
    expect(vEntry!.group).toBe("editing");
  });
});

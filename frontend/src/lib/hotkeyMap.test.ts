// hotkeyMap.test.ts — unit tests for the static keymap.
// Spec: docs/specs/2026-05-12-hotkeys-a11y-design.md
// Issue #235
//
// Acceptance:
//   - Every entry has a unique combo within its scope
//   - All entries have non-empty descriptions
//   - All scopes are from the defined Scope union
//   - HOTKEY_MAP is importable and is a non-empty array

import { describe, it, expect } from "vitest";
import { HOTKEY_MAP, type Scope } from "./hotkeyMap";

const VALID_SCOPES: Scope[] = [
  "global",
  "viewport",
  "matches",
  "dialog",
  "source-folder",
  "gt-input",
  "region-review",
];

describe("hotkeyMap", () => {
  it("is a non-empty array", () => {
    expect(Array.isArray(HOTKEY_MAP)).toBe(true);
    expect(HOTKEY_MAP.length).toBeGreaterThan(0);
  });

  it("every entry has a non-empty combo", () => {
    for (const entry of HOTKEY_MAP) {
      expect(entry.combo, `entry scope=${entry.scope} missing combo`).toBeTruthy();
    }
  });

  it("every entry has a non-empty description", () => {
    for (const entry of HOTKEY_MAP) {
      expect(entry.description, `combo=${entry.combo} missing description`).toBeTruthy();
    }
  });

  it("every entry scope is from the valid scope set", () => {
    for (const entry of HOTKEY_MAP) {
      expect(VALID_SCOPES, `unknown scope: ${entry.scope}`).toContain(entry.scope);
    }
  });

  it("combos are unique within each scope", () => {
    const byScope = new Map<Scope, Set<string>>();
    for (const entry of HOTKEY_MAP) {
      if (!byScope.has(entry.scope)) byScope.set(entry.scope, new Set());
      const set = byScope.get(entry.scope)!;
      expect(
        set.has(entry.combo),
        `duplicate combo "${entry.combo}" in scope "${entry.scope}"`,
      ).toBe(false);
      set.add(entry.combo);
    }
  });

  it("includes the Mod+S (Save Page) global hotkey", () => {
    const entry = HOTKEY_MAP.find((e) => e.scope === "global" && e.combo === "mod+s");
    expect(entry).toBeDefined();
  });

  it("includes the ? (help) global hotkey, registered by character (useKey)", () => {
    // "shift+?", matched by KeyboardEvent.key via useKey: true — not a
    // physical code — so it works on every keyboard layout, not just US
    // (see hotkeyMap.ts header comment).
    const entry = HOTKEY_MAP.find((e) => e.scope === "global" && e.combo === "shift+?");
    expect(entry).toBeDefined();
  });

  it("includes the Mod+, (OCR Config) global hotkey, registered by character (useKey)", () => {
    const entry = HOTKEY_MAP.find((e) => e.scope === "global" && e.combo === "mod+,");
    expect(entry).toBeDefined();
  });

  it("includes Mod+R (Reload OCR) global hotkey", () => {
    const entry = HOTKEY_MAP.find((e) => e.scope === "global" && e.combo === "mod+r");
    expect(entry).toBeDefined();
  });

  it("includes the region-review scope's eight keys (Task 5 + book review queue)", () => {
    const combos = HOTKEY_MAP.filter((e) => e.scope === "region-review").map((e) => e.combo);
    expect(combos.sort()).toEqual(
      ["5", "delete", "enter", "n", "p", "x", "bracketleft", "bracketright"].sort(),
    );
  });
});

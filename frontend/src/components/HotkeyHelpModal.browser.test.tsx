// HotkeyHelpModal.browser.test.tsx — real-browser dialog-positioning guard.
//
// Runs under vitest.browser.config.ts (Playwright/Chromium), not jsdom —
// see that file's header comment for why. jsdom never runs layout, so it
// cannot see the double-CSS-transform bug this pins
// (src/test/dialogPositioning.ts's `expectNoDuplicateDialogPositioning` is
// the cheap, jsdom-safe proxy for the exact class list that one incident
// used; this is the real guard, checking an actual computed box). Any
// reintroduction of off-screen dialog positioning — this exact bug, or a
// different CSS rule that produces the same effect — fails here regardless
// of which classes or styles caused it.

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { HotkeyHelpModal } from "./HotkeyHelpModal";
import { dialogStore } from "../stores/dialog-store";

beforeEach(() => {
  dialogStore.reset();
  dialogStore.open("hotkeyHelp");
});

afterEach(() => {
  dialogStore.reset();
});

describe("HotkeyHelpModal: real-browser dialog positioning", () => {
  it("renders the dialog box and its close button fully inside the viewport", () => {
    render(<HotkeyHelpModal />);

    const dialogBox = screen.getByTestId("hotkey-help-dialog").getBoundingClientRect();
    const closeButtonBox = screen.getByTestId("hotkey-help-close").getBoundingClientRect();

    for (const [label, box] of [
      ["dialog", dialogBox],
      ["close button", closeButtonBox],
    ] as const) {
      expect(
        box.width,
        `${label} has zero width — not actually rendered/measurable`,
      ).toBeGreaterThan(0);
      expect(
        box.height,
        `${label} has zero height — not actually rendered/measurable`,
      ).toBeGreaterThan(0);
      expect(box.top, `${label} top is above the viewport`).toBeGreaterThanOrEqual(0);
      expect(box.left, `${label} left is left of the viewport`).toBeGreaterThanOrEqual(0);
      expect(box.right, `${label} right is right of the viewport`).toBeLessThanOrEqual(
        window.innerWidth,
      );
      expect(box.bottom, `${label} bottom is below the viewport`).toBeLessThanOrEqual(
        window.innerHeight,
      );
    }
  });
});

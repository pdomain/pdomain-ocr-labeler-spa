// index-css.test.ts — Verify index.css does not shadow the design system --accent token.
//
// The shadcn @layer base block historically included --accent HSL triplets that
// conflict with the design system's --accent hex value in tokens.css.
// These lines must be removed or commented out so tokens.css wins.

import { readFileSync } from "fs";
import { resolve } from "path";
import { describe, it, expect } from "vitest";

describe("index.css shadcn/design-system conflict guard", () => {
  // Read index.css from the parent of the styles directory.
  const css = readFileSync(resolve(__dirname, "../index.css"), "utf-8");

  it("does not contain an active --accent HSL shadcn override in :root", () => {
    // The line `--accent: 0 0% 9.2%;` (shadcn default HSL) must not be active.
    // A commented-out version is acceptable; active assignment is not.
    const activeAccentHsl = /^\s*--accent:\s*0\s+0%\s+9\.2%;/m;
    expect(css).not.toMatch(activeAccentHsl);
  });

  it("does not contain an active --accent-foreground HSL shadcn override in :root", () => {
    // The line `--accent-foreground: 0 0% 100%;` must not be active.
    const activeAccentFg = /^\s*--accent-foreground:\s*0\s+0%\s+100%;/m;
    expect(css).not.toMatch(activeAccentFg);
  });

  it("does not contain an active --accent HSL shadcn override in .dark", () => {
    // The line `--accent: 0 0% 98.2%;` in .dark must not be active.
    const activeDarkAccentHsl = /^\s*--accent:\s*0\s+0%\s+98\.2%;/m;
    expect(css).not.toMatch(activeDarkAccentHsl);
  });

  it("still contains --radius (shadcn layout var should remain)", () => {
    expect(css).toContain("--radius:");
  });

  it("still imports tokens.css design system", () => {
    expect(css).toContain("@import");
    expect(css).toContain("tokens.css");
  });
});

import { readFileSync } from "fs";
import { resolve } from "path";
import { describe, it, expect } from "vitest";

describe("font setup", () => {
  const indexCss = readFileSync(resolve(__dirname, "../index.css"), "utf-8");

  it("body sets Inter as primary font", () => {
    expect(indexCss).toContain("font-family: Inter");
  });

  it("body uses ink-1 color token", () => {
    expect(indexCss).toContain("color: var(--ink-1)");
  });

  it("body uses bg-page background token", () => {
    expect(indexCss).toContain("background: var(--bg-page)");
  });

  it("font-pgdp utility exists and targets JetBrains Mono", () => {
    // Tailwind 4 declares custom utilities with @utility rather than a bare
    // class inside @layer components.
    expect(indexCss).toContain("@utility font-pgdp");
    expect(indexCss).toContain("JetBrains Mono");
  });
});

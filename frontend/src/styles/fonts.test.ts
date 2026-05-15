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
    expect(indexCss).toContain(".font-pgdp");
    expect(indexCss).toContain("JetBrains Mono");
  });
});

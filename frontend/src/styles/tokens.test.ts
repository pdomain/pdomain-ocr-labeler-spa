import { readFileSync } from "fs";
import { resolve } from "path";
import { describe, it, expect } from "vitest";

describe("tokens.css", () => {
  const css = readFileSync(resolve(__dirname, "./tokens.css"), "utf-8");

  it("dark default has correct bg-page", () => {
    expect(css).toContain("--bg-page: #0c0c10");
  });

  it("light override has correct bg-page", () => {
    expect(css).toContain("--bg-page: #f6f4ef");
  });

  it("dark accent is amber", () => {
    expect(css).toContain("--accent: #d6925a");
  });

  it("light accent is terracotta", () => {
    expect(css).toContain("--accent: #b85a2e");
  });

  it("has all 5 status tokens in dark", () => {
    expect(css).toContain("--status-exact: #5fbf6a");
    expect(css).toContain("--status-fuzzy: #e8a83a");
    expect(css).toContain("--status-mismatch: #dc6555");
    expect(css).toContain("--status-ocr: #5d9fdf");
    expect(css).toContain("--status-gt: #a888d4");
  });

  it("has all 4 layer tokens in dark", () => {
    expect(css).toContain("--layer-block: #a89074");
    expect(css).toContain("--layer-para: #7fb56a");
    expect(css).toContain("--layer-line: #d088a8");
    expect(css).toContain("--layer-word: #6e9cdf");
  });

  it("has all 5 status tokens in light", () => {
    expect(css).toContain("--status-exact: #2d8c3a");
    expect(css).toContain("--status-fuzzy: #b87b1f");
    expect(css).toContain("--status-mismatch: #b13d32");
    expect(css).toContain("--status-ocr: #2d6fb5");
    expect(css).toContain("--status-gt: #6e4ea5");
  });

  it("has all 4 layer tokens in light", () => {
    expect(css).toContain("--layer-block: #7a5e3a");
    expect(css).toContain("--layer-para: #4d8a3a");
    expect(css).toContain("--layer-line: #a8527a");
    expect(css).toContain("--layer-word: #3d6bb8");
  });
});

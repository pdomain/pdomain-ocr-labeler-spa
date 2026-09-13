import { readFileSync } from "fs";
import { resolve } from "path";
import { describe, it, expect } from "vitest";

// Tailwind 4 moved the theme out of tailwind.config.js and into an `@theme`
// block in index.css, and the config file is gone. This suite used to import
// that config and assert its object shape; it now asserts the same tokens in
// the place they actually live. A missing token here means the matching
// utility class silently stops resolving, which is what it has always guarded.
const indexCss = readFileSync(resolve(__dirname, "../index.css"), "utf-8");

const themeBlock = (() => {
  const start = indexCss.indexOf("@theme");
  if (start === -1) return "";
  return indexCss.slice(start, indexCss.indexOf("}", start) + 1);
})();

function expectToken(name: string, value: string): void {
  expect(themeBlock).toContain(`${name}: ${value}`);
}

describe("index.css @theme tokens", () => {
  it("defines an @theme block", () => {
    expect(themeBlock).not.toBe("");
  });

  describe("bg colors", () => {
    it.each([
      ["--color-bg-page", "var(--bg-page)"],
      ["--color-bg-surface", "var(--bg-surface)"],
      ["--color-bg-raised", "var(--bg-raised)"],
      ["--color-bg-sunk", "var(--bg-sunk)"],
    ])("%s maps to %s", (name, value) => expectToken(name, value));
  });

  describe("border colors", () => {
    it.each([
      ["--color-border-1", "var(--border-1)"],
      ["--color-border-2", "var(--border-2)"],
      ["--color-border-3", "var(--border-3)"],
    ])("%s maps to %s", (name, value) => expectToken(name, value));
  });

  describe("ink colors", () => {
    it.each([
      ["--color-ink-1", "var(--ink-1)"],
      ["--color-ink-2", "var(--ink-2)"],
      ["--color-ink-3", "var(--ink-3)"],
      ["--color-ink-4", "var(--ink-4)"],
    ])("%s maps to %s", (name, value) => expectToken(name, value));
  });

  describe("accent colors", () => {
    it.each([
      ["--color-accent", "var(--accent)"],
      ["--color-accent-ink", "var(--accent-ink)"],
    ])("%s maps to %s", (name, value) => expectToken(name, value));
  });

  describe("status colors", () => {
    it.each([
      ["--color-status-exact", "var(--status-exact)"],
      ["--color-status-fuzzy", "var(--status-fuzzy)"],
      ["--color-status-mismatch", "var(--status-mismatch)"],
      ["--color-status-ocr", "var(--status-ocr)"],
      ["--color-status-gt", "var(--status-gt)"],
    ])("%s maps to %s", (name, value) => expectToken(name, value));
  });

  describe("layer colors", () => {
    it.each([
      ["--color-layer-block", "var(--layer-block)"],
      ["--color-layer-para", "var(--layer-para)"],
      ["--color-layer-line", "var(--layer-line)"],
      ["--color-layer-word", "var(--layer-word)"],
    ])("%s maps to %s", (name, value) => expectToken(name, value));
  });

  describe("fonts", () => {
    it("ui font family is defined", () => {
      expect(themeBlock).toMatch(/--font-ui:.*Inter/);
    });

    it("mono font family is defined", () => {
      expect(themeBlock).toMatch(/--font-mono:.*JetBrains Mono/);
    });
  });

  describe("text sizes", () => {
    it.each([
      ["--text-label", "9.5px", "1.1"],
      ["--text-hint", "10px", "1.2"],
      ["--text-btn-sm", "11px", "1.2"],
      ["--text-body", "12px", "1.4"],
      ["--text-heading", "13px", "1.3"],
    ])("%s is %s with line height %s", (name, size, lineHeight) => {
      expectToken(name, size);
      expectToken(`${name}--line-height`, lineHeight);
    });
  });
});

import { describe, it, expect } from "vitest";
import config from "../../tailwind.config.js";

describe("tailwind.config theme.extend", () => {
  const colors = config.theme?.extend?.colors ?? {};

  describe("bg colors", () => {
    it("bg.page maps to CSS var", () => {
      expect(colors.bg?.page).toBe("var(--bg-page)");
    });

    it("bg.surface maps to CSS var", () => {
      expect(colors.bg?.surface).toBe("var(--bg-surface)");
    });

    it("bg.raised maps to CSS var", () => {
      expect(colors.bg?.raised).toBe("var(--bg-raised)");
    });

    it("bg.sunk maps to CSS var", () => {
      expect(colors.bg?.sunk).toBe("var(--bg-sunk)");
    });
  });

  describe("border colors", () => {
    it("border.1 maps to CSS var", () => {
      expect(colors.border?.["1"]).toBe("var(--border-1)");
    });

    it("border.2 maps to CSS var", () => {
      expect(colors.border?.["2"]).toBe("var(--border-2)");
    });

    it("border.3 maps to CSS var", () => {
      expect(colors.border?.["3"]).toBe("var(--border-3)");
    });
  });

  describe("ink colors", () => {
    it("ink.1 maps to CSS var", () => {
      expect(colors.ink?.["1"]).toBe("var(--ink-1)");
    });

    it("ink.2 maps to CSS var", () => {
      expect(colors.ink?.["2"]).toBe("var(--ink-2)");
    });

    it("ink.3 maps to CSS var", () => {
      expect(colors.ink?.["3"]).toBe("var(--ink-3)");
    });

    it("ink.4 maps to CSS var", () => {
      expect(colors.ink?.["4"]).toBe("var(--ink-4)");
    });
  });

  describe("accent colors", () => {
    it("accent.DEFAULT maps to CSS var", () => {
      expect(colors.accent?.DEFAULT).toBe("var(--accent)");
    });

    it("accent.ink maps to CSS var", () => {
      expect(colors.accent?.ink).toBe("var(--accent-ink)");
    });
  });

  describe("status colors", () => {
    it("status.exact maps to CSS var", () => {
      expect(colors.status?.exact).toBe("var(--status-exact)");
    });

    it("status.fuzzy maps to CSS var", () => {
      expect(colors.status?.fuzzy).toBe("var(--status-fuzzy)");
    });

    it("status.mismatch maps to CSS var", () => {
      expect(colors.status?.mismatch).toBe("var(--status-mismatch)");
    });

    it("status.ocr maps to CSS var", () => {
      expect(colors.status?.ocr).toBe("var(--status-ocr)");
    });

    it("status.gt maps to CSS var", () => {
      expect(colors.status?.gt).toBe("var(--status-gt)");
    });
  });

  describe("layer colors", () => {
    it("layer.block maps to CSS var", () => {
      expect(colors.layer?.block).toBe("var(--layer-block)");
    });

    it("layer.para maps to CSS var", () => {
      expect(colors.layer?.para).toBe("var(--layer-para)");
    });

    it("layer.line maps to CSS var", () => {
      expect(colors.layer?.line).toBe("var(--layer-line)");
    });

    it("layer.word maps to CSS var", () => {
      expect(colors.layer?.word).toBe("var(--layer-word)");
    });
  });

  describe("fontFamily", () => {
    const fontFamily = config.theme?.extend?.fontFamily ?? {};

    it("ui font family is defined", () => {
      expect(Array.isArray(fontFamily.ui)).toBe(true);
      expect(fontFamily.ui).toContain("Inter");
    });

    it("mono font family is defined", () => {
      expect(Array.isArray(fontFamily.mono)).toBe(true);
      expect(fontFamily.mono).toContain("JetBrains Mono");
    });
  });

  describe("fontSize", () => {
    const fontSize = config.theme?.extend?.fontSize ?? {};

    it("label font size is defined", () => {
      expect(fontSize.label).toBeDefined();
    });

    it("hint font size is defined", () => {
      expect(fontSize.hint).toBeDefined();
    });

    it("btn-sm font size is defined", () => {
      expect(fontSize["btn-sm"]).toBeDefined();
    });

    it("body font size is defined", () => {
      expect(fontSize.body).toBeDefined();
    });

    it("heading font size is defined", () => {
      expect(fontSize.heading).toBeDefined();
    });
  });
});

// Tailwind v3.4 configuration. Pinned to v3.x — v4 has a different API
// (CSS-first config, `@import "tailwindcss"` instead of `@tailwind`
// directives) and shadcn/ui generators still target v3 as of M0.
//
// `content` globs are deliberately tight (index.html + src/**) so the
// JIT engine doesn't scan node_modules. The pinning test parses this
// array and asserts it CONTAINS the canonical ./src/**/*.{ts,tsx}
// scan (rather than equals a fixed literal), so shadcn/ui init or
// other tools may freely *add* additional entries (e.g.
// ./components/**/*.{ts,tsx}) without breaking the test.
// See `tests/unit/test_tailwind_config.py`.
//
// ESM (`export default`) to match the rest of `frontend/` (vite.config.ts,
// vitest.config.ts) and `"type": "module"` in package.json.
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: {
          page: "var(--bg-page)",
          surface: "var(--bg-surface)",
          raised: "var(--bg-raised)",
          sunk: "var(--bg-sunk)",
        },
        border: {
          1: "var(--border-1)",
          2: "var(--border-2)",
          3: "var(--border-3)",
        },
        ink: {
          1: "var(--ink-1)",
          2: "var(--ink-2)",
          3: "var(--ink-3)",
          4: "var(--ink-4)",
        },
        accent: {
          DEFAULT: "var(--accent)",
          ink: "var(--accent-ink)",
        },
        status: {
          exact: "var(--status-exact)",
          fuzzy: "var(--status-fuzzy)",
          mismatch: "var(--status-mismatch)",
          ocr: "var(--status-ocr)",
          gt: "var(--status-gt)",
        },
        layer: {
          block: "var(--layer-block)",
          para: "var(--layer-para)",
          line: "var(--layer-line)",
          word: "var(--layer-word)",
        },
      },
      fontFamily: {
        ui: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      fontSize: {
        label: ["9.5px", { lineHeight: "1.1" }],
        hint: ["10px", { lineHeight: "1.2" }],
        "btn-sm": ["11px", { lineHeight: "1.2" }],
        body: ["12px", { lineHeight: "1.4" }],
        heading: ["13px", { lineHeight: "1.3" }],
      },
    },
  },
  plugins: [],
};

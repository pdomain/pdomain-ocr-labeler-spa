// vitest.browser.config.ts — real-browser (Playwright/Chromium) test project.
//
// Separate from vitest.config.ts (jsdom) so `pnpm test` stays exactly what
// it always was — fast, no browser binary required — while a small number
// of layout-dependent regressions get a runner that actually computes CSS.
//
// jsdom never runs layout (no getBoundingClientRect, no real transform
// composition), so a bug like "two CSS transforms stack and push a dialog
// off-screen" (2026-09-18, see src/test/dialogPositioning.ts) is invisible
// to the jsdom suite no matter how the assertion is written — jsdom simply
// has no layout engine to check. `expectNoDuplicateDialogPositioning` is a
// cheap static proxy for that one specific reintroduction of the bug (an
// exact class list); this project adds the real guard: render the
// component in an actual browser and check the actual box.
//
// Run with `pnpm run test:browser`. Requires Chromium
// (`pnpm exec playwright install chromium` — already satisfied in CI/dev
// images that also run the Python E2E suite via tests/e2e/).
import path from "path";

import { defineConfig } from "vitest/config";
import { playwright } from "@vitest/browser-playwright";

export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
      "react/jsx-runtime": path.resolve(__dirname, "./node_modules/react/jsx-runtime.js"),
      react: path.resolve(__dirname, "./node_modules/react"),
      "react-dom": path.resolve(__dirname, "./node_modules/react-dom"),
      "react-konva": path.resolve(__dirname, "./node_modules/react-konva"),
    },
    dedupe: ["react", "react-dom", "react-konva"],
  },
  test: {
    server: {
      deps: {
        inline: [/@pdomain\/pdomain-ui/, /@radix-ui\//],
      },
    },
    globals: true,
    setupFiles: ["./src/test/browserSetup.ts"],
    // Real CSS, unlike vitest.config.ts's `css: false` — a layout assertion
    // is meaningless without Tailwind/pdomain-ui's actual styles applied.
    css: true,
    // Deliberately its own glob, disjoint from vitest.config.ts's
    // `src/**/*.{test,spec}.{ts,tsx}` — these tests need a real browser and
    // must never be picked up by the jsdom project (or vice versa).
    include: ["src/**/*.browser.test.tsx"],
    browser: {
      enabled: true,
      provider: playwright(),
      headless: true,
      // Fixed 1280x720 matches the dimensions the 2026-09-18 off-screen-dialog
      // incident was measured at (dialog top -216px, close-button top -202px)
      // — see src/test/dialogPositioning.ts. Vitest's default browser-mode
      // viewport is smaller and unrelated to the reported incident size.
      viewport: { width: 1280, height: 720 },
      instances: [{ browser: "chromium" }],
    },
  },
  esbuild: {
    jsx: "automatic",
  },
});

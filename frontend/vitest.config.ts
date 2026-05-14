// Vitest config kept separate from vite.config.ts — vitest 2.x bundles its
// own Vite which collides with the project's Vite 6 typings if we put a
// `test` block on the shared config. Runtime behaviour is identical to
// inlining; this just keeps tsc -b happy.
//
// We intentionally do NOT load `@vitejs/plugin-react` here: the plugin is
// typed against the project's Vite 6 and re-introduces the type-collision
// we're avoiding. Vitest's esbuild transform handles `.tsx` JSX out of the
// box, which is sufficient for unit + Testing-Library tests.
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    // Type-check tests against the test-only tsconfig (B-08): production
    // build (`tsc -b` via tsconfig.app.json) excludes test files so test
    // typings + vitest globals stay out of the prod surface.
    typecheck: {
      tsconfig: "./tsconfig.test.json",
    },
    // Coverage: ≥80% overall; 100% on lib/* (pure utility functions).
    // Run with `npm run test:coverage` or `vitest run --coverage`.
    coverage: {
      provider: "v8",
      reporter: ["text", "json", "html"],
      include: ["src/**/*.{ts,tsx}"],
      exclude: [
        "src/**/*.test.{ts,tsx}",
        "src/**/*.spec.{ts,tsx}",
        "src/test/**",
        "src/main.tsx",
        "src/vite-env.d.ts",
        // Auto-generated from OpenAPI — not subject to coverage thresholds.
        "src/api/types.ts",
      ],
      thresholds: {
        global: {
          lines: 80,
          functions: 80,
          branches: 80,
          statements: 80,
        },
        "src/lib/": {
          lines: 100,
          functions: 100,
          branches: 100,
          statements: 100,
        },
      },
    },
  },
  esbuild: {
    // React 19's automatic JSX runtime — no `import React` needed in tests.
    jsx: "automatic",
  },
});

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
  },
  esbuild: {
    // React 19's automatic JSX runtime — no `import React` needed in tests.
    jsx: "automatic",
  },
});

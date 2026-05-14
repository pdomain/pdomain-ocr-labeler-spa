import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// FastAPI proxies /api/* and /image-cache/* during `npm run dev`. The dev
// server runs on :5173; the user starts FastAPI separately with
// `pd-ocr-labeler-ui --frontend-dev http://localhost:5173`.
//
// Backend port matches `Settings.port` default (8080) — see
// `src/pd_ocr_labeler_spa/settings.py` and `docs/architecture/02-backend.md §3`.
// Keep these literals in sync; `tests/unit/test_vite_config.py`
// asserts the proxy targets parse-equal to :8080.
//
// Vitest configuration lives in `vitest.config.ts` (sibling) rather than
// inline here — vitest 2.x bundles its own Vite which conflicts with the
// project's Vite 6 type-wise. Runtime is fine, but tsc -b chokes; a
// separate file sidesteps the type collision cleanly.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8080",
      "/image-cache": "http://localhost:8080",
      "/env.js": "http://localhost:8080",
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    sourcemap: true,
  },
});

import fs from "fs";

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// FastAPI proxies /api/* and /image-cache/* during `npm run dev`. The dev
// server runs on :5173; the user starts FastAPI separately with
// `pd-ocr-labeler-ui --frontend-dev http://localhost:5173`.
//
// Backend port is read from `.pdlabeler-port` (written by the server on every
// start, issue #323). Falls back to 8080 if the file is absent so a first
// `npm run dev` before the server has started still works.
//
// See `docs/architecture/02-backend.md §3` for Settings.port precedence and
// `docs/architecture/15-deployment-dev.md §3` for the port-file contract.
//
// Vitest configuration lives in `vitest.config.ts` (sibling) rather than
// inline here — vitest 2.x bundles its own Vite which conflicts with the
// project's Vite 6 type-wise. Runtime is fine, but tsc -b chokes; a
// separate file sidesteps the type collision cleanly.

function readBackendPort(): number {
  try {
    return parseInt(fs.readFileSync(".pdlabeler-port", "utf8").trim(), 10) || 8080;
  } catch {
    return 8080;
  }
}

const backendPort = readBackendPort();

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": `http://localhost:${backendPort}`,
      "/image-cache": `http://localhost:${backendPort}`,
      "/env.js": `http://localhost:${backendPort}`,
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    sourcemap: true,
  },
});

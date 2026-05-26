import fs from "fs";
import path from "path";

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
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
      // pd-ui 0.2.1 was published with a dev-mode JSX transform: its dist files
      // import `jsxDEV` from "react/jsx-dev-runtime". In production, React's
      // jsx-dev-runtime exports `jsxDEV = undefined`, so any pd-ui component call
      // throws "TypeError: jsxDEV is not a function", preventing React from
      // mounting into #root.
      //
      // The fix: alias "react/jsx-dev-runtime" to a local shim that re-exports
      // `jsxDEV` as the production `jsx` function. Aliasing directly to
      // "react/jsx-runtime" would not work because jsx-runtime doesn't export
      // `jsxDEV`, leaving `f.jsxDEV` as undefined in inlined call sites.
      //
      // Remove this alias (and the shim file) once pd-ui is rebuilt with a
      // production JSX transform.
      // Tracked: pd-ui issue (cross-repo recommendation filed 2026-05-26).
      "react/jsx-dev-runtime": path.resolve(__dirname, "./src/jsx-dev-runtime-shim.ts"),
    },
    // Force single instances of all React-ecosystem packages when pnpm symlink
    // scoping creates multiple paths for the same package.
    //
    // react/react-dom: @concavetrillion/pd-ui resolves from its own pnpm scope
    //   (node_modules/.pnpm/@concavetrillion+pd-ui@.../node_modules/react).
    //
    // react-konva: pd-ui declares peerDeps: "react-konva": "^18.0.0" and brings
    //   in react-konva@18.2.16 via its pnpm scope, while the labeler-spa uses
    //   react-konva@19.2.4. Both get bundled; each creates its own
    //   react-reconciler with conflicting internal state, causing the runtime
    //   error "Cannot read properties of undefined (reading 'ReactCurrentBatchConfig')".
    //   Forcing dedupe resolves both to the top-level react-konva@19.2.4.
    dedupe: ["react", "react-dom", "react-konva"],
  },
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

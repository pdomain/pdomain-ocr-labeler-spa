// Shim: redirect jsxDEV calls from pd-ui's dev-mode build to production jsx.
// pd-ui 0.2.1 was built with dev-mode JSX transform. In production,
// react/jsx-dev-runtime exports jsxDEV=undefined which crashes at runtime.
// This shim re-exports jsxDEV as the production jsx function.
// Remove once pd-ui is rebuilt with production JSX (tracked: pd-ui cross-repo issue 2026-05-26).
export { Fragment, jsx as jsxDEV, jsx, jsxs } from "react/jsx-runtime";

import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/700.css";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/500.css";

import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";

// Tailwind v3.4 base/components/utilities are injected via `./index.css`
// (PostCSS pipeline configured in `postcss.config.js`). shadcn/ui
// generators run on top of this in a later milestone.

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

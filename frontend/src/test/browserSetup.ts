// browserSetup.ts — setup for the real-browser (vitest.browser.config.ts)
// project only. Deliberately NOT src/test/setup.ts: that file wires up
// msw/node (Node's `http` interception, unusable inside a real browser
// page) and jsdom-only polyfills (ResizeObserver, matchMedia, EventSource)
// a real browser already provides natively. Browser-project test files are
// expected to need no network mocking — if one does, it should use MSW's
// browser worker (`msw/browser`) directly, not this file.
import "@testing-library/jest-dom/vitest";

// The app's real Tailwind/pdomain-ui stylesheet — main.tsx's entry point.
// A real-browser layout assertion (getBoundingClientRect) is meaningless
// without it: unstyled content lays out at its raw content size, not the
// fixed/centered/sized box the dialog positioning rules produce.
import "../index.css";

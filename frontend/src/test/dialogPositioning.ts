// dialogPositioning.ts — shared regression guard for dialog centering.
//
// Root cause (2026-09-18): pdomain-ui's shared ".dialog" class (primitives.css)
// already supplies `position: fixed; top: 50%; left: 50%;
// transform: translate(-50%, -50%);` for centering every DialogContent /
// AlertDialogContent. When an app-level dialog ALSO adds Tailwind's
// `fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2` utility classes,
// Tailwind emits the translate as the CSS `translate` longhand property
// (distinct from, and composed *in addition to*, the legacy `transform`
// shorthand `.dialog` sets — see CSS Transforms Level 2 §"Individual
// Transform Properties"). The two translations stack: the dialog is
// shifted by -100%/-100% of its own size instead of -50%/-50%, rendering it
// entirely outside the viewport (measured: dialog top -216px, close-button
// top -202px at 1280x720 — see docs/plans / the hotkey-help-dialog fix).
//
// This can't be caught by measuring layout in jsdom (jsdom does not run
// layout), but the redundant classes themselves are a reliable, cheap
// static signal: no app-level dialog should re-declare positioning that
// ".dialog" already owns. Any DialogContent/AlertDialogContent found with
// these classes has reintroduced the double-transform bug.
//
// This is the cheap check, not the only one: it catches exactly this class
// list, so the same off-screen-dialog effect produced a different way (a
// different Tailwind spelling, an inline style, a new CSS rule entirely)
// would slip past it. HotkeyHelpModal.browser.test.tsx is the real guard —
// it renders in an actual Chromium (vitest.browser.config.ts) and asserts
// the computed box is inside the viewport, regardless of what caused a
// regression. Run both; this one is near-free, the other one needs a
// browser (`pnpm run test:browser`).
const OFFENDING_POSITIONING_CLASSES = [
  "fixed",
  "top-1/2",
  "left-1/2",
  "-translate-x-1/2",
  "-translate-y-1/2",
];

/**
 * Assert that a rendered DialogContent / AlertDialogContent element does not
 * duplicate the centering Tailwind classes that pdomain-ui's ".dialog" class
 * already provides via `transform`. Throws a plain `Error` (so it reads as a
 * normal test failure) when a regression is found.
 */
export function expectNoDuplicateDialogPositioning(el: Element): void {
  const classes = new Set(el.className.toString().split(/\s+/).filter(Boolean));
  const offenders = OFFENDING_POSITIONING_CLASSES.filter((cls) => classes.has(cls));
  if (offenders.length > 0) {
    throw new Error(
      `${el.getAttribute("data-testid") ?? el.tagName} re-declares positioning classes ` +
        `already owned by pdomain-ui's ".dialog" class: [${offenders.join(", ")}]. ` +
        "This doubles the centering transform (CSS `translate` longhand + `transform` " +
        "shorthand both apply) and renders the dialog off-screen. Remove these classes " +
        'and let the shared ".dialog" class handle positioning.',
    );
  }
}

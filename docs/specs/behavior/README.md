---
kind: spec
status: active
owner: maintainers
created: 2026-06-01
last_verified: 2026-07-13
---

# Behavior Specs

These specs are the source of truth for behavior-driven E2E coverage in
`pdomain-ocr-labeler-spa`.

## Behavior documents

- [`component-canvas.md`](component-canvas.md)
- [`component-dialogs-actions.md`](component-dialogs-actions.md)
- [`component-drawer-worklist.md`](component-drawer-worklist.md)
- [`component-driver-contract.md`](component-driver-contract.md)
- [`component-glyph-annotations.md`](component-glyph-annotations.md)
- [`component-jobs-notifications.md`](component-jobs-notifications.md)
- [`component-right-panel.md`](component-right-panel.md)
- [`component-studio-shell.md`](component-studio-shell.md)
- Generated build-consumption table: `coverage.md`
- [`flows.md`](flows.md)
- [`screen-project-page.md`](screen-project-page.md)
- [`screen-root.md`](screen-root.md)
- [`unclear-items.md`](unclear-items.md)

- Each behavior gets a stable ID: `B-<UNIT>-NNN`.
- Cross-unit flows use `F-<DESCRIPTIVE-SEGMENTS>-NN`.
- Records are complete only when observable output and backend /
  side-effects are both stated, including a bad-state path.
- Tests cite covered IDs with a `Covers: B-...` docstring line or
  `@behavior("B-...")`.
- `coverage.md` is generated. Run `make behavior-coverage`; do not edit
  it by hand.

## Files

- `screen-root.md` - `/` project browser.
- `screen-project-page.md` - loaded labeling route.
- `component-studio-shell.md` - shell, rail, breadcrumb, quick search.
- `component-drawer-worklist.md` - worklist, hierarchy, bulk actions.
- `component-canvas.md` - page image and bbox interaction.
- `component-right-panel.md` - word, line, block detail panels.
- `component-dialogs-actions.md` - page actions and dialogs.
- `component-glyph-annotations.md` - glyph chips, review panel, bulk glyphs.
- `component-jobs-notifications.md` - job progress, busy overlay, notifications.
- `component-driver-contract.md` - driver compatibility and hidden stubs.
- `flows.md` - cross-unit scenarios.
- `unclear-items.md` - behaviors that need product or implementation decisions.
- `coverage.md` - generated traceability report.

See `/workspaces/ocr-container/docs/process/behavior-e2e-capture.md` for
the capture methodology.

## Adversarial Review

**Accepted finding:** The behavior-ID and coverage workflow is live; generated coverage does not
prove blocked glyph behavior exists.

**Stage:** migration-time current-state review on 2026-07-13.

**Source:** an independent read-only reviewer compared this document with current
code, tests, architecture, and git history.

**Result:** the review accepted the finding above and used it to declare the
metadata status. Residual risks remain explicit here or in
`docs/context/intent-map.md`; deferred or blocked behavior is not claimed as
shipped.

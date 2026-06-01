# Behavior Specs

These specs are the source of truth for behavior-driven E2E coverage in
`pdomain-ocr-labeler-spa`.

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

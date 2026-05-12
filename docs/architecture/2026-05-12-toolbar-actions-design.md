# pd-ocr-labeler-spa: Toolbar Action Grid

> **Status**: Draft
> **Last updated**: 2026-05-12
> **Spec-Issue**: ConcaveTrillion/pd-ocr-labeler-spa#16

## TL;DR

A 14-column × 4-row action grid (page/paragraph/line/word scopes) above the word-matches
tab list. Each cell fires a scoped backend mutation. Disabled-state logic is computed by
a pure `useToolbarButtonStates(selection)` hook against the current backend `Selection`.
Two additional rows: Apply Style and Add Word.

## Context

The legacy `word_match_toolbar.py` generates the toolbar server-side via NiceGUI. The SPA
renders it as a static grid with disabled-state computed from the in-memory `Selection`.
Each button maps to a specific REST endpoint; no legacy-style callback bus.

The toolbar is mounted inside `<TextTabs>` above the tab switcher, so it persists across
the Matches / GT / OCR tab switch.

## Constraints

- **Disabled-state is pure.** `useToolbarButtonStates(selection)` takes the current
  `Selection` and returns a `ButtonStates` record. No side effects, fully testable.
- **`pd-book-tools` owns label vocabularies.** `ALLOWED_TEXT_STYLE_LABELS` and
  `ALLOWED_WORD_COMPONENT_LABELS` are imported from `pd_book_tools`; not hardcoded.
- **`data-testid="toolbar-{scope}-{action}"`** on every cell (even absent ones, with
  `data-testid-stub="true"` to allow driver assertions without crashes).
- **DOM-present stub cells.** Absent cells for a given scope are rendered as disabled
  `<button>` with `data-testid-stub="true"` so the driver grid index is stable.

## Decision

### Grid layout

4 rows × 14 columns. Row labels in column 1 (scope: page/paragraph/line/word). Action
columns: Merge, Refine, Expand+Refine, Expand, SplitAfter, SplitSelected, Word→Line,
→Para, GT→OCR, OCR→GT, Validate, Unvalidate, Delete.

Enabled cells per scope match `specs/06-toolbar-actions.md §1` table exactly.

### Disabled-state rules

All rules from `update_button_state:742` in legacy. Key rules:

- Page row: always enabled.
- Para/Line/Word rows: enabled only when ≥1 of that scope is selected.
- Merge: ≥2 of scope selected.
- Validate: ≥1 selected AND not all already validated.
- Unvalidate: ≥1 selected AND ≥1 already validated.
- Delete: ≥1 selected.

### Apply Style row

Below the grid: style selector (shadcn Select from `ALLOWED_TEXT_STYLE_LABELS`),
scope selector (whole/part), component selector (`ALLOWED_WORD_COMPONENT_LABELS`),
Apply button, Clear button. testids: `apply-style-select`, `apply-scope-select`,
`apply-component-select`, `apply-style-button`, `clear-style-button`.

### Add Word row

Single `Add Word` button toggling viewport into add-word mode. testid: `add-word-button`.
Shows progress spinner while the POST is in-flight.

### Job-progress indicator

A thin progress bar below the grid, visible while any toolbar-triggered job is running.
Disappears on terminal event.

## Contract / Acceptance

- Vitest: `useToolbarButtonStates` — exhaustive unit tests for all disabled-state rules.
- Playwright: page-scope Validate button always enabled; word-scope Validate disabled
  when no words selected.
- Playwright: Apply Style with "italic" scope "whole" → POST `.../apply-style` fires.
- All 56 cells (4 rows × 14 columns) present in DOM; absent cells have
  `data-testid-stub="true"`.

## Trade-offs considered

**Pure hook vs derived Redux/zustand state for disabled flags.** A zustand selector
could derive button states reactively. A plain hook is simpler to test (pure function)
and avoids storing derived state in a store. Chosen: pure hook.

**Absent cells vs no DOM node.** Keeping absent cells as disabled stubs makes the
driver grid index stable. Without stubs, column 5 of the word row means different
things depending on how many cells are present. Stubs chosen.

## Consequences

- Adding a new action column requires updating the grid layout, the `ButtonStates` type,
  `useToolbarButtonStates`, and the driver contract testid table.
- The Apply Style row depends on `pd-book-tools` label lists; a label rename there
  requires a frontend rebuild and potentially a data migration for saved labels.

## Open questions

None.

## References

- `specs/06-toolbar-actions.md` — legacy feature doc (full action table and disabled rules)
- `specs/13-driver-contract.md` — testid naming convention for toolbar cells
- `specs/05-word-matches.md` — toolbar is mounted above TextTabs
- `pd_book_tools.ocr.label_normalization` — `ALLOWED_TEXT_STYLE_LABELS`,
  `ALLOWED_WORD_COMPONENT_LABELS`

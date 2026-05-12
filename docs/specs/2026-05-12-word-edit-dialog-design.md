# pd-ocr-labeler-spa: Word Edit Dialog

> **Status**: Draft
> **Last updated**: 2026-05-12
> **Spec-Issue**: ConcaveTrillion/pd-ocr-labeler-spa#18

## TL;DR

A shadcn `<Dialog>` focused on a single word: 3-column preview header, Konva interactive
image, merge/split/delete/crop/refine rows, nudge accumulator grid, tag chip row,
drag-erase canvas, and word-level hotkeys. Apply & Close commits pending changes;
× discards. Previous/Next navigation stays within the same line.

## Context

The legacy `word_edit_dialog.py` is the most behaviourally complex single component.
The SPA replicates it as a React modal with Konva for the interactive image preview.
The dialog does not auto-close on each action — multiple actions can be staged and
committed together via Apply & Close, matching legacy behaviour.

All mutations go to dedicated endpoints: rebox, nudge, merge, split, delete, crop,
erase-pixels. The nudge and erase-rect accumulate locally; the POST fires on Apply & Close
or on the Apply button within each row.

## Constraints

- **Konva confined to this component.** The interactive image is a `<Stage>` inside
  `WordEditDialog.tsx`; no Konva in other components.
- **Previous/Next stays in the same line.** Wraps at line boundary; does not cross into
  adjacent lines without user navigating back to the match list.
- **Apply & Close commits; × discards.** Pending nudge and erase rects are only POSTed
  on Apply & Close. × discards them locally.
- **Rebox enters viewport mode.** The Rebox button sets
  `useViewportStore.mode = "rebox"` with `pendingReboxTarget`; the dialog stays open
  until the rebox drag completes in the left pane.
- **No auto-close on apply.** Legacy behaviour: user can apply style + nudge + crop in
  one dialog open, then close once.

## Decision

### Header

Title: "Edit Line {n}, Word {m}". Buttons: Apply & Close (✓, testid
`dialog-apply-close-button`), Close (×, testid `dialog-close-button`).

### Preview row (3 columns)

Previous word | Current word (interactive Konva Stage) | Next word. Read-only image for
prev/next; full-interactive for current. Clicking prev/next switches `target` without
closing.

### Interactive Konva image

`<Stage>` showing the current word's image slice at up to 4 zoom levels (1×/2×/5×/10×).
Overlaid: a click-marker dot for selecting the rebox target point, hover guide lines.
In erase mode: staged erase rects drawn as red semi-transparent overlays.

### Action rows

- **Merge/Split/Delete row:** Merge with prev/next word (POST `.../merge`), Split
  (fractional horizontal, POST `.../split`), Delete (POST `.../delete`).
- **Crop row:** Crop-to-bbox (POST `.../crop`) with padding slider.
- **Refine row:** Refine, Expand+Refine, Expand-only (POST `.../refine`), plus nudge
  grid (8-direction pixel-delta accumulator, committed on Apply).
- **Apply/Reset/Apply+Refine buttons** in the refine row.
- **Tag chips row:** style chips (italic, small_caps, etc.) + component chips (footnote,
  drop_cap, etc.) from `pd-book-tools`. Each chip is a toggle; POST
  `.../apply-style` / `.../apply-component` on click.

### Dialog hotkeys (scoped to dialog)

← / → — prev/next word. Shift+← / Shift+→ — nudge left/right. Shift+↑ / Shift+↓ —
nudge up/down. `R` — refine. Delete — delete word. Shift+Enter — Apply & Close.

## Contract / Acceptance

- Playwright: open dialog for word 2/5; click next → dialog now shows word 3/5.
- Playwright: nudge left × 3 → Apply & Close → POST `.../nudge` fires with
  `{left: -3, right: 0, top: 0, bottom: 0}`.
- Playwright: close with × after nudge → no POST fires.
- Vitest: tag chip toggle fires POST with correct style/component key.
- Playwright: Rebox button → viewport enters rebox mode; dialog stays open.

## Trade-offs considered

**Staged nudge vs per-click POST.** Per-click POST would give immediate visual feedback
but hammer the server on fast nudges. Staged accumulator (one POST on Apply) is simpler
and matches legacy behaviour.

**Konva Stage in dialog vs img tag.** A static `<img>` would suffice for preview but
erase-rect drawing requires a canvas with programmatic hit detection. Konva chosen for
consistency with the left pane.

**Auto-close after merge/split/delete vs keep open.** Legacy keeps dialog open after
merge (user may need to inspect the result). Kept open for all structural operations.

## Consequences

- Rebox operation requires coordination between the dialog and the viewport (shared
  `useViewportStore`). A poorly-timed navigation away from the page while rebox is
  pending must clean up the pending target.
- Adding a new action row requires a new endpoint in `api/words.py` and a new row
  component in `WordEditDialog.tsx`.

## Open questions

None.

## References

- `specs/07-word-edit-dialog.md` — legacy feature doc (full row-by-row detail)
- `specs/04-image-viewport.md` — rebox mode coordination
- `specs/12-hotkeys-a11y.md` — dialog-scoped hotkey table
- `specs/02-backend.md §5.4` — word-level endpoint list

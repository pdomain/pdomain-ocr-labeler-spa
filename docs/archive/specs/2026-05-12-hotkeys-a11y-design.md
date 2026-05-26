# pdomain-ocr-labeler-spa: Hotkeys + Accessibility

> **Status**: Draft
> **Last updated**: 2026-05-12
> **Spec-Issue**: ConcaveTrillion/pdomain-ocr-labeler-spa#28

## TL;DR

Six hotkey scopes (global, viewport, matches, dialog, source-folder, gt-input) implemented via
`react-hotkeys-hook`. Static keymap in `src/lib/hotkeyMap.ts`; `?` opens a help modal that
reads from it. WCAG AA contrast; icon+shape color differentiation; full keyboard-only
operation path; `axe-core` E2E audit on every key page.

## Context

The legacy has only 5 hotkeys. The SPA adopts the gap-analysis wishlist as v1 keymap,
preserving all legacy keys. `react-hotkeys-hook` provides scope-aware binding; `Mod+...`
syntax covers Ctrl/Cmd platform differences. Destructive actions (Load Page, Reload OCR,
Rematch GT) require shadcn `<AlertDialog />` confirmation before firing. The hotkey help
modal is driven by the same static `hotkeyMap.ts` data, so it's always in sync.

## Constraints

- **`enableOnFormTags: false` by default.** Shortcuts must not fire while typing. Per-input
  opt-in required (GT input Tab uses `enableOnFormTags: ['INPUT']`).
- **`?` suppressed inside inputs.** Opening help inside a GT input would insert a character.
- **`Mod+S` preempts browser Save As.** `e.preventDefault()` required; may not work in all
  Safari versions (acceptable known limitation).
- **Viewport drag operations require a mouse.** Document this: all viewport selections are also
  reachable via toolbar + keyboard; drag is a power-user shortcut.
- **Custom key rebinding out of scope for v1.** Keymap is static.
- **WCAG AA contrast required.** 4.5:1 for body text; 3:1 for large/UI text.
- **axe-core in E2E on every key page.** Automated a11y gate, not a manual-only check.

## Decision

### Keymap structure

`src/lib/hotkeyMap.ts` exports `HotkeyEntry[]` with `{combo, scope, description}`. Single
source of truth for both registration and the `?` help modal. Scopes: `global | viewport |
matches | dialog | source-folder | gt-input`.

`src/hooks/useHotkey.ts` wraps `react-hotkeys-hook` with defaults: `preventDefault: true`,
`enableOnFormTags: false`. Per-call overrides allowed.

### Key scopes (summary)

**Global:** `Mod+S` (Save Page), `Mod+Shift+S` (Save Project), `Mod+R` (Reload OCR),
`Mod+Shift+R` (Reload OCR Edited), `Mod+L` (Load Page), `Mod+G` (Rematch GT), `Mod+E`
(Export), `Mod+,` (OCR Config), `Mod+O` (Source Folder), `?` (Help), `Esc` (Close modal).
Navigation: `Mod+ArrowLeft/Right` (prev/next page), `Mod+Home/End` (first/last page),
`Mod+J` (Jump to page).

**Viewport:** `Esc` (cancel mode), `Shift+P/L/W` (toggle layers), `Shift+1/2/3` (selection
mode), `Shift+E` (erase), `Shift+A` (add word). Mouse+key drag modifiers: plain drag =
replace selection, `Shift+drag` = remove, `Ctrl+drag` = toggle (XOR).

**Matches:** `Tab`/`Shift+Tab` (GT input nav), `Enter` (commit GT), `Esc` (revert GT),
`J`/`K` (prev/next line card), `V`/`U` (validate/unvalidate), `D` (delete with confirm),
`R`/`Shift+R` (refine/expand+refine), `M` (merge), `O`/`G` (OCR→GT / GT→OCR).

**Word edit dialog:** `Enter` (commit GT), `Esc` (close), `Shift+Enter` (apply+close),
`ArrowLeft/Right` (prev/next word), `Shift+Arrow` (nudge edges), `R`/`Shift+R` (refine),
`M`/`Shift+M` (apply style/component), `Delete` (delete word with confirm).

**Source-folder dialog:** `Enter` (on path input — open typed path), `Esc` (cancel).

**GT input:** `Tab`/`Shift+Tab` (next/prev input), `Enter` (commit), `Esc` (revert).
`enableOnFormTags: ["INPUT"]` required so these fire inside the form element.

### Hotkey help modal

`?` opens shadcn `<Dialog />`, scrollable list keyed by scope. Reads directly from
`hotkeyMap.ts`. testid: `hotkey-help-dialog`.

### Accessibility contract

- Every interactive element focusable via Tab; visual focus order matches DOM order.
- Radix modals: focus trap + return focus to trigger on close.
- Icon-only buttons: `aria-label` required.
- Form controls: associated `<label>` (visible or `srOnly`) or `aria-label`.
- Matches view: `role="region" aria-label="Word matches"`.
- Viewport `<Stage>`: `role="img" aria-label="Page image with bounding-box overlays"`.
- Status icons: `aria-label` (e.g. "exact match", "fuzzy match").
- `role="status" aria-live="polite"` slot in `App.tsx` for bulk-action narration.
- `role="alert" aria-live="assertive"` slot reserved for errors (used sparingly).
- Status colors differentiated by icon shape + text (colorblind accessible).

## Contract / Acceptance

- `Mod+S` fires Save Page; browser Save As is preempted via `e.preventDefault()`.
- `?` outside a form input opens hotkey help modal; inside a GT input it inserts `?`.
- Destructive actions (Load Page, Reload OCR, Rematch GT) show `<AlertDialog />` before
  executing.
- Viewport layer toggles respond to `Shift+P/L/W` when canvas is focused.
- Tab navigates GT inputs in reading order; `Enter` commits; `Esc` reverts.
- axe-core finds zero WCAG AA violations on root page, project page, and matches view.
- `hotkeyMap.ts` is the single source of truth: help modal always reflects registered keys.

## Trade-offs considered

**`useHotkeys` vs custom keydown handler.** Custom handler is simpler but lacks scope
management, conflict detection, and Mod-key normalization. `react-hotkeys-hook` handles all
three. Chosen: `react-hotkeys-hook`.

**Confirm dialogs for destructive keys vs no confirm.** `Mod+L` (Load Page) discards in-
memory edits. Without confirmation a mispress destroys work. Confirms chosen for all
destructive actions (OCR reload, Load Page, Rematch GT, Delete). Save Page is not destructive,
no confirm needed.

**Static keymap vs rebindable.** Rebinding adds a user-prefs store, conflict-detection UI, and
persistence. Static in v1; rebinding deferred.

**axe-core automated vs manual-only a11y.** Manual tests find issues humans notice; automated
catches regressions. Both are needed. axe-core in E2E gates the PR; manual with NVDA/VoiceOver/
Orca before each release.

## Consequences

- `hotkeyMap.ts` must be updated whenever a new shortcut is added. Forgetting breaks the help
  modal.
- `enableOnFormTags: false` default means any new form control inside a hotkey scope must
  explicitly opt-in if it needs shortcuts (e.g., GT input Tab).
- `Mod+S` preemption may silently fail in Safari; add a Safari-specific note to the help
  modal.

## Open questions

None.

## References

- `specs/12-hotkeys-a11y.md` — legacy feature doc (full keymap tables + a11y contract)
- `specs/05-word-matches.md §7` — matches-view hotkeys
- `specs/07-word-edit-dialog.md §5` — dialog hotkeys
- `specs/04-image-viewport.md §3` — viewport hotkeys + drag modifiers
- `src/lib/hotkeyMap.ts` — static keymap source of truth
- `src/hooks/useHotkey.ts` — `react-hotkeys-hook` wrapper

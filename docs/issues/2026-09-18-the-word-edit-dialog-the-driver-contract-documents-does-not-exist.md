---
status: active
owner: maintainers
created: 2026-09-18
last_verified: 2026-09-18
kind: issue
level: I2
---

# Word-level merge has no home in the product

## Agent Index

- **Kind:** issue
- **Status:** active
- **Level:** I2
- **Last verified:** 2026-09-18
- **Resolution:** Open
- **Severity:** Low as a defect, but the capability is genuinely missing —
  the toolbar button for it is a permanent, disabled stub.
- **Affected version:** master at `fc2be39`
- **Read when:** implementing word-level merge, or wondering why
  `toolbar-word-merge` never becomes clickable.
- **Search terms:** word merge, toolbar-word-merge, WORD_MAP, ToolbarActionGrid,
  driver contract §2.9.

## What's left after the word-edit dialog cleanup

This issue originally covered three problems: a driver-contract section
(§2.11) documenting a word-edit dialog that no longer existed in the code, a
pencil button on each word cell that called a handler nothing supplied, and
word-level merge, which the driver contract tied to that dialog. The first
two are fixed: §2.11 is retired from `docs/architecture/13-driver-contract.md`,
and `WordCell`'s pencil now selects the word and opens the right panel
(`ProjectPage.tsx`'s `handleEditWord`), matching `WordCell`'s own docstring.
No dialog was rebuilt — `WordDetail` in the right panel already covers bbox,
rebox, the char fixer, erase pixels, and the style/component palettes.

Word-level merge is what remains. It didn't move to the right panel along
with everything else the dialog used to do, and it has nowhere to go.

## The toolbar button is a permanent stub

`ToolbarActionGrid`'s 4×14 grid always renders a `toolbar-word-merge` cell
(driver-contract §2.9), but the grid's action map has no `merge` entry for
the `word` scope:

```ts
// frontend/src/components/ToolbarActionGrid.tsx — WORD_MAP
const WORD_MAP: Partial<Record<Action, string>> = {
  refine: "word_refine",
  "expand-refine": "word_expand_refine",
  expand: "word_expand",
  "w-to-l": "word_w_to_l",
  "to-para": "word_to_para",
  "gt-to-ocr": "word_gt_to_ocr",
  "ocr-to-gt": "word_ocr_to_gt",
  validate: "word_validate",
  unvalidate: "word_unvalidate",
  delete: "word_delete",
  // no "merge" key
};
```

Cells without a map entry render `display: none` with `data-testid-stub="true"`
(driver-contract §2.9's convention for "not implemented" vs. "not present").
`toolbar-word-merge` is permanently in that state — not disabled pending a
selection, but structurally incapable of doing anything, because there is no
mutation for it to dispatch.

For comparison, line-level merge works: `toolbar-line-merge` has a live
`LINE_MAP` entry and a backend endpoint. Word-level merge has neither.

## What to decide

Merging two words is a real editing operation — the driver contract's §2.9
description of `toolbar-word-merge` implies it should exist, and it did (via
the dialog) before the migration to the right panel. Someone needs to decide:

1. **Where does word merge live?** Candidates: a `WordDetail` action in the
   right panel (matching how bbox/rebox/erase moved there), a wired
   `toolbar-word-merge` cell (matching how line merge already works), or a
   hotkey-only flow. Whichever surface, it needs a backend endpoint — none
   exists for word-level merge today (only line-level).
2. **What does "merge" mean for two words?** Concatenate OCR/GT text with or
   without a space, union their bboxes, keep the earlier word's `word_id` —
   these choices need a decision before implementation, not during it.

## What is NOT broken

Every other word-editing capability works from the right panel: bbox editing,
rebox, the char fixer, erase pixels, style/component tagging, validation, and
GT commit. This issue is scoped to the one capability — word merge — that the
dialog-to-panel migration dropped.

## Resolution

_Open._ The word-edit dialog and pencil-button parts of this issue are fixed
(see `docs/architecture/13-driver-contract.md` §2.11 and §2.9, and
`ProjectPage.tsx`'s `handleEditWord`). Word-level merge itself is unresolved
pending the decision above. When it lands: wire a `merge` entry into
`WORD_MAP` (or its right-panel equivalent) and the corresponding backend
endpoint, set frontmatter + Agent Index `Status: retired`, add the resolving
commit/spec link here, and route the retirement through `doc-retirer`.

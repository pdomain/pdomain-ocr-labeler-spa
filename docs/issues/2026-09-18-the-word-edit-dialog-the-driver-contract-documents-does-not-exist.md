---
status: active
owner: maintainers
created: 2026-09-18
last_verified: 2026-09-18
kind: issue
level: I2
---

# The word edit dialog the driver contract documents does not exist

## Agent Index

- **Kind:** issue
- **Status:** active
- **Level:** I2
- **Last verified:** 2026-09-18
- **Resolution:** Open
- **Severity:** Low as a defect, medium as a contract lie. Nothing is lost; a
  button does nothing and a documented surface is absent.
- **Affected version:** master at `fc2be39`
- **Read when:** implementing word-level merge, editing the driver contract's
  word-edit section, or wondering why the pencil on a word cell does nothing.
- **Search terms:** word-edit-dialog, WordCell pencil, onEditWord, driver
  contract 2.11, word merge, toolbar-word-merge.

## The dialog is gone from the code and still in the contract

`data-testid="word-edit-dialog"` and its whole family appear nowhere in
`frontend/src` outside test files. `dialogStore` has no `wordEdit` key; its keys
are `ocrConfig`, `export`, `hotkeyHelp`, `sourceFolder`, `pageKinds` and
`confirm`. The driver contract still documents the dialog in §2.11, and
`tests/e2e/test_driver_contract.py::test_word_edit_dialog_testids_present`
fails against it.

That test was skipping until 2026-09-18. The tiny fixture's pages were
one-pixel placeholders, so every test needing word content skipped in every
environment. Seeding real words turned the skip into this failure. See the
2026-09-18 tombstone in `docs/context/decisions.md`.

## The pencil on a word cell does nothing

`WordCell` renders a pencil button that calls `onEditWord`. `ProjectPage`
mounts `WordMatchView` without passing `onEditWord`, so the click is a no-op.
It also passes no `onCommitGt`, `onValidate`, `onClearWordTag` or
`imageBaseUrl`.

## This looks deliberate, except for word merge

The right panel's `WordDetail` accordion now covers what the dialog did:
bbox, rebox, char fixer, erase pixels, and the style and component palettes.
The absence of the dialog is total and consistent, which reads as a finished
migration from a modal to the inline panel rather than a regression.

One capability did not move. The driver contract's §2.9 ties word-level merge
to the dialog, `ToolbarActionGrid`'s word map has no merge entry, so
`toolbar-word-merge` is a permanent stub, and no part of the right panel offers
word merge. Merging two words is a real editing operation with nowhere to go.

## The help modal advertises eighteen dead shortcuts for it

`hotkeyMap.ts` has eighteen entries under `scope: "dialog"` — enter, escape,
shift+enter, the arrow navigation, four nudge pairs, `r`, `shift+r`, `m`,
`shift+m` and delete. `WordDetail` has no keyboard handling at all, so none of
them do anything, and the help modal lists every one. Found 2026-09-18 while
registering the hotkeys that the react-hotkeys-hook 5 bump had broken.

Removing them is not a two-line change: it touches the `Scope` union,
`hotkeyMap.test.ts`'s valid-scope list and `hotkey-bridge.ts`'s scope-to-group
switch. It also presumes the answer to the first decision below, so it waits on
that.

## What to decide

1. **Retire §2.11** of the driver contract, and delete or rewrite
   `test_word_edit_dialog_testids_present`, since the surface it describes was
   replaced on purpose.
2. **Either wire the pencil to select the word and open the right panel**,
   which is what `WordCell`'s own docstring says it should do, **or remove the
   button**. It should not sit there doing nothing.
3. **Decide where word merge lives.** That is the one capability the migration
   dropped, and it needs a home before §2.9 can be honest.

## What is NOT broken

The right panel's word editing works, and is covered by `test_ui_coverage.py`
against the exercise fixture. Word validation, ground-truth commit and tagging
all work from the panel. This issue is about one dead button, one documented
surface that no longer exists, and one capability with no home.

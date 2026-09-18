---
status: active
owner: maintainers
created: 2026-09-18
last_verified: 2026-09-18
kind: issue
level: I1
---

# The per-word validate button can never validate a word

## Agent Index

- **Kind:** issue
- **Status:** active
- **Level:** I1
- **Last verified:** 2026-09-18
- **Resolution:** Open
- **Severity:** Medium. Nothing is lost, and other paths still validate words,
  but one affordance is unusable in the direction it exists for, and a person
  who unvalidates a word cannot put it back.
- **Affected version:** master at `d3adc53`; introduced by `6a04cbe`
  (2026-08-22, the grapheme review editor)
- **Read when:** touching `WordFooter`, the typography review completion rule,
  or anything that gates an edit on review state.
- **Search terms:** word-footer-validate, reviewComplete, typography_page_review,
  text_reviewed, validate gate, unvalidate.

## The gate contradicts itself

`WordFooter` disables its validate button like this:

```
disabled={toggleValidated.isPending || (!isValidated && !reviewComplete)}
```

`reviewComplete` comes from `typography_page_review`, which is complete when
`text_reviewed == total`, `typography_reviewed == total` and nothing is
blocked. For an ordinary project, `text_reviewed` only counts words that
already carry the `validated` label.

So the page's review can only complete once every word is already validated,
and the button that validates a word is disabled until the page's review is
complete. For the first unvalidated word on any page there is no sequence of
clicks that works.

## It also blocks putting back what you just removed

Once a page is fully validated and reviewed, `reviewComplete` is true, so the
button is enabled. A person uses it to unvalidate one word, which is allowed,
because `isValidated` was true. That word's label drops, `text_reviewed` falls
below `total`, `reviewComplete` flips to false, and the button they just used is
disabled. They cannot re-validate that word from there.

In practice the button only ever works as a one-shot unvalidate, and never as a
way to validate.

## Words get validated by other paths, which is why nobody noticed

The toolbar's page-scope `validate-batch` and `LineDetail`'s bulk validate do
not check `reviewComplete`. Every validated word in the product today got there
through one of those.

This was found on 2026-09-18 while making
`test_selection_operations_parity.py::test_grid3_stb1_per_word_validate_mutates_state_end_to_end`
honest. That test had been clicking the button on an unreviewed word and
failing; driving the review to completion first made it pass, and exposed that
the click now only ever exercises the unvalidate direction.

## What to decide

The gate reads like the review-completion rule and the existing per-word
validate affordance were never reconciled. Someone needs to say which rule was
meant:

1. **Drop the gate**, restoring per-word validate as it worked before
   `6a04cbe`, and let review completion be a consequence of validating rather
   than a precondition.
2. **Gate on that word's own typography review** instead of the whole page's,
   which is the reading that makes the original intent coherent: do not validate
   a word whose graphemes nobody has looked at.
3. **Keep the page gate and remove the button**, if the intent is that words are
   only ever validated in bulk. Then the toolbar and bulk paths need to say so.

Option 2 is my recommendation. It preserves what the gate seems to be for
without the circularity, and it leaves both directions of the button usable.

## What is NOT broken

Bulk validation works. Typography review works. The completion rule itself is
consistent; it is the per-word button's precondition that cannot be satisfied.
Unvalidating a word works, once.

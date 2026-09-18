---
kind: architecture
status: built
owner: maintainers
created: 2026-05-06
last_verified: 2026-09-18
---

# 18 — Text Normalization (Long-S, Ligatures, Glyph Variants)

> **Status**: Not offered — removed 2026-09-18 (P2-NORMALIZE-DEAD)
> **Spec-Issue**: pdomain/pdomain-ocr-labeler-spa#40

## Not offered

This capability does not exist and is not planned. The SPA does no text
normalization anywhere: OCR text, GT text, and the plaintext OCR/GT tabs are
all stored and rendered exactly as recognized.

`core/text_normalize.py`, `GET /api/normalize/available`, and the OCR
config modal's "Text normalization" section were removed (P2-NORMALIZE-DEAD,
removed 2026-09-18; see the tombstone in
[`../context/decisions.md`](../context/decisions.md)). They existed only to
probe for `pdomain_book_tools.text.normalize`, a module that has never
existed in any version of `pdomain-book-tools`. The probe was permanently
false, so the UI stayed hidden and the plaintext-rendering call was always a
no-op — removing it changed nothing observable.

A real normalizer does exist —
`apply_text_normalizations`/`normalize_curly_quotes`/`normalize_em_dash` in
`pdomain_book_contracts.text.text_normalize` — but it normalizes curly quotes
and em dashes, not the long s and ligatures this document originally
described. This product transcribes historical text to ground truth, so
silently rewriting punctuation in OCR output is the wrong default; nobody has
proposed wiring that normalizer in here.

## 1. Principle (still true, by default rather than by design)

**OCR fidelity wins.** When DocTR (or any other engine) produces `ſhall` for
an old-typesetting page, that's what is stored and displayed. Nothing
modifies the OCR result, the GT text, or the plaintext tabs.

**GT input is still validated**, independent of this removed capability: the
GT-update endpoint (`api/words.py`) rejects long-s (U+017F) and the U+FB00–
U+FB06 ligature block with `400 validation_error`, so ground truth stays
ASCII. That check is a codepoint denylist, not a normalizer — it does not
transform text, it refuses specific input. See
`tests/integration/test_text_norm_config.py` (acceptance A1).

## 2. What still exists, inert

Three `AppConfig` fields persist in `config.yaml` from the original design
but are not read by any code path today: `normalize_for_gt_matching`,
`normalize_plaintext_tabs`, `normalize_profile` (all default off/`"ascii"`).
No UI sets them (the OCR config modal's normalize section is gone) and no
handler consults them. `WordMatch.normalized_match: bool = False` is the
same story — the field exists, nothing ever sets it `True`, and nothing
renders it. These were flagged as a distinct, out-of-scope finding when
P2-NORMALIZE-DEAD was resolved; removing them is a separate decision nobody
has made yet.

## 3. History

Before removal, this document specified a long-s/ligature-to-ASCII glyph map
(`ſ`→`s`, `ﬁ`→`fi`, `ﬂ`→`fl`, `ﬃ`→`ffi`, `ﬄ`→`ffl`, `ﬅ`/`ﬆ`→`st`,
`Œ`/`œ`→`OE`/`oe`, `Æ`/`æ`→`AE`/`ae`), a normalization-aware fuzz-match mode,
an output-time "render normalized in plaintext tabs" toggle, and an OCR
config modal section with `normalize-gt-matching-checkbox`,
`normalize-plaintext-checkbox`, and `normalize-profile-select` testids. None
of it shipped past the toggle UI and the permanently-false availability
probe: the `pdomain_book_tools.text.normalize` module the whole design
depended on was never built. The full pre-removal text is available in git
history at this file's path as of commit `c68661d` and earlier.

The spec this document originally cited as its authority,
`docs/specs/2026-05-12-text-normalization-design.md`, was never added to the
tree.

## 4. If this capability is wanted again

Two independent decisions would need to be made and recorded before writing
code:

1. **Which normalization.** The long-s/ligature map above was never built
   anywhere. The normalizer that does exist upstream
   (`pdomain_book_contracts.text.text_normalize.apply_text_normalizations`)
   does curly quotes and em dashes instead — a different transform serving a
   different goal (this product's ground-truth fidelity vs. that library's
   text cleanup). Decide which transform, if either, this product wants
   before wiring anything.
2. **Where it runs.** If it changes plaintext OCR/GT tab rendering, GT-match
   comparison, or DocTR export output, each is a separate call site with its
   own product tradeoff (see §1 above — OCR fidelity is the current default
   everywhere).

Cross-refs: ADR — [`17-decisions.md`](../../specs/17-decisions.md) D-025.

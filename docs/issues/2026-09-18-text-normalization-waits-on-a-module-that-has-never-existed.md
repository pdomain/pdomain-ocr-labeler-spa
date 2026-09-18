---
status: active
owner: maintainers
created: 2026-09-18
last_verified: 2026-09-18
kind: issue
level: I2
---

# Text normalization waits on a module that has never existed

## Agent Index

- **Kind:** issue
- **Status:** active
- **Level:** I2
- **Last verified:** 2026-09-18
- **Resolution:** Open
- **Severity:** Low. Nothing breaks, and the UI correctly hides itself, but the
  app reports a capability as pending an upgrade that will never arrive.
- **Affected version:** master at `c68661d`
- **Read when:** touching `core/text_normalize.py`, `/api/normalize`, or the
  page text normalization call in `api/pages.py`.
- **Search terms:** normalize_string, text_normalize, api/normalize/available,
  apply_text_normalizations, issue 260, issue 261.

## The import target does not exist, and never did

`core/text_normalize.py` probes for `pdomain_book_tools.text.normalize` and
falls back to a no-op when the import fails, so that callers can show a
"requires pdomain-book-tools ≥ X.Y.Z" message.

That module has never existed in `pdomain-book-tools`, in the installed 0.28.0
wheel or at git HEAD. So `is_available()` is permanently false, and the upgrade
the message promises cannot happen.

`GET /api/normalize/available` exists only to report that probe, and the SPA
gates its normalize UI on it. The normalization call in `api/pages.py` around
line 933 silently passes text through unchanged.

The spec both files cite as their authority,
`docs/specs/2026-05-12-text-normalization-design.md`, is not in the tree.

## A real normalizer exists, and does something else

`pdomain_book_tools.ocr.text_normalize`, re-exported from
`pdomain_book_contracts.text.text_normalize`, offers
`apply_text_normalizations`, `normalize_curly_quotes` and `normalize_em_dash`.

That is not what this repo's comments describe. They say long s and ligatures,
which nothing upstream implements.

Found 2026-09-18 while removing the export request's dead
`normalize_recognition_labels` flag, which had been threaded to this same
permanently-unavailable helper. See the tombstone for P1-NORMALIZE in
`docs/context/decisions.md`.

## What to decide

1. **Point it at the real normalizer** if curly quotes and em dashes are the
   normalization this product wants. One import changes, the probe starts
   reporting true, and the UI appears. Check first what the page text call would
   then do to OCR output, because it currently changes nothing and would start
   changing text.
2. **Remove the capability**: delete `core/text_normalize.py`, the
   `/api/normalize` route, the SPA's gating, and the call in `api/pages.py`. The
   probe is the only thing keeping the UI hidden, and a capability nobody can
   turn on is worth less than the code it costs.
3. **Keep it pending** only if someone intends to implement long s and ligature
   normalization upstream. If so, the message should name that work rather than
   a version number, and this issue should say who owns it.

Option 1 is my recommendation if the normalization is wanted at all, and option
2 otherwise. What is not worth keeping is the present state, where the app
reports a capability as one upgrade away.

## What is NOT broken

Nothing normalizes text today, and nothing claims to have. The fallback is a
faithful no-op, and the UI stays hidden. This is about a promise the code
cannot keep, not a malfunction.

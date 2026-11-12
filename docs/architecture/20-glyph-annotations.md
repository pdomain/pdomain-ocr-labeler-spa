---
kind: architecture
status: built
owner: maintainers
created: 2026-11-07
last_verified: 2026-11-07
---

# 20 — Glyph annotations

Glyph review preserves printed ligatures, long-s positions, and swash marks alongside canonical ground-truth text.
The manual single-word and page-wide review paths ship today. No glyph predictor exists, and none will be built
here.

## Canonical text and review states

Ground-truth input rejects presentation-form ligatures U+FB00–U+FB06 and long s U+017F. Printed features belong in
glyph annotations instead of those codepoints. This restriction does not mean that all ground-truth text must be
ASCII.

A missing annotation means the word has not been reviewed. An empty annotation object means a person reviewed it
and found nothing to mark. An object with marks records a reviewed word's ligatures, long-s positions, and swash
flag. Glyph review progress is separate from text validation.

The shared model belongs to `pdomain_book_contracts.ocr.glyph_annotations`; the SPA mirrors its wire shape in
`core/models.py`. Ligature spans use half-open ground-truth character offsets; a missing span denotes the whole
word. Long-s positions use ground-truth character offsets. Provenance belongs to the annotation object, with human,
predicted, and human-confirmed sources.

## Manual editing and bulk recipes

WordDetail mounts the glyph panel. A word chip selects its word and opens that panel, as does the pencil control. A
person adds or removes marks, marks the word reviewed without marks, or resets it to unreviewed. Save and reload
preserve the result.

The synchronous page-wide bulk endpoint supports `ct_substring`, `st_substring`, and `long_s_typeset_era`.
Requests can skip already annotated words and preview without mutation. Applying a recipe persists the changes and
refreshes the page. Project-wide bulk work is outside this endpoint's scope.

The picker offers all 14 shared kinds and writes their uppercase wire values. Saved legacy lowercase marks stay as
stored, and the panel names them the same way as current marks. The legacy long-s-t alias is `long_s_t`, not
`long_st`. Bulk recipes still write the legacy `ct` and `st` values, which the shared model migrates on read.

## Persistence and export

PageState carries positional glyph sidecar maps. Content blobs preserve them through `labeler_sidecars`; this
replaced the original proposed envelope-version bump. Structural edit routes reindex sidecars so marks follow their
words. Word split refuses to orphan existing sidecars. Region membership's line-renumbering identity gap remains
separate unresolved work.

Dataset export writes `recognition/glyph_features.json`, keyed by crop id, so confirmed human marks reach
recognition evaluation. The export does not require a prediction producer.

## Prediction boundary

The predictor interface remains, but its only adapter returns no predictions. Prediction acceptance controls
therefore have nothing to accept in normal use. A prediction alone does not count as human review. Resetting
confirmed annotations does not itself clear any prediction state.

A prediction canvas overlay is conditional future polish, not shipped behavior. Per-mark provenance, cross-page
bulk marking, and a profile registry remain deferred design ideas, not implemented contracts.

## API and driver ownership

Per-word annotation and prediction-acceptance routes live in `api/words.py`. Page-wide bulk marking lives in
`api/pages.py`. Generated OpenAPI types define the wire models. [The driver contract](13-driver-contract.md) owns
all glyph panel, chip, and bulk-dialog identifiers.

## Evidence

- Code: `src/pdomain_ocr_labeler_spa/api/words.py`, `api/pages.py`, `core/labeler_sidecars.py`,
  `core/glyph/bulk_mark.py`, and `core/jobs/handlers/glyph_sidecar.py`, under the backend package.
- Tests: `tests/integration/test_glyph_routes.py`, `tests/e2e/test_glyph_panel.py`,
  `tests/e2e/test_bulk_glyph_mark.py`, and `tests/unit/test_gt_rejects_ligature_codepoints.py`.
- Decisions: the 2026-09-18 glyph, persistence, and predictor entries in [the decision log](../context/decisions.md).
- Verified: 2026-11-07 by source, test, and decision inspection. The browser suite was not rerun for this
  documentation change.

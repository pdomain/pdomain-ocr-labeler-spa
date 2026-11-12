---
kind: architecture
status: built
owner: maintainers
created: 2026-11-12
last_verified: 2026-11-12
---

# Typography review

## Agent Index

- **Kind:** architecture
- **Status:** built
- **Owner:** maintainers
- **Last verified:** 2026-11-12
- **Read when:** changing inline typography review, export gates, or the correction journal.
- **Search terms:** typography review, correction journal, grapheme spans, char ranges, page completion.

Phase one of inline typography review is shipped. The right panel writes an append-only correction journal. Suggestion
acceptance and predecessor undo are not built.

The panel widgets live in [right-panel sections](27-right-panel-sections.md). Ownership of training and source data
lives in [repository boundaries](30-repository-boundaries.md). Unfinished product choices stay in the
[typography design](../specs/2026-08-21-typography-review-and-training-export-design.md) and the
[roadmap](../context/intent-map.md).

## What the labeler records

`TypographySection` is the inline-typography editor. It appends to the v1 correction journal at
`.pd-pages/typography-corrections.jsonl`. Existing rows are never rewritten. It does not write character-range sidecars.

`typography_page_review` marks a page complete only when every active word passes both checks and `blocked_words` is 0.

Text passes when the word is in the text-validated set and its latest head is not stale. On a labeling bundle, that set
is the imported-text log. Without a bundle, it is the words whose `word_labels` include `validated`.

Typography passes when `typography_reviewed` accepts the latest head. That requires a replacement, a decision of
`accept`, `approved_edit`, or `reviewed_regular`, a review state of `reviewed` or `reviewed_regular`, and every
required label set to `positive` or `negative`. A missing head, a stale head, or any other decision counts as blocked.
`reject_source` is one of those decisions. The word can count as text-reviewed and still leave the page incomplete.

The typography section shows only `typography_reviewed_words/total_words`. The word footer and the export dialog show
both `text_reviewed_words/total_words` and `typography_reviewed_words/total_words`. None of them show a percentage.

The correction-bundle export writes the journal prefix through the latest selected head. Selecting one word can include
earlier rows for that word and rows for other words that sit before that head.
`test_interleaved_page_global_edits_validate_and_export` selects the first word and gets correction ids
`A1`, `B1`, and `A2`.

Selected heads must be active, text-validated, current, and typography-complete.

General DocTR export does not write this journal.

## Labels in the shipped set

Required for completion: `italic`, `bold`, `small_caps`, `letter_spaced`, `superscript`, `subscript`,
`font_blackletter`, `font_antiqua`, and `font_upright_in_italic`. `_TYPOGRAPHY_POLICY` in `api/typography.py` is the
labeler-v1 taxonomy.

Only `italic`, `bold`, and `small_caps` are trainable. `underline` and `font_other_reviewed` are neither required nor
trainable. The page-review gate uses this fixed required set, not a bundle taxonomy.

## Legacy character ranges

The clean break from legacy character ranges has landed. The OpenAPI schema has no `/char-ranges` path. A legacy
`char_ranges` payload on a word, and a `char_ranges_map` sidecar, are rejected. The 2026-08-22 inventory found no
persisted CharRange payloads to migrate.

## Not built in this app

Suggestion acceptance, suggestion editing, and predecessor-based compensating undo are still open. The design also
leaves six owner choices open: bulk-regular exclusions, quarantine waivers, local reviewer identity, double-review
rate, context-window rule, and the portable export file format.

## Evidence

- Code: `src/pdomain_ocr_labeler_spa/api/typography.py` (`typography_page_review`,
  `export_typography_correction_bundle`, `_TYPOGRAPHY_POLICY`), `src/pdomain_ocr_labeler_spa/core/typography_review.py`
  (`typography_reviewed`), `frontend/src/components/right-panel/WordFooter.tsx`, and `frontend/src/components/ExportDialog.tsx`.
- Tests: `tests/unit/api/test_typography_corrections.py` (`test_rejected_head_blocks_text_and_typography_completion`,
  `test_interleaved_page_global_edits_validate_and_export`) and `tests/unit/api/test_typography_clean_break.py`
  (`test_openapi_contains_no_legacy_char_range_route_or_schema`, `test_word_match_rejects_legacy_char_ranges_payload`, `test_labeler_sidecars_reject_legacy_char_ranges_map`).
- Inventory: [CharRange deletion inventory](../research/2026-08-22-char-range-deletion-inventory.md).
- Verified: 2026-11-12 by reading those functions and tests. The browser suite was not rerun.

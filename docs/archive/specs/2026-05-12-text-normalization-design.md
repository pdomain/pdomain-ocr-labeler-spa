# pdomain-ocr-labeler-spa: Text Normalization (Long-S, Ligatures, Glyph Variants)

> **Status**: Draft
> **Last updated**: 2026-05-12
> **Spec-Issue**: ConcaveTrillion/pdomain-ocr-labeler-spa#40

## TL;DR

OCR fidelity wins by default: `ſhall` is stored as-is. Normalization runs on the way out
(plaintext tabs, export labels) or on-demand for GT-matching. Glyph→ASCII map lives in
`pd_book_tools.text.normalize`; SPA calls in, ships no map of its own. Toggle UI in the OCR
config modal ships in M9. When pdomain-book-tools hasn't shipped the API, toggles are disabled with
"Requires pdomain-book-tools ≥ X.Y.Z" tooltip.

## Context

Old-typesetting pages frequently contain `ſ` (long-s, U+017F), `ﬁ` `ﬂ` `ﬃ` `ﬄ` (ligature
codepoints), and similar glyphs. DocTR may produce these in OCR output. PGDP and DocTR training
corpora expect ASCII. The SPA resolves this by preserving the OCR glyph in storage while
normalizing only at the point of consumption — comparison, display, or export. The decision
principle (D-025) is: "OCR fidelity wins by default; PGDP fidelity wins on request."
Normalization scope (project-level in OCRConfig) is resolved by D-033.

## Constraints

- **SPA ships no glyph map.** All normalization delegates to `pd_book_tools.text.normalize`.
  If that module is absent (older pin), toggles are disabled; no SPA-level fallback map.
- **Stored envelope is never normalized.** `word.ocr_text` and `word.ground_truth_text` in the
  envelope are always the original strings. Normalization is a view/export transform only.
- **Predictions are not persisted.** `glyph_predictions` lives only in-memory; see
  `specs/20-glyph-annotations.md` for the related side-channel.
- **One-way map.** `normalize_string("ſhall") = "shall"` is idempotent;
  `normalize_string("shall") = "shall"`. Never un-normalize.
- **v1 ships `ascii` profile only.** Future profiles (`gaelic`, `fraktur`, `greek-polytonic`)
  are placeholders; the profile select is present but greyed out in v1.
- **GT must not contain ligature codepoints.** Backend rejects GT input containing
  U+FB00–U+FB06 or U+017F with 400 `validation_error`.

## Decision

### Normalization architecture

Three distinct concerns, each with a separate owner:

1. **Glyph→ASCII map**: `pd_book_tools.text.normalize.normalize_string(s, profile="ascii")`.
   Called by the SPA; not implemented in the SPA.
2. **Normalization-aware fuzz matching**: `pd_book_tools.ocr.ground_truth_matching` extended
   with an opt-in flag. When enabled: compare `normalize(ocr_text)` vs `normalize(gt_text)`;
   if equal → `match_status=exact`, `fuzz_score=1.0`, `normalized_match=True` on WordMatch.
3. **Output-time normalization**: applied to plaintext-tab content and export recognition
   labels when the relevant OCR config toggle is on.

### Normalization-aware matching

`WordMatch` gains `normalized_match: bool` (false by default). When the toggle is on and both
normalized strings are equal, the SPA renders a small "≈" badge on the exact-match status icon
to signal "exact only after normalization". This preserves raw strings for researchers while
showing PGDP-friendly match quality.

The fuzz matcher is enabled per-request via a flag; default is off. The SPA passes this flag
to `pd_book_tools` when `OCRConfig.normalize_for_gt_matching = true`.

### Output-time normalization

**Plaintext tabs**: `PagePayload.page_text_ocr` and `page_text_gt` are sent normalized
(profile=ascii) when `OCRConfig.normalize_plaintext_tabs = true`. The Matches tab (per-word)
is unaffected.

**DocTR export**: `ExportRequest` gains `normalize_recognition_labels: bool = false`. When
true, recognition `labels.json` strings are normalized before write. Image bytes are unchanged
(the OCR target is the image, not the label).

### OCR config persistence

`config.yaml` gains three optional fields (all default off, matching legacy behaviour):

```yaml
normalize_for_gt_matching: false
normalize_plaintext_tabs: false
normalize_profile: "ascii"
```

`extra="ignore"` on the config reader means legacy tools ignore these fields on read.

### Toggle UI (M9 polish)

New "Text normalization" section in `<OCRConfigModal />`:
`normalize-gt-matching-checkbox` and `normalize-plaintext-checkbox` checkboxes;
`normalize-profile-select` (greyed out in v1, only `ascii` available).

When `pd_book_tools.text.normalize` is unavailable (ImportError), the section shows
"Requires pdomain-book-tools ≥ X.Y.Z" and toggles are disabled.

### GT validation

Backend rejects GT input containing U+FB00–U+FB06 (`ﬀﬁﬂﬃﬄﬅﬆ`) or U+017F (`ſ`) with
`400 validation_error`. The SPA normalizes these to ASCII before allowing save, or shows a
validation error message.

## Contract / Acceptance

- Storing a page with OCR text `ſhall` preserves `ſhall` in the envelope (not `shall`).
- With `normalize_for_gt_matching=true`: OCR `ſhall` vs GT `shall` → `match_status=exact`,
  `normalized_match=true`, `fuzz_score=1.0`.
- With `normalize_plaintext_tabs=true`: plaintext OCR tab shows `shall` for `ſhall`.
- Export with `normalize_recognition_labels=true`: `labels.json` contains `shall`.
- POST GT input containing `ﬁ` returns 400 `validation_error`.
- When pdomain-book-tools normalize module is absent: toggles are disabled, no 500.
- Unit: `normalize_string("ſhall", "ascii") == "shall"` (in pdomain-book-tools test; SPA test
  verifies the call is made correctly).

## Trade-offs considered

**Normalize on store vs on output.** Storing normalized destroys OCR fidelity (no recovery
path). Normalizing on output preserves all raw data while giving downstream consumers what they
need. Chosen: normalize on output only.

**SPA-local glyph map vs delegate to pdomain-book-tools.** A local map would work today but creates
two maps to maintain (SPA + pdomain-book-tools). Any future profile addition must be done in one
place. Chosen: delegate entirely to pdomain-book-tools.

**Always normalize GT display vs toggle.** Always normalizing the plaintext tabs would simplify
the UI but surprises researchers who want to see the raw OCR glyphs. Toggle chosen; default off.

**Profile registry at SPA level vs pdomain-book-tools.** Profiles are complex (locale-specific
heuristics). SPA passes through the profile name string; pdomain-book-tools owns the registry.
Chosen: SPA is a thin caller.

## Consequences

- If `pd_book_tools.text.normalize` API changes, the SPA call site needs updating. Pin the
  minimum pdomain-book-tools version in `pyproject.toml` when the module is first consumed.
- The "≈" badge on normalized-exact matches must appear in the word-status-icon testid (or as
  a separate `word-normalized-badge-{l}-{w}` testid) — add to `specs/13-driver-contract.md`
  when implemented.
- `normalize_profile: "ascii"` in config.yaml means future profiles require a config migration
  or `extra="ignore"` to avoid breaking old configs (already handled by the reader).

## Open questions

- **Q-A2 — Toggle scope.** Should `normalize_display` be per-project (stored in `OCRConfig`)
  or per-word? Source spec bet: project-level. Pending user confirmation. See
  `specs/18-text-normalization.md §10` and `OPEN_QUESTIONS.md` (entry pending).

## References

- `specs/18-text-normalization.md` — legacy feature doc (glyph table, matching algorithm, tests)
- `specs/17-decisions.md §D-025, §D-033` — normalization principles and toggle-scope decision
- `specs/20-glyph-annotations.md` — the side-channel spec (glyph typographic data, distinct from normalization)
- `pd_book_tools.text.normalize` — implementation home (pdomain-book-tools team)

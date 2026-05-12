# pd-ocr-labeler-spa: Glyph-level Side-channel Annotations

> **Status**: Draft
> **Last updated**: 2026-05-12
> **Spec-Issue**: ConcaveTrillion/pd-ocr-labeler-spa#44

## TL;DR

`GlyphAnnotations` (ligature marks, long-s positions, swash flag) stored per word alongside GT,
never inside GT. Three-state per word: `None` (unreviewed) / empty `GlyphAnnotations()` (reviewed,
no marks) / populated (reviewed with marks). Classifier predictions (`glyph_predictions`) are
advisory and NOT persisted. Envelope bumps to v2.2 (additive; Q-A5 tracks legacy compat).
SPA surfaces `<GlyphAnnotationPanel>`, `<GlyphChip>`, `<BulkGlyphMarkDialog>` (three preset
recipes: CT, ST, long-s heuristic). Driver automates bulk marking via `bulk-glyph-*` testids.

## Context

Pre-1800s printing uses ligature forms (`ct`, `st`, `fi`, `fl`) and long-s (`ſ`) that disappear
from ASCII ground truth. The SPA preserves these as side-channel data so typography researchers,
font-training pipelines, and pd-ocr-synth recipes can consume them. GT text stays ASCII (enforced
by backend validation). The glyph data model lives in `pd_book_tools.ocr.glyph_annotations` (new
module). A future pd-ocr-trainer classifier can inject `glyph_predictions`; the SPA surfaces them
as advisory marks awaiting human confirmation.

## Constraints

- **GT text must never contain ligature codepoints.** Backend rejects U+FB00–U+FB06 and U+017F
  in GT input with 400 `validation_error`.
- **`glyph_predictions` are never persisted.** Predictions are regenerated on page load by the
  classifier adapter. Only `glyph_annotations` (confirmed) writes to the envelope.
- **Three-state distinction is load-bearing.** `None` ≠ empty `GlyphAnnotations()`. The progress
  metric counts "glyphs reviewed" only for non-None words.
- **Data model lives in pd-book-tools.** SPA imports `GlyphAnnotations`, `LigatureMark`,
  `LigatureKind` from `pd_book_tools.ocr.glyph_annotations`; ships no local copy.
- **Envelope v2.2 conditional on Q-A5.** If the legacy reader's `extra="forbid"` on nested
  fields rejects v2.2: fall back to sidecar `<project_id>_<page:03d>.glyph.json`.
- **Page-scope bulk only (v1).** Project-wide bulk mark is out of scope; driver iterates per page.
- **`IGlyphPredictor` adapter = `none` by default.** Classifier wiring is future; the `none`
  adapter returns `{}` cleanly.

## Decision

### Data model (defined in pd-book-tools)

`LigatureKind` enum: CT, ST, LONG_ST, FI, FL, FFI, FFL, OE, AE. `LigatureMark(kind, char_span)`.
`GlyphAnnotations(ligatures, long_s_positions, swash, source)` where
`source ∈ "human"|"predicted"|"human_confirmed"`.

`WordMatch` gains `glyph_annotations: GlyphAnnotations | None` (confirmed) and
`glyph_predictions: GlyphAnnotations | None` (advisory, never persisted).

### Envelope v2.2 schema delta

`payload.glyph_annotations`: `dict[word_id, GlyphAnnotations]`. Absent key → `None` ("not
reviewed"). Empty dict value → `GlyphAnnotations()` ("reviewed, no marks"). SPA writes v2.2
only after verifying legacy tolerance (Q-A5). Until then, sidecar fallback.

Read rules: v2.1 envelope → all `glyph_annotations = None`. v2.2 → rebuild from dict.
Predictions never written.

### UI components

**`<GlyphAnnotationPanel>`**: collapsible "Typography" section in `<WordEditDialog>`, also
accessible as a popover from `<WordCell>` chip row. Shows confirmed (solid bullet `•`) and
predicted (hollow `◌`, with accept/reject buttons) marks. Char-span picker for ligatures
(inline for ≤8 chars, modal for longer). Long-s picker: single-click toggles per char offset.
"Mark reviewed (no marks)": writes empty `GlyphAnnotations()`. "Reset": writes `None`.

**`<GlyphChip>`**: compact pill rendered under `<WordCell>` GT input and in dialog chip row.
Solid chip = confirmed; hollow = predicted-only.

**`<WordCell>` corner badge** (`word-glyph-badge-{line}-{word}`): 6×6px square. Hidden when
no annotations/predictions. Amber = predictions pending. Blue = reviewed (including empty).
Green = reviewed with ≥1 mark.

**`<BulkGlyphMarkDialog>`**: opened from `<ToolbarActionGrid>` "Bulk-mark glyphs" button.
Three recipes: CT substring auto-mark, ST substring auto-mark, long-s typeset-era heuristic.
Recipe is data-driven; pd-book-tools may add future profiles. Dry-run preview shows affected
count. POST `glyph-bulk-mark` endpoint; synchronous (no SSE needed for page-scope).

**Predictions overlay** (M11.x polish): ghost outlines on words with pending predictions in
the canvas viewport. Toggle `predictions-overlay-toggle` in `<ImageTabsHeader>`. Ghost color:
`#3B82F6` at 40% opacity (CSS custom property `--predictions-ghost-color`).

### Backend endpoints

`POST .../words/{l}/{w}/glyph-annotations` body: `{annotations: GlyphAnnotations | null}`.
Returns `WordMatch`. Setting `null` unsets (back to "not reviewed").

`POST .../words/{l}/{w}/accept-prediction`: promotes `glyph_predictions` to
`glyph_annotations(source="human_confirmed")`. Returns `WordMatch`.

`POST .../pages/{idx}/glyph-bulk-mark` body: `{recipe, skip_already_annotated, accept_predictions,
dry_run}`. Returns `{affected_word_ids, skipped_word_ids, page: PagePayload | null}`.

### Progress metric

Two separate axes: validated (existing) and glyphs-reviewed (new). Page header shows both:
"Validated 47/120" and "Glyphs reviewed 12/120". When `glyph_review_required: false` (default),
the second metric renders muted. When `true`, Save Project warns on unreviewed glyphs.

`OCRConfig` gains `glyph_review_required: false`.

### IGlyphPredictor adapter

Protocol: `predict(page: Page) -> dict[str, GlyphAnnotations]`. Adapter `none` returns `{}`.
Adapter `local_pdtrainer` (future) calls pd-ocr-trainer. Predictions populate
`WordMatch.glyph_predictions` on every page fetch; NOT persisted.

## Contract / Acceptance

- `word-glyph-badge-{l}-{w}` absent when `glyph_annotations is None and glyph_predictions is None`.
- `word-glyph-badge-{l}-{w}` amber when predictions pending, no confirmation.
- `word-glyph-badge-{l}-{w}` green when confirmed with ≥1 ligature mark.
- "Mark reviewed (no marks)" → badge turns blue; word counted in "Glyphs reviewed" metric.
- "Reset" → badge hidden; word reverts to `None` (not counted).
- Bulk CT recipe on fixture page with 5 `ct` words: preview count = 5; apply → 5 chips appear.
- POST GT containing `ﬁ` returns 400 `validation_error`.
- `glyph_annotations` persists across server restart (in envelope v2.2 or sidecar).
- `glyph_predictions` NOT present in saved envelope; regenerated on page load.

## Trade-offs considered

**Glyph data in GT vs side-channel.** In-GT storage is convenient but destroys ASCII
interoperability and PGDP compatibility. Side-channel preserves both. Chosen: side-channel.

**Per-mark provenance vs per-annotation-object provenance.** Per-mark is more granular but
complicates the model and the UI. v1 stores `source` at the `GlyphAnnotations` level. If finer
granularity is needed later, a v2.3 bump can add it. Chosen: per-object provenance (Q-A7).

**Persist predictions vs regenerate.** Persisting predictions creates staleness (classifier
improves; old predictions become wrong). Regenerating on load is always fresh. Cost: classifier
run on every page load. If the classifier is fast (< 100ms per page), this is acceptable.
Chosen: regenerate, never persist.

**Page-scope vs project-scope bulk mark.** Project-scope adds SSE complexity. The driver can
iterate pages; page-scope is sufficient for v1. Chosen: page-scope synchronous bulk.

## Consequences

- The `GlyphAnnotations` data model must be stable in pd-book-tools before M9 ships;
  a breaking change in `LigatureKind` after the envelope format is fixed would require a
  data migration.
- The progress metric change ("Glyphs reviewed") adds a new field to `PagePayload`; update
  `specs/01-data-models.md §2` and `openapi-export` accordingly.
- Until Q-A5 is resolved, the SPA logs a WARN on every v2.2 envelope write.

## Open questions

- **Q-A7 — Per-mark provenance granularity.** v1 puts `source` at the object level
  (`GlyphAnnotations.source`), not per `LigatureMark` or per `long_s_positions` entry. Is
  object-level granularity sufficient for training-data needs? See `OPEN_QUESTIONS.md §Q-A7`.

## References

- `specs/20-glyph-annotations.md` — legacy feature doc (full data model, endpoints, testids, tests)
- `specs/18-text-normalization.md` — sister spec (the normalization map; this spec is the side-channel)
- `specs/17-decisions.md §D-025, §D-026, §D-032, §D-034` — relevant ADR entries
- `specs/13-driver-contract.md §2.x` — glyph testid additions for driver bulk-mark
- `pd_book_tools.ocr.glyph_annotations` — data model home (pd-book-tools team)
- `OPEN_QUESTIONS.md §Q-A7` — per-mark provenance question (Q-A5 and Q-A6 resolved)

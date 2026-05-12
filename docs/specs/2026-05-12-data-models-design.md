# pd-ocr-labeler-spa: Data Models

> **Status**: Draft
> **Last updated**: 2026-05-12
> **Spec-Issue**: ConcaveTrillion/pd-ocr-labeler-spa#6

## TL;DR

All Pydantic domain models and per-route wire shapes for the SPA. Domain models live in
`core/models.py` and are shared by adapters and the HTTP layer — no separate DTO layer.
Pydantic v2 with `extra="forbid"` on top-level persistence envelopes and `extra="ignore"`
on nested provenance blocks. `UserPageEnvelope` v2.1 is preserved byte-for-byte for
on-disk compatibility with the legacy labeler.

## Context

The legacy `pd-ocr-labeler` uses a mix of ad-hoc dicts, dataclasses, and NiceGUI reactive
models. The SPA replaces all of this with a single Pydantic v2 model layer that:

1. Serves as the source of truth for both the FastAPI route schemas and the adapter
   protocol interfaces — the same `Project`, `PageRecord`, and `WordMatch` types flow
   from disk through the server into the OpenAPI schema and into the generated TypeScript
   client.
2. Preserves on-disk schema compatibility: `UserPageEnvelope` v2.1 is the shared format
   between the SPA and the legacy labeler, and may not change without a coordinated
   migration path (D-003).
3. Pre-computes aggregates server-side (`LineMatch` counters) so the SPA can render
   header rollups without JavaScript recomputation.

The reference for the model shapes is `specs/01-data-models.md` (legacy feature doc) and
the legacy source files it cross-references.

## Constraints

- **`UserPageEnvelope` v2.1 binary compatibility (D-003).** The schema
  `pd_ocr_labeler.user_page` v2.1 must round-trip identically against fixture envelopes
  from `pd-ocr-labeler/tests/`. Any additive bump to v2.2 requires a coordinated
  migration path.
- **`MatchStatus` enum parity.** Exactly five values —
  `exact | fuzzy | mismatch | unmatched_ocr | unmatched_gt` — matching the legacy
  `WordMatch.match_status`. No renames without a migration.
- **Bbox coordinates are image-space.** Top-left origin, source image pixels (not display
  pixels). Scaling to display pixels happens on the frontend using `EncodedDims.scale`.
- **`extra="forbid"` on top-level persistence envelopes.** Catches schema drift at load
  time. Nested provenance models use `extra="ignore"` for forward-compat with files
  written by future SPA versions.
- **No separate DTO layer.** Per-route request/response shapes (`<Verb><Noun>Request` /
  `<Verb><Noun>Response`) live in the route module that defines them, not in a separate
  `dto.py`. Domain models are reused directly where the wire shape matches.
- **`pd-book-tools` owns label vocabularies.** `ALLOWED_TEXT_STYLE_LABELS` and
  `ALLOWED_WORD_COMPONENT_LABELS` come from `pd_book_tools.ocr.label_normalization`;
  the SPA must not hardcode its own copies.

## Decision

### Domain models (`core/models.py`)

- **`Project`** — mirrors legacy `ProjectModel`; fields: `project_id`, `project_root`,
  `image_paths`, `ground_truth_map`, `version`, `source_lib`, `total_pages`,
  `saved_pages`, `current_page_index`, `include_images`, `copied_images`.
- **`PageRecord`** — wraps per-page metadata (source, OCR provenance, cached image refs);
  the `Page` object itself lives in `PageState` in-memory and is NOT serialised here.
- **`PageSource`** — StrEnum: `ocr | cached_ocr | filesystem | fallback`.
- **`MatchStatus`** — StrEnum: `exact | fuzzy | mismatch | unmatched_ocr | unmatched_gt`.
- **`WordMatch`** — per-word match result including bbox, labels, validation flag, stable
  `word_id` from `pd-book-tools`.
- **`LineMatch`** — per-line rollup with pre-computed counters (`exact_count`,
  `fuzzy_count`, etc.) and `is_fully_validated`.
- **`BBox`** — `{x, y, width, height}` in image-space pixels.
- **`EncodedDims`** — source and display dimensions with `scale` factor; algorithm matches
  legacy `_compute_encoded_dimensions`.
- **`Selection`** — backend-canonical per-page UI selection state (mode + selected sets).
- **`LineFilter`** — StrEnum: `unvalidated | mismatched | all`.
- **`CachedImageSet`** — optional filenames for each cached image type.

### Wire shapes (per-route modules)

Naming convention: `<Verb><Noun>Request` / `<Verb><Noun>Response`. Key shapes:

- **Projects**: `ListProjectsResponse`, `ProjectKey`, `LoadProjectRequest`,
  `LoadProjectResponse`, `SetSourceProjectsRootRequest/Response`.
- **Pages**: `PagePayload` (record + dims + line_matches + text + image URLs +
  `has_edited_image`), `GetPageRequest`, `SavePageRequest/Response`,
  `SaveProjectResponse`, `ReloadOCRRequest`, `RematchGtRequest`.
- **Words**: `UpdateWordGroundTruthRequest`, `ApplyStyleRequest`,
  `ApplyComponentRequest`, `ToggleValidatedRequest`, `ValidateBatchRequest`,
  `AddWordRequest`, `ReboxWordRequest`, `NudgeBboxRequest`, `SplitWordRequest`,
  `MergeWordsRequest`, `ErasePixelsRequest`.
- **Lines/paragraphs**: `CopyLineGtRequest`, `DeleteScopeRequest`,
  `MergeScopeRequest`, `SplitParagraphAfterLineRequest`, `SplitLineAfterWordRequest`,
  `SplitLineWithSelectedWordsRequest`, `GroupSelectedWordsIntoNewParagraphRequest`.
- **Refine**: `RefineScopeRequest` with scope / mode / padding_px.
- **OCR config**: `OCRModelOption`, `GetOCRConfigResponse`, `SetOCRModelsRequest`.
- **Export**: `ExportScope`, `ExportRequest`, `ExportResponse`.
- **Jobs**: `JobStatus`, `JobType`, `JobProgress`, `Job` — mirrors pgdp-prep.

### Pydantic configuration

- Top-level envelopes: `model_config = ConfigDict(extra="forbid")`.
- Nested provenance blocks: `extra="ignore"` (forward-compat).
- All persistence models: explicit `from_dict` / `to_dict` for round-trip JSON.

### `PagePayload` eagerness

`LoadProjectResponse` eagerly fetches the first page's `PagePayload`. Subsequent page
navigations use `GET /api/projects/{id}/pages/{idx}` which returns `PagePayload`
independently. This avoids a second round-trip on first load.

## Contract / Acceptance

- `make openapi-export` generates `frontend/src/api/types.ts` that type-checks with
  `tsc --noEmit`.
- Round-trip golden test: every fixture envelope from
  `pd-ocr-labeler/tests/browser/fixtures/` parses with `parse_envelope`, builds back
  with `build_envelope`, and produces byte-equal output.
- `MatchStatus` values match the legacy enum exactly (regression test against
  `pd_ocr_labeler.models.word_match.MatchStatus`).
- `EncodedDims` scale computation matches legacy `_compute_encoded_dimensions` output
  for a set of known image sizes (parameterised pytest).

## Trade-offs considered

**No DTO layer vs separate DTO layer.** A separate DTO layer (distinct from domain models)
would let the wire schema diverge from internal types. For this project the alignment
between wire and domain is tight enough that a DTO layer adds indirection without value.
Chosen: no DTO layer; route modules define their own request/response shapes.

**Eager first-page vs lazy.** Fetching the first page eagerly in `LoadProjectResponse`
adds server-side cost to every project load. The trade-off: eliminates a waterfall
round-trip in the UI on startup. Given that project load is infrequent and the first page
is always needed, eager fetch is preferred.

**Server-side counter pre-computation vs client-side.** Pre-computing `LineMatch` counters
on the server means the client can render header rollups without iterating word matches.
Cost: extra server-side work on every page fetch. Given the match computation is already
done server-side, the incremental cost is negligible.

**`extra="forbid"` vs `extra="ignore"` on top-level envelopes.** `extra="ignore"` would
silently drop unknown fields, hiding schema drift. `extra="forbid"` fails loudly on
unexpected fields, which is valuable for catching the legacy/SPA drift during the
transition period. Chosen: `extra="forbid"` on top-level envelopes only.

## Consequences

- Adding a new field to any wire shape requires `make openapi-export` to regenerate the
  TS types; CI gate catches drift automatically.
- Any additive field to `UserPageEnvelope` must be declared optional with a default so
  legacy files without it still round-trip (backward-compat reading rule).
- `word_id` from `pd-book-tools` must be stable across OCR runs for optimistic UI
  updates to work correctly after a refine or reload.

## Open questions

None.

## References

- `specs/01-data-models.md` — legacy feature-description doc (model shapes and field
  semantics)
- `specs/09-persistence.md` — `UserPageEnvelope` v2.1 full schema and round-trip rules
- `specs/02-backend.md` — FastAPI endpoint list that consumes these shapes
- `../pd-prep-for-pgdp/src/pd_prep_for_pgdp/core/models.py` — reference implementation
- `pd-book-tools` — `ALLOWED_TEXT_STYLE_LABELS`, `ALLOWED_WORD_COMPONENT_LABELS`,
  `Page`, `Word`, `BBox` types

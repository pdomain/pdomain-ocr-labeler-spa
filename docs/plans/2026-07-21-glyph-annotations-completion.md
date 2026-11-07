---
kind: plan
status: partial
owner: maintainers
created: 2026-07-21
last_verified: 2026-11-07
---

# Glyph picker enum parity

The manual glyph-review workflow ships. This plan retains the picker enum mismatch that the 2026-09-18 close-out
left open.

## Goal

Make the manual ligature picker agree with the shared annotation contract without changing existing saved marks or
wire values.

## Architecture

The shared model belongs to `pdomain_book_contracts.ocr.glyph_annotations`. The SPA mirrors it in the API model
and generated TypeScript types. The glyph panel sends those wire values through the existing per-word mutation.

[Glyph architecture](../architecture/20-glyph-annotations.md) owns the shipped review, sidecar persistence,
progress, bulk recipes, and export behavior. Do not rebuild those paths.

## Tech Stack

React, TypeScript, generated OpenAPI models, FastAPI, Vitest, pytest, and Playwright.

## Global Constraints

- Shared enum values are uppercase. Preserve the existing FF value and saved annotations.
- The legacy long-s-t alias is `long_s_t`, not `long_st`. Do not copy the old lowercase recipe from this plan's
  Git history as a wire contract.
- Do not add a predictor. The 2026-09-18 decision rejected one permanently for this app.
- Keep the [driver identifiers](../architecture/13-driver-contract.md) stable. Regenerate OpenAPI types after any
  API-model change.

## Remaining implementation

1. Compare the actual shared enum, the mirrored API model, and the panel's `LIGATURE_KINDS`. The current picker
   offers ct, st, fi, fl, ff, ffi, and ffl; check every shared enum value, including LONG_ST, OE, AE, LONG_S_S, LONG_S_I, SP, and QU.
2. Add a focused failing test for every supported kind missing from the picker. Check request bodies and reload
   results, rather than testing a copied list against itself.
3. Reconcile the picker and labels while preserving supported legacy values. Do not remove FF merely because an
   older draft omitted it.
4. Run focused frontend and backend tests, then the repository gate. Record any remaining browser limits separately
   from implementation completion.

## Deferred work and verification limits

Prediction overlays and individual prediction controls are conditional polish, not a missing prediction producer.
Per-mark provenance, cross-page bulk work, and a profile registry remain deferred ideas.

Single-word and bulk review browser tests exist in `tests/e2e/test_glyph_panel.py` and
`tests/e2e/test_bulk_glyph_mark.py`. Route coverage lives in `tests/integration/test_glyph_routes.py`. This
consolidation inspected them but did not rerun the browser suite.

## Completion criteria

Every supported shared ligature kind is editable with the correct wire value, existing marks survive save/reload,
and focused tests prove the missing-kind paths. The shipped manual workflow remains usable without predictions.

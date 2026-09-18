---
kind: spec
status: active
owner: maintainers
created: 2026-06-01
last_verified: 2026-09-18
---

# Behavior unit spec - Glyph annotations

- **Unit type:** component/backend side-channel
- **Address:** glyph chips, `GlyphAnnotationPanel`, `BulkGlyphMarkDialog`
- **UI definition:** none - implementation and tests define current behavior.
- **Parent unit(s):** right panel, drawer word cells, page actions
- **Child unit(s):** glyph annotation endpoints and page-state persistence
- **Shared unit:** yes
- **Implementation:** `frontend/src/components/glyph/*`,
  glyph backend endpoints, glyph page-state persistence/model tests
- **Backend / collaborators touched:** glyph annotations, glyph predictions,
  glyph bulk mark endpoint, page state/page payload

## Behavior records

### B-GLYPH-001 - Word glyph badge and chips reflect annotation state

- **Flow(s):** -
- **Composed by:** B-RIGHT-001
- **Trigger:** Page payload includes glyph annotations or predictions.
- **Preconditions:** Word row/cell renders.
- **Observable output:** Badge is absent/amber/blue/green as appropriate and
  confirmed/predicted chips render beside the word.
- **Backend / side-effects:** Render only.
- **Bad-state / error:** Null annotations or predictions hide badge/chips
  without crashing.
- **Tier(s):** A
- **Regression:** no
- **Test:** `frontend/src/components/WordCell.test.tsx` (badge absent/amber/
  blue/green cases) and `frontend/src/components/glyph/GlyphChip.test.tsx`
  (confirmed vs. predicted chip rendering).

### B-GLYPH-002 - Manual glyph review edits word-level annotations

- **Flow(s):** F-GLYPH-REVIEW-01
- **Composed by:** B-GLYPH-001
- **Trigger:** User marks reviewed, resets, adds/removes ligature spans, toggles
  long-s, or toggles swash.
- **Preconditions:** Glyph annotation panel is mounted for a word.
- **Observable output:** Panel controls, selected character cells, and mark
  chips update; empty reviewed state is distinct from unreviewed/null.
- **Backend / side-effects:** Parent callback should persist via glyph
  annotation endpoint where mounted.
- **Bad-state / error:** Reset returns annotation state to null; failed persist
  keeps panel recoverable.
- **Tier(s):** A
- **Regression:** no
- **Test:** `frontend/src/components/right-panel/WordDetail.test.tsx` (mount +
  mark-reviewed), `frontend/src/components/glyph/GlyphAnnotationPanel.test.tsx`,
  and `tests/e2e/test_glyph_panel.py` (browser click through to a persisted
  server-side value).

### B-GLYPH-003 - Prediction accept/reject creates human review state

- **Flow(s):** F-GLYPH-REVIEW-01
- **Composed by:** B-GLYPH-002
- **Trigger:** User accepts or rejects a predicted glyph mark.
- **Preconditions:** Predictions exist for the selected word.
- **Observable output:** Prediction controls render and confirmed/rejected state
  changes.
- **Backend / side-effects:** Accept posts accept-prediction; reject persists a
  human review without the mark.
- **Bad-state / error:** No predictions returns a recoverable backend error.
- **Tier(s):** A
- **Regression:** no
- **Test:** accept only —
  `frontend/src/components/right-panel/WordDetail.test.tsx`'s "accepts a
  prediction, posting to the accept-prediction route" test and
  `frontend/src/hooks/useWordMutations.test.tsx`'s `useAcceptGlyphPrediction`
  suite. No test drives the reject button
  (`glyph-panel-reject-prediction-{kind}`): predictions never populate in the
  e2e suite (`IGlyphPredictor` has no live adapter — see §9), and no unit test
  clicks it either.

### B-GLYPH-004 - Bulk glyph mark dialog previews and applies recipes

- **Flow(s):** F-GLYPH-REVIEW-01
- **Composed by:** B-ACTIONS-008
- **Trigger:** User opens Bulk glyphs, chooses recipe/options, previews, and
  applies.
- **Preconditions:** Project page loaded.
- **Observable output:** Modal, preview count, disabled/busy/error states render;
  successful apply closes dialog.
- **Backend / side-effects:** `POST pages/{idx}/glyph-bulk-mark` runs dry-run
  or mutating mode.
- **Bad-state / error:** Invalid recipe/backend failure shows error and keeps
  dialog open.
- **Tier(s):** A+B
- **Regression:** no
- **Test:** `frontend/src/components/glyph/BulkGlyphMarkDialog.test.tsx`
  (rendering, Cancel, and that a successful apply invalidates the page query
  while a failed apply or a dry-run does not) and, on the backend,
  `tests/integration/test_glyph_routes.py`'s
  `test_glyph_bulk_mark_dry_run_returns_preview_without_mutating` and
  `test_glyph_bulk_mark_apply_stamps_words_and_bumps_generation`.

### B-GLYPH-005 - Glyph side-channel preserves null, empty, and populated states

- **Flow(s):** F-GLYPH-REVIEW-01
- **Composed by:** B-GLYPH-002, B-GLYPH-004
- **Trigger:** User sets annotations, accepts predictions, bulk marks, reloads,
  or saves.
- **Preconditions:** Loaded page supports glyph annotation fields.
- **Observable output:** `WordMatch.glyph_annotations` preserves unreviewed
  null, reviewed empty, and populated states; header metrics can count reviewed
  words.
- **Backend / side-effects:** Page-state glyph annotation maps retain human
  review state for refreshed page payloads within the loaded session;
  predictions are not saved as accepted annotations unless user accepts.
- **Bad-state / error:** none observed — a fresh-store reload correctly
  restores each tri-state case.
- **Tier(s):** A
- **Regression:** no
- **Test:** `tests/integration/test_glyph_routes.py`'s
  `test_glyph_annotations_populated_persist_across_fresh_store_reload`,
  `test_glyph_annotations_empty_reviewed_persist_across_fresh_store_reload`,
  `test_glyph_annotations_cleared_removes_entry_across_fresh_store_reload`,
  and `test_glyph_bulk_mark_apply_persists_across_fresh_store_reload` — each
  closes and reopens the event store between write and read.

## Adversarial Review

**2026-07-13 finding (superseded):** the described frontend glyph components did not exist; this
was draft behavior even though Q-A5–Q-A7 were resolved.

**2026-09-18 update:** the components exist, are mounted in `WordDetail`, and the behaviors above
are backed by real tests — see each record's **Test** field. Two things are not claimed as shipped:
the `glyph-panel-reject-prediction-{kind}` button has no test coverage (B-GLYPH-003), and no
predictor exists to populate `glyph_predictions` at all — the labeler will not build one (decided
2026-09-18, `docs/context/decisions.md`), so the accept/reject prediction UI is a seam that renders
nothing for any real user today.

**Stage:** migration-time current-state review on 2026-07-13; docs close-out verification on
2026-09-18.

**Source:** an independent read-only reviewer compared this document with current code, tests,
architecture, and git history on 2026-07-13; the 2026-09-18 update re-verified against current
`frontend/src/components/glyph/*`, `frontend/src/components/right-panel/WordDetail.tsx`, and the
test files cited above.

**Result:** residual risks remain explicit here or in `docs/context/intent-map.md`; deferred or
blocked behavior is not claimed as shipped.

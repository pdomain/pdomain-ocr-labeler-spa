# Behavior unit spec - Glyph annotations

- **Unit type:** component/backend side-channel
- **Address:** glyph chips, `GlyphAnnotationPanel`, `BulkGlyphMarkDialog`
- **UI definition:** none - implementation and tests define current behavior.
- **Parent unit(s):** right panel, drawer word cells, page actions
- **Child unit(s):** glyph annotation endpoints and envelope persistence
- **Shared unit:** yes
- **Implementation:** `frontend/src/components/glyph/*`,
  glyph backend endpoints, glyph envelope persistence/model tests
- **Backend / collaborators touched:** glyph annotations, glyph predictions,
  glyph bulk mark endpoint, page envelope sidecar

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
- **Test:** -

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
- **Test:** -

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
- **Test:** -

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
- **Test:** -

### B-GLYPH-005 - Glyph side-channel preserves null, empty, and populated states

- **Flow(s):** F-GLYPH-REVIEW-01
- **Composed by:** B-GLYPH-002, B-GLYPH-004
- **Trigger:** User sets annotations, accepts predictions, bulk marks, reloads,
  or saves.
- **Preconditions:** Loaded page supports glyph annotation fields.
- **Observable output:** `WordMatch.glyph_annotations` preserves unreviewed
  null, reviewed empty, and populated states; header metrics can count reviewed
  words.
- **Backend / side-effects:** Sidecar/envelope writes persist human review
  state; predictions are not saved as accepted annotations unless user accepts.
- **Bad-state / error:** Older v2.1 envelopes load as unreviewed/null.
- **Tier(s):** A
- **Regression:** no
- **Test:** -

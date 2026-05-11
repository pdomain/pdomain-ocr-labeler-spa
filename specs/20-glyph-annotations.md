# 20 — Glyph-level Side-channel Annotations

> **Status**: Active
> **Last updated**: 2026-05-11
> **Spec-Issue**: ConcaveTrillion/pd-ocr-labeler-spa#44

How the SPA records and edits **typographic features** (ct/st ligatures,
long-s positions, swash caps, …) that the canonical GT text deliberately
throws away. Glyph annotations live **alongside** GT text, never inside
it: GT stays "perfect" ASCII; annotations are a parallel structure.

> Cross-refs:
> ADR — [`17-decisions.md`](17-decisions.md) D-025 (text normalization;
> the principle that "GT is canonical, OCR/typography is the
> side-channel" — this spec is the side-channel half).
> Sister spec — [`18-text-normalization.md`](18-text-normalization.md).
> 18 covers _which glyphs map to which ASCII_; 20 covers _how
> typographic features are preserved as data_ even after the glyph
> itself is normalized away.
> Data-model owner — **pd-book-tools**
> (`pd_book_tools.ocr.glyph_annotations` — NEW, not yet shipped).
> Predictions producer — **pd-ocr-trainer**
> (glyph-feature classifier — NEW, not yet shipped).
> Driver consumer — **pd-ocr-labeler-driver**
> (bulk-mark automation; testids §6).

---

## 1. Principle

**GT text is canonical and ASCII-clean.** GT NEVER contains Unicode
presentation-form ligatures (no `U+FB00`–`U+FB06`: `ﬀ`, `ﬁ`, `ﬂ`,
`ﬃ`, `ﬄ`, `ﬅ`, `ﬆ`). GT NEVER contains `U+017F` (long-s `ſ`). The
labeler enforces this on save: a GT field containing any forbidden
codepoint is rejected with a `validation_error`
([`02-backend.md`](02-backend.md) §error-envelope).

**Typography is preserved out-of-band.** Each `WordMatch` may carry an
optional `glyph_annotations` field that records the typographic
features the canonical GT discards. Three concepts in v1:

- **Ligature marks** — "this word's `c`+`t` is a ct-ligature
  glyph", "this `s`+`t` is the st-ligature".
- **Long-s positions** — character offsets in the GT string where the
  printed glyph is `ſ` even though GT spells it `s`.
- **Swash flag** — boolean: this word is set in a swash (decorative
  cap) variant.

**Tri-state per word.** `glyph_annotations is None` means _not yet
reviewed_. `glyph_annotations = GlyphAnnotations()` (empty but
present) means _reviewed, nothing to mark_. This distinction drives
the progress metric (§5).

**The classifier is advisory.** When pd-ocr-trainer ships a
glyph-feature classifier, its output enters the envelope as
**predictions** (greyed-out chips). Only a human-confirmed annotation
counts toward "reviewed".

---

## 2. Where this lives

| Concern | Owner | Status |
|---|---|---|
| `GlyphAnnotations` data model + JSON shape | `pd_book_tools.ocr.glyph_annotations` | NEW — needs delegation to pd-book-tools |
| Per-word predictions producer | pd-ocr-trainer (glyph-feature classifier) | NEW — needs delegation to pd-ocr-trainer |
| Envelope schema bump (v2.1 → v2.2) | THIS SPEC + [`01-data-models.md`](01-data-models.md) §3, §4 | NEW |
| `<GlyphAnnotationPanel>` + chip widget | THIS SPEC | NEW |
| Per-page bulk-mark endpoints | THIS SPEC §4 | NEW |
| testid additions for driver bulk-mark | THIS SPEC §6, [`13-driver-contract.md`](13-driver-contract.md) | NEW |

The SPA ships **no** glyph-feature classifier itself. It surfaces
predictions from pd-ocr-trainer when present; otherwise the panel
operates in pure manual mode.

---

## 3. Shared data model (defined in pd-book-tools)

The Pydantic shape consumed by the envelope and wire types:

```python
# pd_book_tools.ocr.glyph_annotations
class LigatureKind(StrEnum):
    CT = "CT"     # c + t
    ST = "ST"     # s + t  (printed-s + t, i.e. the st-ligature)
    LONG_ST = "LONG_ST"  # ſ + t (long-s + t, the ﬅ form)
    FI = "FI"
    FL = "FL"
    FFI = "FFI"
    FFL = "FFL"
    OE = "OE"     # œ (when printed as a ligature)
    AE = "AE"     # æ (when printed as a ligature)

class LigatureMark(BaseModel):
    kind: LigatureKind
    char_span: tuple[int, int] | None = None   # [start, end) in GT chars; None = whole word

class GlyphAnnotations(BaseModel):
    ligatures: list[LigatureMark] = []
    long_s_positions: list[int] = []      # char offsets in GT where printed glyph is ſ
    swash: bool = False

    # Provenance: how each top-level signal got here.
    source: Literal["human", "predicted", "human_confirmed"] = "human"
    # "predicted" = classifier-only, awaiting confirmation
    # "human_confirmed" = classifier was right, human kept it
    # "human" = entered/edited by human, no classifier involvement
```

**Provenance is per-`GlyphAnnotations` object** in v1 (not per-mark).
This keeps the model simple; if mixed-source granularity is needed
later, we bump again.

`WordMatch` ([`01-data-models.md`](01-data-models.md) §1) gains:

```python
class WordMatch(BaseModel):
    # ... existing fields unchanged ...
    glyph_annotations: GlyphAnnotations | None = None
    glyph_predictions: GlyphAnnotations | None = None  # classifier output, not yet confirmed
```

`glyph_annotations` is the **confirmed** state (drives save).
`glyph_predictions` is the **classifier suggestion**, kept on the
in-memory model for UI overlay; it is NOT persisted in the envelope —
re-running the classifier is cheap, persisting predictions creates
staleness.

---

## 4. Envelope schema delta — v2.1 → **v2.2**

**Bump rationale.** v2.1 has been wire-shared with the legacy labeler.
The legacy labeler does not know about `glyph_annotations`. Bumping to
v2.2 lets us add the field cleanly while §4 of
[`01-data-models.md`](01-data-models.md) (versioning policy) covers
back-compat: v2.2 is **additive** — readers of v2.1 must accept v2.2
envelopes if they tolerate unknown nested fields.

**Verification step before SPA writes v2.2.**  Confirm the legacy
labeler's `UserPageEnvelopeSchema` Pydantic config tolerates the new
field on read. If `extra="forbid"` rejects: SPA writes v2.1 envelopes
until legacy is patched, and stores annotations in a sidecar
`<labeled-projects>/<project_id>_<page:03d>.glyph.json` (mirror of
Q-A1's fallback approach for rotation). Q-A5 below tracks this.

### 4.1 Schema delta

```jsonc
{
  "schema": {"name": "pd_ocr_labeler.user_page", "version": "2.2"},  // ← bumped
  // ... unchanged through provenance / source / cached_images ...
  "payload": {
    "page": { /* unchanged */ },
    "original_page": { /* unchanged */ },
    "word_attributes": { /* unchanged */ },
    "glyph_annotations": {                  // ← NEW, optional
      "<word_id>": {
        "ligatures": [
          {"kind": "CT", "char_span": [2, 4]}
        ],
        "long_s_positions": [0],
        "swash": false,
        "source": "human"
      }
    }
  }
}
```

Storage shape: a flat `dict[word_id, GlyphAnnotations]` keyed by the
stable `word_id` already present on `WordMatch` (
[`01-data-models.md`](01-data-models.md) §1). Words with no
annotations are simply absent from the dict. **Absence ≠ empty
GlyphAnnotations()**: an absent key means `glyph_annotations = None`
on the rebuilt `WordMatch` ("not reviewed"). An empty
`GlyphAnnotations()` written to the dict means "reviewed, nothing".
This three-state distinction is preserved across save/load.

### 4.2 Reader / writer rules

`core/persistence/user_page_envelope.py`
([`01-data-models.md`](01-data-models.md) §3.UserPageEnvelope):

- On read of a v2.1 envelope: every `WordMatch.glyph_annotations` is
  `None` (legacy data has no opinion).
- On read of a v2.2 envelope: rebuild from `payload.glyph_annotations`.
- On write: SPA always emits v2.2 if the page has any non-None
  annotation OR Q-A5 resolves to "legacy tolerates v2.2"; otherwise
  the SPA may emit v2.1 (no annotations) for backward safety.
- Predictions (`glyph_predictions`) are NEVER written to the envelope.

### 4.3 Legacy compatibility & migration

Until the legacy labeler is patched (likely never — it's slated for
removal), saving a v2.2 envelope is a one-way door for that page:
legacy reads might error or silently drop the field. The SPA logs a
WARN once per session the first time it writes v2.2.

---

## 5. UI components

### 5.1 New: `<GlyphAnnotationPanel>`

Lives in `frontend/src/components/glyph/GlyphAnnotationPanel.tsx`.

Opens **inside** the existing `<WordEditDialog>`
([`07-word-edit-dialog.md`](07-word-edit-dialog.md)) as a new
collapsible section "Typography". Also accessible without opening the
dialog: a small chip-row appears under each `<WordCell>` GT input
([`05-word-matches.md`](05-word-matches.md)) when the word has
annotations or predictions. Clicking the chip-row opens the panel as
a popover anchored to the word.

Layout:

```
Typography
─────────────────────────────────
Ligatures            [+ Add ▼]
  • CT  c|t  [×]
  • ST  s|t  [×]
  ◌ FL  f|l  (predicted) [✓ accept] [× reject]

Long-s positions      [+ Add ▼]
  • char 0 (s → ſ)  [×]

Swash                 ☐
─────────────────────────────────
[Mark reviewed (no marks)]   [Reset]
```

- Solid bullets (`•`) = confirmed (`source` includes `human` or
  `human_confirmed`).
- Hollow bullets (`◌`) = predicted-only. Show `(predicted)` label,
  greyed text, `accept` / `reject` buttons.
- "Mark reviewed (no marks)" stamps an empty `GlyphAnnotations()` for
  the word — moves it from "not reviewed" (None) to "reviewed,
  nothing".
- "Reset" clears `glyph_annotations` back to `None`.

Char-span picker for ligatures: shows the GT string with clickable
character cells; user shift-clicks to select a span. For words ≤8
chars the picker is inline; longer words use a small modal.

Long-s position picker: same character-cell strip, single-click toggles
each position.

### 5.2 New: `<GlyphChip>`

`frontend/src/components/glyph/GlyphChip.tsx`. Tiny pill rendered
inline under `<WordCell>` GT input:

```
[CT] [ST] [ſ:0]      ← solid (confirmed)
[FI?]                ← hollow (predicted only)
```

Clicking any chip opens the panel. Used in two places:

- Right-pane `<WordCell>` (compact view).
- `<WordEditDialog>` chip row above the Typography section.

### 5.3 Modified: `<WordCell>`

`frontend/src/components/WordCell.tsx`
([`05-word-matches.md`](05-word-matches.md)) gains:

- **Corner badge** `data-testid="word-glyph-badge-{line}-{word}"`:
  a 6×6px square in the cell's top-right, colored:
  - hidden — `glyph_annotations is None and glyph_predictions is None`
  - amber — `glyph_predictions is not None and glyph_annotations is None`
    ("review pending")
  - blue — `glyph_annotations is not None`
    (any state of reviewed, including empty)
  - green — `glyph_annotations is not None` AND it has at least one
    mark (ligatures non-empty OR long_s_positions non-empty OR swash)
- **Chip row** rendered below the GT input when any annotations or
  predictions exist.

### 5.4 Modified: `<WordEditDialog>`

[`07-word-edit-dialog.md`](07-word-edit-dialog.md): add a new
"Typography" section between the existing tag-chips row and the
preview-column row. Section is collapsed by default; auto-expands when
the word has predictions awaiting review.

### 5.5 New: `<BulkGlyphMarkDialog>` (page-scope)

Triggered from `<ToolbarActionGrid>`
([`06-toolbar-actions.md`](06-toolbar-actions.md)) — a new Page-scope
button "Bulk-mark glyphs". Dialog presents a small recipe DSL:

```
Mark all CT ligatures in unflagged words where:
  ☑ GT contains "ct"
  ☐ Predicted by classifier
  ☐ Override existing annotations

Preview: 47 words will be modified.
[Cancel]  [Apply]
```

Three preset recipes ship in v1:

- **CT auto-mark** — every word whose GT contains the substring `ct`
  gets a `LigatureMark(kind=CT, char_span=<the c-t pair>)`.
- **ST auto-mark** — same for `st`.
- **Long-s by typeset-era** — for every lowercase `s` not at end-of-word
  AND not before `b/k/h/f` (typesetter rules), add to
  `long_s_positions`. (Off by default, opt-in: this is heuristic.)

The recipe list is data-driven; pd-book-tools may add more profiles
later (e.g., per-typeface). v1 ships only the three above.

This is the surface the **pd-ocr-labeler-driver** agent will automate
for unattended bulk marking on a project — see §6 for testids.

### 5.6 New: predictions overlay on `<PageImageCanvas>`

Optional, M11.x polish — ghost-color outlines on words with
`glyph_predictions != None and glyph_annotations is None`, so the user
can see at-a-glance which words the classifier wants attention on.
Toggle in `<ImageTabsHeader>` ("Show prediction hints").

---

## 6. Backend FastAPI endpoints

All under `api/words.py` and `api/pages.py`. Wire shapes added to
[`01-data-models.md`](01-data-models.md) §2.

### 6.1 Per-word

```python
# POST /api/projects/{project_id}/pages/{idx0}/words/{line}/{word}/glyph-annotations
class SetGlyphAnnotationsRequest(BaseModel):
    annotations: GlyphAnnotations | None    # None = unset (back to "not reviewed")

class SetGlyphAnnotationsResponse(BaseModel):
    word: WordMatch     # echoes updated state, including any predictions

# POST .../accept-prediction
class AcceptGlyphPredictionRequest(BaseModel):
    pass    # confirms current predictions wholesale → annotations with source="human_confirmed"
```

Setting annotations = None on a word with active predictions does NOT
clear the predictions (those come from the classifier; only re-running
the classifier clears them).

### 6.2 Page-scope bulk

```python
# POST /api/projects/{project_id}/pages/{idx0}/glyph-bulk-mark
class GlyphBulkMarkRequest(BaseModel):
    recipe: Literal["ct_substring", "st_substring", "long_s_typeset_era"]
    skip_already_annotated: bool = True
    accept_predictions: bool = False    # if true, also confirm matching predictions
    dry_run: bool = False               # if true, return preview without mutating

class GlyphBulkMarkResponse(BaseModel):
    affected_word_ids: list[str]
    skipped_word_ids: list[str]
    page: PagePayload | None    # populated unless dry_run
```

**No new SSE jobs in v1.** Page-scope bulk is fast (≤ a few thousand
words per page); it runs synchronously like other page mutations.
Project-wide bulk is explicitly out of scope; if the driver needs to
mark across many pages, it iterates per-page through the existing
`pd-ocr-labeler-driver` machinery.

### 6.3 Predictions ingest

The classifier from pd-ocr-trainer is consumed via the existing OCR
adapter pattern ([`02-backend.md`](02-backend.md) §adapters):

```python
# core/glyph/predictions.py (NEW)
class IGlyphPredictor(Protocol):
    def predict(self, page: Page) -> dict[str, GlyphAnnotations]: ...
        # keyed by word_id; values have source="predicted"
```

Adapter `none` (default — no classifier wired) returns `{}`. Adapter
`local_pdtrainer` calls into pd-ocr-trainer when present.

Predictions populate `WordMatch.glyph_predictions` on every page
fetch (cheap — runs over the in-memory `Page`). Predictions are NOT
persisted; restart re-runs the classifier.

---

## 7. `data-testid` additions

To be added to [`13-driver-contract.md`](13-driver-contract.md) §2 in
a new subsection "2.x Glyph annotations":

| testid | What it is |
|---|---|
| `word-glyph-badge-{line}-{word}` | Corner badge on `<WordCell>`; absent when no annotations/predictions |
| `word-glyph-chip-row-{line}-{word}` | Chip row under GT input |
| `word-glyph-chip-{line}-{word}-{kind}` | Individual chip (`kind` = `ct`, `st`, `long_s`, `fi`, …, `swash`, `predicted-{kind}`) |
| `glyph-panel-{line}-{word}` | The `<GlyphAnnotationPanel>` popover/section |
| `glyph-panel-add-ligature` | "Add ligature" button inside panel |
| `glyph-panel-ligature-kind-select` | Ligature kind enum picker |
| `glyph-panel-charspan-cell-{i}` | i-th char-cell in the span picker |
| `glyph-panel-long-s-cell-{i}` | i-th char-cell in the long-s picker |
| `glyph-panel-swash-checkbox` | Swash toggle |
| `glyph-panel-mark-reviewed-empty` | "Mark reviewed (no marks)" button |
| `glyph-panel-reset` | "Reset" → set annotations back to None |
| `glyph-panel-accept-prediction-{kind}` | Accept a single predicted mark |
| `glyph-panel-reject-prediction-{kind}` | Reject a single predicted mark |
| `bulk-glyph-mark-button` | Toolbar entry that opens the bulk dialog |
| `bulk-glyph-mark-dialog` | The `<BulkGlyphMarkDialog>` |
| `bulk-glyph-recipe-select` | Recipe dropdown |
| `bulk-glyph-skip-annotated-checkbox` | "Skip already annotated" |
| `bulk-glyph-accept-predictions-checkbox` | "Also confirm matching predictions" |
| `bulk-glyph-dry-run-button` | Preview button |
| `bulk-glyph-apply-button` | Apply button |
| `bulk-glyph-preview-count` | Span containing the preview count text (`47 words will be modified`) |
| `predictions-overlay-toggle` | `<ImageTabsHeader>` checkbox for prediction hints overlay |

The driver agent uses `bulk-glyph-*` to script unattended runs across a
labeled corpus. The `{line}-{word}` parameterised testids let it
target specific words by index.

---

## 8. Progress metric

Page progress today (legacy + spec) is "fraction of words validated".
Annotation review is **a separate axis**: a word can be GT-validated
without its glyphs being reviewed.

**Decision: introduce a second metric, do NOT merge.** Page header
shows two numbers:

```
Validated  47/120        Glyphs reviewed  12/120
```

Where "glyphs reviewed" counts words with `glyph_annotations is not
None` (regardless of whether the annotations are empty). This keeps
the existing "validated" metric byte-identical with legacy and avoids
breaking the validation-progress test fixtures.

If the project's OCR config has `glyph_review_required: false`
(default), the second metric renders muted/optional. When `true`, the
metric is prominent and Save Project warns if any page has unreviewed
glyphs (mirrors the existing unvalidated-words warning).

`OCRConfig` gains:

```yaml
glyph_review_required: false   # default — opt-in
```

---

## 9. Predictions data path

End-to-end:

1. **Training time** (out of repo). pd-ocr-trainer trains a
   classifier; ships weights + an inference adapter.
2. **OCR time** (SPA). When the SPA runs OCR on a page (or loads cached
   OCR), the configured `IGlyphPredictor` runs on the resulting `Page`
   and produces `dict[word_id, GlyphAnnotations(source="predicted")]`.
3. **Wire**. The mapping is attached to the `PagePayload`'s
   `LineMatch[].word_matches[].glyph_predictions` field.
4. **UI**. `<GlyphChip>` and `<GlyphAnnotationPanel>` render predicted
   marks as hollow bullets / `(predicted)` label.
5. **Confirmation**. User clicks `accept` → POST `accept-prediction`
   → backend writes `glyph_annotations = predictions` with
   `source="human_confirmed"`. Predictions remain on the in-memory
   word but are now subordinate to the confirmed annotations.
6. **Persistence**. Save writes `glyph_annotations` only.
   `glyph_predictions` is regenerated on next load.

If the classifier is unavailable (adapter = `none`):
`glyph_predictions` is always `None`. UI hides all
prediction-specific affordances. Manual editing via the panel works
exactly the same.

---

## 10. Tests

- Unit (backend): `test_glyph_annotations_envelope.py` — round-trip
  v2.2 with mixed annotation states (None, empty, populated).
- Unit (backend): `test_glyph_envelope_back_compat.py` — v2.1 envelope
  reads as all-None annotations.
- Unit (backend): `test_glyph_bulk_mark.py` — each recipe applied to a
  fixture page produces the right `affected_word_ids`.
- Unit (backend): `test_gt_rejects_ligature_codepoints.py` — POST GT
  containing `ﬁ` returns 400.
- Frontend unit: `<GlyphChip>` renders predicted vs confirmed with
  correct testids.
- Frontend unit: `<GlyphAnnotationPanel>` char-span picker emits
  correct `[start, end)` for click+shift-click.
- Playwright: `test_glyph_panel.py` — open dialog, add CT ligature,
  save, reload, see chip persist.
- Playwright: `test_bulk_glyph_mark.py` — run CT recipe on a fixture
  page with 5 `ct` words, see preview count = 5, apply, see 5 chips.
- Driver-contract: every testid listed in §7 asserted in the
  conformance test (extends [`13-driver-contract.md`](13-driver-contract.md)).

---

## 11. Open issues

- **Q-A5** (legacy v2.2 tolerance). See §4. Listed in
  [`OPEN_QUESTIONS.md`](../OPEN_QUESTIONS.md).
- **Q-A6** (predictions-overlay color). What color is the ghost outline
  on the canvas? Recommend amber-50 to match the corner-badge palette.
  Listed in [`OPEN_QUESTIONS.md`](../OPEN_QUESTIONS.md).
- **Q-A7** (per-mark provenance). v1 puts `source` at the
  `GlyphAnnotations` level, not per-`LigatureMark`. Is this granular
  enough? Listed in [`OPEN_QUESTIONS.md`](../OPEN_QUESTIONS.md).
- **Profile registry overlap** with [`18-text-normalization.md`](18-text-normalization.md).
  Both specs reference future "fraktur"/"gaelic" profiles. The glyph
  classifier and the normalization map should share a profile name
  (so a "fraktur" project gets both fraktur normalization and a
  fraktur-trained classifier). Resolution lives in pd-book-tools.
- **Cross-page bulk mark** is out of v1 scope. If the driver needs it,
  it iterates per-page. A future M with project-wide bulk + SSE
  progress could add it.

# Open Questions for `pd-ocr-labeler-spa`

> **Resolved questions are archived in [`docs/archive/QUESTIONS_RESOLVED.md`](docs/archive/QUESTIONS_RESOLVED.md).**
> Only currently-open questions live below. When a question is answered, move
> its full entry to the archive in the same commit that lands the resolution
> ADR (see [`docs/DEVELOPMENT.md` § Archive on close](docs/DEVELOPMENT.md#archive-on-close)).

Questions the spec authors could not resolve from the source material alone.
Each entry: **Q** (the question), **Context** (why it matters), **Options**
(with trade-offs), **Recommendation** (spec author's bet), **Blocks** (which
milestones can't start until resolved). Once the user answers, a **Resolution**
line links the resulting ADR and the entry moves to the archive.

---

## Open — needs user input

---

### Q-A14 — M4 renderer: must Konva be validated by spike before M4 starts?
> GitHub: ConcaveTrillion/pd-ocr-labeler-spa#55

**Q.** Spec 04 (`specs/04-image-viewport.md`) is written for Konva, but explicitly
notes that a spike at M4 start may recommend raw canvas instead. Must the spike be
completed and an ADR committed to `specs/17-decisions.md` *before* any M4 component
code is written? And if the spike recommends raw canvas, how much of spec 04 needs
revision before implementation proceeds?

**Context.** M4 introduces the image viewport with paragraph/line/word bbox overlays.
Konva is the current default, but raw canvas may outperform it at 4K-page scale
(many hundreds of overlay rects). Committing component code before the spike risks
rewriting `BBoxOverlay.tsx`, `PageImageCanvas.tsx`, and related drag-selection logic
if the recommendation changes.

**Options.**

- (A) Spike is mandatory before any M4 component code lands. Spike result → ADR →
  spec 04 revision (if needed) → implementation. Higher upfront cost; no rewrite risk.
- (B) Start M4 with Konva, treat the spike as an optional optimisation later. Lower
  upfront cost; rewrite risk if 4K-page performance is unacceptable.

**Recommendation.** (A) — the spec author's bet. A spike on a single fixture 4K page
costs one session; a post-hoc rewrite of the full overlay system costs more.

**Blocks.** M4 component implementation.

**Owner.** CT.

**Status.** Open.

---

### Q-A5 — Does the legacy labeler tolerate a v2.2 `UserPageEnvelope` (with `glyph_annotations`)?
> GitHub: ConcaveTrillion/pd-ocr-labeler-spa#56

**Q.** When the SPA saves a page that has any glyph annotation, it bumps the
envelope's `schema.version` to `"2.2"` and writes a `glyph_annotations` key
into the payload. The legacy labeler's `UserPageEnvelopeSchema` Pydantic model
may have `extra="forbid"`, which would cause it to reject v2.2 envelopes
outright. Does the legacy labeler tolerate these new nested fields on read, or
does it crash?

**Context.** `specs/20-glyph-annotations.md` §4 describes the v2.1→v2.2 schema
delta. The SPA's writer rule (§4.2) is: "emit v2.2 if the page has any non-None
annotation OR Q-A5 resolves to 'legacy tolerates v2.2'; otherwise the SPA may
emit v2.1 for backward safety." Without resolving this question, the SPA cannot
decide whether to write v2.2 envelopes or fall back to the sidecar approach
(`<project_id>_<page:03d>.glyph.json`). This blocks M11.

**Options.**

- **(A) Legacy tolerates v2.2.** `UserPageEnvelopeSchema` uses `extra="ignore"`
  (or `extra="allow"`) and silently drops `glyph_annotations`. SPA writes v2.2
  freely. No sidecar needed.
- **(B) Legacy rejects v2.2.** SPA writes v2.1 envelopes and stores glyph
  annotations in a sidecar file (mirror of D-032 / Q-A1 fallback). A future
  legacy patch then absorbs the sidecar into the envelope.
- **(C) Probe at runtime.** SPA sends a test v2.2 envelope write in a dry-run
  check during startup (or on first save) and auto-selects (A) vs (B).

**Recommendation.** **(A)** if confirmed by reading the legacy labeler's Pydantic
model config; fall back to **(B)** if the legacy uses `extra="forbid"` — sidecar
is safe and reversible. A `pd-ocr-labeler` agent read of the Pydantic config would
settle this in minutes.

**Blocks.** M11 (glyph annotations milestone) — `specs/16-milestones.md` §M11
pre-conditions.

**Owner.** CT.

**Status.** Open.

---

### Q-A6 — Predictions-overlay ghost color on `<PageImageCanvas>`
> GitHub: ConcaveTrillion/pd-ocr-labeler-spa#57

**Q.** What color should the ghost outline be on `<PageImageCanvas>` for words
that have classifier predictions (`glyph_predictions != None`) but no confirmed
annotation yet (`glyph_annotations is None`)? The spec's current placeholder
recommendation is amber-50 to match the corner-badge palette.

**Context.** `specs/20-glyph-annotations.md` §5.6 describes the optional
predictions overlay: "ghost-color outlines on words with `glyph_predictions != None`
and `glyph_annotations is None`." The corner badge is already amber (`#FFF7ED` /
Tailwind `amber-50`) when predictions exist. Picking a consistent color now
prevents a design revision after M11 ships. The overlay toggle testid
`predictions-overlay-toggle` is already in the driver contract.

**Options.**

- **(A) Amber-50 (`#FFF7ED`).** Matches the corner badge; consistent amber =
  "prediction, needs review" palette. Apply at ~40% opacity so the page image
  remains legible beneath the ghost outline.
- **(B) A distinct hue.** E.g. sky-blue or purple, to visually separate "overlay
  on canvas" from "badge in word cell."
- **(C) Defer to M11.x polish.** Spec already calls this "Optional, M11.x
  polish" — decide the color in that milestone rather than now.

**Recommendation.** **(A)** — amber-50 at 40% opacity; consistent with the badge palette.

**Blocks.** M11 (`specs/16-milestones.md` §M11 pre-conditions).

**Owner.** CT.

**Status.** Open.

---

### Q-A7 — Per-mark provenance: is object-level `source` granular enough?
> GitHub: ConcaveTrillion/pd-ocr-labeler-spa#58

**Q.** In v1, `GlyphAnnotations.source` is a single `Literal["human",
"predicted", "human_confirmed"]` field on the whole `GlyphAnnotations` object —
not per `LigatureMark`, not per `long_s_positions` entry. Is that granularity
sufficient, or do we need provenance at the individual mark level?

**Context.** `specs/20-glyph-annotations.md` §3 states: "Provenance is
per-`GlyphAnnotations` object in v1 (not per-mark). This keeps the model
simple; if mixed-source granularity is needed later, we bump again." A typical
mixed-source scenario: the classifier predicted 2 ligature marks correctly; the
human then manually added a third ligature mark and corrected a long-s position.
With object-level provenance, the whole `GlyphAnnotations` becomes `"human"`,
losing the fact that 2 marks were originally predicted. This is a schema design
decision that is hard to change post-M11 without a v2.3 envelope bump.

**Options.**

- **(A) Keep object-level provenance.** Accept the simplification for v1; spec
  explicitly plans "bump if needed."
- **(B) Per-mark provenance now.** Add `source` to `LigatureMark`, add
  `long_s_sources: list[Literal[...]]` parallel to `long_s_positions`, and add
  `swash_source`. More complex model, but avoids a future schema bump.
- **(C) Hybrid.** Keep `GlyphAnnotations.source` as the "dominant" signal, plus
  an optional `mark_sources: dict[int, Literal[...]]` escape hatch.

**Recommendation.** **(A)** — object-level is consistent with D-032 (rotation
provenance); the spec explicitly names the trade-off; a v2.3 bump is low-cost if
the need materializes.

**Blocks.** M11 data-model lock-in (`specs/16-milestones.md` §M11 pre-conditions).

**Owner.** CT.

**Status.** Open.

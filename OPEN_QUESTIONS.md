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

### Q-A5 — Does the legacy labeler tolerate a v2.2 `UserPageEnvelope` (with `glyph_annotations`)?
> GitHub: ConcaveTrillion/pd-ocr-labeler-spa#56 — **CLOSED**

**Resolution.** The legacy labeler uses hand-rolled `from_dict` (pure `data.get`
— no Pydantic, no strict validation). Extra/unknown fields are silently ignored.
A v2.2 envelope is loaded without error; the new fields are simply never accessed.
**No compatibility shim needed** for the read path. The write path would strip
new fields (legacy `to_dict` only emits the five fields it knows), which is
acceptable during the transition window. Option **(A)**: SPA writes v2.2 freely.

**Status.** Resolved 2026-05-11.

---

### Q-A6 — Predictions-overlay ghost color on `<PageImageCanvas>`
> GitHub: ConcaveTrillion/pd-ocr-labeler-spa#57 — **CLOSED**

**Resolution.** Translucent blue (`#3B82F6` / Tailwind `blue-500`) at 40%
opacity, exposed as CSS custom property `--predictions-ghost-color` on `:root`
so operators can theme it without a code change.
Spec updated: `specs/20-glyph-annotations.md` §5.6.

**Status.** Resolved 2026-05-11.

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

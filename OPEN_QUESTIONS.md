---
kind: context
status: active
owner: maintainers
created: 2026-05-06
last_verified: 2026-11-11
---

# Open Questions for `pdomain-ocr-labeler-spa`

> **Resolved questions are recorded in [`docs/context/decisions.md`](docs/context/decisions.md) and Git history.**
> Only currently-open questions live below. When a question is answered, remove
> its full entry in the same commit that records the durable decision.

Questions the spec authors could not resolve from the source material alone.
Each entry: **Q** (the question), **Context** (why it matters), **Options**
(with trade-offs), **Recommendation** (spec author's bet), **Blocks** (which
milestones can't start until resolved). Once the user answers, a **Resolution**
line links the resulting ADR and the entry moves to the archive.

---

## Open questions

### OQ-TYPO-1 — Where do typography suggestions come from, and what does one look like?

- **Q:** What record, store, producer, and API carry typography suggestions into the SPA?
- **Context:** The typography spec lists what a suggestion must show and says accepting or
  editing one creates human evidence. Nothing produces or stores a suggestion today: the SPA has
  no F2, Gutenberg, rule, or model typography projection, and `pdomain-book-contracts` 0.3.0
  defines no suggestion or prediction record, only a `prediction_id` field on a span. The spec also
  says model suggestions arrive only after the manual path passes end-to-end tests. Accept and
  edit controls cannot be built until a suggestion exists to accept.
- **Options:** (a) Define a portable suggestion record in `pdomain-book-contracts` and a
  read-only per-page suggestion sidecar in the SPA, filled by an import from
  `pdomain-source-data` bundles. (b) Project PGDP F2 italic, bold, and small-caps markup inside
  the SPA from the existing alignment. (c) Wait for the typography model.
- **Recommendation:** (a). It keeps the SPA a reviewer, not a producer, as the spec's repository
  boundaries describe.
- **Blocks:** typography suggestion accept and edit.

### OQ-TYPO-2 — What does predecessor-based compensating undo append?

- **Q:** How does undo and redo of one word's typography correction work in the append-only
  journal?
- **Context:** The spec names predecessor-based compensating undo and requires an end-to-end
  test of edit, reload, undo, redo, export, and record equality. It does not define the
  behaviour. Open points:
  1. Undoing revision 1 has no predecessor. `CorrectionDecision` has no value that returns a word
     to unreviewed, and `defer` is a human decision, not a reversal.
  2. A compensating record must rebind to the current page, image, text hash and word revision.
     If the text changed since the predecessor, its spans may no longer fit.
  3. Redo needs to know which record an undo reversed. `TypographyCorrection` and
     `TypographyReviewMetadata` have no field for that; only a free-text `note` exists.
  4. The control's place in the UI, its keyboard binding, and its driver test IDs are not
     specified. Page-history undo must not drive it, per the spec.
- **Options:** (a) Add an `undo_of` field and a revert decision to the contract, then append a
  copy of the predecessor head rebound to current hashes, refusing when the text has changed.
  (b) Keep the contract and encode the link in `note`. (c) Give undo only for revision 2 and later.
- **Recommendation:** (a). A structured link keeps the journal auditable and export-safe.
- **Blocks:** typography predecessor undo and redo, and the correction-bundle end-to-end
  acceptance test.

---
kind: context
status: active
owner: maintainers
created: 2026-07-13
last_verified: 2026-11-12
---

# Intent map

This is the roadmap. Shipped behavior lives in [`docs/architecture/`](../architecture/00-overview.md). The three plans
under `docs/plans/` keep implementation steps for items named here. Do not treat `specs/16-milestones.md` as the live list.

## Agent Index

- **Kind:** context
- **Status:** active
- **Owner:** maintainers
- **Last verified:** 2026-11-12
- **Read when:** deciding what to build next, what remains intentionally
  parked, or which repository should own a new job.
- **Search terms:** roadmap, active intent, deferred, blocked, rejected,
  owner decision, separate repository, typography undo, glyph enum, U-M6.

## Now

Build these in this repository.

- Finish suggestion accept and edit, and predecessor-based compensating undo, for the shipped typography journal. Phase
  one is in [typography review](../architecture/31-typography-review.md).
- Make the glyph picker list every shared ligature kind from `pdomain-book-contracts`. Include `LONG_ST`, `OE`, `AE`,
  `LONG_S_S`, `LONG_S_I`, `SP`, and `QU`. Keep `FF` and the `long_s_t` alias. Steps are in the [glyph plan](../plans/2026-07-21-glyph-annotations-completion.md).
- Hydrate ExportDialog from persisted export history so reopening it does not drop the run list. A failed history read
  must not look like an empty history. The [PGDP plan](../plans/2026-07-21-pgdp-alignment-remaining.md) has the
  acceptance check.
- Compare the local right-panel header, collapse controls, and body routing with the shared shell, and record whether
  shared framing is worth extracting. Do not replace the panel as part of the comparison.
- Reconcile driver-contract section 2.11 and its browser coverage with persistent right-panel editing. GitHub issue
  #454 is already deleted.
- Enable `noUncheckedIndexedAccess` in `tsconfig.test.json`. The
  [strictness plan](../plans/2026-07-21-tsconfig-test-strictness.md) is still unchecked. The flag is still false.
- Finish U-M6 history: cross-OCR and rotation-boundary traversal, page-slot lineage, and conservative pruning. U-M7
  listing and jumps already ship. The design remains in the [undo spec](../specs/2026-06-12-event-store-undo.md).
- Stop one `set_region_word_membership` write from renumbering every word on the page. `stable_word_id` hashes a
  page-wide reading order, and a region joins `page.lines`. So the write detaches typography journal rows keyed to the
  old ids. The docstring in `api/regions.py` records that. `tests/integration/test_region_membership_word_identity.py`
  pins today's behavior. This is outside the sidecar-reindex family closed on 2026-09-18. Line merge, split, and delete
  already renumber `page.lines` the same way.
- Reconcile behavior specs with the shipped UI. `docs/specs/behavior/component-dialogs-actions.md` still describes the
  removed word-edit dialog and character-range mutations. `docs/specs/behavior/unclear-items.md` still questions
  page-level erase, while `erase_page_pixels` exists. Check [`decisions.md`](decisions.md) before treating an unclear
  item as open.

## Next

These need another repository, or a short decision, before more labeler code.

- Add a predictor-build callback or structured events in `pdomain-book-tools`. This labeler already reports store
  lookup and one OCR stage. Eager startup warm-up stays rejected.
- Consume immutable typography snapshots in `pdomain-ocr-training` and `pdomain-ocr-trainer-spa`. Do not add a training
  loop here.
- Keep source ingestion and cross-corpus matching in `pdomain-source-data`. Do not start a second design for that job.

## Later

Worth doing, and not scheduled.

- Global jobs history, and export history beyond the dialog hydration in Now. Appearance preferences stay in
  localStorage. App preference persistence is a no-op.
- Mixed-selection and mutation-error browser coverage for multi-line editing. Existing browser tests are not a fresh
  full-suite run.
- Glyph per-mark provenance, cross-page bulk marking, and a profile registry. No predictor will be built in this app.
- Page-kind keyboard path, still separate from the shipped region keyboard loop.
- Driver and adapter documentation so the catalogue matches mounted components and explains the permanent local adapters.

## Separate repositories

Do not create a new repository for these. The checkouts already exist. Detail and the current pins are in [repository boundaries](../architecture/30-repository-boundaries.md).

- OCR runtime and a future predictor-progress callback: `pdomain-book-tools`.
- Glyph enum and other shared contracts: `pdomain-book-contracts`.
- Page records and suite plumbing: `pdomain-ops`.
- Shared chrome: `pdomain-ui`.
- PGDP pipeline: `pdomain-prep-for-pgdp`.
- PGDP API access: `pdomain-pgdp-api-client`.
- Source preparation: `pdomain-source-data`.
- Training and evaluation: `pdomain-ocr-training`.
- Trainer UI: `pdomain-ocr-trainer-spa`.
- Synthetic pages: `pdomain-ocr-synth`.
- Batch OCR CLI: `pdomain-ocr-cli`.

A glyph predictor, if it is ever built, goes in `pdomain-book-tools` or `pdomain-ocr-training`, not here and not in a
new repo.

Auth, S3, Postgres, and managed adapters stay deferred under D-042 until there is a deployment.

`ml-training` and `ml-validation` exist on disk and were not reviewed.

## Done

- **Converged PageRecord imports without widening the shared schema.** Callers import `PageRecord` and `RotationSource`
  from `pdomain_ops.pages`. The `core.models` compatibility exports are removed. Labeler-only view state stays in `extensions["labeler"]`.
- **Published contracts v0.3.0.** `pyproject.toml` requires `pdomain-book-contracts>=0.3.0`. `uv.lock` selects `0.3.0`.
  The P3-F2 branch merged to master as `1445e173`. This replaces the earlier local wheel and the v0.2.1 pin.
- **Enforced OpenAPI response contracts.** GitHub issue #437 is deleted.
- **Accepted resolver narrowing.** Page resolvers return `Page | None`. GitHub issue #460 is deleted.
- **Tagged the labeler `v0.3.0` on 2026-09-18.** `git rev-list --count v0.2.0..v0.3.0` is 645. The tag points at
  `06fc0440`. This is the app tag, not contracts `0.3.0`.
- **Closed the word-identity and empty-page races** recorded on 2026-09-18. Coverage includes
  `tests/integration/test_typography_word_id_survives_gt_edit.py` and `tests/integration/test_page_history_consistency_race.py`.
- **Fixed region carry-forward** so a rejected proposal and a confirmed region whose decision missed the log both
  carry. Hand-drawn regions stay uncarried (`propose_regions.py::_origin_reference_for_region`). The right panel counts
  carried rejections and can bring one back. Reopening appends a `reopened` decision.
- **Fixed out-of-order page refetches** in commit `a0d79d5e`.
- **Fixed the eleven sidecar routes** on 2026-09-18 so char-bbox, glyph, and glyph-prediction maps follow structural
  edits. Word split refuses rather than orphan a word's sidecars.
- **Closed all six open findings**, including BUG-KBD-1/4/5, the XDG data root, empty OCR, zero-area placeholders, and
  hierarchy waits. Commit `6db2e42` registered `mod+,`, `mod+j`, and `mod+shift+r`. BUG-KBD-4 was already done. The
  ledger is [`open-findings.md`](open-findings.md). The 18 deep-review reports under `docs/issues/2026-07-21-*`, the
  two migrated GitHub records, and the same-day September reports are deleted. Tombstones are in [`decisions.md`](decisions.md).
- **Closed #404, #430, #433, #437, and #460.** The CI-equivalence and OpenAPI-drift issues became moot when the named
  GitHub workflows were deleted.
- **Shipped manual glyph review, bulk apply, and the glyph sidecar export.** A person marks ligatures, long s, or
  swash, or marks a word reviewed with none. The mark survives save and reload. Export writes
  `recognition/glyph_features.json`, keyed by crop id, from `core/jobs/handlers/glyph_sidecar.py`. Chips select the
  word and open the panel. Browser coverage is `tests/e2e/test_glyph_panel.py` and `tests/e2e/test_bulk_glyph_mark.py`.
  No predictor exists, and the accept-prediction control never fires.
- **Shipped cold-page jobs and U-M7 history jumps.** See [page loading and history](../architecture/29-page-loading-and-history.md).
- **Removed the legacy character-range API.** See [typography review](../architecture/31-typography-review.md).

## Deferred

- Managed auth, S3, Postgres, and managed-adapter deployment stay under D-042.
- Server preference persistence stays deferred. D-042 bars a preferences API until the owner re-authorizes that
  deployment work. It is not implied by the remaining PGDP-alignment plan.

## Blocked

No product-direction blocker is established by current repository evidence. Finer load progress waits on an upstream
callback, which is listed under Next, not as a blocked product decision.

## Rejected

- Do not add the PGDP 24-stage pipeline, stage folders, or submit-check workflow to this labeler.
- Do not restore the standalone word-edit dialog. Persistent right-panel editing replaced it.
- Do not move labeler-only view state into the suite-wide PageRecord schema.
- Do not claim PageRecord import convergence if a second import path returns. The compatibility exports are already gone.
- Do not warm the OCR predictor at server start. It stays lazy.
- Do not build a glyph predictor in this app.
- Do not adopt a shared workbench layout or archive/restore. Project deletion stays permanent, with confirmation.

## Needs owner decision

- Preserve the shared-primitive and local-adapter split in `docs/architecture/03-frontend.md`. The September decision
  settles worklist ownership. It does not authorize a pipeline port.
- Decide whether the directory-level RUF002 exceptions in `pyproject.toml` are policy. GitHub issue #456 removed the
  global ignore. The remaining exceptions conflict with `CONVENTIONS.md`, which requires escaped ambiguous Unicode and
  rejects suppression.
- Choose which confidence and warning conditions exclude a word from bulk regular confirmation.
- Choose whether a quarantined word can be waived out of page completion, or must always leave the page incomplete.
- Choose reviewer identity for a local single-user install.
- Choose the required double-review rate and promotion thresholds.
- Choose the context window by pixel width, neighboring word count, or both.
- Choose JSONL, Parquet, or a paired manifest for portable typography exports.

## Legacy-unverified sweep

The 2026-07-13 checker-derived sweep classified all 118 legacy documents from code, tests, git history, and graph
links. Shipped architecture was declared `built`. Active process, runbook, behavior, milestone, and decision documents
remain live. Completed or superseded execution and research artifacts were retired. The durable changed directions and
residual intent are recorded here and in [`decisions.md`](decisions.md).

The 2026-11-12 pass did not reclassify those 118 documents. It moved current roadmap items into the sections above. It
left partial specs in place because their unfinished designs are still the source for Now and Next.

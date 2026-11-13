---
kind: context
status: active
owner: maintainers
created: 2026-07-13
last_verified: 2026-11-12
---

# Intent map

This is the roadmap. Shipped behavior lives in [`docs/architecture/`](../architecture/00-overview.md). Do not treat
`specs/16-milestones.md` as the live list.

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
  one is in [typography review](../architecture/31-typography-review.md). The open design questions are in
  [`OPEN_QUESTIONS.md`](../../OPEN_QUESTIONS.md).

## Next

These need another repository, or a short decision, before more labeler code.

- Add a predictor-build callback or structured events in `pdomain-book-tools`. This labeler already reports store
  lookup and one OCR stage. Eager startup warm-up stays rejected.
- Consume immutable typography snapshots in `pdomain-ocr-training` and `pdomain-ocr-trainer-spa`. Do not add a training
  loop here.
- Keep source ingestion and cross-corpus matching in `pdomain-source-data`. Do not start a second design for that job.

## Later

Worth doing, and not scheduled.

- Global jobs history, and export history beyond the saved-export list in the dialog. Appearance preferences stay in
  localStorage. App preference persistence is a no-op.
- Mixed-selection and mutation-error browser coverage for multi-line editing. Existing browser tests are not a fresh
  full-suite run.
- Glyph per-mark provenance, cross-page bulk marking, and a profile registry. No predictor will be built in this app.
  Bulk recipes still write legacy `ct` and `st`.
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
- **Refused verified image loads without memfd sealing.** `a09b50e6` raises `UnsupportedRuntimeError` and the API
  returns `503 unsupported_runtime`. Failed book loads close their session. There is no fallback. An agent made that
  choice on 2026-11-11, and the owner has not reviewed it. The issue file is retired in [`decisions.md`](decisions.md).
- **Enabled `noUncheckedIndexedAccess` in `tsconfig.test.json`.** Commit `9181753e` type-checks the test project with
  no suppressions. The strictness plan is retired.
- **Offered every shared ligature kind in the glyph picker.** Commit `b28085a7` writes the uppercase wire values,
  including `LONG_ST`, `OE`, `AE`, `LONG_S_S`, `LONG_S_I`, `SP`, and `QU`, and keeps `FF` and the `long_s_t` alias.
  Saved legacy lowercase marks keep their stored names.
- **Showed the saved export in ExportDialog.** Commit `18391dd5` reads the on-disk manifest. An unreadable manifest is
  `export_history_unreadable`, not an empty list.
- **Kept the right-panel frame local.** Commit `800a4dad` extracted nothing. An agent made the comparison on
  2026-11-11, and the owner has not reviewed it.
- **Aligned driver and shell docs with mounted components.** Commit `8391cddc` removes the retired word-edit dialog
  from the architecture docs and points erase mode at `rail-mode-erase`.
- **Drove driver-contract section 2.11 through the right panel.** The project-page smoke test clicks the pencil and
  waits for `word-detail`. The real-project exercise opens that panel from a worklist row. Neither test opens the
  retired modal.
- **Shipped U-M6 history boundaries.** Undo and redo follow page-slot lineage across a re-OCR or rotation boundary.
  A jump stays inside the active chain. `POST /api/projects/{project_id}/maintenance/prune` deletes only blobs the
  undo spec marks dead. U-M7 listing and jumps are unchanged. Coverage is
  `tests/integration/test_history_undo_redo.py` and `tests/unit/core/test_page_prune.py`.
- **Kept word ids across one region membership write.** The write stamps each word's reading order before it moves
  words, so typography journal rows stay on the same ids. Line merge, split, and delete still renumber `page.lines`.
  Coverage is `tests/integration/test_region_membership_word_identity.py`.
- **Reconciled the behavior specs with the mounted editor.** `docs/specs/behavior/component-dialogs-actions.md`
  describes the right panel. Character-range mutations are not a current write. Page-level erase is
  `erase_page_pixels`, so it is no longer an open question in `docs/specs/behavior/unclear-items.md`.

## Deferred

- Managed auth, S3, Postgres, and managed-adapter deployment stay under D-042.
- Server preference persistence stays deferred. D-042 bars a preferences API until the owner re-authorizes that
  deployment work. The retired shared-UI alignment does not authorize it.

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
